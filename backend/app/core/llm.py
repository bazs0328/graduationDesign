from __future__ import annotations

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.embeddings import HuggingFaceBgeEmbeddings

from app.core.config import settings


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
    if provider in ("bgem3", "bge-m3", "bge_m3"):
        return HuggingFaceBgeEmbeddings(
            model_name=settings.bge_m3_model,
            model_kwargs={"device": settings.embeddings_device},
            encode_kwargs={"normalize_embeddings": True},
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
