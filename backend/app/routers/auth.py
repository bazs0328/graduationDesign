import uuid

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schemas import AuthLoginRequest, AuthRegisterRequest, AuthResponse

from app.core.auth import create_access_token, get_request_user_id
from app.core.config import settings

BCRYPT_MAX_BYTES = 72

router = APIRouter(prefix="/auth", tags=["auth"])


def _password_bytes(s: str | None) -> bytes:
    """Normalize password to at most 72 bytes for bcrypt."""
    if s is None or not s:
        return b""
    return s.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_password_bytes(plain), hashed.encode("ascii"))
    except Exception:
        return False


@router.post("/register", response_model=AuthResponse)
def register(payload: AuthRegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        username=payload.username,
        password_hash=hash_password(payload.password),
        name=payload.name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthResponse(
        user_id=user.id,
        username=user.username,
        name=user.name,
        access_token=create_access_token(user.id),
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: AuthLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash or ""):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return AuthResponse(
        user_id=user.id,
        username=user.username,
        name=user.name,
        access_token=create_access_token(user.id),
    )


@router.get("/me", response_model=AuthResponse)
def me(user_id: str | None = None, db: Session = Depends(get_db)):
    authenticated = get_request_user_id()
    requested = (user_id or "").strip() or None
    if authenticated and requested and requested != authenticated:
        raise HTTPException(status_code=403, detail="user_id does not match authenticated user")
    if authenticated:
        resolved_user_id = authenticated
    else:
        if settings.auth_allow_legacy_user_id and requested:
            resolved_user_id = requested
        elif settings.auth_allow_legacy_user_id:
            raise HTTPException(status_code=400, detail="缺少 user_id")
        else:
            raise HTTPException(status_code=401, detail="Authentication required")
    user = db.query(User).filter(User.id == resolved_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return AuthResponse(
        user_id=user.id,
        username=user.username,
        name=user.name,
        access_token=create_access_token(user.id),
    )
