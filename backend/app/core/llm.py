from __future__ import annotations

import dashscope
from langchain_core.embeddings import Embeddings
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import OpenAI

from app.core.config import settings

LLM_PROVIDERS = {"openai", "gemini", "deepseek", "qwen"}
EMBEDDING_PROVIDERS = {"openai", "gemini", "deepseek", "qwen", "dashscope"}
LLM_AUTO_PRIORITY = ("qwen", "openai", "deepseek", "gemini")
EMBEDDING_AUTO_FALLBACK_PRIORITY = ("openai", "qwen", "dashscope", "gemini", "deepseek")
DEEPSEEK_EMBEDDING_FALLBACK_PRIORITY = ("openai", "dashscope", "gemini")
_UNCONFIGURED_PROVIDER = "unconfigured"


class QwenEmbeddings(Embeddings):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        payload = [str(text) for text in texts]
        response = self.client.embeddings.create(model=self.model, input=payload)
        data = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class DashScopeVLEmbeddings(Embeddings):
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def _configure_client(self) -> None:
        import logging

        logger = logging.getLogger(__name__)
        dashscope.api_key = self.api_key
        if self.base_url:
            dashscope.base_http_api_url = self.base_url
            logger.debug("Using DashScope base URL: %s", self.base_url)

    def _parse_response_vector(self, resp):
        if not resp:
            raise ValueError("DashScope embedding failed: empty response")
        status_code = resp.get("status_code")
        code = resp.get("code")
        if status_code not in (200, "200") or code not in (None, "", 0, "0"):
            raise ValueError(f"DashScope embedding failed: {resp}")
        output = resp.get("output") or {}
        items = output.get("embeddings") or output.get("data") or []
        if not items:
            raise ValueError(f"DashScope embedding empty: {resp}")
        vector = items[0].get("embedding") or items[0].get("vector")
        if not isinstance(vector, list):
            raise ValueError(f"DashScope embedding invalid: {resp}")
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self._configure_client()
        embeddings = []
        for text in texts:
            try:
                resp = dashscope.MultiModalEmbedding.call(
                    model=self.model,
                    input=[{"text": str(text)}],
                )
            except Exception as exc:
                error_msg = str(exc)
                if "Failed to resolve" in error_msg or "No address associated" in error_msg:
                    raise ConnectionError(
                        "DashScope DNS resolution failed. If you're outside China, set "
                        "DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1 "
                        f"or switch to EMBEDDING_PROVIDER=qwen. Error: {error_msg}"
                    ) from exc
                raise ValueError(f"DashScope embedding API call failed: {error_msg}") from exc

            embeddings.append(self._parse_response_vector(resp))
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def _normalize_provider(value: str | None, *, kind: str) -> str:
    normalized = str(value or "").strip().lower() or "auto"
    if kind == "embedding" and normalized in {"qwen_vl", "qwen3_vl"}:
        return "dashscope"
    return normalized


def _is_configured(text: str | None) -> bool:
    return bool((text or "").strip())


def _llm_provider_ready(provider: str) -> bool:
    if provider == "openai":
        return _is_configured(settings.openai_api_key)
    if provider == "deepseek":
        return _is_configured(settings.deepseek_api_key)
    if provider == "gemini":
        return _is_configured(settings.google_api_key)
    if provider == "qwen":
        return _is_configured(settings.qwen_api_key)
    return False


def _embedding_provider_ready(provider: str) -> bool:
    if provider == "openai":
        return _is_configured(settings.openai_api_key)
    if provider in {"qwen", "dashscope"}:
        return _is_configured(settings.qwen_api_key)
    if provider == "gemini":
        return _is_configured(settings.google_api_key)
    if provider == "deepseek":
        return _is_configured(settings.deepseek_api_key) and _is_configured(settings.deepseek_embedding_model)
    return False


def _resolve_deepseek_embedding_provider(*, strict: bool) -> str | None:
    model = (settings.deepseek_embedding_model or "").strip()
    has_key = _is_configured(settings.deepseek_api_key)
    if model:
        if has_key:
            return "deepseek"
        if strict:
            raise ValueError("DEEPSEEK_API_KEY is not set")
        return None

    for provider in DEEPSEEK_EMBEDDING_FALLBACK_PRIORITY:
        if _embedding_provider_ready(provider):
            return provider

    if strict:
        raise ValueError(
            "DeepSeek embeddings not configured. Set DEEPSEEK_EMBEDDING_MODEL or configure one of "
            "OPENAI_API_KEY / QWEN_API_KEY / GOOGLE_API_KEY."
        )
    return None


def _embedding_provider_following_llm(provider: str | None) -> str | None:
    if provider in {"openai", "qwen", "gemini", "deepseek"}:
        return provider
    return None


def resolve_llm_provider(*, strict: bool = True) -> tuple[str, str, str]:
    configured = _normalize_provider(settings.llm_provider, kind="llm")
    if configured == "auto":
        for provider in LLM_AUTO_PRIORITY:
            if _llm_provider_ready(provider):
                return provider, configured, "auto"
        if strict:
            raise ValueError(
                "No LLM provider is available. Configure one of "
                "QWEN_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY / GOOGLE_API_KEY."
            )
        return _UNCONFIGURED_PROVIDER, configured, "auto"

    if configured not in LLM_PROVIDERS:
        raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
    if strict and not _llm_provider_ready(configured):
        if configured == "openai":
            raise ValueError("OPENAI_API_KEY is not set")
        if configured == "deepseek":
            raise ValueError("DEEPSEEK_API_KEY is not set")
        if configured == "gemini":
            raise ValueError("GOOGLE_API_KEY is not set")
        if configured == "qwen":
            raise ValueError("QWEN_API_KEY is not set")
    return configured, configured, "manual"


def resolve_embedding_provider(*, strict: bool = True, resolved_llm_provider: str | None = None) -> tuple[str, str, str]:
    configured = _normalize_provider(settings.embedding_provider, kind="embedding")
    if configured == "auto":
        llm_provider = resolved_llm_provider
        if not llm_provider:
            llm_provider, _, _ = resolve_llm_provider(strict=False)
            if llm_provider == _UNCONFIGURED_PROVIDER:
                llm_provider = None

        follow_provider = _embedding_provider_following_llm(llm_provider)
        if follow_provider == "deepseek":
            deepseek_target = _resolve_deepseek_embedding_provider(strict=False)
            if deepseek_target:
                return deepseek_target, configured, "auto"
        elif follow_provider and _embedding_provider_ready(follow_provider):
            return follow_provider, configured, "auto"

        for provider in EMBEDDING_AUTO_FALLBACK_PRIORITY:
            if provider == "deepseek":
                deepseek_target = _resolve_deepseek_embedding_provider(strict=False)
                if deepseek_target:
                    return deepseek_target, configured, "auto"
                continue
            if _embedding_provider_ready(provider):
                return provider, configured, "auto"

        if strict:
            raise ValueError(
                "No embedding provider is available. Configure one of "
                "OPENAI_API_KEY / QWEN_API_KEY / GOOGLE_API_KEY or "
                "set DEEPSEEK_API_KEY + DEEPSEEK_EMBEDDING_MODEL."
            )
        return _UNCONFIGURED_PROVIDER, configured, "auto"

    if configured not in EMBEDDING_PROVIDERS:
        raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")

    if configured == "deepseek":
        deepseek_target = _resolve_deepseek_embedding_provider(strict=strict)
        if deepseek_target:
            return deepseek_target, configured, "manual"
        return configured, configured, "manual"

    if strict and not _embedding_provider_ready(configured):
        if configured == "openai":
            raise ValueError("OPENAI_API_KEY is not set")
        if configured in {"qwen", "dashscope"}:
            raise ValueError("QWEN_API_KEY is not set")
        if configured == "gemini":
            raise ValueError("GOOGLE_API_KEY is not set")
    return configured, configured, "manual"


def llm_provider_status() -> dict[str, str]:
    resolved, configured, source = resolve_llm_provider(strict=False)
    return {
        "resolved": resolved,
        "configured": configured,
        "source": source,
    }


def embedding_provider_status(*, resolved_llm_provider: str | None = None) -> dict[str, str]:
    resolved, configured, source = resolve_embedding_provider(
        strict=False,
        resolved_llm_provider=resolved_llm_provider,
    )
    return {
        "resolved": resolved,
        "configured": configured,
        "source": source,
    }


def get_llm(temperature: float = 0.2):
    provider, _, _ = resolve_llm_provider(strict=True)
    if provider == "openai":
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=temperature,
        )
    if provider == "deepseek":
        return ChatOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            temperature=temperature,
        )
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            google_api_key=settings.google_api_key,
            model=settings.gemini_model,
            temperature=temperature,
        )
    if provider == "qwen":
        return ChatOpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            model=settings.qwen_model,
            temperature=temperature,
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")


def get_embeddings():
    llm_provider, _, _ = resolve_llm_provider(strict=False)
    if llm_provider == _UNCONFIGURED_PROVIDER:
        llm_provider = None
    provider, _, _ = resolve_embedding_provider(
        strict=True,
        resolved_llm_provider=llm_provider,
    )
    if provider == "openai":
        return OpenAIEmbeddings(
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
        )
    if provider == "qwen":
        return QwenEmbeddings(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            model=settings.qwen_embedding_model,
        )
    if provider == "dashscope":
        # Use international endpoint if configured, otherwise use default (China region)
        return DashScopeVLEmbeddings(
            api_key=settings.qwen_api_key,
            model=settings.dashscope_embedding_model,
            base_url=settings.dashscope_base_url,
        )
    if provider == "deepseek":
        return OpenAIEmbeddings(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_embedding_model,
        )
    if provider == "gemini":
        return GoogleGenerativeAIEmbeddings(
            google_api_key=settings.google_api_key,
            model=settings.gemini_embedding_model,
        )
    raise ValueError(f"Unsupported embedding provider: {provider}")
