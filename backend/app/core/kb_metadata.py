import json
import os
from datetime import datetime
from typing import Any, Dict

from app.core.config import settings
from app.core.paths import ensure_kb_dirs, kb_base_dir


def _metadata_path(user_id: str, kb_id: str) -> str:
    return os.path.join(kb_base_dir(user_id, kb_id), "metadata.json")


def load_kb_metadata(user_id: str, kb_id: str) -> Dict[str, Any]:
    ensure_kb_dirs(user_id, kb_id)
    path = _metadata_path(user_id, kb_id)
    if not os.path.exists(path):
        return {
            "kb_id": kb_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": None,
            "rag_provider": "chroma",
            "rag_backend": settings.rag_default_backend,
            "query_mode": settings.rag_query_mode,
            "parser_preference": settings.rag_doc_parser_primary,
            "file_hashes": {},
            "parse_policy": "balanced",
            "preferred_parser": "auto",
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Invalid metadata format")
            data.setdefault("parse_policy", "balanced")
            data.setdefault("preferred_parser", "auto")
            data.setdefault("file_hashes", {})
            data.setdefault("rag_backend", settings.rag_default_backend)
            data.setdefault("query_mode", settings.rag_query_mode)
            data.setdefault("parser_preference", settings.rag_doc_parser_primary)
            return data
    except Exception:
        return {
            "kb_id": kb_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": None,
            "rag_provider": "chroma",
            "rag_backend": settings.rag_default_backend,
            "query_mode": settings.rag_query_mode,
            "parser_preference": settings.rag_doc_parser_primary,
            "file_hashes": {},
            "parse_policy": "balanced",
            "preferred_parser": "auto",
        }


def save_kb_metadata(user_id: str, kb_id: str, metadata: Dict[str, Any]) -> None:
    ensure_kb_dirs(user_id, kb_id)
    path = _metadata_path(user_id, kb_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def init_kb_metadata(user_id: str, kb_id: str) -> None:
    path = _metadata_path(user_id, kb_id)
    if os.path.exists(path):
        return
    metadata = load_kb_metadata(user_id, kb_id)
    save_kb_metadata(user_id, kb_id, metadata)


def get_kb_parse_settings(user_id: str, kb_id: str) -> Dict[str, str]:
    metadata = load_kb_metadata(user_id, kb_id)
    return {
        "parse_policy": metadata.get("parse_policy", "balanced"),
        "preferred_parser": metadata.get("preferred_parser", "auto"),
    }


def get_kb_rag_settings(user_id: str, kb_id: str) -> Dict[str, str]:
    metadata = load_kb_metadata(user_id, kb_id)
    return {
        "rag_backend": metadata.get("rag_backend", settings.rag_default_backend),
        "query_mode": metadata.get("query_mode", settings.rag_query_mode),
        "parser_preference": metadata.get("parser_preference", settings.rag_doc_parser_primary),
    }


def update_kb_parse_settings(
    user_id: str,
    kb_id: str,
    *,
    parse_policy: str | None = None,
    preferred_parser: str | None = None,
) -> Dict[str, str]:
    valid_policies = {"stable", "balanced", "aggressive"}
    valid_parsers = {"auto", "native", "docling"}
    metadata = load_kb_metadata(user_id, kb_id)

    if parse_policy is not None:
        normalized_policy = parse_policy.strip().lower()
        if normalized_policy not in valid_policies:
            raise ValueError("Invalid parse_policy")
        metadata["parse_policy"] = normalized_policy

    if preferred_parser is not None:
        normalized_parser = preferred_parser.strip().lower()
        if normalized_parser not in valid_parsers:
            raise ValueError("Invalid preferred_parser")
        metadata["preferred_parser"] = normalized_parser

    metadata["last_updated"] = datetime.utcnow().isoformat()
    save_kb_metadata(user_id, kb_id, metadata)
    return {
        "parse_policy": metadata.get("parse_policy", "balanced"),
        "preferred_parser": metadata.get("preferred_parser", "auto"),
    }


def update_kb_rag_settings(
    user_id: str,
    kb_id: str,
    *,
    rag_backend: str | None = None,
    query_mode: str | None = None,
    parser_preference: str | None = None,
) -> Dict[str, str]:
    valid_backends = {"legacy", "raganything_mineru", "raganything_docling"}
    valid_modes = {"hybrid", "local", "global", "naive"}
    valid_parsers = {"mineru", "docling", "auto"}
    metadata = load_kb_metadata(user_id, kb_id)

    if rag_backend is not None:
        normalized_backend = rag_backend.strip().lower()
        if normalized_backend not in valid_backends:
            raise ValueError("Invalid rag_backend")
        metadata["rag_backend"] = normalized_backend

    if query_mode is not None:
        normalized_mode = query_mode.strip().lower()
        if normalized_mode not in valid_modes:
            raise ValueError("Invalid query_mode")
        metadata["query_mode"] = normalized_mode

    if parser_preference is not None:
        normalized_parser = parser_preference.strip().lower()
        if normalized_parser not in valid_parsers:
            raise ValueError("Invalid parser_preference")
        metadata["parser_preference"] = normalized_parser

    metadata["last_updated"] = datetime.utcnow().isoformat()
    save_kb_metadata(user_id, kb_id, metadata)
    return {
        "rag_backend": metadata.get("rag_backend", settings.rag_default_backend),
        "query_mode": metadata.get("query_mode", settings.rag_query_mode),
        "parser_preference": metadata.get("parser_preference", settings.rag_doc_parser_primary),
    }


def record_file_hash(user_id: str, kb_id: str, filename: str, file_hash: str) -> None:
    metadata = load_kb_metadata(user_id, kb_id)
    metadata.setdefault("file_hashes", {})
    metadata["file_hashes"][filename] = file_hash
    metadata["last_updated"] = datetime.utcnow().isoformat()
    save_kb_metadata(user_id, kb_id, metadata)


def remove_file_hash(user_id: str, kb_id: str, filename: str) -> bool:
    metadata = load_kb_metadata(user_id, kb_id)
    hashes = metadata.setdefault("file_hashes", {})
    if filename not in hashes:
        return False
    hashes.pop(filename, None)
    metadata["last_updated"] = datetime.utcnow().isoformat()
    save_kb_metadata(user_id, kb_id, metadata)
    return True


def rename_file_hash(
    user_id: str,
    kb_id: str,
    old_filename: str,
    new_filename: str,
) -> bool:
    metadata = load_kb_metadata(user_id, kb_id)
    hashes = metadata.setdefault("file_hashes", {})
    if old_filename not in hashes:
        return False
    hashes[new_filename] = hashes.pop(old_filename)
    metadata["last_updated"] = datetime.utcnow().isoformat()
    save_kb_metadata(user_id, kb_id, metadata)
    return True


def transfer_file_hash(
    user_id: str,
    from_kb_id: str,
    to_kb_id: str,
    old_filename: str,
    new_filename: str | None = None,
    file_hash: str | None = None,
) -> bool:
    moved = False
    source_meta = load_kb_metadata(user_id, from_kb_id)
    source_hashes = source_meta.setdefault("file_hashes", {})
    hash_value = file_hash
    if hash_value is None:
        hash_value = source_hashes.pop(old_filename, None)
    else:
        source_hashes.pop(old_filename, None)

    if hash_value:
        target_name = (new_filename or old_filename).strip()
        target_meta = load_kb_metadata(user_id, to_kb_id)
        target_hashes = target_meta.setdefault("file_hashes", {})
        target_hashes[target_name] = hash_value
        target_meta["last_updated"] = datetime.utcnow().isoformat()
        save_kb_metadata(user_id, to_kb_id, target_meta)
        moved = True

    source_meta["last_updated"] = datetime.utcnow().isoformat()
    save_kb_metadata(user_id, from_kb_id, source_meta)
    return moved
