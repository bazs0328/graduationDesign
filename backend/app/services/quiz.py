import json
import logging
import math
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.core.llm import get_llm
from app.core.vectorstore import get_vectorstore
from app.services.quiz_context import build_quiz_context_from_seeds
from app.services.text_noise_guard import is_low_quality
from app.utils.json_tools import safe_json_loads

logger = logging.getLogger(__name__)

# Max length for reference_questions to avoid exceeding model context
REFERENCE_QUESTIONS_MAX_CHARS = 8000
QUIZ_DUPLICATE_SIMILARITY_THRESHOLD = 0.92
QUIZ_RESAMPLE_MAX_ROUNDS = 1
MAX_AVOID_LIST_IN_PROMPT = 8
QUIZ_CONTEXT_MIN_K = 6
QUIZ_CONTEXT_MAX_K_DOC = 14
QUIZ_CONTEXT_MAX_K_KB = 24
QUIZ_CONTEXT_DOCS_PER_QUESTION_DOC = 2
QUIZ_CONTEXT_DOCS_PER_QUESTION_KB = 3
QUIZ_CONTEXT_MAX_CHARS = 16000

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


def _context_search_k(
    target_count: int,
    *,
    kb_scope: bool,
    focus_concepts: Optional[List[str]] = None,
) -> int:
    count = max(1, int(target_count or 1))
    per_question = (
        QUIZ_CONTEXT_DOCS_PER_QUESTION_KB if kb_scope else QUIZ_CONTEXT_DOCS_PER_QUESTION_DOC
    )
    k = max(QUIZ_CONTEXT_MIN_K, count * per_question)
    focus_count = len([c for c in (focus_concepts or []) if str(c).strip()])
    if focus_count > 1:
        k += min(4, focus_count - 1)
    return min(QUIZ_CONTEXT_MAX_K_KB if kb_scope else QUIZ_CONTEXT_MAX_K_DOC, k)


def _context_seed_search_k(
    target_count: int,
    *,
    kb_scope: bool,
    focus_concepts: Optional[List[str]] = None,
) -> int:
    base_k = _context_search_k(target_count, kb_scope=kb_scope, focus_concepts=focus_concepts)
    multiplier = 1.0
    try:
        multiplier = float(getattr(settings, "quiz_context_seed_k_multiplier", 2.0) or 2.0)
    except (TypeError, ValueError):
        multiplier = 2.0
    multiplier = max(1.0, multiplier)
    max_k = QUIZ_CONTEXT_MAX_K_KB if kb_scope else QUIZ_CONTEXT_MAX_K_DOC
    return min(max_k, max(base_k, int(math.ceil(base_k * multiplier))))


def _context_char_budget(target_count: int, *, kb_scope: bool) -> int:
    count = max(1, int(target_count or 1))
    base = 7000 if kb_scope else 5000
    per_question = 900 if kb_scope else 700
    return max(5000, min(QUIZ_CONTEXT_MAX_CHARS, base + count * per_question))


def _build_context_text(docs, *, max_chars: int) -> str:
    blocks: list[str] = []
    total_chars = 0
    for doc in docs or []:
        text = str(getattr(doc, "page_content", "") or "").strip()
        if not text:
            continue
        sep_len = 2 if blocks else 0
        remaining = max_chars - total_chars - sep_len
        if remaining <= 0:
            break
        if len(text) > remaining:
            if remaining > 20:
                text = f"{text[: remaining - 16].rstrip()}\n[... truncated]"
                blocks.append(text)
            elif not blocks:
                blocks.append(text[:remaining])
            break
        blocks.append(text)
        total_chars += sep_len + len(text)
    return "\n\n".join(blocks)


def _doc_search_identity(doc: Any) -> tuple[str, str, str]:
    meta = dict(getattr(doc, "metadata", {}) or {})
    doc_id = str(meta.get("doc_id") or "")
    chunk = str(meta.get("chunk") or "")
    page = str(meta.get("page") or "")
    if doc_id and (chunk or page):
        return (doc_id, page, chunk)
    content = str(getattr(doc, "page_content", "") or "").strip()
    return (doc_id, page, content[:160])


def _dedupe_search_docs(docs: list[Any], *, limit: int | None = None) -> list[Any]:
    out: list[Any] = []
    seen: set[tuple[str, str, str]] = set()
    for doc in docs or []:
        ident = _doc_search_identity(doc)
        if ident in seen:
            continue
        seen.add(ident)
        out.append(doc)
        if limit is not None and len(out) >= limit:
            break
    return out


def _similarity_search_focus_seed_docs(
    *,
    vectorstore: Any,
    focus_concepts: list[str],
    fallback_query: str,
    k: int,
    search_filter: dict[str, Any],
) -> list[Any]:
    cleaned = [str(item).strip() for item in (focus_concepts or []) if str(item).strip()]
    if not cleaned:
        return vectorstore.similarity_search(fallback_query, k=k, filter=search_filter)

    if len(cleaned) == 1:
        return vectorstore.similarity_search(cleaned[0], k=k, filter=search_filter)

    target_k = max(1, int(k or 1))
    # Pull a small batch per concept, then dedupe + trim.
    per_focus_k = max(4, min(target_k, int(math.ceil(target_k / len(cleaned))) + 2))
    merged: list[Any] = []
    for concept in cleaned:
        try:
            merged.extend(vectorstore.similarity_search(concept, k=per_focus_k, filter=search_filter) or [])
        except Exception:
            logger.exception("Quiz focus seed search failed for concept=%s", concept)
    merged = _dedupe_search_docs(merged, limit=target_k)
    if len(merged) >= target_k:
        return merged

    try:
        fallback = vectorstore.similarity_search(fallback_query, k=target_k, filter=search_filter) or []
    except Exception:
        fallback = []
    return _dedupe_search_docs([*merged, *fallback], limit=target_k)


def _build_context(
    user_id: str,
    doc_id: Optional[str],
    kb_id: Optional[str],
    reference_questions: Optional[str],
    focus_concepts: Optional[List[str]] = None,
    target_count: int = 5,
) -> tuple[str, List[str]]:
    """Build context and collect related keypoint_ids from vector search metadata.

    Returns (context_text, keypoint_ids).
    """
    query = "key concepts and definitions"
    cleaned_focus: list[str] = []
    if focus_concepts:
        cleaned_focus = [str(item).strip() for item in focus_concepts if str(item).strip()]
        if cleaned_focus:
            query = ", ".join(cleaned_focus)
    if doc_id:
        vectorstore = get_vectorstore(user_id)
        k = _context_seed_search_k(target_count, kb_scope=False, focus_concepts=focus_concepts)
        docs = _similarity_search_focus_seed_docs(
            vectorstore=vectorstore,
            focus_concepts=cleaned_focus,
            fallback_query=query,
            k=k,
            search_filter={"doc_id": doc_id},
        )
        if not docs:
            raise ValueError("No relevant context found for quiz generation")
        max_chars = _context_char_budget(target_count, kb_scope=False)
        context = ""
        if bool(getattr(settings, "quiz_context_reconstruct_enabled", True)):
            try:
                built = build_quiz_context_from_seeds(
                    user_id=user_id,
                    seed_docs=list(docs),
                    max_chars=max_chars,
                    kb_scope=False,
                )
                context = built.text or ""
                logger.info(
                    "Quiz context build doc_scope seeds=%s filtered=%s reconstructed=%s modes=%s fallback=%s used=%s",
                    built.stats.get("seed_count", 0),
                    built.stats.get("filtered_seed_count", 0),
                    built.stats.get("reconstructed_count", 0),
                    built.stats.get("build_modes", {}),
                    built.stats.get("fallback_used", False),
                    built.stats.get("used_passage_count", 0),
                )
            except Exception:
                logger.exception("Quiz context reconstruction failed for doc scope; fallback to raw chunks")
        if not context:
            context = _build_context_text(docs, max_chars=max_chars)
        return context, _extract_keypoint_ids(docs)
    if kb_id:
        vectorstore = get_vectorstore(user_id)
        k = _context_seed_search_k(target_count, kb_scope=True, focus_concepts=focus_concepts)
        docs = _similarity_search_focus_seed_docs(
            vectorstore=vectorstore,
            focus_concepts=cleaned_focus,
            fallback_query=query,
            k=k,
            search_filter={"kb_id": kb_id},
        )
        if not docs:
            raise ValueError("No relevant context found for quiz generation")
        max_chars = _context_char_budget(target_count, kb_scope=True)
        context = ""
        if bool(getattr(settings, "quiz_context_reconstruct_enabled", True)):
            try:
                built = build_quiz_context_from_seeds(
                    user_id=user_id,
                    seed_docs=list(docs),
                    max_chars=max_chars,
                    kb_scope=True,
                    default_kb_id=kb_id,
                )
                context = built.text or ""
                logger.info(
                    "Quiz context build kb_scope seeds=%s filtered=%s reconstructed=%s modes=%s fallback=%s used=%s",
                    built.stats.get("seed_count", 0),
                    built.stats.get("filtered_seed_count", 0),
                    built.stats.get("reconstructed_count", 0),
                    built.stats.get("build_modes", {}),
                    built.stats.get("fallback_used", False),
                    built.stats.get("used_passage_count", 0),
                )
            except Exception:
                logger.exception("Quiz context reconstruction failed for kb scope; fallback to raw chunks")
        if not context:
            context = _build_context_text(docs, max_chars=max_chars)
        return context, _extract_keypoint_ids(docs)
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
                "Focus on the following concepts when generating questions.\n"
                "Every question must primarily test at least one listed concept.\n"
                "In the `concepts` field, include at least one concept name copied from this list verbatim whenever possible:\n"
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


def _question_matches_focus_concepts(question: dict[str, Any], focus_concepts: Optional[List[str]]) -> bool:
    cleaned_focus = [str(item).strip() for item in (focus_concepts or []) if str(item).strip()]
    if not cleaned_focus:
        return True
    focus_keys = [_normalize_text_for_compare(item) for item in cleaned_focus]
    focus_keys = [key for key in focus_keys if key]
    if not focus_keys:
        return True

    concept_keys = [
        _normalize_text_for_compare(item)
        for item in (question.get("concepts") or [])
        if str(item).strip()
    ]
    concept_keys = [key for key in concept_keys if key]
    for c_key in concept_keys:
        for f_key in focus_keys:
            if c_key == f_key or c_key in f_key or f_key in c_key:
                return True

    combined_text = " ".join(
        [
            str(question.get("question") or ""),
            str(question.get("explanation") or ""),
        ]
    )
    combined_key = _normalize_text_for_compare(combined_text)
    if not combined_key:
        return False
    for f_key in focus_keys:
        if f_key and f_key in combined_key:
            return True
    return False


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


def _is_fragmented_quiz_text(text: str) -> bool:
    candidate = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not candidate:
        return False
    if "[... truncated]" in candidate:
        return True
    lines = [line.strip() for line in candidate.split("\n") if line.strip()]
    if len(lines) < 3:
        return False
    if is_low_quality(
        candidate,
        mode=getattr(settings, "noise_filter_level", "balanced"),
    ):
        return True
    lengths = [len(re.sub(r"\s+", "", line)) for line in lines]
    if not lengths:
        return False
    avg_len = sum(lengths) / max(1, len(lengths))
    single_char_ratio = sum(1 for n in lengths if n <= 1) / max(1, len(lengths))
    short_line_ratio = sum(1 for n in lengths if n <= 6) / max(1, len(lengths))
    if single_char_ratio >= 0.45:
        return True
    if short_line_ratio >= 0.75 and avg_len < 8:
        return True
    if candidate.count("\n") >= 4 and avg_len < 10:
        return True
    return False


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
    if bool(getattr(settings, "quiz_context_fragment_filter_enabled", True)):
        if _is_fragmented_quiz_text(question):
            return None, "fragmented_question"
        if _is_fragmented_quiz_text(explanation):
            return None, "fragmented_explanation"

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
        "dropped_focus_mismatch": 0,
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
        if focus_concepts and not _question_matches_focus_concepts(normalized, focus_concepts):
            report["dropped_focus_mismatch"] += 1
            continue
        if _would_exceed_concept_repeat_limit(concepts, concept_counts, concept_limit):
            report["dropped_concept_overload"] += 1
            continue

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
        "dropped_focus_mismatch": int(base.get("dropped_focus_mismatch", 0)) + int(extra.get("dropped_focus_mismatch", 0)),
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
        "Quiz quality guardrail stage=%s requested=%s raw=%s kept=%s drop_invalid=%s drop_dup_exact=%s drop_dup_near=%s drop_concept=%s drop_focus=%s resampled=%s invalid_reasons=%s",
        stage,
        requested_count,
        report.get("raw_count", 0),
        report.get("kept_count", 0),
        report.get("dropped_invalid", 0),
        report.get("dropped_duplicate_exact", 0),
        report.get("dropped_duplicate_near", 0),
        report.get("dropped_concept_overload", 0),
        report.get("dropped_focus_mismatch", 0),
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
        user_id,
        doc_id,
        kb_id,
        reference_questions,
        focus_concepts,
        target_count=count,
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
