from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models import User

RUNTIME_VALUE_MISSING = object()

USER_PROVIDER_RUNTIME_KEYS: tuple[str, ...] = (
    "llm_provider",
    "embedding_provider",
    "deepseek_api_key",
    "deepseek_base_url",
    "deepseek_model",
    "qwen_api_key",
    "qwen_base_url",
    "qwen_model",
    "qwen_embedding_model",
    "dashscope_base_url",
    "dashscope_embedding_model",
)

USER_ADVANCED_RUNTIME_KEYS: tuple[str, ...] = (
    "chunk_size",
    "chunk_overlap",
    "index_text_cleanup_enabled",
    "index_text_cleanup_mode",
    "index_text_cleanup_non_pdf_mode",
    "noise_filter_level",
    "noise_drop_low_quality_hits",
    "lexical_stopwords_enabled",
    "lexical_tokenizer_version",
    "ocr_enabled",
    "ocr_engine",
    "ocr_fallback_engines",
    "ocr_language",
    "ocr_tesseract_language",
    "ocr_min_text_length",
    "ocr_render_dpi",
    "ocr_check_pages",
    "ocr_preprocess_enabled",
    "ocr_deskew_enabled",
    "ocr_low_confidence_threshold",
    "pdf_parser_mode",
    "pdf_garbled_ocr_enabled",
    "pdf_garbled_ocr_force",
    "pdf_garbled_ocr_min_len_ratio",
    "pdf_garbled_single_char_line_ratio",
    "pdf_garbled_short_line_ratio",
    "quiz_context_reconstruct_enabled",
    "quiz_context_seed_k_multiplier",
    "quiz_context_neighbor_window",
    "quiz_context_passage_target_chars",
    "quiz_context_fragment_filter_enabled",
    "qa_top_k",
    "qa_fetch_k",
    "qa_bm25_k",
    "qa_dynamic_window_enabled",
    "qa_summary_auto_expand_enabled",
    "qa_summary_top_k",
    "qa_summary_fetch_k",
    "rag_mode",
    "rag_dense_weight",
    "rag_bm25_weight",
)

RUNTIME_USER_SETTING_KEYS = frozenset(USER_PROVIDER_RUNTIME_KEYS + USER_ADVANCED_RUNTIME_KEYS)

_RUNTIME_USER_SETTINGS: ContextVar[dict[str, Any] | None] = ContextVar(
    "runtime_user_settings",
    default=None,
)


def _loads_json(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except Exception:
        return {}
    if not isinstance(value, dict):
        return {}
    return value


def dumps_runtime_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _raw_setting_value(key: str) -> Any:
    return object.__getattribute__(settings, key)


def _model_default(key: str) -> Any:
    field = Settings.model_fields[key]
    if field.default_factory is not None:
        return field.default_factory()
    return deepcopy(field.default)


def provider_runtime_defaults() -> dict[str, Any]:
    return {
        "llm_provider": _model_default("llm_provider"),
        "embedding_provider": _model_default("embedding_provider"),
        "deepseek_api_key": None,
        "deepseek_base_url": _raw_setting_value("deepseek_base_url"),
        "deepseek_model": _raw_setting_value("deepseek_model"),
        "qwen_api_key": None,
        "qwen_base_url": _raw_setting_value("qwen_base_url"),
        "qwen_model": _raw_setting_value("qwen_model"),
        "qwen_embedding_model": _raw_setting_value("qwen_embedding_model"),
        "dashscope_base_url": _raw_setting_value("dashscope_base_url"),
        "dashscope_embedding_model": _raw_setting_value("dashscope_embedding_model"),
    }


def advanced_runtime_defaults() -> dict[str, Any]:
    return {key: _raw_setting_value(key) for key in USER_ADVANCED_RUNTIME_KEYS}


def parse_user_provider_config(text: str | None) -> dict[str, Any]:
    from app.core.provider_config import normalize_provider_config

    return normalize_provider_config(_loads_json(text))


def parse_user_advanced_config(text: str | None) -> dict[str, Any]:
    from app.core.runtime_overrides import normalize_advanced_overrides

    return normalize_advanced_overrides(_loads_json(text))


def build_effective_runtime_settings(
    *,
    provider_config: dict[str, Any] | None = None,
    advanced_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.core.provider_config import provider_runtime_values_from_config

    effective = {
        **provider_runtime_defaults(),
        **advanced_runtime_defaults(),
    }
    if provider_config:
        effective.update(provider_runtime_values_from_config(provider_config))
    if advanced_config:
        effective.update({key: value for key, value in advanced_config.items() if key in USER_ADVANCED_RUNTIME_KEYS})
    return effective


def get_runtime_setting(key: str) -> Any:
    if key not in RUNTIME_USER_SETTING_KEYS:
        return RUNTIME_VALUE_MISSING
    current = _RUNTIME_USER_SETTINGS.get()
    if current is None:
        return RUNTIME_VALUE_MISSING
    if key not in current:
        return RUNTIME_VALUE_MISSING
    return current[key]


def get_runtime_settings() -> dict[str, Any]:
    return deepcopy(_RUNTIME_USER_SETTINGS.get() or {})


def set_runtime_settings(values: dict[str, Any] | None):
    normalized = deepcopy(values) if isinstance(values, dict) else None
    return _RUNTIME_USER_SETTINGS.set(normalized)


def reset_runtime_settings(token) -> None:
    _RUNTIME_USER_SETTINGS.reset(token)


def clear_runtime_settings() -> None:
    _RUNTIME_USER_SETTINGS.set(None)


def build_runtime_settings_for_user(user: User | None) -> dict[str, Any]:
    provider_config = parse_user_provider_config(getattr(user, "provider_config_json", None))
    advanced_config = parse_user_advanced_config(getattr(user, "advanced_config_json", None))
    return build_effective_runtime_settings(
        provider_config=provider_config,
        advanced_config=advanced_config,
    )


def activate_runtime_settings_for_user(user: User | None) -> dict[str, Any]:
    effective = build_runtime_settings_for_user(user)
    _RUNTIME_USER_SETTINGS.set(effective)
    return effective


def activate_runtime_settings_for_user_id(db: Session, user_id: str) -> dict[str, Any]:
    user = db.query(User).filter(User.id == user_id).first()
    return activate_runtime_settings_for_user(user)


@contextmanager
def runtime_settings_scope(
    *,
    provider_config: dict[str, Any] | None = None,
    advanced_config: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    token = set_runtime_settings(
        build_effective_runtime_settings(
            provider_config=provider_config,
            advanced_config=advanced_config,
        )
    )
    try:
        yield get_runtime_settings()
    finally:
        reset_runtime_settings(token)
