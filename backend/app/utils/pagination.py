from __future__ import annotations


def normalize_page_args(
    offset: int | None = 0,
    limit: int | None = 20,
    default: int = 20,
    max_limit: int = 100,
) -> tuple[int, int]:
    normalized_offset = max(0, int(offset or 0))

    resolved_default = max(1, int(default or 20))
    resolved_max = max(resolved_default, int(max_limit or resolved_default))
    raw_limit = int(limit if limit is not None else resolved_default)
    normalized_limit = max(1, min(raw_limit, resolved_max))

    return normalized_offset, normalized_limit
