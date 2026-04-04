"""Tests for keypoint extraction quality post-processing."""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import app.services.keypoints as kp
from app.utils.chroma_filters import build_chroma_eq_filter


def test_postprocess_keypoints_dedupes_numbering_and_whitespace_variants():
    points = [
        {"text": "1. 矩阵定义"},
        {"text": "矩阵定义"},
        {"text": " 矩阵 定义 "},
    ]

    kept, diag = kp._postprocess_extracted_keypoints(points, mode="final")

    assert [p["text"] for p in kept] == ["1. 矩阵定义"]
    assert diag["kept_count"] == 1
    assert diag["dropped_duplicate"] == 2


def test_postprocess_keypoints_filters_generic_items_in_final_mode_but_not_chunk():
    points = [
        {"text": "重要概念"},
        {"text": "核心知识点"},
        {"text": "矩阵的秩定义"},
    ]

    final_kept, final_diag = kp._postprocess_extracted_keypoints(points, mode="final")
    chunk_kept, chunk_diag = kp._postprocess_extracted_keypoints(points, mode="chunk")

    assert [p["text"] for p in final_kept] == ["矩阵的秩定义"]
    assert final_diag["dropped_generic"] == 2
    assert [p["text"] for p in chunk_kept] == ["重要概念", "核心知识点", "矩阵的秩定义"]
    assert chunk_diag["dropped_generic"] == 0


def test_postprocess_keypoints_filters_heading_like_text():
    points = [
        {"text": "参考文献"},
        {"text": "第一章节"},
        {"text": "特征值与特征向量"},
    ]

    kept, diag = kp._postprocess_extracted_keypoints(points, mode="final")

    assert [p["text"] for p in kept] == ["特征值与特征向量"]
    assert diag["dropped_heading_like"] >= 2


def test_postprocess_keypoints_filters_length_outliers_and_relaxed_fallback_keeps_them():
    too_long = (
        "这是一个明显超过四十个字符的知识点文本用于验证长度过滤规则不会误伤正常短文本"
        "并且继续补充一些描述确保长度一定超过阈值"
    )
    points = [
        {"text": "定义"},
        {"text": too_long},
        {"text": "矩阵乘法条件"},
    ]

    final_kept, final_diag = kp._postprocess_extracted_keypoints(points, mode="final")
    relaxed_kept, relaxed_diag = kp._postprocess_extracted_keypoints(
        points, mode="final_relaxed_fallback"
    )

    assert [p["text"] for p in final_kept] == ["矩阵乘法条件"]
    assert final_diag["dropped_length"] == 2
    assert [p["text"] for p in relaxed_kept] == ["定义", too_long, "矩阵乘法条件"]
    assert relaxed_diag["dropped_length"] == 0


def test_clean_keypoint_explanation_compacts_truncates_and_drops_redundant_text():
    assert kp._clean_keypoint_explanation("  矩阵定义  ", text="矩阵定义") is None

    cleaned = kp._clean_keypoint_explanation("  解释   里   有   多个空格  ", text="矩阵")
    assert cleaned == "解释 里 有 多个空格"

    long_exp = "说明" * 100
    truncated = kp._clean_keypoint_explanation(long_exp, text="矩阵")
    assert truncated is not None
    assert len(truncated) <= kp._KP_MAX_EXPLANATION_LEN


def test_postprocess_keypoints_preserves_order_after_filtering():
    points = [
        {"text": "重要概念"},
        {"text": "线性变换定义"},
        {"text": "1. 线性变换定义"},
        {"text": "矩阵的秩"},
        {"text": "参考文献"},
        {"text": "向量空间基底"},
    ]

    kept, diag = kp._postprocess_extracted_keypoints(points, mode="final")

    assert [p["text"] for p in kept] == ["线性变换定义", "矩阵的秩", "向量空间基底"]
    assert diag["dropped_generic"] == 1
    assert diag["dropped_duplicate"] == 1
    assert diag["dropped_heading_like"] == 1


class _FakeSplitter:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def split_text(self, text: str) -> list[str]:
        return [text]


class _FakeAsyncLLM:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    async def ainvoke(self, _msg):
        self.calls += 1
        content = self._responses.pop(0)
        return SimpleNamespace(content=content)


def test_extract_keypoints_applies_strict_final_postprocess_and_attaches_source(monkeypatch):
    llm = _FakeAsyncLLM(
        [
            json.dumps(
                [{"text": "1. 矩阵定义"}, {"text": "矩阵定义"}, {"text": " "}],
                ensure_ascii=False,
            ),
            json.dumps(
                [{"text": "重要概念"}, {"text": "矩阵乘法条件", "explanation": "  乘法条件  "}],
                ensure_ascii=False,
            ),
        ]
    )
    attach_calls: list[tuple[str, str, str]] = []

    def _fake_attach_source(user_id: str, doc_id: str, point: dict) -> dict:
        attach_calls.append((user_id, doc_id, point["text"]))
        point["source"] = "doc.pdf"
        point["page"] = 1
        point["chunk"] = 0
        return point

    monkeypatch.setattr(kp, "get_llm", lambda temperature=0.2: llm)
    monkeypatch.setattr(kp, "RecursiveCharacterTextSplitter", _FakeSplitter)
    monkeypatch.setattr(kp, "_attach_source", _fake_attach_source)

    result = asyncio.run(kp.extract_keypoints("dummy text", user_id="u1", doc_id="d1"))

    assert llm.calls == 2
    assert [p["text"] for p in result] == ["矩阵乘法条件"]
    assert result[0]["source"] == "doc.pdf"
    assert attach_calls == [("u1", "d1", "矩阵乘法条件")]


def test_extract_keypoints_uses_relaxed_fallback_when_strict_final_filters_everything(
    monkeypatch, caplog
):
    llm = _FakeAsyncLLM(
        [
            json.dumps([{"text": "矩阵定义"}], ensure_ascii=False),
            json.dumps([{"text": "重要概念"}, {"text": "核心知识点"}], ensure_ascii=False),
        ]
    )

    monkeypatch.setattr(kp, "get_llm", lambda temperature=0.2: llm)
    monkeypatch.setattr(kp, "RecursiveCharacterTextSplitter", _FakeSplitter)

    caplog.set_level(logging.INFO, logger=kp.__name__)
    result = asyncio.run(kp.extract_keypoints("dummy text"))

    assert [p["text"] for p in result] == ["重要概念", "核心知识点"]
    assert any(
        "keypoints.extract.final_summary" in record.message
        and "'postprocess_relaxed_fallback': True" in record.message
        for record in caplog.records
    )


def test_match_keypoints_by_concepts_uses_chroma_and_filter(monkeypatch):
    vectorstore = Mock()
    vectorstore.similarity_search_with_score.return_value = []
    monkeypatch.setattr(kp, "get_vectorstore", lambda user_id: vectorstore)

    result = kp.match_keypoints_by_concepts("u1", "doc-1", ["矩阵"])

    assert result == []
    vectorstore.similarity_search_with_score.assert_called_once()
    _, kwargs = vectorstore.similarity_search_with_score.call_args
    assert kwargs["filter"] == build_chroma_eq_filter(doc_id="doc-1", type="keypoint")


def test_match_keypoints_by_kb_uses_chroma_and_filter(monkeypatch):
    vectorstore = Mock()
    vectorstore.similarity_search_with_score.return_value = []
    monkeypatch.setattr(kp, "get_vectorstore", lambda user_id: vectorstore)

    result = kp.match_keypoints_by_kb("u1", "kb-1", ["矩阵"])

    assert result == []
    vectorstore.similarity_search_with_score.assert_called_once()
    _, kwargs = vectorstore.similarity_search_with_score.call_args
    assert kwargs["filter"] == build_chroma_eq_filter(kb_id="kb-1", type="keypoint")


def test_save_keypoints_to_db_overwrite_deletes_vectors_with_chroma_and_filter(monkeypatch):
    db = Mock()
    db.query.return_value.filter.return_value.delete.return_value = 0
    vectorstore = Mock()
    monkeypatch.setattr(kp, "get_vectorstore", lambda user_id: vectorstore)

    result = kp.save_keypoints_to_db(
        db,
        "u1",
        "doc-1",
        [],
        kb_id="kb-1",
        overwrite=True,
    )

    assert result == []
    vectorstore.delete.assert_called_once_with(
        where=build_chroma_eq_filter(doc_id="doc-1", type="keypoint")
    )
