from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.index_text_cleaning import clean_text_for_indexing_with_stats
from app.services.text_noise_guard import clean_fragment
from app.services.text_extraction import ExtractionResult


CHINESE_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
logger = logging.getLogger(__name__)


@dataclass
class ChunkBuildResult:
    text_docs: list[LCDocument]
    all_docs: list[LCDocument]
    manifest: list[dict[str, Any]]


@dataclass
class _BufferedTextSegment:
    page: int | None
    pieces: list[str]
    block_ids: list[str]
    order_hint: int = 0
    meta_extra: dict[str, Any] = field(default_factory=dict)

    def text(self) -> str:
        return "\n\n".join([p for p in self.pieces if p]).strip()


def _splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=CHINESE_SEPARATORS,
        keep_separator=True,
    )


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return "[]" if isinstance(value, list) else "{}"


def _doc_base_metadata(doc_id: str, kb_id: str, filename: str, page: int | None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "doc_id": doc_id,
        "kb_id": kb_id,
        "source": filename,
    }
    if page is not None:
        data["page"] = page
    return data


def _prepare_index_text(
    segment_text: str,
    *,
    meta: dict[str, Any],
    enable_cleanup: bool,
    format_hint: str | None,
) -> str:
    text = (segment_text or "").strip()
    if not text:
        return ""
    if not enable_cleanup:
        return text
    if not bool(getattr(settings, "index_text_cleanup_enabled", True)):
        return text

    resolved_format = (format_hint or "").strip().lower()
    if resolved_format == ".pdf":
        mode = str(getattr(settings, "index_text_cleanup_mode", "conservative") or "conservative")
        cleaned, stats = clean_text_for_indexing_with_stats(text, mode=mode)
        if cleaned != text:
            logger.info(
                "Index text cleanup applied scope=pdf doc_id=%s page=%s before=%s after=%s pairs_removed=%s noise_lines_removed=%s short_line_groups_merged=%s",
                meta.get("doc_id"),
                meta.get("page"),
                stats.get("before_len"),
                stats.get("after_len"),
                stats.get("pairs_removed"),
                stats.get("noise_lines_removed"),
                stats.get("short_line_groups_merged"),
            )
        return cleaned.strip()

    non_pdf_mode = str(
        getattr(settings, "index_text_cleanup_non_pdf_mode", "structure_preserving")
        or "structure_preserving"
    )
    cleaned = clean_fragment(text, mode=non_pdf_mode, format_hint=resolved_format or None)
    if cleaned != text:
        logger.info(
            "Index text cleanup applied scope=non_pdf doc_id=%s page=%s before=%s after=%s mode=%s format=%s",
            meta.get("doc_id"),
            meta.get("page"),
            len(text),
            len(cleaned),
            non_pdf_mode,
            resolved_format or "unknown",
        )
    return cleaned.strip()


def _make_text_docs_from_segment(
    segment_text: str,
    *,
    meta: dict[str, Any],
    block_ids: list[str],
    splitter: RecursiveCharacterTextSplitter,
    order_hint: int | None = None,
    enable_cleanup: bool = False,
    format_hint: str | None = None,
) -> list[LCDocument]:
    text = _prepare_index_text(
        segment_text,
        meta=meta,
        enable_cleanup=enable_cleanup,
        format_hint=format_hint,
    )
    if not text:
        return []
    docs = splitter.create_documents([text])
    out: list[LCDocument] = []
    for idx, d in enumerate(docs, start=1):
        md = dict(meta)
        md["modality"] = "text"
        md["chunk_kind"] = "text"
        md["block_ids"] = _safe_json(block_ids)
        if order_hint is not None:
            base = int(order_hint)
            md["_order_hint"] = base * 1000 + idx
        out.append(LCDocument(page_content=d.page_content, metadata=md))
    return out


def _flush_text_segment(
    current: _BufferedTextSegment | None,
    *,
    out: list[LCDocument],
    doc_id: str,
    kb_id: str,
    filename: str,
    splitter: RecursiveCharacterTextSplitter,
    enable_cleanup: bool,
    format_hint: str | None = None,
) -> _BufferedTextSegment | None:
    if current is None:
        return None
    text = current.text()
    if not text:
        return None
    meta = _doc_base_metadata(doc_id, kb_id, filename, current.page)
    if current.meta_extra:
        meta.update(current.meta_extra)
    out.extend(
        _make_text_docs_from_segment(
            text,
            meta=meta,
            block_ids=current.block_ids,
            splitter=splitter,
            order_hint=current.order_hint,
            enable_cleanup=enable_cleanup,
            format_hint=format_hint,
        )
    )
    return None


def build_chunked_documents(
    *,
    extraction: ExtractionResult,
    suffix: str,
    doc_id: str,
    user_id: str,  # noqa: ARG001 (reserved for future local path strategies)
    kb_id: str,
    filename: str,
    chunk_size: int,
    chunk_overlap: int,
) -> ChunkBuildResult:
    splitter = _splitter(chunk_size, chunk_overlap)

    text_docs: list[LCDocument] = []

    if suffix == ".pdf" and getattr(extraction, "page_blocks", None):
        for page_layout in extraction.page_blocks or []:
            override_text = (getattr(page_layout, "ocr_override_text", None) or "").strip()
            page_quality_score = getattr(page_layout, "text_quality_score", None)
            if override_text:
                meta = _doc_base_metadata(doc_id, kb_id, filename, getattr(page_layout, "page", None))
                if page_quality_score is not None:
                    meta["page_text_quality_score"] = float(page_quality_score)
                meta["ocr_override"] = True
                text_docs.extend(
                    _make_text_docs_from_segment(
                        override_text,
                        meta=meta,
                        block_ids=[f"p{getattr(page_layout, 'page', 0)}:ocr"],
                        splitter=splitter,
                        order_hint=0,
                        enable_cleanup=True,
                        format_hint=suffix,
                    )
                )
            else:
                buffer: _BufferedTextSegment | None = None
                for block in getattr(page_layout, "ordered_blocks", []) or []:
                    text = (getattr(block, "text", None) or "").strip()
                    if not text:
                        continue
                    if buffer is None:
                        buffer = _BufferedTextSegment(
                            page=getattr(block, "page", None),
                            pieces=[],
                            block_ids=[],
                            order_hint=int(getattr(block, "order_index", 0) or 0),
                            meta_extra={
                                **(
                                    {"page_text_quality_score": float(page_quality_score)}
                                    if page_quality_score is not None
                                    else {}
                                ),
                                "ocr_override": False,
                            },
                        )
                    buffer.pieces.append(text)
                    block_id = getattr(block, "block_id", None)
                    if block_id:
                        buffer.block_ids.append(block_id)
                    if len("\n\n".join(buffer.pieces)) >= chunk_size:
                        buffer = _flush_text_segment(
                            buffer,
                            out=text_docs,
                            doc_id=doc_id,
                            kb_id=kb_id,
                            filename=filename,
                            splitter=splitter,
                            enable_cleanup=True,
                            format_hint=suffix,
                        )
                buffer = _flush_text_segment(
                    buffer,
                    out=text_docs,
                    doc_id=doc_id,
                    kb_id=kb_id,
                    filename=filename,
                    splitter=splitter,
                    enable_cleanup=True,
                    format_hint=suffix,
                )
    else:
        if suffix in {".pdf", ".pptx"}:
            for page_num, page_text in enumerate(extraction.pages, start=1):
                meta = {
                    "doc_id": doc_id,
                    "kb_id": kb_id,
                    "source": filename,
                    "page": page_num,
                }
                cleaned_page_text = _prepare_index_text(
                    page_text,
                    meta=meta,
                    enable_cleanup=True,
                    format_hint=suffix,
                )
                if not cleaned_page_text:
                    continue
                docs = splitter.create_documents([cleaned_page_text])
                for local_idx, d in enumerate(docs, start=1):
                    text_docs.append(
                        LCDocument(
                            page_content=d.page_content,
                            metadata={
                                **meta,
                                "modality": "text",
                                "chunk_kind": "text",
                                "_order_hint": local_idx,
                            },
                        )
                    )
        else:
            meta = {
                "doc_id": doc_id,
                "kb_id": kb_id,
                "source": filename,
            }
            cleaned_text = _prepare_index_text(
                extraction.text,
                meta=meta,
                enable_cleanup=True,
                format_hint=suffix,
            )
            if not cleaned_text:
                docs = []
            else:
                docs = splitter.create_documents([cleaned_text])
            for local_idx, d in enumerate(docs, start=1):
                text_docs.append(
                    LCDocument(
                        page_content=d.page_content,
                        metadata={
                            **meta,
                            "modality": "text",
                            "chunk_kind": "text",
                            "_order_hint": local_idx,
                        },
                    )
                )

    def _sort_key(doc: LCDocument) -> tuple[int, int, str]:
        meta = doc.metadata or {}
        page_val = meta.get("page")
        try:
            page = int(page_val)
        except (TypeError, ValueError):
            page = 0
        try:
            order_hint = int(meta.get("_order_hint") or 0)
        except (TypeError, ValueError):
            order_hint = 0
        return page, order_hint, doc.page_content[:40]

    text_docs.sort(key=_sort_key)

    manifest: list[dict[str, Any]] = []
    for idx, doc in enumerate(text_docs, start=1):
        doc.metadata.pop("_order_hint", None)
        doc.metadata.setdefault("chunk", idx)
        manifest.append(
            {
                "chunk": idx,
                "page": doc.metadata.get("page"),
                "modality": doc.metadata.get("modality"),
                "chunk_kind": doc.metadata.get("chunk_kind"),
                "block_ids": doc.metadata.get("block_ids"),
            }
        )

    all_docs = list(text_docs)

    return ChunkBuildResult(
        text_docs=text_docs,
        all_docs=all_docs,
        manifest=manifest,
    )
