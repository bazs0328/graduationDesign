from __future__ import annotations

from time import perf_counter
from typing import Optional, Tuple

from .base import ParseRequest, ParseResult


FALLBACK_ENCODINGS: tuple[str, ...] = (
    "utf-8",
    "utf-8-sig",
    "gb18030",
    "gbk",
    "big5",
    "latin-1",
)


def _detect_encoding(data: bytes) -> Optional[str]:
    try:
        from charset_normalizer import from_bytes  # type: ignore

        result = from_bytes(data).best()
        if result and result.encoding:
            return result.encoding
    except Exception:
        return None
    return None


def _read_text_with_fallback(file_path: str) -> Tuple[str, Optional[str]]:
    with open(file_path, "rb") as f:
        data = f.read()

    encoding = _detect_encoding(data)
    if encoding:
        try:
            return data.decode(encoding), encoding
        except Exception:
            encoding = None

    for enc in FALLBACK_ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="ignore"), "utf-8-ignored"


def _normalize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


class TextParser:
    provider = "native"

    def parse(self, request: ParseRequest) -> ParseResult:
        started = perf_counter()
        text, encoding = _read_text_with_fallback(request.file_path)
        normalized = _normalize_text(text)
        elapsed = (perf_counter() - started) * 1000

        return ParseResult(
            text=normalized,
            page_count=1,
            pages=[normalized],
            parser_provider=self.provider,
            extract_method="text_layer",
            quality_score=100.0 if normalized else 0.0,
            diagnostics={
                "strategy": "text_only",
                "complexity_class": "fast_text",
                "low_quality_pages": [],
                "ocr_pages": [],
                "page_scores": [
                    {
                        "page": 1,
                        "chars": len(normalized),
                        "quality_score": 100.0 if normalized else 0.0,
                        "flags": [],
                        "method": "text_layer",
                    }
                ],
            },
            timing_ms={"extract": elapsed},
            encoding=encoding,
        )
