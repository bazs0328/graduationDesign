"""Integration tests for settings router."""

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


def _auth_headers(payload: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_get_settings_returns_defaults_and_system_status_without_secret_values(client):
    user = _register_or_login(client, "settings_defaults_user")
    resp = client.get("/api/settings", headers=_auth_headers(user))
    assert resp.status_code == 200

    data = resp.json()
    assert data["system_status"]["llm_provider"] == "qwen"
    assert data["system_status"]["embedding_provider"] == "dashscope"
    assert data["system_status"]["llm_provider_configured"] == "qwen"
    assert data["system_status"]["embedding_provider_configured"] == "dashscope"
    assert data["system_status"]["llm_provider_source"] == "manual"
    assert data["system_status"]["embedding_provider_source"] == "manual"
    assert "openai_api_key" not in data["system_status"]
    assert isinstance(data["system_status"]["secrets_configured"], dict)

    effective = data["effective"]
    assert effective["qa"]["retrieval_preset"] == "balanced"
    assert effective["qa"]["top_k"] == 4
    assert effective["qa"]["fetch_k"] == 12
    assert effective["quiz"]["count_default"] == 5
    assert effective["ui"]["density"] == "comfortable"


def test_patch_user_settings_deep_merge_and_explicit_null_clears_manual_values(client):
    user = _register_or_login(client, "settings_patch_user")
    headers = _auth_headers(user)

    first = client.patch(
        "/api/settings/user",
        json={
            "qa": {"retrieval_preset": "deep", "top_k": 9, "fetch_k": 30},
            "ui": {"density": "compact"},
        },
        headers=headers,
    )
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["user_defaults"]["qa"]["retrieval_preset"] == "deep"
    assert first_data["user_defaults"]["qa"]["top_k"] == 9
    assert first_data["user_defaults"]["qa"]["fetch_k"] == 30
    assert first_data["user_defaults"]["ui"]["density"] == "compact"
    assert first_data["effective"]["qa"]["top_k"] == 9
    assert first_data["effective"]["qa"]["fetch_k"] == 30

    second = client.patch(
        "/api/settings/user",
        json={
            "qa": {"retrieval_preset": "fast", "top_k": None, "fetch_k": None},
        },
        headers=headers,
    )
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["user_defaults"]["qa"]["retrieval_preset"] == "fast"
    assert second_data["user_defaults"]["qa"]["top_k"] is None
    assert second_data["user_defaults"]["qa"]["fetch_k"] is None
    assert second_data["effective"]["qa"]["top_k"] == 3
    assert second_data["effective"]["qa"]["fetch_k"] == 8
    assert second_data["user_defaults"]["ui"]["density"] == "compact"


def test_patch_kb_settings_rejects_cross_user_kb_access_with_404(client):
    user_a = _register_or_login(client, "settings_kb_owner_a")
    user_b = _register_or_login(client, "settings_kb_owner_b")

    kbs_resp = client.get("/api/kb", headers=_auth_headers(user_b))
    assert kbs_resp.status_code == 200
    kb_list = kbs_resp.json()
    assert kb_list
    user_b_kb_id = kb_list[0]["id"]

    patch_resp = client.patch(
        f"/api/settings/kb/{user_b_kb_id}",
        json={"qa": {"mode": "explain"}},
        headers=_auth_headers(user_a),
    )
    assert patch_resp.status_code == 404
    assert "Knowledge base not found" in patch_resp.json()["detail"]


def test_patch_kb_settings_rejects_ui_payload(client):
    user = _register_or_login(client, "settings_kb_scope_user")
    kbs_resp = client.get("/api/kb", headers=_auth_headers(user))
    kb_id = kbs_resp.json()[0]["id"]

    resp = client.patch(
        f"/api/settings/kb/{kb_id}",
        json={"ui": {"density": "compact"}},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 400
    assert "KB overrides only support qa and quiz settings" in resp.json()["detail"]


def test_settings_validation_rejects_out_of_range_values(client):
    user = _register_or_login(client, "settings_validation_user")
    resp = client.patch(
        "/api/settings/user",
        json={"qa": {"top_k": 0}},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 422


def test_settings_route_requires_auth_when_legacy_user_id_disabled(client):
    old_allow_legacy = settings.auth_allow_legacy_user_id
    try:
        settings.auth_allow_legacy_user_id = False
        resp = client.get("/api/settings")
        assert resp.status_code == 401
    finally:
        settings.auth_allow_legacy_user_id = old_allow_legacy


def test_system_settings_patch_and_reset_runtime_overrides(client):
    user = _register_or_login(client, "settings_system_patch_user")
    headers = _auth_headers(user)

    initial = client.get("/api/settings/system", headers=headers)
    assert initial.status_code == 200
    initial_data = initial.json()
    assert "rag_mode" in initial_data["editable_keys"]
    assert isinstance(initial_data.get("schema"), dict)
    assert isinstance(initial_data["schema"].get("groups"), list)
    assert isinstance(initial_data["schema"].get("fields"), list)
    assert any(item.get("key") == "rag_mode" for item in initial_data["schema"]["fields"])

    patched = client.patch(
        "/api/settings/system",
        json={"values": {"rag_mode": "dense", "qa_top_k": 9, "qa_fetch_k": 18}},
        headers=headers,
    )
    assert patched.status_code == 200
    patched_data = patched.json()
    assert patched_data["overrides"]["rag_mode"] == "dense"
    assert patched_data["overrides"]["qa_top_k"] == 9
    assert patched_data["effective"]["qa_fetch_k"] == 18

    status = client.get("/api/settings", headers=headers)
    assert status.status_code == 200
    status_data = status.json()
    assert status_data["system_status"]["qa_defaults_from_env"]["rag_mode"] == "dense"
    assert status_data["system_status"]["qa_defaults_from_env"]["qa_top_k"] == 9

    reset = client.post("/api/settings/system/reset", json={"keys": ["rag_mode", "qa_top_k", "qa_fetch_k"]}, headers=headers)
    assert reset.status_code == 200
    assert "rag_mode" not in reset.json()["overrides"]


def test_system_settings_patch_rejects_unknown_key(client):
    user = _register_or_login(client, "settings_system_bad_key_user")
    headers = _auth_headers(user)
    resp = client.patch(
        "/api/settings/system",
        json={"values": {"not_a_real_setting": 1}},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Unsupported system setting key" in resp.json()["detail"]
