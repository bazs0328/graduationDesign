from app.services.parsers.base import ParseRequest
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
