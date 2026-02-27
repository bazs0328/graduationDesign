"""Tests for adaptive QA prompt behavior."""

from langchain_core.documents import Document

from app.services.qa import (
    _is_summary_like_question,
    _resolve_retrieval_window,
    _strip_inline_source_markers,
    build_adaptive_system_prompt,
    build_explain_system_prompt,
    build_sources_and_context,
)
from app.services import qa as qa_service


def test_adaptive_system_prompt_differs_by_ability_level():
    """Different ability levels should produce clearly different prompts."""
    beginner_prompt = build_adaptive_system_prompt(ability_level="beginner")
    advanced_prompt = build_adaptive_system_prompt(ability_level="advanced")

    assert beginner_prompt != advanced_prompt
    assert "初学者" in beginner_prompt
    assert "高水平学习者" in advanced_prompt


def test_adaptive_system_prompt_includes_weak_concepts():
    """Weak concepts should be included in system prompt hints."""
    prompt = build_adaptive_system_prompt(
        ability_level="intermediate",
        weak_concepts=["矩阵", "特征值"],
    )

    assert "薄弱知识点" in prompt
    assert "矩阵" in prompt
    assert "特征值" in prompt


def test_explain_system_prompt_requires_fixed_sections():
    prompt = build_explain_system_prompt(ability_level="intermediate")

    assert "讲解模式" in prompt
    assert "## 标题" in prompt
    assert "题意理解" in prompt
    assert "相关知识点" in prompt
    assert "分步解答" in prompt
    assert "易错点" in prompt
    assert "自测问题" in prompt


def test_strip_inline_source_markers_removes_citations_and_page_chunk_markers():
    raw = "答案如下[1][2]。见 p.19 c.177 与 p.3 c.12。"
    cleaned = _strip_inline_source_markers(raw)
    assert "[1]" not in cleaned and "[2]" not in cleaned
    assert "p.19 c.177" not in cleaned
    assert "p.3 c.12" not in cleaned
    assert "答案如下" in cleaned


def test_build_sources_and_context_returns_text_only_sources():
    docs = [
        Document(
            page_content="矩阵是线性代数中的基础对象。",
            metadata={
                "doc_id": "doc-1",
                "kb_id": "kb-1",
                "source": "sample.pdf",
                "page": 1,
                "chunk": 3,
            },
        )
    ]

    sources, context = build_sources_and_context(docs, user_id="u1")

    assert len(sources) == 1
    assert set(sources[0].keys()) == {"source", "snippet", "doc_id", "kb_id", "page", "chunk"}
    assert "矩阵" in sources[0]["snippet"]
    assert "[1] Source:" in context
    assert "线性代数" in context


def test_build_sources_and_context_filters_low_quality_snippet():
    docs = [
        Document(
            page_content="shRn\n么\n第四单元\n使",
            metadata={
                "doc_id": "doc-1",
                "kb_id": "kb-1",
                "source": "sample.pdf",
                "page": 1,
                "chunk": 1,
            },
        )
    ]

    sources, context = build_sources_and_context(docs, user_id="u1")

    assert len(sources) == 1
    assert sources[0]["snippet"] == ""
    assert "shRn" not in context


def test_summary_like_question_detection():
    assert _is_summary_like_question("请总结这一章的重点内容")
    assert _is_summary_like_question("Can you summarize this chapter?")
    assert not _is_summary_like_question("矩阵的特征值怎么计算？")


def test_resolve_retrieval_window_expands_for_summary_question(monkeypatch):
    monkeypatch.setattr(qa_service.settings, "qa_top_k", 4)
    monkeypatch.setattr(qa_service.settings, "qa_fetch_k", 12)
    monkeypatch.setattr(qa_service.settings, "qa_summary_auto_expand_enabled", True)
    monkeypatch.setattr(qa_service.settings, "qa_summary_top_k", 8)
    monkeypatch.setattr(qa_service.settings, "qa_summary_fetch_k", 28)

    k, fetch_k = _resolve_retrieval_window(
        question="请总结这个文档的核心知识点",
        top_k=4,
        fetch_k=12,
    )

    assert k == 8
    assert fetch_k == 28


def test_resolve_retrieval_window_keeps_larger_manual_values(monkeypatch):
    monkeypatch.setattr(qa_service.settings, "qa_top_k", 4)
    monkeypatch.setattr(qa_service.settings, "qa_fetch_k", 12)
    monkeypatch.setattr(qa_service.settings, "qa_summary_auto_expand_enabled", True)
    monkeypatch.setattr(qa_service.settings, "qa_summary_top_k", 8)
    monkeypatch.setattr(qa_service.settings, "qa_summary_fetch_k", 28)

    k, fetch_k = _resolve_retrieval_window(
        question="summary this section",
        top_k=10,
        fetch_k=40,
    )

    assert k == 10
    assert fetch_k == 40


def test_resolve_retrieval_window_does_not_expand_when_disabled(monkeypatch):
    monkeypatch.setattr(qa_service.settings, "qa_top_k", 4)
    monkeypatch.setattr(qa_service.settings, "qa_fetch_k", 12)
    monkeypatch.setattr(qa_service.settings, "qa_summary_auto_expand_enabled", False)
    monkeypatch.setattr(qa_service.settings, "qa_summary_top_k", 8)
    monkeypatch.setattr(qa_service.settings, "qa_summary_fetch_k", 28)

    k, fetch_k = _resolve_retrieval_window(
        question="请总结这个文档",
        top_k=4,
        fetch_k=12,
    )

    assert k == 4
    assert fetch_k == 12
