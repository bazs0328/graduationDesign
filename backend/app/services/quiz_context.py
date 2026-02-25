from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from app.core.config import settings
from app.core.paths import kb_base_dir
from app.core.vectorstore import get_doc_vector_entries

logger = logging.getLogger(__name__)

_CAPTIONISH_RE = re.compile(r"^\s*(图|表|figure|fig\.?|table)\s*[\(（]?\s*[0-9一二三四五六七八九十A-Za-z]+", re.I)
_IMG_PLACEHOLDER_RE = re.compile(r"\[\s*图片块\s*\]")
_SEED_MIN_VISIBLE_CHARS = 80


@dataclass
class QuizContextPassage:
    doc_id: str
    kb_id: str | None
    source: str
    page: int | None
    start_chunk: int | None
    end_chunk: int | None
    text: str
    quality_score: float
    seed_rank: int
    build_mode: str


@dataclass
class QuizContextBuildResult:
    text: str
    stats: dict[str, Any] = field(default_factory=dict)


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_ws(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    return normalized.strip()


def _merge_broken_lines(text: str) -> str:
    lines = [line.strip() for line in _normalize_ws(text).split("\n")]
    if not lines:
        return ""
    merged: list[str] = []
    for line in lines:
        if not line:
            if merged and merged[-1] != "":
                merged.append("")
            continue
        if not merged or merged[-1] == "":
            merged.append(line)
            continue
        prev = merged[-1]
        # Join short broken lines into one sentence-like line.
        if (
            len(line) <= 18
            and len(prev) <= 60
            and not re.search(r"[。！？；;:：]$", prev)
            and not re.match(r"^[-•*]\s*", line)
            and not _CAPTIONISH_RE.match(line)
        ):
            merged[-1] = f"{prev} {line}".strip()
        else:
            merged.append(line)
    text = "\n".join(merged)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _visible_chars(text: str) -> str:
    return "".join(ch for ch in str(text or "") if not ch.isspace())


def _text_metrics(text: str) -> dict[str, float]:
    normalized = _normalize_ws(text)
    visible = _visible_chars(normalized)
    visible_len = len(visible)
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if not lines or visible_len == 0:
        return {
            "visible_len": float(visible_len),
            "line_count": float(len(lines)),
            "avg_line_len": 0.0,
            "single_char_line_ratio": 1.0 if lines else 0.0,
            "short_line_ratio": 1.0 if lines else 0.0,
            "line_break_ratio": 1.0 if visible_len else 0.0,
        }
    line_visible_lengths = [len(_visible_chars(line)) for line in lines]
    avg_line_len = sum(line_visible_lengths) / max(1, len(line_visible_lengths))
    single_char_lines = sum(1 for n in line_visible_lengths if n <= 1)
    short_lines = sum(1 for n in line_visible_lengths if n <= 6)
    return {
        "visible_len": float(visible_len),
        "line_count": float(len(lines)),
        "avg_line_len": float(avg_line_len),
        "single_char_line_ratio": single_char_lines / max(1, len(lines)),
        "short_line_ratio": short_lines / max(1, len(lines)),
        "line_break_ratio": normalized.count("\n") / max(1, visible_len),
    }


def _quality_score(text: str) -> float:
    m = _text_metrics(text)
    if m["visible_len"] <= 0:
        return 0.0
    score = 0.35
    score += min(0.35, m["visible_len"] / 1200.0)
    score += min(0.2, m["avg_line_len"] / 40.0)
    score -= m["single_char_line_ratio"] * 0.35
    score -= m["short_line_ratio"] * 0.2
    score -= min(0.15, m["line_break_ratio"] * 4.0)
    if _IMG_PLACEHOLDER_RE.search(text):
        score -= 0.5
    return max(0.0, min(1.0, score))


def _seed_quality_score(text: str, metadata: dict[str, Any]) -> float:
    score = _quality_score(text)
    normalized = _normalize_ws(text)
    if len(_visible_chars(normalized)) < _SEED_MIN_VISIBLE_CHARS:
        score -= 0.2
    if _CAPTIONISH_RE.match(normalized) and len(_visible_chars(normalized)) < 120:
        score -= 0.25
    if _IMG_PLACEHOLDER_RE.search(normalized):
        score -= 0.8
    if bool(metadata.get("ocr_override")):
        score -= 0.06
    page_q = _safe_float(metadata.get("page_text_quality_score"))
    if page_q is not None and page_q < 0.45:
        score -= min(0.12, (0.45 - page_q) * 0.3)
    return max(0.0, min(1.0, score))


def _should_filter_seed(text: str, metadata: dict[str, Any], score: float) -> tuple[bool, str | None]:
    normalized = _normalize_ws(text)
    if not normalized:
        return True, "empty"
    if _IMG_PLACEHOLDER_RE.search(normalized):
        return True, "image_placeholder"
    if score < 0.14:
        return True, "low_quality"
    m = _text_metrics(normalized)
    if m["single_char_line_ratio"] >= 0.45:
        return True, "single_char_lines"
    if m["short_line_ratio"] >= 0.75 and m["avg_line_len"] < 8:
        return True, "too_fragmented"
    if _CAPTIONISH_RE.match(normalized) and len(_visible_chars(normalized)) < 80:
        return True, "short_caption"
    return False, None


def _parse_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    return []


def _sidecar_path(user_id: str, kb_id: str | None, doc_id: str) -> str | None:
    if not kb_id:
        return None
    return os.path.join(kb_base_dir(user_id, kb_id), "content_list", f"{doc_id}.layout.json")


def _load_sidecar(user_id: str, kb_id: str | None, doc_id: str, cache: dict[tuple[str, str], dict | None]) -> dict | None:
    if not kb_id:
        return None
    cache_key = (kb_id, doc_id)
    if cache_key in cache:
        return cache[cache_key]
    path = _sidecar_path(user_id, kb_id, doc_id)
    if not path or not os.path.exists(path):
        cache[cache_key] = None
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        cache[cache_key] = payload if isinstance(payload, dict) else None
    except Exception:
        logger.debug("Failed to load quiz sidecar doc_id=%s path=%s", doc_id, path, exc_info=True)
        cache[cache_key] = None
    return cache[cache_key]


def _truncate_soft(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 24:
        return text[:max_chars]
    return f"{text[: max_chars - 16].rstrip()}\n[... truncated]"


def _build_neighbor_passage(entries: list[dict[str, Any]], *, chunk: int | None, target_chars: int, window: int) -> tuple[str, int | None, int | None]:
    if not entries:
        return "", None, None
    if chunk is None:
        text = _merge_broken_lines(str(entries[0].get("content") or ""))
        meta = entries[0].get("metadata") or {}
        c = _safe_int(meta.get("chunk"))
        return _truncate_soft(text, int(target_chars * 1.3)), c, c

    text_entries = [
        entry
        for entry in entries
        if str(((entry.get("metadata") or {}).get("modality") or "text")) != "image"
    ]
    if not text_entries:
        return "", None, None
    center_idx: int | None = None
    for idx, entry in enumerate(text_entries):
        c = _safe_int((entry.get("metadata") or {}).get("chunk"))
        if c == chunk:
            center_idx = idx
            break
    if center_idx is None:
        return "", None, None

    center_meta = text_entries[center_idx].get("metadata") or {}
    center_page = _safe_int(center_meta.get("page"))
    left = max(0, center_idx - max(1, window))
    right = min(len(text_entries) - 1, center_idx + max(1, window))
    selected = text_entries[left : right + 1]

    same_page = []
    if center_page is not None:
        same_page = [
            item
            for item in selected
            if _safe_int((item.get("metadata") or {}).get("page")) == center_page
        ]
    if same_page:
        same_page_text = _merge_broken_lines("\n\n".join(str(item.get("content") or "") for item in same_page))
        if len(_visible_chars(same_page_text)) >= min(220, target_chars // 2):
            selected = same_page

    # Widen once if still too short.
    joined = _merge_broken_lines("\n\n".join(str(item.get("content") or "") for item in selected))
    if len(_visible_chars(joined)) < min(220, target_chars // 2):
        left = max(0, center_idx - max(2, window + 2))
        right = min(len(text_entries) - 1, center_idx + max(2, window + 2))
        selected = text_entries[left : right + 1]
        joined = _merge_broken_lines("\n\n".join(str(item.get("content") or "") for item in selected))

    selected_chunks = [
        _safe_int((item.get("metadata") or {}).get("chunk"))
        for item in selected
    ]
    selected_chunks = [c for c in selected_chunks if c is not None]
    return (
        _truncate_soft(joined, int(target_chars * 1.35)),
        (min(selected_chunks) if selected_chunks else chunk),
        (max(selected_chunks) if selected_chunks else chunk),
    )


def _build_sidecar_passage(sidecar: dict | None, *, chunk: int | None, page: int | None, target_chars: int) -> str:
    if not sidecar or chunk is None:
        return ""
    manifest = sidecar.get("chunk_manifest")
    pages = sidecar.get("pages")
    if not isinstance(manifest, list) or not isinstance(pages, list):
        return ""

    manifest_entry = None
    for item in manifest:
        if not isinstance(item, dict):
            continue
        if _safe_int(item.get("chunk")) == chunk:
            manifest_entry = item
            break
    if not isinstance(manifest_entry, dict):
        return ""
    if str(manifest_entry.get("modality") or "text") == "image":
        return ""

    target_page = _safe_int(manifest_entry.get("page")) or page
    if target_page is None:
        return ""
    block_ids = _parse_json_list(manifest_entry.get("block_ids"))
    if not block_ids:
        return ""

    page_item = next(
        (item for item in pages if isinstance(item, dict) and _safe_int(item.get("page")) == target_page),
        None,
    )
    if not isinstance(page_item, dict):
        return ""
    ordered_blocks = page_item.get("ordered_blocks")
    if not isinstance(ordered_blocks, list):
        return ""

    target_positions: list[int] = []
    for idx, block in enumerate(ordered_blocks):
        if not isinstance(block, dict):
            continue
        if str(block.get("block_id") or "") in set(block_ids):
            target_positions.append(idx)
    if not target_positions:
        return ""

    left = min(target_positions)
    right = max(target_positions)
    target_chars = max(200, int(target_chars or 900))
    while True:
        text_parts: list[str] = []
        visible_len = 0
        for idx in range(left, right + 1):
            block = ordered_blocks[idx]
            if not isinstance(block, dict):
                continue
            if str(block.get("kind") or "") == "image":
                continue
            text = _normalize_ws(str(block.get("text") or ""))
            if not text:
                continue
            text_parts.append(text)
            visible_len += len(_visible_chars(text))
        if visible_len >= min(320, target_chars // 2):
            break
        if left <= 0 and right >= len(ordered_blocks) - 1:
            break
        if left > 0:
            left -= 1
        if right < len(ordered_blocks) - 1:
            right += 1
        if (right - left) > 14:
            break
    passage = _merge_broken_lines("\n\n".join(text_parts))
    return _truncate_soft(passage, int(target_chars * 1.35))


def _get_doc_entries_cached(user_id: str, doc_id: str, cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if doc_id in cache:
        return cache[doc_id]
    try:
        rows = get_doc_vector_entries(user_id, doc_id)
    except Exception:
        logger.debug("Quiz context doc entry fetch failed doc_id=%s", doc_id, exc_info=True)
        rows = []
    rows = [
        row
        for row in rows
        if str(((row.get("metadata") or {}).get("modality") or "text")) != "image"
        and str(((row.get("metadata") or {}).get("chunk_kind") or "text")) != "image"
    ]
    cache[doc_id] = rows
    return rows


def _normalize_compare(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized, flags=re.UNICODE)
    return normalized


def _is_similar_passage(text: str, seen: list[str]) -> bool:
    norm = _normalize_compare(text)
    if not norm:
        return True
    for existing in seen:
        existing_norm = _normalize_compare(existing)
        if not existing_norm:
            continue
        if norm == existing_norm:
            return True
        if len(norm) > 40 and len(existing_norm) > 40:
            if SequenceMatcher(None, norm, existing_norm).ratio() >= 0.94:
                return True
    return False


def _compose_context(passages: list[QuizContextPassage], *, max_chars: int, kb_scope: bool) -> tuple[str, int]:
    if not passages:
        return "", 0

    ordered = sorted(passages, key=lambda item: (item.seed_rank, -(item.quality_score)))
    if kb_scope:
        doc_order: list[str] = []
        grouped: dict[str, list[QuizContextPassage]] = {}
        for item in ordered:
            if item.doc_id not in grouped:
                grouped[item.doc_id] = []
                doc_order.append(item.doc_id)
            grouped[item.doc_id].append(item)
        interleaved: list[QuizContextPassage] = []
        while True:
            appended = False
            for doc_id in doc_order:
                bucket = grouped.get(doc_id) or []
                if not bucket:
                    continue
                interleaved.append(bucket.pop(0))
                appended = True
            if not appended:
                break
        ordered = interleaved

    blocks: list[str] = []
    total = 0
    used = 0
    for item in ordered:
        body = _normalize_ws(item.text)
        if not body:
            continue
        header = f"来源: {item.source}".strip()
        segment = f"{header}\n{body}" if header else body
        sep_len = 2 if blocks else 0
        remaining = max_chars - total - sep_len
        if remaining <= 0:
            break
        if len(segment) > remaining:
            if remaining <= 40:
                break
            segment = _truncate_soft(segment, remaining)
        blocks.append(segment)
        total += sep_len + len(segment)
        used += 1
    return "\n\n".join(blocks).strip(), used


def build_quiz_context_from_seeds(
    *,
    user_id: str,
    seed_docs: list[Any],
    max_chars: int,
    kb_scope: bool,
    default_kb_id: str | None = None,
) -> QuizContextBuildResult:
    stats: dict[str, Any] = {
        "seed_count": len(seed_docs or []),
        "filtered_seed_count": 0,
        "reconstructed_count": 0,
        "fallback_used": False,
        "drop_reasons": {},
        "build_modes": {},
    }
    if not seed_docs:
        return QuizContextBuildResult(text="", stats=stats)

    neighbor_window = max(1, int(getattr(settings, "quiz_context_neighbor_window", 2) or 2))
    target_chars = max(300, int(getattr(settings, "quiz_context_passage_target_chars", 900) or 900))
    fragment_filter_enabled = bool(getattr(settings, "quiz_context_fragment_filter_enabled", True))

    doc_entries_cache: dict[str, list[dict[str, Any]]] = {}
    sidecar_cache: dict[tuple[str, str], dict | None] = {}

    filtered_seeds: list[tuple[int, Any, dict[str, Any], str, float]] = []
    fallback_seeds: list[tuple[int, Any, dict[str, Any], str, float]] = []
    for rank, seed in enumerate(seed_docs or []):
        metadata = dict(getattr(seed, "metadata", {}) or {})
        text = _normalize_ws(str(getattr(seed, "page_content", "") or ""))
        score = _seed_quality_score(text, metadata)
        fallback_seeds.append((rank, seed, metadata, text, score))
        drop, reason = _should_filter_seed(text, metadata, score)
        if fragment_filter_enabled and drop:
            stats["filtered_seed_count"] += 1
            if reason:
                drops = stats["drop_reasons"]
                drops[reason] = int(drops.get(reason, 0)) + 1
            continue
        filtered_seeds.append((rank, seed, metadata, text, score))

    working_seeds = filtered_seeds or fallback_seeds
    if not filtered_seeds and fragment_filter_enabled:
        stats["fallback_used"] = True

    passages: list[QuizContextPassage] = []
    seen_passage_texts: list[str] = []
    for rank, _seed, metadata, seed_text, seed_score in working_seeds:
        doc_id = str(metadata.get("doc_id") or "").strip()
        if not doc_id:
            continue
        kb_id = str(metadata.get("kb_id") or default_kb_id or "").strip() or None
        source = str(metadata.get("source") or doc_id).strip() or doc_id
        page = _safe_int(metadata.get("page"))
        chunk = _safe_int(metadata.get("chunk"))

        neighbor_text = ""
        start_chunk = chunk
        end_chunk = chunk
        entries = _get_doc_entries_cached(user_id, doc_id, doc_entries_cache)
        if entries:
            neighbor_text, start_chunk, end_chunk = _build_neighbor_passage(
                entries,
                chunk=chunk,
                target_chars=target_chars,
                window=neighbor_window,
            )

        sidecar_text = _build_sidecar_passage(
            _load_sidecar(user_id, kb_id, doc_id, sidecar_cache),
            chunk=chunk,
            page=page,
            target_chars=target_chars,
        )

        candidates: list[tuple[str, str]] = []
        if neighbor_text:
            candidates.append(("chunk-neighbor", neighbor_text))
        if sidecar_text:
            candidates.append(("sidecar", sidecar_text))
        if seed_text:
            candidates.append(("raw-seed", seed_text))

        if not candidates:
            continue

        best_mode, best_text = candidates[0]
        best_score = _quality_score(best_text)
        for mode, text in candidates[1:]:
            q = _quality_score(text)
            bonus = 0.08 if mode == "sidecar" else 0.0
            if q + bonus > best_score + (0.02 if best_mode == "sidecar" else 0.0):
                best_mode, best_text, best_score = mode, text, q

        if _is_similar_passage(best_text, seen_passage_texts):
            continue
        seen_passage_texts.append(best_text)
        stats["build_modes"][best_mode] = int(stats["build_modes"].get(best_mode, 0)) + 1
        if best_mode != "raw-seed":
            stats["reconstructed_count"] += 1
        passages.append(
            QuizContextPassage(
                doc_id=doc_id,
                kb_id=kb_id,
                source=source,
                page=page,
                start_chunk=start_chunk,
                end_chunk=end_chunk,
                text=best_text,
                quality_score=max(best_score, seed_score),
                seed_rank=rank,
                build_mode=best_mode,
            )
        )

    if not passages:
        stats["fallback_used"] = True
        raw = "\n\n".join(
            _normalize_ws(str(getattr(seed, "page_content", "") or ""))
            for seed in (seed_docs or [])
            if _normalize_ws(str(getattr(seed, "page_content", "") or ""))
        )
        return QuizContextBuildResult(text=_truncate_soft(raw, max_chars), stats=stats)

    context_text, used_count = _compose_context(passages, max_chars=max_chars, kb_scope=kb_scope)
    stats["used_passage_count"] = used_count
    return QuizContextBuildResult(text=context_text, stats=stats)
