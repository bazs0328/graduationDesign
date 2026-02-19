import hashlib
import os
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.paths import ensure_kb_dirs, ensure_user_dirs, kb_base_dir, user_base_dir
from app.core.knowledge_bases import ensure_kb
from app.core.kb_metadata import load_kb_metadata
from app.core.users import ensure_user
from app.db import get_db
from app.models import Document
from app.schemas import DocumentOut
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
