#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.services.lexical_analyzer import tokenize_for_index  # noqa: E402


@dataclass
class BackfillStats:
    files_scanned: int = 0
    files_updated: int = 0
    entries_scanned: int = 0
    entries_updated: int = 0
    entries_skipped: int = 0
    parse_errors: int = 0


def _is_valid_token_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(token, str) for token in value)


def _iter_lexical_files(*, user_id: str | None, kb_id: str | None) -> list[tuple[str, str, Path]]:
    users_root = Path(settings.data_dir) / "users"
    if not users_root.exists():
        return []

    results: list[tuple[str, str, Path]] = []
    for user_dir in users_root.iterdir():
        if not user_dir.is_dir():
            continue
        resolved_user_id = user_dir.name
        if user_id and resolved_user_id != user_id:
            continue
        lexical_dir = user_dir / "lexical"
        if not lexical_dir.exists() or not lexical_dir.is_dir():
            continue
        for path in lexical_dir.glob("*.jsonl"):
            resolved_kb_id = path.stem
            if kb_id and resolved_kb_id != kb_id:
                continue
            results.append((resolved_user_id, resolved_kb_id, path))
    return sorted(results, key=lambda item: (item[0], item[1]))


def _backfill_file(
    *,
    user_id: str,
    kb_id: str,
    path: Path,
    execute: bool,
    stats: BackfillStats,
) -> None:
    stats.files_scanned += 1
    current_version = str(getattr(settings, "lexical_tokenizer_version", "v2") or "v2")

    changed = False
    output_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            stats.parse_errors += 1
            output_lines.append(stripped)
            continue

        if not isinstance(payload, dict):
            stats.parse_errors += 1
            output_lines.append(stripped)
            continue

        stats.entries_scanned += 1
        tokens = payload.get("tokens")
        tokenizer_version = str(payload.get("tokenizer_version") or "")
        if _is_valid_token_list(tokens) and tokenizer_version == current_version:
            stats.entries_skipped += 1
            output_lines.append(json.dumps(payload, ensure_ascii=False))
            continue

        text = str(payload.get("text", "") or "")
        payload["tokens"] = tokenize_for_index(text, user_id=user_id, kb_id=kb_id)
        payload["tokenizer_version"] = current_version
        stats.entries_updated += 1
        changed = True
        output_lines.append(json.dumps(payload, ensure_ascii=False))

    if changed:
        stats.files_updated += 1
        if execute:
            path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def backfill_lexical_tokens(
    *,
    user_id: str | None,
    kb_id: str | None,
    execute: bool,
) -> BackfillStats:
    stats = BackfillStats()
    files = _iter_lexical_files(user_id=user_id, kb_id=kb_id)
    for resolved_user_id, resolved_kb_id, path in files:
        _backfill_file(
            user_id=resolved_user_id,
            kb_id=resolved_kb_id,
            path=path,
            execute=execute,
            stats=stats,
        )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill lexical jsonl entries with tokens/tokenizer_version."
    )
    parser.add_argument("--user-id", default=None, help="Only process one user_id.")
    parser.add_argument("--kb-id", default=None, help="Only process one kb_id.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write updates to files. Without this flag, runs in dry-run mode.",
    )
    args = parser.parse_args()

    stats = backfill_lexical_tokens(
        user_id=(str(args.user_id).strip() or None) if args.user_id is not None else None,
        kb_id=(str(args.kb_id).strip() or None) if args.kb_id is not None else None,
        execute=bool(args.execute),
    )
    print(json.dumps(asdict(stats), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

