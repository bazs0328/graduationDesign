import json
import os

from app.core.paths import kb_base_dir
from app.services.rag.base import RAGIngestRequest, RAGIngestResult
from app.services.rag.mineru_adapter import MinerUParseOutput
from app.services.rag.providers.raganything_provider import RAGAnythingProvider


def _request(user_id: str, kb_id: str, doc_id: str) -> RAGIngestRequest:
    return RAGIngestRequest(
        file_path="tmp/demo.pdf",
        filename="demo.pdf",
        doc_id=doc_id,
        user_id=user_id,
        kb_id=kb_id,
        parser_preference="mineru",
    )


def _legacy_result(parser_provider: str = "docling") -> RAGIngestResult:
    return RAGIngestResult(
        text_path="tmp/doc.txt",
        num_chunks=2,
        num_pages=1,
        char_count=36,
        parser_provider=parser_provider,
        extract_method="hybrid",
        quality_score=78.0,
        diagnostics={},
        timing={"total": 8.0},
        rag_backend="legacy",
        parser_engine=parser_provider,
    )


def test_mineru_success_generates_assets_and_source_map(monkeypatch):
    provider = RAGAnythingProvider(backend_id="raganything_mineru", parser_preference="mineru")
    adapter = provider._mineru_adapter

    monkeypatch.setattr(adapter, "is_available", lambda: True)
    monkeypatch.setattr(
        adapter,
        "parse_pdf",
        lambda **kwargs: MinerUParseOutput(
            content_list=[
                {"type": "text", "text": "矩阵是线性变换的表示。", "page_idx": 0},
                {
                    "type": "image",
                    "img_path": "",
                    "image_caption": "图1 线性变换示意",
                    "page_idx": 0,
                },
                {
                    "type": "table",
                    "table_img_path": "",
                    "table_caption": "表1 计算结果",
                    "table_body": [["A", "B"], ["1", "2"]],
                    "page_idx": 1,
                },
            ],
            markdown_text="矩阵是线性变换的表示。",
            parser_engine="mineru",
            timing_ms={"parse": 6.5},
            raw_stats={"page_count": 2},
        ),
    )

    captured_dense_docs = []
    captured_lexical_docs = []
    monkeypatch.setattr(
        provider,
        "_index_dense_docs",
        lambda _user_id, docs: captured_dense_docs.extend(docs),
    )
    monkeypatch.setattr(
        provider,
        "_index_lexical_docs",
        lambda _user_id, _kb_id, docs: captured_lexical_docs.extend(docs),
    )

    user_id = "u-rag-success"
    kb_id = "kb-rag-success"
    doc_id = "doc-rag-success"
    result = provider.ingest(_request(user_id, kb_id, doc_id))

    assert result.parser_engine == "mineru"
    assert result.parser_provider == "raganything"
    assert result.extract_method == "mineru_multimodal"
    assert result.asset_stats["total"] >= 2
    assert len(result.assets) >= 2
    assert captured_dense_docs
    assert captured_lexical_docs

    first_doc_meta = captured_dense_docs[0].metadata
    assert "doc_id" in first_doc_meta
    assert "kb_id" in first_doc_meta
    assert "source" in first_doc_meta
    assert "page" in first_doc_meta
    assert "chunk" in first_doc_meta
    assert "parser_provider" in first_doc_meta
    assert "extract_method" in first_doc_meta
    assert "modality" in first_doc_meta

    map_path = os.path.join(kb_base_dir(user_id, kb_id), "source_map", f"{doc_id}.jsonl")
    assert os.path.exists(map_path)
    with open(map_path, "r", encoding="utf-8") as f:
        row = json.loads(f.readline().strip())
    assert row["doc_id"] == doc_id
    assert row["kb_id"] == kb_id
    assert row["parser_engine"] == "mineru"


def test_mineru_unavailable_falls_back_to_docling(monkeypatch):
    provider = RAGAnythingProvider(backend_id="raganything_mineru", parser_preference="mineru")
    monkeypatch.setattr(provider._mineru_adapter, "is_available", lambda: False)

    monkeypatch.setattr(
        provider,
        "_ingest_with_legacy_parser",
        lambda request, parser_engine, preferred_parser, fallback_chain, strategy: RAGIngestResult(
            text_path="tmp/doc.txt",
            num_chunks=2,
            num_pages=1,
            char_count=24,
            parser_provider="docling",
            extract_method="hybrid",
            quality_score=72.0,
            diagnostics={
                "parser_engine": parser_engine,
                "fallback_chain": list(fallback_chain),
                "strategy": strategy,
            },
            timing={"total": 9.0},
            rag_backend="raganything_mineru",
            parser_engine=parser_engine,
            fallback_chain=list(fallback_chain),
            asset_stats={"total": 0, "by_type": {}},
            assets=[],
        ),
    )

    result = provider.ingest(_request("u-rag-fallback-1", "kb-rag-fallback-1", "doc-rag-fallback-1"))

    assert result.parser_engine == "docling"
    assert "mineru_unavailable" in result.fallback_chain
    assert result.diagnostics["strategy"] == "mineru_fallback_docling"


def test_mineru_and_docling_fail_then_fallback_to_native(monkeypatch):
    provider = RAGAnythingProvider(backend_id="raganything_mineru", parser_preference="mineru")
    monkeypatch.setattr(provider._mineru_adapter, "is_available", lambda: True)
    monkeypatch.setattr(provider._mineru_adapter, "parse_pdf", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("mineru parse failed")))

    def _legacy_side_effect(request, parser_engine, preferred_parser, fallback_chain, strategy):
        if parser_engine == "docling":
            raise RuntimeError("docling fallback failed")
        result = _legacy_result(parser_provider="native")
        result.fallback_chain = list(fallback_chain)
        result.diagnostics = {"fallback_chain": list(fallback_chain), "strategy": strategy}
        return result

    monkeypatch.setattr(provider, "_ingest_with_legacy_parser", _legacy_side_effect)

    result = provider.ingest(_request("u-rag-fallback-2", "kb-rag-fallback-2", "doc-rag-fallback-2"))

    assert result.parser_provider == "native"
    assert "mineru_parse_failed" in result.fallback_chain
    assert "docling_fallback_failed" in result.fallback_chain
    assert "native_legacy_fallback" in result.fallback_chain
