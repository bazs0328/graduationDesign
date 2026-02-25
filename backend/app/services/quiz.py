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
from app.core.image_vectorstore import query_image_documents
from app.core.vectorstore import get_vectorstore
from app.services.quiz_context import build_quiz_context_from_seeds
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
QUIZ_IMAGE_SCORE_THRESHOLD = 0.35
QUIZ_IMAGE_GENERIC_SCORE_THRESHOLD = 0.65
QUIZ_IMAGE_HINT_RE = re.compile(
    r"(图中|下图|上图|如图|图示|见图|figure|fig\\.?|diagram|shown\\s+in\\s+the\\s+figure)",
    re.IGNORECASE,
)
QUIZ_FIGURE_REF_RE = re.compile(
    r"(?:图|fig(?:ure)?\.?)\s*[（(]?\s*([0-9]+|[一二三四五六七八九十]+)\s*[)）]?",
    re.IGNORECASE,
)
_CN_NUM_TO_INT = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_INT_TO_CN_SMALL = {value: key for key, value in _CN_NUM_TO_INT.items()}

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
    if focus_concepts:
        cleaned = [str(item).strip() for item in focus_concepts if str(item).strip()]
        if cleaned:
            query = ", ".join(cleaned)
    if doc_id:
        vectorstore = get_vectorstore(user_id)
        k = _context_seed_search_k(target_count, kb_scope=False, focus_concepts=focus_concepts)
        docs = vectorstore.similarity_search(
            query, k=k, filter={"doc_id": doc_id}
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
        docs = vectorstore.similarity_search(
            query, k=k, filter={"kb_id": kb_id}
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


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_json_list(value: Any) -> list | None:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return None
    return None


def _cn_numeral_to_int(text: str) -> int | None:
    token = str(text or "").strip()
    if not token:
        return None
    if token.isdigit():
        try:
            return int(token)
        except ValueError:
            return None
    if token in _CN_NUM_TO_INT:
        return _CN_NUM_TO_INT[token]
    if len(token) == 2 and token.startswith("十") and token[1] in _CN_NUM_TO_INT:
        return 10 + _CN_NUM_TO_INT[token[1]]
    if len(token) == 2 and token.endswith("十") and token[0] in _CN_NUM_TO_INT:
        return _CN_NUM_TO_INT[token[0]] * 10
    if len(token) == 3 and token[1] == "十" and token[0] in _CN_NUM_TO_INT and token[2] in _CN_NUM_TO_INT:
        return _CN_NUM_TO_INT[token[0]] * 10 + _CN_NUM_TO_INT[token[2]]
    return None


def _normalize_figure_token(token: str) -> str:
    raw = str(token or "").strip()
    if not raw:
        return ""
    raw = raw.strip("()（）[]【】")
    numeric = _cn_numeral_to_int(raw)
    if numeric is not None and numeric > 0:
        return str(numeric)
    return raw.lower()


def _extract_figure_refs(question: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            str(question.get("question") or ""),
            str(question.get("explanation") or ""),
        ]
    )
    refs: list[str] = []
    seen: set[str] = set()
    for match in QUIZ_FIGURE_REF_RE.finditer(text or ""):
        normalized = _normalize_figure_token(match.group(1) or "")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        refs.append(normalized)
    return refs


def _figure_ref_aliases(ref_token: str) -> list[str]:
    token = _normalize_figure_token(ref_token)
    if not token:
        return []
    aliases = [token]
    if token.isdigit():
        value = int(token)
        cn = _INT_TO_CN_SMALL.get(value)
        if cn:
            aliases.append(cn)
    return aliases


def _caption_matches_figure_ref(text: str, ref_token: str) -> bool:
    content = str(text or "").strip()
    if not content:
        return False
    aliases = [re.escape(alias) for alias in _figure_ref_aliases(ref_token) if alias]
    if not aliases:
        return False
    alias_group = "|".join(aliases)
    pattern = re.compile(
        rf"(?:图|fig(?:ure)?\.?)\s*[（(]?\s*(?:{alias_group})\s*[)）]?",
        re.IGNORECASE,
    )
    return bool(pattern.search(content))


def _rerank_image_hits_for_figure_ref(
    question: dict[str, Any],
    image_hits: list[tuple[Any, float]],
) -> list[tuple[Any, float]]:
    if not image_hits:
        return []
    if not bool(getattr(settings, "quiz_image_figure_ref_rerank_enabled", True)):
        return image_hits
    refs = _extract_figure_refs(question)
    if not refs:
        return image_hits
    primary_ref = refs[0]
    min_semantic_floor = 0.12

    scored: list[tuple[float, float, int, Any]] = []
    for idx, (image_doc, score) in enumerate(image_hits):
        base_score = float(score)
        meta = getattr(image_doc, "metadata", {}) or {}
        caption = str(meta.get("caption") or "").strip()
        surrogate = str(getattr(image_doc, "page_content", "") or "").strip()
        matches = _caption_matches_figure_ref(caption, primary_ref) or _caption_matches_figure_ref(
            surrogate, primary_ref
        )
        bonus = 1.0 if matches and base_score >= min_semantic_floor else 0.0
        scored.append((bonus, base_score, -idx, image_doc))

    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [(doc, score) for bonus, score, _idx, doc in scored]


def _question_mentions_figure(question: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(question.get("question") or ""),
            str(question.get("explanation") or ""),
        ]
    )
    return bool(QUIZ_IMAGE_HINT_RE.search(text) or QUIZ_FIGURE_REF_RE.search(text))


def _question_image_query(question: dict[str, Any]) -> str:
    q_text = str(question.get("question") or "").strip()
    concepts = [str(c).strip() for c in (question.get("concepts") or []) if str(c).strip()]
    parts = [q_text]
    if concepts:
        parts.append(" ".join(concepts[:3]))
    refs = _extract_figure_refs(question)
    if refs:
        parts.append(" ".join([f"图{refs[0]}", f"Figure {refs[0]}", "图示意图 figure diagram"]))
    elif _question_mentions_figure(question):
        parts.append("图 示意图 figure diagram")
    return " ".join([p for p in parts if p]).strip()


def _build_quiz_question_image_payload(question: dict[str, Any], image_doc: Any, score: float) -> dict[str, Any] | None:
    meta = getattr(image_doc, "metadata", {}) or {}
    image_doc_id = meta.get("doc_id")
    if not image_doc_id:
        return None
    page = _safe_int(meta.get("page"))
    chunk = _safe_int(meta.get("chunk"))
    if page is None and chunk is None:
        return None

    params: list[str] = []
    if page is not None:
        params.append(f"page={page}")
    if chunk is not None:
        params.append(f"chunk={chunk}")
    query = "&".join(params)
    url = f"/api/docs/{image_doc_id}/image"
    if query:
        url = f"{url}?{query}"

    caption = str(meta.get("caption") or "").strip() or None
    bbox = _safe_json_list(meta.get("bbox"))
    surrogate = str(getattr(image_doc, "page_content", "") or "").strip() or None
    payload = {
        "url": url,
        "doc_id": str(image_doc_id),
        "page": page,
        "chunk": chunk,
        "caption": caption,
        "bbox": bbox,
        "score": round(float(score), 4),
        "surrogate_text": surrogate,
    }
    threshold = QUIZ_IMAGE_SCORE_THRESHOLD if _question_mentions_figure(question) else QUIZ_IMAGE_GENERIC_SCORE_THRESHOLD
    if float(score) < threshold:
        return None
    return payload


def _attach_images_to_questions(
    *,
    user_id: str,
    doc_id: str | None,
    kb_id: str | None,
    questions: list[dict],
) -> list[dict]:
    if not questions or (not doc_id and not kb_id):
        return questions
    search_filter = {"doc_id": doc_id} if doc_id else {"kb_id": kb_id}
    out: list[dict] = []
    for question in questions:
        q = dict(question or {})
        query = _question_image_query(q)
        if not query:
            out.append(q)
            continue
        refs = _extract_figure_refs(q)
        image_top_k = 2
        if refs:
            try:
                image_top_k = max(2, int(getattr(settings, "quiz_image_figure_ref_top_k", 5) or 5))
            except (TypeError, ValueError):
                image_top_k = 5
        try:
            image_hits = query_image_documents(
                user_id,
                query,
                top_k=image_top_k,
                search_filter=search_filter,
            )
        except Exception:
            logger.exception("Quiz image lookup failed")
            image_hits = []
        if refs and image_hits:
            image_hits = _rerank_image_hits_for_figure_ref(q, image_hits)
        attached = None
        for image_doc, score in image_hits:
            attached = _build_quiz_question_image_payload(q, image_doc, float(score))
            if attached:
                break
        if attached:
            q["image"] = attached
        out.append(q)
    return out


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


def _is_fragmented_quiz_text(text: str) -> bool:
    candidate = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not candidate:
        return False
    if "[... truncated]" in candidate:
        return True
    lines = [line.strip() for line in candidate.split("\n") if line.strip()]
    if len(lines) < 3:
        return False
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
    validated_questions = _attach_images_to_questions(
        user_id=user_id,
        doc_id=doc_id,
        kb_id=kb_id,
        questions=validated_questions,
    )

    try:
        json.dumps(validated_questions)  # validate serializable
    except TypeError as e:
        logger.error(f"Questions are not JSON serializable: {e}")
        raise ValueError(f"Generated questions are not JSON serializable: {str(e)}")

    return validated_questions
