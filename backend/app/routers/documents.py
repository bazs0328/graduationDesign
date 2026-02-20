import hashlib
import glob
import os
import shutil
from datetime import datetime
from uuid import uuid4
import re

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc

from app.core.knowledge_bases import ensure_kb
from app.core.kb_metadata import (
    load_kb_metadata,
    record_file_hash,
    remove_file_hash,
    rename_file_hash,
    transfer_file_hash,
)
from app.core.paths import ensure_kb_dirs, ensure_user_dirs, kb_base_dir, user_base_dir
from app.core.users import ensure_user
from app.core.vectorstore import (
    delete_doc_vectors,
    get_doc_vector_entries,
    update_doc_vector_metadata,
)
from app.db import get_db
from app.models import (
    ChatMessage,
    ChatSession,
    Document,
    Keypoint,
    KeypointDependency,
    KeypointRecord,
    QARecord,
    Quiz,
    QuizAttempt,
    SummaryRecord,
)
from app.schemas import (
    DocumentOut,
    DocumentRetryRequest,
    DocumentRetryResponse,
    DocumentTaskCenterResponse,
    SourcePreviewResponse,
    DocumentUpdateRequest,
)
from app.services.lexical import move_doc_chunks, remove_doc_chunks, update_doc_chunks_metadata
from app.services.ingest_tasks import process_document_task
from app.utils.document_validator import DocumentValidator

router = APIRouter()


@router.get("/docs", response_model=list[DocumentOut])
def list_docs(
    user_id: str | None = None,
    kb_id: str | None = None,
    status: str | None = None,
    file_type: str | None = None,
    keyword: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, user_id)
    query = db.query(Document)
    query = query.filter(Document.user_id == resolved_user_id)
    if kb_id:
        query = query.filter(Document.kb_id == kb_id)
    if status:
        normalized = status.strip().lower()
        if normalized not in {"processing", "ready", "error"}:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        query = query.filter(Document.status == normalized)
    if file_type:
        normalized_file_type = file_type.strip().lower().lstrip(".")
        if normalized_file_type:
            query = query.filter(Document.file_type == normalized_file_type)
    if keyword:
        normalized_keyword = keyword.strip()
        if normalized_keyword:
            query = query.filter(Document.filename.ilike(f"%{normalized_keyword}%"))

    sort_columns = {
        "created_at": Document.created_at,
        "filename": Document.filename,
        "file_type": Document.file_type,
        "status": Document.status,
        "num_pages": Document.num_pages,
        "num_chunks": Document.num_chunks,
    }
    column = sort_columns.get(sort_by, Document.created_at)
    order_desc = (sort_order or "desc").strip().lower() != "asc"
    order_clause = desc(column) if order_desc else asc(column)
    return query.order_by(order_clause, Document.created_at.desc()).all()


def _get_doc_or_404(db: Session, user_id: str, doc_id: str) -> Document:
    doc = (
        db.query(Document)
        .filter(Document.id == doc_id, Document.user_id == user_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _find_raw_candidates(user_id: str, kb_id: str | None, doc_id: str) -> list[str]:
    if not kb_id:
        return []
    raw_dir = os.path.join(kb_base_dir(user_id, kb_id), "raw")
    return sorted(glob.glob(os.path.join(raw_dir, f"{doc_id}_*")))


def _pick_raw_path(candidates: list[str], filename: str) -> str | None:
    if not candidates:
        return None
    target_suffix = f"_{filename}"
    for path in candidates:
        if os.path.basename(path).endswith(target_suffix):
            return path
    return candidates[0]


def _normalize_int(value) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _contains_query(text: str, query: str) -> bool:
    if not query:
        return True
    text_l = text.lower()
    query_l = query.lower()
    if query_l in text_l:
        return True
    tokens = [t for t in re.split(r"\s+", query_l) if len(t) >= 2]
    if not tokens:
        return False
    return sum(1 for token in tokens if token in text_l) >= max(1, len(tokens) // 2)


def _extract_snippet_window(text: str, query: str | None, window_chars: int = 220) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""
    if not query or not query.strip():
        return normalized[: window_chars * 2]
    query_l = query.lower().strip()
    text_l = normalized.lower()
    idx = text_l.find(query_l)
    if idx < 0:
        return normalized[: window_chars * 2]
    start = max(0, idx - window_chars)
    end = min(len(normalized), idx + len(query_l) + window_chars)
    return normalized[start:end]


def _build_source_preview(
    doc: Document,
    vector_entries: list[dict],
    *,
    page: int | None = None,
    chunk: int | None = None,
    query: str | None = None,
) -> tuple[str, int | None, int | None, str, str | None]:
    query_text = (query or "").strip()
    target_page = _normalize_int(page)
    target_chunk = _normalize_int(chunk)

    selected_entry: dict | None = None
    matched_by = "fallback"

    if target_chunk is not None:
        for entry in vector_entries:
            meta = entry.get("metadata") or {}
            if _normalize_int(meta.get("chunk")) == target_chunk:
                if not query_text or _contains_query(entry.get("content", ""), query_text):
                    selected_entry = entry
                    matched_by = "chunk"
                    break

    if selected_entry is None and target_page is not None:
        page_entries = [
            entry
            for entry in vector_entries
            if _normalize_int((entry.get("metadata") or {}).get("page")) == target_page
        ]
        if query_text:
            selected_entry = next(
                (entry for entry in page_entries if _contains_query(entry.get("content", ""), query_text)),
                None,
            )
        if selected_entry is None and page_entries:
            selected_entry = page_entries[0]
        if selected_entry is not None:
            matched_by = "page"

    if selected_entry is None and query_text:
        selected_entry = next(
            (entry for entry in vector_entries if _contains_query(entry.get("content", ""), query_text)),
            None,
        )
        if selected_entry is not None:
            matched_by = "query"

    if selected_entry is not None:
        metadata = selected_entry.get("metadata") or {}
        source_page = _normalize_int(metadata.get("page"))
        source_chunk = _normalize_int(metadata.get("chunk"))
        snippet = _extract_snippet_window(selected_entry.get("content", ""), query_text or None)
        source_name = metadata.get("source") if isinstance(metadata.get("source"), str) else doc.filename
        return snippet, source_page, source_chunk, matched_by, source_name

    if doc.text_path and os.path.exists(doc.text_path):
        with open(doc.text_path, "r", encoding="utf-8", errors="ignore") as f:
            full_text = f.read()
        snippet = _extract_snippet_window(full_text, query_text or None, window_chars=260)
        if snippet:
            return snippet, target_page, target_chunk, "text_path", doc.filename

    raise HTTPException(status_code=404, detail="No source preview available")


def _queue_doc_reprocess(
    db: Session,
    background_tasks: BackgroundTasks,
    doc: Document,
    resolved_user_id: str,
) -> tuple[bool, str | None]:
    if not doc.kb_id:
        return False, "Document has no knowledge base"

    raw_candidates = _find_raw_candidates(resolved_user_id, doc.kb_id, doc.id)
    file_path = _pick_raw_path(raw_candidates, doc.filename)
    if not file_path:
        return False, "Original file not found, reprocess is unavailable"

    delete_doc_vectors(resolved_user_id, doc.id)
    remove_doc_chunks(resolved_user_id, doc.kb_id, doc.id)

    doc.status = "processing"
    doc.error_message = None
    doc.retry_count = int(doc.retry_count or 0) + 1
    doc.last_retry_at = datetime.utcnow()
    doc.num_chunks = 0
    doc.num_pages = 0
    doc.char_count = 0
    doc.processed_at = None
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(
        process_document_task,
        doc.id,
        resolved_user_id,
        doc.kb_id,
        file_path,
        doc.filename,
        doc.file_hash or "",
    )
    return True, None


def _delete_doc_records(db: Session, doc: Document) -> None:
    quiz_ids = [row[0] for row in db.query(Quiz.id).filter(Quiz.doc_id == doc.id).all()]
    if quiz_ids:
        db.query(QuizAttempt).filter(QuizAttempt.quiz_id.in_(quiz_ids)).delete(
            synchronize_session=False
        )

    session_ids = [
        row[0] for row in db.query(ChatSession.id).filter(ChatSession.doc_id == doc.id).all()
    ]
    if session_ids:
        db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).delete(
            synchronize_session=False
        )
        db.query(ChatSession).filter(ChatSession.id.in_(session_ids)).delete(
            synchronize_session=False
        )

    db.query(SummaryRecord).filter(SummaryRecord.doc_id == doc.id).delete(
        synchronize_session=False
    )
    db.query(KeypointRecord).filter(KeypointRecord.doc_id == doc.id).delete(
        synchronize_session=False
    )
    db.query(Keypoint).filter(Keypoint.doc_id == doc.id).delete(
        synchronize_session=False
    )
    db.query(QARecord).filter(QARecord.doc_id == doc.id).delete(
        synchronize_session=False
    )
    db.query(Quiz).filter(Quiz.doc_id == doc.id).delete(synchronize_session=False)
    if doc.kb_id:
        db.query(KeypointDependency).filter(
            KeypointDependency.kb_id == doc.kb_id
        ).delete(synchronize_session=False)
    db.delete(doc)


@router.delete("/docs/{doc_id}")
def delete_doc(doc_id: str, user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    doc = _get_doc_or_404(db, resolved_user_id, doc_id)

    raw_candidates = _find_raw_candidates(resolved_user_id, doc.kb_id, doc.id)
    for raw_path in raw_candidates:
        if os.path.exists(raw_path):
            os.remove(raw_path)
    if doc.text_path and os.path.exists(doc.text_path):
        os.remove(doc.text_path)

    remove_doc_chunks(resolved_user_id, doc.kb_id or "", doc.id) if doc.kb_id else None
    delete_doc_vectors(resolved_user_id, doc.id)
    if doc.kb_id:
        remove_file_hash(resolved_user_id, doc.kb_id, doc.filename)

    _delete_doc_records(db, doc)
    db.commit()
    return {"doc_id": doc_id, "deleted": True}


@router.patch("/docs/{doc_id}", response_model=DocumentOut)
def update_doc(
    doc_id: str,
    payload: DocumentUpdateRequest,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, payload.user_id)
    doc = _get_doc_or_404(db, resolved_user_id, doc_id)

    new_filename = doc.filename
    if payload.filename is not None:
        candidate = payload.filename.strip()
        if not candidate:
            raise HTTPException(status_code=400, detail="Filename cannot be empty")
        current_ext = f".{doc.file_type.lower()}"
        try:
            new_filename = DocumentValidator.validate_upload_safety(
                candidate,
                file_size=doc.file_size,
                allowed_extensions={current_ext},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    new_kb_id = doc.kb_id
    if payload.kb_id is not None:
        try:
            new_kb_id = ensure_kb(db, resolved_user_id, payload.kb_id).id
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    changed_name = new_filename != doc.filename
    changed_kb = new_kb_id != doc.kb_id
    if not changed_name and not changed_kb:
        return doc

    if changed_kb and doc.kb_id:
        ensure_kb_dirs(resolved_user_id, new_kb_id)
        old_candidates = _find_raw_candidates(resolved_user_id, doc.kb_id, doc.id)
        new_raw_dir = os.path.join(kb_base_dir(resolved_user_id, new_kb_id), "raw")
        for old_path in old_candidates:
            shutil.move(old_path, os.path.join(new_raw_dir, os.path.basename(old_path)))

    if changed_kb and doc.kb_id:
        transfer_file_hash(
            resolved_user_id,
            doc.kb_id,
            new_kb_id,
            doc.filename,
            new_filename=new_filename,
            file_hash=doc.file_hash,
        )
    elif changed_name and doc.kb_id:
        if not rename_file_hash(resolved_user_id, doc.kb_id, doc.filename, new_filename):
            if doc.file_hash:
                record_file_hash(resolved_user_id, doc.kb_id, new_filename, doc.file_hash)

    try:
        update_doc_vector_metadata(
            resolved_user_id,
            doc.id,
            kb_id=new_kb_id if changed_kb else None,
            source=new_filename if changed_name else None,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to update vector index: {exc}") from exc

    if changed_kb and doc.kb_id:
        move_doc_chunks(
            resolved_user_id,
            doc.kb_id,
            new_kb_id,
            doc.id,
            source=new_filename if changed_name else None,
        )
    elif changed_name and doc.kb_id:
        update_doc_chunks_metadata(
            resolved_user_id,
            doc.kb_id,
            doc.id,
            source=new_filename,
        )

    old_kb_id = doc.kb_id
    doc.filename = new_filename
    doc.kb_id = new_kb_id
    db.query(Keypoint).filter(Keypoint.doc_id == doc.id).update(
        {Keypoint.kb_id: new_kb_id},
        synchronize_session=False,
    )
    db.query(QARecord).filter(QARecord.doc_id == doc.id).update(
        {QARecord.kb_id: new_kb_id},
        synchronize_session=False,
    )
    db.query(Quiz).filter(Quiz.doc_id == doc.id).update(
        {Quiz.kb_id: new_kb_id},
        synchronize_session=False,
    )
    db.query(ChatSession).filter(ChatSession.doc_id == doc.id).update(
        {ChatSession.kb_id: new_kb_id},
        synchronize_session=False,
    )
    if old_kb_id:
        db.query(KeypointDependency).filter(
            KeypointDependency.kb_id == old_kb_id
        ).delete(synchronize_session=False)
    if new_kb_id and new_kb_id != old_kb_id:
        db.query(KeypointDependency).filter(
            KeypointDependency.kb_id == new_kb_id
        ).delete(synchronize_session=False)

    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/docs/{doc_id}/reprocess", response_model=DocumentOut)
def reprocess_doc(
    doc_id: str,
    background_tasks: BackgroundTasks,
    user_id: str | None = None,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, user_id)
    doc = _get_doc_or_404(db, resolved_user_id, doc_id)
    ok, err = _queue_doc_reprocess(db, background_tasks, doc, resolved_user_id)
    if not ok:
        status_code = 404 if err and "not found" in err.lower() else 400
        raise HTTPException(status_code=status_code, detail=err or "Failed to reprocess document")
    return doc


@router.get("/docs/{doc_id}/preview", response_model=SourcePreviewResponse)
def preview_doc_source(
    doc_id: str,
    user_id: str | None = None,
    page: int | None = None,
    chunk: int | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, user_id)
    doc = _get_doc_or_404(db, resolved_user_id, doc_id)
    vector_entries = get_doc_vector_entries(resolved_user_id, doc_id)
    snippet, source_page, source_chunk, matched_by, source_name = _build_source_preview(
        doc,
        vector_entries,
        page=page,
        chunk=chunk,
        query=q,
    )
    return SourcePreviewResponse(
        doc_id=doc.id,
        filename=doc.filename,
        page=source_page,
        chunk=source_chunk,
        source=source_name,
        snippet=snippet,
        matched_by=matched_by,
    )


@router.get("/docs/tasks", response_model=DocumentTaskCenterResponse)
def get_doc_tasks(
    user_id: str | None = None,
    kb_id: str | None = None,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, user_id)
    query = db.query(Document).filter(Document.user_id == resolved_user_id)
    if kb_id:
        query = query.filter(Document.kb_id == kb_id)
    rows = (
        query.filter(Document.status.in_(["processing", "error"]))
        .order_by(Document.created_at.desc())
        .all()
    )
    processing = [doc for doc in rows if doc.status == "processing"]
    error = [doc for doc in rows if doc.status == "error"]
    return DocumentTaskCenterResponse(
        processing=processing,
        error=error,
        processing_count=len(processing),
        error_count=len(error),
    )


@router.post("/docs/retry-failed", response_model=DocumentRetryResponse)
def retry_failed_docs(
    payload: DocumentRetryRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, payload.user_id)
    query = db.query(Document).filter(
        Document.user_id == resolved_user_id,
        Document.status == "error",
    )
    if payload.doc_ids:
        doc_ids = [doc_id.strip() for doc_id in payload.doc_ids if doc_id and doc_id.strip()]
        if not doc_ids:
            return DocumentRetryResponse(queued=[], skipped=[])
        query = query.filter(Document.id.in_(doc_ids))

    docs = query.all()
    queued: list[str] = []
    skipped: list[str] = []
    for doc in docs:
        ok, _ = _queue_doc_reprocess(db, background_tasks, doc, resolved_user_id)
        if ok:
            queued.append(doc.id)
        else:
            skipped.append(doc.id)

    return DocumentRetryResponse(queued=queued, skipped=skipped)


@router.post("/docs/upload", response_model=DocumentOut)
def upload_doc(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str | None = Form(default=None),
    kb_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    resolved_user_id = ensure_user(db, user_id)
    try:
        kb = ensure_kb(db, resolved_user_id, kb_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    doc_id = str(uuid4())
    try:
        safe_name = DocumentValidator.validate_upload_safety(
            file.filename, None, content_type=file.content_type
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    suffix = os.path.splitext(safe_name)[1].lower()

    ensure_user_dirs(resolved_user_id)
    ensure_kb_dirs(resolved_user_id, kb.id)
    raw_dir = os.path.join(kb_base_dir(resolved_user_id, kb.id), "raw")
    file_path = os.path.join(raw_dir, f"{doc_id}_{safe_name}")

    hasher = hashlib.sha256()
    total_size = 0
    max_size = (
        DocumentValidator.MAX_PDF_SIZE
        if suffix == ".pdf"
        else DocumentValidator.MAX_FILE_SIZE
    )

    try:
        with open(file_path, "wb") as f:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    raise HTTPException(status_code=400, detail="File too large")
                hasher.update(chunk)
                f.write(chunk)
    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    try:
        DocumentValidator.validate_upload_safety(
            safe_name, total_size, content_type=file.content_type
        )
    except ValueError as exc:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    file_hash = hasher.hexdigest()

    metadata = load_kb_metadata(resolved_user_id, kb.id)
    if file_hash in (metadata.get("file_hashes") or {}).values():
        existing = (
            db.query(Document)
            .filter(
                Document.user_id == resolved_user_id,
                Document.kb_id == kb.id,
                Document.file_hash == file_hash,
            )
            .first()
        )
        if os.path.exists(file_path):
            os.remove(file_path)
        if existing:
            return existing
        raise HTTPException(status_code=409, detail="Duplicate document already uploaded")

    existing = (
        db.query(Document)
        .filter(
            Document.user_id == resolved_user_id,
            Document.kb_id == kb.id,
            Document.file_hash == file_hash,
            Document.status.in_(["processing", "ready"]),
        )
        .first()
    )
    if existing:
        if os.path.exists(file_path):
            os.remove(file_path)
        return existing

    text_path = os.path.join(user_base_dir(resolved_user_id), "text", f"{doc_id}.txt")
    doc = Document(
        id=doc_id,
        user_id=resolved_user_id,
        kb_id=kb.id,
        filename=safe_name,
        file_type=suffix.replace(".", ""),
        text_path=text_path,
        file_size=total_size,
        file_hash=file_hash,
        status="processing",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(
        process_document_task,
        doc_id,
        resolved_user_id,
        kb.id,
        file_path,
        safe_name,
        file_hash,
    )
    return doc
