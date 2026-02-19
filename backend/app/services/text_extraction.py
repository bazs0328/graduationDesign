import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pdfplumber

from app.core.config import settings


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
OCR_CHECK_PAGES = 3
OCR_RENDER_DPI = 300

logger = logging.getLogger(__name__)


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


def _is_low_text_page(page_text: str, min_text_length: int) -> bool:
    return len(page_text.strip()) < min_text_length


def _is_scanned_pdf(pages: List[str], min_text_length: int) -> bool:
    """Treat PDF as scanned when the first few pages have near-empty text layer."""
    if not pages:
        return True

    sample_count = min(len(pages), OCR_CHECK_PAGES)
    low_text_pages = sum(1 for page in pages[:sample_count] if _is_low_text_page(page, min_text_length))
    return low_text_pages == sample_count


def _ocr_page(file_path: str, page_num: int, language: str) -> str:
    """Run OCR for one PDF page and return normalized text."""
    try:
        from pdf2image import convert_from_path  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "OCR dependency missing: install pdf2image and poppler-utils."
        ) from exc

    try:
        import pytesseract  # type: ignore
        from pytesseract import TesseractNotFoundError  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "OCR dependency missing: install pytesseract and tesseract-ocr."
        ) from exc

    try:
        images = convert_from_path(
            file_path,
            first_page=page_num,
            last_page=page_num,
            dpi=OCR_RENDER_DPI,
            fmt="png",
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Failed to render PDF page for OCR. Please install poppler-utils."
        ) from exc

    if not images:
        return ""

    image = images[0]
    try:
        ocr_text = pytesseract.image_to_string(image, lang=language)
    except TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR engine not found. Please install tesseract-ocr."
        ) from exc
    except Exception:  # noqa: BLE001
        logger.exception("OCR failed on page %s", page_num)
        return ""
    finally:
        image.close()

    return _normalize_text(ocr_text)


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

        min_text_length = max(1, settings.ocr_min_text_length)
        scanned_pdf = _is_scanned_pdf(pages, min_text_length)
        if settings.ocr_enabled:
            if scanned_pdf:
                ocr_pages = list(range(1, page_count + 1))
            else:
                ocr_pages = [
                    idx
                    for idx, page_text in enumerate(pages, start=1)
                    if _is_low_text_page(page_text, min_text_length)
                ]
            for page_num in ocr_pages:
                try:
                    ocr_text = _ocr_page(file_path, page_num, settings.ocr_language)
                except RuntimeError:
                    if scanned_pdf:
                        raise
                    logger.exception("Skip OCR on page %s due to setup/runtime error", page_num)
                    continue

                if not ocr_text:
                    continue
                if pages[page_num - 1]:
                    pages[page_num - 1] = f"{pages[page_num - 1]}\n{ocr_text}".strip()
                else:
                    pages[page_num - 1] = ocr_text
        elif scanned_pdf:
            logger.info("Scanned PDF detected but OCR is disabled")

        combined = "\n\n".join([p for p in pages if p])
        return ExtractionResult(text=combined, page_count=page_count, pages=pages)

    raw_text, encoding = _read_text_with_fallback(file_path)
    normalized = _normalize_text(raw_text)
    return ExtractionResult(text=normalized, page_count=1, pages=[normalized], encoding=encoding)
