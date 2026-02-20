import json
import os
from datetime import datetime
from typing import Any, Dict

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
            return data
    except Exception:
        return {
            "kb_id": kb_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": None,
            "rag_provider": "chroma",
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
