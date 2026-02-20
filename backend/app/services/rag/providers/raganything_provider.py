from __future__ import annotations

import json
import os
import re
from typing import Any

from app.core.config import settings
from app.core.paths import kb_base_dir
from app.core.vectorstore import get_doc_vector_entries
from app.services.rag.base import (
    RAGIngestRequest,
    RAGIngestResult,
    RAGSearchRequest,
    RAGSearchResult,
)
from .legacy_provider import LegacyProvider


class RAGAnythingProvider:
    backend_id = "raganything_mineru"

    def __init__(
        self,
        backend_id: str = "raganything_mineru",
        parser_preference: str = "mineru",
        query_mode: str = "hybrid",
        allow_legacy_fallback: bool = True,
    ):
        self.backend_id = backend_id
        self.parser_preference = (parser_preference or "mineru").strip().lower()
        self.query_mode = (query_mode or "hybrid").strip().lower()
        self.allow_legacy_fallback = bool(allow_legacy_fallback)
        self._legacy = LegacyProvider()

    @staticmethod
    def _raganything_available() -> bool:
        if not settings.raganything_enabled:
            return False
        try:
            import raganything  # type: ignore  # noqa: F401

            return True
        except Exception:
            return False

    def _resolve_parser_engine(self, request: RAGIngestRequest) -> tuple[str, list[str], str]:
        fallback_chain: list[str] = []
        preferred = (request.parser_preference or self.parser_preference or "mineru").strip().lower()
        parser_engine = preferred if preferred in {"mineru", "docling"} else "mineru"
        preferred_parser = "docling" if parser_engine == "docling" else request.preferred_parser

        if parser_engine == "mineru" and not self._raganything_available():
            fallback_chain.append("mineru_unavailable")
            parser_engine = settings.rag_doc_parser_fallback.strip().lower() or "docling"
            if parser_engine not in {"docling", "native", "auto"}:
                parser_engine = "docling"
            preferred_parser = "docling" if parser_engine == "docling" else "auto"

        return parser_engine, fallback_chain, preferred_parser

    @staticmethod
    def _asset_stats_from_diagnostics(diagnostics: dict[str, Any], parser_engine: str) -> dict[str, Any]:
        docling_stats = (diagnostics or {}).get("docling_stats") or {}
        placeholders = int(docling_stats.get("image_placeholders") or 0)
        by_type = {"image": placeholders} if placeholders > 0 else {}
        return {
            "total": placeholders,
            "by_type": by_type,
            "parser_engine": parser_engine,
        }

    @staticmethod
    def _source_map_dir(user_id: str, kb_id: str) -> str:
        base = kb_base_dir(user_id, kb_id)
        path = os.path.join(base, "source_map")
        os.makedirs(path, exist_ok=True)
        return path

    def _write_source_map(
        self,
        user_id: str,
        kb_id: str,
        doc_id: str,
        filename: str,
        *,
        parser_engine: str,
    ) -> None:
        entries = get_doc_vector_entries(user_id, doc_id)
        map_path = os.path.join(self._source_map_dir(user_id, kb_id), f"{doc_id}.jsonl")
        with open(map_path, "w", encoding="utf-8") as f:
            for row in entries:
                metadata = dict(row.get("metadata") or {})
                payload = {
                    "doc_id": doc_id,
                    "kb_id": kb_id,
                    "source": metadata.get("source") or filename,
                    "page": metadata.get("page"),
                    "chunk": metadata.get("chunk"),
                    "text": row.get("content") or "",
                    "modality": metadata.get("modality") or "text",
                    "asset_id": metadata.get("asset_id"),
                    "asset_url": metadata.get("asset_url"),
                    "asset_caption": metadata.get("asset_caption"),
                    "score": None,
                    "parser_engine": parser_engine,
                }
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def ingest(self, request: RAGIngestRequest) -> RAGIngestResult:
        parser_engine, fallback_chain, preferred_parser = self._resolve_parser_engine(request)
        legacy_result = self._legacy.ingest(
            RAGIngestRequest(
                file_path=request.file_path,
                filename=request.filename,
                doc_id=request.doc_id,
                user_id=request.user_id,
                kb_id=request.kb_id,
                mode=request.mode,
                parse_policy=request.parse_policy,
                preferred_parser=preferred_parser,
                parser_preference=parser_engine,
                stage_callback=request.stage_callback,
            )
        )
        diagnostics = dict(legacy_result.diagnostics or {})
        diagnostics.setdefault("rag_backend", self.backend_id)
        diagnostics.setdefault("parser_engine", parser_engine)
        diagnostics.setdefault("fallback_chain", list(fallback_chain))
        diagnostics.setdefault("strategy", diagnostics.get("strategy") or "dual_write_legacy")
        asset_stats = self._asset_stats_from_diagnostics(diagnostics, parser_engine)
        diagnostics["asset_stats"] = asset_stats

        try:
            self._write_source_map(
                request.user_id,
                request.kb_id,
                request.doc_id,
                request.filename,
                parser_engine=parser_engine,
            )
        except Exception:
            fallback_chain.append("source_map_write_failed")
            diagnostics["fallback_chain"] = list(fallback_chain)

        return RAGIngestResult(
            text_path=legacy_result.text_path,
            num_chunks=legacy_result.num_chunks,
            num_pages=legacy_result.num_pages,
            char_count=legacy_result.char_count,
            parser_provider=legacy_result.parser_provider,
            extract_method=legacy_result.extract_method,
            quality_score=legacy_result.quality_score,
            diagnostics=diagnostics,
            timing=legacy_result.timing,
            rag_backend=self.backend_id,
            parser_engine=parser_engine,
            fallback_chain=fallback_chain,
            asset_stats=asset_stats,
            assets=[],
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", (text or "").lower())

    def _search_source_map(self, request: RAGSearchRequest) -> list[dict]:
        map_dir = self._source_map_dir(request.user_id, request.kb_id)
        target_file = (
            [os.path.join(map_dir, f"{request.doc_id}.jsonl")]
            if request.doc_id
            else sorted(
                os.path.join(map_dir, name)
                for name in os.listdir(map_dir)
                if name.endswith(".jsonl")
            )
        )
        rows: list[dict] = []
        query_tokens = self._tokenize(request.question)
        token_set = set(query_tokens)
        for path in target_file:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    text = row.get("text") or row.get("asset_caption") or ""
                    tokens = set(self._tokenize(text))
                    overlap = len(token_set & tokens) if token_set else 0
                    if overlap <= 0:
                        continue
                    score = overlap / max(1, len(token_set))
                    row["score"] = round(float(score), 4)
                    rows.append(row)
        rows.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        top_k = int(request.top_k or settings.qa_top_k)
        return rows[: max(1, top_k)]

    def search(self, request: RAGSearchRequest) -> RAGSearchResult:
        rows = self._search_source_map(request)
        if rows:
            sources = []
            context_blocks = []
            for idx, row in enumerate(rows, start=1):
                source_name = row.get("source") or "document"
                page = row.get("page")
                chunk = row.get("chunk")
                label_parts = [str(source_name)]
                if page is not None:
                    label_parts.append(f"p.{page}")
                if chunk is not None:
                    label_parts.append(f"c.{chunk}")
                source_label = " ".join(label_parts)
                snippet = str(row.get("text") or "")[:400].replace("\n", " ")
                sources.append(
                    {
                        "source": source_label,
                        "snippet": snippet,
                        "doc_id": row.get("doc_id"),
                        "kb_id": row.get("kb_id"),
                        "page": row.get("page"),
                        "chunk": row.get("chunk"),
                        "modality": row.get("modality"),
                        "asset_id": row.get("asset_id"),
                        "asset_url": row.get("asset_url"),
                        "asset_caption": row.get("asset_caption"),
                        "score": row.get("score"),
                    }
                )
                context_blocks.append(f"[{idx}] Source: {source_label}\n{row.get('text', '')}")
            return RAGSearchResult(
                sources=sources,
                context="\n\n".join(context_blocks),
                backend=self.backend_id,
                mode=self.query_mode,
                diagnostics={"fallback_chain": [], "provider": self.backend_id},
            )

        if not self.allow_legacy_fallback:
            return RAGSearchResult(
                sources=[],
                context="",
                backend=self.backend_id,
                mode=self.query_mode,
                diagnostics={"fallback_chain": ["search_empty"], "provider": self.backend_id},
            )

        legacy_result = self._legacy.search(request)
        diagnostics = dict(legacy_result.diagnostics or {})
        chain = list(diagnostics.get("fallback_chain") or [])
        chain.append("search_fallback_to_legacy")
        diagnostics["fallback_chain"] = chain
        diagnostics["provider"] = self.backend_id
        return RAGSearchResult(
            sources=legacy_result.sources,
            context=legacy_result.context,
            backend=self.backend_id,
            mode=self.query_mode,
            diagnostics=diagnostics,
        )

    def delete_doc(self, user_id: str, kb_id: str, doc_id: str) -> None:
        self._legacy.delete_doc(user_id, kb_id, doc_id)
        map_path = os.path.join(self._source_map_dir(user_id, kb_id), f"{doc_id}.jsonl")
        if os.path.exists(map_path):
            os.remove(map_path)

    def health(self) -> dict:
        return {
            "backend": self.backend_id,
            "available": True,
            "raganything_installed": self._raganything_available(),
            "parser_preference": self.parser_preference,
        }
