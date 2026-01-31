from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.users import ensure_user
from app.db import get_db
from app.models import Document, KeypointRecord, Quiz, QuizAttempt, QARecord, SummaryRecord
from app.schemas import ProgressResponse

router = APIRouter()


@router.get("/progress", response_model=ProgressResponse)
def get_progress(user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
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

    total_docs = doc_query.count()
    total_quizzes = quiz_query.count()
    total_attempts = attempt_query.count()
    total_questions = qa_query.count()
    total_summaries = summary_query.count()
    total_keypoints = keypoint_query.count()
    avg_score = attempt_query.with_entities(func.avg(QuizAttempt.score)).scalar() or 0.0

    last_doc = doc_query.with_entities(func.max(Document.created_at)).scalar()
    last_quiz = quiz_query.with_entities(func.max(Quiz.created_at)).scalar()
    last_attempt = attempt_query.with_entities(func.max(QuizAttempt.created_at)).scalar()
    last_qa = qa_query.with_entities(func.max(QARecord.created_at)).scalar()
    last_summary = summary_query.with_entities(func.max(SummaryRecord.created_at)).scalar()
    last_keypoint = keypoint_query.with_entities(func.max(KeypointRecord.created_at)).scalar()

    last_activity = max(
        [
            dt
            for dt in (
                last_doc,
                last_quiz,
                last_attempt,
                last_qa,
                last_summary,
                last_keypoint,
            )
            if dt is not None
        ],
        default=None,
    )

    return ProgressResponse(
        total_docs=total_docs,
        total_quizzes=total_quizzes,
        total_attempts=total_attempts,
        total_questions=total_questions,
        total_summaries=total_summaries,
        total_keypoints=total_keypoints,
        avg_score=round(avg_score, 3),
        last_activity=last_activity,
    )
