"""Integration tests for settings router."""

import json

from app.core import bootstrap_config
from app.core.config import settings
from app.core import provider_config
from app.models import KnowledgeBase, User
from app.routers import settings as settings_router
import pytest


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


@pytest.fixture
def isolated_provider_data_dir(tmp_path, monkeypatch):
    original_data_dir = settings.data_dir
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    provider_config.load_provider_config()
    try:
        yield tmp_path
    finally:
        monkeypatch.setattr(settings, "data_dir", original_data_dir)
        provider_config.load_provider_config()


def test_get_settings_returns_defaults_and_system_status_without_secret_values(client):
    user = _register_or_login(client, "settings_defaults_user")
    resp = client.get("/api/settings", headers=_auth_headers(user))
    assert resp.status_code == 200

    data = resp.json()
    assert data["system_status"]["llm_provider"] == "unconfigured"
    assert data["system_status"]["embedding_provider"] == "unconfigured"
    assert data["system_status"]["llm_provider_configured"] == "auto"
    assert data["system_status"]["embedding_provider_configured"] == "auto"
    assert data["system_status"]["llm_provider_source"] == "auto"
    assert data["system_status"]["embedding_provider_source"] == "auto"
    assert isinstance(data["system_status"]["secrets_configured"], dict)
    assert data["system_status"]["secrets_configured"]["qwen_api_key"] is False
    assert "auth_secret_key_configured" not in data["system_status"]["secrets_configured"]
    assert data["system_status"]["qa_defaults"]["qa_dynamic_window_enabled"] is True
    assert data["system_status"]["notices"] == []

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


def test_get_settings_tolerates_legacy_kb_extra_keys(client, db_session):
    user = _register_or_login(client, "settings_legacy_kb_extra_user")
    headers = _auth_headers(user)
    kb_id = client.get("/api/kb", headers=headers).json()[0]["id"]

    kb = db_session.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    assert kb is not None
    kb.preferences_json = json.dumps(
        {"learning_path": {"order_anchor": {"keypoint_ids": ["kp-1"], "updated_at": 1772198555}}},
        ensure_ascii=False,
    )
    db_session.add(kb)
    db_session.commit()

    resp = client.get(f"/api/settings?kb_id={kb_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["kb_overrides"] is not None
    assert "learning_path" not in data["kb_overrides"]

    db_session.refresh(kb)
    raw = json.loads(kb.preferences_json)
    assert "learning_path" in raw


def test_patch_kb_settings_overwrites_legacy_dirty_payload(client, db_session):
    user = _register_or_login(client, "settings_legacy_kb_patch_user")
    headers = _auth_headers(user)
    kb_id = client.get("/api/kb", headers=headers).json()[0]["id"]

    kb = db_session.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    assert kb is not None
    kb.preferences_json = json.dumps(
        {"learning_path": {"order_anchor": {"keypoint_ids": ["kp-1"], "updated_at": 1772198555}}},
        ensure_ascii=False,
    )
    db_session.add(kb)
    db_session.commit()

    resp = client.patch(
        f"/api/settings/kb/{kb_id}",
        json={"qa": {"mode": "explain"}},
        headers=headers,
    )
    assert resp.status_code == 200
    assert "learning_path" not in (resp.json()["kb_overrides"] or {})

    db_session.refresh(kb)
    stored = json.loads(kb.preferences_json)
    assert stored == {"qa": {"mode": "explain"}}


def test_get_settings_tolerates_legacy_user_extra_keys(client, db_session):
    user = _register_or_login(client, "settings_legacy_user_extra_user")
    headers = _auth_headers(user)

    row = db_session.query(User).filter(User.id == user["user_id"]).first()
    assert row is not None
    row.preferences_json = json.dumps(
        {"qa": {"mode": "normal"}, "learning_path": {"order_anchor": {"updated_at": 1772198555}}},
        ensure_ascii=False,
    )
    db_session.add(row)
    db_session.commit()

    resp = client.get("/api/settings", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_defaults"]["qa"]["mode"] == "normal"
    assert "learning_path" not in data["user_defaults"]

    db_session.refresh(row)
    raw = json.loads(row.preferences_json)
    assert "learning_path" in raw


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


def test_advanced_settings_patch_and_reset_are_user_scoped(client):
    user = _register_or_login(client, "settings_advanced_patch_user")
    other_user = _register_or_login(client, "settings_adv_patch_other")
    headers = _auth_headers(user)
    other_headers = _auth_headers(other_user)

    initial = client.get("/api/settings/advanced", headers=headers)
    assert initial.status_code == 200
    initial_data = initial.json()
    assert "rag_mode" in initial_data["editable_keys"]
    assert "qa_dynamic_window_enabled" in initial_data["editable_keys"]
    assert "auth_require_login" not in initial_data["editable_keys"]
    assert "lexical_stopwords_global_path" not in initial_data["editable_keys"]
    assert isinstance(initial_data.get("schema"), dict)
    assert isinstance(initial_data["schema"].get("groups"), list)
    assert isinstance(initial_data["schema"].get("fields"), list)
    assert any(item.get("key") == "rag_mode" for item in initial_data["schema"]["fields"])
    assert any(item.get("key") == "qa_dynamic_window_enabled" for item in initial_data["schema"]["fields"])

    patched = client.patch(
        "/api/settings/advanced",
        json={"values": {"rag_mode": "dense", "qa_top_k": 9, "qa_fetch_k": 18, "qa_dynamic_window_enabled": False}},
        headers=headers,
    )
    assert patched.status_code == 200
    patched_data = patched.json()
    assert patched_data["overrides"]["rag_mode"] == "dense"
    assert patched_data["overrides"]["qa_top_k"] == 9
    assert patched_data["overrides"]["qa_dynamic_window_enabled"] is False
    assert patched_data["effective"]["qa_fetch_k"] == 18

    status = client.get("/api/settings", headers=headers)
    assert status.status_code == 200
    status_data = status.json()
    assert status_data["system_status"]["qa_defaults"]["rag_mode"] == "dense"
    assert status_data["system_status"]["qa_defaults"]["qa_top_k"] == 9
    assert status_data["system_status"]["qa_defaults"]["qa_dynamic_window_enabled"] is False

    other_status = client.get("/api/settings", headers=other_headers)
    assert other_status.status_code == 200
    other_status_data = other_status.json()
    assert other_status_data["system_status"]["qa_defaults"]["rag_mode"] == "hybrid"
    assert other_status_data["system_status"]["qa_defaults"]["qa_top_k"] == 4

    reset = client.post("/api/settings/advanced/reset", json={"keys": ["rag_mode", "qa_top_k", "qa_fetch_k", "qa_dynamic_window_enabled"]}, headers=headers)
    assert reset.status_code == 200
    assert "rag_mode" not in reset.json()["overrides"]


def test_advanced_settings_patch_rejects_unknown_key(client):
    user = _register_or_login(client, "settings_advanced_bad_key_user")
    headers = _auth_headers(user)
    resp = client.patch(
        "/api/settings/advanced",
        json={"values": {"not_a_real_setting": 1}},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Unsupported advanced setting key" in resp.json()["detail"]


def test_provider_settings_patch_masks_keys_and_updates_setup(client, db_session):
    user = _register_or_login(client, "settings_provider_patch_user")
    other_user = _register_or_login(client, "settings_provider_other")
    headers = _auth_headers(user)
    other_headers = _auth_headers(other_user)

    patched = client.patch(
        "/api/settings/provider",
        json={
            "values": {
                "llm_provider": "qwen",
                "embedding_provider": "dashscope",
                "qwen": {
                    "api_key": "draft-secret-5678",
                    "region": "international",
                    "model": "qwen-plus",
                },
                "dashscope": {
                    "region": "international",
                    "embedding_model": "text-embedding-v4",
                },
            }
        },
        headers=headers,
    )
    assert patched.status_code == 200
    patched_data = patched.json()
    assert patched_data["effective"]["qwen"]["api_key_configured"] is True
    assert patched_data["effective"]["qwen"]["api_key_masked"] == "••••5678"
    assert "api_key" not in patched_data["effective"]["qwen"]
    assert patched_data["effective"]["qwen"]["base_url"] == provider_config.QWEN_REGION_PRESETS["international"]["base_url"]
    assert patched_data["effective"]["dashscope"]["base_url"] == provider_config.DASHSCOPE_REGION_PRESETS["international"]["base_url"]
    assert patched_data["setup"]["llm_ready"] is True
    assert patched_data["setup"]["embedding_ready"] is True

    stored_user = db_session.query(User).filter(User.id == user["user_id"]).first()
    assert stored_user is not None
    stored_raw = json.loads(stored_user.provider_config_json)
    assert stored_raw["qwen"]["api_key"] == "draft-secret-5678"
    assert stored_raw["qwen"]["base_url"] == provider_config.QWEN_REGION_PRESETS["international"]["base_url"]
    assert stored_raw["dashscope"]["base_url"] == provider_config.DASHSCOPE_REGION_PRESETS["international"]["base_url"]

    get_resp = client.get("/api/settings/provider", headers=headers)
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["effective"]["qwen"]["api_key_masked"] == "••••5678"
    assert "api_key" not in get_data["effective"]["qwen"]

    other_get_resp = client.get("/api/settings/provider", headers=other_headers)
    assert other_get_resp.status_code == 200
    other_get_data = other_get_resp.json()
    assert other_get_data["effective"]["qwen"]["api_key_configured"] is False
    assert other_get_data["effective"]["llm_provider"] == "auto"

    settings_resp = client.get("/api/settings", headers=headers)
    assert settings_resp.status_code == 200
    setup = settings_resp.json()["system_status"]["provider_setup"]
    assert setup["llm_ready"] is True
    assert setup["embedding_ready"] is True
    assert setup["current_llm_provider"] == "qwen"
    assert setup["current_embedding_provider"] == "dashscope"

    cleared = client.patch(
        "/api/settings/provider",
        json={
            "values": {
                "qwen": {"clear_api_key": True},
            }
        },
        headers=headers,
    )
    assert cleared.status_code == 200
    cleared_data = cleared.json()
    assert cleared_data["effective"]["qwen"]["api_key_configured"] is False
    assert cleared_data["effective"]["qwen"]["api_key_masked"] is None

    settings_after_clear = client.get("/api/settings", headers=headers)
    assert settings_after_clear.status_code == 200
    cleared_setup = settings_after_clear.json()["system_status"]["provider_setup"]
    assert cleared_setup["llm_ready"] is False
    assert cleared_setup["embedding_ready"] is False
    assert "qwen.api_key" in cleared_setup["missing"]


def test_provider_settings_detect_legacy_global_config_without_inheriting_secrets(client, isolated_provider_data_dir):
    legacy_provider_path = isolated_provider_data_dir / "system_provider_config.json"
    legacy_provider_path.write_text(
        json.dumps(
            {
                "llm_provider": "qwen",
                "embedding_provider": "dashscope",
                "qwen": {
                    "api_key": "legacy-shared-key",
                    "base_url": "https://legacy.example.com/compatible-mode/v1",
                    "model": "legacy-qwen",
                },
                "dashscope": {
                    "base_url": "https://legacy.example.com/api/v1",
                    "embedding_model": "legacy-embed",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    provider_config.load_provider_config()

    user = _register_or_login(client, "settings_provider_legacy_user")
    headers = _auth_headers(user)

    resp = client.get("/api/settings/provider", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["effective"]["llm_provider"] == "auto"
    assert data["effective"]["embedding_provider"] == "auto"
    assert data["effective"]["qwen"]["api_key_configured"] is False

    settings_resp = client.get("/api/settings", headers=headers)
    assert settings_resp.status_code == 200
    notices = settings_resp.json()["system_status"]["notices"]
    assert any("历史全局 provider 配置文件" in notice for notice in notices)


def test_provider_settings_test_endpoint_uses_draft_without_persisting(
    client,
    isolated_provider_data_dir,
    monkeypatch,
):
    calls = {}

    def fake_test_provider_connection(current_config, values, target="auto", advanced_config=None):
        calls["current_config"] = current_config
        calls["values"] = values
        calls["target"] = target
        calls["advanced_config"] = advanced_config
        return {
            "ok": True,
            "provider": "deepseek",
            "target": "llm",
            "message": "deepseek 对话模型连接正常",
        }

    monkeypatch.setattr(settings_router, "test_provider_connection", fake_test_provider_connection)

    user = _register_or_login(client, "settings_provider_test_user")
    headers = _auth_headers(user)
    resp = client.post(
        "/api/settings/provider/test",
        json={
            "target": "llm",
            "values": {
                "llm_provider": "deepseek",
                "deepseek": {
                    "api_key": "preview-only-key",
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat",
                },
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert calls["target"] == "llm"
    assert calls["values"]["deepseek"]["api_key"] == "preview-only-key"
    assert calls["current_config"] == {}
    assert calls["advanced_config"] == {}

    stored_path = isolated_provider_data_dir / "system_provider_config.json"
    assert not stored_path.exists()

    get_resp = client.get("/api/settings/provider", headers=headers)
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["effective"]["deepseek"]["api_key_configured"] is False


def test_startup_generates_bootstrap_auth_secret(isolated_provider_data_dir, monkeypatch):
    monkeypatch.setattr(settings, "auth_secret_key", "gradtutor-dev-secret")

    state = bootstrap_config.ensure_bootstrap_config()

    bootstrap_path = isolated_provider_data_dir / "system_bootstrap.json"
    assert bootstrap_path.exists()
    stored = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    assert stored["auth_secret_key"] == state["auth_secret_key"]
    assert stored["auth_secret_key"] == settings.auth_secret_key
    assert stored["auth_secret_key"] != "gradtutor-dev-secret"


def test_startup_migrates_env_values_only_to_override_file(isolated_provider_data_dir, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "qwen")
    monkeypatch.setattr(settings, "embedding_provider", "dashscope")
    monkeypatch.setattr(settings, "qwen_api_key", "migrated-qwen-key")
    monkeypatch.setattr(settings, "qwen_base_url", "https://migrate.example.com/compatible-mode/v1")
    monkeypatch.setattr(settings, "dashscope_base_url", "https://migrate.example.com/api/v1")
    monkeypatch.setattr(settings, "qa_top_k", 9)
    monkeypatch.setattr(settings, "rag_mode", "dense")

    result = bootstrap_config.run_startup_migrations()

    provider_path = isolated_provider_data_dir / "system_provider_config.json"
    overrides_path = isolated_provider_data_dir / "system_overrides.json"
    assert not provider_path.exists()
    assert overrides_path.exists()

    overrides_data = json.loads(overrides_path.read_text(encoding="utf-8"))

    assert result["provider_config"] == {}
    assert overrides_data["qa_top_k"] == 9
    assert overrides_data["rag_mode"] == "dense"
