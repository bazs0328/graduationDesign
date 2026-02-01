from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.knowledge_bases import ensure_kb
from app.core.users import ensure_user
from app.db import get_db
from app.models import Document, KeypointRecord, QARecord, Quiz, SummaryRecord
from app.schemas import (
    RecommendationAction,
    RecommendationItem,
    RecommendationsResponse,
)

router = APIRouter()


@router.get("/recommendations", response_model=RecommendationsResponse)
def get_recommendations(
    user_id: str | None = None,
    kb_id: str | None = None,
    limit: int = 5,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, user_id)
    try:
        kb = ensure_kb(db, resolved_user_id, kb_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    limit = max(1, min(limit, 20))
    docs = (
        db.query(Document)
        .filter(
            Document.user_id == resolved_user_id,
            Document.kb_id == kb.id,
            Document.status == "ready",
        )
        .order_by(Document.created_at.desc())
        .all()
    )

    if not docs:
        return RecommendationsResponse(kb_id=kb.id, kb_name=kb.name, items=[])

    doc_ids = [doc.id for doc in docs]

    summary_doc_ids = {
        row[0]
        for row in db.query(SummaryRecord.doc_id)
        .filter(
            SummaryRecord.user_id == resolved_user_id,
            SummaryRecord.doc_id.in_(doc_ids),
        )
        .distinct()
        .all()
    }
    keypoint_doc_ids = {
        row[0]
        for row in db.query(KeypointRecord.doc_id)
        .filter(
            KeypointRecord.user_id == resolved_user_id,
            KeypointRecord.doc_id.in_(doc_ids),
        )
        .distinct()
        .all()
    }
    quiz_doc_ids = {
        row[0]
        for row in db.query(Quiz.doc_id)
        .filter(Quiz.user_id == resolved_user_id, Quiz.doc_id.in_(doc_ids))
        .distinct()
        .all()
    }
    qa_doc_ids = {
        row[0]
        for row in db.query(QARecord.doc_id)
        .filter(QARecord.user_id == resolved_user_id, QARecord.doc_id.in_(doc_ids))
        .distinct()
        .all()
    }

    ranked_items = []
    for doc in docs:
        actions = []
        missing = 0
        if doc.id not in summary_doc_ids:
            actions.append(RecommendationAction(type="summary", reason="No summary yet"))
            missing += 1
        if doc.id not in keypoint_doc_ids:
            actions.append(RecommendationAction(type="keypoints", reason="No keypoints yet"))
            missing += 1
        if doc.id not in quiz_doc_ids:
            actions.append(RecommendationAction(type="quiz", reason="No quiz yet"))
            missing += 1
        if doc.id not in qa_doc_ids:
            actions.append(RecommendationAction(type="qa", reason="No questions yet"))
        else:
            actions.append(RecommendationAction(type="qa", reason="Continue Q&A practice"))

        ranked_items.append(
            (
                missing,
                doc.created_at or datetime.min,
                RecommendationItem(
                    doc_id=doc.id,
                    doc_name=doc.filename,
                    actions=actions,
                ),
            )
        )

    ranked_items.sort(key=lambda item: (item[0], item[1]), reverse=True)
    items = [item[2] for item in ranked_items[:limit]]

    return RecommendationsResponse(kb_id=kb.id, kb_name=kb.name, items=items)
