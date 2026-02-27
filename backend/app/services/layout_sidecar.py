from __future__ import annotations

import json
import os
import re
from typing import Any

from app.core.paths import kb_base_dir

_IMG_PLACEHOLDER_RE = re.compile(r"^\[\s*图片块\s*\]$", re.IGNORECASE)
_OCR_BLOCK_SENTINEL_RE = re.compile(r":ocr$", re.IGNORECASE)


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _normalize_ws(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    return normalized.strip()


def _parse_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return []
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return []


def _visible_chars(text: str) -> int:
    return len("".join(ch for ch in str(text or "") if not ch.isspace()))


def _find_manifest_entry(sidecar: dict[str, Any] | None, chunk: int | None) -> dict[str, Any] | None:
    if not sidecar or chunk is None:
        return None
    manifest = sidecar.get("chunk_manifest")
    if not isinstance(manifest, list):
        return None
    for item in manifest:
        if not isinstance(item, dict):
            continue
        if _safe_int(item.get("chunk")) == chunk:
            return item
    return None


def _find_page_blocks(sidecar: dict[str, Any] | None, page: int | None) -> list[dict[str, Any]]:
    if not sidecar or page is None:
        return []
    pages = sidecar.get("pages")
    if not isinstance(pages, list):
        return []
    for page_item in pages:
        if not isinstance(page_item, dict):
            continue
        if _safe_int(page_item.get("page")) != page:
            continue
        ordered_blocks = page_item.get("ordered_blocks")
        if isinstance(ordered_blocks, list):
            return [block for block in ordered_blocks if isinstance(block, dict)]
    return []


def load_layout_sidecar(user_id: str, kb_id: str | None, doc_id: str) -> dict[str, Any] | None:
    if not kb_id:
        return None
    path = os.path.join(kb_base_dir(user_id, kb_id), "content_list", f"{doc_id}.layout.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _metadata_block_ids(metadata: dict[str, Any], sidecar: dict[str, Any] | None = None) -> list[str]:
    block_ids: list[str] = []

    direct = str(metadata.get("block_id") or "").strip()
    if direct:
        block_ids.append(direct)

    for item in _parse_json_list(metadata.get("block_ids")):
        if item and item not in block_ids:
            block_ids.append(item)

    chunk = _safe_int(metadata.get("chunk"))
    manifest_entry = _find_manifest_entry(sidecar, chunk)
    if isinstance(manifest_entry, dict):
        for item in _parse_json_list(manifest_entry.get("block_ids")):
            if item and item not in block_ids:
                block_ids.append(item)

    return block_ids


def resolve_block_id(metadata: dict[str, Any], sidecar: dict[str, Any] | None = None) -> str | None:
    block_ids = _metadata_block_ids(metadata, sidecar)
    if block_ids:
        return block_ids[0]
    return None


def should_skip_text_sidecar_preview(
    metadata: dict[str, Any],
    sidecar: dict[str, Any] | None = None,
) -> bool:
    if _is_truthy(metadata.get("ocr_override")):
        return True
    block_ids = _metadata_block_ids(metadata, sidecar)
    return any(_OCR_BLOCK_SENTINEL_RE.search(block_id) for block_id in block_ids)


def extract_snippet_window(text: str, query: str | None, window_chars: int = 220) -> str:
    normalized = _normalize_ws(text)
    if not normalized:
        return ""
    if not query or not query.strip():
        return normalized[: window_chars * 2]
    query_l = query.lower().strip()
    text_l = normalized.lower()
    idx = text_l.find(query_l)
    if idx < 0:
        return normalized[: window_chars * 2]
    start = max(0, idx - window_chars)
    end = min(len(normalized), idx + len(query_l) + window_chars)
    return normalized[start:end]


def _collect_text_from_blocks(blocks: list[dict[str, Any]], left: int, right: int) -> tuple[str, int]:
    parts: list[str] = []
    visible = 0
    for idx in range(left, right + 1):
        block = blocks[idx]
        if str(block.get("kind") or "") == "image":
            continue
        text = _normalize_ws(str(block.get("text") or ""))
        if not text:
            continue
        parts.append(text)
        visible += _visible_chars(text)
    return "\n\n".join(parts).strip(), visible


def build_text_preview_from_sidecar(
    sidecar: dict[str, Any] | None,
    metadata: dict[str, Any],
    *,
    query: str | None = None,
    window_chars: int = 220,
    target_chars: int = 900,
) -> str:
    if not sidecar:
        return ""
    if should_skip_text_sidecar_preview(metadata, sidecar):
        return ""

    chunk = _safe_int(metadata.get("chunk"))
    manifest_entry = _find_manifest_entry(sidecar, chunk)
    page = _safe_int(metadata.get("page"))
    if isinstance(manifest_entry, dict):
        page = _safe_int(manifest_entry.get("page")) or page

    ordered_blocks = _find_page_blocks(sidecar, page)
    if not ordered_blocks:
        return ""

    block_ids = _metadata_block_ids(metadata, sidecar)
    positions: list[int] = []
    if block_ids:
        target_ids = set(block_ids)
        for idx, block in enumerate(ordered_blocks):
            if str(block.get("block_id") or "") in target_ids:
                positions.append(idx)

    if positions:
        left = min(positions)
        right = max(positions)
        min_visible = max(220, int(target_chars * 0.4))
        passage, visible = _collect_text_from_blocks(ordered_blocks, left, right)
        while visible < min_visible and (left > 0 or right < len(ordered_blocks) - 1):
            if left > 0:
                left -= 1
            if right < len(ordered_blocks) - 1:
                right += 1
            passage, visible = _collect_text_from_blocks(ordered_blocks, left, right)
            if right - left > 16:
                break
    else:
        passage, _ = _collect_text_from_blocks(ordered_blocks, 0, len(ordered_blocks) - 1)

    if not passage:
        return ""
    return extract_snippet_window(passage, query, window_chars=window_chars)


def _nearest_neighbor_text(ordered_blocks: list[dict[str, Any]], center_idx: int, step: int) -> str:
    idx = center_idx + step
    while 0 <= idx < len(ordered_blocks):
        block = ordered_blocks[idx]
        if str(block.get("kind") or "") != "image":
            text = _normalize_ws(str(block.get("text") or ""))
            if text:
                return text
        idx += step
    return ""


def _truncate_soft(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 24:
        return text[:max_chars]
    return f"{text[: max_chars - 16].rstrip()}\n[... truncated]"


def build_image_preview_from_sidecar(
    sidecar: dict[str, Any] | None,
    metadata: dict[str, Any],
    *,
    target_chars: int = 420,
) -> str:
    if not sidecar:
        return ""

    chunk = _safe_int(metadata.get("chunk"))
    manifest_entry = _find_manifest_entry(sidecar, chunk)
    page = _safe_int(metadata.get("page"))
    if isinstance(manifest_entry, dict):
        page = _safe_int(manifest_entry.get("page")) or page

    ordered_blocks = _find_page_blocks(sidecar, page)
    if not ordered_blocks:
        return ""

    block_ids = _metadata_block_ids(metadata, sidecar)
    target_id_set = set(block_ids)
    target_idx: int | None = None
    for idx, block in enumerate(ordered_blocks):
        if str(block.get("kind") or "") != "image":
            continue
        if target_id_set and str(block.get("block_id") or "") not in target_id_set:
            continue
        target_idx = idx
        break

    if target_idx is None and target_id_set:
        for idx, block in enumerate(ordered_blocks):
            if str(block.get("block_id") or "") in target_id_set:
                target_idx = idx
                break
    if target_idx is None:
        return ""

    target_block = ordered_blocks[target_idx]
    caption = _normalize_ws(str(target_block.get("caption_text") or metadata.get("caption") or ""))
    nearby = _normalize_ws(str(target_block.get("nearby_text") or ""))
    if not nearby:
        prev_text = _nearest_neighbor_text(ordered_blocks, target_idx, -1)
        next_text = _nearest_neighbor_text(ordered_blocks, target_idx, 1)
        nearby_parts = []
        if prev_text:
            nearby_parts.append(prev_text[:220])
        if next_text and next_text != prev_text:
            nearby_parts.append(next_text[:220])
        nearby = "\n".join(nearby_parts).strip()

    lines: list[str] = []
    if page is not None:
        lines.append(f"页码: {page}")
    if caption:
        lines.append(f"图注: {caption}")
    if nearby:
        lines.append(f"邻近正文: {nearby}")

    if not lines:
        return ""
    return _truncate_soft("\n".join(lines), max(180, int(target_chars)))


def sanitize_image_placeholder_text(text: str) -> str:
    lines_out: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _IMG_PLACEHOLDER_RE.match(line):
            continue
        if line.startswith("邻近文字:"):
            line = line.split(":", 1)[1].strip()
        elif line.startswith("图片OCR:"):
            line = line.split(":", 1)[1].strip()
        if line:
            lines_out.append(line)
    return _normalize_ws("\n".join(lines_out))
