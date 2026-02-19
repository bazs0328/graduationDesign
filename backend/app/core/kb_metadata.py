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
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "kb_id": kb_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": None,
            "rag_provider": "chroma",
            "file_hashes": {},
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


def record_file_hash(user_id: str, kb_id: str, filename: str, file_hash: str) -> None:
    metadata = load_kb_metadata(user_id, kb_id)
    metadata.setdefault("file_hashes", {})
    metadata["file_hashes"][filename] = file_hash
    metadata["last_updated"] = datetime.utcnow().isoformat()
    save_kb_metadata(user_id, kb_id, metadata)
