import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.users import ensure_user
from app.db import get_db
from app.models import Document, KeypointRecord
from app.schemas import KeypointItem, KeypointsRequest, KeypointsResponse
from app.services.keypoints import extract_keypoints
from app.utils.json_tools import safe_json_loads

router = APIRouter()


def _normalize_points(points) -> list[KeypointItem]:
    if not isinstance(points, list):
        return []
    normalized = []
    for item in points:
        if isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append(KeypointItem(text=text))
        elif isinstance(item, dict):
            text = (item.get("text") or "").strip()
            if text:
                normalized.append(
                    KeypointItem(
                        text=text,
                        explanation=item.get("explanation"),
                        source=item.get("source"),
                        page=item.get("page"),
                        chunk=item.get("chunk"),
                    )
                )
    return normalized


@router.post("/keypoints", response_model=KeypointsResponse)
def generate_keypoints(payload: KeypointsRequest, db: Session = Depends(get_db)):
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
            db.query(KeypointRecord)
            .filter(
                KeypointRecord.doc_id == payload.doc_id,
                KeypointRecord.user_id == resolved_user_id,
            )
            .order_by(KeypointRecord.created_at.desc())
            .first()
        )
        if cached:
            raw = safe_json_loads(cached.points_json)
            keypoints = _normalize_points(raw)
            return KeypointsResponse(
                doc_id=doc.id,
                keypoints=keypoints,
                cached=True,
            )

    with open(doc.text_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    try:
        points = extract_keypoints(
            text,
            user_id=resolved_user_id,
            doc_id=doc.id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Keypoint extraction failed. Check LLM output or model settings.",
        ) from exc

    keypoints = _normalize_points(points)
    store = [p.model_dump() for p in keypoints]
    record = KeypointRecord(
        id=str(uuid4()),
        user_id=resolved_user_id,
        doc_id=doc.id,
        points_json=json.dumps(store, ensure_ascii=False),
    )
    db.add(record)
    db.commit()

    return KeypointsResponse(doc_id=doc.id, keypoints=keypoints, cached=False)
