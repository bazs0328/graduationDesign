from __future__ import annotations

import json
import logging
import os
from typing import Any, Iterable

import chromadb
from langchain_core.documents import Document

from app.core.config import settings
from app.core.llm import get_embeddings
from app.core.paths import ensure_user_dirs, user_base_dir

logger = logging.getLogger(__name__)


def _persist_dir(user_id: str) -> str:
    ensure_user_dirs(user_id)
    return os.path.join(user_base_dir(user_id), "chroma")


def _collection_name() -> str:
    return (getattr(settings, "mm_image_collection_name", None) or "documents_images").strip() or "documents_images"


def _get_collection(user_id: str):
    client = chromadb.PersistentClient(path=_persist_dir(user_id))
    return client.get_or_create_collection(name=_collection_name())


def _supports_image_embeddings(embeddings: Any) -> bool:
    fn = getattr(embeddings, "embed_image_paths", None)
    return callable(fn)


def is_image_indexing_available() -> bool:
    if not bool(getattr(settings, "mm_image_index_enabled", True)):
        return False
    try:
        embeddings = get_embeddings()
    except Exception:
        return False
    return _supports_image_embeddings(embeddings)


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
            continue
        try:
            out[key] = json.dumps(value, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            out[key] = str(value)
    return out


def _image_doc_id(doc: Document) -> str:
    meta = doc.metadata or {}
    doc_id = str(meta.get("doc_id") or "doc")
    page = meta.get("page")
    chunk = meta.get("chunk")
    if page is None:
        page = 0
    if chunk is None:
        chunk = 0
    return f"{doc_id}:p{page}:c{chunk}:img"


def add_image_documents(user_id: str, docs: Iterable[Document]) -> int:
    docs_list = [doc for doc in docs if isinstance(doc, Document)]
    if not docs_list:
        return 0
    if not bool(getattr(settings, "mm_image_index_enabled", True)):
        return 0

    embeddings = get_embeddings()
    if not _supports_image_embeddings(embeddings):
        logger.info("Image indexing skipped: embedding provider does not support image embeddings")
        return 0

    paths: list[str] = []
    kept_docs: list[Document] = []
    for doc in docs_list:
        meta = doc.metadata or {}
        path = str(meta.get("asset_path") or "").strip()
        if not path or not os.path.exists(path):
            continue
        paths.append(path)
        kept_docs.append(doc)
    if not kept_docs:
        return 0

    vectors = embeddings.embed_image_paths(paths)
    if len(vectors) != len(kept_docs):
        raise ValueError("Image embedding vector count mismatch")

    collection = _get_collection(user_id)
    ids = [_image_doc_id(doc) for doc in kept_docs]
    metadatas = [_sanitize_metadata(doc.metadata or {}) for doc in kept_docs]
    documents = [str(doc.page_content or "") for doc in kept_docs]

    # Upsert semantics across chromadb versions: delete existing ids then add.
    try:
        collection.delete(ids=ids)
    except Exception:
        pass
    collection.add(ids=ids, embeddings=vectors, metadatas=metadatas, documents=documents)
    return len(kept_docs)


def query_image_documents(
    user_id: str,
    query: str,
    *,
    top_k: int = 5,
    search_filter: dict[str, Any] | None = None,
) -> list[tuple[Document, float]]:
    if top_k <= 0:
        return []
    if not bool(getattr(settings, "mm_image_index_enabled", True)):
        return []

    embeddings = get_embeddings()
    if not _supports_image_embeddings(embeddings):
        return []

    query_vector = embeddings.embed_query(query)
    collection = _get_collection(user_id)
    try:
        query_kwargs = dict(
            query_embeddings=[query_vector],
            n_results=int(top_k),
            include=["documents", "metadatas", "distances"],
        )
        if search_filter:
            query_kwargs["where"] = search_filter
        payload = collection.query(
            **query_kwargs,
        )
    except Exception:
        logger.exception("Image vector query failed")
        return []

    docs_rows = (payload.get("documents") or [[]])[0] if isinstance(payload, dict) else []
    metas_rows = (payload.get("metadatas") or [[]])[0] if isinstance(payload, dict) else []
    dist_rows = (payload.get("distances") or [[]])[0] if isinstance(payload, dict) else []

    out: list[tuple[Document, float]] = []
    for idx, content in enumerate(docs_rows):
        metadata = metas_rows[idx] if idx < len(metas_rows) else {}
        distance = dist_rows[idx] if idx < len(dist_rows) else None
        try:
            dist_f = float(distance)
            score = 1.0 / (1.0 + max(dist_f, 0.0))
        except (TypeError, ValueError):
            score = 0.0
        out.append((Document(page_content=str(content or ""), metadata=dict(metadata or {})), score))
    return out


def delete_doc_image_vectors(user_id: str, doc_id: str) -> int:
    collection = _get_collection(user_id)
    try:
        payload = collection.get(where={"doc_id": doc_id}, include=["metadatas"])
    except Exception:
        return 0
    ids = payload.get("ids") if isinstance(payload, dict) else None
    if not ids:
        return 0
    try:
        collection.delete(ids=ids)
    except Exception:
        return 0
    return len(ids)


def update_doc_image_vector_metadata(
    user_id: str,
    doc_id: str,
    *,
    kb_id: str | None = None,
    source: str | None = None,
) -> int:
    collection = _get_collection(user_id)
    try:
        payload = collection.get(where={"doc_id": doc_id}, include=["metadatas"])
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    ids = payload.get("ids") or []
    metadatas = payload.get("metadatas") or []
    if not ids or len(ids) != len(metadatas):
        return 0
    new_mds = []
    for md in metadatas:
        item = dict(md or {})
        if kb_id is not None:
            item["kb_id"] = kb_id
        if source is not None:
            item["source"] = source
        new_mds.append(_sanitize_metadata(item))
    try:
        collection.update(ids=ids, metadatas=new_mds)
    except Exception:
        logger.exception("Failed updating image vector metadata")
        return 0
    return len(ids)


def rewrite_doc_image_asset_paths(
    user_id: str,
    doc_id: str,
    *,
    old_prefix: str,
    new_prefix: str,
) -> int:
    if not old_prefix or not new_prefix or old_prefix == new_prefix:
        return 0
    collection = _get_collection(user_id)
    try:
        payload = collection.get(where={"doc_id": doc_id}, include=["metadatas"])
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    ids = payload.get("ids") or []
    metadatas = payload.get("metadatas") or []
    if not ids or len(ids) != len(metadatas):
        return 0
    updated = 0
    new_mds = []
    for md in metadatas:
        item = dict(md or {})
        path = item.get("asset_path")
        if isinstance(path, str) and path.startswith(old_prefix):
            item["asset_path"] = new_prefix + path[len(old_prefix):]
            updated += 1
        new_mds.append(_sanitize_metadata(item))
    if not updated:
        return 0
    try:
        collection.update(ids=ids, metadatas=new_mds)
    except Exception:
        logger.exception("Failed rewriting image vector asset paths")
        return 0
    return updated


def get_doc_image_vector_entries(user_id: str, doc_id: str) -> list[dict[str, Any]]:
    collection = _get_collection(user_id)
    try:
        payload = collection.get(where={"doc_id": doc_id}, include=["documents", "metadatas"])
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    ids = payload.get("ids") or []
    docs = payload.get("documents") or []
    metadatas = payload.get("metadatas") or []
    rows: list[dict[str, Any]] = []
    for idx, content in enumerate(docs):
        metadata = dict(metadatas[idx] or {}) if idx < len(metadatas) else {}
        rows.append(
            {
                "id": ids[idx] if idx < len(ids) else None,
                "content": str(content or ""),
                "metadata": metadata,
            }
        )

    def _sort_key(item: dict[str, Any]) -> tuple[int, int]:
        md = item.get("metadata") or {}
        try:
            page = int(md.get("page"))
        except (TypeError, ValueError):
            page = 0
        try:
            chunk = int(md.get("chunk"))
        except (TypeError, ValueError):
            chunk = 0
        return page, chunk

    rows.sort(key=_sort_key)
    return rows
