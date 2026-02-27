from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.services import text_extraction as te


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakePdf:
    def __init__(self, page_texts: list[str]):
        self.pages = [_FakePage(text) for text in page_texts]

    def __enter__(self) -> "_FakePdf":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False


@dataclass
class _FakeEngine:
    result: te.OcrPageResult
    calls: int = 0

    def ocr_page(self, image: Any) -> te.OcrPageResult:  # noqa: ARG002
        self.calls += 1
        return self.result


@pytest.fixture(autouse=True)
def _reset_ocr_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(te, "_OCR_ENGINES", {})
    monkeypatch.setattr(te, "_UNKNOWN_OCR_ENGINE_WARNED", set())


def test_get_tesseract_language_prefers_new_setting(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(te.settings, "ocr_language", "chi_sim+eng")
    monkeypatch.setattr(te.settings, "ocr_tesseract_language", "eng")
    assert te._get_tesseract_language() == "eng"

    monkeypatch.setattr(te.settings, "ocr_tesseract_language", "")
    assert te._get_tesseract_language() == "chi_sim+eng"


def test_ocr_engine_chain_uses_primary_dedupes_and_skips_unknown(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(te.settings, "ocr_engine", "rapidocr")
    monkeypatch.setattr(te.settings, "ocr_fallback_engines", "rapidocr,unknown,tesseract")

    assert te._get_ocr_engine_chain_names() == ["rapidocr", "tesseract"]


def test_is_scanned_pdf_respects_configured_check_pages(monkeypatch: pytest.MonkeyPatch):
    pages = ["", "", "这一页有很多很多文本，超过阈值"]
    monkeypatch.setattr(te.settings, "ocr_check_pages", 2)
    assert te._is_scanned_pdf(pages, min_text_length=10) is True

    monkeypatch.setattr(te.settings, "ocr_check_pages", 3)
    assert te._is_scanned_pdf(pages, min_text_length=10) is False


def test_run_ocr_with_fallbacks_uses_next_engine_on_low_confidence(monkeypatch: pytest.MonkeyPatch):
    rapid_engine = _FakeEngine(
        te.OcrPageResult(text="低置信度结果", engine="rapidocr", avg_confidence=0.35, raw_line_count=1)
    )
    tess_engine = _FakeEngine(
        te.OcrPageResult(text="高置信度结果", engine="tesseract", avg_confidence=0.92, raw_line_count=1)
    )

    monkeypatch.setattr(te, "_get_ocr_engine_chain_names", lambda: ["rapidocr", "tesseract"])
    monkeypatch.setattr(te, "_get_ocr_low_confidence_threshold", lambda: 0.78)
    monkeypatch.setattr(
        te,
        "_get_ocr_engine",
        lambda name: rapid_engine if name == "rapidocr" else tess_engine,
    )

    result = te._run_ocr_with_fallbacks(image=object(), page_num=1)

    assert result.text == "高置信度结果"
    assert result.engine == "tesseract"
    assert rapid_engine.calls == 1
    assert tess_engine.calls == 1


def test_extract_pdf_does_not_invoke_ocr_when_text_layer_is_sufficient(monkeypatch: pytest.MonkeyPatch):
    rich_pages = [
        "这是一段足够长的文本内容，用于模拟可直接提取的 PDF 文本层。",
        "第二页也有足够多的文本，应该不会触发 OCR。",
    ]

    monkeypatch.setattr(te.pdfplumber, "open", lambda path: _FakePdf(rich_pages))
    monkeypatch.setattr(te.settings, "ocr_enabled", True)
    monkeypatch.setattr(te.settings, "ocr_min_text_length", 10)
    monkeypatch.setattr(te.settings, "ocr_check_pages", 3)

    called_pages: list[int] = []

    def _unexpected_ocr(file_path: str, page_num: int) -> te.OcrPageResult:  # noqa: ARG001
        called_pages.append(page_num)
        return te.OcrPageResult(text="should-not-happen", engine="rapidocr")

    monkeypatch.setattr(te, "_ocr_page", _unexpected_ocr)

    result = te._extract_pdf("dummy.pdf")

    assert called_pages == []
    assert result.page_count == 2
    assert result.pages[0].startswith("这是一段足够长的文本内容")
    assert "第二页" in result.text


def test_extract_pdf_scanned_pdf_replaces_low_quality_text_with_ocr(monkeypatch: pytest.MonkeyPatch):
    page_texts = ["x", ""]
    monkeypatch.setattr(te.pdfplumber, "open", lambda path: _FakePdf(page_texts))
    monkeypatch.setattr(te.settings, "ocr_enabled", True)
    monkeypatch.setattr(te.settings, "ocr_min_text_length", 10)
    monkeypatch.setattr(te.settings, "ocr_check_pages", 3)

    ocr_map = {
        1: te.OcrPageResult(text="第一页 OCR 内容", engine="rapidocr", avg_confidence=0.88, raw_line_count=1),
        2: te.OcrPageResult(text="第二页 OCR 内容", engine="rapidocr", avg_confidence=0.87, raw_line_count=1),
    }
    monkeypatch.setattr(te, "_ocr_page", lambda file_path, page_num: ocr_map[page_num])

    result = te._extract_pdf("scanned.pdf")

    assert result.pages == ["第一页 OCR 内容", "第二页 OCR 内容"]
    assert result.text == "第一页 OCR 内容\n\n第二页 OCR 内容"


def test_extract_pdf_scanned_pdf_with_ocr_disabled_does_not_call_ocr(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(te.pdfplumber, "open", lambda path: _FakePdf(["", ""]))
    monkeypatch.setattr(te.settings, "ocr_enabled", False)
    monkeypatch.setattr(te.settings, "ocr_min_text_length", 10)
    monkeypatch.setattr(te.settings, "ocr_check_pages", 3)

    def _unexpected_ocr(file_path: str, page_num: int):  # noqa: ANN001, ARG001
        raise AssertionError("OCR should not be called when disabled")

    monkeypatch.setattr(te, "_ocr_page", _unexpected_ocr)

    result = te._extract_pdf("scanned.pdf")

    assert result.page_count == 2
    assert result.pages == ["", ""]
    assert result.text == ""


def test_pick_page_text_after_ocr_prefers_ocr_when_page_is_garbled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(te.settings, "pdf_garbled_ocr_force", True)
    monkeypatch.setattr(te.settings, "pdf_garbled_ocr_min_len_ratio", 0.3)

    original_text = "bAo\n护\nhM\n感\nzSi\n黑\nhEi\n夜"
    ocr_text = "保护黑夜中的行动"

    chosen, reason = te._pick_page_text_after_ocr(
        original_text,
        ocr_text,
        scanned_pdf=False,
        min_text_length=10,
        trigger_reasons=["garbled_text"],
    )

    assert chosen == ocr_text
    assert reason == "ocr_forced_garbled"


def test_pick_page_text_after_ocr_fallbacks_when_garbled_ocr_is_too_short(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(te.settings, "pdf_garbled_ocr_force", True)
    monkeypatch.setattr(te.settings, "pdf_garbled_ocr_min_len_ratio", 0.3)

    original_text = "bAo\n护\nhM\n感\n保\nzSi\n黑\nhEi\n夜\nyF\n中\nzhTng\n行"
    ocr_text = "保护"

    chosen, reason = te._pick_page_text_after_ocr(
        original_text,
        ocr_text,
        scanned_pdf=False,
        min_text_length=10,
        trigger_reasons=["garbled_text"],
    )

    assert chosen == original_text
    assert reason == "garbled_force_fallback_short_ocr"
