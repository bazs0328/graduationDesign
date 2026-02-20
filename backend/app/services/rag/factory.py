from __future__ import annotations

from app.core.config import settings
from app.core.kb_metadata import get_kb_rag_settings
from app.services.rag.base import RAGProvider
from app.services.rag.providers import LegacyProvider, RAGAnythingProvider


def get_rag_provider(
    user_id: str,
    kb_id: str,
) -> RAGProvider:
    rag_settings = get_kb_rag_settings(user_id, kb_id)
    backend = (rag_settings.get("rag_backend") or settings.rag_default_backend).strip().lower()
    query_mode = (rag_settings.get("query_mode") or settings.rag_query_mode).strip().lower()
    parser_preference = (
        rag_settings.get("parser_preference") or settings.rag_doc_parser_primary
    ).strip().lower()

    if backend in {"raganything_mineru", "raganything_docling"}:
        return RAGAnythingProvider(
            backend_id=backend,
            parser_preference=parser_preference,
            query_mode=query_mode,
            allow_legacy_fallback=settings.rag_fallback_to_legacy,
        )
    return LegacyProvider()
