from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from app.core.config import settings
from app.core.paths import ensure_kb_dirs, kb_base_dir

logger = logging.getLogger(__name__)

_CAPTION_RE = re.compile(r"^(图|表|Figure|Fig\.?|Table)\s*([0-9A-Za-z一二三四五六七八九十]+)?")


@dataclass
class ExtractedBlock:
    block_id: str
    kind: str
    page: int
    bbox: list[float]
    text: str | None = None
    asset_path: str | None = None
    caption_text: str | None = None
    nearby_text: str | None = None
    ocr_text: str | None = None
    order_index: int = 0


@dataclass
class PageLayoutResult:
    page: int
    text_blocks: list[ExtractedBlock] = field(default_factory=list)
    image_blocks: list[ExtractedBlock] = field(default_factory=list)
    ordered_blocks: list[ExtractedBlock] = field(default_factory=list)
    ocr_override_text: str | None = None
    text_quality_score: float | None = None


@dataclass
class PdfLayoutExtractionResult:
    text: str
    page_count: int
    pages: list[str]
    blocks: list[ExtractedBlock] = field(default_factory=list)
    page_blocks: list[PageLayoutResult] = field(default_factory=list)
    sidecar: dict[str, Any] | None = None


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_caption_text(text: str) -> bool:
    return bool(_CAPTION_RE.match((text or "").strip()))


def _safe_bbox(raw_bbox: Any) -> list[float]:
    if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
        try:
            return [float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3])]
        except Exception:  # noqa: BLE001
            pass
    return [0.0, 0.0, 0.0, 0.0]


def _bbox_area(bbox: list[float]) -> float:
    x0, y0, x1, y1 = bbox
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _block_sort_key(block: ExtractedBlock) -> tuple[float, float]:
    x0, y0, x1, y1 = block.bbox
    return ((y0 + y1) / 2.0, x0)


def _cluster_columns(blocks: list[ExtractedBlock], page_width: float) -> list[list[ExtractedBlock]]:
    if len(blocks) <= 1:
        return [blocks[:]] if blocks else []
    threshold = max(40.0, page_width * 0.18)
    sorted_by_x = sorted(blocks, key=lambda b: b.bbox[0])
    columns: list[list[ExtractedBlock]] = []
    centers: list[float] = []
    for block in sorted_by_x:
        x0, _, x1, _ = block.bbox
        cx = (x0 + x1) / 2.0
        target_idx: int | None = None
        for idx, center in enumerate(centers):
            if abs(cx - center) <= threshold:
                target_idx = idx
                break
        if target_idx is None:
            columns.append([block])
            centers.append(cx)
            continue
        columns[target_idx].append(block)
        centers[target_idx] = (centers[target_idx] * (len(columns[target_idx]) - 1) + cx) / len(columns[target_idx])
    columns = [sorted(col, key=_block_sort_key) for col in columns if col]
    columns.sort(key=lambda col: min(item.bbox[0] for item in col))
    return columns


def _sort_blocks_reading_order(blocks: list[ExtractedBlock], page_width: float) -> list[ExtractedBlock]:
    if not blocks:
        return []
    columns = _cluster_columns(blocks, page_width)
    ordered: list[ExtractedBlock] = []
    for col in columns:
        ordered.extend(col)
    if not ordered:
        ordered = sorted(blocks, key=_block_sort_key)
    for idx, block in enumerate(ordered, start=1):
        block.order_index = idx
    return ordered


def _join_text_block_lines(block: dict[str, Any]) -> str:
    lines_out: list[str] = []
    for line in block.get("lines") or []:
        parts: list[str] = []
        for span in line.get("spans") or []:
            text = str(span.get("text") or "")
            if text:
                parts.append(text)
        line_text = "".join(parts)
        if line_text:
            lines_out.append(line_text)
    return _normalize_text("\n".join(lines_out))


def _image_asset_dir(user_id: str, kb_id: str, doc_id: str) -> str:
    ensure_kb_dirs(user_id, kb_id)
    path = os.path.join(kb_base_dir(user_id, kb_id), "images", doc_id)
    os.makedirs(path, exist_ok=True)
    return path


def _crop_image_block(page: Any, bbox: list[float], save_path: str) -> bytes | None:
    try:
        import fitz  # type: ignore
    except Exception:
        return None
    try:
        rect = fitz.Rect(*bbox)
        if rect.width <= 1 or rect.height <= 1:
            return None
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
        png_bytes = pix.tobytes("png")
        with open(save_path, "wb") as f:
            f.write(png_bytes)
        return png_bytes
    except Exception:  # noqa: BLE001
        logger.exception("Failed to crop image block: %s", save_path)
        return None


def _sanitize_file_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "")
    return safe.strip("_") or "doc"


def _attach_image_text_fields(page_layout: PageLayoutResult) -> None:
    ordered = page_layout.ordered_blocks
    for idx, block in enumerate(ordered):
        if block.kind != "image":
            continue
        prev_text = None
        next_text = None
        for j in range(idx - 1, -1, -1):
            cand = ordered[j]
            if cand.kind == "image":
                continue
            if cand.text:
                prev_text = cand.text
                break
        for j in range(idx + 1, len(ordered)):
            cand = ordered[j]
            if cand.kind == "image":
                continue
            if cand.text:
                next_text = cand.text
                break
        if prev_text and _is_caption_text(prev_text):
            block.caption_text = prev_text[:300]
        elif next_text and _is_caption_text(next_text):
            block.caption_text = next_text[:300]
        nearby_parts = []
        if prev_text and prev_text != block.caption_text:
            nearby_parts.append(prev_text[:240])
        if next_text and next_text != block.caption_text:
            nearby_parts.append(next_text[:240])
        if nearby_parts:
            block.nearby_text = "\n".join(nearby_parts[:2])


def extract_pdf_layout(
    file_path: str,
    *,
    user_id: str | None = None,
    kb_id: str | None = None,
    doc_id: str | None = None,
) -> PdfLayoutExtractionResult:
    try:
        import fitz  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("PDF layout parser dependency missing: install PyMuPDF.") from exc

    extract_images = bool(getattr(settings, "pdf_extract_images", True))
    min_area_ratio = max(0.0, float(getattr(settings, "pdf_image_min_area_ratio", 0.01) or 0.01))
    max_images_per_page = max(0, int(getattr(settings, "pdf_image_max_per_page", 12) or 12))

    doc = fitz.open(file_path)
    try:
        page_results: list[PageLayoutResult] = []
        all_blocks: list[ExtractedBlock] = []
        page_texts: list[str] = []
        image_hashes_seen: set[str] = set()
        asset_dir = None
        if extract_images and user_id and kb_id and doc_id:
            asset_dir = _image_asset_dir(user_id, kb_id, doc_id)

        for page_index in range(doc.page_count):
            page_num = page_index + 1
            page = doc.load_page(page_index)
            page_rect = page.rect
            page_area = max(1.0, float(page_rect.width) * float(page_rect.height))
            page_dict = page.get_text("dict")
            raw_blocks = page_dict.get("blocks") if isinstance(page_dict, dict) else []

            text_blocks: list[ExtractedBlock] = []
            image_blocks: list[ExtractedBlock] = []
            image_count = 0

            for raw_block in raw_blocks or []:
                if not isinstance(raw_block, dict):
                    continue
                block_type = raw_block.get("type")
                bbox = _safe_bbox(raw_block.get("bbox"))
                if block_type == 0:
                    block_text = _join_text_block_lines(raw_block)
                    if not block_text:
                        continue
                    kind = "caption" if _is_caption_text(block_text) else "text"
                    block_id = f"p{page_num}:t{len(text_blocks)+1}"
                    text_blocks.append(
                        ExtractedBlock(
                            block_id=block_id,
                            kind=kind,
                            page=page_num,
                            bbox=bbox,
                            text=block_text,
                        )
                    )
                    continue

                if block_type != 1 or not extract_images:
                    continue
                if max_images_per_page and image_count >= max_images_per_page:
                    continue
                area_ratio = _bbox_area(bbox) / page_area
                if area_ratio < min_area_ratio:
                    continue

                asset_path: str | None = None
                if asset_dir:
                    safe_doc_id = _sanitize_file_component(doc_id or "doc")
                    filename = f"{safe_doc_id}_p{page_num:04d}_img{image_count+1:03d}.png"
                    candidate_path = os.path.join(asset_dir, filename)
                    png_bytes = _crop_image_block(page, bbox, candidate_path)
                    if png_bytes:
                        digest = hashlib.sha1(png_bytes).hexdigest()
                        if digest in image_hashes_seen:
                            try:
                                os.remove(candidate_path)
                            except OSError:
                                pass
                            continue
                        image_hashes_seen.add(digest)
                        asset_path = candidate_path
                    else:
                        try:
                            if os.path.exists(candidate_path):
                                os.remove(candidate_path)
                        except OSError:
                            pass

                image_count += 1
                block_id = f"p{page_num}:i{len(image_blocks)+1}"
                image_blocks.append(
                    ExtractedBlock(
                        block_id=block_id,
                        kind="image",
                        page=page_num,
                        bbox=bbox,
                        asset_path=asset_path,
                    )
                )

            ordered_blocks = _sort_blocks_reading_order([*text_blocks, *image_blocks], float(page_rect.width))
            page_layout = PageLayoutResult(
                page=page_num,
                text_blocks=text_blocks,
                image_blocks=image_blocks,
                ordered_blocks=ordered_blocks,
            )
            _attach_image_text_fields(page_layout)
            page_results.append(page_layout)

            page_text_parts = [b.text for b in ordered_blocks if b.kind != "image" and b.text]
            page_text = _normalize_text("\n\n".join(page_text_parts))
            page_texts.append(page_text)
            all_blocks.extend(ordered_blocks)

        combined_text = "\n\n".join([p for p in page_texts if p])
        sidecar = {
            "version": 1,
            "parser": "layout",
            "engine": "pymupdf",
            "page_count": doc.page_count,
            "pages": [
                {
                    "page": p.page,
                    "ordered_blocks": [asdict(block) for block in p.ordered_blocks],
                }
                for p in page_results
            ],
        }
        return PdfLayoutExtractionResult(
            text=combined_text,
            page_count=doc.page_count,
            pages=page_texts,
            blocks=all_blocks,
            page_blocks=page_results,
            sidecar=sidecar,
        )
    finally:
        doc.close()
