from __future__ import annotations


def build_chroma_eq_filter(**kwargs) -> dict | None:
    """Build a Chroma where/filter dict compatible with multi-condition equality.

    Chroma 1.4.x rejects multi-key flat dicts (e.g. {"doc_id": "...", "type": "keypoint"})
    and expects an explicit operator wrapper when multiple conditions are present.
    """
    conditions: list[tuple[str, object]] = [
        (key, value)
        for key, value in kwargs.items()
        if value is not None
    ]
    if not conditions:
        return None
    if len(conditions) == 1:
        key, value = conditions[0]
        return {key: value}
    return {"$and": [{key: value} for key, value in conditions]}
