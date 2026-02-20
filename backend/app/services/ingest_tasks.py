from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.kb_metadata import record_file_hash
from app.db import SessionLocal
from app.models import Document
from app.services.ingest import ingest_document


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
            doc.processed_at = datetime.utcnow()
            db.commit()

            if file_hash:
                record_file_hash(user_id, kb_id, filename, file_hash)
        except Exception as exc:  # noqa: BLE001
            doc.status = "error"
            doc.error_message = str(exc)[:800]
            db.commit()
    finally:
        db.close()
