from app.services.rag.mineru_adapter import MinerUAdapter


def test_normalize_content_list_maps_pages_and_assets():
    adapter = MinerUAdapter()
    content_list = [
        {"type": "text", "text": "这是第一页正文。", "page_idx": 0},
        {
            "type": "image",
            "img_path": "/tmp/demo-image.png",
            "image_caption": [" 图 1 ", "流程示意"],
            "page_idx": 1,
        },
        {
            "type": "table",
            "table_img_path": "/tmp/demo-table.png",
            "table_caption": " 表 1 结果 ",
            "table_body": [["A", "B"], ["1", "2"]],
            "page_idx": 1,
        },
        {
            "type": "equation",
            "equation_img_path": "/tmp/demo-equation.png",
            "latex": "E=mc^2",
            "text": "质能方程",
            "page_idx": 2,
        },
    ]

    bundle = adapter.normalize_content_list(
        content_list=content_list,
        markdown_text="fallback",
        doc_id="doc-adapter-1",
        kb_id="kb-adapter-1",
        filename="demo.pdf",
        parser_provider="raganything",
        extract_method="mineru_multimodal",
    )

    assert bundle.full_text
    assert len(bundle.page_texts) >= 3
    assert bundle.asset_stats["total"] == 3
    assert bundle.asset_stats["by_type"]["image"] == 1
    assert bundle.asset_stats["by_type"]["table"] == 1
    assert bundle.asset_stats["by_type"]["equation"] == 1

    assets_by_type = {row["asset_type"]: row for row in bundle.assets}
    assert assets_by_type["image"]["page"] == 2
    assert assets_by_type["table"]["page"] == 2
    assert assets_by_type["equation"]["page"] == 3
    assert "流程示意" in (assets_by_type["image"]["caption_text"] or "")
    assert assets_by_type["table"]["source_path"] == "/tmp/demo-table.png"
    assert assets_by_type["equation"]["source_path"] == "/tmp/demo-equation.png"

    modalities = {doc.metadata.get("modality") for doc in bundle.chunk_docs}
    assert "text" in modalities
    assert "image" in modalities or "table" in modalities or "equation" in modalities
