from __future__ import annotations

from datetime import datetime
import json
import logging

from sqlalchemy.orm import Session

from app.core.kb_metadata import get_kb_parse_settings, record_file_hash
from app.db import SessionLocal
from app.models import Document
from app.services.ingest import IngestResult, ingest_document

logger = logging.getLogger(__name__)


def _update_progress(doc: Document, db: Session, stage: str, progress: int, message: str | None = None) -> None:
    doc.stage = stage
    doc.progress_percent = max(0, min(int(progress), 100))
    if message:
        doc.error_message = message if stage == "error" else doc.error_message
    db.add(doc)
    db.commit()


def process_document_task(
    doc_id: str,
    user_id: str,
    kb_id: str,
    file_path: str,
    filename: str,
    file_hash: str,
    mode: str = "auto",
) -> None:
    db: Session = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return

        parse_settings = get_kb_parse_settings(user_id, kb_id)
        parse_policy = parse_settings.get("parse_policy", "balanced")
        preferred_parser = parse_settings.get("preferred_parser", "auto")

        doc.status = "processing"
        doc.stage = "queued"
        doc.progress_percent = 0
        doc.error_message = None
        db.add(doc)
        db.commit()

        def _stage_callback(stage: str, progress: int, _msg: str):
            try:
                doc.stage = stage
                doc.progress_percent = progress
                db.add(doc)
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()

        try:
            result = ingest_document(
                file_path,
                filename,
                doc_id,
                user_id,
                kb_id,
                mode=mode,
                parse_policy=parse_policy,
                preferred_parser=preferred_parser,
                stage_callback=_stage_callback,
                return_details=True,
            )
            assert isinstance(result, IngestResult)

            doc.text_path = result.text_path
            doc.num_chunks = result.num_chunks
            doc.num_pages = result.num_pages
            doc.char_count = result.char_count
            doc.status = "ready"
            doc.stage = "done"
            doc.progress_percent = 100
            doc.error_message = None
            doc.parser_provider = result.parser_provider
            doc.extract_method = result.extract_method
            doc.quality_score = result.quality_score
            doc.diagnostics_json = json.dumps(result.diagnostics or {}, ensure_ascii=False)
            doc.timing_json = json.dumps(result.timing or {}, ensure_ascii=False)
            doc.processed_at = datetime.utcnow()
            db.commit()

            if file_hash:
                record_file_hash(user_id, kb_id, filename, file_hash)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Document ingest failed: %s", doc_id)
            doc.status = "error"
            doc.stage = "error"
            doc.progress_percent = 100
            doc.error_message = str(exc)[:800]
            if not doc.diagnostics_json:
                doc.diagnostics_json = json.dumps(
                    {
                        "error": str(exc)[:800],
                        "strategy": "failed",
                    },
                    ensure_ascii=False,
                )
            doc.processed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
