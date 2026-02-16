from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.users import ensure_user
from app.db import get_db
from app.schemas import DifficultyPlan, LearnerProfileOut
from app.services.learner_profile import (
    generate_difficulty_plan,
    get_or_create_profile,
    get_weak_concepts,
)

router = APIRouter()


@router.get("/profile", response_model=LearnerProfileOut)
def get_profile(user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    profile = get_or_create_profile(db, resolved_user_id)
    return LearnerProfileOut(
        user_id=profile.user_id,
        ability_level=profile.ability_level,
        theta=profile.theta,
        frustration_score=profile.frustration_score,
        weak_concepts=get_weak_concepts(profile),
        recent_accuracy=profile.recent_accuracy,
        total_attempts=profile.total_attempts,
        updated_at=profile.updated_at,
    )


@router.get("/profile/difficulty-plan", response_model=DifficultyPlan)
def get_difficulty_plan(user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    profile = get_or_create_profile(db, resolved_user_id)
    return generate_difficulty_plan(profile)
