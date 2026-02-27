import re

from app.services import chunking as chunking_service
from app.services.chunking import build_chunked_documents
from app.services.pdf_layout import ExtractedBlock, PageLayoutResult
from app.services.text_extraction import ExtractionResult


def test_build_chunked_documents_preserves_text_image_order_and_metadata():
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
                block_id="p1:i1",
                kind="image",
                page=1,
                bbox=[0, 30, 120, 120],
                asset_path="/tmp/fake.png",
                caption_text="图1 示例",
                nearby_text="相邻说明",
                order_index=2,
            ),
            ExtractedBlock(
                block_id="p1:t2",
                kind="text",
                page=1,
                bbox=[0, 130, 100, 160],
                text="第二段文字",
                order_index=3,
            ),
        ],
        image_blocks=[],
        text_blocks=[],
    )
    # Keep image_blocks populated like real parser output.
    page_layout.image_blocks = [page_layout.ordered_blocks[1]]
    page_layout.text_blocks = [page_layout.ordered_blocks[0], page_layout.ordered_blocks[2]]

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

    assert len(result.text_docs) == 2
    assert len(result.image_docs) == 1
    assert len(result.all_docs) == 2
    assert [d.metadata.get("modality") for d in result.all_docs] == ["text", "text"]
    assert [d.metadata.get("chunk") for d in result.all_docs] == [1, 2]
    assert [item.get("modality") for item in result.manifest] == ["text", "text"]
    image_doc = result.image_docs[0]
    assert image_doc.metadata.get("asset_path") == "/tmp/fake.png"
    assert image_doc.metadata.get("caption") == "图1 示例"
    assert image_doc.metadata.get("block_id") == "p1:i1"
    assert image_doc.metadata.get("chunk") is None
    assert "图注: 图1 示例" in image_doc.page_content


def test_build_chunked_documents_cleans_text_chunks_without_affecting_image_chunks(
    monkeypatch,
):
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
                block_id="p1:i1",
                kind="image",
                page=1,
                bbox=[0, 30, 120, 120],
                asset_path="/tmp/fake.png",
                caption_text="图1 示例",
                nearby_text="相邻说明",
                order_index=2,
            ),
            ExtractedBlock(
                block_id="p1:t2",
                kind="text",
                page=1,
                bbox=[0, 130, 100, 160],
                text="我们使用 Python 和 AI。",
                order_index=3,
            ),
        ],
        image_blocks=[],
        text_blocks=[],
    )
    page_layout.image_blocks = [page_layout.ordered_blocks[1]]
    page_layout.text_blocks = [page_layout.ordered_blocks[0], page_layout.ordered_blocks[2]]

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

    assert len(result.text_docs) == 2
    assert len(result.image_docs) == 1
    assert len(result.all_docs) == 2
    assert [d.metadata.get("modality") for d in result.all_docs] == ["text", "text"]
    assert result.all_docs[0].page_content == "家中。"
    assert re.search(r"[A-Za-z]", result.all_docs[0].page_content) is None
    assert "Python 和 AI" in result.all_docs[1].page_content
    assert result.image_docs[0].metadata.get("asset_path") == "/tmp/fake.png"


def test_build_chunked_documents_does_not_clean_non_pdf_text(monkeypatch):
    monkeypatch.setattr(chunking_service.settings, "index_text_cleanup_enabled", True)
    monkeypatch.setattr(chunking_service.settings, "index_text_cleanup_mode", "conservative")

    extraction = ExtractionResult(
        text="家jiQ\n中zhTng\n。\n\n我们使用 Python 和 AI。",
        page_count=1,
        pages=["家jiQ\n中zhTng\n。\n\n我们使用 Python 和 AI。"],
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
    assert "家jiQ" in result.text_docs[0].page_content
    assert "中zhTng" in result.text_docs[0].page_content
