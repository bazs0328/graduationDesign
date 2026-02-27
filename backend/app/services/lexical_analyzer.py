from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import jieba

from app.core.config import settings
from app.core.paths import kb_base_dir

logger = logging.getLogger(__name__)

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\u2060\ufeff]")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TOKEN_PART_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+")
_ASCII_WORD_RE = re.compile(r"^[a-z0-9_]+$")

_DEFAULT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
    "与",
    "且",
    "了",
    "于",
    "以",
    "们",
    "但",
    "你",
    "其",
    "和",
    "在",
    "将",
    "就",
    "并",
    "并且",
    "很",
    "把",
    "是",
    "有",
    "及",
    "或",
    "我",
    "所以",
    "把",
    "等",
    "而",
    "与",
    "被",
    "让",
    "该",
    "这",
    "这个",
    "这些",
    "那",
    "那个",
    "那些",
    "都",
    "通过",
    "进行",
    "以及",
}


@dataclass
class _AnalyzerState:
    tokenizer: jieba.Tokenizer
    stopwords: set[str]
    signature: tuple[Any, ...]


_ANALYZER_CACHE: dict[tuple[str, str], _AnalyzerState] = {}


def _scope_key(user_id: str | None, kb_id: str | None) -> tuple[str, str]:
    return str(user_id or ""), str(kb_id or "")


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = _CONTROL_CHAR_RE.sub(" ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


def _abs_path(path: str | None) -> str | None:
    candidate = str(path or "").strip()
    if not candidate:
        return None
    return os.path.abspath(candidate)


def _stat_signature(path: str | None) -> tuple[str, int, int]:
    if not path:
        return ("", -1, -1)
    try:
        stat = os.stat(path)
        return (path, int(stat.st_mtime_ns), int(stat.st_size))
    except OSError:
        return (path, -1, -1)


def _resolve_scope_paths(user_id: str | None, kb_id: str | None) -> dict[str, str | None]:
    global_stopwords = _abs_path(getattr(settings, "lexical_stopwords_global_path", ""))
    global_userdict = _abs_path(getattr(settings, "lexical_userdict_global_path", ""))

    kb_stopwords: str | None = None
    kb_userdict: str | None = None
    if user_id and kb_id:
        kb_root = kb_base_dir(str(user_id), str(kb_id))
        kb_stop_rel = str(getattr(settings, "lexical_stopwords_kb_rel_path", "") or "").strip()
        kb_dict_rel = str(getattr(settings, "lexical_userdict_kb_rel_path", "") or "").strip()
        if kb_stop_rel:
            kb_stopwords = os.path.abspath(os.path.join(kb_root, kb_stop_rel))
        if kb_dict_rel:
            kb_userdict = os.path.abspath(os.path.join(kb_root, kb_dict_rel))

    return {
        "global_stopwords": global_stopwords,
        "global_userdict": global_userdict,
        "kb_stopwords": kb_stopwords,
        "kb_userdict": kb_userdict,
    }


def _read_stopwords(path: str | None) -> set[str]:
    if not path or not os.path.exists(path):
        return set()

    values: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                values.add(_normalize_text(line))
    except Exception:
        logger.exception("Failed to load lexical stopwords path=%s", path)
        return set()
    return values


def _load_userdict(tokenizer: jieba.Tokenizer, path: str | None) -> None:
    if not path or not os.path.exists(path):
        return
    try:
        tokenizer.load_userdict(path)
    except Exception:
        logger.exception("Failed to load jieba user dictionary path=%s", path)


def _build_signature(
    *,
    user_id: str | None,
    kb_id: str | None,
    paths: dict[str, str | None],
) -> tuple[Any, ...]:
    return (
        str(getattr(settings, "lexical_tokenizer_version", "v2") or "v2"),
        bool(getattr(settings, "lexical_stopwords_enabled", True)),
        _stat_signature(paths.get("global_stopwords")),
        _stat_signature(paths.get("global_userdict")),
        _stat_signature(paths.get("kb_stopwords")),
        _stat_signature(paths.get("kb_userdict")),
        str(user_id or ""),
        str(kb_id or ""),
    )


def _build_analyzer_state(
    *,
    user_id: str | None,
    kb_id: str | None,
    paths: dict[str, str | None],
    signature: tuple[Any, ...],
) -> _AnalyzerState:
    tokenizer = jieba.Tokenizer()
    _load_userdict(tokenizer, paths.get("global_userdict"))
    _load_userdict(tokenizer, paths.get("kb_userdict"))

    stopwords: set[str] = set(_DEFAULT_STOPWORDS)
    if bool(getattr(settings, "lexical_stopwords_enabled", True)):
        stopwords.update(_read_stopwords(paths.get("global_stopwords")))
        stopwords.update(_read_stopwords(paths.get("kb_stopwords")))

    return _AnalyzerState(
        tokenizer=tokenizer,
        stopwords=stopwords,
        signature=signature,
    )


def _get_analyzer_state(user_id: str | None, kb_id: str | None) -> _AnalyzerState:
    key = _scope_key(user_id, kb_id)
    paths = _resolve_scope_paths(user_id, kb_id)
    signature = _build_signature(user_id=user_id, kb_id=kb_id, paths=paths)

    cached = _ANALYZER_CACHE.get(key)
    if cached and cached.signature == signature:
        return cached

    state = _build_analyzer_state(
        user_id=user_id,
        kb_id=kb_id,
        paths=paths,
        signature=signature,
    )
    _ANALYZER_CACHE[key] = state
    return state


def _tokenize_impl(
    text: str,
    *,
    user_id: str | None,
    kb_id: str | None,
    apply_stopwords: bool,
) -> list[str]:
    state = _get_analyzer_state(user_id=user_id, kb_id=kb_id)
    normalized = _normalize_text(text)
    if not normalized:
        return []

    tokens: list[str] = []
    for piece in state.tokenizer.cut(normalized, cut_all=False):
        chunk = str(piece or "").strip()
        if not chunk:
            continue
        for part in _TOKEN_PART_RE.findall(chunk):
            token = part.strip()
            if not token:
                continue
            if _ASCII_WORD_RE.fullmatch(token) and len(token) < 2:
                continue
            if apply_stopwords and token in state.stopwords:
                continue
            tokens.append(token)
    return tokens


def _tokenize_with_stopword_fallback(
    text: str,
    *,
    user_id: str | None,
    kb_id: str | None,
) -> list[str]:
    stopwords_enabled = bool(getattr(settings, "lexical_stopwords_enabled", True))
    tokens = _tokenize_impl(
        text,
        user_id=user_id,
        kb_id=kb_id,
        apply_stopwords=stopwords_enabled,
    )
    if tokens:
        return tokens
    if stopwords_enabled:
        return _tokenize_impl(
            text,
            user_id=user_id,
            kb_id=kb_id,
            apply_stopwords=False,
        )
    return tokens


def tokenize_for_index(text: str, *, user_id: str | None, kb_id: str | None) -> list[str]:
    return _tokenize_with_stopword_fallback(text, user_id=user_id, kb_id=kb_id)


def tokenize_for_query(text: str, *, user_id: str | None, kb_id: str | None) -> list[str]:
    return _tokenize_with_stopword_fallback(text, user_id=user_id, kb_id=kb_id)
