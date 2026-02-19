from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.knowledge_bases import ensure_default_kb
from app.core.kb_metadata import init_kb_metadata
from app.core.paths import ensure_kb_dirs
from app.core.users import ensure_user
from app.db import get_db
from app.models import KnowledgeBase
from app.schemas import KnowledgeBaseCreateRequest, KnowledgeBaseOut

router = APIRouter()


@router.get("/kb", response_model=list[KnowledgeBaseOut])
def list_kbs(user_id: str | None = None, db: Session = Depends(get_db)):
    resolved_user_id = ensure_user(db, user_id)
    ensure_default_kb(db, resolved_user_id)
    return (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.user_id == resolved_user_id)
        .order_by(KnowledgeBase.created_at.desc())
        .all()
    )


@router.post("/kb", response_model=KnowledgeBaseOut)
def create_kb(payload: KnowledgeBaseCreateRequest, db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Knowledge base name is required")

    resolved_user_id = ensure_user(db, payload.user_id)
    existing = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.user_id == resolved_user_id,
            KnowledgeBase.name == payload.name.strip(),
        )
        .first()
    )
    if existing:
        return existing

    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id=resolved_user_id,
        name=payload.name.strip(),
        description=payload.description,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    ensure_kb_dirs(resolved_user_id, kb.id)
    init_kb_metadata(resolved_user_id, kb.id)
    return kb
