from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.users import ensure_user
from app.db import get_db
from app.models import Keypoint
from app.schemas import DifficultyPlan, LearnerProfileOut
from app.services.learner_profile import (
    generate_difficulty_plan,
    get_or_create_profile,
    get_weak_concepts_by_mastery,
)
from app.services.mastery import mastery_average, mastery_completion_rate

router = APIRouter()


@router.get("/profile", response_model=LearnerProfileOut)
def get_profile(user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    profile = get_or_create_profile(db, resolved_user_id)
    mastery_values = [
        float(row[0] or 0.0)
        for row in db.query(Keypoint.mastery_level)
        .filter(Keypoint.user_id == resolved_user_id)
        .all()
    ]
    return LearnerProfileOut(
        user_id=profile.user_id,
        ability_level=profile.ability_level,
        theta=profile.theta,
        frustration_score=profile.frustration_score,
        weak_concepts=get_weak_concepts_by_mastery(db, resolved_user_id),
        recent_accuracy=profile.recent_accuracy,
        total_attempts=profile.total_attempts,
        mastery_avg=mastery_average(mastery_values),
        mastery_completion_rate=mastery_completion_rate(mastery_values),
        updated_at=profile.updated_at,
    )


@router.get("/profile/difficulty-plan", response_model=DifficultyPlan)
def get_difficulty_plan(user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    profile = get_or_create_profile(db, resolved_user_id)
    return generate_difficulty_plan(profile)
