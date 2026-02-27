import json
import os
from typing import Tuple

from app.core.config import settings
from app.core.paths import ensure_user_dirs, kb_base_dir, user_base_dir
from app.core.vectorstore import get_vectorstore
from app.services.chunking import build_chunked_documents
from app.services.lexical import append_lexical_chunks
from app.services.text_extraction import extract_text

SUPPORTED_TYPES = {".pdf", ".txt", ".md", ".docx", ".pptx"}


def _layout_sidecar_path(user_id: str, kb_id: str, doc_id: str) -> str:
    return os.path.join(kb_base_dir(user_id, kb_id), "content_list", f"{doc_id}.layout.json")


def _write_layout_sidecar(
    *,
    user_id: str,
    kb_id: str,
    doc_id: str,
    extraction,
    chunk_manifest: list[dict],
) -> None:
    if not (getattr(extraction, "page_blocks", None) or getattr(extraction, "sidecar", None)):
        return
    path = _layout_sidecar_path(user_id, kb_id, doc_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = dict(getattr(extraction, "sidecar", None) or {})
    payload.setdefault("version", 1)
    payload.setdefault("page_count", int(getattr(extraction, "page_count", 0) or 0))
    payload.setdefault("parser", "layout")
    payload["chunk_manifest"] = chunk_manifest
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def ingest_document(
    file_path: str, filename: str, doc_id: str, user_id: str, kb_id: str
) -> Tuple[str, int, int, int]:
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in SUPPORTED_TYPES:
        raise ValueError("Unsupported file type")

    extraction = extract_text(file_path, suffix, user_id=user_id, kb_id=kb_id, doc_id=doc_id)
    text = (extraction.text or "").strip()

    ensure_user_dirs(user_id)
    text_path = os.path.join(user_base_dir(user_id), "text", f"{doc_id}.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)

    chunk_size = max(200, settings.chunk_size)
    chunk_overlap = max(0, min(settings.chunk_overlap, chunk_size - 1))

    chunk_result = build_chunked_documents(
        extraction=extraction,
        suffix=suffix,
        doc_id=doc_id,
        user_id=user_id,
        kb_id=kb_id,
        filename=filename,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    text_docs = chunk_result.text_docs

    if not text_docs:
        raise ValueError("No text extracted from file")

    vectorstore = get_vectorstore(user_id)
    vectorstore.add_documents(text_docs)
    vectorstore.persist()

    append_lexical_chunks(user_id, kb_id, text_docs)
    _write_layout_sidecar(
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        extraction=extraction,
        chunk_manifest=chunk_result.manifest,
    )

    char_count = len(text)
    return text_path, len(text_docs), extraction.page_count, char_count
