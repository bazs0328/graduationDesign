import json
import logging
import os
import tempfile
from collections import defaultdict
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.knowledge_bases import ensure_kb
from app.core.users import ensure_user
from app.db import get_db
from app.models import Document, Keypoint, Quiz, QuizAttempt
from app.schemas import (
    MasteryUpdate,
    ParseReferenceResponse,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestion,
    QuizFeedback,
    QuizSubmitRequest,
    QuizSubmitResponse,
    NextQuizRecommendation,
    WrongQuestionGroup,
)
from app.services.learner_profile import (
    extract_weak_concepts,
    generate_difficulty_plan,
    get_weak_concepts_by_mastery,
    get_or_create_profile,
    update_profile_after_quiz,
)
from app.services.keypoints import (
    match_keypoints_by_concepts,
    match_keypoints_by_kb,
)
from app.services.mastery import record_quiz_result
from app.services.quiz import generate_quiz
from app.services.text_extraction import extract_text
from app.utils.document_validator import DocumentValidator

logger = logging.getLogger(__name__)

router = APIRouter()


def _has_quiz_input(payload: QuizGenerateRequest) -> bool:
    """At least one of doc_id, kb_id, or reference_questions must be provided."""
    return bool(
        (payload.doc_id and payload.doc_id.strip())
        or (payload.kb_id and payload.kb_id.strip())
        or (payload.reference_questions and payload.reference_questions.strip())
    )


def _split_counts(total: int, ratios: dict[str, float]) -> dict[str, int]:
    counts = {key: int(total * ratio) for key, ratio in ratios.items()}
    remainder = total - sum(counts.values())

    if remainder > 0:
        for key, _ in sorted(ratios.items(), key=lambda item: item[1], reverse=True):
            if remainder <= 0:
                break
            counts[key] += 1
            remainder -= 1
    elif remainder < 0:
        for key, _ in sorted(ratios.items(), key=lambda item: item[1], reverse=True):
            if remainder >= 0:
                break
            if counts[key] > 0:
                counts[key] -= 1
                remainder += 1

    return counts


def _group_wrong_questions_by_concept(
    questions: list[dict], results: list[bool]
) -> list[WrongQuestionGroup]:
    """Group wrong questions by concept name."""
    grouped: dict[str, list[int]] = defaultdict(list)
    for idx, (question, is_correct) in enumerate(zip(questions, results)):
        if is_correct:
            continue
        concepts = question.get("concepts") or []
        if not isinstance(concepts, list):
            continue
        for concept in concepts:
            concept_name = str(concept).strip()
            if concept_name:
                grouped[concept_name].append(idx + 1)

    return [
        WrongQuestionGroup(concept=concept, question_indices=indices)
        for concept, indices in sorted(grouped.items())
    ]


@router.post("/quiz/generate", response_model=QuizGenerateResponse)
def create_quiz(payload: QuizGenerateRequest, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, payload.user_id)
    if not _has_quiz_input(payload):
        raise HTTPException(
            status_code=400,
            detail="At least one of doc_id, kb_id, or reference_questions is required.",
        )

    if payload.doc_id:
        doc = db.query(Document).filter(Document.id == payload.doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if payload.user_id and doc.user_id != resolved_user_id:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.status != "ready":
            raise HTTPException(status_code=409, detail="Document is still processing")

    if payload.kb_id:
        try:
            ensure_kb(db, resolved_user_id, payload.kb_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        if payload.auto_adapt and payload.difficulty is None:
            profile = get_or_create_profile(db, resolved_user_id)
            plan = generate_difficulty_plan(profile)
            counts = _split_counts(
                payload.count,
                {"easy": plan.easy, "medium": plan.medium, "hard": plan.hard},
            )
            questions = []
            for difficulty, count in counts.items():
                if count <= 0:
                    continue
                questions.extend(
                    generate_quiz(
                        resolved_user_id,
                        payload.doc_id,
                        count,
                        difficulty,
                        kb_id=payload.kb_id,
                        focus_concepts=payload.focus_concepts,
                        style_prompt=payload.style_prompt,
                        reference_questions=payload.reference_questions,
                    )
                )
            if len(questions) > payload.count:
                questions = questions[: payload.count]
            difficulty_label = "adaptive"
        else:
            difficulty = payload.difficulty or "medium"
            questions = generate_quiz(
                resolved_user_id,
                payload.doc_id,
                payload.count,
                difficulty,
                kb_id=payload.kb_id,
                focus_concepts=payload.focus_concepts,
                style_prompt=payload.style_prompt,
                reference_questions=payload.reference_questions,
            )
            difficulty_label = difficulty
        parsed = [QuizQuestion(**q) for q in questions]
    except ValueError as exc:
        logger.exception("Quiz generation validation error")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Quiz generation failed with unexpected error")
        raise HTTPException(
            status_code=500,
            detail=f"Quiz generation failed: {str(exc)}. Check LLM output or model settings.",
        ) from exc

    quiz_id = str(uuid4())
    quiz = Quiz(
        id=quiz_id,
        user_id=resolved_user_id,
        kb_id=payload.kb_id,
        doc_id=payload.doc_id,
        difficulty=difficulty_label,
        question_type="mcq",
        questions_json=json.dumps(questions),
    )
    db.add(quiz)
    db.commit()

    return QuizGenerateResponse(quiz_id=quiz_id, questions=parsed)


@router.post("/quiz/parse-reference", response_model=ParseReferenceResponse)
def parse_reference_pdf(file: UploadFile = File(...)):
    """Parse a reference exam PDF to plain text; does not persist. Return text for use as reference_questions."""
    if not file.filename or not file.filename.strip():
        raise HTTPException(status_code=400, detail="Missing filename")

    try:
        safe_name = DocumentValidator.validate_upload_safety(
            file.filename,
            None,
            allowed_extensions={".pdf"},
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_size = 0
    max_size = DocumentValidator.MAX_PDF_SIZE
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    raise HTTPException(
                        status_code=400,
                        detail="PDF file too large",
                    )
                tmp.write(chunk)

        try:
            DocumentValidator.validate_upload_safety(
                safe_name, total_size, allowed_extensions={".pdf"}, content_type=file.content_type
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            result = extract_text(tmp_path, ".pdf")
        except Exception as exc:
            detail = str(exc).strip() or "Failed to extract text from PDF."
            raise HTTPException(
                status_code=500,
                detail=detail,
            ) from exc

        if not result.text or not result.text.strip():
            raise HTTPException(
                status_code=400,
                detail="No text extracted from PDF",
            )
        return ParseReferenceResponse(text=result.text)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _resolve_keypoints_for_question(
    q: dict, user_id: str, doc_id: str | None, kb_id: str | None,
) -> list[str]:
    """Get keypoint_ids for a question: prefer pre-bound ids, fallback to concept search."""
    kp_ids = q.get("keypoint_ids")
    if kp_ids and isinstance(kp_ids, list):
        return [k for k in kp_ids if isinstance(k, str)]

    concepts = q.get("concepts") or []
    if not concepts:
        return []
    if doc_id:
        return match_keypoints_by_concepts(user_id, doc_id, concepts)
    if kb_id:
        return match_keypoints_by_kb(user_id, kb_id, concepts)
    return []


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
    mastery_deltas: dict[str, tuple[float, float]] = {}

    for idx, q in enumerate(questions):
        expected = q.get("answer_index")
        provided = payload.answers[idx] if idx < len(payload.answers) else None
        is_correct = provided == expected
        results.append(is_correct)
        explanations.append(q.get("explanation", ""))
        if is_correct:
            correct += 1

        kp_ids = _resolve_keypoints_for_question(
            q, resolved_user_id, quiz.doc_id, quiz.kb_id
        )
        for kp_id in kp_ids:
            delta = record_quiz_result(db, kp_id, is_correct)
            if not delta:
                continue
            old_lv, new_lv = delta
            previous = mastery_deltas.get(kp_id)
            if previous:
                # Keep the initial old level, but always refresh to the latest new level
                # so quiz summary stays consistent with persisted mastery.
                mastery_deltas[kp_id] = (previous[0], new_lv)
            else:
                mastery_deltas[kp_id] = (old_lv, new_lv)

    mastery_updates: list[MasteryUpdate] = []
    if mastery_deltas:
        kp_rows = (
            db.query(Keypoint)
            .filter(Keypoint.id.in_(mastery_deltas.keys()))
            .all()
        )
        kp_text_map = {kp.id: kp.text for kp in kp_rows}
        for kp_id, (old_lv, new_lv) in mastery_deltas.items():
            mastery_updates.append(
                MasteryUpdate(
                    keypoint_id=kp_id,
                    text=kp_text_map.get(kp_id, ""),
                    old_level=old_lv,
                    new_level=new_lv,
                )
            )

    score = correct / total if total else 0.0
    first_five_wrong = sum(1 for item in results[:5] if not item)
    weak_concepts = extract_weak_concepts(questions, results)
    _, profile_delta = update_profile_after_quiz(
        db, resolved_user_id, score, weak_concepts
    )
    weak_concepts_by_mastery = get_weak_concepts_by_mastery(db, resolved_user_id)
    wrong_questions_by_concept = _group_wrong_questions_by_concept(questions, results)

    feedback = None
    next_quiz_recommendation = None
    if score < 0.3 or first_five_wrong >= 4:
        feedback = QuizFeedback(
            type="encouragement",
            message="本次题目难度偏高，下次会为你调整更适合的题目，继续加油！",
        )
        next_quiz_recommendation = NextQuizRecommendation(
            difficulty="easy",
            focus_concepts=weak_concepts_by_mastery,
        )

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
        feedback=feedback,
        next_quiz_recommendation=next_quiz_recommendation,
        profile_delta=profile_delta,
        wrong_questions_by_concept=wrong_questions_by_concept,
        mastery_updates=mastery_updates,
    )
