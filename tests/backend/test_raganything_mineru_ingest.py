import json
import os

from app.core.paths import kb_base_dir
from app.services.rag.base import RAGIngestRequest, RAGIngestResult
from app.services.rag.providers.raganything_provider import RAGAnythingProvider


def _legacy_ingest_result() -> RAGIngestResult:
    return RAGIngestResult(
        text_path="tmp/doc.txt",
        num_chunks=3,
        num_pages=2,
        char_count=123,
        parser_provider="native",
        extract_method="hybrid",
        quality_score=81.5,
        diagnostics={},
        timing={"total": 12.5},
        rag_backend="legacy",
    )


def test_mineru_unavailable_falls_back_to_docling(monkeypatch):
    provider = RAGAnythingProvider(backend_id="raganything_mineru", parser_preference="mineru")
    monkeypatch.setattr(provider, "_raganything_available", lambda: False)
    monkeypatch.setattr(provider._legacy, "ingest", lambda _request: _legacy_ingest_result())
    monkeypatch.setattr(provider, "_write_source_map", lambda *args, **kwargs: None)

    result = provider.ingest(
        RAGIngestRequest(
            file_path="tmp/demo.pdf",
            filename="demo.pdf",
            doc_id="doc-rag-1",
            user_id="u-rag-1",
            kb_id="kb-rag-1",
            parser_preference="mineru",
        )
    )

    assert result.parser_engine == "docling"
    assert "mineru_unavailable" in result.fallback_chain
    assert result.diagnostics["rag_backend"] == "raganything_mineru"
    assert result.diagnostics["parser_engine"] == "docling"


def test_ingest_writes_source_map_for_dual_write_compat(monkeypatch):
    provider = RAGAnythingProvider(backend_id="raganything_mineru", parser_preference="mineru")
    monkeypatch.setattr(provider, "_raganything_available", lambda: True)
    monkeypatch.setattr(provider._legacy, "ingest", lambda _request: _legacy_ingest_result())
    monkeypatch.setattr(
        "app.services.rag.providers.raganything_provider.get_doc_vector_entries",
        lambda _user_id, _doc_id: [
            {
                "content": "矩阵用于表示线性变换。",
                "metadata": {"source": "demo.pdf", "page": 1, "chunk": 0},
            }
        ],
    )

    user_id = "u-rag-2"
    kb_id = "kb-rag-2"
    doc_id = "doc-rag-2"
    _ = provider.ingest(
        RAGIngestRequest(
            file_path="tmp/demo.pdf",
            filename="demo.pdf",
            doc_id=doc_id,
            user_id=user_id,
            kb_id=kb_id,
            parser_preference="mineru",
        )
    )

    map_path = os.path.join(kb_base_dir(user_id, kb_id), "source_map", f"{doc_id}.jsonl")
    assert os.path.exists(map_path)

    with open(map_path, "r", encoding="utf-8") as f:
        line = f.readline().strip()
    payload = json.loads(line)
    assert payload["doc_id"] == doc_id
    assert payload["kb_id"] == kb_id
    assert payload["source"] == "demo.pdf"
    assert payload["text"] == "矩阵用于表示线性变换。"
