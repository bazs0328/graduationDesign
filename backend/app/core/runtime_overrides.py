from __future__ import annotations

import json
import threading
import types
from pathlib import Path
from typing import Any, get_args, get_origin

from app.core.config import Settings, settings

# Keep secrets and storage paths in env only; expose non-secret system tuning knobs.
EDITABLE_SYSTEM_KEYS: tuple[str, ...] = (
    "llm_provider",
    "embedding_provider",
    "openai_model",
    "openai_embedding_model",
    "gemini_model",
    "gemini_embedding_model",
    "deepseek_base_url",
    "deepseek_model",
    "deepseek_embedding_model",
    "qwen_base_url",
    "qwen_model",
    "qwen_embedding_model",
    "dashscope_embedding_model",
    "dashscope_base_url",
    "auth_require_login",
    "auth_allow_legacy_user_id",
    "chunk_size",
    "chunk_overlap",
    "index_text_cleanup_enabled",
    "index_text_cleanup_mode",
    "index_text_cleanup_non_pdf_mode",
    "noise_filter_level",
    "noise_drop_low_quality_hits",
    "lexical_stopwords_enabled",
    "lexical_stopwords_global_path",
    "lexical_userdict_global_path",
    "lexical_stopwords_kb_rel_path",
    "lexical_userdict_kb_rel_path",
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
    "qa_summary_auto_expand_enabled",
    "qa_summary_top_k",
    "qa_summary_fetch_k",
    "rag_mode",
    "rag_dense_weight",
    "rag_bm25_weight",
)

_GROUP_ORDER = (
    "providers",
    "auth",
    "retrieval",
    "lexical",
    "ocr",
    "pdf",
    "quiz_context",
    "misc",
)

_GROUP_LABELS: dict[str, str] = {
    "providers": "模型与提供商",
    "auth": "登录与权限",
    "retrieval": "检索与召回",
    "lexical": "词法与分词",
    "ocr": "OCR 识别",
    "pdf": "PDF 解析",
    "quiz_context": "测验上下文重建",
    "misc": "其他",
}

_ENUM_OPTIONS: dict[str, tuple[Any, ...]] = {
    "llm_provider": ("auto", "openai", "gemini", "deepseek", "qwen"),
    "embedding_provider": ("auto", "openai", "gemini", "deepseek", "qwen", "dashscope"),
    "index_text_cleanup_mode": ("balanced", "conservative", "aggressive", "structure_preserving"),
    "index_text_cleanup_non_pdf_mode": ("balanced", "conservative", "aggressive", "structure_preserving"),
    "noise_filter_level": ("balanced", "conservative", "aggressive", "structure_preserving"),
    "ocr_engine": ("rapidocr", "tesseract", "cloud"),
    "pdf_parser_mode": ("auto", "legacy", "layout"),
    "rag_mode": ("hybrid", "dense"),
}

_OPTION_LABELS: dict[str, dict[Any, str]] = {
    "llm_provider": {
        "auto": "自动选择",
        "openai": "OpenAI",
        "gemini": "Gemini",
        "deepseek": "DeepSeek",
        "qwen": "Qwen",
    },
    "embedding_provider": {
        "auto": "自动选择",
        "openai": "OpenAI",
        "gemini": "Gemini",
        "deepseek": "DeepSeek",
        "qwen": "Qwen",
        "dashscope": "DashScope",
    },
    "index_text_cleanup_mode": {
        "balanced": "均衡",
        "conservative": "保守",
        "aggressive": "激进",
        "structure_preserving": "结构优先",
    },
    "index_text_cleanup_non_pdf_mode": {
        "balanced": "均衡",
        "conservative": "保守",
        "aggressive": "激进",
        "structure_preserving": "结构优先",
    },
    "noise_filter_level": {
        "balanced": "均衡",
        "conservative": "保守",
        "aggressive": "激进",
        "structure_preserving": "结构优先",
    },
    "ocr_engine": {
        "rapidocr": "RapidOCR",
        "tesseract": "Tesseract",
        "cloud": "Cloud（预留）",
    },
    "pdf_parser_mode": {
        "auto": "自动",
        "legacy": "legacy 文本层",
        "layout": "layout 布局解析",
    },
    "rag_mode": {
        "hybrid": "混合（向量+词法）",
        "dense": "纯向量",
    },
}

_NUMBER_CONSTRAINTS: dict[str, dict[str, float]] = {
    "chunk_size": {"min": 200, "max": 8000, "step": 50},
    "chunk_overlap": {"min": 0, "max": 4000, "step": 10},
    "ocr_min_text_length": {"min": 1, "max": 500, "step": 1},
    "ocr_render_dpi": {"min": 100, "max": 600, "step": 10},
    "ocr_check_pages": {"min": 1, "max": 20, "step": 1},
    "ocr_low_confidence_threshold": {"min": 0, "max": 1, "step": 0.01},
    "pdf_garbled_ocr_min_len_ratio": {"min": 0, "max": 1, "step": 0.01},
    "pdf_garbled_single_char_line_ratio": {"min": 0, "max": 1, "step": 0.01},
    "pdf_garbled_short_line_ratio": {"min": 0, "max": 1, "step": 0.01},
    "quiz_context_seed_k_multiplier": {"min": 0.1, "max": 10, "step": 0.1},
    "quiz_context_neighbor_window": {"min": 1, "max": 20, "step": 1},
    "quiz_context_passage_target_chars": {"min": 200, "max": 5000, "step": 50},
    "qa_top_k": {"min": 1, "max": 20, "step": 1},
    "qa_fetch_k": {"min": 1, "max": 50, "step": 1},
    "qa_bm25_k": {"min": 1, "max": 100, "step": 1},
    "qa_summary_top_k": {"min": 1, "max": 50, "step": 1},
    "qa_summary_fetch_k": {"min": 1, "max": 100, "step": 1},
    "rag_dense_weight": {"min": 0, "max": 1, "step": 0.05},
    "rag_bm25_weight": {"min": 0, "max": 1, "step": 0.05},
}

_SETTING_LABELS: dict[str, str] = {
    "llm_provider": "对话模型提供商",
    "embedding_provider": "向量模型提供商",
    "openai_model": "OpenAI 对话模型",
    "openai_embedding_model": "OpenAI 向量模型",
    "gemini_model": "Gemini 对话模型",
    "gemini_embedding_model": "Gemini 向量模型",
    "deepseek_base_url": "DeepSeek 基础地址",
    "deepseek_model": "DeepSeek 对话模型",
    "deepseek_embedding_model": "DeepSeek 向量模型",
    "qwen_base_url": "Qwen 基础地址",
    "qwen_model": "Qwen 对话模型",
    "qwen_embedding_model": "Qwen 向量模型",
    "dashscope_embedding_model": "DashScope 多模态向量模型",
    "dashscope_base_url": "DashScope 基础地址",
    "auth_require_login": "接口需要登录",
    "auth_allow_legacy_user_id": "允许 legacy user_id",
    "chunk_size": "分块大小",
    "chunk_overlap": "分块重叠",
    "index_text_cleanup_enabled": "索引前清洗文本",
    "index_text_cleanup_mode": "PDF 清洗模式",
    "index_text_cleanup_non_pdf_mode": "非 PDF 清洗模式",
    "noise_filter_level": "噪声过滤级别",
    "noise_drop_low_quality_hits": "丢弃低质量检索片段",
    "lexical_stopwords_enabled": "启用词法停用词",
    "lexical_stopwords_global_path": "全局停用词路径",
    "lexical_userdict_global_path": "全局用户词典路径",
    "lexical_stopwords_kb_rel_path": "知识库停用词相对路径",
    "lexical_userdict_kb_rel_path": "知识库用户词典相对路径",
    "lexical_tokenizer_version": "词法分词版本",
    "ocr_enabled": "启用 OCR",
    "ocr_engine": "OCR 主引擎",
    "ocr_fallback_engines": "OCR 回退引擎链（逗号分隔）",
    "ocr_language": "OCR 语言包",
    "ocr_tesseract_language": "Tesseract 语言包（可空）",
    "ocr_min_text_length": "触发 OCR 的最小文本长度",
    "ocr_render_dpi": "OCR 渲染 DPI",
    "ocr_check_pages": "扫描检测页数",
    "ocr_preprocess_enabled": "OCR 预处理",
    "ocr_deskew_enabled": "OCR 倾斜校正",
    "ocr_low_confidence_threshold": "OCR 低置信阈值",
    "pdf_parser_mode": "PDF 解析模式",
    "pdf_garbled_ocr_enabled": "启用乱码页 OCR 修复",
    "pdf_garbled_ocr_force": "乱码页强制用 OCR 结果",
    "pdf_garbled_ocr_min_len_ratio": "乱码页 OCR 最小长度比",
    "pdf_garbled_single_char_line_ratio": "单字行比例阈值",
    "pdf_garbled_short_line_ratio": "短行比例阈值",
    "quiz_context_reconstruct_enabled": "启用测验上下文重建",
    "quiz_context_seed_k_multiplier": "测验上下文初始检索倍率",
    "quiz_context_neighbor_window": "测验上下文邻域窗口",
    "quiz_context_passage_target_chars": "测验上下文目标字符数",
    "quiz_context_fragment_filter_enabled": "测验上下文片段过滤",
    "qa_top_k": "问答参考片段数量",
    "qa_fetch_k": "问答候选范围",
    "qa_bm25_k": "BM25 候选数量",
    "qa_summary_auto_expand_enabled": "摘要类问题自动扩展",
    "qa_summary_top_k": "摘要类参考片段数量",
    "qa_summary_fetch_k": "摘要类候选范围",
    "rag_mode": "检索策略",
    "rag_dense_weight": "向量检索权重",
    "rag_bm25_weight": "词法检索权重",
}

_SETTING_DESCRIPTIONS: dict[str, str] = {
    "llm_provider": "使用 auto 时会根据已配置密钥自动选择。",
    "embedding_provider": "使用 auto 时优先跟随对话模型提供商。",
    "ocr_fallback_engines": "示例：rapidocr,tesseract",
    "lexical_stopwords_global_path": "路径相对 backend 工作目录。",
    "lexical_userdict_global_path": "路径相对 backend 工作目录。",
    "dashscope_base_url": "国际站可设为 https://dashscope-intl.aliyuncs.com/api/v1",
}

_LOCK = threading.Lock()
_BASE_VALUES: dict[str, Any] = {key: getattr(settings, key) for key in EDITABLE_SYSTEM_KEYS}


def _overrides_file_path() -> Path:
    return Path(settings.data_dir) / "system_overrides.json"


def _load_file_overrides() -> dict[str, Any]:
    path = _overrides_file_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        if key in EDITABLE_SYSTEM_KEYS:
            normalized[key] = value
    return normalized


def _persist_overrides(data: dict[str, Any]) -> None:
    path = _overrides_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _coerce_with_annotation(value: Any, annotation: Any) -> Any:
    if annotation in (Any, object):
        return value

    origin = get_origin(annotation)
    if origin is None:
        if annotation is bool:
            return _coerce_bool(value)
        if annotation is int:
            if isinstance(value, bool):
                raise ValueError(f"Invalid integer value: {value!r}")
            return int(value)
        if annotation is float:
            if isinstance(value, bool):
                raise ValueError(f"Invalid float value: {value!r}")
            return float(value)
        if annotation is str:
            if value is None:
                raise ValueError("Expected string, got null")
            return str(value)
        return value

    if str(origin).endswith("Union") or origin is types.UnionType:
        args = get_args(annotation)
        if value is None and type(None) in args:
            return None
        first_error: Exception | None = None
        for candidate in args:
            if candidate is type(None):
                continue
            try:
                return _coerce_with_annotation(value, candidate)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error:
            raise first_error
        return value

    return value


def _coerce_value(key: str, value: Any) -> Any:
    if key not in Settings.model_fields:
        return value
    field = Settings.model_fields[key]
    annotation = field.annotation
    return _coerce_with_annotation(value, annotation)


def _apply_overrides(overrides: dict[str, Any]) -> None:
    # Always start from env-derived baseline; then apply runtime overrides.
    for key, base in _BASE_VALUES.items():
        setattr(settings, key, base)
    for key, value in overrides.items():
        if key not in EDITABLE_SYSTEM_KEYS:
            continue
        setattr(settings, key, _coerce_value(key, value))


def _annotation_allows_none(annotation: Any) -> bool:
    if annotation is type(None):
        return True
    origin = get_origin(annotation)
    if origin is None:
        return False
    if str(origin).endswith("Union") or origin is types.UnionType:
        return any(_annotation_allows_none(arg) for arg in get_args(annotation))
    return False


def _unwrap_optional_annotation(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is None:
        return annotation
    if str(origin).endswith("Union") or origin is types.UnionType:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return _unwrap_optional_annotation(args[0])
    return annotation


def _annotation_kind(key: str) -> tuple[str, bool]:
    field = Settings.model_fields.get(key)
    if not field:
        return "string", True
    annotation = field.annotation
    nullable = _annotation_allows_none(annotation)
    base = _unwrap_optional_annotation(annotation)
    if base is bool:
        return "bool", nullable
    if base is int:
        return "int", nullable
    if base is float:
        return "float", nullable
    return "string", nullable


def _group_for_key(key: str) -> str:
    if key.startswith("auth_"):
        return "auth"
    if key.startswith("lexical_"):
        return "lexical"
    if key.startswith("ocr_"):
        return "ocr"
    if key.startswith("pdf_"):
        return "pdf"
    if key.startswith("quiz_context_"):
        return "quiz_context"
    if key in {"llm_provider", "embedding_provider"}:
        return "providers"
    if key.startswith(("openai_", "gemini_", "deepseek_", "qwen_", "dashscope_")):
        return "providers"
    if key.startswith(("chunk_", "index_", "noise_", "qa_", "rag_")):
        return "retrieval"
    return "misc"


def _resolve_field_label(key: str) -> str:
    return _SETTING_LABELS.get(key, key)


def _resolve_input_type(key: str, kind: str) -> str:
    if key in _ENUM_OPTIONS:
        return "select"
    if kind == "bool":
        return "switch"
    if kind in {"int", "float"}:
        return "number"
    return "text"


def _build_system_settings_schema() -> dict[str, Any]:
    groups_used: list[str] = []
    fields: list[dict[str, Any]] = []

    for key in EDITABLE_SYSTEM_KEYS:
        kind, nullable = _annotation_kind(key)
        group = _group_for_key(key)
        if group not in groups_used:
            groups_used.append(group)

        item: dict[str, Any] = {
            "key": key,
            "label": _resolve_field_label(key),
            "group": group,
            "input_type": _resolve_input_type(key, kind),
            "nullable": bool(nullable),
            "description": _SETTING_DESCRIPTIONS.get(key),
            "options": [],
            "min": None,
            "max": None,
            "step": None,
        }

        if key in _ENUM_OPTIONS:
            value_label_map = _OPTION_LABELS.get(key, {})
            item["options"] = [
                {"value": value, "label": value_label_map.get(value, str(value))}
                for value in _ENUM_OPTIONS[key]
            ]

        if kind in {"int", "float"} and key in _NUMBER_CONSTRAINTS:
            cfg = _NUMBER_CONSTRAINTS[key]
            item["min"] = cfg.get("min")
            item["max"] = cfg.get("max")
            item["step"] = cfg.get("step")

        fields.append(item)

    groups = [
        {"id": group_id, "label": _GROUP_LABELS.get(group_id, group_id)}
        for group_id in _GROUP_ORDER
        if group_id in groups_used
    ]
    return {"groups": groups, "fields": fields}


_SYSTEM_SETTINGS_SCHEMA: dict[str, Any] = _build_system_settings_schema()


def load_system_overrides() -> dict[str, Any]:
    with _LOCK:
        overrides = _load_file_overrides()
        _apply_overrides(overrides)
        return dict(overrides)


def patch_system_overrides(patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise ValueError("values must be a JSON object")
    with _LOCK:
        current = _load_file_overrides()
        for key, value in patch.items():
            if key not in EDITABLE_SYSTEM_KEYS:
                raise ValueError(f"Unsupported system setting key: {key}")
            if value is None:
                current.pop(key, None)
                continue
            current[key] = _coerce_value(key, value)
        _persist_overrides(current)
        _apply_overrides(current)
        return dict(current)


def reset_system_overrides(keys: list[str] | None = None) -> dict[str, Any]:
    with _LOCK:
        if not keys:
            current: dict[str, Any] = {}
        else:
            current = _load_file_overrides()
            for key in keys:
                if key not in EDITABLE_SYSTEM_KEYS:
                    raise ValueError(f"Unsupported system setting key: {key}")
                current.pop(key, None)
        _persist_overrides(current)
        _apply_overrides(current)
        return dict(current)


def get_system_settings_payload() -> dict[str, Any]:
    with _LOCK:
        overrides = _load_file_overrides()
        effective = {key: getattr(settings, key) for key in EDITABLE_SYSTEM_KEYS}
    return {
        "editable_keys": list(EDITABLE_SYSTEM_KEYS),
        "overrides": overrides,
        "effective": effective,
        "schema": _SYSTEM_SETTINGS_SCHEMA,
    }
