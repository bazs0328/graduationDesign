"""Tests for provider auto-resolution in app.core.llm."""

import pytest

from app.core import llm
from app.core.config import settings


@pytest.fixture(autouse=True)
def _reset_provider_settings(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "auto")
    monkeypatch.setattr(settings, "embedding_provider", "auto")
    monkeypatch.setattr(settings, "qwen_api_key", None)
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    monkeypatch.setattr(settings, "deepseek_embedding_model", None)


def test_auto_provider_prefers_qwen_when_qwen_key_exists(monkeypatch):
    monkeypatch.setattr(settings, "qwen_api_key", "qwen_test_key")

    llm_provider, llm_configured, llm_source = llm.resolve_llm_provider(strict=True)
    emb_provider, emb_configured, emb_source = llm.resolve_embedding_provider(
        strict=True,
        resolved_llm_provider=llm_provider,
    )

    assert llm_provider == "qwen"
    assert llm_configured == "auto"
    assert llm_source == "auto"
    assert emb_provider == "qwen"
    assert emb_configured == "auto"
    assert emb_source == "auto"


def test_auto_provider_priority_qwen_over_deepseek(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "deepseek_test_key")
    monkeypatch.setattr(settings, "qwen_api_key", "qwen_test_key")

    provider, _, _ = llm.resolve_llm_provider(strict=True)
    assert provider == "qwen"


def test_legacy_openai_and_gemini_values_downgrade_to_auto(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "embedding_provider", "gemini")
    monkeypatch.setattr(settings, "qwen_api_key", "qwen_test_key")

    llm_provider, llm_configured, llm_source = llm.resolve_llm_provider(strict=True)
    emb_provider, emb_configured, emb_source = llm.resolve_embedding_provider(
        strict=True,
        resolved_llm_provider=llm_provider,
    )

    assert llm_provider == "qwen"
    assert llm_configured == "auto"
    assert llm_source == "auto"
    assert emb_provider == "qwen"
    assert emb_configured == "auto"
    assert emb_source == "auto"


def test_deprecated_deepseek_embedding_setting_falls_back_to_qwen(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "deepseek")
    monkeypatch.setattr(settings, "qwen_api_key", "qwen_test_key")

    provider, configured, source = llm.resolve_embedding_provider(
        strict=True,
        resolved_llm_provider="deepseek",
    )

    assert provider == "qwen"
    assert configured == "auto"
    assert source == "auto"


def test_auto_provider_raises_clear_error_when_no_key_configured():
    with pytest.raises(ValueError, match="No LLM provider is available"):
        llm.resolve_llm_provider(strict=True)

    with pytest.raises(ValueError, match="No embedding provider is available"):
        llm.resolve_embedding_provider(strict=True)
