import json
import logging
import os
import tempfile
from collections import defaultdict
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
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
from app.services.aggregate_mastery import resolve_effective_kb_id
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
from app.services.keypoint_dedup import (
    build_keypoint_cluster_index,
    collapse_kb_keypoint_ids_to_representatives,
    cluster_kb_keypoints,
    normalize_keypoint_text,
)
from app.services.learning_path import (
    get_unlocked_keypoint_ids,
)
from app.services.mastery import record_quiz_result
from app.services.quiz import filter_quiz_questions_quality, generate_quiz
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


def _normalize_focus_concepts(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        text = str(raw or "").strip()
        if not text:
            continue
        key = normalize_keypoint_text(text) or text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def _ensure_focus_concepts_unlocked(
    db: Session,
    user_id: str,
    kb_id: str,
    focus_concepts: list[str] | None,
) -> None:
    normalized_focus = _normalize_focus_concepts(focus_concepts)
    if not normalized_focus:
        return

    clusters = cluster_kb_keypoints(db, user_id, kb_id)
    if not clusters:
        return
    representative_keypoints = [cluster.representative_keypoint for cluster in clusters]
    cluster_map = {cluster.representative_id: cluster for cluster in clusters}
    unlocked_ids = get_unlocked_keypoint_ids(
        db,
        user_id,
        kb_id,
        keypoints=representative_keypoints,
        cluster_map=cluster_map,
    )

    representative_by_exact_text: dict[str, Keypoint] = {}
    representative_by_normalized_text: dict[str, Keypoint] = {}
    for cluster in clusters:
        representative = cluster.representative_keypoint
        rep_text = str(representative.text or "").strip()
        if rep_text and rep_text not in representative_by_exact_text:
            representative_by_exact_text[rep_text] = representative
        normalized_rep_text = normalize_keypoint_text(rep_text)
        if normalized_rep_text and normalized_rep_text not in representative_by_normalized_text:
            representative_by_normalized_text[normalized_rep_text] = representative
        for member in cluster.members:
            member_text = str(member.keypoint.text or "").strip()
            if member_text and member_text not in representative_by_exact_text:
                representative_by_exact_text[member_text] = representative
            normalized_member_text = normalize_keypoint_text(member_text)
            if (
                normalized_member_text
                and normalized_member_text not in representative_by_normalized_text
            ):
                representative_by_normalized_text[normalized_member_text] = representative

    blocked_labels: list[str] = []
    blocked_seen: set[str] = set()
    for concept in normalized_focus:
        representative = representative_by_exact_text.get(concept)
        if representative is None:
            representative = representative_by_normalized_text.get(
                normalize_keypoint_text(concept)
            )
        if not representative:
            continue
        representative_id = str(representative.id or "")
        if not representative_id or representative_id in unlocked_ids:
            continue

        label = str(representative.text or concept).strip() or concept
        key = normalize_keypoint_text(label) or label.lower()
        if key in blocked_seen:
            continue
        blocked_seen.add(key)
        blocked_labels.append(label)

    if not blocked_labels:
        return
    blocked_preview = "、".join(blocked_labels[:5])
    blocked_suffix = "" if len(blocked_labels) <= 5 else " 等"
    raise HTTPException(
        status_code=409,
        detail=f"Focus concepts are locked by learning path prerequisites: {blocked_preview}{blocked_suffix}",
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


def _collapse_kb_keypoint_ids(
    db: Session,
    user_id: str,
    kb_id: str,
    kp_ids: list[str],
    kb_member_to_rep: dict[str, str] | None = None,
) -> list[str]:
    """Collapse KB keypoint ids to representative ids and deduplicate."""
    if not kp_ids:
        return []
    if kb_member_to_rep is not None:
        out: list[str] = []
        seen: set[str] = set()
        for kp_id in kp_ids:
            rep_id = kb_member_to_rep.get(kp_id, kp_id)
            if rep_id in seen:
                continue
            seen.add(rep_id)
            out.append(rep_id)
        return out
    return collapse_kb_keypoint_ids_to_representatives(db, user_id, kb_id, kp_ids)


def _build_kb_member_to_rep_index(
    db: Session,
    user_id: str,
    kb_id: str,
) -> dict[str, str]:
    """Build a KB member->representative index once for dedup-aware mastery updates."""
    return build_keypoint_cluster_index(cluster_kb_keypoints(db, user_id, kb_id))


def _build_kb_mastery_guard_context(
    db: Session,
    user_id: str,
    kb_id: str,
) -> tuple[dict[str, str], set[str]]:
    """Build KB dedup + learning-path unlock context once per request."""
    clusters = cluster_kb_keypoints(db, user_id, kb_id)
    member_to_rep = build_keypoint_cluster_index(clusters)
    representative_keypoints = [cluster.representative_keypoint for cluster in clusters]
    cluster_map = {cluster.representative_id: cluster for cluster in clusters}
    unlocked_ids = get_unlocked_keypoint_ids(
        db,
        user_id,
        kb_id,
        keypoints=representative_keypoints,
        cluster_map=cluster_map,
    )
    return member_to_rep, unlocked_ids


def _clean_bound_keypoint_ids(
    values: object,
) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        cleaned.append(candidate)
    return cleaned


def _resolve_primary_keypoint_for_submit(
    db: Session,
    q: dict,
    user_id: str,
    kb_id: str | None,
    kb_member_to_rep: dict[str, str] | None,
    unlocked_ids: set[str] | None,
) -> tuple[str | None, str | None]:
    """Resolve one submit-time target keypoint from pre-bound fields only."""
    primary_raw = q.get("primary_keypoint_id")
    primary_id = primary_raw.strip() if isinstance(primary_raw, str) else ""
    candidate_ids = _clean_bound_keypoint_ids(q.get("keypoint_ids"))

    if kb_id:
        if primary_id:
            collapsed_primary = _collapse_kb_keypoint_ids(
                db,
                user_id,
                kb_id,
                [primary_id],
                kb_member_to_rep=kb_member_to_rep,
            )
            primary_id = collapsed_primary[0] if collapsed_primary else ""
        candidate_ids = _collapse_kb_keypoint_ids(
            db,
            user_id,
            kb_id,
            candidate_ids,
            kb_member_to_rep=kb_member_to_rep,
        )

    ordered_candidates: list[str] = []
    seen: set[str] = set()
    if primary_id and primary_id not in seen:
        seen.add(primary_id)
        ordered_candidates.append(primary_id)
    for kp_id in candidate_ids:
        if kp_id in seen:
            continue
        seen.add(kp_id)
        ordered_candidates.append(kp_id)

    if not ordered_candidates:
        return None, "missing_binding"
    if unlocked_ids is None:
        return ordered_candidates[0], None
    for kp_id in ordered_candidates:
        if kp_id in unlocked_ids:
            return kp_id, None
    return None, "locked"


def _match_keypoints_by_free_text(
    db: Session,
    user_id: str,
    doc_id: str | None,
    kb_id: str | None,
    text: str,
    kb_member_to_rep: dict[str, str] | None = None,
) -> list[str]:
    """Fallback vector match using full question/explanation text, limited to top-1."""
    query_text = str(text or "").strip()
    if not query_text:
        return []
    if doc_id:
        matched = match_keypoints_by_concepts(
            user_id,
            doc_id,
            [query_text],
            top_k=1,
        )
        if kb_id and matched:
            return _collapse_kb_keypoint_ids(
                db,
                user_id,
                kb_id,
                matched,
                kb_member_to_rep=kb_member_to_rep,
            )
        return matched
    if kb_id:
        matched = match_keypoints_by_kb(
            user_id,
            kb_id,
            [query_text],
            top_k=1,
        )
        return _collapse_kb_keypoint_ids(
            db,
            user_id,
            kb_id,
            matched,
            kb_member_to_rep=kb_member_to_rep,
        )
    return []


def _prebind_quiz_question_keypoints(
    db: Session,
    questions: list[dict],
    user_id: str,
    doc_id: str | None,
    kb_id: str | None,
) -> None:
    """
    Attach hidden `keypoint_ids` to questions before quiz persistence.

    These ids are stored in Quiz.questions_json and used by /quiz/submit for stable mastery updates.
    """
    if not (doc_id or kb_id):
        return

    total_questions = 0
    bound_questions = 0
    bound_refs = 0
    kb_member_to_rep: dict[str, str] | None = None

    for q in questions or []:
        if not isinstance(q, dict):
            continue
        total_questions += 1

        if kb_id and kb_member_to_rep is None:
            kb_member_to_rep = _build_kb_member_to_rep_index(db, user_id, kb_id)

        kp_ids = _resolve_keypoints_for_question(
            db,
            q,
            user_id,
            doc_id,
            kb_id,
            kb_member_to_rep=kb_member_to_rep,
        )
        if not kp_ids:
            continue

        q["keypoint_ids"] = kp_ids
        q["primary_keypoint_id"] = kp_ids[0]
        bound_questions += 1
        bound_refs += len(kp_ids)

    if total_questions > 0:
        logger.info(
            "Quiz question keypoint prebind summary user_id=%s doc_id=%s kb_id=%s total=%s bound=%s refs=%s",
            user_id,
            doc_id,
            kb_id,
            total_questions,
            bound_questions,
            bound_refs,
        )


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
        if doc.user_id != resolved_user_id:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.status != "ready":
            raise HTTPException(status_code=409, detail="Document is still processing")

    if payload.kb_id:
        try:
            ensure_kb(db, resolved_user_id, payload.kb_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    effective_kb_id = resolve_effective_kb_id(
        db,
        resolved_user_id,
        doc_id=payload.doc_id,
        kb_id=payload.kb_id,
    )
    if effective_kb_id and payload.focus_concepts:
        _ensure_focus_concepts_unlocked(
            db,
            resolved_user_id,
            effective_kb_id,
            payload.focus_concepts,
        )

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
                existing_stems = [str(item.get("question") or "") for item in questions if isinstance(item, dict)]
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
                        avoid_question_texts=existing_stems,
                    )
                )
            if questions:
                questions = filter_quiz_questions_quality(
                    questions,
                    target_count=payload.count,
                    focus_concepts=payload.focus_concepts,
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
        _prebind_quiz_question_keypoints(
            db,
            questions,
            resolved_user_id,
            payload.doc_id,
            effective_kb_id,
        )
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
    db: Session,
    q: dict,
    user_id: str,
    doc_id: str | None,
    kb_id: str | None,
    kb_member_to_rep: dict[str, str] | None = None,
) -> list[str]:
    """Get keypoint_ids for a question: prefer pre-bound ids, fallback to concept search."""
    kp_ids = q.get("keypoint_ids")
    if kp_ids and isinstance(kp_ids, list):
        cleaned = [k for k in kp_ids if isinstance(k, str)]
        if kb_id:
            return _collapse_kb_keypoint_ids(
                db,
                user_id,
                kb_id,
                cleaned,
                kb_member_to_rep=kb_member_to_rep,
            )
        return cleaned

    concepts = q.get("concepts") or []
    if not isinstance(concepts, list):
        concepts = []
    if doc_id:
        matched = match_keypoints_by_concepts(user_id, doc_id, concepts) if concepts else []
        if matched:
            if kb_id:
                return _collapse_kb_keypoint_ids(
                    db,
                    user_id,
                    kb_id,
                    matched,
                    kb_member_to_rep=kb_member_to_rep,
                )
            return matched
    if kb_id:
        matched = match_keypoints_by_kb(user_id, kb_id, concepts) if concepts else []
        if matched:
            return _collapse_kb_keypoint_ids(
                db,
                user_id,
                kb_id,
                matched,
                kb_member_to_rep=kb_member_to_rep,
            )

    for field in ("question", "explanation"):
        matched = _match_keypoints_by_free_text(
            db,
            user_id,
            doc_id,
            kb_id,
            str(q.get(field) or ""),
            kb_member_to_rep=kb_member_to_rep,
        )
        if matched:
            return matched
    return []


@router.post("/quiz/submit", response_model=QuizSubmitResponse)
def submit_quiz(payload: QuizSubmitRequest, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, payload.user_id)
    quiz = db.query(Quiz).filter(Quiz.id == payload.quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if quiz.user_id != resolved_user_id:
        raise HTTPException(status_code=404, detail="Quiz not found")
    existing_attempt = (
        db.query(QuizAttempt)
        .filter(
            QuizAttempt.quiz_id == payload.quiz_id,
            QuizAttempt.user_id == resolved_user_id,
        )
        .first()
    )
    if existing_attempt:
        raise HTTPException(status_code=409, detail="Quiz already submitted")

    questions = json.loads(quiz.questions_json)
    total = len(questions)
    results = []
    explanations = []
    correct = 0
    mastery_deltas: dict[str, tuple[float, float]] = {}
    kb_member_to_rep: dict[str, str] | None = None
    unlocked_ids: set[str] | None = None
    updated_count = 0
    skipped_missing_binding = 0
    skipped_locked = 0
    effective_kb_id = resolve_effective_kb_id(
        db,
        resolved_user_id,
        doc_id=quiz.doc_id,
        kb_id=quiz.kb_id,
    )
    if effective_kb_id:
        kb_member_to_rep, unlocked_ids = _build_kb_mastery_guard_context(
            db,
            resolved_user_id,
            effective_kb_id,
        )

    for idx, q in enumerate(questions):
        expected = q.get("answer_index")
        provided = payload.answers[idx] if idx < len(payload.answers) else None
        is_correct = provided == expected
        results.append(is_correct)
        explanations.append(q.get("explanation", ""))
        if is_correct:
            correct += 1

        target_kp_id, skip_reason = _resolve_primary_keypoint_for_submit(
            db,
            q,
            resolved_user_id,
            effective_kb_id,
            kb_member_to_rep,
            unlocked_ids,
        )
        if not target_kp_id:
            if skip_reason == "locked":
                skipped_locked += 1
            else:
                skipped_missing_binding += 1
            continue

        delta = record_quiz_result(db, target_kp_id, is_correct)
        if not delta:
            skipped_missing_binding += 1
            continue

        updated_count += 1
        old_lv, new_lv = delta
        previous = mastery_deltas.get(target_kp_id)
        if previous:
            # Keep the initial old level, but always refresh to the latest new level
            # so quiz summary stays consistent with persisted mastery.
            mastery_deltas[target_kp_id] = (previous[0], new_lv)
        else:
            mastery_deltas[target_kp_id] = (old_lv, new_lv)

    logger.info(
        "Quiz submit mastery summary quiz_id=%s user_id=%s total=%s updated_count=%s skipped_missing_binding=%s skipped_locked=%s",
        payload.quiz_id,
        resolved_user_id,
        total,
        updated_count,
        skipped_missing_binding,
        skipped_locked,
    )
    if total > 0 and not mastery_deltas:
        logger.warning(
            "Quiz submit produced no mastery updates quiz_id=%s user_id=%s doc_id=%s kb_id=%s total=%s skipped_missing_binding=%s skipped_locked=%s",
            payload.quiz_id,
            resolved_user_id,
            quiz.doc_id,
            quiz.kb_id,
            total,
            skipped_missing_binding,
            skipped_locked,
        )

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
        db,
        resolved_user_id,
        score,
        weak_concepts,
        quiz_difficulty=quiz.difficulty,
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
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        msg = str(getattr(exc, "orig", exc)).lower()
        if "quiz_attempts" in msg and ("user_id" in msg and "quiz_id" in msg):
            raise HTTPException(status_code=409, detail="Quiz already submitted") from exc
        raise
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
