import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.users import ensure_user
from app.db import get_db
from app.models import Document, Quiz, QuizAttempt
from app.schemas import QuizGenerateRequest, QuizGenerateResponse, QuizQuestion, QuizSubmitRequest, QuizSubmitResponse
from app.services.quiz import generate_quiz

router = APIRouter()


def _has_quiz_input(payload: QuizGenerateRequest) -> bool:
    """At least one of doc_id, reference_questions, or style_prompt must be provided."""
    return bool(
        (payload.doc_id and payload.doc_id.strip())
        or (payload.reference_questions and payload.reference_questions.strip())
        or (payload.style_prompt and payload.style_prompt.strip())
    )


@router.post("/quiz/generate", response_model=QuizGenerateResponse)
def create_quiz(payload: QuizGenerateRequest, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, payload.user_id)
    if not _has_quiz_input(payload):
        raise HTTPException(
            status_code=400,
            detail="At least one of doc_id, reference_questions, or style_prompt is required.",
        )

    if payload.doc_id:
        doc = db.query(Document).filter(Document.id == payload.doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if payload.user_id and doc.user_id != resolved_user_id:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.status != "ready":
            raise HTTPException(status_code=409, detail="Document is still processing")

    try:
        questions = generate_quiz(
            resolved_user_id,
            payload.doc_id,
            payload.count,
            payload.difficulty,
            style_prompt=payload.style_prompt,
            reference_questions=payload.reference_questions,
        )
        parsed = [QuizQuestion(**q) for q in questions]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Quiz generation failed. Check LLM output or model settings.",
        ) from exc

    quiz_id = str(uuid4())
    quiz = Quiz(
        id=quiz_id,
        user_id=resolved_user_id,
        doc_id=payload.doc_id,
        difficulty=payload.difficulty,
        question_type="mcq",
        questions_json=json.dumps(questions),
    )
    db.add(quiz)
    db.commit()

    return QuizGenerateResponse(quiz_id=quiz_id, questions=parsed)


@router.post("/quiz/submit", response_model=QuizSubmitResponse)
def submit_quiz(payload: QuizSubmitRequest, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, payload.user_id)
    quiz = db.query(Quiz).filter(Quiz.id == payload.quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if payload.user_id and quiz.user_id != resolved_user_id:
        raise HTTPException(status_code=404, detail="Quiz not found")

    questions = json.loads(quiz.questions_json)
    total = len(questions)
    results = []
    explanations = []
    correct = 0

    for idx, q in enumerate(questions):
        expected = q.get("answer_index")
        provided = payload.answers[idx] if idx < len(payload.answers) else None
        is_correct = provided == expected
        results.append(is_correct)
        explanations.append(q.get("explanation", ""))
        if is_correct:
            correct += 1

    score = correct / total if total else 0.0

    attempt = QuizAttempt(
        id=str(uuid4()),
        user_id=resolved_user_id,
        quiz_id=payload.quiz_id,
        answers_json=json.dumps(payload.answers),
        score=score,
        total=total,
    )
    db.add(attempt)
    db.commit()

    return QuizSubmitResponse(
        score=score,
        correct=correct,
        total=total,
        results=results,
        explanations=explanations,
    )
