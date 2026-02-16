from sqlalchemy.orm import Session

from app.models import User

DEFAULT_USER_ID = "default"


def ensure_user(db: Session, user_id: str | None) -> str:
    resolved = (user_id or DEFAULT_USER_ID).strip() or DEFAULT_USER_ID
    user = db.query(User).filter(User.id == resolved).first()
    if not user:
        user = User(
            id=resolved,
            username=resolved,
            password_hash="",
            name=None,
        )
        db.add(user)
        db.commit()
    # Ensure a default knowledge base exists for the user
    from app.core.knowledge_bases import ensure_default_kb

    ensure_default_kb(db, resolved)
    return resolved
