from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ValidationError


def prune_empty_dicts(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            nested = prune_empty_dicts(item)
            if nested:
                result[key] = nested
            continue
        result[key] = item
    return result


def _delete_loc_path(container: Any, loc: tuple[Any, ...]) -> bool:
    if not loc:
        return False

    current = container
    for segment in loc[:-1]:
        if isinstance(current, dict):
            if segment not in current:
                return False
            current = current[segment]
            continue
        if isinstance(current, list) and isinstance(segment, int):
            if segment < 0 or segment >= len(current):
                return False
            current = current[segment]
            continue
        return False

    leaf = loc[-1]
    if isinstance(current, dict):
        if leaf not in current:
            return False
        current.pop(leaf, None)
        return True
    if isinstance(current, list) and isinstance(leaf, int):
        if leaf < 0 or leaf >= len(current):
            return False
        current.pop(leaf)
        return True
    return False


def normalize_settings_payload_for_read_with_change(
    data: dict[str, Any],
    model_cls: type[BaseModel],
) -> tuple[dict[str, Any], bool]:
    current: dict[str, Any] = deepcopy(data or {})
    changed = False

    while True:
        try:
            validated = model_cls.model_validate(current)
        except ValidationError as exc:
            errors = exc.errors()
            extra_errors = [item for item in errors if item.get("type") == "extra_forbidden"]
            if not extra_errors or len(extra_errors) != len(errors):
                raise

            removed = False
            for item in sorted(extra_errors, key=lambda value: len(value.get("loc") or ()), reverse=True):
                loc = tuple(item.get("loc") or ())
                if _delete_loc_path(current, loc):
                    removed = True
                    changed = True
            if not removed:
                raise
            continue

        normalized = validated.model_dump(exclude_none=True)
        return prune_empty_dicts(normalized), changed


def normalize_settings_payload_for_read(data: dict[str, Any], model_cls: type[BaseModel]) -> dict[str, Any]:
    normalized, _ = normalize_settings_payload_for_read_with_change(data, model_cls)
    return normalized
