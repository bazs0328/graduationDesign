from __future__ import annotations

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.embeddings import Embeddings
from openai import OpenAI
import dashscope

from app.core.config import settings


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
            logger.debug(f"Using DashScope base URL: {self.base_url}")

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
        import logging
        logger = logging.getLogger(__name__)

        self._configure_client()
        embeddings = []
        for text in texts:
            try:
                resp = dashscope.MultiModalEmbedding.call(
                    model=self.model,
                    input=[{"text": str(text)}],
                )
            except Exception as e:
                error_msg = str(e)
                if "Failed to resolve" in error_msg or "No address associated" in error_msg:
                    raise ConnectionError(
                        f"DashScope DNS resolution failed. "
                        f"If you're outside China, set DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1 "
                        f"or switch to EMBEDDING_PROVIDER=qwen. Error: {error_msg}"
                    ) from e
                raise ValueError(f"DashScope embedding API call failed: {error_msg}") from e

            embeddings.append(self._parse_response_vector(resp))
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def get_llm(temperature: float = 0.2):
    provider = settings.llm_provider.lower()
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=temperature,
        )
    if provider == "deepseek":
        if not settings.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY is not set")
        return ChatOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            temperature=temperature,
        )
    if provider == "gemini":
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is not set")
        return ChatGoogleGenerativeAI(
            google_api_key=settings.google_api_key,
            model=settings.gemini_model,
            temperature=temperature,
        )
    if provider == "qwen":
        if not settings.qwen_api_key:
            raise ValueError("QWEN_API_KEY is not set")
        return ChatOpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            model=settings.qwen_model,
            temperature=temperature,
        )
    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")


def get_embeddings():
    provider = settings.embedding_provider.lower()
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        return OpenAIEmbeddings(
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
        )
    if provider == "qwen":
        if not settings.qwen_api_key:
            raise ValueError("QWEN_API_KEY is not set")
        return QwenEmbeddings(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            model=settings.qwen_embedding_model,
        )
    if provider in ("dashscope", "qwen_vl", "qwen3_vl"):
        if not settings.qwen_api_key:
            raise ValueError("QWEN_API_KEY is not set")
        # Use international endpoint if configured, otherwise use default (China region)
        base_url = settings.dashscope_base_url
        return DashScopeVLEmbeddings(
            api_key=settings.qwen_api_key,
            model=settings.dashscope_embedding_model,
            base_url=base_url,
        )
    if provider == "deepseek":
        if settings.deepseek_embedding_model:
            if not settings.deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY is not set")
            return OpenAIEmbeddings(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                model=settings.deepseek_embedding_model,
            )
        # Fallback to OpenAI embeddings if DeepSeek doesn't provide embeddings
        if settings.openai_api_key:
            return OpenAIEmbeddings(
                api_key=settings.openai_api_key,
                model=settings.openai_embedding_model,
            )
        raise ValueError(
            "DeepSeek embeddings not configured. Set DEEPSEEK_EMBEDDING_MODEL or provide OPENAI_API_KEY."
        )
    if provider == "gemini":
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is not set")
        return GoogleGenerativeAIEmbeddings(
            google_api_key=settings.google_api_key,
            model=settings.gemini_embedding_model,
        )
    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")
