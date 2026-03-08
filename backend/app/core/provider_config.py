from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

from openai import OpenAI

from app.core.config import Settings, settings
from app.core.llm import (
    _UNCONFIGURED_PROVIDER,
    embedding_provider_status,
    get_embeddings,
    llm_provider_status,
    resolve_embedding_provider,
    resolve_llm_provider,
)
from app.core.runtime_user_config import runtime_settings_scope

SUPPORTED_LLM_PROVIDERS: tuple[str, ...] = ("auto", "deepseek", "qwen")
SUPPORTED_EMBEDDING_PROVIDERS: tuple[str, ...] = ("auto", "qwen", "dashscope")

QWEN_REGION_PRESETS: dict[str, dict[str, str | None]] = {
    "china": {
        "label": "中国站",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "international": {
        "label": "国际站",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    },
    "custom": {
        "label": "自定义",
        "base_url": None,
    },
}

DASHSCOPE_REGION_PRESETS: dict[str, dict[str, str | None]] = {
    "china": {
        "label": "中国站",
        "base_url": "https://dashscope.aliyuncs.com/api/v1",
    },
    "international": {
        "label": "国际站",
        "base_url": "https://dashscope-intl.aliyuncs.com/api/v1",
    },
    "custom": {
        "label": "自定义",
        "base_url": None,
    },
}

PROVIDER_RUNTIME_KEYS: tuple[str, ...] = (
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

LEGACY_PROVIDER_FALLBACK_KEYS: tuple[str, ...] = (
    "llm_provider",
    "embedding_provider",
    "deepseek_base_url",
    "deepseek_model",
    "qwen_base_url",
    "qwen_model",
    "qwen_embedding_model",
    "dashscope_base_url",
    "dashscope_embedding_model",
)

_BASE_PROVIDER_VALUES: dict[str, Any] = {key: object.__getattribute__(settings, key) for key in PROVIDER_RUNTIME_KEYS}
_LOCK = threading.Lock()


def _provider_file_path() -> Path:
    return Path(settings.data_dir) / "system_provider_config.json"


def _legacy_overrides_path() -> Path:
    return Path(settings.data_dir) / "system_overrides.json"


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _persist_json_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_region(value: Any) -> str | None:
    text = _normalize_text(value)
    if text in {"china", "international", "custom"}:
        return text
    return None


def _normalize_embedding_provider_choice(value: Any) -> str | None:
    text = _normalize_text(value)
    if text in {"deepseek", "openai", "gemini"}:
        return "auto"
    return text


def _normalize_llm_provider_choice(value: Any) -> str | None:
    text = _normalize_text(value)
    if text in {"openai", "gemini"}:
        return "auto"
    return text


def _mask_secret(value: str | None) -> str | None:
    secret = _normalize_text(value)
    if not secret:
        return None
    suffix = secret[-4:] if len(secret) >= 4 else secret
    return f"••••{suffix}"


def _resolve_qwen_region(base_url: str | None) -> str:
    normalized = _normalize_text(base_url)
    if normalized == QWEN_REGION_PRESETS["china"]["base_url"]:
        return "china"
    if normalized == QWEN_REGION_PRESETS["international"]["base_url"]:
        return "international"
    return "custom"


def _resolve_dashscope_region(base_url: str | None) -> str:
    normalized = _normalize_text(base_url)
    if not normalized or normalized == DASHSCOPE_REGION_PRESETS["china"]["base_url"]:
        return "china"
    if normalized == DASHSCOPE_REGION_PRESETS["international"]["base_url"]:
        return "international"
    return "custom"


def _resolve_preset_base_url(preset_map: dict[str, dict[str, str | None]], region: str | None, current: str | None) -> str | None:
    if region in {"china", "international"}:
        return str(preset_map[region]["base_url"] or "")
    return _normalize_text(current)


def normalize_provider_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    deepseek = data.get("deepseek") if isinstance(data.get("deepseek"), dict) else {}
    qwen = data.get("qwen") if isinstance(data.get("qwen"), dict) else {}
    dashscope = data.get("dashscope") if isinstance(data.get("dashscope"), dict) else {}

    normalized: dict[str, Any] = {}

    llm_provider = _normalize_llm_provider_choice(data.get("llm_provider"))
    if llm_provider in SUPPORTED_LLM_PROVIDERS:
        normalized["llm_provider"] = llm_provider

    embedding_provider = _normalize_embedding_provider_choice(data.get("embedding_provider"))
    if embedding_provider in SUPPORTED_EMBEDDING_PROVIDERS:
        normalized["embedding_provider"] = embedding_provider

    deepseek_block: dict[str, Any] = {}
    if "api_key" in deepseek:
        deepseek_block["api_key"] = _normalize_text(deepseek.get("api_key"))
    if "base_url" in deepseek:
        deepseek_block["base_url"] = _normalize_text(deepseek.get("base_url"))
    if "model" in deepseek:
        deepseek_block["model"] = _normalize_text(deepseek.get("model"))
    if deepseek_block:
        normalized["deepseek"] = deepseek_block

    qwen_block: dict[str, Any] = {}
    if qwen:
        qwen_region = _normalize_region(qwen.get("region"))
        if qwen_region is None and "base_url" in qwen:
            qwen_region = _resolve_qwen_region(_normalize_text(qwen.get("base_url")))
        if "api_key" in qwen:
            qwen_block["api_key"] = _normalize_text(qwen.get("api_key"))
        if "region" in qwen and qwen_region:
            qwen_block["region"] = qwen_region
        if "base_url" in qwen or ("region" in qwen and qwen_region):
            qwen_block["base_url"] = _resolve_preset_base_url(
                QWEN_REGION_PRESETS,
                qwen_region,
                qwen.get("base_url"),
            )
        if "model" in qwen:
            qwen_block["model"] = _normalize_text(qwen.get("model"))
        if "embedding_model" in qwen:
            qwen_block["embedding_model"] = _normalize_text(qwen.get("embedding_model"))
    if qwen_block:
        normalized["qwen"] = qwen_block

    dashscope_block: dict[str, Any] = {}
    if dashscope:
        dashscope_region = _normalize_region(dashscope.get("region"))
        if dashscope_region is None and "base_url" in dashscope:
            dashscope_region = _resolve_dashscope_region(_normalize_text(dashscope.get("base_url")))
        if "region" in dashscope and dashscope_region:
            dashscope_block["region"] = dashscope_region
        if "base_url" in dashscope or ("region" in dashscope and dashscope_region):
            dashscope_block["base_url"] = _resolve_preset_base_url(
                DASHSCOPE_REGION_PRESETS,
                dashscope_region,
                dashscope.get("base_url"),
            )
        if "embedding_model" in dashscope:
            dashscope_block["embedding_model"] = _normalize_text(dashscope.get("embedding_model"))
    if dashscope_block:
        normalized["dashscope"] = dashscope_block

    return normalized


def _load_persisted_provider_config() -> dict[str, Any]:
    return normalize_provider_config(_load_json_file(_provider_file_path()))


def _load_legacy_provider_fallbacks() -> dict[str, Any]:
    raw = _load_json_file(_legacy_overrides_path())
    fallback: dict[str, Any] = {}
    for key in LEGACY_PROVIDER_FALLBACK_KEYS:
        if key in raw:
            if key == "llm_provider":
                fallback[key] = _normalize_llm_provider_choice(raw[key])
            elif key == "embedding_provider":
                fallback[key] = _normalize_embedding_provider_choice(raw[key])
            else:
                fallback[key] = raw[key]
    return fallback


def _apply_provider_values(config: dict[str, Any]) -> None:
    for key, value in _BASE_PROVIDER_VALUES.items():
        if key == "llm_provider":
            setattr(settings, key, _normalize_llm_provider_choice(value) or "auto")
        elif key == "embedding_provider":
            setattr(settings, key, _normalize_embedding_provider_choice(value) or "auto")
        else:
            setattr(settings, key, value)

    for key, value in _load_legacy_provider_fallbacks().items():
        setattr(settings, key, value)

    if "llm_provider" in config:
        settings.llm_provider = config["llm_provider"]
    if "embedding_provider" in config:
        settings.embedding_provider = config["embedding_provider"]

    deepseek = config.get("deepseek") if isinstance(config.get("deepseek"), dict) else {}
    if "api_key" in deepseek:
        settings.deepseek_api_key = deepseek.get("api_key")
    if "base_url" in deepseek and deepseek.get("base_url") is not None:
        settings.deepseek_base_url = deepseek.get("base_url")
    if "model" in deepseek and deepseek.get("model") is not None:
        settings.deepseek_model = deepseek.get("model")

    qwen = config.get("qwen") if isinstance(config.get("qwen"), dict) else {}
    if "api_key" in qwen:
        settings.qwen_api_key = qwen.get("api_key")
    if "base_url" in qwen and qwen.get("base_url") is not None:
        settings.qwen_base_url = qwen.get("base_url")
    if "model" in qwen and qwen.get("model") is not None:
        settings.qwen_model = qwen.get("model")
    if "embedding_model" in qwen and qwen.get("embedding_model") is not None:
        settings.qwen_embedding_model = qwen.get("embedding_model")

    dashscope = config.get("dashscope") if isinstance(config.get("dashscope"), dict) else {}
    if "base_url" in dashscope:
        settings.dashscope_base_url = dashscope.get("base_url")
    if "embedding_model" in dashscope and dashscope.get("embedding_model") is not None:
        settings.dashscope_embedding_model = dashscope.get("embedding_model")


def load_provider_config() -> dict[str, Any]:
    with _LOCK:
        return deepcopy(_load_persisted_provider_config())


def _seed_provider_block_from_runtime(current: dict[str, Any], runtime_values: dict[str, Any], *, allow_region: bool = False) -> dict[str, Any]:
    next_block = deepcopy(current or {})

    for key in ("api_key", "base_url", "model", "embedding_model"):
        if key in next_block:
            continue
        runtime_value = _normalize_text(runtime_values.get(key))
        if runtime_value is not None:
            next_block[key] = runtime_value

    if allow_region and "region" not in next_block:
        runtime_region = _normalize_region(runtime_values.get("region"))
        if runtime_region is not None:
            next_block["region"] = runtime_region

    return next_block


def _model_default(key: str) -> Any:
    field = Settings.model_fields[key]
    if field.default_factory is not None:
        return field.default_factory()
    return deepcopy(field.default)


def backfill_provider_config_from_runtime() -> dict[str, Any]:
    # Provider secrets are no longer migrated into a shared global file.
    with _LOCK:
        return deepcopy(_load_persisted_provider_config())


def _provider_missing_fields(provider: str, *, target: str) -> list[str]:
    missing: list[str] = []
    if target == "llm":
        if provider == "deepseek":
            if not _normalize_text(settings.deepseek_api_key):
                missing.append("deepseek.api_key")
            if not _normalize_text(settings.deepseek_base_url):
                missing.append("deepseek.base_url")
            if not _normalize_text(settings.deepseek_model):
                missing.append("deepseek.model")
        elif provider == "qwen":
            if not _normalize_text(settings.qwen_api_key):
                missing.append("qwen.api_key")
            if not _normalize_text(settings.qwen_base_url):
                missing.append("qwen.base_url")
            if not _normalize_text(settings.qwen_model):
                missing.append("qwen.model")
        elif provider == _UNCONFIGURED_PROVIDER:
            missing.extend(["deepseek.api_key", "qwen.api_key"])
        return missing

    if provider == "deepseek":
        missing.extend(_provider_missing_fields("qwen", target="embedding"))
    elif provider == "qwen":
        if not _normalize_text(settings.qwen_api_key):
            missing.append("qwen.api_key")
        if not _normalize_text(settings.qwen_base_url):
            missing.append("qwen.base_url")
        if not _normalize_text(settings.qwen_embedding_model):
            missing.append("qwen.embedding_model")
    elif provider == "dashscope":
        if not _normalize_text(settings.qwen_api_key):
            missing.append("qwen.api_key")
        dashscope_url = settings.dashscope_base_url or DASHSCOPE_REGION_PRESETS["china"]["base_url"]
        if not _normalize_text(dashscope_url):
            missing.append("dashscope.base_url")
        if not _normalize_text(settings.dashscope_embedding_model):
            missing.append("dashscope.embedding_model")
    elif provider == _UNCONFIGURED_PROVIDER:
        missing.extend(_provider_missing_fields("qwen", target="embedding"))
    return missing


def provider_setup_status() -> dict[str, Any]:
    llm_status = llm_provider_status()
    embedding_status = embedding_provider_status(resolved_llm_provider=llm_status["resolved"])
    llm_ready = llm_status["resolved"] != _UNCONFIGURED_PROVIDER and not _provider_missing_fields(
        llm_status["resolved"],
        target="llm",
    )
    embedding_ready = (
        embedding_status["resolved"] != _UNCONFIGURED_PROVIDER
        and not _provider_missing_fields(embedding_status["resolved"], target="embedding")
    )
    missing = []
    missing.extend(_provider_missing_fields(llm_status["resolved"], target="llm"))
    missing.extend(_provider_missing_fields(embedding_status["resolved"], target="embedding"))
    return {
        "llm_ready": bool(llm_ready),
        "embedding_ready": bool(embedding_ready),
        "missing": sorted(set(missing)),
        "current_llm_provider": llm_status["resolved"],
        "current_embedding_provider": embedding_status["resolved"],
    }


def get_provider_compatibility_notices() -> list[str]:
    notices: list[str] = []
    legacy_file = _load_persisted_provider_config()
    legacy_overrides = _load_legacy_provider_fallbacks()
    raw_llm_provider = _normalize_text(legacy_file.get("llm_provider") or legacy_overrides.get("llm_provider"))
    raw_embedding_provider = _normalize_text(
        legacy_file.get("embedding_provider") or legacy_overrides.get("embedding_provider")
    )

    if raw_llm_provider in {"openai", "gemini"}:
        notices.append(
            f"检测到旧的对话 provider 配置 {raw_llm_provider}，当前账号配置已不再提供该选项，会回退为 auto。"
        )
    if raw_embedding_provider in {"openai", "gemini"}:
        notices.append(
            f"检测到旧的向量 provider 配置 {raw_embedding_provider}，当前账号配置已不再提供该选项，会回退为 auto。"
        )
    if legacy_file:
        notices.append("检测到历史全局 provider 配置文件；其密钥不会自动继承到当前账号。")
    return notices


def get_provider_config_payload() -> dict[str, Any]:
    setup = provider_setup_status()
    effective_llm_provider = _normalize_llm_provider_choice(settings.llm_provider) or "auto"
    effective_embedding_provider = _normalize_embedding_provider_choice(settings.embedding_provider) or "auto"
    qwen_base_url = _normalize_text(settings.qwen_base_url)
    dashscope_base_url = _normalize_text(settings.dashscope_base_url) or str(
        DASHSCOPE_REGION_PRESETS["china"]["base_url"] or ""
    )

    return {
        "editable": True,
        "read_only_reason": None,
        "supported_llm_providers": list(SUPPORTED_LLM_PROVIDERS),
        "supported_embedding_providers": list(SUPPORTED_EMBEDDING_PROVIDERS),
        "region_presets": {
            "qwen": [
                {"id": key, "label": value["label"], "base_url": value["base_url"]}
                for key, value in QWEN_REGION_PRESETS.items()
            ],
            "dashscope": [
                {"id": key, "label": value["label"], "base_url": value["base_url"]}
                for key, value in DASHSCOPE_REGION_PRESETS.items()
            ],
        },
        "effective": {
            "llm_provider": effective_llm_provider,
            "embedding_provider": effective_embedding_provider,
            "deepseek": {
                "api_key_configured": bool(_normalize_text(settings.deepseek_api_key)),
                "api_key_masked": _mask_secret(settings.deepseek_api_key),
                "base_url": _normalize_text(settings.deepseek_base_url),
                "model": _normalize_text(settings.deepseek_model),
                "embedding_model": _normalize_text(settings.deepseek_embedding_model),
            },
            "qwen": {
                "api_key_configured": bool(_normalize_text(settings.qwen_api_key)),
                "api_key_masked": _mask_secret(settings.qwen_api_key),
                "region": _resolve_qwen_region(qwen_base_url),
                "base_url": qwen_base_url,
                "model": _normalize_text(settings.qwen_model),
                "embedding_model": _normalize_text(settings.qwen_embedding_model),
            },
            "dashscope": {
                "region": _resolve_dashscope_region(dashscope_base_url),
                "base_url": dashscope_base_url,
                "embedding_model": _normalize_text(settings.dashscope_embedding_model),
                "using_shared_api_key": True,
            },
        },
        "setup": setup,
    }


def _merge_provider_block(current: dict[str, Any], patch: dict[str, Any] | None, *, allow_region: bool = False) -> dict[str, Any]:
    next_block = deepcopy(current or {})
    incoming = patch or {}
    for key in ("base_url", "model", "embedding_model"):
        if key in incoming:
            next_block[key] = _normalize_text(incoming.get(key))
    if "api_key" in incoming:
        next_block["api_key"] = _normalize_text(incoming.get("api_key"))
    if allow_region and "region" in incoming:
        next_block["region"] = _normalize_region(incoming.get("region"))
    if incoming.get("clear_api_key") is True:
        next_block["api_key"] = None
    return next_block


def _merge_provider_config(current: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(current or {})
    normalized_llm_provider = _normalize_llm_provider_choice(values.get("llm_provider"))
    if "llm_provider" in values and normalized_llm_provider in SUPPORTED_LLM_PROVIDERS:
        merged["llm_provider"] = normalized_llm_provider
    normalized_embedding_provider = _normalize_embedding_provider_choice(values.get("embedding_provider"))
    if "embedding_provider" in values and normalized_embedding_provider in SUPPORTED_EMBEDDING_PROVIDERS:
        merged["embedding_provider"] = normalized_embedding_provider

    if "deepseek" in values:
        merged["deepseek"] = _merge_provider_block(
            merged.get("deepseek", {}),
            values.get("deepseek") if isinstance(values.get("deepseek"), dict) else {},
        )
    if "qwen" in values:
        merged["qwen"] = _merge_provider_block(
            merged.get("qwen", {}),
            values.get("qwen") if isinstance(values.get("qwen"), dict) else {},
            allow_region=True,
        )
    if "dashscope" in values:
        merged["dashscope"] = _merge_provider_block(
            merged.get("dashscope", {}),
            values.get("dashscope") if isinstance(values.get("dashscope"), dict) else {},
            allow_region=True,
        )

    return normalize_provider_config(merged)


def merge_provider_config(current: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    return _merge_provider_config(current, values)


def provider_runtime_values_from_config(config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_provider_config(config)
    runtime: dict[str, Any] = {}

    if "llm_provider" in normalized:
        runtime["llm_provider"] = normalized["llm_provider"]
    if "embedding_provider" in normalized:
        runtime["embedding_provider"] = normalized["embedding_provider"]

    deepseek = normalized.get("deepseek") if isinstance(normalized.get("deepseek"), dict) else {}
    if "api_key" in deepseek:
        runtime["deepseek_api_key"] = deepseek.get("api_key")
    if "base_url" in deepseek:
        runtime["deepseek_base_url"] = deepseek.get("base_url")
    if "model" in deepseek:
        runtime["deepseek_model"] = deepseek.get("model")

    qwen = normalized.get("qwen") if isinstance(normalized.get("qwen"), dict) else {}
    if "api_key" in qwen:
        runtime["qwen_api_key"] = qwen.get("api_key")
    if "base_url" in qwen:
        runtime["qwen_base_url"] = qwen.get("base_url")
    if "model" in qwen:
        runtime["qwen_model"] = qwen.get("model")
    if "embedding_model" in qwen:
        runtime["qwen_embedding_model"] = qwen.get("embedding_model")

    dashscope = normalized.get("dashscope") if isinstance(normalized.get("dashscope"), dict) else {}
    if "base_url" in dashscope:
        runtime["dashscope_base_url"] = dashscope.get("base_url")
    if "embedding_model" in dashscope:
        runtime["dashscope_embedding_model"] = dashscope.get("embedding_model")

    return runtime


def patch_provider_config(values: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        current = _load_persisted_provider_config()
        return deepcopy(_merge_provider_config(current, values))


@contextmanager
def preview_provider_config(
    current_config: dict[str, Any],
    values: dict[str, Any],
    *,
    advanced_config: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    preview = _merge_provider_config(current_config, values)
    with runtime_settings_scope(provider_config=preview, advanced_config=advanced_config):
        yield deepcopy(preview)


def _test_openai_compatible_llm(api_key: str | None, base_url: str | None, model: str | None) -> None:
    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        client.models.list()
        return
    except Exception:
        pass
    client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=1,
    )


def test_provider_connection(
    current_config: dict[str, Any],
    values: dict[str, Any],
    target: str = "auto",
    *,
    advanced_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with preview_provider_config(current_config, values, advanced_config=advanced_config):
        llm_status = llm_provider_status()
        resolved_target = target
        if resolved_target == "auto":
            if llm_status["resolved"] in {"deepseek", "qwen"}:
                resolved_target = "llm"
            else:
                resolved_target = "embedding"

        if resolved_target == "llm":
            provider, _, _ = resolve_llm_provider(strict=True)
            if provider == "deepseek":
                _test_openai_compatible_llm(settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model)
            elif provider == "qwen":
                _test_openai_compatible_llm(settings.qwen_api_key, settings.qwen_base_url, settings.qwen_model)
            else:
                raise ValueError(f"当前对话 provider 不在本期前端支持范围：{provider}")
            return {
                "ok": True,
                "provider": provider,
                "target": "llm",
                "message": f"{provider} 对话模型连接正常",
            }

        resolved_llm = llm_status["resolved"]
        if resolved_llm == _UNCONFIGURED_PROVIDER:
            resolved_llm = None
        provider, _, _ = resolve_embedding_provider(strict=True, resolved_llm_provider=resolved_llm)
        if provider not in {"qwen", "dashscope"}:
            raise ValueError(f"当前向量 provider 不在本期前端支持范围：{provider}")
        embeddings = get_embeddings()
        embeddings.embed_query("连接测试")
        return {
            "ok": True,
            "provider": provider,
            "target": "embedding",
            "message": f"{provider} 向量模型连接正常",
        }
