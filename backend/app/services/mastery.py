"""Unified mastery service: EMA-based calculation, quiz & study interaction recording."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Keypoint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mastery thresholds (single source of truth)
# ---------------------------------------------------------------------------

MASTERY_MASTERED = 0.8
MASTERY_PARTIAL = 0.3
MASTERY_PREREQ_THRESHOLD = 0.6

# EMA weights
ALPHA_QUIZ = 0.3
ALPHA_STUDY = 0.1


# ---------------------------------------------------------------------------
# Core update helpers
# ---------------------------------------------------------------------------


def _ema(old: float, signal: float, alpha: float) -> float:
    """Exponential moving average: new = alpha * signal + (1 - alpha) * old."""
    return alpha * signal + (1.0 - alpha) * old


def record_quiz_result(
    db: Session,
    keypoint_id: str,
    is_correct: bool,
) -> Optional[tuple[float, float]]:
    """Update mastery after a quiz answer. Returns (old_level, new_level) or None."""
    keypoint = db.query(Keypoint).filter(Keypoint.id == keypoint_id).first()
    if not keypoint:
        return None

    old_level = keypoint.mastery_level or 0.0
    keypoint.attempt_count = (keypoint.attempt_count or 0) + 1
    if is_correct:
        keypoint.correct_count = (keypoint.correct_count or 0) + 1

    signal = 1.0 if is_correct else 0.0
    keypoint.mastery_level = round(_ema(old_level, signal, ALPHA_QUIZ), 4)
    db.flush()
    return old_level, keypoint.mastery_level


def record_study_interaction(
    db: Session,
    keypoint_id: str,
) -> Optional[tuple[float, float]]:
    """Nudge mastery upward after a QA/study interaction (smaller weight)."""
    keypoint = db.query(Keypoint).filter(Keypoint.id == keypoint_id).first()
    if not keypoint:
        return None

    old_level = keypoint.mastery_level or 0.0
    if old_level >= MASTERY_MASTERED:
        return old_level, old_level

    keypoint.mastery_level = round(_ema(old_level, 1.0, ALPHA_STUDY), 4)
    db.flush()
    return old_level, keypoint.mastery_level


def mastery_priority(level: float) -> str:
    if level >= MASTERY_MASTERED:
        return "completed"
    if level < MASTERY_PARTIAL:
        return "high"
    if level < 0.7:
        return "medium"
    return "low"


def mastery_action(level: float, attempt_count: int) -> str:
    if level >= MASTERY_MASTERED:
        return "review"
    if attempt_count == 0:
        return "study"
    return "quiz"
