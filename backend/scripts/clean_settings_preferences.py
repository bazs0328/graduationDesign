#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DATA_DIR", str(BACKEND_DIR / "data"))

from app.core.settings_preferences import normalize_settings_payload_for_read_with_change  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import KnowledgeBase, User  # noqa: E402
from app.schemas import KbSettingsPayload, UserSettingsPayload  # noqa: E402


@dataclass
class CleanupStats:
    users_scanned: int = 0
    users_dirty: int = 0
    users_invalid_json: int = 0
    users_updated: int = 0

    kbs_scanned: int = 0
    kbs_dirty: int = 0
    kbs_invalid_json: int = 0
    kbs_updated: int = 0


def _loads_json_object(raw: str | None) -> dict[str, Any] | None:
    if raw is None or not str(raw).strip():
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _dumps_json(payload: dict[str, Any]) -> str | None:
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _normalize_raw_payload(
    raw: str | None,
    model_cls: type[BaseModel],
) -> tuple[str | None, bool, bool]:
    parsed = _loads_json_object(raw)
    if parsed is None:
        return raw, False, True
    normalized, changed = normalize_settings_payload_for_read_with_change(parsed, model_cls)
    if not changed:
        return raw, False, False
    return _dumps_json(normalized), True, False


def _clean_user_preferences(db, args, stats: CleanupStats, *, execute: bool) -> None:
    query = db.query(User)
    if args.user_id:
        query = query.filter(User.id == args.user_id)
    for row in query.all():
        stats.users_scanned += 1
        if row.preferences_json is None:
            continue
        next_raw, is_dirty, invalid = _normalize_raw_payload(row.preferences_json, UserSettingsPayload)
        if invalid:
            stats.users_invalid_json += 1
            continue
        if not is_dirty:
            continue
        stats.users_dirty += 1
        if execute:
            row.preferences_json = next_raw
            stats.users_updated += 1


def _clean_kb_preferences(db, args, stats: CleanupStats, *, execute: bool) -> None:
    query = db.query(KnowledgeBase)
    if args.kb_id:
        query = query.filter(KnowledgeBase.id == args.kb_id)
    for row in query.all():
        stats.kbs_scanned += 1
        if row.preferences_json is None:
            continue
        next_raw, is_dirty, invalid = _normalize_raw_payload(row.preferences_json, KbSettingsPayload)
        if invalid:
            stats.kbs_invalid_json += 1
            continue
        if not is_dirty:
            continue
        stats.kbs_dirty += 1
        if execute:
            row.preferences_json = next_raw
            stats.kbs_updated += 1


def _print_summary(stats: CleanupStats, *, execute: bool) -> None:
    update_key = "updated" if execute else "would_update"
    user_update_value = stats.users_updated if execute else stats.users_dirty
    kb_update_value = stats.kbs_updated if execute else stats.kbs_dirty
    print(
        f"users: scanned={stats.users_scanned}, dirty={stats.users_dirty}, "
        f"invalid_json={stats.users_invalid_json}, {update_key}={user_update_value}"
    )
    print(
        f"knowledge_bases: scanned={stats.kbs_scanned}, dirty={stats.kbs_dirty}, "
        f"invalid_json={stats.kbs_invalid_json}, {update_key}={kb_update_value}"
    )


def _sqlite_has_column(db, table_name: str, column_name: str) -> bool:
    result = db.execute(text(f"PRAGMA table_info({table_name})"))
    cols = {row[1] for row in result}
    return column_name in cols


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Clean legacy extra keys in users/knowledge_bases preferences_json. "
            "Default mode is dry-run; pass --execute to persist changes."
        )
    )
    parser.add_argument("--execute", action="store_true", help="Persist cleaned preferences to the database.")
    parser.add_argument("--user-id", default=None, help="Only scan a specific user ID.")
    parser.add_argument("--kb-id", default=None, help="Only scan a specific knowledge base ID.")
    args = parser.parse_args()

    print(f"mode={'execute' if args.execute else 'dry-run'}")
    if args.user_id:
        print(f"filter user_id={args.user_id}")
    if args.kb_id:
        print(f"filter kb_id={args.kb_id}")

    stats = CleanupStats()
    db = SessionLocal()
    try:
        if not _sqlite_has_column(db, "users", "preferences_json"):
            print("error: users.preferences_json column not found; run backend schema migration first.")
            return 1
        if not _sqlite_has_column(db, "knowledge_bases", "preferences_json"):
            print("error: knowledge_bases.preferences_json column not found; run backend schema migration first.")
            return 1

        _clean_user_preferences(db, args, stats, execute=args.execute)
        _clean_kb_preferences(db, args, stats, execute=args.execute)
        if args.execute:
            try:
                db.commit()
            except Exception as exc:
                db.rollback()
                print(f"error: failed to commit cleaned preferences: {exc}")
                return 1
        else:
            db.rollback()
    finally:
        db.close()

    _print_summary(stats, execute=args.execute)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
