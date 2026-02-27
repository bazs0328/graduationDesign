import json
import logging
import os
import re
import tempfile
from collections import defaultdict
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.knowledge_bases import ensure_kb
from app.core.users import ensure_user
from app.db import get_db
from app.models import Document, Keypoint, Quiz, QuizAttempt
from app.schemas import (
    MasteryGuardStats,
    MasteryUpdate,
    PaperBlueprint,
    PaperMeta,
    PaperSectionBlueprint,
    PaperSectionMeta,
    ParseReferenceResponse,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestionResult,
    QuizSectionScore,
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
from app.services.mastery import record_quiz_result_guarded
from app.services.quiz import (
    QUIZ_TYPE_FILL_BLANK,
    QUIZ_TYPE_MULTIPLE,
    QUIZ_TYPE_SINGLE,
    QUIZ_TYPE_TRUE_FALSE,
    filter_quiz_questions_quality,
    generate_quiz,
)
from app.services.text_extraction import extract_text
from app.utils.document_validator import DocumentValidator

logger = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_PAPER_DURATION_MINUTES = 20
DEFAULT_PAPER_TITLE = "自动组卷"
DEFAULT_SECTION_RATIOS = {
    QUIZ_TYPE_SINGLE: 0.5,
    QUIZ_TYPE_MULTIPLE: 0.2,
    QUIZ_TYPE_TRUE_FALSE: 0.15,
    QUIZ_TYPE_FILL_BLANK: 0.15,
}
DEFAULT_SECTION_ORDER = [
    QUIZ_TYPE_SINGLE,
    QUIZ_TYPE_MULTIPLE,
    QUIZ_TYPE_TRUE_FALSE,
    QUIZ_TYPE_FILL_BLANK,
]
ANSWER_TRUE_SYNONYMS = {"true", "t", "yes", "y", "1", "正确", "对", "是"}
ANSWER_FALSE_SYNONYMS = {"false", "f", "no", "n", "0", "错误", "错", "否"}
FILL_BLANK_PLACEHOLDER_RE = re.compile(r"_{3,}|＿{3,}|\(\s*\)|（\s*）|\[\s*\]|【\s*】")
FILL_BLANK_CANONICAL_PLACEHOLDER = "____"


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


def _normalize_scope_key(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return normalize_keypoint_text(text) or text.lower()


def _build_unlocked_scope_index(
    db: Session,
    user_id: str,
    kb_id: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """
    Build unlocked concept lookup:
    - concept_key -> representative_keypoint_id
    - representative_keypoint_id -> display_text
    """
    clusters = cluster_kb_keypoints(db, user_id, kb_id)
    if not clusters:
        return {}, {}

    representative_keypoints = [cluster.representative_keypoint for cluster in clusters]
    cluster_map = {cluster.representative_id: cluster for cluster in clusters}
    unlocked_ids = get_unlocked_keypoint_ids(
        db,
        user_id,
        kb_id,
        keypoints=representative_keypoints,
        cluster_map=cluster_map,
    )

    concept_to_rep: dict[str, str] = {}
    rep_to_label: dict[str, str] = {}
    for cluster in clusters:
        rep_id = str(cluster.representative_id or "")
        if not rep_id or rep_id not in unlocked_ids:
            continue

        rep_text = str(cluster.representative_keypoint.text or "").strip()
        rep_to_label[rep_id] = rep_text or rep_id

        for raw_text in [rep_text] + [str(member.keypoint.text or "").strip() for member in cluster.members]:
            key = _normalize_scope_key(raw_text)
            if not key or key in concept_to_rep:
                continue
            concept_to_rep[key] = rep_id

    return concept_to_rep, rep_to_label


def _resolve_scope_rep_ids(
    values: list[str] | None,
    *,
    concept_to_rep: dict[str, str],
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for text in _normalize_focus_concepts(values):
        key = _normalize_scope_key(text)
        if not key:
            continue
        rep_id = concept_to_rep.get(key)
        if not rep_id or rep_id in seen:
            continue
        seen.add(rep_id)
        out.append(rep_id)
    return out


def _rep_ids_to_scope_labels(
    rep_ids: list[str],
    *,
    rep_to_label: dict[str, str],
) -> list[str]:
    labels: list[str] = []
    for rep_id in rep_ids:
        label = str(rep_to_label.get(rep_id) or rep_id).strip()
        if label:
            labels.append(label)
    return labels


def _normalize_compare_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    normalized = re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)
    return normalized


def _question_matches_scope_concepts(question: dict[str, Any], scope_concepts: list[str]) -> bool:
    cleaned_scope = [str(item).strip() for item in (scope_concepts or []) if str(item).strip()]
    if not cleaned_scope:
        return True

    scope_keys = [_normalize_compare_text(item) for item in cleaned_scope]
    scope_keys = [key for key in scope_keys if key]
    if not scope_keys:
        return True

    concept_keys = [
        _normalize_compare_text(item)
        for item in (question.get("concepts") or [])
        if str(item).strip()
    ]
    concept_keys = [key for key in concept_keys if key]
    for concept_key in concept_keys:
        for scope_key in scope_keys:
            if concept_key == scope_key or concept_key in scope_key or scope_key in concept_key:
                return True

    combined = " ".join([str(question.get("question") or ""), str(question.get("explanation") or "")])
    combined_key = _normalize_compare_text(combined)
    if not combined_key:
        return False
    for scope_key in scope_keys:
        if scope_key and scope_key in combined_key:
            return True
    return False


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
    if not ratios:
        return {}
    if total <= 0:
        return {key: 0 for key in ratios}

    normalized: dict[str, float] = {}
    weight_sum = 0.0
    for key, raw_weight in ratios.items():
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            weight = 0.0
        if weight < 0:
            weight = 0.0
        normalized[key] = weight
        weight_sum += weight

    keys = list(normalized.keys())
    if weight_sum <= 0:
        base = total // max(1, len(keys))
        remainder = total - base * len(keys)
        counts = {key: base for key in keys}
        for key in keys[:remainder]:
            counts[key] += 1
        return counts

    raw_counts = {key: (total * normalized[key] / weight_sum) for key in keys}
    counts = {key: int(raw_counts[key]) for key in keys}
    remainder = total - sum(counts.values())
    if remainder > 0:
        order = sorted(
            keys,
            key=lambda key: (raw_counts[key] - counts[key], normalized[key]),
            reverse=True,
        )
        for idx in range(remainder):
            key = order[idx % len(order)]
            counts[key] += 1
    elif remainder < 0:
        order = sorted(
            keys,
            key=lambda key: (raw_counts[key] - counts[key], normalized[key]),
        )
        for key in order:
            if remainder >= 0:
                break
            if counts[key] <= 0:
                continue
            counts[key] -= 1
            remainder += 1

    return counts


def _normalize_question_type(value: str | None) -> str:
    normalized = str(value or QUIZ_TYPE_SINGLE).strip().lower()
    if normalized not in DEFAULT_SECTION_RATIOS:
        return QUIZ_TYPE_SINGLE
    return normalized


def _normalize_section_id(section_type: str, index: int) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", str(section_type or "").strip().lower()).strip("_")
    if not base:
        base = "section"
    return f"{base}_{index + 1}"


def _normalize_score_per_question(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 1.0
    if score <= 0:
        return 1.0
    return round(score, 3)


def _build_default_paper_blueprint(total_count: int, *, difficulty: str | None) -> PaperBlueprint:
    counts = _split_counts(total_count, DEFAULT_SECTION_RATIOS)
    sections: list[PaperSectionBlueprint] = []
    for idx, section_type in enumerate(DEFAULT_SECTION_ORDER):
        section_count = int(counts.get(section_type, 0) or 0)
        if section_count <= 0:
            continue
        sections.append(
            PaperSectionBlueprint(
                section_id=_normalize_section_id(section_type, idx),
                type=section_type,  # type: ignore[arg-type]
                count=section_count,
                score_per_question=1.0,
                difficulty=difficulty,  # type: ignore[arg-type]
            )
        )
    if not sections:
        sections.append(
            PaperSectionBlueprint(
                section_id=_normalize_section_id(QUIZ_TYPE_SINGLE, 0),
                type=QUIZ_TYPE_SINGLE,  # type: ignore[arg-type]
                count=max(1, total_count),
                score_per_question=1.0,
                difficulty=difficulty,  # type: ignore[arg-type]
            )
        )
    return PaperBlueprint(
        title=DEFAULT_PAPER_TITLE,
        duration_minutes=DEFAULT_PAPER_DURATION_MINUTES,
        sections=sections,
    )


def _collect_question_stems(items: list[dict]) -> list[str]:
    out: list[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("question") or "").strip()
        if text:
            out.append(text)
    return out


def _render_fill_blank_placeholders(count: int) -> str:
    safe_count = max(1, int(count or 1))
    return " / ".join([FILL_BLANK_CANONICAL_PLACEHOLDER] * safe_count)


def _align_fill_blank_question(question: Any, blank_count: int) -> str:
    """
    Ensure fill-blank question stem placeholder count is consistent with blank_count.
    """
    expected = max(1, int(blank_count or 1))
    text = str(question or "").strip()
    if not text:
        return f"请完成填空：{_render_fill_blank_placeholders(expected)}"

    current_count = len(FILL_BLANK_PLACEHOLDER_RE.findall(text))
    if current_count == expected:
        return text

    normalized_text = FILL_BLANK_PLACEHOLDER_RE.sub(FILL_BLANK_CANONICAL_PLACEHOLDER, text)
    normalized_count = len(re.findall(r"_{3,}", normalized_text))
    if normalized_count == expected:
        return normalized_text

    text_without_placeholders = re.sub(FILL_BLANK_PLACEHOLDER_RE, " ", text)
    text_without_placeholders = re.sub(r"\s+", " ", text_without_placeholders).strip()
    placeholders = _render_fill_blank_placeholders(expected)

    if not text_without_placeholders:
        return f"请完成填空：{placeholders}"
    if text_without_placeholders.endswith(("：", ":")):
        return f"{text_without_placeholders}{placeholders}"
    return f"{text_without_placeholders}（{placeholders}）"


def _normalize_quiz_question_shape(q: dict, idx: int, *, section_id: str, section_type: str, score: float) -> dict:
    normalized = dict(q or {})
    normalized.setdefault("question_id", f"{section_id}-{idx + 1}-{uuid4().hex[:8]}")
    normalized["type"] = _normalize_question_type(str(normalized.get("type") or section_type))
    normalized["section_id"] = str(normalized.get("section_id") or section_id)
    normalized["score"] = _normalize_score_per_question(normalized.get("score") or score)

    question_type = normalized["type"]
    normalized.setdefault("concepts", [])
    normalized.setdefault("explanation", "")
    normalized.setdefault("question", "")

    if question_type == QUIZ_TYPE_SINGLE:
        answer_index = normalized.get("answer_index")
        if not isinstance(answer_index, int):
            answer = normalized.get("answer")
            answer_index = answer if isinstance(answer, int) else 0
        normalized["answer_index"] = max(0, min(3, answer_index))
        normalized["answer"] = normalized["answer_index"]
        normalized.setdefault("options", ["A", "B", "C", "D"])
        normalized.setdefault("answer_indexes", [])
        normalized.setdefault("answer_bool", None)
        normalized.setdefault("answer_blanks", [])
        normalized.setdefault("blank_count", 1)
        return normalized

    if question_type == QUIZ_TYPE_MULTIPLE:
        indexes = normalized.get("answer_indexes")
        if not isinstance(indexes, list):
            answer = normalized.get("answer")
            indexes = answer if isinstance(answer, list) else []
        cleaned: list[int] = []
        for raw in indexes:
            if isinstance(raw, int) and 0 <= raw <= 3 and raw not in cleaned:
                cleaned.append(raw)
        if not cleaned:
            fallback = normalized.get("answer_index")
            if isinstance(fallback, int) and 0 <= fallback <= 3:
                cleaned = [fallback]
        if not cleaned:
            cleaned = [0]
        normalized["answer_indexes"] = sorted(cleaned)
        normalized["answer"] = normalized["answer_indexes"]
        normalized["answer_index"] = normalized["answer_indexes"][0]
        normalized.setdefault("options", ["A", "B", "C", "D"])
        normalized.setdefault("answer_bool", None)
        normalized.setdefault("answer_blanks", [])
        normalized.setdefault("blank_count", 1)
        return normalized

    if question_type == QUIZ_TYPE_TRUE_FALSE:
        answer_bool = _normalize_bool_answer_value(
            normalized.get("answer_bool") if normalized.get("answer_bool") is not None else normalized.get("answer")
        )
        if answer_bool is None:
            answer_index = normalized.get("answer_index")
            if isinstance(answer_index, int):
                if answer_index == 0:
                    answer_bool = True
                elif answer_index == 1:
                    answer_bool = False
        if answer_bool is None:
            answer_bool = True
        normalized["answer_bool"] = answer_bool
        normalized["answer"] = answer_bool
        normalized["answer_index"] = 0 if answer_bool else 1
        normalized["options"] = ["正确", "错误"]
        normalized.setdefault("answer_indexes", [])
        normalized.setdefault("answer_blanks", [])
        normalized.setdefault("blank_count", 1)
        return normalized

    blanks = _normalize_blank_answers(normalized.get("answer_blanks") if normalized.get("answer_blanks") is not None else normalized.get("answer"))
    if not blanks:
        fallback = str(normalized.get("answer") or "").strip()
        blanks = [fallback] if fallback else ["示例答案"]
    normalized["answer_blanks"] = blanks
    normalized["answer"] = blanks
    normalized["answer_index"] = None
    normalized["answer_indexes"] = []
    normalized["answer_bool"] = None
    normalized["blank_count"] = max(int(normalized.get("blank_count") or 0), len(blanks), 1)
    normalized["question"] = _align_fill_blank_question(
        normalized.get("question"),
        normalized["blank_count"],
    )
    normalized["options"] = []
    return normalized


def _normalize_bool_answer_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value == 1:
            return True
        if value == 0:
            return False
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in ANSWER_TRUE_SYNONYMS:
        return True
    if text in ANSWER_FALSE_SYNONYMS:
        return False
    return None


def _normalize_blank_answers(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, list):
        candidates = value
    else:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _normalize_answer_indexes(value: Any) -> list[int]:
    if isinstance(value, int):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []
    out: list[int] = []
    seen: set[int] = set()
    for raw in values:
        if not isinstance(raw, int):
            continue
        if raw < 0 or raw > 3 or raw in seen:
            continue
        seen.add(raw)
        out.append(raw)
    return sorted(out)


def _normalize_text_answer(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def _answer_is_correct(question: dict, provided: Any) -> bool:
    question_type = _normalize_question_type(str(question.get("type") or QUIZ_TYPE_SINGLE))
    if question_type == QUIZ_TYPE_SINGLE:
        expected = question.get("answer_index")
        return isinstance(expected, int) and provided == expected

    if question_type == QUIZ_TYPE_MULTIPLE:
        expected = _normalize_answer_indexes(question.get("answer_indexes") if question.get("answer_indexes") is not None else question.get("answer"))
        got = _normalize_answer_indexes(provided)
        return bool(expected) and expected == got

    if question_type == QUIZ_TYPE_TRUE_FALSE:
        expected = _normalize_bool_answer_value(
            question.get("answer_bool") if question.get("answer_bool") is not None else question.get("answer")
        )
        got = _normalize_bool_answer_value(provided)
        return expected is not None and got is not None and expected == got

    expected_blanks = _normalize_blank_answers(
        question.get("answer_blanks") if question.get("answer_blanks") is not None else question.get("answer")
    )
    if not expected_blanks:
        return False
    if isinstance(provided, str):
        provided_blanks = [provided]
    elif isinstance(provided, list):
        provided_blanks = [str(item or "") for item in provided]
    else:
        return False
    if len(provided_blanks) != len(expected_blanks):
        return False
    return all(
        _normalize_text_answer(got) == _normalize_text_answer(exp)
        for got, exp in zip(provided_blanks, expected_blanks)
    )


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
    allowed_keypoint_ids: set[str] | None = None,
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
        if allowed_keypoint_ids is not None and kp_ids:
            kp_ids = [kp_id for kp_id in kp_ids if kp_id in allowed_keypoint_ids]
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

    scope_field_provided = payload.scope_concepts is not None
    normalized_scope_input = _normalize_focus_concepts(payload.scope_concepts)
    effective_scope_concepts: list[str] = []
    allowed_scope_keypoint_ids: set[str] | None = None

    if scope_field_provided and not normalized_scope_input:
        raise HTTPException(
            status_code=409,
            detail="scope_concepts is empty after normalization",
        )

    if scope_field_provided:
        if effective_kb_id:
            concept_to_rep, rep_to_label = _build_unlocked_scope_index(
                db,
                resolved_user_id,
                effective_kb_id,
            )
            scope_rep_ids = _resolve_scope_rep_ids(
                normalized_scope_input,
                concept_to_rep=concept_to_rep,
            )
            if not scope_rep_ids:
                raise HTTPException(
                    status_code=409,
                    detail="scope_concepts has no unlocked concepts in current KB",
                )

            effective_rep_ids = list(scope_rep_ids)
            if payload.focus_concepts:
                focus_rep_ids = set(
                    _resolve_scope_rep_ids(
                        payload.focus_concepts,
                        concept_to_rep=concept_to_rep,
                    )
                )
                effective_rep_ids = [rep_id for rep_id in scope_rep_ids if rep_id in focus_rep_ids]
                if not effective_rep_ids:
                    raise HTTPException(
                        status_code=409,
                        detail="focus_concepts has no overlap with scope_concepts",
                    )

            effective_scope_concepts = _rep_ids_to_scope_labels(
                effective_rep_ids,
                rep_to_label=rep_to_label,
            )
            if not effective_scope_concepts:
                raise HTTPException(
                    status_code=409,
                    detail="No effective concepts available after scope/focus validation",
                )
            allowed_scope_keypoint_ids = set(effective_rep_ids)
        else:
            # Legacy fallback when KB context is unavailable: keep textual intersection only.
            effective_scope_concepts = list(normalized_scope_input)
            if payload.focus_concepts:
                focus_keys = {
                    _normalize_scope_key(item)
                    for item in _normalize_focus_concepts(payload.focus_concepts)
                }
                effective_scope_concepts = [
                    concept
                    for concept in effective_scope_concepts
                    if _normalize_scope_key(concept) in focus_keys
                ]
                if not effective_scope_concepts:
                    raise HTTPException(
                        status_code=409,
                        detail="focus_concepts has no overlap with scope_concepts",
                    )
    else:
        effective_scope_concepts = _normalize_focus_concepts(payload.focus_concepts)
        if effective_kb_id and payload.focus_concepts:
            _ensure_focus_concepts_unlocked(
                db,
                resolved_user_id,
                effective_kb_id,
                payload.focus_concepts,
            )

    try:
        adaptive_plan = None
        global_difficulty = (payload.difficulty or "").strip().lower() or "medium"
        if payload.auto_adapt and payload.difficulty is None:
            profile = get_or_create_profile(db, resolved_user_id)
            adaptive_plan = generate_difficulty_plan(profile)
            global_difficulty = "adaptive"
            difficulty_label = "adaptive"
        else:
            difficulty_label = global_difficulty

        if payload.paper_blueprint:
            blueprint = payload.paper_blueprint
        else:
            default_difficulty = global_difficulty if global_difficulty in {"easy", "medium", "hard", "adaptive"} else "medium"
            blueprint = _build_default_paper_blueprint(payload.count, difficulty=default_difficulty)

        sections = list(blueprint.sections or [])
        if not sections:
            default_difficulty = global_difficulty if global_difficulty in {"easy", "medium", "hard", "adaptive"} else "medium"
            blueprint = _build_default_paper_blueprint(payload.count, difficulty=default_difficulty)
            sections = list(blueprint.sections)

        questions: list[dict] = []
        section_meta: list[PaperSectionMeta] = []
        all_stems: list[str] = []

        for section_index, section in enumerate(sections):
            section_type = _normalize_question_type(str(section.type))
            section_id = str(section.section_id or _normalize_section_id(section_type, section_index)).strip()
            if not section_id:
                section_id = _normalize_section_id(section_type, section_index)
            section_count = max(1, int(section.count or 1))
            score_per_question = _normalize_score_per_question(section.score_per_question)

            section_difficulty = str(section.difficulty or global_difficulty or "medium").strip().lower()
            if section_difficulty not in {"easy", "medium", "hard", "adaptive"}:
                section_difficulty = "medium"

            section_questions: list[dict] = []
            if section_difficulty == "adaptive":
                if adaptive_plan is None:
                    profile = get_or_create_profile(db, resolved_user_id)
                    adaptive_plan = generate_difficulty_plan(profile)
                per_diff = _split_counts(
                    section_count,
                    {"easy": adaptive_plan.easy, "medium": adaptive_plan.medium, "hard": adaptive_plan.hard},
                )
                for diff, diff_count in per_diff.items():
                    if diff_count <= 0:
                        continue
                    avoid_stems = [*all_stems, *_collect_question_stems(section_questions)]
                    batch = generate_quiz(
                        resolved_user_id,
                        payload.doc_id,
                        diff_count,
                        diff,
                        kb_id=payload.kb_id,
                        focus_concepts=effective_scope_concepts,
                        style_prompt=payload.style_prompt,
                        reference_questions=payload.reference_questions,
                        avoid_question_texts=avoid_stems,
                        question_type=section_type,
                        section_id=section_id,
                        score_per_question=score_per_question,
                    )
                    section_questions.extend(batch[:diff_count])
            else:
                batch = generate_quiz(
                    resolved_user_id,
                    payload.doc_id,
                    section_count,
                    section_difficulty,
                    kb_id=payload.kb_id,
                    focus_concepts=effective_scope_concepts,
                    style_prompt=payload.style_prompt,
                    reference_questions=payload.reference_questions,
                    avoid_question_texts=all_stems,
                    question_type=section_type,
                    section_id=section_id,
                    score_per_question=score_per_question,
                )
                section_questions.extend(batch[:section_count])

            if len(section_questions) < section_count:
                missing = section_count - len(section_questions)
                retry_difficulty = "medium" if section_difficulty == "adaptive" else section_difficulty
                retry_batch = generate_quiz(
                    resolved_user_id,
                    payload.doc_id,
                    missing,
                    retry_difficulty,
                    kb_id=payload.kb_id,
                    focus_concepts=effective_scope_concepts,
                    style_prompt=payload.style_prompt,
                    reference_questions=payload.reference_questions,
                    avoid_question_texts=[*all_stems, *_collect_question_stems(section_questions)],
                    question_type=section_type,
                    section_id=section_id,
                    score_per_question=score_per_question,
                )
                section_questions.extend(retry_batch[:missing])

            if section_questions:
                section_questions = filter_quiz_questions_quality(
                    section_questions,
                    target_count=section_count,
                    question_type=section_type,
                    focus_concepts=effective_scope_concepts,
                )

            refill_attempts = 0
            max_refill_attempts = 2
            while len(section_questions) < section_count and refill_attempts < max_refill_attempts:
                refill_attempts += 1
                missing = section_count - len(section_questions)
                retry_difficulty = "medium" if section_difficulty == "adaptive" else section_difficulty
                refill_batch = generate_quiz(
                    resolved_user_id,
                    payload.doc_id,
                    missing,
                    retry_difficulty,
                    kb_id=payload.kb_id,
                    focus_concepts=effective_scope_concepts,
                    style_prompt=payload.style_prompt,
                    reference_questions=payload.reference_questions,
                    avoid_question_texts=[*all_stems, *_collect_question_stems(section_questions)],
                    question_type=section_type,
                    section_id=section_id,
                    score_per_question=score_per_question,
                )
                if not refill_batch:
                    break
                expanded = [*section_questions, *refill_batch]
                refiltered = filter_quiz_questions_quality(
                    expanded,
                    target_count=section_count,
                    question_type=section_type,
                    focus_concepts=effective_scope_concepts,
                )
                if len(refiltered) <= len(section_questions):
                    break
                section_questions = refiltered

            normalized_section_questions: list[dict] = []
            for idx, q in enumerate(section_questions[:section_count]):
                if not isinstance(q, dict):
                    continue
                normalized_section_questions.append(
                    _normalize_quiz_question_shape(
                        q,
                        idx,
                        section_id=section_id,
                        section_type=section_type,
                        score=score_per_question,
                    )
                )
            if effective_scope_concepts:
                normalized_section_questions = [
                    item
                    for item in normalized_section_questions
                    if _question_matches_scope_concepts(item, effective_scope_concepts)
                ]

            questions.extend(normalized_section_questions)
            all_stems.extend(_collect_question_stems(normalized_section_questions))
            section_meta.append(
                PaperSectionMeta(
                    section_id=section_id,
                    type=section_type,  # type: ignore[arg-type]
                    requested_count=section_count,
                    generated_count=len(normalized_section_questions),
                    score_per_question=score_per_question,
                    difficulty=section_difficulty,  # type: ignore[arg-type]
                )
            )

        if not payload.paper_blueprint and len(questions) > payload.count:
            questions = questions[: payload.count]

        for idx, q in enumerate(questions):
            if not isinstance(q, dict):
                continue
            if not str(q.get("question_id") or "").strip():
                section_id = str(q.get("section_id") or "section-1")
                q["question_id"] = f"{section_id}-{idx + 1}-{uuid4().hex[:8]}"

        paper_total_score = round(sum(float(item.get("score") or 0.0) for item in questions), 2)
        paper_meta = PaperMeta(
            title=blueprint.title or DEFAULT_PAPER_TITLE,
            duration_minutes=int(blueprint.duration_minutes or DEFAULT_PAPER_DURATION_MINUTES),
            total_score=paper_total_score,
            sections=section_meta,
        )

        _prebind_quiz_question_keypoints(
            db,
            questions,
            resolved_user_id,
            payload.doc_id,
            effective_kb_id,
            allowed_keypoint_ids=allowed_scope_keypoint_ids,
        )
        if allowed_scope_keypoint_ids is not None:
            scoped_questions: list[dict] = []
            for q in questions:
                if not isinstance(q, dict):
                    continue
                bound_ids = _clean_bound_keypoint_ids(q.get("keypoint_ids"))
                if not bound_ids:
                    scoped_questions.append(q)
                    continue
                if any(bound_id in allowed_scope_keypoint_ids for bound_id in bound_ids):
                    scoped_questions.append(q)
            questions = scoped_questions

            generated_by_section: dict[str, int] = defaultdict(int)
            for q in questions:
                section_id = str(q.get("section_id") or "")
                if section_id:
                    generated_by_section[section_id] += 1
            for meta in section_meta:
                meta.generated_count = int(generated_by_section.get(meta.section_id, 0))

            paper_meta.total_score = round(
                sum(float(item.get("score") or 0.0) for item in questions),
                2,
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
        question_type="mixed" if any(str(item.get("type") or "") != QUIZ_TYPE_SINGLE for item in questions) else "mcq",
        questions_json=json.dumps(questions, ensure_ascii=False),
        paper_meta_json=json.dumps(paper_meta.model_dump(), ensure_ascii=False),
    )
    db.add(quiz)
    db.commit()

    return QuizGenerateResponse(quiz_id=quiz_id, questions=parsed, paper_meta=paper_meta)


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

    questions_raw = json.loads(quiz.questions_json)
    if not isinstance(questions_raw, list):
        raise HTTPException(status_code=400, detail="Invalid quiz payload")
    questions: list[dict] = []
    for idx, raw in enumerate(questions_raw):
        if not isinstance(raw, dict):
            continue
        section_id = str(raw.get("section_id") or "section-1")
        section_type = _normalize_question_type(str(raw.get("type") or QUIZ_TYPE_SINGLE))
        score_value = _normalize_score_per_question(raw.get("score") or 1.0)
        questions.append(
            _normalize_quiz_question_shape(
                raw,
                idx,
                section_id=section_id,
                section_type=section_type,
                score=score_value,
            )
        )

    total = len(questions)
    results = []
    explanations = []
    correct = 0
    total_score = 0.0
    earned_score = 0.0
    section_score_map: dict[str, dict[str, float]] = {}
    question_results: list[QuizQuestionResult] = []
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

    answers_by_question_id: dict[str, Any] = {}
    legacy_answers: list[Any] = []
    for item in payload.answers or []:
        if isinstance(item, dict) and "question_id" in item:
            question_id = str(item.get("question_id") or "").strip()
            if question_id:
                answers_by_question_id[question_id] = item.get("answer")
                continue
        legacy_answers.append(item)

    for idx, q in enumerate(questions):
        question_id = str(q.get("question_id") or "")
        if question_id and question_id in answers_by_question_id:
            provided = answers_by_question_id.get(question_id)
        else:
            provided = legacy_answers[idx] if idx < len(legacy_answers) else None

        is_correct = _answer_is_correct(q, provided)
        results.append(is_correct)
        explanations.append(q.get("explanation", ""))
        if is_correct:
            correct += 1

        question_score = _normalize_score_per_question(q.get("score") or 1.0)
        question_earned = question_score if is_correct else 0.0
        total_score += question_score
        earned_score += question_earned

        section_id = str(q.get("section_id") or "section-1")
        section_stats = section_score_map.setdefault(section_id, {"earned": 0.0, "total": 0.0})
        section_stats["earned"] += question_earned
        section_stats["total"] += question_score

        question_results.append(
            QuizQuestionResult(
                question_id=question_id or f"q-{idx + 1}",
                correct=is_correct,
                earned=round(question_earned, 3),
                total=round(question_score, 3),
                explanation=str(q.get("explanation") or ""),
            )
        )

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

        delta, guard_reason = record_quiz_result_guarded(
            db,
            target_kp_id,
            is_correct,
            unlocked_ids=unlocked_ids,
        )
        if not delta:
            if guard_reason == "locked":
                skipped_locked += 1
            else:
                skipped_missing_binding += 1
            continue
        if guard_reason is not None:
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
    section_scores = [
        QuizSectionScore(
            section_id=section_id,
            earned=round(stats["earned"], 3),
            total=round(stats["total"], 3),
        )
        for section_id, stats in sorted(section_score_map.items())
    ]
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
        answers_json=json.dumps(payload.answers, ensure_ascii=False),
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
        total_score=round(total_score, 3),
        earned_score=round(earned_score, 3),
        section_scores=section_scores,
        question_results=question_results,
        feedback=feedback,
        next_quiz_recommendation=next_quiz_recommendation,
        profile_delta=profile_delta,
        wrong_questions_by_concept=wrong_questions_by_concept,
        mastery_updates=mastery_updates,
        mastery_guard=MasteryGuardStats(
            updated_count=updated_count,
            skipped_locked=skipped_locked,
            skipped_missing_binding=skipped_missing_binding,
        ),
    )
