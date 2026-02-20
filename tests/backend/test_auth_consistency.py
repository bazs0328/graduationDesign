"""Tests for token-based auth consistency and user isolation."""

from app.core.config import settings


def _register_or_login(client, username: str, password: str = "pass123456"):
    register = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "name": username},
    )
    if register.status_code == 200:
        return register.json()
    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200
    return login.json()


def test_auth_login_returns_access_token(client):
    payload = _register_or_login(client, "auth_consistency_user_1")
    assert payload["user_id"]
    assert payload["access_token"]
    assert payload["token_type"] == "bearer"


def test_write_operations_use_authenticated_user_context(client):
    user_a = _register_or_login(client, "auth_consistency_user_a")
    user_b = _register_or_login(client, "auth_consistency_user_b")

    headers = {"Authorization": f"Bearer {user_a['access_token']}"}

    mismatch_resp = client.post(
        "/api/kb",
        json={"name": "Should Fail", "user_id": user_b["user_id"]},
        headers=headers,
    )
    assert mismatch_resp.status_code == 403

    ok_resp = client.post(
        "/api/kb",
        json={"name": "Owned by A"},
        headers=headers,
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["user_id"] == user_a["user_id"]


def test_protected_route_rejects_unauthenticated_when_legacy_disabled(client):
    old_allow_legacy = settings.auth_allow_legacy_user_id
    try:
        settings.auth_allow_legacy_user_id = False
        resp = client.get("/api/kb")
        assert resp.status_code == 401
    finally:
        settings.auth_allow_legacy_user_id = old_allow_legacy
