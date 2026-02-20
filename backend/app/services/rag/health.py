from __future__ import annotations

import logging
import shutil

from app.core.config import settings

logger = logging.getLogger(__name__)

_logged_once = False


def log_rag_boot_health(force: bool = False) -> None:
    global _logged_once
    if _logged_once and not force:
        return

    raganything_installed = False
    mineru_cli_available = bool(shutil.which("mineru"))
    mineru_parser_available = False
    error_reasons: list[str] = []

    if not settings.raganything_enabled:
        logger.info("RAG boot probe skipped: raganything is disabled by config")
        _logged_once = True
        return

    try:
        import raganything  # type: ignore  # noqa: F401

        raganything_installed = True
    except Exception as exc:  # noqa: BLE001
        error_reasons.append(f"raganything_import_error={str(exc)[:200]}")

    if raganything_installed:
        try:
            from raganything.parser import MineruParser  # type: ignore

            mineru_parser_available = bool(MineruParser().check_installation())
        except Exception as exc:  # noqa: BLE001
            error_reasons.append(f"mineru_parser_check_error={str(exc)[:200]}")

    payload = {
        "raganything_enabled": True,
        "raganything_installed": raganything_installed,
        "mineru_cli_available": mineru_cli_available,
        "mineru_parser_available": mineru_parser_available,
    }
    if raganything_installed and mineru_cli_available and mineru_parser_available:
        logger.info("RAG boot probe: %s", payload)
    else:
        logger.warning(
            "RAG boot probe degraded: %s reasons=%s",
            payload,
            error_reasons or ["missing_runtime_dependency"],
        )
    _logged_once = True
