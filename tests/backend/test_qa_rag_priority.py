from unittest.mock import patch

from app.services.qa import _retrieve_context_and_sources
from app.services.rag.base import RAGSearchResult


def test_qa_prefers_rag_provider_when_context_available():
    class _Provider:
        def search(self, _request):
            return RAGSearchResult(
                sources=[{"source": "doc p.1 c.0", "snippet": "rag snippet"}],
                context="[1] Source: doc p.1 c.0\nrag context",
                backend="raganything_mineru",
                mode="hybrid",
            )

    with (
        patch("app.services.qa.get_rag_provider", return_value=_Provider()),
        patch("app.services.qa.retrieve_documents_legacy") as legacy_retrieve_mock,
    ):
        sources, context = _retrieve_context_and_sources(
            user_id="u1",
            question="什么是矩阵",
            kb_id="kb1",
            top_k=4,
        )

    assert "rag context" in context
    assert len(sources) == 1
    legacy_retrieve_mock.assert_not_called()


def test_qa_falls_back_to_legacy_when_rag_fails():
    docs = [{"page_content": "legacy context"}]
    legacy_sources = [{"source": "doc p.2 c.1", "snippet": "legacy snippet"}]
    legacy_context = "[1] Source: doc p.2 c.1\nlegacy context"

    with (
        patch("app.services.qa.get_rag_provider", side_effect=RuntimeError("rag down")),
        patch("app.services.qa.retrieve_documents_legacy", return_value=docs),
        patch(
            "app.services.qa.build_sources_and_context_legacy",
            return_value=(legacy_sources, legacy_context),
        ),
    ):
        sources, context = _retrieve_context_and_sources(
            user_id="u2",
            question="问一个问题",
            kb_id="kb2",
        )

    assert sources == legacy_sources
    assert context == legacy_context
