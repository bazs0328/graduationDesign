from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from math import fsum
import re
from time import perf_counter
from typing import Iterable

import pdfplumber

from app.core.config import settings

from .base import PageDiagnostic, ParseRequest, ParseResult

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    text = (text or "").replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fix_cjk_spacing(text: str) -> str:
    # Merge artificial spaces inserted between CJK chars by broken PDF text layer.
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)


def _remove_weird_tokens(text: str) -> str:
    # Remove short mixed-case artifacts like zDn/ySng that frequently appear in garbled extraction.
    return re.sub(r"\b[a-z]{1,3}[A-Z][a-zA-Z]{0,5}\b", " ", text)


def _iter_batches(items: Iterable[int], batch_size: int) -> Iterable[list[int]]:
    bucket: list[int] = []
    for item in items:
        bucket.append(item)
        if len(bucket) >= batch_size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket


def _page_quality(text: str, min_text_length: int) -> tuple[float, list[str]]:
    text = text or ""
    length = len(text.strip())
    if length == 0:
        return 0.0, ["low_text"]

    flags: list[str] = []
    score = 100.0

    han_chars = re.findall(r"[\u4e00-\u9fff]", text)
    han_ratio = len(han_chars) / max(1, len(text))

    tokens = re.findall(r"[A-Za-z]+", text)
    weird = [
        token
        for token in tokens
        if 2 <= len(token) <= 8 and any(ch.isupper() for ch in token[1:]) and token.lower() != token
    ]
    weird_ratio = len(weird) / max(1, len(tokens))

    han_spaced_hits = re.findall(r"(?:[\u4e00-\u9fff]\s+){2,}[\u4e00-\u9fff]", text)
    han_spaced_ratio = len(han_spaced_hits) / max(1, len(han_chars))

    non_printable = sum(1 for ch in text if not ch.isprintable())
    non_printable_ratio = non_printable / max(1, len(text))

    if length < min_text_length:
        flags.append("low_text")
        score -= 30

    if han_spaced_ratio >= 0.08:
        flags.append("han_spaced")
        score -= 40

    if weird_ratio >= 0.25:
        flags.append("weird_tokens")
        score -= 35

    if non_printable_ratio >= 0.02:
        flags.append("non_printable")
        score -= 20

    # Penalize very low CJK ratio when language is mixed Chinese docs.
    if han_ratio < 0.03 and length >= min_text_length * 2:
        score -= 10

    return max(0.0, min(100.0, score)), flags


def _clean_page(text: str, flags: list[str]) -> str:
    cleaned = _normalize_text(text)
    if "han_spaced" in flags:
        cleaned = _fix_cjk_spacing(cleaned)
    if "weird_tokens" in flags:
        cleaned = _remove_weird_tokens(cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _ocr_page(file_path: str, page_num: int, language: str) -> str:
    try:
        from pdf2image import convert_from_path  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("OCR dependency missing: install pdf2image and poppler-utils") from exc

    try:
        import pytesseract  # type: ignore
        from pytesseract import TesseractNotFoundError  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("OCR dependency missing: install pytesseract and tesseract-ocr") from exc

    try:
        images = convert_from_path(
            file_path,
            first_page=page_num,
            last_page=page_num,
            dpi=300,
            fmt="png",
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Failed to render PDF page for OCR. Please install poppler-utils") from exc

    if not images:
        return ""

    image = images[0]
    try:
        text = pytesseract.image_to_string(image, lang=language)
    except TesseractNotFoundError as exc:
        raise RuntimeError("Tesseract OCR engine not found. Please install tesseract-ocr") from exc
    except Exception:  # noqa: BLE001
        logger.exception("OCR failed on page %s", page_num)
        return ""
    finally:
        image.close()

    return _normalize_text(text)


class NativePDFParser:
    provider = "native"

    @staticmethod
    def quick_preflight(file_path: str, min_text_length: int) -> dict[str, float | str]:
        pages: list[str] = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:5]:
                try:
                    txt = page.extract_text() or ""
                except Exception:
                    txt = ""
                pages.append(_normalize_text(txt))

        if not pages:
            return {"complexity_class": "scanned_heavy", "empty_ratio": 1.0, "low_quality_ratio": 1.0}

        scores = [_page_quality(p, min_text_length)[0] for p in pages]
        low_quality = sum(1 for s in scores if s < settings.ocr_low_quality_score)
        low_text = sum(1 for p in pages if len(p.strip()) < min_text_length)
        empty_ratio = low_text / max(1, len(pages))
        low_ratio = low_quality / max(1, len(pages))

        if empty_ratio >= settings.ocr_full_scan_empty_ratio:
            cls = "scanned_heavy"
        elif low_ratio >= settings.ocr_full_scan_low_quality_ratio:
            cls = "layout_complex"
        elif low_ratio < 0.25 and empty_ratio < 0.2:
            cls = "fast_text"
        else:
            cls = "mixed"

        return {
            "complexity_class": cls,
            "empty_ratio": round(empty_ratio, 4),
            "low_quality_ratio": round(low_ratio, 4),
        }

    def parse(self, request: ParseRequest) -> ParseResult:
        mode = (request.mode or "auto").strip().lower()
        if mode not in {"auto", "force_ocr", "text_layer", "parser_auto"}:
            mode = "auto"
        if mode == "parser_auto":
            mode = "auto"

        started = perf_counter()
        phase_extract_start = perf_counter()

        pages: list[str] = []
        with pdfplumber.open(request.file_path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""
                pages.append(_normalize_text(page_text))

        extract_ms = (perf_counter() - phase_extract_start) * 1000

        min_text_length = max(1, settings.ocr_min_text_length)
        page_diags: list[PageDiagnostic] = []
        for i, page_text in enumerate(pages, start=1):
            score, flags = _page_quality(page_text, min_text_length)
            cleaned = _clean_page(page_text, flags)
            pages[i - 1] = cleaned
            score_after, flags_after = _page_quality(cleaned, min_text_length)
            page_diags.append(
                PageDiagnostic(
                    page_num=i,
                    char_count=len(cleaned),
                    quality_score=score_after,
                    flags=flags_after,
                    method="text_layer",
                )
            )

        if page_count == 0:
            return ParseResult(
                text="",
                page_count=0,
                pages=[],
                parser_provider=self.provider,
                extract_method="text_layer",
                quality_score=0.0,
                diagnostics={
                    "strategy": "empty",
                    "complexity_class": "fast_text",
                    "low_quality_pages": [],
                    "ocr_pages": [],
                    "page_scores": [],
                },
                timing_ms={"extract": round(extract_ms, 2)},
            )

        low_quality_pages = [
            d.page_num for d in page_diags if d.quality_score < settings.ocr_low_quality_score
        ]
        low_text_pages = [d.page_num for d in page_diags if d.char_count < min_text_length]

        sample_count = min(page_count, 5)
        sample_low_text = sum(1 for d in page_diags[:sample_count] if d.char_count < min_text_length)
        sample_low_quality = sum(
            1
            for d in page_diags[:sample_count]
            if d.quality_score < settings.ocr_low_quality_score
        )
        empty_ratio = sample_low_text / max(1, sample_count)
        low_quality_ratio = sample_low_quality / max(1, sample_count)

        if empty_ratio >= settings.ocr_full_scan_empty_ratio:
            complexity_class = "scanned_heavy"
        elif low_quality_ratio >= settings.ocr_full_scan_low_quality_ratio:
            complexity_class = "layout_complex"
        elif low_quality_ratio < 0.25 and empty_ratio < 0.2:
            complexity_class = "fast_text"
        else:
            complexity_class = "mixed"

        ocr_pages: list[int] = []
        strategy = "text_layer"

        if mode == "force_ocr":
            strategy = "force_ocr"
            ocr_pages = list(range(1, page_count + 1))
        elif mode == "text_layer":
            strategy = "text_layer_only"
            ocr_pages = []
        else:
            if empty_ratio >= settings.ocr_full_scan_empty_ratio or low_quality_ratio >= settings.ocr_full_scan_low_quality_ratio:
                strategy = "full_ocr"
                ocr_pages = list(range(1, page_count + 1))
            else:
                strategy = "selective_ocr"
                ocr_pages = sorted(set(low_quality_pages + low_text_pages))

        ocr_ms = 0.0
        if settings.ocr_enabled and ocr_pages:
            phase_ocr_start = perf_counter()
            max_workers = max(1, int(settings.ocr_page_workers))
            batch_size = max(1, int(settings.ocr_batch_size))

            try:
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    for batch in _iter_batches(ocr_pages, batch_size):
                        future_map = {
                            pool.submit(_ocr_page, request.file_path, page_num, settings.ocr_language): page_num
                            for page_num in batch
                        }
                        for future in as_completed(future_map):
                            page_num = future_map[future]
                            ocr_text = future.result()
                            if not ocr_text:
                                continue

                            original = pages[page_num - 1]
                            original_diag = page_diags[page_num - 1]
                            ocr_score, ocr_flags = _page_quality(ocr_text, min_text_length)
                            threshold = max(original_diag.quality_score, float(settings.ocr_low_quality_score))

                            if original.strip() and ocr_score < threshold:
                                continue

                            cleaned_ocr = _clean_page(ocr_text, ocr_flags)
                            final_score, final_flags = _page_quality(cleaned_ocr, min_text_length)
                            pages[page_num - 1] = cleaned_ocr
                            page_diags[page_num - 1] = PageDiagnostic(
                                page_num=page_num,
                                char_count=len(cleaned_ocr),
                                quality_score=final_score,
                                flags=final_flags,
                                method="ocr",
                            )
            except RuntimeError:
                # Dependency/runtime issue. Keep text layer as fallback.
                logger.exception("OCR setup/runtime issue. Falling back to text layer for %s", request.file_path)

            ocr_ms = (perf_counter() - phase_ocr_start) * 1000

        text = "\n\n".join([page for page in pages if page.strip()])
        quality_values = [diag.quality_score for diag in page_diags]
        quality_avg = fsum(quality_values) / max(1, len(quality_values))

        methods = {diag.method for diag in page_diags if diag.char_count > 0}
        if methods == {"ocr"}:
            extract_method = "ocr"
        elif "ocr" in methods and "text_layer" in methods:
            extract_method = "hybrid"
        else:
            extract_method = "text_layer"

        total_ms = (perf_counter() - started) * 1000
        diagnostics = {
            "strategy": strategy,
            "complexity_class": complexity_class,
            "low_quality_pages": [
                d.page_num for d in page_diags if d.quality_score < settings.ocr_low_quality_score
            ],
            "ocr_pages": [d.page_num for d in page_diags if d.method == "ocr"],
            "page_scores": [d.to_dict() for d in page_diags],
            "empty_ratio": round(empty_ratio, 4),
            "low_quality_ratio": round(low_quality_ratio, 4),
        }
        timing = {
            "extract": round(extract_ms, 2),
            "ocr": round(ocr_ms, 2),
            "total": round(total_ms, 2),
        }

        return ParseResult(
            text=text,
            page_count=page_count,
            pages=pages,
            parser_provider=self.provider,
            extract_method=extract_method,
            quality_score=round(quality_avg, 2),
            diagnostics=diagnostics,
            timing_ms=timing,
        )
