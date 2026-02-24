from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.knowledge_bases import ensure_kb
from app.core.users import ensure_user
from app.db import get_db
from app.models import (
    Document,
    KeypointRecord,
    KnowledgeBase,
    QARecord,
    Quiz,
    QuizAttempt,
    SummaryRecord,
)
from app.schemas import ProgressByKb, ProgressResponse

router = APIRouter()


def _max_datetime(values):
    return max([v for v in values if v is not None], default=None)


def _count_and_last(query, id_col, ts_col):
    count_value, last_value = query.with_entities(
        func.count(id_col),
        func.max(ts_col),
    ).one()
    return int(count_value or 0), last_value


@router.get("/progress", response_model=ProgressResponse)
def get_progress(
    user_id: str | None = None,
    kb_id: str | None = None,
    db: Session = Depends(get_db),
):
    resolved_user_id = ensure_user(db, user_id)

    if kb_id:
        try:
            kb = ensure_kb(db, resolved_user_id, kb_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        doc_query = db.query(Document).filter(
            Document.kb_id == kb.id,
            Document.user_id == resolved_user_id,
        )
        total_docs, last_doc = _count_and_last(doc_query, Document.id, Document.created_at)

        summary_query = (
            db.query(SummaryRecord)
            .join(Document, SummaryRecord.doc_id == Document.id)
            .filter(
                SummaryRecord.user_id == resolved_user_id,
                Document.user_id == resolved_user_id,
                Document.kb_id == kb.id,
            )
        )
        total_summaries, last_summary = _count_and_last(
            summary_query, SummaryRecord.id, SummaryRecord.created_at
        )

        keypoint_query = (
            db.query(KeypointRecord)
            .join(Document, KeypointRecord.doc_id == Document.id)
            .filter(
                KeypointRecord.user_id == resolved_user_id,
                Document.user_id == resolved_user_id,
                Document.kb_id == kb.id,
            )
        )
        total_keypoints, last_keypoint = _count_and_last(
            keypoint_query, KeypointRecord.id, KeypointRecord.created_at
        )

        quiz_query = (
            db.query(Quiz)
            .join(Document, Quiz.doc_id == Document.id)
            .filter(
                Quiz.user_id == resolved_user_id,
                Document.user_id == resolved_user_id,
                Document.kb_id == kb.id,
            )
        )
        total_quizzes, last_quiz = _count_and_last(quiz_query, Quiz.id, Quiz.created_at)

        qa_query = (
            db.query(QARecord)
            .outerjoin(Document, QARecord.doc_id == Document.id)
            .filter(
                QARecord.user_id == resolved_user_id,
                or_(QARecord.kb_id == kb.id, Document.kb_id == kb.id),
            )
        )
        total_questions, last_qa = _count_and_last(qa_query, QARecord.id, QARecord.created_at)

        attempt_query = (
            db.query(QuizAttempt)
            .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
            .join(Document, Quiz.doc_id == Document.id)
            .filter(
                QuizAttempt.user_id == resolved_user_id,
                Quiz.user_id == resolved_user_id,
                Document.user_id == resolved_user_id,
                Document.kb_id == kb.id,
            )
        )
        total_attempts, avg_score, last_attempt = attempt_query.with_entities(
            func.count(QuizAttempt.id),
            func.avg(QuizAttempt.score),
            func.max(QuizAttempt.created_at),
        ).one()
        total_attempts = int(total_attempts or 0)
        avg_score = float(avg_score or 0.0)

        last_activity = _max_datetime(
            [
                last_doc,
                last_quiz,
                last_attempt,
                last_qa,
                last_summary,
                last_keypoint,
            ]
        )

        avg_score_value = round(avg_score or 0.0, 3)
        by_kb = [
            ProgressByKb(
                kb_id=kb.id,
                kb_name=kb.name,
                total_docs=total_docs,
                total_quizzes=total_quizzes,
                total_attempts=total_attempts,
                total_questions=total_questions,
                total_summaries=total_summaries,
                total_keypoints=total_keypoints,
                avg_score=avg_score_value,
                last_activity=last_activity,
            )
        ]

        return ProgressResponse(
            total_docs=total_docs,
            total_quizzes=total_quizzes,
            total_attempts=total_attempts,
            total_questions=total_questions,
            total_summaries=total_summaries,
            total_keypoints=total_keypoints,
            avg_score=avg_score_value,
            last_activity=last_activity,
            by_kb=by_kb,
        )

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

    total_docs, last_doc = _count_and_last(doc_query, Document.id, Document.created_at)
    total_quizzes, last_quiz = _count_and_last(quiz_query, Quiz.id, Quiz.created_at)
    total_questions, last_qa = _count_and_last(qa_query, QARecord.id, QARecord.created_at)
    total_summaries, last_summary = _count_and_last(
        summary_query, SummaryRecord.id, SummaryRecord.created_at
    )
    total_keypoints, last_keypoint = _count_and_last(
        keypoint_query, KeypointRecord.id, KeypointRecord.created_at
    )
    total_attempts, avg_score, last_attempt = attempt_query.with_entities(
        func.count(QuizAttempt.id),
        func.avg(QuizAttempt.score),
        func.max(QuizAttempt.created_at),
    ).one()
    total_attempts = int(total_attempts or 0)
    avg_score = float(avg_score or 0.0)

    last_activity = _max_datetime(
        [
            last_doc,
            last_quiz,
            last_attempt,
            last_qa,
            last_summary,
            last_keypoint,
        ]
    )

    kb_query = db.query(KnowledgeBase)
    kb_query = kb_query.filter(KnowledgeBase.user_id == resolved_user_id)
    kbs = kb_query.order_by(KnowledgeBase.created_at.asc()).all()

    doc_rows = db.query(
        Document.kb_id,
        func.count(Document.id),
        func.max(Document.created_at),
    )
    doc_rows = doc_rows.filter(Document.user_id == resolved_user_id)
    doc_rows = doc_rows.group_by(Document.kb_id).all()
    doc_counts = {row[0]: row[1] for row in doc_rows if row[0]}
    doc_last = {row[0]: row[2] for row in doc_rows if row[0]}

    summary_rows = db.query(
        Document.kb_id,
        func.count(SummaryRecord.id),
        func.max(SummaryRecord.created_at),
    ).join(Document, SummaryRecord.doc_id == Document.id)
    summary_rows = summary_rows.filter(SummaryRecord.user_id == resolved_user_id)
    summary_rows = summary_rows.group_by(Document.kb_id).all()
    summary_counts = {row[0]: row[1] for row in summary_rows if row[0]}
    summary_last = {row[0]: row[2] for row in summary_rows if row[0]}

    keypoint_rows = db.query(
        Document.kb_id,
        func.count(KeypointRecord.id),
        func.max(KeypointRecord.created_at),
    ).join(Document, KeypointRecord.doc_id == Document.id)
    keypoint_rows = keypoint_rows.filter(KeypointRecord.user_id == resolved_user_id)
    keypoint_rows = keypoint_rows.group_by(Document.kb_id).all()
    keypoint_counts = {row[0]: row[1] for row in keypoint_rows if row[0]}
    keypoint_last = {row[0]: row[2] for row in keypoint_rows if row[0]}

    quiz_rows = db.query(
        Document.kb_id,
        func.count(Quiz.id),
        func.max(Quiz.created_at),
    ).join(Document, Quiz.doc_id == Document.id)
    quiz_rows = quiz_rows.filter(Quiz.user_id == resolved_user_id)
    quiz_rows = quiz_rows.group_by(Document.kb_id).all()
    quiz_counts = {row[0]: row[1] for row in quiz_rows if row[0]}
    quiz_last = {row[0]: row[2] for row in quiz_rows if row[0]}

    attempt_rows = db.query(
        Document.kb_id,
        func.count(QuizAttempt.id),
        func.avg(QuizAttempt.score),
        func.max(QuizAttempt.created_at),
    ).join(Quiz, QuizAttempt.quiz_id == Quiz.id)
    attempt_rows = attempt_rows.join(Document, Quiz.doc_id == Document.id)
    attempt_rows = attempt_rows.filter(QuizAttempt.user_id == resolved_user_id)
    attempt_rows = attempt_rows.group_by(Document.kb_id).all()
    attempt_counts = {row[0]: row[1] for row in attempt_rows if row[0]}
    attempt_avg = {row[0]: row[2] for row in attempt_rows if row[0]}
    attempt_last = {row[0]: row[3] for row in attempt_rows if row[0]}

    qa_kb = func.coalesce(QARecord.kb_id, Document.kb_id)
    qa_rows = db.query(
        qa_kb,
        func.count(QARecord.id),
        func.max(QARecord.created_at),
    ).outerjoin(Document, QARecord.doc_id == Document.id)
    qa_rows = qa_rows.filter(QARecord.user_id == resolved_user_id)
    qa_rows = qa_rows.group_by(qa_kb).all()
    qa_counts = {row[0]: row[1] for row in qa_rows if row[0]}
    qa_last = {row[0]: row[2] for row in qa_rows if row[0]}

    by_kb: list[ProgressByKb] = []
    for kb in kbs:
        kb_id = kb.id
        last_kb_activity = _max_datetime(
            [
                doc_last.get(kb_id),
                quiz_last.get(kb_id),
                attempt_last.get(kb_id),
                qa_last.get(kb_id),
                summary_last.get(kb_id),
                keypoint_last.get(kb_id),
            ]
        )
        by_kb.append(
            ProgressByKb(
                kb_id=kb_id,
                kb_name=kb.name,
                total_docs=doc_counts.get(kb_id, 0),
                total_quizzes=quiz_counts.get(kb_id, 0),
                total_attempts=attempt_counts.get(kb_id, 0),
                total_questions=qa_counts.get(kb_id, 0),
                total_summaries=summary_counts.get(kb_id, 0),
                total_keypoints=keypoint_counts.get(kb_id, 0),
                avg_score=round(attempt_avg.get(kb_id, 0.0) or 0.0, 3),
                last_activity=last_kb_activity,
            )
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
        by_kb=by_kb,
    )
