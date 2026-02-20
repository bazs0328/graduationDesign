from __future__ import annotations

from app.core.config import settings

from .base import ParseRequest, ParseResult
from .docling_parser import DoclingParser
from .native_pdf_parser import NativePDFParser
from .text_parser import TextParser


class ParserRouter:
    def __init__(self):
        self._native = NativePDFParser()
        self._text = TextParser()
        self._docling = DoclingParser()

    def _choose_pdf_parser(self, request: ParseRequest) -> str:
        preferred = (request.preferred_parser or "auto").strip().lower()
        parse_policy = (request.parse_policy or "balanced").strip().lower()

        can_use_docling = settings.doc_parser_enable_docling and self._docling.is_available()

        if preferred == "native":
            return "native"
        if preferred == "docling":
            return "docling" if can_use_docling else "native"

        # auto mode: only route to docling for higher complexity with aggressive policy.
        if not can_use_docling:
            return "native"

        if parse_policy == "aggressive":
            preflight = NativePDFParser.quick_preflight(
                request.file_path,
                max(1, settings.ocr_min_text_length),
            )
            complexity = preflight.get("complexity_class", "mixed")
            if complexity in {"layout_complex", "mixed", "scanned_heavy"}:
                return "docling"
        elif parse_policy == "balanced":
            preflight = NativePDFParser.quick_preflight(
                request.file_path,
                max(1, settings.ocr_min_text_length),
            )
            complexity = preflight.get("complexity_class", "mixed")
            if complexity in {"layout_complex", "scanned_heavy"}:
                return "docling"

        return "native"

    def parse(self, request: ParseRequest) -> ParseResult:
        suffix = (request.suffix or "").strip().lower()
        if suffix in {".txt", ".md"}:
            return self._text.parse(request)
        if suffix != ".pdf":
            raise ValueError("Unsupported file type")

        parser = self._choose_pdf_parser(request)
        if parser == "docling":
            try:
                return self._docling.parse(request)
            except Exception:
                # Fallback to native parser for reliability
                return self._native.parse(request)

        return self._native.parse(request)
