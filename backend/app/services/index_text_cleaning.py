from __future__ import annotations

import re
from typing import Any

from app.services.text_noise_guard import clean_fragment_with_stats


_CHINESE_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_PINYIN_PAIR_RE = re.compile(r"([\u4e00-\u9fff])([A-Za-z]{1,8})")


def _normalize_text(text: str) -> str:
    normalized = (text or "").replace("\x00", "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _coerce_mode(mode: str | None) -> str:
    normalized = (mode or "conservative").strip().lower()
    if normalized != "conservative":
        return "conservative"
    return normalized


def _process_paragraph(paragraph: str) -> tuple[str, int, int, bool]:
    text = (paragraph or "").strip()
    if not text:
        return "", 0, 0, False

    pair_count = len(_PINYIN_PAIR_RE.findall(text))
    if pair_count <= 0:
        return text, 0, 0, False

    chinese_count = len(_CHINESE_CHAR_RE.findall(text))
    ratio = pair_count / max(1, chinese_count)
    should_clean = pair_count >= 6 or ratio >= 0.35
    if not should_clean:
        return text, pair_count, 0, False

    replaced_text, replaced_count = _PINYIN_PAIR_RE.subn(r"\1", text)
    return replaced_text, pair_count, replaced_count, True


def _visible_len(text: str) -> int:
    return len("".join(ch for ch in (text or "") if not ch.isspace()))


def _merge_short_lines(text: str) -> tuple[str, int]:
    lines = (text or "").split("\n")
    output: list[str] = []
    short_run: list[str] = []
    merged_groups = 0

    def flush_short_run() -> None:
        nonlocal merged_groups
        if not short_run:
            return
        if len(short_run) >= 2:
            output.append("".join(short_run))
            merged_groups += 1
        else:
            output.append(short_run[0])
        short_run.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if short_run:
                # Keep short run continuous even when OCR/extractor inserts blank lines.
                continue
            if output and output[-1] != "":
                output.append("")
            continue

        if _visible_len(line) <= 2:
            short_run.append(line)
            continue

        flush_short_run()
        output.append(line)

    flush_short_run()
    return "\n".join(output), merged_groups


def _normalize_chinese_context_ascii_punct(text: str) -> str:
    normalized = str(text or "")
    punct_map = {
        ",": "，",
        ".": "。",
        ";": "；",
        ":": "：",
        "!": "！",
        "?": "？",
    }
    for ascii_punct, zh_punct in punct_map.items():
        normalized = re.sub(
            rf"(?<=[\u4e00-\u9fff]){re.escape(ascii_punct)}(?=$|[\s”’」』】）)])",
            zh_punct,
            normalized,
        )
    return normalized


def clean_text_for_indexing_with_stats(
    text: str,
    *,
    mode: str = "conservative",
) -> tuple[str, dict[str, Any]]:
    resolved_mode = _coerce_mode(mode)
    normalized = _normalize_text(text)

    stats: dict[str, Any] = {
        "mode": resolved_mode,
        "before_len": len(normalized),
        "after_len": 0,
        "paragraphs_processed": 0,
        "paragraphs_cleaned": 0,
        "pairs_detected": 0,
        "pairs_removed": 0,
        "noise_lines_removed": 0,
        "latin_noise_lines_removed": 0,
        "short_line_groups_merged": 0,
        "common_normalizations_applied": 0,
        "header_footer_lines_removed": 0,
    }
    if not normalized:
        return "", stats

    paragraphs = re.split(r"\n{2,}", normalized)
    cleaned_paragraphs: list[str] = []
    for paragraph in paragraphs:
        para = paragraph.strip()
        if not para:
            continue
        cleaned, detected, replaced, paragraph_cleaned = _process_paragraph(para)
        stats["paragraphs_processed"] += 1
        stats["pairs_detected"] += detected
        stats["pairs_removed"] += replaced
        if paragraph_cleaned:
            stats["paragraphs_cleaned"] += 1
        cleaned_paragraphs.append(cleaned)

    joined = "\n\n".join(cleaned_paragraphs)
    finalized, extra_stats = clean_fragment_with_stats(
        joined,
        mode="balanced",
        format_hint=".pdf",
        enable_pinyin_cleanup=False,
    )
    merged_short, short_groups = _merge_short_lines(finalized)
    finalized = _normalize_text(merged_short)
    finalized = _normalize_chinese_context_ascii_punct(finalized)
    latin_removed = int(extra_stats.get("latin_noise_lines_removed", 0) or 0)
    merged_groups = int(extra_stats.get("line_merges_applied", 0) or 0) + short_groups
    common_norms = int(extra_stats.get("common_normalizations_applied", 0) or 0)

    stats["noise_lines_removed"] = latin_removed
    stats["latin_noise_lines_removed"] = latin_removed
    stats["short_line_groups_merged"] = merged_groups
    stats["common_normalizations_applied"] = common_norms
    stats["after_len"] = len(finalized)
    return finalized, stats


def clean_text_for_indexing(text: str, *, mode: str = "conservative") -> str:
    cleaned, _ = clean_text_for_indexing_with_stats(text, mode=mode)
    return cleaned
