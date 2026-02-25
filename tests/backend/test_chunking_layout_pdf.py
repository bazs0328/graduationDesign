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

    assert len(result.all_docs) == 3
    assert [d.metadata.get("modality") for d in result.all_docs] == ["text", "image", "text"]
    assert [d.metadata.get("chunk") for d in result.all_docs] == [1, 2, 3]
    image_doc = result.all_docs[1]
    assert image_doc.metadata.get("asset_path") == "/tmp/fake.png"
    assert image_doc.metadata.get("caption") == "图1 示例"
    assert "图注: 图1 示例" in image_doc.page_content
