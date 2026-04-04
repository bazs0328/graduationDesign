"""Tests for adaptive QA prompt behavior."""

from types import SimpleNamespace

from langchain_core.documents import Document

from app.services.qa import (
    _is_summary_like_question,
    _resolve_dynamic_retrieval_window,
    _resolve_retrieval_window,
    _strip_inline_source_markers,
    build_adaptive_system_prompt,
    build_explain_system_prompt,
    build_sources_and_context,
    retrieve_documents,
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


def test_resolve_dynamic_retrieval_window_expands_for_complex_large_kb_question():
    k, fetch_k = _resolve_dynamic_retrieval_window(
        question="请总结这个资料库里关于矩阵的核心知识点",
        retrieval_preset="balanced",
        scope_stats={"scope": "kb", "doc_count": 8, "total_chunks": 360},
    )

    assert k == 8
    assert fetch_k == 28


def test_resolve_dynamic_retrieval_window_adds_medium_complexity_for_rewritten_followup():
    k, fetch_k = _resolve_dynamic_retrieval_window(
        question="这个呢",
        retrieval_preset="fast",
        scope_stats={"scope": "doc", "num_chunks": 20, "num_pages": 5},
        rewritten_for_retrieval=True,
    )

    assert k == 4
    assert fetch_k == 12


def test_resolve_dynamic_retrieval_window_expands_for_large_doc_scope():
    k, fetch_k = _resolve_dynamic_retrieval_window(
        question="矩阵是什么",
        retrieval_preset="deep",
        scope_stats={"scope": "doc", "num_chunks": 160, "num_pages": 48},
    )

    assert k == 7
    assert fetch_k == 24


def test_retrieve_documents_retries_low_coverage_with_dynamic_window(monkeypatch):
    monkeypatch.setattr(qa_service.settings, "rag_mode", "dense")
    monkeypatch.setattr(qa_service.settings, "qa_dynamic_window_enabled", True)
    monkeypatch.setattr(qa_service.settings, "noise_drop_low_quality_hits", True)

    calls: list[tuple[int, int]] = []
    first_docs = [
        Document(
            page_content="简短片段",
            metadata={"doc_id": "doc-1", "kb_id": "kb-1", "page": 1, "chunk": 1},
        )
    ]
    second_docs = [
        Document(
            page_content="矩阵基础知识。" * 80,
            metadata={"doc_id": "doc-1", "kb_id": "kb-1", "page": 1, "chunk": 1},
        ),
        Document(
            page_content="线性变换与矩阵关系。" * 60,
            metadata={"doc_id": "doc-2", "kb_id": "kb-1", "page": 2, "chunk": 2},
        ),
    ]

    def _mmr_search(question, k, fetch_k, filter):  # noqa: A002
        calls.append((k, fetch_k))
        if len(calls) == 1:
            return first_docs
        return second_docs

    vectorstore = SimpleNamespace(max_marginal_relevance_search=_mmr_search)
    monkeypatch.setattr(qa_service, "get_vectorstore", lambda _user_id: vectorstore)

    docs = retrieve_documents(
        user_id="u1",
        question="请总结这个资料库里关于矩阵的核心知识点",
        kb_id="kb-1",
        retrieval_preset="balanced",
        scope_stats={"scope": "kb", "doc_count": 8, "total_chunks": 360},
    )

    assert calls == [(8, 28), (12, 50)]
    assert len(docs) == 2
    assert docs[0].metadata["doc_id"] == "doc-1"


def test_retrieve_documents_uses_static_fallback_when_dynamic_window_disabled(monkeypatch):
    monkeypatch.setattr(qa_service.settings, "rag_mode", "dense")
    monkeypatch.setattr(qa_service.settings, "qa_dynamic_window_enabled", False)

    calls: list[tuple[int, int]] = []

    def _mmr_search(question, k, fetch_k, filter):  # noqa: A002
        calls.append((k, fetch_k))
        return [
            Document(
                page_content="矩阵定义。" * 40,
                metadata={"doc_id": "doc-1", "kb_id": "kb-1", "page": 1, "chunk": 1},
            )
        ]

    vectorstore = SimpleNamespace(max_marginal_relevance_search=_mmr_search)
    monkeypatch.setattr(qa_service, "get_vectorstore", lambda _user_id: vectorstore)

    retrieve_documents(
        user_id="u1",
        question="矩阵是什么",
        kb_id="kb-1",
        retrieval_preset="deep",
        top_k=4,
        fetch_k=12,
    )

    assert calls == [(4, 12)]


def test_retrieve_documents_expands_bm25_window_in_hybrid_mode(monkeypatch):
    monkeypatch.setattr(qa_service.settings, "rag_mode", "hybrid")
    monkeypatch.setattr(qa_service.settings, "qa_dynamic_window_enabled", True)
    monkeypatch.setattr(qa_service.settings, "qa_bm25_k", 6)

    long_doc_a = Document(
        page_content="矩阵的定义与性质。" * 50,
        metadata={"doc_id": "doc-1", "kb_id": "kb-1", "page": 1, "chunk": 1},
    )
    long_doc_b = Document(
        page_content="不同矩阵运算之间的关系。" * 50,
        metadata={"doc_id": "doc-2", "kb_id": "kb-1", "page": 2, "chunk": 2},
    )

    vectorstore = SimpleNamespace(
        similarity_search_with_relevance_scores=lambda question, k, filter: [
            (long_doc_a, 0.9),
            (long_doc_b, 0.8),
        ]
    )
    monkeypatch.setattr(qa_service, "get_vectorstore", lambda _user_id: vectorstore)

    lexical_calls: list[int] = []

    def _bm25_search(user_id, kb_id, question, top_k, doc_id=None):
        lexical_calls.append(top_k)
        return []

    monkeypatch.setattr(qa_service, "bm25_search", _bm25_search)

    docs = retrieve_documents(
        user_id="u1",
        question="请总结这个资料库里关于矩阵的核心知识点",
        kb_id="kb-1",
        retrieval_preset="balanced",
        scope_stats={"scope": "kb", "doc_count": 8, "total_chunks": 360},
    )

    assert lexical_calls == [28]
    assert len(docs) == 2
