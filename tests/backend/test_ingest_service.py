from pathlib import Path
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
