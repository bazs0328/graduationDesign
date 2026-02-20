import json
import os

from app.core.paths import kb_base_dir
from app.services.rag.base import RAGIngestRequest
from app.services.rag.mineru_adapter import MinerUParseOutput
from app.services.rag.providers.raganything_provider import RAGAnythingProvider


def test_dual_write_metadata_keeps_modality_and_asset_fields(monkeypatch):
    provider = RAGAnythingProvider(backend_id="raganything_mineru", parser_preference="mineru")
    adapter = provider._mineru_adapter

    monkeypatch.setattr(adapter, "is_available", lambda: True)
    monkeypatch.setattr(
        adapter,
        "parse_pdf",
        lambda **kwargs: MinerUParseOutput(
            content_list=[
                {"type": "text", "text": "线性代数基础内容", "page_idx": 0},
                {
                    "type": "image",
                    "img_path": "",
                    "image_caption": "图2 矩阵变换",
                    "page_idx": 0,
                },
            ],
            markdown_text="线性代数基础内容",
            parser_engine="mineru",
            timing_ms={"parse": 4.2},
            raw_stats={"page_count": 1},
        ),
    )

    dense_docs = []
    lexical_docs = []
    monkeypatch.setattr(provider, "_index_dense_docs", lambda _u, docs: dense_docs.extend(docs))
    monkeypatch.setattr(
        provider,
        "_index_lexical_docs",
        lambda _u, _k, docs: lexical_docs.extend(docs),
    )

    req = RAGIngestRequest(
        file_path="tmp/dual-write.pdf",
        filename="dual-write.pdf",
        doc_id="doc-dual-write-1",
        user_id="u-dual-write-1",
        kb_id="kb-dual-write-1",
        parser_preference="mineru",
    )
    result = provider.ingest(req)

    assert result.num_chunks > 0
    assert dense_docs
    assert lexical_docs

    row = dense_docs[0]
    metadata = row.metadata
    for key in [
        "doc_id",
        "kb_id",
        "source",
        "page",
        "chunk",
        "parser_provider",
        "extract_method",
        "modality",
        "asset_id",
        "asset_caption",
    ]:
        assert key in metadata

    map_path = os.path.join(kb_base_dir(req.user_id, req.kb_id), "source_map", f"{req.doc_id}.jsonl")
    assert os.path.exists(map_path)
    with open(map_path, "r", encoding="utf-8") as f:
        payload = json.loads(f.readline().strip())

    assert payload["modality"] in {"text", "image", "table", "equation"}
    assert "asset_id" in payload
    assert "asset_caption" in payload
