from __future__ import annotations

import os
import re
import unicodedata
from typing import Any


_CHINESE_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_PINYIN_PAIR_RE = re.compile(r"([\u4e00-\u9fff])([A-Za-z]{1,8})")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z]+")
_LATIN_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z .,_\-]{0,31}$")
_CODE_FENCE_RE = re.compile(r"^(```|~~~)")
_MARKDOWN_LIST_RE = re.compile(r"^(\*|-|\+|\d+\.)\s+")
_MARKDOWN_HEADER_RE = re.compile(r"^#{1,6}\s+")
_URL_RE = re.compile(r"(https?://|www\.)", re.I)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\u2060\ufeff]")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PAGE_NUMBER_LINE_RE = re.compile(r"^(第?\s*\d{1,4}\s*页?|[0-9]{1,4})$")

_SAFE_LATIN_TERMS = {
    "ai",
    "api",
    "app",
    "cpu",
    "css",
    "dna",
    "html",
    "http",
    "https",
    "id",
    "ip",
    "js",
    "json",
    "pdf",
    "ppt",
    "pptx",
    "python",
    "sdk",
    "sql",
    "tcp",
    "txt",
    "ui",
    "url",
    "utf",
    "wifi",
    "xml",
}

_ASCII_TO_ZH_PUNCT = {
    ",": "，",
    ".": "。",
    ";": "；",
    ":": "：",
    "!": "！",
    "?": "？",
}

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


def _normalize_text(text: str, *, apply_nfkc: bool = True) -> str:
    normalized = str(text or "")
    if apply_nfkc:
        normalized = unicodedata.normalize("NFKC", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u3000", " ").replace("\u00a0", " ")
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = _CONTROL_CHAR_RE.sub("", normalized)
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _visible_chars(text: str) -> str:
    return "".join(ch for ch in (text or "") if not ch.isspace())


def _contains_chinese(text: str) -> bool:
    return bool(_CHINESE_CHAR_RE.search(text or ""))


def _is_safe_latin_token(token: str) -> bool:
    token = str(token or "")
    if not token:
        return False
    lower = token.lower()
    if lower in _SAFE_LATIN_TERMS:
        return True
    if token.isupper() and 1 <= len(token) <= 6:
        return True
    return token in {"WiFi", "iOS", "macOS", "OpenAI"}


def _longest_consonant_run(token: str) -> int:
    max_run = 0
    cur = 0
    for ch in str(token or "").lower():
        if "a" <= ch <= "z" and ch not in {"a", "e", "i", "o", "u"}:
            cur += 1
            max_run = max(max_run, cur)
        else:
            cur = 0
    return max_run


def _neighbor_has_chinese(lines: list[str], idx: int) -> bool:
    left_has_ch = False
    right_has_ch = False
    for j in range(idx - 1, -1, -1):
        candidate = lines[j].strip()
        if not candidate:
            continue
        left_has_ch = _contains_chinese(candidate)
        break
    for j in range(idx + 1, len(lines)):
        candidate = lines[j].strip()
        if not candidate:
            continue
        right_has_ch = _contains_chinese(candidate)
        break
    return left_has_ch or right_has_ch


def _looks_like_short_latin_noise_line(
    line: str,
    *,
    neighbor_has_chinese: bool = False,
    single_line_input: bool = False,
) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if single_line_input:
        return False
    if _contains_chinese(stripped):
        return False
    if _URL_RE.search(stripped) or _EMAIL_RE.search(stripped):
        return False
    if _PAGE_NUMBER_LINE_RE.fullmatch(stripped):
        return False
    if len(stripped) > 32:
        return False
    if not _LATIN_LINE_RE.fullmatch(stripped):
        return False

    tokens = _LATIN_TOKEN_RE.findall(stripped)
    if not tokens:
        return False
    if all(_is_safe_latin_token(token) for token in tokens):
        return False

    dotted_or_joined = bool(re.search(r"[A-Za-z][._-][A-Za-z]", stripped))
    if dotted_or_joined and len(stripped) <= 18 and " " not in stripped:
        if any(not _is_safe_latin_token(token) and len(token) <= 6 for token in tokens):
            return True

    if len(tokens) >= 2:
        if (
            len(tokens) <= 3
            and any(len(token) <= 2 and not token.isupper() for token in tokens)
            and neighbor_has_chinese
            and len(stripped) <= 14
        ):
            return True
        if len(tokens) <= 3 and all(len(token) <= 4 for token in tokens) and not any(
            _is_safe_latin_token(token) for token in tokens
        ):
            return True
        return False

    token = tokens[0]
    if _is_safe_latin_token(token):
        return False
    if (
        any(ch.islower() for ch in token)
        and any(ch.isupper() for ch in token)
        and len(token) <= 8
    ):
        return True
    if len(token) <= 3:
        return True
    if dotted_or_joined and len(token) <= 14:
        return neighbor_has_chinese or len(stripped) <= 10
    if token.islower() and len(token) >= 9 and neighbor_has_chinese:
        return True
    if token.islower() and neighbor_has_chinese and _longest_consonant_run(token) >= 4:
        return True
    return False


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


def _normalize_inline_spacing(line: str) -> str:
    normalized = re.sub(r"[ \t]{2,}", " ", line.strip())
    normalized = re.sub(r"\s+([，。！？；：,.;!?])", r"\1", normalized)
    return normalized


def _clean_plain_lines(lines: list[str], *, preserve_structure: bool) -> tuple[list[str], int]:
    non_empty_count = sum(1 for line in lines if line.strip())
    single_line_input = non_empty_count <= 1
    out: list[str] = []
    removed_latin_noise_lines = 0

    for idx, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped:
            if out and out[-1] != "":
                out.append("")
            continue

        if preserve_structure and _is_markdown_structural_line(stripped):
            out.append(raw_line.rstrip())
            continue

        normalized_line = _normalize_inline_spacing(stripped)
        neighbor_has_chinese = _neighbor_has_chinese(lines, idx)
        if _looks_like_short_latin_noise_line(
            normalized_line,
            neighbor_has_chinese=neighbor_has_chinese,
            single_line_input=single_line_input,
        ):
            removed_latin_noise_lines += 1
            continue
        out.append(normalized_line)
    return out, removed_latin_noise_lines


def _clean_markdown_lines(lines: list[str]) -> tuple[list[str], int]:
    output: list[str] = []
    pending_plain: list[str] = []
    in_code_block = False
    removed_latin_noise_lines = 0

    def _flush_pending_plain() -> None:
        nonlocal removed_latin_noise_lines
        if not pending_plain:
            return
        cleaned, removed = _clean_plain_lines(pending_plain, preserve_structure=True)
        output.extend(cleaned)
        removed_latin_noise_lines += removed
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
    return output, removed_latin_noise_lines


def _join_lines(left: str, right: str) -> str:
    if re.search(r"[A-Za-z]-$", left) and re.match(r"^[A-Za-z]{2,}", right):
        return f"{left[:-1]}{right}"
    left_has_ch = _contains_chinese(left)
    right_has_ch = _contains_chinese(right)
    if left_has_ch and right_has_ch:
        return f"{left}{right}"
    return f"{left} {right}".strip()


def _can_merge_lines(left: str, right: str, *, preserve_structure: bool) -> bool:
    if not left or not right:
        return False
    if preserve_structure:
        if _is_markdown_structural_line(left) or _is_markdown_structural_line(right):
            return False
        if _CODE_FENCE_RE.match(left.strip()) or _CODE_FENCE_RE.match(right.strip()):
            return False
    if _URL_RE.search(left) or _URL_RE.search(right) or _EMAIL_RE.search(left) or _EMAIL_RE.search(right):
        return False
    if re.search(r"[。！？；.!?;:：]$", left):
        return False
    if _MARKDOWN_LIST_RE.match(right):
        return False
    if re.search(r"[A-Za-z]-$", left) and re.match(r"^[A-Za-z]{2,}", right):
        return True
    if re.search(r"[，、,:;：；]$", left):
        return True
    left_len = len(_visible_chars(left))
    right_len = len(_visible_chars(right))
    if (
        not _contains_chinese(left)
        and not _contains_chinese(right)
        and left_len <= 26
        and right_len <= 18
        and left[-1].isalnum()
        and right[0].islower()
    ):
        return True
    return False


def _merge_broken_lines(lines: list[str], *, preserve_structure: bool) -> tuple[list[str], int]:
    out: list[str] = []
    merged = 0
    for raw_line in lines:
        line = (raw_line or "").strip()
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        if not out or out[-1] == "":
            out.append(line)
            continue
        prev = out[-1]
        if _can_merge_lines(prev, line, preserve_structure=preserve_structure):
            out[-1] = _join_lines(prev, line)
            merged += 1
        else:
            out.append(line)
    return out, merged


def _normalize_chinese_punctuation(line: str) -> tuple[str, int]:
    if not line:
        return "", 0
    if _URL_RE.search(line) or _EMAIL_RE.search(line):
        return line, 0
    changed = 0
    normalized = re.sub(r"\s+([，。！？；：,.;!?])", r"\1", line)
    if normalized != line:
        changed += 1
    line = normalized

    def _replace_ascii_punct(match: re.Match[str]) -> str:
        punct = match.group("punct")
        return _ASCII_TO_ZH_PUNCT.get(punct, punct)

    normalized, count = re.subn(
        r"(?P<left>[\u4e00-\u9fff])\s*(?P<punct>[,.;:!?])\s*(?P<right>[\u4e00-\u9fff])",
        lambda m: f"{m.group('left')}{_replace_ascii_punct(m)}{m.group('right')}",
        line,
    )
    if count:
        changed += count
    line = normalized

    normalized, count = re.subn(
        r"(?P<left>[\u4e00-\u9fff])\s*(?P<punct>[,.;:!?])(?=$|[\s”’」』】）)])",
        lambda m: f"{m.group('left')}{_replace_ascii_punct(m)}",
        line,
    )
    if count:
        changed += count
    line = normalized

    normalized, count = re.subn(r"([，。！？；：]){2,}", r"\1", line)
    if count:
        changed += count
    return normalized, changed


def _apply_chinese_punctuation(lines: list[str], *, preserve_structure: bool) -> tuple[list[str], int]:
    if preserve_structure:
        return lines, 0
    out: list[str] = []
    changed = 0
    for line in lines:
        normalized, c = _normalize_chinese_punctuation(line)
        out.append(normalized)
        changed += c
    return out, changed


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


def clean_fragment_with_stats(
    text: str,
    *,
    mode: str | None = _MODE_BALANCED,
    format_hint: str | None = None,
    enable_pinyin_cleanup: bool = True,
) -> tuple[str, dict[str, Any]]:
    resolved_mode = _normalize_mode(mode)
    resolved_format = infer_format_hint(format_hint)
    preserve_structure = (
        resolved_mode == _MODE_STRUCTURE_PRESERVING or resolved_format == ".md"
    )

    normalized = str(text or "")
    stats: dict[str, Any] = {
        "mode": resolved_mode,
        "format_hint": resolved_format,
        "common_normalizations_applied": 0,
        "latin_noise_lines_removed": 0,
        "line_merges_applied": 0,
        "pinyin_pairs_removed": 0,
        "pinyin_pairs_detected": 0,
    }
    if not normalized:
        return "", stats

    before_basic = normalized
    normalized = _normalize_text(normalized, apply_nfkc=True)
    if normalized != before_basic.strip():
        stats["common_normalizations_applied"] += 1
    if not normalized:
        return "", stats

    lines = normalized.split("\n")
    if preserve_structure:
        cleaned_lines, removed_latin_noise = _clean_markdown_lines(lines)
    else:
        cleaned_lines, removed_latin_noise = _clean_plain_lines(lines, preserve_structure=False)
    stats["latin_noise_lines_removed"] = removed_latin_noise

    merged_lines, merge_count = _merge_broken_lines(cleaned_lines, preserve_structure=preserve_structure)
    stats["line_merges_applied"] = merge_count
    if merge_count:
        stats["common_normalizations_applied"] += merge_count

    punct_lines, punct_changes = _apply_chinese_punctuation(
        merged_lines,
        preserve_structure=preserve_structure,
    )
    if punct_changes:
        stats["common_normalizations_applied"] += punct_changes

    joined = _normalize_text("\n".join(punct_lines), apply_nfkc=False)
    if not joined:
        return "", stats

    if enable_pinyin_cleanup:
        pair_count = len(_PINYIN_PAIR_RE.findall(joined))
        stats["pinyin_pairs_detected"] = pair_count
        force_pinyin_cleanup = resolved_mode == _MODE_AGGRESSIVE or resolved_format == ".pdf"
        if not force_pinyin_cleanup and resolved_format not in {".md"}:
            pre_metrics = score_text_fragment(joined, mode=resolved_mode, format_hint=resolved_format)
            force_pinyin_cleanup = float(pre_metrics.get("score", 0.0)) < 0.16
        joined, pair_removed = _remove_pinyin_noise(joined, force=force_pinyin_cleanup)
        stats["pinyin_pairs_removed"] = pair_removed

    return _normalize_text(joined, apply_nfkc=False), stats


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
    noise_flags = [
        _looks_like_short_latin_noise_line(
            line,
            neighbor_has_chinese=_neighbor_has_chinese(lines, idx),
            single_line_input=(len(lines) <= 1),
        )
        for idx, line in enumerate(lines)
    ]
    avg_line_len = sum(line_lengths) / max(1, len(line_lengths))
    single_char_line_ratio = sum(1 for n in line_lengths if n <= 1) / max(1, len(line_lengths))
    short_line_ratio = sum(1 for n in line_lengths if n <= 4) / max(1, len(line_lengths))
    noise_line_ratio = sum(1 for flag in noise_flags if flag) / max(1, len(lines))
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
    enable_pinyin_cleanup: bool = True,
) -> str:
    cleaned, _ = clean_fragment_with_stats(
        text,
        mode=mode,
        format_hint=format_hint,
        enable_pinyin_cleanup=enable_pinyin_cleanup,
    )
    return cleaned
