import re

from app.services import chunking as chunking_service
from app.services.chunking import build_chunked_documents
from app.services.pdf_layout import ExtractedBlock, PageLayoutResult
from app.services.text_extraction import ExtractionResult


def test_build_chunked_documents_preserves_text_order_and_metadata():
    page_layout = PageLayoutResult(
        page=1,
        ordered_blocks=[
            ExtractedBlock(
                block_id="p1:t1",
                kind="text",
                page=1,
                bbox=[0, 0, 100, 20],
                text="第一段文字",
                order_index=1,
            ),
            ExtractedBlock(
                block_id="p1:t2",
                kind="text",
                page=1,
                bbox=[0, 30, 120, 120],
                text="第二段文字",
                order_index=2,
            ),
        ],
        text_blocks=[],
    )
    page_layout.text_blocks = list(page_layout.ordered_blocks)

    extraction = ExtractionResult(
        text="第一段文字\n\n第二段文字",
        page_count=1,
        pages=["第一段文字\n\n第二段文字"],
        page_blocks=[page_layout],
        blocks=page_layout.ordered_blocks,
    )

    result = build_chunked_documents(
        extraction=extraction,
        suffix=".pdf",
        doc_id="doc1",
        user_id="u1",
        kb_id="kb1",
        filename="sample.pdf",
        chunk_size=1000,
        chunk_overlap=0,
    )

    assert len(result.text_docs) == 1
    assert len(result.all_docs) == 1
    assert [d.metadata.get("modality") for d in result.all_docs] == ["text"]
    assert [d.metadata.get("chunk") for d in result.all_docs] == [1]
    assert [item.get("modality") for item in result.manifest] == ["text"]
    assert "第一段文字" in result.text_docs[0].page_content
    assert "第二段文字" in result.text_docs[0].page_content


def test_build_chunked_documents_cleans_text_chunks_for_pdf(monkeypatch):
    monkeypatch.setattr(chunking_service.settings, "index_text_cleanup_enabled", True)
    monkeypatch.setattr(chunking_service.settings, "index_text_cleanup_mode", "conservative")

    page_layout = PageLayoutResult(
        page=1,
        ordered_blocks=[
            ExtractedBlock(
                block_id="p1:t1",
                kind="text",
                page=1,
                bbox=[0, 0, 100, 20],
                text="家jiQ\n中zhTng\n。",
                order_index=1,
            ),
            ExtractedBlock(
                block_id="p1:t2",
                kind="text",
                page=1,
                bbox=[0, 130, 100, 160],
                text="我们使用 Python 和 AI。",
                order_index=2,
            ),
        ],
        text_blocks=[],
    )
    page_layout.text_blocks = list(page_layout.ordered_blocks)

    extraction = ExtractionResult(
        text="家jiQ\n中zhTng\n。\n\n我们使用 Python 和 AI。",
        page_count=1,
        pages=["家jiQ\n中zhTng\n。\n\n我们使用 Python 和 AI。"],
        page_blocks=[page_layout],
        blocks=page_layout.ordered_blocks,
    )

    result = build_chunked_documents(
        extraction=extraction,
        suffix=".pdf",
        doc_id="doc1",
        user_id="u1",
        kb_id="kb1",
        filename="sample.pdf",
        chunk_size=1000,
        chunk_overlap=0,
    )

    assert len(result.text_docs) == 1
    assert len(result.all_docs) == 1
    assert [d.metadata.get("modality") for d in result.all_docs] == ["text"]
    assert "家中。" in result.all_docs[0].page_content
    assert "jiQ" not in result.all_docs[0].page_content
    assert "zhTng" not in result.all_docs[0].page_content
    assert "Python 和 AI" in result.all_docs[0].page_content


def test_build_chunked_documents_cleans_non_pdf_text_with_structure_preserving_mode(monkeypatch):
    monkeypatch.setattr(chunking_service.settings, "index_text_cleanup_enabled", True)
    monkeypatch.setattr(chunking_service.settings, "index_text_cleanup_mode", "conservative")
    monkeypatch.setattr(chunking_service.settings, "index_text_cleanup_non_pdf_mode", "structure_preserving")

    extraction = ExtractionResult(
        text="bAo\nhM\nzhTng\n\n我们使用 Python 和 AI。",
        page_count=1,
        pages=["bAo\nhM\nzhTng\n\n我们使用 Python 和 AI。"],
    )

    result = build_chunked_documents(
        extraction=extraction,
        suffix=".txt",
        doc_id="doc-nonpdf",
        user_id="u1",
        kb_id="kb1",
        filename="sample.txt",
        chunk_size=1000,
        chunk_overlap=0,
    )

    assert len(result.text_docs) == 1
    assert "bAo" not in result.text_docs[0].page_content
    assert "hM" not in result.text_docs[0].page_content
    assert "zhTng" not in result.text_docs[0].page_content
    assert "Python 和 AI" in result.text_docs[0].page_content


def test_build_chunked_documents_removes_pdf_repeated_header_footer_and_page_numbers():
    extraction = ExtractionResult(
        text="人民教育出版社\n单元回顾\n正文一\n62\n\n人民教育出版社\n正文二\n63",
        page_count=2,
        pages=[
            "人民教育出版社\n单元回顾\n正文一\n62",
            "人民教育出版社\n正文二\n63",
        ],
    )

    result = build_chunked_documents(
        extraction=extraction,
        suffix=".pdf",
        doc_id="doc-pdf-edge",
        user_id="u1",
        kb_id="kb1",
        filename="edge.pdf",
        chunk_size=1000,
        chunk_overlap=0,
    )

    combined = "\n".join(doc.page_content for doc in result.text_docs)
    assert "人民教育出版社" not in combined
    assert "\n62" not in combined
    assert "\n63" not in combined
    assert "正文一" in combined
    assert "正文二" in combined
