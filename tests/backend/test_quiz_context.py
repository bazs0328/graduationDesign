import json
from types import SimpleNamespace
from unittest.mock import patch

from app.services.quiz_context import build_quiz_context_from_seeds


def _seed(*, doc_id: str, kb_id: str, source: str, chunk: int, page: int, text: str, **meta):
    metadata = {
        "doc_id": doc_id,
        "kb_id": kb_id,
        "source": source,
        "chunk": chunk,
        "page": page,
        "modality": "text",
        "chunk_kind": "text",
    }
    metadata.update(meta)
    return SimpleNamespace(page_content=text, metadata=metadata)


def _entry(*, doc_id: str, kb_id: str, source: str, chunk: int, page: int, text: str, **meta):
    metadata = {
        "doc_id": doc_id,
        "kb_id": kb_id,
        "source": source,
        "chunk": chunk,
        "page": page,
        "modality": "text",
        "chunk_kind": "text",
    }
    metadata.update(meta)
    return {"content": text, "metadata": metadata}


def test_quiz_context_reconstructs_neighbor_chunks_and_filters_fragment_seed():
    seed = _seed(
        doc_id="doc-1",
        kb_id="kb-1",
        source="A.pdf",
        chunk=3,
        page=1,
        text="图1\n矩阵\n变换",
    )
    entries = [
        _entry(
            doc_id="doc-1",
            kb_id="kb-1",
            source="A.pdf",
            chunk=2,
            page=1,
            text="矩阵变换的定义：通过线性映射将点从一个坐标系映射到另一个坐标系。",
        ),
        _entry(
            doc_id="doc-1",
            kb_id="kb-1",
            source="A.pdf",
            chunk=3,
            page=1,
            text="当变换矩阵的行列式为负时，图形会发生翻转。",
        ),
        _entry(
            doc_id="doc-1",
            kb_id="kb-1",
            source="A.pdf",
            chunk=4,
            page=1,
            text="在二维平面中，关于 y 轴对称可由 x 坐标取相反数表示。",
        ),
    ]

    with patch("app.services.quiz_context.get_doc_vector_entries", return_value=entries):
        result = build_quiz_context_from_seeds(
            user_id="u1",
            seed_docs=[seed],
            max_chars=2000,
            kb_scope=False,
        )

    assert "来源: A.pdf" in result.text
    assert "矩阵变换的定义" in result.text
    assert "关于 y 轴对称" in result.text
    assert "图1\n矩阵\n变换" not in result.text
    assert result.stats.get("reconstructed_count", 0) >= 1


def test_quiz_context_round_robins_multiple_docs_in_kb_scope():
    seeds = [
        _seed(doc_id="doc-1", kb_id="kb-1", source="A.pdf", chunk=1, page=1, text="A seed"),
        _seed(doc_id="doc-1", kb_id="kb-1", source="A.pdf", chunk=2, page=1, text="A seed2"),
        _seed(doc_id="doc-2", kb_id="kb-1", source="B.pdf", chunk=1, page=1, text="B seed"),
    ]
    rows = {
        "doc-1": [
            _entry(doc_id="doc-1", kb_id="kb-1", source="A.pdf", chunk=1, page=1, text="A文档核心概念一。"),
            _entry(doc_id="doc-1", kb_id="kb-1", source="A.pdf", chunk=2, page=1, text="A文档核心概念二。"),
        ],
        "doc-2": [
            _entry(doc_id="doc-2", kb_id="kb-1", source="B.pdf", chunk=1, page=1, text="B文档关键定义。"),
            _entry(doc_id="doc-2", kb_id="kb-1", source="B.pdf", chunk=2, page=1, text="B文档应用场景。"),
        ],
    }

    def _fetch(_user_id: str, doc_id: str):
        return rows.get(doc_id, [])

    with patch("app.services.quiz_context.get_doc_vector_entries", side_effect=_fetch):
        result = build_quiz_context_from_seeds(
            user_id="u1",
            seed_docs=seeds,
            max_chars=4000,
            kb_scope=True,
            default_kb_id="kb-1",
        )

    first_a = result.text.find("来源: A.pdf")
    first_b = result.text.find("来源: B.pdf")
    assert first_a >= 0 and first_b >= 0
    assert first_a < first_b
    # Round-robin should surface B.pdf before A.pdf's second segment.
    second_a = result.text.find("来源: A.pdf", first_a + 1)
    assert second_a == -1 or first_b < second_a


def test_quiz_context_prefers_sidecar_reconstruction_when_available(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    sidecar_dir = data_dir / "users" / "u1" / "kb" / "kb-1" / "content_list"
    sidecar_dir.mkdir(parents=True)
    sidecar_path = sidecar_dir / "doc-1.layout.json"
    sidecar_payload = {
        "pages": [
            {
                "page": 1,
                "ordered_blocks": [
                    {"block_id": "p1:t1", "kind": "text", "text": "矩阵变换用于描述图形坐标变化。"},
                    {"block_id": "p1:t2", "kind": "text", "text": "图1展示了关于 y 轴对称的结果。"},
                    {"block_id": "p1:t3", "kind": "text", "text": "当 x 坐标取反时可得到对称图像。"},
                ],
            }
        ],
        "chunk_manifest": [
            {"chunk": 5, "page": 1, "modality": "text", "block_ids": json.dumps(["p1:t2"], ensure_ascii=False)},
        ],
    }
    sidecar_path.write_text(json.dumps(sidecar_payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("app.services.quiz_context.settings.data_dir", str(data_dir))

    seed = _seed(doc_id="doc-1", kb_id="kb-1", source="A.pdf", chunk=5, page=1, text="图1\n对称")
    entries = [
        _entry(doc_id="doc-1", kb_id="kb-1", source="A.pdf", chunk=5, page=1, text="图1\n对称"),
    ]

    with patch("app.services.quiz_context.get_doc_vector_entries", return_value=entries):
        result = build_quiz_context_from_seeds(
            user_id="u1",
            seed_docs=[seed],
            max_chars=4000,
            kb_scope=False,
        )

    assert "关于 y 轴对称" in result.text
    assert "x 坐标取反" in result.text
    assert result.stats.get("build_modes", {}).get("sidecar", 0) >= 1


def test_quiz_context_filters_latin_fragment_noise_seed():
    seed = _seed(
        doc_id="doc-noise",
        kb_id="kb-1",
        source="noise.txt",
        chunk=1,
        page=1,
        text="shRn\n么\n第四单元\n使",
    )
    clean_entry = _entry(
        doc_id="doc-noise",
        kb_id="kb-1",
        source="noise.txt",
        chunk=1,
        page=1,
        text="线性变换可以将平面中的点映射到新的位置。",
    )

    with patch("app.services.quiz_context.get_doc_vector_entries", return_value=[clean_entry]):
        result = build_quiz_context_from_seeds(
            user_id="u1",
            seed_docs=[seed],
            max_chars=1800,
            kb_scope=False,
        )

    assert "shRn" not in result.text
    assert "线性变换" in result.text


def test_quiz_context_filters_dotted_and_long_latin_noise_seed():
    seed = _seed(
        doc_id="doc-noise-2",
        kb_id="kb-1",
        source="noise.txt",
        chunk=2,
        page=1,
        text="人民教育出版社\ndaikocicn\nz.nyong\n作用",
    )
    clean_entry = _entry(
        doc_id="doc-noise-2",
        kb_id="kb-1",
        source="noise.txt",
        chunk=2,
        page=1,
        text="工具发明改变生活，带来便利。",
    )

    with patch("app.services.quiz_context.get_doc_vector_entries", return_value=[clean_entry]):
        result = build_quiz_context_from_seeds(
            user_id="u1",
            seed_docs=[seed],
            max_chars=1800,
            kb_scope=False,
        )

    assert "daikocicn" not in result.text
    assert "z.nyong" not in result.text
    assert "改变生活，带来便利" in result.text
