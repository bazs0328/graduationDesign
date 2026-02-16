from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.knowledge_bases import ensure_kb
from app.core.users import ensure_user
from app.db import get_db
from app.models import Document, Keypoint, KeypointRecord, QARecord, Quiz, SummaryRecord
from app.schemas import (
    LearningPathItem,
    RecommendationAction,
    RecommendationItem,
    RecommendationsResponse,
)
from app.services.learner_profile import get_or_create_profile, get_weak_concepts

router = APIRouter()


def _build_learning_path(
    keypoints: list[Keypoint], doc_map: dict[str, str], limit: int = 10
) -> list[LearningPathItem]:
    sorted_keypoints = sorted(
        keypoints, key=lambda item: (item.mastery_level or 0.0, item.attempt_count or 0)
    )
    items: list[LearningPathItem] = []
    for keypoint in sorted_keypoints[:limit]:
        mastery_level = keypoint.mastery_level or 0.0
        if mastery_level < 0.3:
            priority = "high"
        elif mastery_level < 0.7:
            priority = "medium"
        else:
            priority = "low"
        items.append(
            LearningPathItem(
                keypoint_id=keypoint.id,
                text=keypoint.text,
                doc_id=keypoint.doc_id,
                doc_name=doc_map.get(keypoint.doc_id),
                mastery_level=mastery_level,
                priority=priority,
            )
        )
    return items


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
    profile = get_or_create_profile(db, resolved_user_id)
    weak_concepts = get_weak_concepts(profile)
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

    doc_map = {doc.id: doc.filename for doc in docs}
    keypoints = (
        db.query(Keypoint)
        .filter(
            Keypoint.user_id == resolved_user_id,
            Keypoint.kb_id == kb.id,
        )
        .all()
    )
    learning_path = _build_learning_path(keypoints, doc_map, limit=10)

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

        if weak_concepts:
            actions.append(
                RecommendationAction(
                    type="review",
                    reason="根据薄弱知识点推荐复习",
                    params={"focus_concepts": weak_concepts[:3]},
                )
            )

        if profile.ability_level == "beginner" and profile.recent_accuracy >= 0.7:
            actions.append(
                RecommendationAction(
                    type="challenge",
                    reason="基础掌握不错，可尝试中等难度",
                    params={"difficulty": "medium"},
                )
            )
        elif profile.ability_level == "advanced" and profile.recent_accuracy >= 0.7:
            actions.append(
                RecommendationAction(
                    type="challenge",
                    reason="表现优秀，可尝试高难度挑战",
                    params={"difficulty": "hard"},
                )
            )

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

    return RecommendationsResponse(
        kb_id=kb.id,
        kb_name=kb.name,
        items=items,
        learning_path=learning_path,
    )
