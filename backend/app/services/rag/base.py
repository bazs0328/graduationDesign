from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol


StageCallback = Callable[[str, int, str], None] | None


@dataclass(slots=True)
class RAGIngestRequest:
    file_path: str
    filename: str
    doc_id: str
    user_id: str
    kb_id: str
    mode: str = "auto"
    parse_policy: str = "balanced"
    preferred_parser: str = "auto"
    parser_preference: str = "mineru"
    stage_callback: StageCallback = None


@dataclass(slots=True)
class RAGIngestResult:
    text_path: str
    num_chunks: int
    num_pages: int
    char_count: int
    parser_provider: str
    extract_method: str
    quality_score: float | None
    diagnostics: dict
    timing: dict[str, float]
    rag_backend: str = "legacy"
    parser_engine: str | None = None
    fallback_chain: list[str] = field(default_factory=list)
    asset_stats: dict = field(default_factory=dict)
    assets: list[dict] = field(default_factory=list)


@dataclass(slots=True)
class RAGSearchRequest:
    user_id: str
    question: str
    kb_id: str
    doc_id: str | None = None
    top_k: int | None = None
    fetch_k: int | None = None
    mode: str = "hybrid"


@dataclass(slots=True)
class RAGSearchResult:
    sources: list[dict]
    context: str
    backend: str
    mode: str
    diagnostics: dict = field(default_factory=dict)


class RAGProvider(Protocol):
    backend_id: str

    def ingest(self, request: RAGIngestRequest) -> RAGIngestResult: ...

    def search(self, request: RAGSearchRequest) -> RAGSearchResult: ...

    def delete_doc(self, user_id: str, kb_id: str, doc_id: str) -> None: ...

    def health(self) -> dict: ...
