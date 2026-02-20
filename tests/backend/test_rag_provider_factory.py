from app.core.config import settings
from app.services.rag.factory import get_rag_provider
from app.services.rag.providers import LegacyProvider, RAGAnythingProvider


def test_factory_selects_raganything_provider(monkeypatch):
    monkeypatch.setattr(
        "app.services.rag.factory.get_kb_rag_settings",
        lambda _user_id, _kb_id: {
            "rag_backend": "raganything_mineru",
            "query_mode": "hybrid",
            "parser_preference": "mineru",
        },
    )
    monkeypatch.setattr(settings, "rag_fallback_to_legacy", True, raising=False)

    provider = get_rag_provider("u1", "kb1")
    assert isinstance(provider, RAGAnythingProvider)
    assert provider.backend_id == "raganything_mineru"
    assert provider.query_mode == "hybrid"
    assert provider.parser_preference == "mineru"


def test_factory_selects_legacy_provider(monkeypatch):
    monkeypatch.setattr(
        "app.services.rag.factory.get_kb_rag_settings",
        lambda _user_id, _kb_id: {
            "rag_backend": "legacy",
            "query_mode": "hybrid",
            "parser_preference": "mineru",
        },
    )

    provider = get_rag_provider("u2", "kb2")
    assert isinstance(provider, LegacyProvider)


def test_factory_falls_back_to_default_backend(monkeypatch):
    monkeypatch.setattr(
        "app.services.rag.factory.get_kb_rag_settings",
        lambda _user_id, _kb_id: {},
    )
    monkeypatch.setattr(settings, "rag_default_backend", "legacy", raising=False)

    provider = get_rag_provider("u3", "kb3")
    assert isinstance(provider, LegacyProvider)
