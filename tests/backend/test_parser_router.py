from app.services.parsers.base import ParseRequest, ParseResult
from app.services.parsers.router import ParserRouter


def test_router_parses_text_file(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("线性代数基础", encoding="utf-8")

    router = ParserRouter()
    result = router.parse(
        ParseRequest(file_path=str(path), suffix=".txt", mode="auto", parse_policy="balanced")
    )

    assert result.parser_provider == "native"
    assert result.extract_method == "text_layer"
    assert "线性代数" in result.text


def test_router_falls_back_to_native_when_docling_unavailable(monkeypatch):
    router = ParserRouter()
    req = ParseRequest(
        file_path="/tmp/nonexistent.pdf",
        suffix=".pdf",
        mode="auto",
        parse_policy="aggressive",
        preferred_parser="docling",
    )

    monkeypatch.setattr(router._docling, "is_available", lambda: False)
    assert router._choose_pdf_parser(req) == "native"


def test_router_prefers_docling_for_balanced_scanned_heavy(monkeypatch):
    router = ParserRouter()
    req = ParseRequest(
        file_path="/tmp/nonexistent.pdf",
        suffix=".pdf",
        mode="auto",
        parse_policy="balanced",
        preferred_parser="auto",
    )

    monkeypatch.setattr(router._docling, "is_available", lambda: True)
    monkeypatch.setattr(
        "app.services.parsers.router.NativePDFParser.quick_preflight",
        lambda *_args, **_kwargs: {"complexity_class": "scanned_heavy"},
    )
    assert router._choose_pdf_parser(req) == "docling"


def test_router_falls_back_to_native_when_docling_quality_guard_triggers(monkeypatch):
    router = ParserRouter()
    req = ParseRequest(
        file_path="/tmp/nonexistent.pdf",
        suffix=".pdf",
        mode="auto",
        parse_policy="balanced",
        preferred_parser="docling",
    )

    monkeypatch.setattr(router, "_choose_pdf_parser", lambda _req: "docling")
    monkeypatch.setattr(
        router._docling,
        "parse",
        lambda _req: ParseResult(
            text="bad output",
            page_count=1,
            pages=["bad output"],
            parser_provider="docling",
            extract_method="text_layer",
            quality_score=32.0,
            diagnostics={
                "quality_guard": {
                    "fallback_recommended": True,
                    "reasons": ["low_quality_score"],
                }
            },
            timing_ms={"total": 10.0},
        ),
    )
    monkeypatch.setattr(
        router._native,
        "parse",
        lambda _req: ParseResult(
            text="native output",
            page_count=2,
            pages=["p1", "p2"],
            parser_provider="native",
            extract_method="text_layer",
            quality_score=80.0,
            diagnostics={},
            timing_ms={"total": 2.0},
        ),
    )

    result = router.parse(req)
    assert result.parser_provider == "native"
    assert (result.diagnostics or {}).get("fallback", {}).get("from") == "docling"
