import hashlib
import glob
import os
import shutil
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

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
from app.core.vectorstore import delete_doc_vectors, update_doc_vector_metadata
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
from app.schemas import DocumentOut, DocumentUpdateRequest
from app.services.lexical import move_doc_chunks, remove_doc_chunks, update_doc_chunks_metadata
from app.services.ingest_tasks import process_document_task
from app.utils.document_validator import DocumentValidator

router = APIRouter()


@router.get("/docs", response_model=list[DocumentOut])
def list_docs(
    user_id: str | None = None,
    kb_id: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Document)
    if user_id:
        query = query.filter(Document.user_id == user_id)
    if kb_id:
        query = query.filter(Document.kb_id == kb_id)
    return query.order_by(Document.created_at.desc()).all()


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
    if not doc.kb_id:
        raise HTTPException(status_code=400, detail="Document has no knowledge base")

    raw_candidates = _find_raw_candidates(resolved_user_id, doc.kb_id, doc.id)
    file_path = _pick_raw_path(raw_candidates, doc.filename)
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail="Original file not found, reprocess is unavailable",
        )

    delete_doc_vectors(resolved_user_id, doc.id)
    remove_doc_chunks(resolved_user_id, doc.kb_id, doc.id)

    doc.status = "processing"
    doc.error_message = None
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
    return doc


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
