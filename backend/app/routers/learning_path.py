from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.knowledge_bases import ensure_kb
from app.core.users import ensure_user
from app.db import get_db
from app.schemas import LearningPathEdge, LearningPathItem
from app.services.learning_path import build_dependency_graph, generate_learning_path

router = APIRouter()


class LearningPathBuildResponse(BaseModel):
    kb_id: str
    edges_count: int
    message: str


class LearningPathGetResponse(BaseModel):
    kb_id: str
    items: List[LearningPathItem] = []
    edges: List[LearningPathEdge] = []


@router.post("/learning-path/build", response_model=LearningPathBuildResponse)
def build_path(
    kb_id: str,
    user_id: str | None = None,
    force: bool = False,
    db: Session = Depends(get_db),
):
    """Build or refresh the dependency graph for a knowledge base."""
    resolved_user_id = ensure_user(db, user_id)
    try:
        kb = ensure_kb(db, resolved_user_id, kb_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    deps = build_dependency_graph(db, resolved_user_id, kb.id, force=force)
    return LearningPathBuildResponse(
        kb_id=kb.id,
        edges_count=len(deps),
        message="依赖图已构建" if deps else "知识点不足，无法构建依赖图",
    )


@router.get("/learning-path", response_model=LearningPathGetResponse)
def get_path(
    kb_id: str,
    user_id: str | None = None,
    limit: int = 15,
    db: Session = Depends(get_db),
):
    """Get personalized learning path for a knowledge base."""
    resolved_user_id = ensure_user(db, user_id)
    try:
        kb = ensure_kb(db, resolved_user_id, kb_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    limit = max(1, min(limit, 50))
    items, edges = generate_learning_path(db, resolved_user_id, kb.id, limit=limit)
    return LearningPathGetResponse(kb_id=kb.id, items=items, edges=edges)
