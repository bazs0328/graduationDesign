from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.core.auth import get_request_user_id
from app.core.config import settings
from app.models import User

DEFAULT_USER_ID = "default"


def ensure_user(db: Session, user_id: str | None) -> str:
    requested = (user_id or "").strip() or None
    authenticated = get_request_user_id()

    if authenticated:
        if requested and requested != authenticated:
            raise HTTPException(status_code=403, detail="user_id does not match authenticated user")
        resolved = authenticated
    else:
        if settings.auth_require_login and not settings.auth_allow_legacy_user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        resolved = requested or DEFAULT_USER_ID

    user = db.query(User).filter(User.id == resolved).first()
    if not user:
        if authenticated:
            raise HTTPException(status_code=401, detail="Authenticated user no longer exists")
        user = User(
            id=resolved,
            username=resolved,
            password_hash="",
            name=None,
        )
        db.add(user)
        db.commit()
    return resolved
