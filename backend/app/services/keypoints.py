import asyncio
import logging
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.llm import get_llm
from app.core.vectorstore import get_vectorstore
from app.models import Keypoint
from app.services.keypoint_dedup import normalize_keypoint_text
from app.utils.json_tools import safe_json_loads

logger = logging.getLogger(__name__)

KEYPOINT_SYSTEM = (
    "你是一位知识提取专家。从材料中提取核心和关键的知识点。"
    "重点关注：(1) 可以独立学习的独立概念/理论/方法，"
    "(2) 关键定义、公式、原理或关键步骤，"
    "(3) 重要的关系或模式。"
    "每个知识点应该简洁且聚焦 - 避免冗长的描述。"
    "优先考虑深度和重要性，而非数量。"
    "返回 JSON 数组：[{{text: string, explanation?: string}}, ...]。"
    "text 应该是简洁清晰的陈述（通常 10-30 个字）。"
    "explanation 是可选的，仅在提供必要说明时添加（保持简短，不超过 50 个字）。"
    "\n\n重要：所有输出必须使用中文（简体中文）。"
)

CHUNK_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", KEYPOINT_SYSTEM),
        (
            "human",
            "从此文档片段中提取 3-5 个核心知识点。专注于最重要的概念，"
            "忽略次要细节。每个知识点必须独立且有意义。"
            "仅返回 JSON 对象数组（不要其他文本）。"
            "所有内容必须使用中文（简体中文）。\n\n文档片段：\n{chunk}",
        ),
    ]
)

FINAL_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", KEYPOINT_SYSTEM),
        (
            "human",
            "审查并精炼这些知识点。你的任务：\n"
            "1. 删除重复项并合并相似的点\n"
            "2. 仅保留最重要和核心的点（优先深度而非广度）\n"
            "3. 确保每个点独立且可以独立存在\n"
            "4. 使文本简洁且聚焦 - 删除不必要的词语\n"
            "5. 保持解释简短，如果冗余则删除\n"
            "目标：8-12 个核心要点（如果能抓住核心，更少更好）。"
            "仅返回 JSON 数组 [{{text, explanation?}}]（不要其他文本）。"
            "所有内容必须使用中文（简体中文）。\n\n知识点列表：\n{points}",
        ),
    ]
)

# Larger chunks = fewer LLM calls; cap prevents runaway on huge docs
_KP_CHUNK_SIZE = 6000
_KP_CHUNK_OVERLAP = 300
_MAX_CHUNKS = 15
_KP_MIN_TEXT_LEN = 4
_KP_MAX_TEXT_LEN = 40
_KP_MAX_EXPLANATION_LEN = 80
_KP_WARN_LOW_COUNT = 3

_KP_GENERIC_TEXT_PATTERNS = [
    "重要概念",
    "核心概念",
    "关键概念",
    "关键知识点",
    "核心知识点",
    "相关知识点",
    "主要内容",
    "核心内容",
    "重点内容",
    "本节内容",
    "知识点总结",
    "学习目标",
]
_KP_GENERIC_TEXT_PATTERNS_NORMALIZED = [normalize_keypoint_text(p) for p in _KP_GENERIC_TEXT_PATTERNS]
_KP_HEADING_LIKE_PATTERNS = [
    re.compile(r"^第[一二三四五六七八九十0-9]+[章节部分]"),
    re.compile(r"^\d+(?:\.\d+){0,3}$"),
    re.compile(r"^(引言|绪论|总结|小结|习题|参考文献)$"),
]
_KP_COMPARE_REMOVE_RE = re.compile(
    r"[\s\-_—·•、，,。；;：:()（）\[\]{}<>《》\"'“”‘’]+"
)


def _sample_chunks(chunks: list[str], max_count: int) -> list[str]:
    """Evenly sample chunks when there are too many."""
    if len(chunks) <= max_count:
        return chunks
    step = len(chunks) / max_count
    return [chunks[int(i * step)] for i in range(max_count)]


def _parse_point(p) -> dict:
    if isinstance(p, str):
        t = p.strip()
        return {"text": t, "explanation": None, "source": None, "page": None, "chunk": None} if t else None
    if isinstance(p, dict):
        text = p.get("text") or str(p.get("text", "")).strip()
        if not text:
            return None
        return {
            "text": text,
            "explanation": p.get("explanation") or None,
            "source": None,
            "page": None,
            "chunk": None,
        }
    return None


def _clean_keypoint_text(text: str) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    s = re.sub(r"^[\-\u2022\u00b7•·,，;；:：]+", "", s).strip()
    s = re.sub(r"[，,；;。.!！?？：:]+$", "", s).strip()
    return s


def _clean_keypoint_explanation(explanation: str | None, text: str | None = None) -> str | None:
    if explanation is None:
        return None
    s = re.sub(r"\s+", " ", str(explanation or "")).strip()
    if not s:
        return None
    if len(s) > _KP_MAX_EXPLANATION_LEN:
        s = s[:_KP_MAX_EXPLANATION_LEN].rstrip(" ，,；;。.!！?？：:")
    if not s:
        return None
    if text:
        norm_text = normalize_keypoint_text(text)
        norm_exp = normalize_keypoint_text(s)
        if norm_text and norm_exp:
            if norm_text == norm_exp:
                return None
            if (norm_text in norm_exp or norm_exp in norm_text) and abs(len(norm_text) - len(norm_exp)) <= 8:
                return None
    return s


def _is_heading_like_keypoint_text(text: str, normalized_text: str) -> bool:
    candidate = (text or "").strip() or normalized_text
    if not candidate:
        return True
    return any(pattern.match(candidate) for pattern in _KP_HEADING_LIKE_PATTERNS)


def _is_generic_keypoint_text(text: str, normalized_text: str) -> bool:
    if not normalized_text:
        return False
    if normalized_text in _KP_GENERIC_TEXT_PATTERNS_NORMALIZED:
        return True
    if len(normalized_text) <= 12:
        return any(p and p in normalized_text for p in _KP_GENERIC_TEXT_PATTERNS_NORMALIZED)
    return False


def _comparison_key_from_normalized(normalized_text: str) -> str:
    return _KP_COMPARE_REMOVE_RE.sub("", normalized_text or "")


def _postprocess_extracted_keypoints(points: list[Any], *, mode: str) -> tuple[list[dict], dict]:
    if mode not in {"chunk", "final", "final_relaxed_fallback"}:
        raise ValueError(f"Unsupported keypoint postprocess mode: {mode}")

    diagnostics = {
        "input_count": len(points or []),
        "kept_count": 0,
        "dropped_invalid": 0,
        "dropped_empty": 0,
        "dropped_duplicate": 0,
        "dropped_length": 0,
        "dropped_generic": 0,
        "dropped_heading_like": 0,
        "mode": mode,
    }

    apply_strict_filters = mode == "final"
    seen_keys: set[str] = set()
    out: list[dict] = []

    for raw in points or []:
        parsed = _parse_point(raw)
        if not parsed:
            diagnostics["dropped_invalid"] += 1
            continue

        text = _clean_keypoint_text(parsed.get("text") or "")
        if not text:
            diagnostics["dropped_empty"] += 1
            continue

        normalized_text = normalize_keypoint_text(text)
        compare_key = _comparison_key_from_normalized(normalized_text)
        if not normalized_text or not compare_key:
            diagnostics["dropped_empty"] += 1
            continue

        if compare_key in seen_keys:
            diagnostics["dropped_duplicate"] += 1
            continue

        if apply_strict_filters and (
            len(normalized_text) < _KP_MIN_TEXT_LEN or len(normalized_text) > _KP_MAX_TEXT_LEN
        ):
            diagnostics["dropped_length"] += 1
            continue

        if apply_strict_filters and _is_heading_like_keypoint_text(text, normalized_text):
            diagnostics["dropped_heading_like"] += 1
            continue

        if apply_strict_filters and _is_generic_keypoint_text(text, normalized_text):
            diagnostics["dropped_generic"] += 1
            continue

        parsed["text"] = text
        parsed["explanation"] = _clean_keypoint_explanation(parsed.get("explanation"), text=text)
        seen_keys.add(compare_key)
        out.append(parsed)

    diagnostics["kept_count"] = len(out)
    return out, diagnostics


def _attach_source(user_id: str, doc_id: str, point: dict) -> dict:
    query_text = point.get("text") or ""
    if not query_text:
        return point
    try:
        vectorstore = get_vectorstore(user_id)
        docs = vectorstore.similarity_search(
            query_text, k=1, filter={"doc_id": doc_id}
        )
        if docs:
            meta = docs[0].metadata or {}
            point["source"] = meta.get("source")
            point["page"] = meta.get("page")
            point["chunk"] = meta.get("chunk")
    except Exception:
        pass
    return point


def _build_keypoint_id(doc_id: str, index: int) -> str:
    """Build a stable keypoint id for a document."""
    safe_prefix = (doc_id or "doc")[:8]
    return f"KP-{safe_prefix}-{index:03d}"


def save_keypoints_to_db(
    db: Session,
    user_id: str,
    doc_id: str,
    points: list[dict],
    kb_id: Optional[str] = None,
    overwrite: bool = False,
) -> list[Keypoint]:
    """Persist keypoints to DB and vectorstore with stable ids."""
    if overwrite:
        db.query(Keypoint).filter(
            Keypoint.user_id == user_id, Keypoint.doc_id == doc_id
        ).delete()
        db.commit()
        try:
            vectorstore = get_vectorstore(user_id)
            vectorstore.delete(where={"doc_id": doc_id, "type": "keypoint"})
        except Exception:
            pass

    vectorstore = get_vectorstore(user_id)
    saved: list[Keypoint] = []
    for idx, point in enumerate(points, start=1):
        parsed = _parse_point(point) if isinstance(point, (dict, str)) else None
        if not parsed or not parsed.get("text"):
            continue
        kp_id = _build_keypoint_id(doc_id, idx)
        keypoint = Keypoint(
            id=kp_id,
            user_id=user_id,
            doc_id=doc_id,
            kb_id=kb_id,
            text=parsed["text"],
            explanation=point.get("explanation") if isinstance(point, dict) else None,
            source=point.get("source") if isinstance(point, dict) else None,
            page=point.get("page") if isinstance(point, dict) else None,
            chunk=point.get("chunk") if isinstance(point, dict) else None,
        )
        db.add(keypoint)
        saved.append(keypoint)
        vectorstore.add_texts(
            [keypoint.text],
            metadatas=[
                {
                    "keypoint_id": kp_id,
                    "doc_id": doc_id,
                    "kb_id": kb_id,
                    "type": "keypoint",
                }
            ],
            ids=[kp_id],
        )
    db.commit()
    return saved


def _search_keypoints_per_concept(
    vectorstore,
    concepts: list[str],
    filter_dict: dict,
    max_distance: float = 1.0,
    top_k_per_concept: int = 2,
) -> list[str]:
    """Search per concept individually and merge results (deduplicated)."""
    seen: set[str] = set()
    matched: list[str] = []
    for concept in concepts:
        text = str(concept).strip()
        if not text:
            continue
        try:
            results = vectorstore.similarity_search_with_score(
                text, k=top_k_per_concept, filter=filter_dict,
            )
        except Exception:
            continue
        for doc, score in results:
            meta = getattr(doc, "metadata", {}) or {}
            kp_id = meta.get("keypoint_id")
            if not kp_id or kp_id in seen:
                continue
            if score <= max_distance:
                seen.add(kp_id)
                matched.append(kp_id)
    return matched


def match_keypoints_by_concepts(
    user_id: str,
    doc_id: str,
    concepts: list[str],
    max_distance: float = 1.0,
    top_k: int = 2,
) -> list[str]:
    """Match concepts to keypoint ids within a document (per-concept search)."""
    if not concepts:
        return []
    vectorstore = get_vectorstore(user_id)
    return _search_keypoints_per_concept(
        vectorstore, concepts,
        filter_dict={"doc_id": doc_id, "type": "keypoint"},
        max_distance=max_distance,
        top_k_per_concept=top_k,
    )


def match_keypoints_by_kb(
    user_id: str,
    kb_id: str,
    concepts: list[str],
    max_distance: float = 1.0,
    top_k: int = 2,
) -> list[str]:
    """Match concepts to keypoint ids within a knowledge base (per-concept search)."""
    if not concepts:
        return []
    vectorstore = get_vectorstore(user_id)
    return _search_keypoints_per_concept(
        vectorstore, concepts,
        filter_dict={"kb_id": kb_id, "type": "keypoint"},
        max_distance=max_distance,
        top_k_per_concept=top_k,
    )


def update_keypoint_mastery(db: Session, keypoint_id: str, is_correct: bool) -> None:
    """Deprecated: use app.services.mastery.record_quiz_result instead."""
    from app.services.mastery import record_quiz_result

    record_quiz_result(db, keypoint_id, is_correct)
    db.commit()


async def extract_keypoints(
    text: str,
    user_id: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> list[dict]:
    llm = get_llm(temperature=0.2)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_KP_CHUNK_SIZE, chunk_overlap=_KP_CHUNK_OVERLAP
    )
    chunks = splitter.split_text(text)
    chunks = _sample_chunks(chunks, _MAX_CHUNKS)

    async def _process_chunk(chunk_index: int, chunk: str) -> list[dict]:
        safe_chunk = chunk.replace("{", "{{").replace("}", "}}")
        msg = CHUNK_PROMPT.format_messages(chunk=safe_chunk)
        result = await llm.ainvoke(msg)
        try:
            raw_points = safe_json_loads(result.content)
        except Exception as exc:
            logger.warning(
                "keypoints.extract.chunk_parse_error %s",
                {
                    "doc_id": doc_id,
                    "chunk_count": len(chunks),
                    "chunk_index": chunk_index,
                    "error": str(exc),
                },
            )
            raw_points = []
        if not isinstance(raw_points, list):
            logger.warning(
                "keypoints.extract.chunk_non_list %s",
                {
                    "doc_id": doc_id,
                    "chunk_count": len(chunks),
                    "chunk_index": chunk_index,
                    "result_type": type(raw_points).__name__,
                },
            )
            points = []
        else:
            points = raw_points
        processed, diag = _postprocess_extracted_keypoints(points, mode="chunk")
        logger.info(
            "keypoints.extract.chunk_summary %s",
            {
                "doc_id": doc_id,
                "chunk_count": len(chunks),
                "chunk_index": chunk_index,
                "raw_chunk_count": len(points),
                "chunk_kept_count": diag["kept_count"],
                "chunk_dropped_invalid": diag["dropped_invalid"],
                "chunk_dropped_empty": diag["dropped_empty"],
                "chunk_dropped_duplicate": diag["dropped_duplicate"],
            },
        )
        return processed

    chunk_results = await asyncio.gather(
        *[_process_chunk(idx, c) for idx, c in enumerate(chunks, start=1)]
    )
    all_points: list[dict] = [p for chunk_pts in chunk_results for p in chunk_pts]

    points_str = "\n".join(
        f"- {p.get('text', '')}" + (f" ({p.get('explanation')})" if p.get("explanation") else "")
        for p in all_points
    )
    final_msg = FINAL_PROMPT.format_messages(points=points_str)
    final_result = await llm.ainvoke(final_msg)
    try:
        raw_final_points = safe_json_loads(final_result.content)
    except Exception as exc:
        logger.warning(
            "keypoints.extract.final_parse_error %s",
            {
                "doc_id": doc_id,
                "chunk_count": len(chunks),
                "all_chunk_points_count": len(all_points),
                "error": str(exc),
            },
        )
        raw_final_points = []
    if not isinstance(raw_final_points, list):
        logger.warning(
            "keypoints.extract.final_non_list %s",
            {
                "doc_id": doc_id,
                "chunk_count": len(chunks),
                "all_chunk_points_count": len(all_points),
                "result_type": type(raw_final_points).__name__,
            },
        )
        raw_final_points = []

    strict_points, strict_diag = _postprocess_extracted_keypoints(raw_final_points, mode="final")
    final_points = strict_points
    final_diag = strict_diag
    relaxed_fallback_used = False

    if not final_points and raw_final_points:
        relaxed_points, relaxed_diag = _postprocess_extracted_keypoints(
            raw_final_points, mode="final_relaxed_fallback"
        )
        if relaxed_points:
            final_points = relaxed_points
            final_diag = relaxed_diag
            relaxed_fallback_used = True

    out: list[dict] = []
    source_attach_hits = 0
    source_attach_misses = 0
    for parsed in final_points:
        if user_id and doc_id:
            parsed = _attach_source(user_id, doc_id, parsed)
            if any(parsed.get(field) is not None for field in ("source", "page", "chunk")):
                source_attach_hits += 1
            else:
                source_attach_misses += 1
        out.append(parsed)

    summary_payload = {
        "doc_id": doc_id,
        "chunk_count": len(chunks),
        "all_chunk_points_count": len(all_points),
        "raw_final_candidate_count": len(raw_final_points),
        "final_count": len(out),
        "postprocess_mode_used": final_diag["mode"],
        "postprocess_relaxed_fallback": relaxed_fallback_used,
        "dropped_invalid": final_diag["dropped_invalid"],
        "dropped_empty": final_diag["dropped_empty"],
        "dropped_duplicate": final_diag["dropped_duplicate"],
        "dropped_length": final_diag["dropped_length"],
        "dropped_generic": final_diag["dropped_generic"],
        "dropped_heading_like": final_diag["dropped_heading_like"],
        "source_attach_hits": source_attach_hits,
        "source_attach_misses": source_attach_misses,
    }
    logger.info("keypoints.extract.final_summary %s", summary_payload)
    if not out:
        logger.warning("keypoints.extract.final_empty %s", summary_payload)
    elif len(out) < _KP_WARN_LOW_COUNT:
        logger.warning("keypoints.extract.final_low_count %s", summary_payload)
    return out
