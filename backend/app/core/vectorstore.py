import os

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
