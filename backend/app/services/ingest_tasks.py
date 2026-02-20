from __future__ import annotations

from datetime import datetime
import json
import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.kb_metadata import (
    get_kb_parse_settings,
    get_kb_rag_settings,
    record_file_hash,
)
from app.db import SessionLocal
from app.models import Document, DocumentAsset, IngestRun
from app.services.rag.base import RAGIngestRequest, RAGIngestResult
from app.services.rag.factory import get_rag_provider

logger = logging.getLogger(__name__)


def _store_ingest_run(
    db: Session,
    *,
    doc_id: str,
    user_id: str,
    kb_id: str,
    backend: str,
    parser_engine: str | None,
    status: str,
    mode: str,
    stage: str | None,
    timing: dict | None,
    diagnostics: dict | None,
    error_message: str | None = None,
) -> None:
    row = IngestRun(
        id=str(uuid4()),
        doc_id=doc_id,
        user_id=user_id,
        kb_id=kb_id,
        backend=backend,
        parser_engine=parser_engine,
        status=status,
        mode=mode,
        stage=stage,
        timing_json=json.dumps(timing or {}, ensure_ascii=False),
        diagnostics_json=json.dumps(diagnostics or {}, ensure_ascii=False),
        error_message=error_message,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()


def _persist_assets(
    db: Session,
    *,
    doc_id: str,
    user_id: str,
    kb_id: str,
    assets: list[dict],
) -> int:
    db.query(DocumentAsset).filter(DocumentAsset.doc_id == doc_id).delete(
        synchronize_session=False
    )
    inserted = 0
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        row = DocumentAsset(
            id=str(asset.get("id") or uuid4()),
            doc_id=doc_id,
            user_id=user_id,
            kb_id=kb_id,
            page=asset.get("page"),
            asset_type=str(asset.get("asset_type") or "image"),
            image_path=asset.get("image_path"),
            caption_text=asset.get("caption_text"),
            ocr_text=asset.get("ocr_text"),
            quality_score=asset.get("quality_score"),
            metadata_json=json.dumps(asset.get("metadata") or {}, ensure_ascii=False),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        inserted += 1
    db.commit()
    return inserted


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
        rag_settings = get_kb_rag_settings(user_id, kb_id)
        parse_policy = parse_settings.get("parse_policy", "balanced")
        preferred_parser = parse_settings.get("preferred_parser", "auto")
        parser_preference = rag_settings.get("parser_preference", "mineru")

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

        provider = get_rag_provider(user_id, kb_id)
        backend_id = getattr(provider, "backend_id", "legacy")
        try:
            result = provider.ingest(
                RAGIngestRequest(
                    file_path=file_path,
                    filename=filename,
                    doc_id=doc_id,
                    user_id=user_id,
                    kb_id=kb_id,
                    mode=mode,
                    parse_policy=parse_policy,
                    preferred_parser=preferred_parser,
                    parser_preference=parser_preference,
                    stage_callback=_stage_callback,
                )
            )
            assert isinstance(result, RAGIngestResult)

            diagnostics = dict(result.diagnostics or {})
            diagnostics.setdefault("rag_backend", result.rag_backend or backend_id)
            diagnostics.setdefault("parser_engine", result.parser_engine)
            diagnostics.setdefault("fallback_chain", result.fallback_chain or [])
            diagnostics.setdefault("asset_stats", result.asset_stats or {"total": 0, "by_type": {}})

            inserted_assets = _persist_assets(
                db,
                doc_id=doc_id,
                user_id=user_id,
                kb_id=kb_id,
                assets=result.assets or [],
            )

            asset_total = int(
                (result.asset_stats or {}).get("total")
                or inserted_assets
                or 0
            )
            visual_coverage = (
                round(float(asset_total) / float(max(1, result.num_pages)), 4)
                if result.num_pages
                else 0.0
            )
            multimodal_status = "ready" if asset_total > 0 else "text_only"

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
            doc.rag_backend = result.rag_backend or backend_id
            doc.asset_count = asset_total
            doc.visual_coverage = visual_coverage
            doc.multimodal_status = multimodal_status
            doc.diagnostics_json = json.dumps(diagnostics, ensure_ascii=False)
            doc.timing_json = json.dumps(result.timing or {}, ensure_ascii=False)
            doc.processed_at = datetime.utcnow()
            db.commit()

            _store_ingest_run(
                db,
                doc_id=doc_id,
                user_id=user_id,
                kb_id=kb_id,
                backend=result.rag_backend or backend_id,
                parser_engine=result.parser_engine,
                status="ready",
                mode=mode,
                stage="done",
                timing=result.timing or {},
                diagnostics=diagnostics,
            )

            if file_hash:
                record_file_hash(user_id, kb_id, filename, file_hash)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Document ingest failed: %s", doc_id)
            doc.status = "error"
            doc.stage = "error"
            doc.progress_percent = 100
            doc.error_message = str(exc)[:800]
            doc.multimodal_status = "error"
            if not doc.diagnostics_json:
                doc.diagnostics_json = json.dumps(
                    {
                        "error": str(exc)[:800],
                        "strategy": "failed",
                        "rag_backend": backend_id,
                        "fallback_chain": ["ingest_error"],
                    },
                    ensure_ascii=False,
                )
            doc.processed_at = datetime.utcnow()
            db.commit()
            _store_ingest_run(
                db,
                doc_id=doc_id,
                user_id=user_id,
                kb_id=kb_id,
                backend=backend_id,
                parser_engine=parser_preference,
                status="error",
                mode=mode,
                stage="error",
                timing={},
                diagnostics={"error": str(exc)[:800]},
                error_message=str(exc)[:800],
            )
    finally:
        db.close()
