from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Document, KnowledgeBase

DEFAULT_KB_NAME = "Default"


def ensure_default_kb(db: Session, user_id: str) -> KnowledgeBase:
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.user_id == user_id, KnowledgeBase.name == DEFAULT_KB_NAME)
        .first()
    )
    if not kb:
        kb = KnowledgeBase(
            id=str(uuid4()),
            user_id=user_id,
            name=DEFAULT_KB_NAME,
            description="Default knowledge base",
        )
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
