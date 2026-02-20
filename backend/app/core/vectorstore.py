import os
from typing import Any

from langchain_community.vectorstores import Chroma

from app.core.llm import get_embeddings
from app.core.paths import ensure_user_dirs, user_base_dir


def get_vectorstore(user_id: str):
    ensure_user_dirs(user_id)
    persist_dir = os.path.join(user_base_dir(user_id), "chroma")
    embeddings = get_embeddings()
    return Chroma(
        collection_name="documents",
        persist_directory=persist_dir,
        embedding_function=embeddings,
    )


def _get_doc_vector_ids(vectorstore: Chroma, doc_id: str) -> list[str]:
    try:
        payload = vectorstore.get(where={"doc_id": doc_id}, include=["metadatas"])
    except Exception:
        return []
    ids = payload.get("ids") if isinstance(payload, dict) else None
    return [item for item in (ids or []) if isinstance(item, str)]


def delete_doc_vectors(user_id: str, doc_id: str) -> int:
    vectorstore = get_vectorstore(user_id)
    ids = _get_doc_vector_ids(vectorstore, doc_id)
    if not ids:
        return 0
    vectorstore.delete(ids=ids)
    vectorstore.persist()
    return len(ids)


def update_doc_vector_metadata(
    user_id: str,
    doc_id: str,
    *,
    kb_id: str | None = None,
    source: str | None = None,
) -> int:
    vectorstore = get_vectorstore(user_id)
    try:
        payload = vectorstore.get(where={"doc_id": doc_id}, include=["metadatas"])
    except Exception:
        return 0

    if not isinstance(payload, dict):
        return 0

    ids = payload.get("ids") or []
    metadatas = payload.get("metadatas") or []
    if not ids or len(ids) != len(metadatas):
        return 0

    updated_metadatas = []
    for metadata in metadatas:
        item = dict(metadata or {})
        if kb_id is not None:
            item["kb_id"] = kb_id
        if source is not None:
            item["source"] = source
        updated_metadatas.append(item)

    collection = getattr(vectorstore, "_collection", None)
    if collection is None:
        return 0

    collection.update(ids=ids, metadatas=updated_metadatas)
    vectorstore.persist()
    return len(ids)


def get_doc_vector_entries(user_id: str, doc_id: str) -> list[dict[str, Any]]:
    vectorstore = get_vectorstore(user_id)
    try:
        payload = vectorstore.get(
            where={"doc_id": doc_id},
            include=["documents", "metadatas"],
        )
    except Exception:
        return []

    if not isinstance(payload, dict):
        return []

    documents = payload.get("documents") or []
    metadatas = payload.get("metadatas") or []
    ids = payload.get("ids") or []
    if not documents or len(documents) != len(metadatas):
        return []

    rows: list[dict[str, Any]] = []
    for idx, content in enumerate(documents):
        metadata = metadatas[idx] if idx < len(metadatas) else None
        row_id = ids[idx] if idx < len(ids) else None
        if not isinstance(content, str):
            continue
        rows.append(
            {
                "id": row_id if isinstance(row_id, str) else None,
                "content": content,
                "metadata": dict(metadata or {}),
            }
        )

    def _chunk_sort_key(item: dict[str, Any]) -> tuple[int, int]:
        metadata = item.get("metadata") or {}
        chunk_val = metadata.get("chunk")
        page_val = metadata.get("page")
        try:
            page_num = int(page_val)
        except (TypeError, ValueError):
            page_num = 0
        try:
            chunk_num = int(chunk_val)
        except (TypeError, ValueError):
            chunk_num = 0
        return page_num, chunk_num

    rows.sort(key=_chunk_sort_key)
    return rows
