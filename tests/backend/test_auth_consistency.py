"""Tests for token-based auth consistency and user isolation."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.models import Document, Keypoint, Quiz, SummaryRecord


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


def test_read_progress_route_uses_authenticated_user_context_without_user_id(
    client, db_session
):
    user_a = _register_or_login(client, "auth_consistency_progress_a")
    user_b = _register_or_login(client, "auth_consistency_progress_b")
    user_a_id = user_a["user_id"]
    user_b_id = user_b["user_id"]

    db_session.add(
        Document(
            id="progress-doc-a",
            user_id=user_a_id,
            kb_id=None,
            filename="a.txt",
            file_type="txt",
            text_path="tmp/a.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
        )
    )
    db_session.add(
        Document(
            id="progress-doc-b",
            user_id=user_b_id,
            kb_id=None,
            filename="b.txt",
            file_type="txt",
            text_path="tmp/b.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
        )
    )
    db_session.commit()

    resp = client.get("/api/progress", headers=_auth_headers(user_a))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_docs"] == 1


def test_cross_user_resource_reads_are_rejected_without_explicit_user_id(
    client, db_session, tmp_path
):
    user_a = _register_or_login(client, "auth_consistency_read_a")
    user_b = _register_or_login(client, "auth_consistency_read_b")
    user_b_id = user_b["user_id"]

    text_path = Path(tmp_path) / "auth_read_b.txt"
    text_path.write_text("test content", encoding="utf-8")
    doc_id = "auth-read-doc-b"
    quiz_id = "auth-read-quiz-b"

    db_session.add(
        Document(
            id=doc_id,
            user_id=user_b_id,
            kb_id=None,
            filename="b.txt",
            file_type="txt",
            text_path=str(text_path),
            num_chunks=1,
            num_pages=1,
            char_count=12,
            status="ready",
        )
    )
    db_session.add(
        SummaryRecord(
            id="auth-read-summary-b",
            user_id=user_b_id,
            doc_id=doc_id,
            summary_text="summary",
        )
    )
    db_session.add(
        Keypoint(
            id="auth-read-kp-b",
            user_id=user_b_id,
            kb_id=None,
            doc_id=doc_id,
            text="概念B",
            mastery_level=0.1,
        )
    )
    db_session.add(
        Quiz(
            id=quiz_id,
            user_id=user_b_id,
            kb_id=None,
            doc_id=doc_id,
            difficulty="medium",
            question_type="mcq",
            questions_json=json.dumps(
                [
                    {
                        "question": "q1",
                        "options": ["A", "B", "C", "D"],
                        "answer_index": 0,
                        "explanation": "e",
                        "concepts": ["概念B"],
                    }
                ]
            ),
        )
    )
    db_session.commit()

    headers = _auth_headers(user_a)

    with patch("app.routers.summary.summarize_text", new=AsyncMock(return_value="summary")):
        summary_resp = client.post("/api/summary", json={"doc_id": doc_id}, headers=headers)
    assert summary_resp.status_code == 404

    keypoints_resp = client.get(f"/api/keypoints/{doc_id}", headers=headers)
    assert keypoints_resp.status_code == 404

    with patch("app.routers.quiz.generate_quiz", return_value=[]):
        quiz_generate_resp = client.post(
            "/api/quiz/generate",
            json={"doc_id": doc_id, "count": 1, "difficulty": "easy"},
            headers=headers,
        )
    assert quiz_generate_resp.status_code == 404

    quiz_submit_resp = client.post(
        "/api/quiz/submit",
        json={"quiz_id": quiz_id, "answers": [0]},
        headers=headers,
    )
    assert quiz_submit_resp.status_code == 404
