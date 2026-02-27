import json
import os
from typing import Iterable, List, Optional, Tuple

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.core.paths import ensure_user_dirs, user_base_dir
from app.services.lexical_analyzer import tokenize_for_index, tokenize_for_query


def _lexical_path(user_id: str, kb_id: str) -> str:
    return os.path.join(user_base_dir(user_id), "lexical", f"{kb_id}.jsonl")


def append_lexical_chunks(user_id: str, kb_id: str, docs: Iterable[Document]) -> None:
    ensure_user_dirs(user_id)
    path = _lexical_path(user_id, kb_id)
    with open(path, "a", encoding="utf-8") as f:
        for doc in docs:
            text = str(doc.page_content or "")
            payload = {
                "text": text,
                "metadata": doc.metadata or {},
                "tokens": tokenize_for_index(text, user_id=user_id, kb_id=kb_id),
                "tokenizer_version": str(getattr(settings, "lexical_tokenizer_version", "v2") or "v2"),
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_chunks(user_id: str, kb_id: str) -> List[dict]:
    path = _lexical_path(user_id, kb_id)
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _save_chunks(user_id: str, kb_id: str, entries: List[dict]) -> None:
    ensure_user_dirs(user_id)
    path = _lexical_path(user_id, kb_id)
    if not entries:
        if os.path.exists(path):
            os.remove(path)
        return
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def remove_doc_chunks(user_id: str, kb_id: str, doc_id: str) -> int:
    entries = _load_chunks(user_id, kb_id)
    if not entries:
        return 0
    kept: List[dict] = []
    removed = 0
    for entry in entries:
        metadata = entry.get("metadata", {}) if isinstance(entry, dict) else {}
        if metadata.get("doc_id") == doc_id:
            removed += 1
            continue
        kept.append(entry)
    if removed:
        _save_chunks(user_id, kb_id, kept)
    return removed


def update_doc_chunks_metadata(
    user_id: str,
    kb_id: str,
    doc_id: str,
    *,
    source: Optional[str] = None,
) -> int:
    entries = _load_chunks(user_id, kb_id)
    if not entries:
        return 0
    updated = 0
    for entry in entries:
        metadata = entry.get("metadata", {}) if isinstance(entry, dict) else {}
        if metadata.get("doc_id") != doc_id:
            continue
        if source is not None:
            metadata["source"] = source
        entry["metadata"] = metadata
        updated += 1
    if updated:
        _save_chunks(user_id, kb_id, entries)
    return updated


def move_doc_chunks(
    user_id: str,
    from_kb_id: str,
    to_kb_id: str,
    doc_id: str,
    *,
    source: Optional[str] = None,
) -> int:
    if from_kb_id == to_kb_id:
        return update_doc_chunks_metadata(
            user_id,
            from_kb_id,
            doc_id,
            source=source,
        )

    source_entries = _load_chunks(user_id, from_kb_id)
    if not source_entries:
        return 0

    kept: List[dict] = []
    moved_entries: List[dict] = []
    for entry in source_entries:
        metadata = entry.get("metadata", {}) if isinstance(entry, dict) else {}
        if metadata.get("doc_id") != doc_id:
            kept.append(entry)
            continue
        metadata = dict(metadata)
        metadata["kb_id"] = to_kb_id
        if source is not None:
            metadata["source"] = source
        text = str(entry.get("text", "") if isinstance(entry, dict) else "")
        tokens = entry.get("tokens") if isinstance(entry, dict) else None
        if not isinstance(tokens, list) or not all(isinstance(token, str) for token in tokens):
            tokens = tokenize_for_index(text, user_id=user_id, kb_id=to_kb_id)
        tokenizer_version = str(entry.get("tokenizer_version") or "") if isinstance(entry, dict) else ""
        current_version = str(getattr(settings, "lexical_tokenizer_version", "v2") or "v2")
        if tokenizer_version != current_version:
            tokens = tokenize_for_index(text, user_id=user_id, kb_id=to_kb_id)
            tokenizer_version = current_version
        moved_entries.append(
            {
                "text": text,
                "metadata": metadata,
                "tokens": tokens,
                "tokenizer_version": tokenizer_version,
            }
        )

    if not moved_entries:
        return 0

    _save_chunks(user_id, from_kb_id, kept)
    target_entries = _load_chunks(user_id, to_kb_id)
    target_entries.extend(moved_entries)
    _save_chunks(user_id, to_kb_id, target_entries)
    return len(moved_entries)


def bm25_search(
    user_id: str,
    kb_id: str,
    query: str,
    top_k: int = 5,
    doc_id: Optional[str] = None,
) -> List[Tuple[Document, float]]:
    entries = _load_chunks(user_id, kb_id)
    if doc_id:
        entries = [e for e in entries if e.get("metadata", {}).get("doc_id") == doc_id]
    if not entries:
        return []

    current_version = str(getattr(settings, "lexical_tokenizer_version", "v2") or "v2")
    corpus_tokens: List[List[str]] = []
    for entry in entries:
        text = str(entry.get("text", "") if isinstance(entry, dict) else "")
        cached_tokens = entry.get("tokens") if isinstance(entry, dict) else None
        cached_version = str(entry.get("tokenizer_version") or "") if isinstance(entry, dict) else ""
        if (
            isinstance(cached_tokens, list)
            and all(isinstance(token, str) for token in cached_tokens)
            and cached_version == current_version
        ):
            corpus_tokens.append([token for token in cached_tokens if token])
            continue
        corpus_tokens.append(tokenize_for_index(text, user_id=user_id, kb_id=kb_id))

    if not any(corpus_tokens):
        return []

    query_tokens = tokenize_for_query(query, user_id=user_id, kb_id=kb_id)
    if not query_tokens:
        return []

    bm25 = BM25Okapi(corpus_tokens)
    scores = bm25.get_scores(query_tokens)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

    results = []
    for idx, score in ranked:
        entry = entries[idx]
        results.append(
            (
                Document(
                    page_content=entry.get("text", ""),
                    metadata=entry.get("metadata", {}),
                ),
                float(score),
            )
        )
    return results
