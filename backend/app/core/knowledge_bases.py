from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Document, KnowledgeBase

DEFAULT_KB_NAME = "默认知识库"
DEFAULT_KB_LEGACY_NAMES = {"Default"}
DEFAULT_KB_DESCRIPTION = "系统默认知识库"


def ensure_default_kb(db: Session, user_id: str) -> KnowledgeBase:
    candidate_names = [DEFAULT_KB_NAME, *sorted(DEFAULT_KB_LEGACY_NAMES)]
    candidates = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.name.in_(candidate_names),
        )
        .order_by(KnowledgeBase.created_at.asc())
        .all()
    )
    kb = next((item for item in candidates if item.name == DEFAULT_KB_NAME), None)
    if not kb and candidates:
        kb = candidates[0]

    if not kb:
        kb = KnowledgeBase(
            id=str(uuid4()),
            user_id=user_id,
            name=DEFAULT_KB_NAME,
            description=DEFAULT_KB_DESCRIPTION,
        )
        db.add(kb)
        db.commit()
        db.refresh(kb)
    else:
        needs_update = False
        if kb.name != DEFAULT_KB_NAME:
            kb.name = DEFAULT_KB_NAME
            needs_update = True
        if (kb.description or "").strip() in {"", "Default knowledge base"}:
            kb.description = DEFAULT_KB_DESCRIPTION
            needs_update = True
        if needs_update:
            db.add(kb)
            db.commit()
            db.refresh(kb)
    from app.core.kb_metadata import init_kb_metadata
    from app.core.paths import ensure_kb_dirs

    ensure_kb_dirs(user_id, kb.id)
    init_kb_metadata(user_id, kb.id)

    # Backfill existing documents that do not have a knowledge base
    missing = (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.kb_id.is_(None))
        .first()
    )
    if missing:
        db.query(Document).filter(
            Document.user_id == user_id, Document.kb_id.is_(None)
        ).update({Document.kb_id: kb.id})
        db.commit()

    return kb


def ensure_kb(db: Session, user_id: str, kb_id: str | None) -> KnowledgeBase:
    if not kb_id:
        return ensure_default_kb(db, user_id)

    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user_id)
        .first()
    )
    if not kb:
        raise ValueError("Knowledge base not found")
    return kb
