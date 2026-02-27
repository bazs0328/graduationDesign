import json

from app.services.layout_sidecar import build_text_preview_from_sidecar


def _sample_sidecar() -> dict:
    return {
        "version": 1,
        "page_count": 1,
        "pages": [
            {
                "page": 1,
                "ordered_blocks": [
                    {"block_id": "p1:t1", "kind": "text", "text": "这是 sidecar 里的旧文本。"},
                    {"block_id": "p1:t2", "kind": "text", "text": "第二段旧文本。"},
                ],
            }
        ],
        "chunk_manifest": [
            {
                "chunk": 1,
                "page": 1,
                "modality": "text",
                "block_ids": json.dumps(["p1:t1"], ensure_ascii=False),
            }
        ],
    }


def test_build_text_preview_from_sidecar_skips_when_ocr_override_enabled():
    preview = build_text_preview_from_sidecar(
        _sample_sidecar(),
        {
            "page": 1,
            "chunk": 1,
            "ocr_override": True,
            "modality": "text",
        },
    )
    assert preview == ""


def test_build_text_preview_from_sidecar_skips_when_block_ids_contains_ocr_sentinel():
    preview = build_text_preview_from_sidecar(
        _sample_sidecar(),
        {
            "page": 1,
            "chunk": 1,
            "modality": "text",
            "block_ids": json.dumps(["p1:ocr"], ensure_ascii=False),
        },
    )
    assert preview == ""
