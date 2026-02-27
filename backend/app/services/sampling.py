from __future__ import annotations


def sample_evenly(chunks: list[str], max_count: int) -> list[str]:
    """Evenly sample chunks when there are more than max_count."""
    if len(chunks) <= max_count:
        return chunks
    step = len(chunks) / max_count
    return [chunks[int(i * step)] for i in range(max_count)]
