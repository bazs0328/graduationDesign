from __future__ import annotations

import json
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.core.config import DEFAULT_AUTH_SECRET_KEY, Settings, settings
from app.core.provider_config import backfill_provider_config_from_runtime
from app.core.runtime_overrides import backfill_system_overrides_from_runtime


def _bootstrap_file_path() -> Path:
    return Path(settings.data_dir) / "system_bootstrap.json"


def _load_bootstrap_file() -> dict[str, Any]:
    path = _bootstrap_file_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _persist_bootstrap_file(data: dict[str, Any]) -> None:
    path = _bootstrap_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_secret(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _auth_secret_from_env() -> str | None:
    secret = _normalize_secret(settings.auth_secret_key)
    if not secret or secret == DEFAULT_AUTH_SECRET_KEY:
        return None
    return secret


def ensure_bootstrap_config() -> dict[str, Any]:
    state = _load_bootstrap_file()
    changed = False

    env_secret = _auth_secret_from_env()
    persisted_secret = _normalize_secret(state.get("auth_secret_key"))

    if env_secret:
        active_secret = env_secret
        if persisted_secret != env_secret:
            state["auth_secret_key"] = env_secret
            changed = True
    elif persisted_secret:
        active_secret = persisted_secret
    else:
        active_secret = secrets.token_urlsafe(48)
        state["auth_secret_key"] = active_secret
        changed = True

    settings.auth_secret_key = active_secret

    if changed or not _bootstrap_file_path().exists():
        _persist_bootstrap_file(state)
    return deepcopy(state)


def _field_default_value(key: str) -> Any:
    field = Settings.model_fields[key]
    if field.default_factory is not None:
        return field.default_factory()
    return deepcopy(field.default)


def run_startup_migrations() -> dict[str, Any]:
    migrated_provider = backfill_provider_config_from_runtime()
    migrated_overrides = backfill_system_overrides_from_runtime(
        default_values={key: _field_default_value(key) for key in Settings.model_fields},
    )
    return {
        "provider_config": migrated_provider,
        "system_overrides": migrated_overrides,
    }
