from __future__ import annotations

from math import fsum
from time import perf_counter

from app.core.config import settings

from .base import PageDiagnostic, ParseRequest, ParseResult
from .native_pdf_parser import _normalize_text, _page_quality


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

        converter, opts_meta = self._build_converter(request)
        started = perf_counter()
        converted = converter.convert(request.file_path)
        elapsed = (perf_counter() - started) * 1000

        document = getattr(converted, "document", None) or getattr(converted, "doc", None) or converted
        full_text = _normalize_text(self._export_markdown(document))
        pages = self._extract_pages(document, full_text)
        if not pages and full_text:
            pages = [full_text]

        page_diags: list[PageDiagnostic] = []
        min_len = max(1, int(settings.ocr_min_text_length))
        for idx, page_text in enumerate(pages, start=1):
            score, flags = _page_quality(page_text, min_len)
            method = "ocr" if (request.mode or "").strip().lower() == "force_ocr" else "text_layer"
            page_diags.append(
                PageDiagnostic(
                    page_num=idx,
                    char_count=len(page_text),
                    quality_score=score,
                    flags=flags,
                    method=method,
                )
            )

        quality_values = [diag.quality_score for diag in page_diags]
        quality_avg = round(fsum(quality_values) / max(1, len(quality_values)), 2)
        normalized_mode = (request.mode or "auto").strip().lower()
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
        }
        timing = {
            "extract": round(elapsed, 2),
            "total": round(elapsed, 2),
        }

        return ParseResult(
            text=full_text,
            page_count=len(pages),
            pages=pages,
            parser_provider=self.provider,
            extract_method=extract_method,
            quality_score=quality_avg,
            diagnostics=diagnostics,
            timing_ms=timing,
        )

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

    def _build_converter(self, request: ParseRequest):
        from docling.document_converter import DocumentConverter

        mode = (request.mode or "auto").strip().lower()
        opts_meta = {
            "mode": mode,
            "do_ocr": mode != "text_layer",
            "force_full_page_ocr": mode == "force_ocr",
            "ocr_languages": self._resolve_ocr_langs(settings.ocr_language),
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
