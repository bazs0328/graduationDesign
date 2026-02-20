from __future__ import annotations

from math import fsum
import re
from time import perf_counter

from app.core.config import settings

from .base import PageDiagnostic, ParseRequest, ParseResult
from .native_pdf_parser import _clean_page, _normalize_text, _page_quality

_IMAGE_PLACEHOLDER_RE = re.compile(r"^\s*<!--\s*image\s*-->\s*$", re.IGNORECASE | re.MULTILINE)
_MARKDOWN_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_WEIRD_TOKEN_RE = re.compile(r"\b[a-z]{1,3}[A-Z][a-zA-Z]{0,5}\b")
_HAN_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_HAN_SPACED_RE = re.compile(r"(?:[\u4e00-\u9fff]\s+){2,}[\u4e00-\u9fff]")


class DoclingParser:
    provider = "docling"

    @staticmethod
    def is_available() -> bool:
        try:
            import docling  # type: ignore  # noqa: F401

            return True
        except Exception:
            return False

    def parse(self, request: ParseRequest) -> ParseResult:
        if not self.is_available():
            raise ImportError("Docling is not installed")

        normalized_mode = self._normalize_mode(request.mode)
        converter, opts_meta = self._build_converter(request, normalized_mode)
        started = perf_counter()
        converted = converter.convert(request.file_path)
        elapsed = (perf_counter() - started) * 1000

        document = getattr(converted, "document", None) or getattr(converted, "doc", None) or converted
        raw_text = _normalize_text(self._export_markdown(document))
        full_text = self._strip_docling_markdown_noise(raw_text)
        pages = self._extract_pages(document, full_text)
        if not pages and full_text:
            pages = [full_text]

        cleaned_pages: list[str] = []
        page_diags: list[PageDiagnostic] = []
        min_len = max(1, int(settings.ocr_min_text_length))
        for idx, page_text in enumerate(pages, start=1):
            normalized_page = self._strip_docling_markdown_noise(page_text)
            score_before, flags_before = _page_quality(normalized_page, min_len)
            cleaned = _clean_page(normalized_page, flags_before)
            score, flags = _page_quality(cleaned, min_len)
            method = "ocr" if normalized_mode == "force_ocr" and opts_meta.get("do_ocr") else "text_layer"
            page_diags.append(
                PageDiagnostic(
                    page_num=idx,
                    char_count=len(cleaned),
                    quality_score=score,
                    flags=flags,
                    method=method,
                )
            )
            cleaned_pages.append(cleaned)

        if cleaned_pages:
            full_text = "\n\n".join([p for p in cleaned_pages if p.strip()])

        quality_values = [diag.quality_score for diag in page_diags]
        quality_avg = round(fsum(quality_values) / max(1, len(quality_values)), 2)
        if normalized_mode == "force_ocr":
            strategy = "force_ocr"
            extract_method = "ocr"
            ocr_pages = [d.page_num for d in page_diags]
        elif normalized_mode == "text_layer":
            strategy = "text_layer_only"
            extract_method = "text_layer"
            ocr_pages = []
        else:
            strategy = "docling_auto"
            extract_method = "hybrid" if opts_meta.get("do_ocr") else "text_layer"
            ocr_pages = []

        text_stats = self._text_stats(full_text)
        raw_placeholder_count = len(_IMAGE_PLACEHOLDER_RE.findall(raw_text or ""))
        text_stats["image_placeholders"] = raw_placeholder_count
        source_pdf_pages = self._safe_pdf_page_count(request.file_path)
        quality_guard_reasons: list[str] = []
        if quality_avg < max(float(settings.ocr_low_quality_score), 55.0):
            quality_guard_reasons.append("low_quality_score")
        if text_stats["weird_token_ratio"] >= 0.35:
            quality_guard_reasons.append("weird_token_ratio")
        if text_stats["non_printable_ratio"] >= 0.02:
            quality_guard_reasons.append("non_printable_ratio")
        if (
            source_pdf_pages
            and source_pdf_pages >= 6
            and len(page_diags) <= 1
            and text_stats["image_placeholders"] > 0
        ):
            quality_guard_reasons.append("collapsed_single_page_output")

        diagnostics = {
            "strategy": strategy,
            "complexity_class": "layout_complex",
            "low_quality_pages": [
                d.page_num for d in page_diags if d.quality_score < float(settings.ocr_low_quality_score)
            ],
            "ocr_pages": ocr_pages,
            "page_scores": [d.to_dict() for d in page_diags],
            "docling_mode": "native_docling",
            "docling_options": opts_meta,
            "docling_stats": {
                **text_stats,
                "source_pdf_pages": source_pdf_pages,
            },
            "quality_guard": {
                "fallback_recommended": bool(quality_guard_reasons),
                "reasons": quality_guard_reasons,
            },
        }
        timing = {
            "extract": round(elapsed, 2),
            "total": round(elapsed, 2),
        }

        return ParseResult(
            text=full_text,
            page_count=len(cleaned_pages),
            pages=cleaned_pages,
            parser_provider=self.provider,
            extract_method=extract_method,
            quality_score=quality_avg,
            diagnostics=diagnostics,
            timing_ms=timing,
        )

    @staticmethod
    def _normalize_mode(mode: str | None) -> str:
        normalized = (mode or "auto").strip().lower()
        if normalized == "parser_auto":
            normalized = "auto"
        if normalized not in {"auto", "force_ocr", "text_layer"}:
            return "auto"
        return normalized

    @staticmethod
    def _strip_docling_markdown_noise(text: str) -> str:
        cleaned = _normalize_text(text)
        cleaned = _IMAGE_PLACEHOLDER_RE.sub("", cleaned)
        cleaned = _MARKDOWN_HEADER_RE.sub("", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _text_stats(text: str) -> dict[str, float | int]:
        text = text or ""
        alpha_tokens = re.findall(r"[A-Za-z]+", text)
        weird_tokens = _WEIRD_TOKEN_RE.findall(text)
        han_chars = _HAN_CHAR_RE.findall(text)
        han_spaced_hits = _HAN_SPACED_RE.findall(text)
        non_printable = sum(1 for ch in text if not ch.isprintable())
        return {
            "char_count": len(text),
            "alpha_tokens": len(alpha_tokens),
            "weird_tokens": len(weird_tokens),
            "weird_token_ratio": round(len(weird_tokens) / max(1, len(alpha_tokens)), 4),
            "han_chars": len(han_chars),
            "han_spaced_hits": len(han_spaced_hits),
            "han_space_ratio": round(len(han_spaced_hits) / max(1, len(han_chars)), 4),
            "non_printable_ratio": round(non_printable / max(1, len(text)), 4),
            "image_placeholders": len(_IMAGE_PLACEHOLDER_RE.findall(text)),
        }

    @staticmethod
    def _safe_pdf_page_count(file_path: str) -> int | None:
        try:
            import pdfplumber

            with pdfplumber.open(file_path) as pdf:
                return len(pdf.pages)
        except Exception:
            return None

    @staticmethod
    def _resolve_ocr_langs(raw_lang: str) -> list[str]:
        langs = [part.strip() for part in (raw_lang or "").replace(",", "+").split("+") if part.strip()]
        return langs or ["eng"]

    @staticmethod
    def _set_langs_if_possible(ocr_options, langs: list[str]) -> None:
        for attr in ("lang", "langs", "languages"):
            if not hasattr(ocr_options, attr):
                continue
            current = getattr(ocr_options, attr)
            try:
                if isinstance(current, str):
                    setattr(ocr_options, attr, "+".join(langs))
                else:
                    setattr(ocr_options, attr, langs)
            except Exception:
                continue
            return

    def _build_converter(self, request: ParseRequest, normalized_mode: str):
        from docling.document_converter import DocumentConverter

        do_ocr = (
            True
            if normalized_mode == "force_ocr"
            else False
            if normalized_mode == "text_layer"
            else bool(settings.ocr_enabled)
        )
        opts_meta = {
            "mode": normalized_mode,
            "do_ocr": do_ocr,
            "force_full_page_ocr": normalized_mode == "force_ocr",
            "ocr_languages": self._resolve_ocr_langs(settings.ocr_language),
            "ocr_enabled_setting": bool(settings.ocr_enabled),
        }

        pdf_pipeline_options = None
        try:
            from docling.datamodel.pipeline_options import PdfPipelineOptions

            pdf_pipeline_options = PdfPipelineOptions()
            pdf_pipeline_options.do_ocr = opts_meta["do_ocr"]

            try:
                from docling.datamodel.pipeline_options import TesseractCliOcrOptions

                ocr_options = TesseractCliOcrOptions(
                    force_full_page_ocr=opts_meta["force_full_page_ocr"]
                )
                self._set_langs_if_possible(ocr_options, opts_meta["ocr_languages"])
                pdf_pipeline_options.ocr_options = ocr_options
            except Exception:
                pass
        except Exception:
            pdf_pipeline_options = None

        if pdf_pipeline_options is None:
            return DocumentConverter(), opts_meta

        try:
            from docling.datamodel.base_models import InputFormat
            from docling.document_converter import PdfFormatOption

            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_pipeline_options)
                }
            )
            return converter, opts_meta
        except Exception:
            return DocumentConverter(), opts_meta

    @staticmethod
    def _export_markdown(document) -> str:
        for fn_name in ("export_to_markdown", "to_markdown", "export_to_text", "to_text"):
            fn = getattr(document, fn_name, None)
            if callable(fn):
                try:
                    value = fn()
                    if isinstance(value, str) and value.strip():
                        return value
                except Exception:
                    continue
        return str(document or "")

    @classmethod
    def _page_to_text(cls, page) -> str:
        for fn_name in ("export_to_markdown", "to_markdown", "export_to_text", "to_text"):
            fn = getattr(page, fn_name, None)
            if callable(fn):
                try:
                    value = fn()
                    if isinstance(value, str):
                        normalized = _normalize_text(value)
                        if normalized:
                            return normalized
                except Exception:
                    continue
        for attr_name in ("text", "markdown", "content"):
            value = getattr(page, attr_name, None)
            if isinstance(value, str):
                normalized = _normalize_text(value)
                if normalized:
                    return normalized
        return ""

    @classmethod
    def _extract_pages(cls, document, full_text: str) -> list[str]:
        pages_obj = getattr(document, "pages", None)
        page_entries: list = []
        if isinstance(pages_obj, dict):
            try:
                page_entries = [pages_obj[k] for k in sorted(pages_obj.keys())]
            except Exception:
                page_entries = list(pages_obj.values())
        elif isinstance(pages_obj, (list, tuple)):
            page_entries = list(pages_obj)
        elif hasattr(pages_obj, "values"):
            try:
                page_entries = list(pages_obj.values())
            except Exception:
                page_entries = []

        pages: list[str] = []
        for page in page_entries:
            page_text = cls._page_to_text(page)
            if page_text:
                pages.append(page_text)

        if pages:
            return pages

        ff_pages = [_normalize_text(part) for part in full_text.split("\f")]
        ff_pages = [part for part in ff_pages if part]
        return ff_pages
