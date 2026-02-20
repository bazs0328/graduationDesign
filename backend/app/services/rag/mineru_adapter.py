from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
from time import perf_counter
from typing import Any

from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings

_WEIRD_TOKEN_RE = re.compile(r"\b[a-z]{1,3}[A-Z][a-zA-Z]{0,6}\b")
_NON_PRINTABLE_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


@dataclass(slots=True)
class MinerUParseOutput:
    content_list: list[dict[str, Any]]
    markdown_text: str
    parser_engine: str
    timing_ms: dict[str, float]
    raw_stats: dict[str, Any]


@dataclass(slots=True)
class CanonicalContentBundle:
    full_text: str
    page_texts: list[str]
    chunk_docs: list[LCDocument]
    assets: list[dict[str, Any]]
    asset_stats: dict[str, Any]
    quality_score: float


class MinerUAdapter:
    parser_engine = "mineru"

    @staticmethod
    @lru_cache(maxsize=1)
    def _cached_installation_check() -> bool:
        if not settings.raganything_enabled:
            return False
        if not shutil.which("mineru"):
            return False
        try:
            from raganything.parser import MineruParser  # type: ignore

            parser = MineruParser()
            return bool(parser.check_installation())
        except Exception:
            return False

    def is_available(self) -> bool:
        return self._cached_installation_check()

    @staticmethod
    def _normalize_mode(mode: str | None) -> str:
        normalized = (mode or "auto").strip().lower()
        if normalized == "parser_auto":
            normalized = "auto"
        if normalized == "force_ocr":
            return "ocr"
        if normalized == "text_layer":
            return "txt"
        return "auto"

    @staticmethod
    def _strip_text(text: str) -> str:
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        text = _NON_PRINTABLE_RE.sub(" ", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def parse_pdf(
        self,
        file_path: str,
        output_dir: str,
        mode: str,
        parser_backend: str | None,
        lang: str | None,
        device: str | None,
        source: str | None,
    ) -> MinerUParseOutput:
        if not self.is_available():
            raise RuntimeError("MinerU parser is unavailable")

        started = perf_counter()
        parse_method = self._normalize_mode(mode)
        kwargs: dict[str, Any] = {}
        if parser_backend:
            kwargs["backend"] = parser_backend
        if device:
            kwargs["device"] = device
        if source:
            kwargs["source"] = source

        from raganything.parser import MineruParser  # type: ignore

        parser = MineruParser()
        content_list = parser.parse_pdf(
            pdf_path=Path(file_path),
            output_dir=output_dir,
            method=parse_method,
            lang=lang,
            **kwargs,
        )
        elapsed = (perf_counter() - started) * 1000

        normalized_content = [item for item in (content_list or []) if isinstance(item, dict)]
        markdown_text = self._content_to_markdown(normalized_content)
        by_type: dict[str, int] = {}
        for item in normalized_content:
            key = str(item.get("type") or "unknown").strip().lower()
            by_type[key] = by_type.get(key, 0) + 1

        return MinerUParseOutput(
            content_list=normalized_content,
            markdown_text=markdown_text,
            parser_engine=self.parser_engine,
            timing_ms={"parse": round(elapsed, 2)},
            raw_stats={
                "item_count": len(normalized_content),
                "by_type": by_type,
            },
        )

    @classmethod
    def _content_to_markdown(cls, content_list: list[dict[str, Any]]) -> str:
        chunks: list[str] = []
        for item in content_list:
            ctype = str(item.get("type") or "text").strip().lower()
            if ctype == "text":
                text = cls._strip_text(cls._as_text(item.get("text")))
                if text:
                    chunks.append(text)
                continue
            caption = cls._normalize_caption(
                item.get("image_caption")
                if ctype == "image"
                else item.get("table_caption")
                if ctype == "table"
                else item.get("caption")
            )
            body = cls._normalize_modal_body(item, ctype)
            block_lines = [f"[{ctype}]"]
            if caption:
                block_lines.append(caption)
            if body:
                block_lines.append(body)
            block_text = cls._strip_text("\n".join(line for line in block_lines if line))
            if block_text:
                chunks.append(block_text)
        return cls._strip_text("\n\n".join(chunks))

    @staticmethod
    def _as_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(str(item) for item in value if item is not None)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @classmethod
    def _normalize_caption(cls, value: Any) -> str:
        text = cls._as_text(value)
        text = cls._strip_text(text)
        return text[:400].strip()

    @classmethod
    def _normalize_modal_body(cls, item: dict[str, Any], ctype: str) -> str:
        if ctype == "table":
            body = item.get("table_body")
            return cls._strip_text(cls._as_text(body))
        if ctype == "equation":
            primary = item.get("latex") or item.get("text")
            return cls._strip_text(cls._as_text(primary))
        if ctype == "image":
            return cls._strip_text(cls._as_text(item.get("text")))
        return cls._strip_text(cls._as_text(item.get("text")))

    @staticmethod
    def _safe_page(page_idx: Any) -> int:
        try:
            return max(1, int(page_idx) + 1)
        except Exception:
            return 1

    @staticmethod
    def _asset_type(raw_type: str) -> str | None:
        value = (raw_type or "").strip().lower()
        if value in {"image", "picture"}:
            return "image"
        if value in {"table"}:
            return "table"
        if value in {"equation", "formula"}:
            return "equation"
        return None

    @staticmethod
    def _pick_asset_source(item: dict[str, Any], asset_type: str) -> str | None:
        candidates: list[Any] = []
        if asset_type == "image":
            candidates.extend([item.get("img_path"), item.get("image_path"), item.get("path")])
        elif asset_type == "table":
            candidates.extend([item.get("table_img_path"), item.get("img_path"), item.get("image_path")])
        elif asset_type == "equation":
            candidates.extend([item.get("equation_img_path"), item.get("img_path"), item.get("image_path")])
        for value in candidates:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _compact_metadata(item: dict[str, Any]) -> dict[str, Any]:
        keep_keys = {
            "type",
            "page_idx",
            "img_path",
            "table_img_path",
            "equation_img_path",
            "image_caption",
            "table_caption",
            "table_footnote",
            "image_footnote",
            "table_body",
            "latex",
            "text",
        }
        compact: dict[str, Any] = {}
        for key in keep_keys:
            if key in item:
                compact[key] = item.get(key)
        return compact

    @classmethod
    def _quality_score(cls, full_text: str, text_blocks: int, modal_blocks: int) -> float:
        text = full_text or ""
        score = 100.0
        alpha_tokens = re.findall(r"[A-Za-z]+", text)
        weird_tokens = _WEIRD_TOKEN_RE.findall(text)
        weird_ratio = len(weird_tokens) / max(1, len(alpha_tokens))
        if weird_ratio >= 0.2:
            score -= min(45.0, weird_ratio * 90.0)
        if len(text) < max(200, settings.ocr_min_text_length):
            score -= 25.0
        if text_blocks <= 0:
            score -= 20.0
        if modal_blocks > 0 and text_blocks <= 0:
            score -= 10.0
        return round(max(0.0, min(100.0, score)), 2)

    def normalize_content_list(
        self,
        *,
        content_list: list[dict[str, Any]],
        markdown_text: str,
        doc_id: str,
        kb_id: str,
        filename: str,
        parser_provider: str,
        extract_method: str,
    ) -> CanonicalContentBundle:
        page_fragments: dict[int, list[str]] = {}
        base_docs: list[LCDocument] = []
        assets: list[dict[str, Any]] = []
        by_type: dict[str, int] = {"image": 0, "table": 0, "equation": 0}
        text_blocks = 0
        modal_blocks = 0
        asset_index = 0

        for item in content_list:
            raw_type = str(item.get("type") or "text").strip().lower()
            page = self._safe_page(item.get("page_idx"))
            asset_type = self._asset_type(raw_type)
            metadata_common = {
                "doc_id": doc_id,
                "kb_id": kb_id,
                "source": filename,
                "page": page,
                "parser_provider": parser_provider,
                "extract_method": extract_method,
            }

            if asset_type is None:
                text = self._strip_text(self._as_text(item.get("text")))
                if not text:
                    continue
                text_blocks += 1
                page_fragments.setdefault(page, []).append(text)
                base_docs.append(
                    LCDocument(
                        page_content=text,
                        metadata={
                            **metadata_common,
                            "modality": "text",
                            "asset_id": None,
                            "asset_caption": None,
                        },
                    )
                )
                continue

            modal_blocks += 1
            by_type[asset_type] = by_type.get(asset_type, 0) + 1
            asset_index += 1
            asset_id = f"{doc_id}-asset-{asset_index}"
            caption = self._normalize_caption(
                item.get("image_caption")
                if asset_type == "image"
                else item.get("table_caption")
                if asset_type == "table"
                else item.get("caption")
            )
            ocr_text = self._normalize_modal_body(item, asset_type)
            source_path = self._pick_asset_source(item, asset_type)
            assets.append(
                {
                    "id": asset_id,
                    "page": page,
                    "asset_type": asset_type,
                    "source_path": source_path,
                    "caption_text": caption or None,
                    "ocr_text": ocr_text or None,
                    "quality_score": None,
                    "metadata": self._compact_metadata(item),
                }
            )

            text_parts = [f"[{asset_type}]"]
            if caption:
                text_parts.append(caption)
            if ocr_text:
                text_parts.append(ocr_text)
            normalized_text = self._strip_text("\n".join(text_parts))
            if not normalized_text:
                continue
            page_fragments.setdefault(page, []).append(normalized_text)
            base_docs.append(
                LCDocument(
                    page_content=normalized_text,
                    metadata={
                        **metadata_common,
                        "modality": asset_type,
                        "asset_id": asset_id,
                        "asset_caption": caption or None,
                    },
                )
            )

        if not base_docs and markdown_text.strip():
            fallback_text = self._strip_text(markdown_text)
            if fallback_text:
                base_docs.append(
                    LCDocument(
                        page_content=fallback_text,
                        metadata={
                            "doc_id": doc_id,
                            "kb_id": kb_id,
                            "source": filename,
                            "page": 1,
                            "parser_provider": parser_provider,
                            "extract_method": extract_method,
                            "modality": "text",
                            "asset_id": None,
                            "asset_caption": None,
                        },
                    )
                )
                page_fragments.setdefault(1, []).append(fallback_text)
                text_blocks += 1

        chunk_size = max(200, settings.chunk_size)
        chunk_overlap = max(0, min(settings.chunk_overlap, chunk_size - 1))
        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunk_docs = splitter.split_documents(base_docs) if base_docs else []
        for idx, doc in enumerate(chunk_docs, start=1):
            doc.metadata.setdefault("chunk", idx)

        max_page = max(page_fragments.keys(), default=1)
        page_texts = []
        for page in range(1, max_page + 1):
            content = self._strip_text("\n\n".join(page_fragments.get(page, [])))
            page_texts.append(content)
        full_text = self._strip_text("\n\n".join(text for text in page_texts if text))
        if not full_text:
            full_text = self._strip_text(markdown_text)

        asset_total = sum(by_type.values())
        asset_stats = {
            "total": asset_total,
            "by_type": {k: v for k, v in by_type.items() if v > 0},
            "text_blocks": text_blocks,
            "modal_blocks": modal_blocks,
        }
        quality_score = self._quality_score(full_text, text_blocks=text_blocks, modal_blocks=modal_blocks)

        return CanonicalContentBundle(
            full_text=full_text,
            page_texts=page_texts,
            chunk_docs=chunk_docs,
            assets=assets,
            asset_stats=asset_stats,
            quality_score=quality_score,
        )
