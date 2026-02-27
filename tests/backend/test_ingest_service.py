from pathlib import Path
import json
from unittest.mock import MagicMock

from langchain_core.documents import Document

from app.services.chunking import ChunkBuildResult
from app.services.ingest import ingest_document
from app.services import ingest as ingest_service
from app.services.text_extraction import ExtractionResult


def test_ingest_document_indexes_only_text_docs_for_lexical_store(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest_service.settings, "data_dir", str(tmp_path))

    source_file = Path(tmp_path) / "sample.txt"
    source_file.write_text("raw", encoding="utf-8")

    extraction = ExtractionResult(
        text="第一段文本\n\n第二段文本",
        page_count=1,
        pages=["第一段文本\n\n第二段文本"],
    )
    monkeypatch.setattr("app.services.ingest.extract_text", lambda *args, **kwargs: extraction)

    text_doc = Document(
        page_content="第一段文本",
        metadata={"doc_id": "doc1", "kb_id": "kb1", "source": "sample.txt", "modality": "text", "chunk": 1},
    )
    chunk_result = ChunkBuildResult(
        text_docs=[text_doc],
        all_docs=[text_doc],
        manifest=[{"chunk": 1, "modality": "text"}],
    )
    monkeypatch.setattr("app.services.ingest.build_chunked_documents", lambda *args, **kwargs: chunk_result)

    vectorstore = MagicMock()
    monkeypatch.setattr("app.services.ingest.get_vectorstore", lambda _user_id: vectorstore)

    appended_docs: list[Document] = []

    def _capture_append(_user_id: str, _kb_id: str, docs):
        appended_docs.extend(list(docs))

    monkeypatch.setattr("app.services.ingest.append_lexical_chunks", _capture_append)

    text_path, num_chunks, num_pages, char_count = ingest_document(
        str(source_file),
        "sample.txt",
        "doc1",
        "u1",
        "kb1",
    )

    assert num_chunks == 1
    assert num_pages == 1
    assert char_count == len(extraction.text)
    assert Path(text_path).exists()
    assert appended_docs == [text_doc]
    vectorstore.add_documents.assert_called_once_with([text_doc])


def test_ingest_document_writes_lexical_tokens_and_version(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest_service.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(ingest_service.settings, "lexical_stopwords_enabled", True)
    monkeypatch.setattr(ingest_service.settings, "lexical_tokenizer_version", "v2")

    source_file = Path(tmp_path) / "sample2.txt"
    source_file.write_text("raw", encoding="utf-8")

    extraction = ExtractionResult(
        text="我们使用 Python 和 AI 学习矩阵分解。",
        page_count=1,
        pages=["我们使用 Python 和 AI 学习矩阵分解。"],
    )
    monkeypatch.setattr("app.services.ingest.extract_text", lambda *args, **kwargs: extraction)

    text_doc = Document(
        page_content="我们使用 Python 和 AI 学习矩阵分解。",
        metadata={"doc_id": "doc2", "kb_id": "kb2", "source": "sample2.txt", "modality": "text", "chunk": 1},
    )
    chunk_result = ChunkBuildResult(
        text_docs=[text_doc],
        all_docs=[text_doc],
        manifest=[{"chunk": 1, "modality": "text"}],
    )
    monkeypatch.setattr("app.services.ingest.build_chunked_documents", lambda *args, **kwargs: chunk_result)

    vectorstore = MagicMock()
    monkeypatch.setattr("app.services.ingest.get_vectorstore", lambda _user_id: vectorstore)

    ingest_document(
        str(source_file),
        "sample2.txt",
        "doc2",
        "u2",
        "kb2",
    )

    lexical_path = Path(tmp_path) / "users" / "u2" / "lexical" / "kb2.jsonl"
    assert lexical_path.exists()
    row = json.loads(lexical_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert row.get("tokenizer_version") == "v2"
    tokens = row.get("tokens")
    assert isinstance(tokens, list)
    assert "python" in tokens
    assert "ai" in tokens
