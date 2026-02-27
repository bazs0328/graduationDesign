from __future__ import annotations

import os
import re
from typing import Any


_CHINESE_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_PINYIN_PAIR_RE = re.compile(r"([\u4e00-\u9fff])([A-Za-z]{1,8})")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z]+")
_LATIN_LINE_RE = re.compile(r"^[A-Za-z ]+$")
_CODE_FENCE_RE = re.compile(r"^(```|~~~)")
_MARKDOWN_LIST_RE = re.compile(r"^(\*|-|\+|\d+\.)\s+")
_MARKDOWN_HEADER_RE = re.compile(r"^#{1,6}\s+")

_MODE_BALANCED = "balanced"
_MODE_CONSERVATIVE = "conservative"
_MODE_AGGRESSIVE = "aggressive"
_MODE_STRUCTURE_PRESERVING = "structure_preserving"


def infer_format_hint(source: str | None, *, default: str | None = None) -> str | None:
    candidate = (source or "").strip()
    if candidate:
        _, ext = os.path.splitext(candidate)
        if ext:
            return ext.lower()
        if candidate.startswith("."):
            return candidate.lower()
    if default:
        return default.lower()
    return None


def _normalize_mode(mode: str | None) -> str:
    normalized = (mode or _MODE_BALANCED).strip().lower()
    if normalized in {
        _MODE_BALANCED,
        _MODE_CONSERVATIVE,
        _MODE_AGGRESSIVE,
        _MODE_STRUCTURE_PRESERVING,
    }:
        return normalized
    return _MODE_BALANCED


def _normalize_text(text: str) -> str:
    normalized = (text or "").replace("\x00", "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _visible_chars(text: str) -> str:
    return "".join(ch for ch in (text or "") if not ch.isspace())


def _looks_like_short_latin_noise_line(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if _CHINESE_CHAR_RE.search(stripped):
        return False
    if len(stripped) > 24:
        return False
    if not _LATIN_LINE_RE.fullmatch(stripped):
        return False
    tokens = _LATIN_TOKEN_RE.findall(stripped)
    if not tokens:
        return False
    if any(len(token) > 8 for token in tokens):
        return False
    return True


def _is_markdown_structural_line(stripped: str) -> bool:
    if not stripped:
        return False
    if _MARKDOWN_HEADER_RE.match(stripped):
        return True
    if _MARKDOWN_LIST_RE.match(stripped):
        return True
    if stripped.startswith(">"):
        return True
    return False


def _clean_plain_lines(lines: list[str], *, preserve_structure: bool) -> list[str]:
    non_empty_count = sum(1 for line in lines if line.strip())
    single_line_input = non_empty_count <= 1
    out: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            if out and out[-1] != "":
                out.append("")
            continue

        if preserve_structure and _is_markdown_structural_line(stripped):
            out.append(raw_line.rstrip())
            continue

        if _looks_like_short_latin_noise_line(stripped) and not single_line_input:
            continue
        out.append(stripped)
    return out


def _clean_markdown_lines(lines: list[str]) -> list[str]:
    output: list[str] = []
    pending_plain: list[str] = []
    in_code_block = False

    def _flush_pending_plain() -> None:
        if not pending_plain:
            return
        output.extend(_clean_plain_lines(pending_plain, preserve_structure=True))
        pending_plain.clear()

    for raw_line in lines:
        stripped = raw_line.strip()
        if _CODE_FENCE_RE.match(stripped):
            _flush_pending_plain()
            in_code_block = not in_code_block
            output.append(raw_line.rstrip())
            continue
        if in_code_block:
            output.append(raw_line.rstrip())
            continue
        pending_plain.append(raw_line)

    _flush_pending_plain()
    return output


def _remove_pinyin_noise(text: str, *, force: bool) -> tuple[str, int]:
    normalized = (text or "").strip()
    if not normalized:
        return "", 0
    pair_count = len(_PINYIN_PAIR_RE.findall(normalized))
    if pair_count <= 0:
        return normalized, 0

    chinese_count = len(_CHINESE_CHAR_RE.findall(normalized))
    ratio = pair_count / max(1, chinese_count)
    should_clean = force or pair_count >= 6 or ratio >= 0.35
    if not should_clean:
        return normalized, 0
    replaced_text, replaced_count = _PINYIN_PAIR_RE.subn(r"\1", normalized)
    return replaced_text, replaced_count


def score_text_fragment(
    text: str,
    *,
    mode: str | None = _MODE_BALANCED,
    format_hint: str | None = None,
) -> dict[str, Any]:
    resolved_mode = _normalize_mode(mode)
    resolved_format = infer_format_hint(format_hint)
    normalized = _normalize_text(text)
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    visible = _visible_chars(normalized)
    visible_len = len(visible)
    if not lines or visible_len <= 0:
        return {
            "mode": resolved_mode,
            "format_hint": resolved_format,
            "score": 0.0,
            "visible_len": float(visible_len),
            "line_count": float(len(lines)),
            "avg_line_len": 0.0,
            "single_char_line_ratio": 1.0 if lines else 0.0,
            "short_line_ratio": 1.0 if lines else 0.0,
            "noise_line_ratio": 1.0 if lines else 0.0,
            "line_break_ratio": 1.0 if visible_len else 0.0,
            "latin_ratio": 0.0,
        }

    line_lengths = [len(_visible_chars(line)) for line in lines]
    avg_line_len = sum(line_lengths) / max(1, len(line_lengths))
    single_char_line_ratio = sum(1 for n in line_lengths if n <= 1) / max(1, len(line_lengths))
    short_line_ratio = sum(1 for n in line_lengths if n <= 4) / max(1, len(line_lengths))
    noise_line_ratio = sum(1 for line in lines if _looks_like_short_latin_noise_line(line)) / max(1, len(lines))
    line_break_ratio = normalized.count("\n") / max(1, visible_len)
    latin_ratio = sum(1 for ch in visible if ("a" <= ch.lower() <= "z")) / max(1, visible_len)

    score = 0.35
    score += min(0.28, visible_len / 1400.0)
    score += min(0.18, avg_line_len / 36.0)
    score -= single_char_line_ratio * 0.35
    score -= short_line_ratio * 0.22
    score -= noise_line_ratio * 0.45
    score -= min(0.15, line_break_ratio * 4.0)

    if visible_len <= 3:
        score -= 0.32
    elif visible_len <= 8:
        score -= 0.18

    if resolved_format == ".md":
        markdown_structural = sum(1 for line in lines if _is_markdown_structural_line(line))
        if markdown_structural:
            structure_ratio = markdown_structural / max(1, len(lines))
            score += min(0.12, structure_ratio * 0.2)

    if resolved_mode == _MODE_CONSERVATIVE:
        score += 0.05
    elif resolved_mode == _MODE_AGGRESSIVE:
        score -= 0.05

    return {
        "mode": resolved_mode,
        "format_hint": resolved_format,
        "score": max(0.0, min(1.0, score)),
        "visible_len": float(visible_len),
        "line_count": float(len(lines)),
        "avg_line_len": float(avg_line_len),
        "single_char_line_ratio": single_char_line_ratio,
        "short_line_ratio": short_line_ratio,
        "noise_line_ratio": noise_line_ratio,
        "line_break_ratio": line_break_ratio,
        "latin_ratio": latin_ratio,
    }


def is_low_quality(
    text: str,
    *,
    mode: str | None = _MODE_BALANCED,
    format_hint: str | None = None,
) -> bool:
    metrics = score_text_fragment(text, mode=mode, format_hint=format_hint)
    score = float(metrics.get("score", 0.0))
    visible_len = float(metrics.get("visible_len", 0.0))
    line_count = int(metrics.get("line_count", 0.0))
    single_char_ratio = float(metrics.get("single_char_line_ratio", 0.0))
    short_line_ratio = float(metrics.get("short_line_ratio", 0.0))
    noise_line_ratio = float(metrics.get("noise_line_ratio", 0.0))
    avg_line_len = float(metrics.get("avg_line_len", 0.0))
    resolved_mode = _normalize_mode(mode)

    if visible_len <= 0:
        return True
    if visible_len <= 3 and line_count >= 1:
        return True
    if single_char_ratio >= 0.48 and line_count >= 3:
        return True
    if short_line_ratio >= 0.8 and avg_line_len < 6 and line_count >= 3:
        return True
    if noise_line_ratio >= 0.5 and line_count >= 2:
        return True

    threshold = 0.18
    if resolved_mode == _MODE_CONSERVATIVE:
        threshold = 0.12
    elif resolved_mode == _MODE_AGGRESSIVE:
        threshold = 0.24
    elif resolved_mode == _MODE_STRUCTURE_PRESERVING:
        threshold = 0.2
    return score < threshold


def clean_fragment(
    text: str,
    *,
    mode: str | None = _MODE_BALANCED,
    format_hint: str | None = None,
) -> str:
    resolved_mode = _normalize_mode(mode)
    resolved_format = infer_format_hint(format_hint)
    normalized = _normalize_text(text)
    if not normalized:
        return ""

    lines = normalized.split("\n")
    if resolved_mode == _MODE_STRUCTURE_PRESERVING or resolved_format == ".md":
        cleaned_lines = _clean_markdown_lines(lines)
    else:
        cleaned_lines = _clean_plain_lines(lines, preserve_structure=False)

    joined = "\n".join(cleaned_lines)
    joined = _normalize_text(joined)
    if not joined:
        return ""

    force_pinyin_cleanup = resolved_mode == _MODE_AGGRESSIVE or resolved_format == ".pdf"
    if not force_pinyin_cleanup and resolved_format not in {".md"}:
        pre_metrics = score_text_fragment(joined, mode=resolved_mode, format_hint=resolved_format)
        force_pinyin_cleanup = float(pre_metrics.get("score", 0.0)) < 0.16
    joined, _ = _remove_pinyin_noise(joined, force=force_pinyin_cleanup)
    return _normalize_text(joined)
