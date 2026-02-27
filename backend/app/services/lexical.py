import json
import os
import re
from typing import Iterable, List, Optional, Tuple

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from app.core.paths import ensure_user_dirs, user_base_dir

WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> List[str]:
    return WORD_RE.findall(text.lower())


def _lexical_path(user_id: str, kb_id: str) -> str:
    return os.path.join(user_base_dir(user_id), "lexical", f"{kb_id}.jsonl")


def append_lexical_chunks(user_id: str, kb_id: str, docs: Iterable[Document]) -> None:
    ensure_user_dirs(user_id)
    path = _lexical_path(user_id, kb_id)
    with open(path, "a", encoding="utf-8") as f:
        for doc in docs:
            payload = {"text": doc.page_content, "metadata": doc.metadata or {}}
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
        moved_entries.append(
            {
                "text": entry.get("text", ""),
                "metadata": metadata,
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

    tokens = [_tokenize(e.get("text", "")) for e in entries]
    if not any(tokens):
        return []

    bm25 = BM25Okapi(tokens)
    scores = bm25.get_scores(_tokenize(query))
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
