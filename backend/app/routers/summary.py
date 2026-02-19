import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.users import ensure_user
from app.db import get_db
from app.models import Document, SummaryRecord
from app.schemas import SummaryRequest, SummaryResponse
from app.services.summary import summarize_text

router = APIRouter()


@router.post("/summary", response_model=SummaryResponse)
async def generate_summary(payload: SummaryRequest, db: Session = Depends(get_db)):
    def _normalize_summary(value):
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    resolved_user_id = ensure_user(db, payload.user_id)
    doc = db.query(Document).filter(Document.id == payload.doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if payload.user_id and doc.user_id != resolved_user_id:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.status != "ready":
        raise HTTPException(status_code=409, detail="Document is still processing")

    if not payload.force:
        cached = (
            db.query(SummaryRecord)
            .filter(
                SummaryRecord.doc_id == payload.doc_id,
                SummaryRecord.user_id == resolved_user_id,
            )
            .order_by(SummaryRecord.created_at.desc())
            .first()
        )
        if cached:
            return SummaryResponse(
                doc_id=doc.id,
                summary=_normalize_summary(cached.summary_text),
                cached=True,
            )

    with open(doc.text_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    try:
        summary = await summarize_text(text)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Summary generation failed. Check LLM output or model settings.",
        ) from exc
    summary = _normalize_summary(summary)
    record = SummaryRecord(
        id=str(uuid4()),
        user_id=resolved_user_id,
        doc_id=doc.id,
        summary_text=summary,
    )
    db.add(record)
    db.commit()
    return SummaryResponse(doc_id=doc.id, summary=summary, cached=False)
