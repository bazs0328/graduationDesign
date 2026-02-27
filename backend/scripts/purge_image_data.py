#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import ChatMessage, Quiz  # noqa: E402


@dataclass
class PurgeStats:
    users_scanned: int = 0
    image_dirs_found: int = 0
    image_dirs_deleted: int = 0
    image_files_found: int = 0

    layout_files_scanned: int = 0
    layout_files_updated: int = 0
    layout_image_blocks_removed: int = 0
    layout_manifest_rows_removed: int = 0
    layout_block_fields_removed: int = 0

    quiz_rows_scanned: int = 0
    quiz_rows_updated: int = 0
    quiz_questions_scanned: int = 0
    quiz_image_fields_removed: int = 0

    chat_rows_scanned: int = 0
    chat_rows_updated: int = 0
    chat_source_items_scanned: int = 0
    chat_fields_removed: int = 0

    chroma_collections_found: int = 0
    chroma_collections_deleted: int = 0

    errors: int = 0


def _safe_load_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return None


def _prune_layout_payload(payload: dict[str, Any], stats: PurgeStats) -> bool:
    changed = False
    pages = payload.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            ordered_blocks = page.get("ordered_blocks")
            if not isinstance(ordered_blocks, list):
                continue
            new_blocks: list[Any] = []
            for block in ordered_blocks:
                if not isinstance(block, dict):
                    new_blocks.append(block)
                    continue
                if str(block.get("kind") or "").strip().lower() == "image":
                    stats.layout_image_blocks_removed += 1
                    changed = True
                    continue
                removed = 0
                for key in ("asset_path", "caption", "caption_text", "nearby_text", "ocr_text"):
                    if key in block:
                        block.pop(key, None)
                        removed += 1
                if removed:
                    stats.layout_block_fields_removed += removed
                    changed = True
                new_blocks.append(block)
            if len(new_blocks) != len(ordered_blocks):
                page["ordered_blocks"] = new_blocks

            # Drop legacy convenience arrays if present.
            if "image_blocks" in page:
                page.pop("image_blocks", None)
                changed = True

    manifest = payload.get("chunk_manifest")
    if isinstance(manifest, list):
        new_manifest: list[Any] = []
        for item in manifest:
            if not isinstance(item, dict):
                new_manifest.append(item)
                continue
            modality = str(item.get("modality") or "").strip().lower()
            chunk_kind = str(item.get("chunk_kind") or "").strip().lower()
            if modality == "image" or chunk_kind == "image":
                stats.layout_manifest_rows_removed += 1
                changed = True
                continue
            new_manifest.append(item)
        if len(new_manifest) != len(manifest):
            payload["chunk_manifest"] = new_manifest
    return changed


def _prune_quiz_questions(raw: str, stats: PurgeStats) -> tuple[str | None, bool]:
    data = _safe_load_json(raw)
    if data is None:
        return None, False

    changed = False
    if isinstance(data, dict):
        questions = data.get("questions")
        if isinstance(questions, list):
            target = questions
        else:
            return None, False
    elif isinstance(data, list):
        target = data
    else:
        return None, False

    for item in target:
        if not isinstance(item, dict):
            continue
        stats.quiz_questions_scanned += 1
        if "image" in item:
            item.pop("image", None)
            stats.quiz_image_fields_removed += 1
            changed = True

    if not changed:
        return None, False
    return json.dumps(data, ensure_ascii=False), True


def _prune_chat_sources(raw: str, stats: PurgeStats) -> tuple[str | None, bool]:
    data = _safe_load_json(raw)
    if not isinstance(data, list):
        return None, False

    changed = False
    for item in data:
        if not isinstance(item, dict):
            continue
        stats.chat_source_items_scanned += 1
        removed = 0
        for key in ("asset_path", "caption", "bbox", "modality", "block_id"):
            if key in item:
                item.pop(key, None)
                removed += 1
        if removed:
            stats.chat_fields_removed += removed
            changed = True

    if not changed:
        return None, False
    return json.dumps(data, ensure_ascii=False), True


def _purge_image_dirs(users_root: Path, *, execute: bool, stats: PurgeStats) -> None:
    if not users_root.exists():
        return
    for user_dir in users_root.iterdir():
        if not user_dir.is_dir():
            continue
        stats.users_scanned += 1
        kb_root = user_dir / "kb"
        if not kb_root.exists():
            continue
        for kb_dir in kb_root.iterdir():
            images_dir = kb_dir / "images"
            if not images_dir.exists() or not images_dir.is_dir():
                continue
            stats.image_dirs_found += 1
            stats.image_files_found += sum(1 for p in images_dir.rglob("*") if p.is_file())
            if execute:
                shutil.rmtree(images_dir, ignore_errors=True)
                stats.image_dirs_deleted += 1


def _purge_layout_files(users_root: Path, *, execute: bool, stats: PurgeStats) -> None:
    if not users_root.exists():
        return
    for path in users_root.glob("*/kb/*/content_list/*.layout.json"):
        stats.layout_files_scanned += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            stats.errors += 1
            continue
        if not isinstance(payload, dict):
            continue
        changed = _prune_layout_payload(payload, stats)
        if changed:
            stats.layout_files_updated += 1
            if execute:
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _purge_db_rows(*, execute: bool, stats: PurgeStats) -> None:
    db = SessionLocal()
    try:
        quizzes = db.query(Quiz).all()
        for row in quizzes:
            stats.quiz_rows_scanned += 1
            if not row.questions_json:
                continue
            new_json, changed = _prune_quiz_questions(str(row.questions_json), stats)
            if not changed or new_json is None:
                continue
            stats.quiz_rows_updated += 1
            if execute:
                row.questions_json = new_json

        chat_rows = db.query(ChatMessage).filter(ChatMessage.sources_json.isnot(None)).all()
        for row in chat_rows:
            stats.chat_rows_scanned += 1
            raw = row.sources_json
            if not raw:
                continue
            new_json, changed = _prune_chat_sources(str(raw), stats)
            if not changed or new_json is None:
                continue
            stats.chat_rows_updated += 1
            if execute:
                row.sources_json = new_json

        if execute:
            db.commit()
        else:
            db.rollback()
    except Exception:
        stats.errors += 1
        db.rollback()
    finally:
        db.close()


def _purge_image_collections(users_root: Path, *, execute: bool, stats: PurgeStats) -> None:
    try:
        import chromadb  # type: ignore
    except Exception:
        return

    if not users_root.exists():
        return
    for user_dir in users_root.iterdir():
        if not user_dir.is_dir():
            continue
        chroma_dir = user_dir / "chroma"
        if not chroma_dir.exists():
            continue
        try:
            client = chromadb.PersistentClient(path=str(chroma_dir))
            names = {collection.name for collection in client.list_collections()}
        except Exception:
            stats.errors += 1
            continue
        if "documents_images" not in names:
            continue
        stats.chroma_collections_found += 1
        if execute:
            try:
                client.delete_collection(name="documents_images")
                stats.chroma_collections_deleted += 1
            except Exception:
                stats.errors += 1


def _print_summary(*, execute: bool, stats: PurgeStats) -> None:
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"[purge_image_data] mode={mode}")
    print(f"users_scanned={stats.users_scanned}")
    print(f"image_dirs_found={stats.image_dirs_found}")
    print(f"image_dirs_deleted={stats.image_dirs_deleted}")
    print(f"image_files_found={stats.image_files_found}")
    print(f"layout_files_scanned={stats.layout_files_scanned}")
    print(f"layout_files_updated={stats.layout_files_updated}")
    print(f"layout_image_blocks_removed={stats.layout_image_blocks_removed}")
    print(f"layout_manifest_rows_removed={stats.layout_manifest_rows_removed}")
    print(f"layout_block_fields_removed={stats.layout_block_fields_removed}")
    print(f"quiz_rows_scanned={stats.quiz_rows_scanned}")
    print(f"quiz_rows_updated={stats.quiz_rows_updated}")
    print(f"quiz_questions_scanned={stats.quiz_questions_scanned}")
    print(f"quiz_image_fields_removed={stats.quiz_image_fields_removed}")
    print(f"chat_rows_scanned={stats.chat_rows_scanned}")
    print(f"chat_rows_updated={stats.chat_rows_updated}")
    print(f"chat_source_items_scanned={stats.chat_source_items_scanned}")
    print(f"chat_fields_removed={stats.chat_fields_removed}")
    print(f"chroma_collections_found={stats.chroma_collections_found}")
    print(f"chroma_collections_deleted={stats.chroma_collections_deleted}")
    print(f"errors={stats.errors}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge legacy image data from GradTutor storage.")
    parser.add_argument("--dry-run", action="store_true", help="Scan and report only (default mode).")
    parser.add_argument("--execute", action="store_true", help="Apply destructive cleanup operations.")
    args = parser.parse_args()

    if args.dry_run and args.execute:
        parser.error("--dry-run and --execute are mutually exclusive")

    execute = bool(args.execute)
    users_root = Path(settings.data_dir) / "users"
    stats = PurgeStats()

    _purge_image_dirs(users_root, execute=execute, stats=stats)
    _purge_layout_files(users_root, execute=execute, stats=stats)
    _purge_db_rows(execute=execute, stats=stats)
    _purge_image_collections(users_root, execute=execute, stats=stats)
    _print_summary(execute=execute, stats=stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
