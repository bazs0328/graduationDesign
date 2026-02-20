from __future__ import annotations

from app.core.vectorstore import delete_doc_vectors
from app.services.ingest import IngestResult, ingest_document
from app.services.lexical import remove_doc_chunks
from app.services.qa_legacy import (
    build_sources_and_context_legacy,
    retrieve_documents_legacy,
)
from app.services.rag.base import (
    RAGIngestRequest,
    RAGIngestResult,
    RAGSearchRequest,
    RAGSearchResult,
)


class LegacyProvider:
    backend_id = "legacy"

    def ingest(self, request: RAGIngestRequest) -> RAGIngestResult:
        result = ingest_document(
            request.file_path,
            request.filename,
            request.doc_id,
            request.user_id,
            request.kb_id,
            mode=request.mode,
            parse_policy=request.parse_policy,
            preferred_parser=request.preferred_parser,
            stage_callback=request.stage_callback,
            return_details=True,
        )
        if not isinstance(result, IngestResult):
            raise RuntimeError("Legacy ingest returned unexpected result")
        return RAGIngestResult(
            text_path=result.text_path,
            num_chunks=result.num_chunks,
            num_pages=result.num_pages,
            char_count=result.char_count,
            parser_provider=result.parser_provider,
            extract_method=result.extract_method,
            quality_score=result.quality_score,
            diagnostics=result.diagnostics or {},
            timing=result.timing or {},
            rag_backend=self.backend_id,
            parser_engine=result.parser_provider,
            asset_stats={"total": 0, "by_type": {}},
            assets=[],
        )

    def search(self, request: RAGSearchRequest) -> RAGSearchResult:
        docs = retrieve_documents_legacy(
            request.user_id,
            request.question,
            doc_id=request.doc_id,
            kb_id=request.kb_id,
            top_k=request.top_k,
            fetch_k=request.fetch_k,
        )
        sources, context = build_sources_and_context_legacy(docs)
        return RAGSearchResult(
            sources=sources,
            context=context,
            backend=self.backend_id,
            mode="legacy",
            diagnostics={"fallback_chain": [], "provider": self.backend_id},
        )

    def delete_doc(self, user_id: str, kb_id: str, doc_id: str) -> None:
        delete_doc_vectors(user_id, doc_id)
        if kb_id:
            remove_doc_chunks(user_id, kb_id, doc_id)

    def health(self) -> dict:
        return {"backend": self.backend_id, "available": True}
