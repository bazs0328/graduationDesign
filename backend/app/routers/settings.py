import json
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.knowledge_bases import ensure_kb
from app.core.users import ensure_user
from app.db import get_db
from app.models import KnowledgeBase, User
from app.schemas import (
    KbSettingsPayload,
    SettingsMeta,
    SettingsPatchRequest,
    SettingsResetRequest,
    SettingsResponse,
    SettingsSystemStatus,
    UserSettingsPayload,
)

router = APIRouter(prefix="/settings", tags=["settings"])

RETRIEVAL_PRESET_MAP: dict[str, dict[str, int]] = {
    "fast": {"top_k": 3, "fetch_k": 8},
    "balanced": {"top_k": 4, "fetch_k": 12},
    "deep": {"top_k": 6, "fetch_k": 20},
}

DEFAULT_USER_SETTINGS: dict[str, Any] = {
    "qa": {
        "mode": "normal",
        "retrieval_preset": "balanced",
        "top_k": None,
        "fetch_k": None,
    },
    "quiz": {
        "count_default": 5,
        "auto_adapt_default": True,
        "difficulty_default": "medium",
    },
    "ui": {
        "show_advanced_controls": False,
        "density": "comfortable",
    },
    "upload": {
        "post_upload_suggestions": True,
    },
}

DEFAULT_KB_OVERRIDES: dict[str, Any] = {
    "qa": {},
    "quiz": {},
}

META_RANGES = {
    "qa": {"top_k_min": 1, "top_k_max": 20, "fetch_k_min": 1, "fetch_k_max": 50},
    "quiz": {"count_min": 1, "count_max": 20},
}


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


def _dumps_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _prune_empty_dicts(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            nested = _prune_empty_dicts(item)
            if nested:
                result[key] = nested
            continue
        result[key] = item
    return result


def _normalize_user_settings(data: dict[str, Any]) -> dict[str, Any]:
    validated = UserSettingsPayload.model_validate(data or {})
    normalized = validated.model_dump(exclude_none=True)
    return _prune_empty_dicts(normalized)


def _normalize_kb_settings(data: dict[str, Any]) -> dict[str, Any]:
    validated = KbSettingsPayload.model_validate(data or {})
    normalized = validated.model_dump(exclude_none=True)
    return _prune_empty_dicts(normalized)


def _normalize_user_settings_patch(data: dict[str, Any]) -> dict[str, Any]:
    # Keep explicit nulls so PATCH can clear nullable fields (e.g., top_k/fetch_k).
    validated = UserSettingsPayload.model_validate(data or {})
    normalized = validated.model_dump(exclude_unset=True)
    return _prune_empty_dicts(normalized)


def _normalize_kb_settings_patch(data: dict[str, Any]) -> dict[str, Any]:
    # Keep explicit nulls so KB overrides can revert to "follow user default".
    validated = KbSettingsPayload.model_validate(data or {})
    normalized = validated.model_dump(exclude_unset=True)
    return _prune_empty_dicts(normalized)


def _effective_user_settings(user_defaults: dict[str, Any], kb_overrides: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_merge(_deep_merge(DEFAULT_USER_SETTINGS, user_defaults), kb_overrides)
    qa_settings = merged.setdefault("qa", {})
    preset_name = str(qa_settings.get("retrieval_preset") or "balanced").strip().lower()
    preset = RETRIEVAL_PRESET_MAP.get(preset_name, RETRIEVAL_PRESET_MAP["balanced"])
    if qa_settings.get("top_k") is None:
        qa_settings["top_k"] = int(preset["top_k"])
    if qa_settings.get("fetch_k") is None:
        qa_settings["fetch_k"] = int(preset["fetch_k"])
    if qa_settings.get("mode") not in {"normal", "explain"}:
        qa_settings["mode"] = "normal"
    return merged


def _system_status() -> SettingsSystemStatus:
    secrets_configured = {
        "openai_api_key": bool(settings.openai_api_key),
        "google_api_key": bool(settings.google_api_key),
        "deepseek_api_key": bool(settings.deepseek_api_key),
        "qwen_api_key": bool(settings.qwen_api_key),
        "auth_secret_key_customized": bool(settings.auth_secret_key and settings.auth_secret_key != "gradtutor-dev-secret"),
    }
    return SettingsSystemStatus(
        llm_provider=settings.llm_provider,
        embedding_provider=settings.embedding_provider,
        qa_defaults_from_env={
            "qa_top_k": settings.qa_top_k,
            "qa_fetch_k": settings.qa_fetch_k,
            "qa_bm25_k": settings.qa_bm25_k,
            "rag_mode": settings.rag_mode,
            "rag_dense_weight": settings.rag_dense_weight,
            "rag_bm25_weight": settings.rag_bm25_weight,
        },
        ocr_enabled=bool(settings.ocr_enabled),
        pdf_parser_mode=settings.pdf_parser_mode,
        auth_require_login=bool(settings.auth_require_login),
        secrets_configured=secrets_configured,
        version_info={"app_name": settings.app_name},
    )


def _meta() -> SettingsMeta:
    return SettingsMeta(
        qa_modes=["normal", "explain"],
        retrieval_presets=["fast", "balanced", "deep"],
        quiz_difficulty_options=["easy", "medium", "hard"],
        preset_map=deepcopy(RETRIEVAL_PRESET_MAP),
        ranges=deepcopy(META_RANGES),
        defaults=deepcopy(DEFAULT_USER_SETTINGS),
    )


def _get_user(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _resolve_kb_or_404(db: Session, user_id: str, kb_id: str | None) -> KnowledgeBase:
    try:
        return ensure_kb(db, user_id, kb_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _build_response(
    db: Session,
    *,
    resolved_user_id: str,
    kb_id: str | None = None,
) -> SettingsResponse:
    user = _get_user(db, resolved_user_id)
    user_defaults = _normalize_user_settings(_loads_json(user.preferences_json))

    kb_overrides: dict[str, Any] = {}
    kb_payload: KbSettingsPayload | None = None
    if kb_id:
        kb = _resolve_kb_or_404(db, resolved_user_id, kb_id)
        kb_overrides = _normalize_kb_settings(_loads_json(kb.preferences_json))
        kb_payload = KbSettingsPayload.model_validate(kb_overrides or {})

    effective = _effective_user_settings(user_defaults, kb_overrides)

    return SettingsResponse(
        system_status=_system_status(),
        user_defaults=UserSettingsPayload.model_validate(user_defaults),
        kb_overrides=kb_payload,
        effective=UserSettingsPayload.model_validate(effective),
        meta=_meta(),
    )


@router.get("", response_model=SettingsResponse)
def get_settings(user_id: str | None = None, kb_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    return _build_response(db, resolved_user_id=resolved_user_id, kb_id=kb_id)


@router.patch("/user", response_model=SettingsResponse)
def patch_user_settings(payload: SettingsPatchRequest, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, payload.user_id)
    user = _get_user(db, resolved_user_id)
    existing = _normalize_user_settings(_loads_json(user.preferences_json))

    patch_dict = payload.model_dump(exclude_unset=True)
    patch_dict.pop("user_id", None)
    normalized_patch = _normalize_user_settings_patch(patch_dict)
    merged = _normalize_user_settings(_deep_merge(existing, normalized_patch))

    user.preferences_json = _dumps_json(merged) if merged else None
    db.add(user)
    db.commit()
    return _build_response(db, resolved_user_id=resolved_user_id)


@router.patch("/kb/{kb_id}", response_model=SettingsResponse)
def patch_kb_settings(kb_id: str, payload: SettingsPatchRequest, db: Session = Depends(get_db)):
    if payload.ui is not None or payload.upload is not None:
        raise HTTPException(status_code=400, detail="KB overrides only support qa and quiz settings")

    resolved_user_id = ensure_user(db, payload.user_id)
    kb = _resolve_kb_or_404(db, resolved_user_id, kb_id)
    existing = _normalize_kb_settings(_loads_json(kb.preferences_json))

    patch_dict = payload.model_dump(exclude_unset=True)
    patch_dict.pop("user_id", None)
    patch_dict.pop("ui", None)
    patch_dict.pop("upload", None)
    normalized_patch = _normalize_kb_settings_patch(patch_dict)
    merged = _normalize_kb_settings(_deep_merge(existing, normalized_patch))

    kb.preferences_json = _dumps_json(merged) if merged else None
    db.add(kb)
    db.commit()
    return _build_response(db, resolved_user_id=resolved_user_id, kb_id=kb.id)


@router.post("/reset", response_model=SettingsResponse)
def reset_settings(payload: SettingsResetRequest, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, payload.user_id)
    if payload.scope == "user":
        user = _get_user(db, resolved_user_id)
        user.preferences_json = None
        db.add(user)
        db.commit()
        return _build_response(db, resolved_user_id=resolved_user_id, kb_id=payload.kb_id)

    if not payload.kb_id:
        raise HTTPException(status_code=400, detail="kb_id is required when scope=kb")
    kb = _resolve_kb_or_404(db, resolved_user_id, payload.kb_id)
    kb.preferences_json = None
    db.add(kb)
    db.commit()
    return _build_response(db, resolved_user_id=resolved_user_id, kb_id=kb.id)
