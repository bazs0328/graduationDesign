from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.users import ensure_user
from app.db import get_db
from app.models import Document, KeypointRecord, QARecord, Quiz, QuizAttempt, SummaryRecord
from app.schemas import ActivityItem, ActivityResponse

router = APIRouter()


def _doc_name_map(query):
    return {doc.id: doc.filename for doc in query.all()}


@router.get("/activity", response_model=ActivityResponse)
def get_activity(limit: int = 20, user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    limit = max(1, min(limit, 100))

    doc_query = db.query(Document)
    quiz_query = db.query(Quiz)
    attempt_query = db.query(QuizAttempt)
    qa_query = db.query(QARecord)
    summary_query = db.query(SummaryRecord)
    keypoint_query = db.query(KeypointRecord)

    if user_id:
        doc_query = doc_query.filter(Document.user_id == resolved_user_id)
        quiz_query = quiz_query.filter(Quiz.user_id == resolved_user_id)
        attempt_query = attempt_query.filter(QuizAttempt.user_id == resolved_user_id)
        qa_query = qa_query.filter(QARecord.user_id == resolved_user_id)
        summary_query = summary_query.filter(SummaryRecord.user_id == resolved_user_id)
        keypoint_query = keypoint_query.filter(KeypointRecord.user_id == resolved_user_id)

    doc_name = _doc_name_map(doc_query)
    quiz_doc = {quiz.id: quiz.doc_id for quiz in quiz_query.all()}

    items: list[ActivityItem] = []

    for doc in doc_query.order_by(Document.created_at.desc()).limit(limit).all():
        items.append(
            ActivityItem(
                type="document_upload",
                timestamp=doc.created_at,
                doc_id=doc.id,
                doc_name=doc.filename,
                detail=f"Uploaded {doc.filename}",
            )
        )

    for record in summary_query.order_by(SummaryRecord.created_at.desc()).limit(limit).all():
        items.append(
            ActivityItem(
                type="summary_generated",
                timestamp=record.created_at,
                doc_id=record.doc_id,
                doc_name=doc_name.get(record.doc_id),
                detail="Summary generated",
            )
        )

    for record in keypoint_query.order_by(KeypointRecord.created_at.desc()).limit(limit).all():
        items.append(
            ActivityItem(
                type="keypoints_generated",
                timestamp=record.created_at,
                doc_id=record.doc_id,
                doc_name=doc_name.get(record.doc_id),
                detail="Keypoints generated",
            )
        )

    for record in qa_query.order_by(QARecord.created_at.desc()).limit(limit).all():
        items.append(
            ActivityItem(
                type="question_asked",
                timestamp=record.created_at,
                doc_id=record.doc_id,
                doc_name=doc_name.get(record.doc_id),
                detail=record.question,
            )
        )

    for attempt in attempt_query.order_by(QuizAttempt.created_at.desc()).limit(limit).all():
        doc_id = quiz_doc.get(attempt.quiz_id)
        items.append(
            ActivityItem(
                type="quiz_attempt",
                timestamp=attempt.created_at,
                doc_id=doc_id,
                doc_name=doc_name.get(doc_id),
                detail="Quiz submitted",
                score=attempt.score,
                total=attempt.total,
            )
        )

    items.sort(key=lambda item: item.timestamp or datetime.min, reverse=True)
    return ActivityResponse(items=items[:limit])
