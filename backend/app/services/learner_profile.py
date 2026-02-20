import json
from collections import Counter
from typing import Iterable, List, Tuple

from sqlalchemy.orm import Session

from app.models import Keypoint, LearnerProfile
from app.schemas import DifficultyPlan, ProfileDelta
from app.services.mastery import is_weak_mastery

ABILITY_LEVELS = ("beginner", "intermediate", "advanced")
WEAK_CONCEPT_LIMIT = 10


def get_or_create_profile(db: Session, user_id: str) -> LearnerProfile:
    """Fetch an existing learner profile or create a default one."""
    profile = (
        db.query(LearnerProfile).filter(LearnerProfile.user_id == user_id).first()
    )
    if profile:
        return profile

    profile = LearnerProfile(
        id=user_id,
        user_id=user_id,
        ability_level="intermediate",
        theta=0.0,
        frustration_score=0.0,
        weak_concepts=json.dumps([]),
        recent_accuracy=0.5,
        total_attempts=0,
        consecutive_low_scores=0,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _deserialize_weak_concepts(raw: str | None) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [str(item) for item in data if item]
    return []


def get_weak_concepts(profile: LearnerProfile) -> List[str]:
    """Get weak concepts list from learner profile."""
    return _deserialize_weak_concepts(profile.weak_concepts)


def get_weak_concepts_by_mastery(
    db: Session,
    user_id: str,
    limit: int = WEAK_CONCEPT_LIMIT,
) -> List[str]:
    """
    Determine weak concepts from keypoint mastery instead of wrong-answer frequency.

    Rules:
    - concept must be weak by mastery threshold (< MASTERY_PARTIAL)
    - exclude untouched zero-state keypoints (attempt_count == 0 and mastery_level == 0)
    - deduplicate by text, keep lower-mastery / more-attempted items first
    """
    rows = (
        db.query(Keypoint.text, Keypoint.mastery_level, Keypoint.attempt_count)
        .filter(Keypoint.user_id == user_id)
        .all()
    )

    candidates = []
    for text, mastery_level, attempt_count in rows:
        concept = str(text or "").strip()
        if not concept:
            continue
        mastery = float(mastery_level or 0.0)
        attempts = int(attempt_count or 0)
        if attempts == 0 and mastery <= 0.0:
            continue
        if not is_weak_mastery(mastery):
            continue
        candidates.append((concept, mastery, attempts))

    # weaker first, then more attempts first to prioritize repeatedly problematic concepts
    candidates.sort(key=lambda item: (item[1], -item[2], item[0]))

    weak_concepts: List[str] = []
    seen: set[str] = set()
    for concept, _, _ in candidates:
        if concept in seen:
            continue
        seen.add(concept)
        weak_concepts.append(concept)
        if len(weak_concepts) >= max(1, limit):
            break
    return weak_concepts


def _serialize_weak_concepts(concepts: Iterable[str]) -> str:
    return json.dumps(list(concepts), ensure_ascii=False)


def generate_difficulty_plan(profile: LearnerProfile) -> DifficultyPlan:
    """Generate difficulty ratios based on the learner profile."""
    if profile.ability_level == "beginner" or profile.frustration_score > 0.7:
        return DifficultyPlan(
            easy=0.8,
            medium=0.2,
            hard=0.0,
            message="为你准备了基础巩固题目，加油！",
        )

    if profile.ability_level == "intermediate":
        if profile.recent_accuracy < 0.5:
            return DifficultyPlan(easy=0.5, medium=0.4, hard=0.1)
        return DifficultyPlan(easy=0.3, medium=0.5, hard=0.2)

    return DifficultyPlan(easy=0.1, medium=0.4, hard=0.5)


def extract_weak_concepts(questions: List[dict], results: List[bool]) -> List[str]:
    """Extract weak concepts from incorrect answers."""
    weak: List[str] = []
    for question, is_correct in zip(questions, results):
        if is_correct:
            continue
        concepts = question.get("concepts") or []
        if isinstance(concepts, list):
            weak.extend([str(item) for item in concepts if item])
    return weak


def update_profile_after_quiz(
    db: Session,
    user_id: str,
    accuracy: float,
    wrong_concepts: List[str] | None = None,
) -> Tuple[LearnerProfile, ProfileDelta]:
    """Update learner profile based on quiz results."""
    profile = get_or_create_profile(db, user_id)
    before_theta = profile.theta
    before_ability_level = profile.ability_level
    before_frustration = profile.frustration_score
    before_recent_accuracy = profile.recent_accuracy

    if profile.total_attempts == 0:
        profile.recent_accuracy = accuracy
    else:
        alpha = 0.3
        profile.recent_accuracy = (
            (1 - alpha) * profile.recent_accuracy + alpha * accuracy
        )

    profile.total_attempts += 1

    if accuracy < 0.3:
        profile.consecutive_low_scores += 1
        profile.frustration_score = min(1.0, profile.frustration_score + 0.15)
    elif accuracy < 0.5:
        profile.consecutive_low_scores = max(0, profile.consecutive_low_scores - 1)
        profile.frustration_score = min(1.0, profile.frustration_score + 0.05)
    else:
        profile.consecutive_low_scores = 0
        profile.frustration_score = max(0.0, profile.frustration_score - 0.05)

    # Keep storage field for backward compatibility but derive content from mastery-level.
    weak_by_mastery = get_weak_concepts_by_mastery(db, user_id, limit=WEAK_CONCEPT_LIMIT)
    if weak_by_mastery:
        profile.weak_concepts = _serialize_weak_concepts(weak_by_mastery)
    elif wrong_concepts:
        # Fallback only when keypoint mastery evidence is unavailable.
        existing = _deserialize_weak_concepts(profile.weak_concepts)
        counter = Counter(existing + wrong_concepts)
        profile.weak_concepts = _serialize_weak_concepts(
            [concept for concept, _ in counter.most_common(WEAK_CONCEPT_LIMIT)]
        )
    else:
        profile.weak_concepts = _serialize_weak_concepts([])

    _maybe_update_ability(profile)
    db.commit()
    db.refresh(profile)

    delta = ProfileDelta(
        theta_delta=profile.theta - before_theta,
        frustration_delta=profile.frustration_score - before_frustration,
        recent_accuracy_delta=profile.recent_accuracy - before_recent_accuracy,
        ability_level_changed=profile.ability_level != before_ability_level,
    )
    return profile, delta


def _maybe_update_ability(profile: LearnerProfile) -> None:
    if profile.total_attempts < 3:
        return

    current = profile.ability_level
    if current not in ABILITY_LEVELS:
        profile.ability_level = "intermediate"
        return

    if profile.recent_accuracy >= 0.8 and current != "advanced":
        profile.ability_level = (
            "intermediate" if current == "beginner" else "advanced"
        )
    elif profile.recent_accuracy <= 0.4 and current == "advanced":
        profile.ability_level = "intermediate"
