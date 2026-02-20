from __future__ import annotations

from typing import List, Tuple

from app.core.config import settings
from app.core.vectorstore import get_vectorstore
from app.services.lexical import bm25_search


def retrieve_documents_legacy(
    user_id: str,
    question: str,
    doc_id: str | None = None,
    kb_id: str | None = None,
    top_k: int | None = None,
    fetch_k: int | None = None,
) -> list:
    vectorstore = get_vectorstore(user_id)
    search_filter = None
    if doc_id:
        search_filter = {"doc_id": doc_id}
    elif kb_id:
        search_filter = {"kb_id": kb_id}

    k = top_k or settings.qa_top_k
    fetch = fetch_k or settings.qa_fetch_k
    if fetch < k:
        fetch = k

    docs = []
    if settings.rag_mode == "dense":
        try:
            docs = vectorstore.max_marginal_relevance_search(
                question, k=k, fetch_k=fetch, filter=search_filter
            )
        except Exception:
            docs = vectorstore.similarity_search(question, k=k, filter=search_filter)
        return docs

    dense_results = []
    dense_is_similarity = True
    try:
        dense_results = vectorstore.similarity_search_with_relevance_scores(
            question, k=fetch, filter=search_filter
        )
    except Exception:
        dense_is_similarity = False
        try:
            dense_results = vectorstore.similarity_search_with_score(
                question, k=fetch, filter=search_filter
            )
        except Exception:
            dense_results = []

    bm25_k = settings.qa_bm25_k
    if bm25_k < k:
        bm25_k = k
    lexical_results = []
    if kb_id:
        lexical_results = bm25_search(
            user_id,
            kb_id,
            question,
            top_k=bm25_k,
            doc_id=doc_id,
        )

    combined = {}
    for doc, score in dense_results:
        meta = doc.metadata or {}
        key = (
            meta.get("doc_id"),
            meta.get("page"),
            meta.get("chunk"),
            doc.page_content[:80],
        )
        dense_score = float(score)
        if not dense_is_similarity:
            dense_score = 1.0 / (1.0 + max(dense_score, 0.0))
        combined[key] = {
            "doc": doc,
            "dense": dense_score,
            "bm25": 0.0,
        }

    for doc, score in lexical_results:
        meta = doc.metadata or {}
        key = (
            meta.get("doc_id"),
            meta.get("page"),
            meta.get("chunk"),
            doc.page_content[:80],
        )
        if key not in combined:
            combined[key] = {"doc": doc, "dense": 0.0, "bm25": float(score)}
        else:
            combined[key]["bm25"] = max(combined[key]["bm25"], float(score))

    if not combined:
        return []

    dense_scores = [item["dense"] for item in combined.values()]
    bm25_scores = [item["bm25"] for item in combined.values()]
    dense_min = min(dense_scores)
    dense_max = max(dense_scores)
    bm25_min = min(bm25_scores)
    bm25_max = max(bm25_scores)

    def _norm(val: float, min_val: float, max_val: float) -> float:
        if max_val - min_val < 1e-9:
            return 0.0
        return (val - min_val) / (max_val - min_val)

    dense_weight = max(0.0, settings.rag_dense_weight)
    bm25_weight = max(0.0, settings.rag_bm25_weight)
    if dense_weight + bm25_weight < 1e-9:
        dense_weight = 1.0

    weighted = []
    for item in combined.values():
        dense_norm = _norm(item["dense"], dense_min, dense_max)
        bm25_norm = _norm(item["bm25"], bm25_min, bm25_max)
        score = dense_norm * dense_weight + bm25_norm * bm25_weight
        weighted.append((item["doc"], score))

    weighted.sort(key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in weighted[:k]]


def build_sources_and_context_legacy(docs: list) -> Tuple[List[dict], str]:
    sources = []
    context_blocks = []
    for idx, doc in enumerate(docs, start=1):
        metadata = doc.metadata or {}
        snippet = doc.page_content[:400].replace("\n", " ")
        source_name = metadata.get("source", "document")
        page = metadata.get("page")
        chunk = metadata.get("chunk")
        doc_id_meta = metadata.get("doc_id")
        kb_id_meta = metadata.get("kb_id")

        label_parts = [source_name]
        if page:
            label_parts.append(f"p.{page}")
        if chunk:
            label_parts.append(f"c.{chunk}")
        source_label = " ".join(label_parts)

        sources.append(
            {
                "source": source_label,
                "snippet": snippet,
                "doc_id": doc_id_meta,
                "kb_id": kb_id_meta,
                "page": page,
                "chunk": chunk,
            }
        )
        context_blocks.append(f"[{idx}] Source: {source_label}\n{doc.page_content}")

    context = "\n\n".join(context_blocks)
    return sources, context
