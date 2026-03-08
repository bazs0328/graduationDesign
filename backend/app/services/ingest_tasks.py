from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.kb_metadata import record_file_hash
from app.core.runtime_user_config import activate_runtime_settings_for_user_id, clear_runtime_settings
from app.db import SessionLocal
from app.models import Document
from app.services.ingest import ingest_document
from app.utils.time import utc_now


def process_document_task(
    doc_id: str,
    user_id: str,
    kb_id: str,
    file_path: str,
    filename: str,
    file_hash: str,
) -> None:
    db: Session = SessionLocal()
    try:
        activate_runtime_settings_for_user_id(db, user_id)
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return

        try:
            text_path, num_chunks, num_pages, char_count = ingest_document(
                file_path, filename, doc_id, user_id, kb_id
            )
            doc.text_path = text_path
            doc.num_chunks = num_chunks
            doc.num_pages = num_pages
            doc.char_count = char_count
            doc.status = "ready"
            doc.error_message = None
            doc.processed_at = utc_now()
            db.commit()

            if file_hash:
                record_file_hash(user_id, kb_id, filename, file_hash)
        except Exception as exc:  # noqa: BLE001
            doc.status = "error"
            doc.error_message = str(exc)[:800]
            doc.processed_at = utc_now()
            db.commit()
    finally:
        clear_runtime_settings()
        db.close()
