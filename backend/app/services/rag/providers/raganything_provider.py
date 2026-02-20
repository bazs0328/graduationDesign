from __future__ import annotations

import json
import os
import re
import shutil
from time import perf_counter
from typing import Any
from uuid import uuid4

from langchain_core.documents import Document as LCDocument

from app.core.config import settings
from app.core.paths import ensure_kb_dirs, ensure_user_dirs, kb_base_dir, user_base_dir
from app.core.vectorstore import get_doc_vector_entries, get_vectorstore
from app.services.lexical import append_lexical_chunks
from app.services.rag.base import (
    RAGIngestRequest,
    RAGIngestResult,
    RAGSearchRequest,
    RAGSearchResult,
)
from app.services.rag.mineru_adapter import CanonicalContentBundle, MinerUAdapter, MinerUParseOutput
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
        self._mineru_adapter = MinerUAdapter()

    @staticmethod
    def _emit(callback, stage: str, progress: int, message: str) -> None:
        if callback:
            callback(stage, max(0, min(int(progress), 100)), message)

    def _raganything_available(self) -> bool:
        return self._mineru_adapter.is_available()

    def _resolve_parser_engine(self, request: RAGIngestRequest) -> tuple[str, list[str], str]:
        fallback_chain: list[str] = []
        preferred = (request.parser_preference or self.parser_preference or "mineru").strip().lower()
        if preferred == "docling":
            parser_engine = "docling"
            preferred_parser = "docling"
        elif preferred == "native":
            parser_engine = "native"
            preferred_parser = "native"
        else:
            parser_engine = "mineru"
            preferred_parser = "auto"
        return parser_engine, fallback_chain, preferred_parser

    @staticmethod
    def _asset_stats_from_diagnostics(diagnostics: dict[str, Any], parser_engine: str) -> dict[str, Any]:
        docling_stats = (diagnostics or {}).get("docling_stats") or {}
        placeholders = int(docling_stats.get("image_placeholders") or 0)
        by_type = {"image": placeholders} if placeholders > 0 else {}
        return {
            "total": placeholders,
            "by_type": by_type,
            "text_blocks": int(docling_stats.get("char_count") or 0),
            "modal_blocks": placeholders,
            "parser_engine": parser_engine,
        }

    @staticmethod
    def _source_map_dir(user_id: str, kb_id: str) -> str:
        base = kb_base_dir(user_id, kb_id)
        path = os.path.join(base, "source_map")
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def _asset_url(doc_id: str, asset_id: str, user_id: str) -> str:
        return f"/api/docs/{doc_id}/assets/{asset_id}/file?user_id={user_id}"

    def _persist_text(self, user_id: str, doc_id: str, text: str) -> str:
        ensure_user_dirs(user_id)
        text_path = os.path.join(user_base_dir(user_id), "text", f"{doc_id}.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text)
        return text_path

    def _index_dense_docs(self, user_id: str, docs: list[LCDocument]) -> None:
        vectorstore = get_vectorstore(user_id)
        batch_size = max(1, int(settings.ingest_vector_batch_size))
        for start in range(0, len(docs), batch_size):
            vectorstore.add_documents(docs[start : start + batch_size])
        vectorstore.persist()

    @staticmethod
    def _index_lexical_docs(user_id: str, kb_id: str, docs: list[LCDocument]) -> None:
        append_lexical_chunks(user_id, kb_id, docs)

    def _write_source_map_rows(self, user_id: str, kb_id: str, doc_id: str, rows: list[dict[str, Any]]) -> int:
        map_path = os.path.join(self._source_map_dir(user_id, kb_id), f"{doc_id}.jsonl")
        count = 0
        with open(map_path, "w", encoding="utf-8") as f:
            for payload in rows:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                count += 1
        return count

    def _build_source_rows_from_docs(
        self,
        request: RAGIngestRequest,
        docs: list[LCDocument],
        *,
        parser_engine: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for doc in docs:
            metadata = dict(doc.metadata or {})
            rows.append(
                {
                    "doc_id": request.doc_id,
                    "kb_id": request.kb_id,
                    "source": metadata.get("source") or request.filename,
                    "page": metadata.get("page"),
                    "chunk": metadata.get("chunk"),
                    "text": doc.page_content or "",
                    "modality": metadata.get("modality") or "text",
                    "asset_id": metadata.get("asset_id"),
                    "asset_url": metadata.get("asset_url"),
                    "asset_caption": metadata.get("asset_caption"),
                    "score": None,
                    "parser_engine": parser_engine,
                }
            )
        return rows

    def _write_source_map_from_vectors(
        self,
        user_id: str,
        kb_id: str,
        doc_id: str,
        filename: str,
        *,
        parser_engine: str,
    ) -> None:
        entries = get_doc_vector_entries(user_id, doc_id)
        rows: list[dict[str, Any]] = []
        for row in entries:
            metadata = dict(row.get("metadata") or {})
            rows.append(
                {
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
            )
        self._write_source_map_rows(user_id, kb_id, doc_id, rows)

    @staticmethod
    def _materialize_asset_path(
        request: RAGIngestRequest,
        index: int,
        source_path: str | None,
    ) -> str | None:
        if not source_path:
            return None
        if not os.path.exists(source_path):
            return None
        ensure_kb_dirs(request.user_id, request.kb_id)
        image_dir = os.path.join(kb_base_dir(request.user_id, request.kb_id), "images")
        os.makedirs(image_dir, exist_ok=True)
        ext = os.path.splitext(source_path)[1].lower() or ".png"
        target_path = os.path.join(image_dir, f"{request.doc_id}_{index:04d}{ext}")
        if os.path.abspath(source_path) != os.path.abspath(target_path):
            shutil.copy2(source_path, target_path)
        else:
            target_path = source_path
        return target_path

    def _materialize_assets(
        self,
        request: RAGIngestRequest,
        bundle: CanonicalContentBundle,
    ) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        for index, row in enumerate(bundle.assets, start=1):
            asset_id = str(row.get("id") or f"{request.doc_id}-asset-{index}" or uuid4())
            source_path = row.get("source_path")
            metadata = dict(row.get("metadata") or {})
            try:
                image_path = self._materialize_asset_path(request, index, source_path)
            except Exception as exc:  # noqa: BLE001
                image_path = None
                metadata["copy_error"] = str(exc)[:300]

            assets.append(
                {
                    "id": asset_id,
                    "page": row.get("page"),
                    "asset_type": str(row.get("asset_type") or "image"),
                    "image_path": image_path,
                    "caption_text": row.get("caption_text"),
                    "ocr_text": row.get("ocr_text"),
                    "quality_score": row.get("quality_score"),
                    "metadata": {
                        **metadata,
                        "parser_engine": "mineru",
                    },
                }
            )
        return assets

    def _bind_asset_urls(
        self,
        request: RAGIngestRequest,
        docs: list[LCDocument],
        assets: list[dict[str, Any]],
    ) -> None:
        available_assets = {
            str(row.get("id")): row for row in assets if isinstance(row, dict) and row.get("id")
        }
        for doc in docs:
            metadata = dict(doc.metadata or {})
            asset_id = metadata.get("asset_id")
            if not asset_id:
                doc.metadata = metadata
                continue
            asset = available_assets.get(str(asset_id))
            if asset and asset.get("image_path"):
                metadata["asset_url"] = self._asset_url(request.doc_id, str(asset_id), request.user_id)
            else:
                metadata["asset_url"] = None
            doc.metadata = metadata

    @staticmethod
    def _page_count_from_bundle(bundle: CanonicalContentBundle, parse_output: MinerUParseOutput) -> int:
        page_count = len(bundle.page_texts)
        raw_page_count = int((parse_output.raw_stats or {}).get("page_count") or 0)
        return max(1, page_count, raw_page_count)

    def _build_mineru_diagnostics(
        self,
        *,
        request: RAGIngestRequest,
        fallback_chain: list[str],
        parse_output: MinerUParseOutput,
        bundle: CanonicalContentBundle,
        asset_stats: dict[str, Any],
        source_rows: int,
    ) -> dict[str, Any]:
        return {
            "strategy": "mineru_native_dual_write",
            "complexity_class": "layout_complex",
            "low_quality_pages": [],
            "ocr_pages": [],
            "page_scores": [],
            "rag_backend": self.backend_id,
            "parser_engine": "mineru",
            "fallback_chain": list(fallback_chain),
            "asset_stats": asset_stats,
            "mineru_stats": parse_output.raw_stats,
            "source_map_rows": source_rows,
            "mode": request.mode,
        }

    def _ingest_with_mineru(
        self,
        request: RAGIngestRequest,
        fallback_chain: list[str],
    ) -> RAGIngestResult:
        started = perf_counter()
        self._emit(request.stage_callback, "preflight", 5, "Preparing MinerU native parse")

        output_dir = os.path.join(kb_base_dir(request.user_id, request.kb_id), "content_list", request.doc_id)
        os.makedirs(output_dir, exist_ok=True)
        parse_output = self._mineru_adapter.parse_pdf(
            file_path=request.file_path,
            output_dir=output_dir,
            mode=request.mode,
            parser_backend=None,
            lang=settings.ocr_language,
            device=None,
            source=None,
        )
        self._emit(request.stage_callback, "extract", 35, "MinerU parse completed")

        bundle = self._mineru_adapter.normalize_content_list(
            content_list=parse_output.content_list,
            markdown_text=parse_output.markdown_text,
            doc_id=request.doc_id,
            kb_id=request.kb_id,
            filename=request.filename,
            parser_provider="raganything",
            extract_method="mineru_multimodal",
        )
        if not bundle.full_text.strip():
            raise ValueError("MinerU parse generated empty content")
        if not bundle.chunk_docs:
            raise ValueError("MinerU parse generated no chunks")

        text_path = self._persist_text(request.user_id, request.doc_id, bundle.full_text)
        assets = self._materialize_assets(request, bundle)
        self._bind_asset_urls(request, bundle.chunk_docs, assets)

        self._emit(request.stage_callback, "chunk", 60, "Chunk normalization finished")
        dense_started = perf_counter()
        self._emit(request.stage_callback, "index_dense", 75, "Indexing dense vectors")
        self._index_dense_docs(request.user_id, bundle.chunk_docs)
        dense_ms = (perf_counter() - dense_started) * 1000

        lexical_started = perf_counter()
        self._emit(request.stage_callback, "index_lexical", 90, "Indexing lexical store")
        self._index_lexical_docs(request.user_id, request.kb_id, bundle.chunk_docs)
        lexical_ms = (perf_counter() - lexical_started) * 1000

        source_started = perf_counter()
        rows = self._build_source_rows_from_docs(request, bundle.chunk_docs, parser_engine="mineru")
        source_rows = self._write_source_map_rows(request.user_id, request.kb_id, request.doc_id, rows)
        source_ms = (perf_counter() - source_started) * 1000
        self._emit(request.stage_callback, "done", 100, "MinerU ingest completed")

        total_ms = (perf_counter() - started) * 1000
        asset_stats = {
            **dict(bundle.asset_stats or {}),
            "parser_engine": "mineru",
        }
        diagnostics = self._build_mineru_diagnostics(
            request=request,
            fallback_chain=fallback_chain,
            parse_output=parse_output,
            bundle=bundle,
            asset_stats=asset_stats,
            source_rows=source_rows,
        )
        timing = {
            "parse": round(float((parse_output.timing_ms or {}).get("parse", 0.0)), 2),
            "index_dense": round(dense_ms, 2),
            "index_lexical": round(lexical_ms, 2),
            "source_map": round(source_ms, 2),
            "total": round(total_ms, 2),
        }
        return RAGIngestResult(
            text_path=text_path,
            num_chunks=len(bundle.chunk_docs),
            num_pages=self._page_count_from_bundle(bundle, parse_output),
            char_count=len(bundle.full_text),
            parser_provider="raganything",
            extract_method="mineru_multimodal",
            quality_score=bundle.quality_score,
            diagnostics=diagnostics,
            timing=timing,
            rag_backend=self.backend_id,
            parser_engine="mineru",
            fallback_chain=list(fallback_chain),
            asset_stats=asset_stats,
            assets=assets,
        )

    def _ingest_with_legacy_parser(
        self,
        request: RAGIngestRequest,
        *,
        parser_engine: str,
        preferred_parser: str,
        fallback_chain: list[str],
        strategy: str,
    ) -> RAGIngestResult:
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
        diagnostics["fallback_chain"] = list(fallback_chain)
        diagnostics.setdefault("strategy", strategy)
        asset_stats = self._asset_stats_from_diagnostics(diagnostics, parser_engine)
        diagnostics["asset_stats"] = asset_stats
        self._write_source_map_from_vectors(
            request.user_id,
            request.kb_id,
            request.doc_id,
            request.filename,
            parser_engine=parser_engine,
        )
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
            fallback_chain=list(fallback_chain),
            asset_stats=asset_stats,
            assets=[],
        )

    def _fallback_docling_then_native(
        self,
        request: RAGIngestRequest,
        fallback_chain: list[str],
        *,
        mineru_error: Exception | None = None,
    ) -> RAGIngestResult:
        fallback_errors: dict[str, str] = {}
        if mineru_error is not None:
            fallback_errors["mineru"] = str(mineru_error)[:400]

        try:
            result = self._ingest_with_legacy_parser(
                request,
                parser_engine="docling",
                preferred_parser="docling",
                fallback_chain=fallback_chain,
                strategy="mineru_fallback_docling",
            )
            diagnostics = dict(result.diagnostics or {})
            if fallback_errors:
                diagnostics["fallback_errors"] = fallback_errors
            result.diagnostics = diagnostics
            return result
        except Exception as docling_exc:  # noqa: BLE001
            fallback_chain.append("docling_fallback_failed")
            fallback_errors["docling"] = str(docling_exc)[:400]

        try:
            fallback_chain.append("native_legacy_fallback")
            result = self._ingest_with_legacy_parser(
                request,
                parser_engine="native",
                preferred_parser="native",
                fallback_chain=fallback_chain,
                strategy="mineru_fallback_native",
            )
            diagnostics = dict(result.diagnostics or {})
            diagnostics["fallback_errors"] = fallback_errors
            result.diagnostics = diagnostics
            return result
        except Exception as native_exc:  # noqa: BLE001
            fallback_errors["native"] = str(native_exc)[:400]
            raise RuntimeError(
                "RAG ingest failed after mineru/docling/native fallback chain: "
                + " -> ".join(fallback_chain)
            ) from native_exc

    def ingest(self, request: RAGIngestRequest) -> RAGIngestResult:
        parser_engine, fallback_chain, preferred_parser = self._resolve_parser_engine(request)
        if parser_engine != "mineru":
            return self._ingest_with_legacy_parser(
                request,
                parser_engine=parser_engine,
                preferred_parser=preferred_parser,
                fallback_chain=fallback_chain,
                strategy="legacy_parser_preferred",
            )

        if not self._raganything_available():
            fallback_chain.append("mineru_unavailable")
            return self._fallback_docling_then_native(request, fallback_chain)

        try:
            return self._ingest_with_mineru(request, fallback_chain)
        except Exception as exc:  # noqa: BLE001
            fallback_chain.append("mineru_parse_failed")
            return self._fallback_docling_then_native(
                request,
                fallback_chain,
                mineru_error=exc,
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
        try:
            import raganything  # type: ignore  # noqa: F401

            rag_installed = True
        except Exception:
            rag_installed = False
        return {
            "backend": self.backend_id,
            "available": True,
            "raganything_installed": rag_installed,
            "mineru_available": self._mineru_adapter.is_available(),
            "parser_preference": self.parser_preference,
        }
