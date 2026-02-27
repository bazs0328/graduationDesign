"""Unified mastery service: EMA-based calculation, scoring helpers, and updates."""

import logging
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.models import Keypoint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mastery thresholds (single source of truth)
# ---------------------------------------------------------------------------

MASTERY_MASTERED = 0.8
MASTERY_PARTIAL = 0.3
MASTERY_PREREQ_THRESHOLD = 0.6
MASTERY_STABLE = 0.7

# EMA weights
ALPHA_QUIZ = 0.15
ALPHA_STUDY = 0.1


# ---------------------------------------------------------------------------
# Core update helpers
# ---------------------------------------------------------------------------


def _ema(old: float, signal: float, alpha: float) -> float:
    """Exponential moving average: new = alpha * signal + (1 - alpha) * old."""
    return alpha * signal + (1.0 - alpha) * old


def normalize_mastery(level: float | None) -> float:
    """Normalize mastery value to [0, 1]."""
    try:
        value = float(level or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(1.0, value))


def is_mastered(level: float | None) -> bool:
    """Whether mastery reaches the 'completed/mastered' threshold."""
    return normalize_mastery(level) >= MASTERY_MASTERED


def is_weak_mastery(level: float | None) -> bool:
    """Whether mastery is still in the weak area."""
    return normalize_mastery(level) < MASTERY_PARTIAL


def mastery_ratio(levels: Sequence[float], *, threshold: float) -> float:
    """Ratio of levels that reach the given threshold."""
    if not levels:
        return 0.0
    hits = sum(1 for level in levels if normalize_mastery(level) >= threshold)
    return round(hits / len(levels), 4)


def mastery_completion_rate(levels: Sequence[float]) -> float:
    """Completion rate based on mastered keypoints."""
    return mastery_ratio(levels, threshold=MASTERY_MASTERED)


def mastery_average(levels: Sequence[float]) -> float:
    """Average normalized mastery level."""
    if not levels:
        return 0.0
    total = sum(normalize_mastery(level) for level in levels)
    return round(total / len(levels), 4)


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
    if is_mastered(level):
        return "completed"
    if is_weak_mastery(level):
        return "high"
    if normalize_mastery(level) < MASTERY_STABLE:
        return "medium"
    return "low"


def mastery_action(level: float, attempt_count: int) -> str:
    """
    Determine the recommended action based on mastery level and attempt count.
    
    Logic:
    - If mastered (>= 0.8): review to maintain
    - If never quizzed (attempt_count == 0): quiz first to assess current level
    - If quizzed but very low mastery (< 0.3): study to build foundation
    - Otherwise: continue quizzing to improve
    """
    if is_mastered(level):
        return "review"
    # Prioritize quiz for new keypoints to assess understanding
    if attempt_count == 0:
        return "quiz"
    # If quizzed but mastery is very low, suggest study first
    if is_weak_mastery(level):
        return "study"
    # Continue quizzing for moderate mastery levels
    return "quiz"
