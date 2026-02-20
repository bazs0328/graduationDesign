import base64
import hashlib
import hmac
import json
import time
from contextvars import ContextVar, Token
from typing import Any

from app.core.config import settings

_request_user_id: ContextVar[str | None] = ContextVar("request_user_id", default=None)


def set_request_user_id(user_id: str | None) -> Token:
    return _request_user_id.set(user_id)


def reset_request_user_id(token: Token) -> None:
    _request_user_id.reset(token)


def get_request_user_id() -> str | None:
    return _request_user_id.get()


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _sign(body: str) -> str:
    digest = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64_encode(digest)


def create_access_token(user_id: str) -> str:
    payload: dict[str, Any] = {
        "uid": user_id,
        "exp": int(time.time()) + max(1, settings.auth_token_ttl_hours) * 3600,
    }
    body = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(body)
    return f"{body}.{signature}"


def verify_access_token(token: str) -> str | None:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None
    expected = _sign(body)
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64_decode(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    uid = payload.get("uid")
    exp = payload.get("exp")
    if not isinstance(uid, str) or not uid.strip():
        return None
    if not isinstance(exp, int) or exp < int(time.time()):
        return None
    return uid.strip()


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()
