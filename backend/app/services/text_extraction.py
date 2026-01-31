import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pdfplumber


@dataclass
class ExtractionResult:
    text: str
    page_count: int
    pages: List[str]
    encoding: Optional[str] = None


FALLBACK_ENCODINGS: Tuple[str, ...] = (
    "utf-8",
    "utf-8-sig",
    "gb18030",
    "gbk",
    "big5",
    "latin-1",
)


def _normalize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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


def extract_text(file_path: str, suffix: str) -> ExtractionResult:
    if suffix == ".pdf":
        pages: List[str] = []
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""
                pages.append(_normalize_text(page_text))
        combined = "\n\n".join([p for p in pages if p])
        return ExtractionResult(text=combined, page_count=page_count, pages=pages)

    raw_text, encoding = _read_text_with_fallback(file_path)
    normalized = _normalize_text(raw_text)
    return ExtractionResult(text=normalized, page_count=1, pages=[normalized], encoding=encoding)
