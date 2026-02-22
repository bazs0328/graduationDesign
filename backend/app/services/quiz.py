import json
import logging
import math
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.core.vectorstore import get_vectorstore
from app.utils.json_tools import safe_json_loads

logger = logging.getLogger(__name__)

# Max length for reference_questions to avoid exceeding model context
REFERENCE_QUESTIONS_MAX_CHARS = 8000
QUIZ_DUPLICATE_SIMILARITY_THRESHOLD = 0.92
QUIZ_RESAMPLE_MAX_ROUNDS = 1
MAX_AVOID_LIST_IN_PROMPT = 8

QUIZ_SYSTEM = (
    "You are an exam writer. Generate multiple-choice questions strictly from the context. "
    "Return JSON only."
)

QUIZ_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", QUIZ_SYSTEM),
        (
            "human",
            "Create {count} {difficulty} multiple-choice questions. "
            "Each question must have 4 options and one correct answer. "
            "Return JSON array with fields: question, options, answer_index, explanation, concepts.\n"
            "concepts must be a list of 1-3 key concepts tested.\n\n"
            "Context:\n{context}",
        ),
    ]
)

QUIZ_MIMIC_SYSTEM = (
    "You are an exam writer. Generate multiple-choice questions. "
    "When reference questions or style requirements are given, match their style and difficulty. "
    "Return JSON only."
)

QUIZ_MIMIC_HUMAN_TEMPLATE = (
    "Create {count} {difficulty} multiple-choice questions. "
    "Each question must have 4 options and one correct answer. "
    "Return JSON array with fields: question, options, answer_index, explanation, concepts.\n"
    "concepts must be a list of 1-3 key concepts tested.\n\n"
    "{extra_instructions}"
    "Context:\n{context}"
)


def _extract_keypoint_ids(docs) -> List[str]:
    """Extract unique keypoint_ids from vector search result metadata."""
    seen: set[str] = set()
    ids: List[str] = []
    for doc in docs:
        meta = getattr(doc, "metadata", {}) or {}
        kp_id = meta.get("keypoint_id")
        if kp_id and kp_id not in seen:
            seen.add(kp_id)
            ids.append(kp_id)
    return ids


def _build_context(
    user_id: str,
    doc_id: Optional[str],
    kb_id: Optional[str],
    reference_questions: Optional[str],
    focus_concepts: Optional[List[str]] = None,
) -> tuple[str, List[str]]:
    """Build context and collect related keypoint_ids from vector search metadata.

    Returns (context_text, keypoint_ids).
    """
    query = "key concepts and definitions"
    if focus_concepts:
        cleaned = [str(item).strip() for item in focus_concepts if str(item).strip()]
        if cleaned:
            query = ", ".join(cleaned)
    if doc_id:
        vectorstore = get_vectorstore(user_id)
        docs = vectorstore.similarity_search(
            query, k=6, filter={"doc_id": doc_id}
        )
        if not docs:
            raise ValueError("No relevant context found for quiz generation")
        return "\n\n".join(doc.page_content for doc in docs), _extract_keypoint_ids(docs)
    if kb_id:
        vectorstore = get_vectorstore(user_id)
        docs = vectorstore.similarity_search(
            query, k=6, filter={"kb_id": kb_id}
        )
        if not docs:
            raise ValueError("No relevant context found for quiz generation")
        return "\n\n".join(doc.page_content for doc in docs), _extract_keypoint_ids(docs)
    if reference_questions:
        text = reference_questions.strip()
        if len(text) > REFERENCE_QUESTIONS_MAX_CHARS:
            text = text[:REFERENCE_QUESTIONS_MAX_CHARS] + "\n[... truncated]"
        return text, []
    return "General knowledge.", []


def _build_avoid_questions_instructions(avoid_question_texts: Optional[List[str]]) -> str:
    if not avoid_question_texts:
        return ""
    cleaned = []
    seen: set[str] = set()
    for text in avoid_question_texts:
        candidate = str(text or "").strip()
        if not candidate:
            continue
        normalized = _normalize_text_for_compare(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(candidate)
        if len(cleaned) >= MAX_AVOID_LIST_IN_PROMPT:
            break
    if not cleaned:
        return ""
    lines = "\n".join(f"- {item[:180]}" for item in cleaned)
    return (
        "Avoid generating questions that duplicate or closely paraphrase the following stems:\n"
        f"{lines}\n\n"
    )


def _build_extra_instructions(
    style_prompt: Optional[str],
    reference_questions: Optional[str],
    context_is_from_reference: bool,
    focus_concepts: Optional[List[str]] = None,
    avoid_question_texts: Optional[List[str]] = None,
) -> str:
    """Build extra prompt section for mimic (style / reference questions)."""
    parts = []
    if focus_concepts:
        cleaned = [str(item).strip() for item in focus_concepts if str(item).strip()]
        if cleaned:
            parts.append(
                "Focus on the following concepts when generating questions:\n"
                f"{', '.join(cleaned)}\n\n"
            )
    avoid_part = _build_avoid_questions_instructions(avoid_question_texts)
    if avoid_part:
        parts.append(avoid_part)
    if reference_questions and not context_is_from_reference:
        text = reference_questions.strip()
        if len(text) > REFERENCE_QUESTIONS_MAX_CHARS:
            text = text[:REFERENCE_QUESTIONS_MAX_CHARS] + "\n[... truncated]"
        parts.append(
            "Reference the following questions for style and difficulty, then generate new questions in the same style:\n"
            f"{text}\n\n"
        )
    if style_prompt and style_prompt.strip():
        parts.append(f"Style/template requirements:\n{style_prompt.strip()}\n\n")
    return "".join(parts) if parts else ""


def _normalize_text_for_compare(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    normalized = re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)
    return normalized


def _normalize_concepts_list(raw_concepts: Any) -> List[str]:
    if not isinstance(raw_concepts, list):
        return []
    cleaned: List[str] = []
    seen: set[str] = set()
    for concept in raw_concepts:
        text = str(concept or "").strip()
        if not text:
            continue
        key = _normalize_text_for_compare(text)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned[:3]


def _normalize_and_validate_question(q: Any) -> tuple[dict | None, str | None]:
    if not isinstance(q, dict):
        return None, "invalid_type"

    required_fields = ["question", "options", "answer_index", "explanation"]
    missing_fields = [field for field in required_fields if field not in q]
    if missing_fields:
        return None, "missing_fields"

    question = str(q.get("question") or "").strip()
    explanation = str(q.get("explanation") or "").strip()
    if not question:
        return None, "empty_question"
    if not explanation:
        return None, "empty_explanation"

    options = q.get("options")
    if not isinstance(options, list) or len(options) != 4:
        return None, "invalid_options"
    normalized_options: list[str] = []
    option_keys: set[str] = set()
    for option in options:
        opt_text = str(option or "").strip()
        if not opt_text:
            return None, "empty_option"
        opt_key = _normalize_text_for_compare(opt_text)
        if opt_key in option_keys:
            return None, "duplicate_options"
        option_keys.add(opt_key)
        normalized_options.append(opt_text)

    answer_index = q.get("answer_index")
    if not isinstance(answer_index, int) or answer_index < 0 or answer_index >= 4:
        return None, "invalid_answer_index"

    normalized = dict(q)
    normalized["question"] = question
    normalized["options"] = normalized_options
    normalized["answer_index"] = answer_index
    normalized["explanation"] = explanation
    normalized["concepts"] = _normalize_concepts_list(q.get("concepts"))
    return normalized, None


def _max_concept_repeat(target_count: int, focus_concepts: Optional[List[str]] = None) -> int:
    if target_count <= 0:
        return 1
    ratio = 0.8 if focus_concepts else 0.6
    return max(2, int(math.ceil(target_count * ratio)))


def _is_near_duplicate_question(stem: str, seen_stems: list[str]) -> bool:
    if not stem or not seen_stems:
        return False
    for seen in seen_stems:
        if not seen:
            continue
        if stem == seen:
            return True
        similarity = SequenceMatcher(None, stem, seen).ratio()
        if similarity >= QUIZ_DUPLICATE_SIMILARITY_THRESHOLD:
            return True
    return False


def _would_exceed_concept_repeat_limit(
    concepts: list[str],
    concept_counts: Counter,
    limit: int,
) -> bool:
    if not concepts:
        return False
    normalized_keys = [_normalize_text_for_compare(concept) for concept in concepts if str(concept).strip()]
    normalized_keys = [key for key in normalized_keys if key]
    if not normalized_keys:
        return False
    return all(concept_counts.get(key, 0) >= limit for key in normalized_keys)


def _apply_quality_guardrails(
    raw_questions: list[Any],
    *,
    target_count: int,
    focus_concepts: Optional[List[str]] = None,
    keypoint_ids: Optional[List[str]] = None,
    seed_questions: Optional[List[dict]] = None,
    external_avoid_question_texts: Optional[List[str]] = None,
) -> tuple[list[dict], dict]:
    kept: list[dict] = []
    report = {
        "raw_count": len(raw_questions or []),
        "kept_count": 0,
        "dropped_invalid": 0,
        "dropped_duplicate_exact": 0,
        "dropped_duplicate_near": 0,
        "dropped_concept_overload": 0,
        "invalid_reasons": {},
    }

    concept_limit = _max_concept_repeat(target_count, focus_concepts)
    concept_counts: Counter = Counter()
    seen_stems: list[str] = []
    seen_exact: set[str] = set()

    for seed in seed_questions or []:
        seed_stem = _normalize_text_for_compare(seed.get("question", ""))
        if seed_stem:
            seen_exact.add(seed_stem)
            seen_stems.append(seed_stem)
        for concept in seed.get("concepts") or []:
            concept_key = _normalize_text_for_compare(concept)
            if concept_key:
                concept_counts[concept_key] += 1

    for text in external_avoid_question_texts or []:
        stem = _normalize_text_for_compare(text)
        if stem and stem not in seen_exact:
            seen_exact.add(stem)
            seen_stems.append(stem)

    for raw in raw_questions or []:
        normalized, invalid_reason = _normalize_and_validate_question(raw)
        if not normalized:
            report["dropped_invalid"] += 1
            report["invalid_reasons"][invalid_reason] = report["invalid_reasons"].get(invalid_reason, 0) + 1
            continue

        stem = _normalize_text_for_compare(normalized.get("question", ""))
        if not stem:
            report["dropped_invalid"] += 1
            report["invalid_reasons"]["empty_question"] = report["invalid_reasons"].get("empty_question", 0) + 1
            continue

        if stem in seen_exact:
            report["dropped_duplicate_exact"] += 1
            continue
        if _is_near_duplicate_question(stem, seen_stems):
            report["dropped_duplicate_near"] += 1
            continue

        concepts = normalized.get("concepts") or []
        if _would_exceed_concept_repeat_limit(concepts, concept_counts, concept_limit):
            report["dropped_concept_overload"] += 1
            continue

        if keypoint_ids and "keypoint_ids" not in normalized:
            normalized["keypoint_ids"] = keypoint_ids

        kept.append(normalized)
        seen_exact.add(stem)
        seen_stems.append(stem)
        for concept in concepts:
            concept_key = _normalize_text_for_compare(concept)
            if concept_key:
                concept_counts[concept_key] += 1

        if len(kept) >= max(target_count, 0):
            break

    report["kept_count"] = len(kept)
    report["concept_repeat_limit"] = concept_limit
    return kept, report


def _merge_quality_reports(base: dict, extra: dict) -> dict:
    merged = {
        "raw_count": int(base.get("raw_count", 0)) + int(extra.get("raw_count", 0)),
        "kept_count": int(base.get("kept_count", 0)) + int(extra.get("kept_count", 0)),
        "dropped_invalid": int(base.get("dropped_invalid", 0)) + int(extra.get("dropped_invalid", 0)),
        "dropped_duplicate_exact": int(base.get("dropped_duplicate_exact", 0)) + int(extra.get("dropped_duplicate_exact", 0)),
        "dropped_duplicate_near": int(base.get("dropped_duplicate_near", 0)) + int(extra.get("dropped_duplicate_near", 0)),
        "dropped_concept_overload": int(base.get("dropped_concept_overload", 0)) + int(extra.get("dropped_concept_overload", 0)),
        "invalid_reasons": {},
    }
    invalid_reasons = dict(base.get("invalid_reasons") or {})
    for key, value in (extra.get("invalid_reasons") or {}).items():
        invalid_reasons[key] = int(invalid_reasons.get(key, 0)) + int(value)
    merged["invalid_reasons"] = invalid_reasons
    if "concept_repeat_limit" in extra:
        merged["concept_repeat_limit"] = extra["concept_repeat_limit"]
    elif "concept_repeat_limit" in base:
        merged["concept_repeat_limit"] = base["concept_repeat_limit"]
    return merged


def _log_quality_report(report: dict, *, requested_count: int, stage: str, resampled: bool = False) -> None:
    logger.info(
        "Quiz quality guardrail stage=%s requested=%s raw=%s kept=%s drop_invalid=%s drop_dup_exact=%s drop_dup_near=%s drop_concept=%s resampled=%s invalid_reasons=%s",
        stage,
        requested_count,
        report.get("raw_count", 0),
        report.get("kept_count", 0),
        report.get("dropped_invalid", 0),
        report.get("dropped_duplicate_exact", 0),
        report.get("dropped_duplicate_near", 0),
        report.get("dropped_concept_overload", 0),
        resampled,
        report.get("invalid_reasons") or {},
    )


def _coerce_llm_questions(data: Any) -> list[Any]:
    if isinstance(data, dict):
        data = data.get("questions", [])
    if not isinstance(data, list):
        logger.error("Expected list of questions, got %s: %s", type(data), data)
        raise ValueError(f"Expected list of questions, got {type(data).__name__}")
    if len(data) == 0:
        logger.warning("LLM returned empty question list")
        raise ValueError("No questions generated. Please check context or try again.")
    return data


def _invoke_quiz_llm_once(
    llm: Any,
    *,
    count: int,
    difficulty: str,
    context: str,
    base_extra_instructions: str,
) -> list[Any]:
    try:
        if base_extra_instructions:
            human_msg = QUIZ_MIMIC_HUMAN_TEMPLATE.format(
                count=count,
                difficulty=difficulty,
                extra_instructions=base_extra_instructions,
                context=context,
            )
            msg_list = [
                SystemMessage(content=QUIZ_MIMIC_SYSTEM),
                HumanMessage(content=human_msg),
            ]
            result = llm.invoke(msg_list)
        else:
            messages = QUIZ_PROMPT.format_messages(
                count=count, difficulty=difficulty, context=context
            )
            result = llm.invoke(messages)
    except Exception as e:
        logger.error(f"LLM invocation failed: {e}")
        raise ValueError(f"Failed to generate quiz questions from LLM: {str(e)}")

    if not hasattr(result, "content") or not result.content:
        logger.error("LLM returned empty or invalid response")
        raise ValueError("LLM returned empty or invalid response")

    try:
        parsed = safe_json_loads(result.content)
    except Exception as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        logger.debug(f"LLM response content: {str(result.content)[:500]}")
        raise ValueError(f"Failed to parse quiz questions from LLM response: {str(e)}")

    return _coerce_llm_questions(parsed)


def filter_quiz_questions_quality(
    questions: list[Any],
    *,
    target_count: int,
    focus_concepts: Optional[List[str]] = None,
) -> list[dict]:
    kept, report = _apply_quality_guardrails(
        questions,
        target_count=target_count,
        focus_concepts=focus_concepts,
    )
    _log_quality_report(report, requested_count=target_count, stage="router-finalize")
    return kept[:target_count]


def generate_quiz(
    user_id: str,
    doc_id: Optional[str],
    count: int,
    difficulty: str,
    kb_id: Optional[str] = None,
    focus_concepts: Optional[List[str]] = None,
    style_prompt: Optional[str] = None,
    reference_questions: Optional[str] = None,
    avoid_question_texts: Optional[List[str]] = None,
) -> List[dict]:
    context, keypoint_ids = _build_context(
        user_id, doc_id, kb_id, reference_questions, focus_concepts
    )
    context_is_from_reference = not doc_id and not kb_id and bool(
        reference_questions and reference_questions.strip()
    )

    try:
        llm = get_llm(temperature=0.4)
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        raise ValueError(f"Failed to initialize LLM: {str(e)}")

    base_extra = _build_extra_instructions(
        style_prompt,
        reference_questions,
        context_is_from_reference,
        focus_concepts,
        avoid_question_texts=avoid_question_texts,
    )

    raw_primary = _invoke_quiz_llm_once(
        llm,
        count=count,
        difficulty=difficulty,
        context=context,
        base_extra_instructions=base_extra,
    )
    questions, report = _apply_quality_guardrails(
        raw_primary,
        target_count=count,
        focus_concepts=focus_concepts,
        keypoint_ids=keypoint_ids,
        external_avoid_question_texts=avoid_question_texts,
    )
    _log_quality_report(report, requested_count=count, stage="primary")

    resample_rounds = 0
    while len(questions) < count and resample_rounds < QUIZ_RESAMPLE_MAX_ROUNDS:
        resample_rounds += 1
        missing = count - len(questions)
        request_count = min(20, missing + min(2, missing))
        extra_avoid = list(avoid_question_texts or []) + [
            str(item.get("question") or "") for item in questions
        ]
        resample_extra = _build_extra_instructions(
            style_prompt,
            reference_questions,
            context_is_from_reference,
            focus_concepts,
            avoid_question_texts=extra_avoid,
        )
        try:
            raw_resample = _invoke_quiz_llm_once(
                llm,
                count=request_count,
                difficulty=difficulty,
                context=context,
                base_extra_instructions=resample_extra,
            )
        except ValueError as exc:
            logger.warning("Quiz resample round %s failed: %s", resample_rounds, exc)
            break

        resample_kept, resample_report = _apply_quality_guardrails(
            raw_resample,
            target_count=count,
            focus_concepts=focus_concepts,
            keypoint_ids=keypoint_ids,
            seed_questions=questions,
            external_avoid_question_texts=avoid_question_texts,
        )
        _log_quality_report(
            resample_report,
            requested_count=count,
            stage=f"resample-{resample_rounds}",
            resampled=True,
        )
        questions.extend(resample_kept)
        report = _merge_quality_reports(report, resample_report)
        if not resample_kept:
            break

    if len(questions) == 0:
        logger.error("No valid questions after quality guardrails")
        raise ValueError("No valid questions generated. Please check LLM output format.")

    if len(questions) < count:
        logger.info(
            "Quiz generation returned fewer questions than requested after guardrails: requested=%s actual=%s",
            count,
            len(questions),
        )

    validated_questions = questions[:count]

    try:
        json.dumps(validated_questions)  # validate serializable
    except TypeError as e:
        logger.error(f"Questions are not JSON serializable: {e}")
        raise ValueError(f"Generated questions are not JSON serializable: {str(e)}")

    return validated_questions
