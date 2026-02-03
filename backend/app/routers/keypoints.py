import json
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.knowledge_bases import ensure_kb
from app.core.users import ensure_user
from app.db import get_db
from app.models import Document, Keypoint, KeypointRecord
from app.schemas import KeypointItemV2, KeypointsRequest, KeypointsResponse
from app.services.keypoints import extract_keypoints, save_keypoints_to_db
from app.utils.json_tools import safe_json_loads

router = APIRouter()


def _normalize_cached_points(points: list) -> list[dict]:
    """Normalize cached keypoints JSON into save-ready dicts."""
    if not isinstance(points, list):
        return []
    normalized = []
    for item in points:
        if isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append({"text": text})
        elif isinstance(item, dict):
            text = (item.get("text") or "").strip()
            if text:
                normalized.append(
                    {
                        "text": text,
                        "explanation": item.get("explanation"),
                        "source": item.get("source"),
                        "page": item.get("page"),
                        "chunk": item.get("chunk"),
                    }
                )
    return normalized


def _to_keypoint_items(points: list[Keypoint]) -> list[KeypointItemV2]:
    """Convert Keypoint models into response items."""
    return [
        KeypointItemV2(
            id=point.id,
            text=point.text,
            explanation=point.explanation,
            source=point.source,
            page=point.page,
            chunk=point.chunk,
            mastery_level=point.mastery_level or 0.0,
            attempt_count=point.attempt_count or 0,
            correct_count=point.correct_count or 0,
        )
        for point in points
    ]


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
        existing = (
            db.query(Keypoint)
            .filter(
                Keypoint.doc_id == payload.doc_id,
                Keypoint.user_id == resolved_user_id,
            )
            .order_by(Keypoint.created_at.asc())
            .all()
        )
        if existing:
            return KeypointsResponse(
                doc_id=doc.id,
                keypoints=_to_keypoint_items(existing),
                cached=True,
            )
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
            points = _normalize_cached_points(raw)
            keypoints = save_keypoints_to_db(
                db,
                resolved_user_id,
                doc.id,
                points,
                kb_id=doc.kb_id,
                overwrite=False,
            )
            return KeypointsResponse(
                doc_id=doc.id,
                keypoints=_to_keypoint_items(keypoints),
                cached=True,
            )

    try:
        with open(doc.text_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as open_exc:
        raise HTTPException(status_code=500, detail="Document text file not readable.") from open_exc

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

    keypoints = save_keypoints_to_db(
        db,
        resolved_user_id,
        doc.id,
        points,
        kb_id=doc.kb_id,
        overwrite=payload.force,
    )
    store = [
        {
            "text": kp.text,
            "explanation": kp.explanation,
            "source": kp.source,
            "page": kp.page,
            "chunk": kp.chunk,
        }
        for kp in keypoints
    ]
    record = KeypointRecord(
        id=str(uuid4()),
        user_id=resolved_user_id,
        doc_id=doc.id,
        points_json=json.dumps(store, ensure_ascii=False),
    )
    db.add(record)
    db.commit()

    return KeypointsResponse(
        doc_id=doc.id, keypoints=_to_keypoint_items(keypoints), cached=False
    )


@router.get("/keypoints/{doc_id}", response_model=KeypointsResponse)
def get_keypoints(
    doc_id: str, user_id: Optional[str] = None, db: Session = Depends(get_db)
):
    """Get keypoints for a document with mastery stats."""
    resolved_user_id = ensure_user(db, user_id)
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if user_id and doc.user_id != resolved_user_id:
        raise HTTPException(status_code=404, detail="Document not found")

    keypoints = (
        db.query(Keypoint)
        .filter(Keypoint.doc_id == doc_id, Keypoint.user_id == resolved_user_id)
        .order_by(Keypoint.created_at.asc())
        .all()
    )
    return KeypointsResponse(
        doc_id=doc.id,
        keypoints=_to_keypoint_items(keypoints),
        cached=True,
    )


@router.get("/keypoints/kb/{kb_id}", response_model=KeypointsResponse)
def get_keypoints_by_kb(
    kb_id: str, user_id: Optional[str] = None, db: Session = Depends(get_db)
):
    """Get keypoints for a knowledge base with mastery stats."""
    resolved_user_id = ensure_user(db, user_id)
    kb = ensure_kb(db, resolved_user_id, kb_id)

    keypoints = (
        db.query(Keypoint)
        .filter(Keypoint.user_id == resolved_user_id, Keypoint.kb_id == kb.id)
        .order_by(Keypoint.created_at.asc())
        .all()
    )
    return KeypointsResponse(
        doc_id=kb.id,
        keypoints=_to_keypoint_items(keypoints),
        cached=True,
    )
