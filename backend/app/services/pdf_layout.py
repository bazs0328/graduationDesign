from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

_CAPTION_RE = re.compile(r"^(图|表|Figure|Fig\.?|Table)\s*([0-9A-Za-z一二三四五六七八九十]+)?")


@dataclass
class ExtractedBlock:
    block_id: str
    kind: str
    page: int
    bbox: list[float]
    text: str | None = None
    order_index: int = 0


@dataclass
class PageLayoutResult:
    page: int
    text_blocks: list[ExtractedBlock] = field(default_factory=list)
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


def extract_pdf_layout(
    file_path: str,
    *,
    user_id: str | None = None,  # noqa: ARG001
    kb_id: str | None = None,  # noqa: ARG001
    doc_id: str | None = None,  # noqa: ARG001
) -> PdfLayoutExtractionResult:
    try:
        import fitz  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("PDF layout parser dependency missing: install PyMuPDF.") from exc

    doc = fitz.open(file_path)
    try:
        page_results: list[PageLayoutResult] = []
        all_blocks: list[ExtractedBlock] = []
        page_texts: list[str] = []

        for page_index in range(doc.page_count):
            page_num = page_index + 1
            page = doc.load_page(page_index)
            page_rect = page.rect
            page_dict = page.get_text("dict")
            raw_blocks = page_dict.get("blocks") if isinstance(page_dict, dict) else []

            text_blocks: list[ExtractedBlock] = []
            for raw_block in raw_blocks or []:
                if not isinstance(raw_block, dict):
                    continue
                if raw_block.get("type") != 0:
                    continue
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
                        bbox=_safe_bbox(raw_block.get("bbox")),
                        text=block_text,
                    )
                )

            ordered_blocks = _sort_blocks_reading_order(text_blocks, float(page_rect.width))
            page_layout = PageLayoutResult(
                page=page_num,
                text_blocks=text_blocks,
                ordered_blocks=ordered_blocks,
            )
            page_results.append(page_layout)

            page_text_parts = [b.text for b in ordered_blocks if b.text]
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
