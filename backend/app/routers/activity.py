from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.users import ensure_user
from app.db import get_db
from app.models import Document, KeypointRecord, QARecord, Quiz, QuizAttempt, SummaryRecord
from app.schemas import ActivityItem, ActivityResponse

router = APIRouter()


def _extend_doc_name_map(
    db: Session,
    user_id: str,
    doc_ids: set[str],
    doc_name: dict[str, str],
) -> None:
    missing_ids = [doc_id for doc_id in doc_ids if doc_id and doc_id not in doc_name]
    if not missing_ids:
        return
    for doc_id, filename in (
        db.query(Document.id, Document.filename)
        .filter(Document.user_id == user_id, Document.id.in_(missing_ids))
        .all()
    ):
        doc_name[doc_id] = filename


@router.get("/activity", response_model=ActivityResponse)
def get_activity(
    limit: int = 20,
    offset: int = 0,
    user_id: str | None = None,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, user_id)
    offset = max(0, int(offset or 0))
    limit = max(1, min(limit, 100))
    fetch_window = offset + limit

    doc_query = db.query(Document)
    quiz_query = db.query(Quiz)
    attempt_query = db.query(QuizAttempt)
    qa_query = db.query(QARecord)
    summary_query = db.query(SummaryRecord)
    keypoint_query = db.query(KeypointRecord)

    doc_query = doc_query.filter(Document.user_id == resolved_user_id)
    quiz_query = quiz_query.filter(Quiz.user_id == resolved_user_id)
    attempt_query = attempt_query.filter(QuizAttempt.user_id == resolved_user_id)
    qa_query = qa_query.filter(QARecord.user_id == resolved_user_id)
    summary_query = summary_query.filter(SummaryRecord.user_id == resolved_user_id)
    keypoint_query = keypoint_query.filter(KeypointRecord.user_id == resolved_user_id)

    total = (
        doc_query.count()
        + summary_query.count()
        + keypoint_query.count()
        + qa_query.count()
        + attempt_query.count()
    )

    items: list[ActivityItem] = []

    doc_rows = (
        doc_query.order_by(Document.created_at.desc())
        .with_entities(Document.id, Document.filename, Document.created_at)
        .limit(fetch_window)
        .all()
    )
    summary_rows = (
        summary_query.order_by(SummaryRecord.created_at.desc())
        .with_entities(SummaryRecord.doc_id, SummaryRecord.created_at)
        .limit(fetch_window)
        .all()
    )
    keypoint_rows = (
        keypoint_query.order_by(KeypointRecord.created_at.desc())
        .with_entities(KeypointRecord.doc_id, KeypointRecord.created_at)
        .limit(fetch_window)
        .all()
    )
    qa_rows = (
        qa_query.order_by(QARecord.created_at.desc())
        .with_entities(QARecord.doc_id, QARecord.created_at, QARecord.question)
        .limit(fetch_window)
        .all()
    )
    attempt_rows = (
        attempt_query.order_by(QuizAttempt.created_at.desc())
        .with_entities(
            QuizAttempt.quiz_id,
            QuizAttempt.created_at,
            QuizAttempt.score,
            QuizAttempt.total,
        )
        .limit(fetch_window)
        .all()
    )

    quiz_ids = {row.quiz_id for row in attempt_rows if row.quiz_id}
    quiz_doc = {}
    if quiz_ids:
        quiz_doc = {
            quiz_id: doc_id
            for quiz_id, doc_id in (
                db.query(Quiz.id, Quiz.doc_id)
                .filter(Quiz.user_id == resolved_user_id, Quiz.id.in_(quiz_ids))
                .all()
            )
        }

    doc_name = {row.id: row.filename for row in doc_rows}
    all_doc_ids = {row.id for row in doc_rows}
    all_doc_ids.update(row.doc_id for row in summary_rows if row.doc_id)
    all_doc_ids.update(row.doc_id for row in keypoint_rows if row.doc_id)
    all_doc_ids.update(row.doc_id for row in qa_rows if row.doc_id)
    all_doc_ids.update(doc_id for doc_id in quiz_doc.values() if doc_id)
    _extend_doc_name_map(db, resolved_user_id, all_doc_ids, doc_name)

    for doc in doc_rows:
        items.append(
            ActivityItem(
                type="document_upload",
                timestamp=doc.created_at,
                doc_id=doc.id,
                doc_name=doc.filename,
                detail=f"Uploaded {doc.filename}",
            )
        )

    for record in summary_rows:
        items.append(
            ActivityItem(
                type="summary_generated",
                timestamp=record.created_at,
                doc_id=record.doc_id,
                doc_name=doc_name.get(record.doc_id),
                detail="Summary generated",
            )
        )

    for record in keypoint_rows:
        items.append(
            ActivityItem(
                type="keypoints_generated",
                timestamp=record.created_at,
                doc_id=record.doc_id,
                doc_name=doc_name.get(record.doc_id),
                detail="Keypoints generated",
            )
        )

    for record in qa_rows:
        items.append(
            ActivityItem(
                type="question_asked",
                timestamp=record.created_at,
                doc_id=record.doc_id,
                doc_name=doc_name.get(record.doc_id),
                detail=record.question,
            )
        )

    for attempt in attempt_rows:
        doc_id = quiz_doc.get(attempt.quiz_id)
        detail = "Quiz submitted (style mimic)" if doc_id is None else "Quiz submitted"
        items.append(
            ActivityItem(
                type="quiz_attempt",
                timestamp=attempt.created_at,
                doc_id=doc_id,
                doc_name=doc_name.get(doc_id) if doc_id else None,
                detail=detail,
                score=attempt.score,
                total=attempt.total,
            )
        )

    items.sort(key=lambda item: item.timestamp or datetime.min, reverse=True)
    paged_items = items[offset: offset + limit]
    return ActivityResponse(
        items=paged_items,
        total=total,
        offset=offset,
        limit=limit,
        has_more=(offset + len(paged_items)) < total,
    )
