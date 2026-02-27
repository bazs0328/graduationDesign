import os

from app.core.config import settings


def user_base_dir(user_id: str) -> str:
    return os.path.join(settings.data_dir, "users", user_id)


def kb_base_dir(user_id: str, kb_id: str) -> str:
    return os.path.join(user_base_dir(user_id), "kb", kb_id)


def ensure_data_dirs():
    os.makedirs(os.path.join(settings.data_dir, "users"), exist_ok=True)


def ensure_user_dirs(user_id: str):
    base = user_base_dir(user_id)
    for name in ("uploads", "text", "chroma", "lexical", "kb"):
        os.makedirs(os.path.join(base, name), exist_ok=True)


def ensure_kb_dirs(user_id: str, kb_id: str):
    base = kb_base_dir(user_id, kb_id)
    for name in ("raw", "content_list", "rag_storage"):
        os.makedirs(os.path.join(base, name), exist_ok=True)
