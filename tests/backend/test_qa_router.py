"""Tests for QA router."""
from types import SimpleNamespace
from unittest.mock import patch

from app.models import ChatMessage


def _mock_answer(*args, **kwargs):
    return (
        "mock answer from LLM",
        [{"source": "doc p.1 c.0", "snippet": "snippet text", "doc_id": "doc-1"}],
    )


def test_qa_without_doc_or_kb_returns_400(client):
    """POST /api/qa without doc_id or kb_id returns 400."""
    resp = client.post(
        "/api/qa",
        json={"question": "What is a matrix?", "user_id": "test"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "detail" in data
    assert "doc_id" in data["detail"] or "kb_id" in data["detail"]


def test_qa_with_kb_id_success(client, seeded_session):
    """POST /api/qa with kb_id only returns answer and sources (mocked)."""
    with patch("app.routers.qa.answer_question", side_effect=_mock_answer):
        resp = client.post(
            "/api/qa",
            json={
                "kb_id": seeded_session["kb_id"],
                "user_id": seeded_session["user_id"],
                "question": "What is a matrix?",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "mock answer from LLM"
    assert isinstance(data["sources"], list)
    assert len(data["sources"]) > 0


def test_qa_passes_adaptive_profile_to_service(client, seeded_session):
    """POST /api/qa passes profile ability/weak concepts and returns ability_level."""
    profile = SimpleNamespace(ability_level="advanced")
    with (
        patch("app.routers.qa.get_or_create_profile", return_value=profile),
        patch("app.routers.qa.get_weak_concepts_by_mastery", return_value=["矩阵", "特征值"]),
        patch("app.routers.qa.answer_question", side_effect=_mock_answer) as mocked_answer,
    ):
        resp = client.post(
            "/api/qa",
            json={
                "kb_id": seeded_session["kb_id"],
                "user_id": seeded_session["user_id"],
                "question": "What is a matrix?",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ability_level"] == "advanced"
    kwargs = mocked_answer.call_args.kwargs
    assert kwargs["ability_level"] == "advanced"
    assert kwargs["weak_concepts"] == ["矩阵", "特征值"]


def test_qa_with_invalid_session_id_returns_404(client, seeded_session):
    """POST /api/qa with non-existent session_id returns 404."""
    with patch("app.routers.qa.answer_question", side_effect=_mock_answer):
        resp = client.post(
            "/api/qa",
            json={
                "doc_id": seeded_session["doc_id"],
                "user_id": seeded_session["user_id"],
                "session_id": "00000000-0000-0000-0000-000000000000",
                "question": "What is a matrix?",
            },
        )
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower() or "Session" in data["detail"]


def test_qa_with_session_persists_sources(client, seeded_session, db_session):
    """POST /api/qa with session_id persists answer and sources; GET messages returns them."""
    with patch("app.routers.qa.answer_question", side_effect=_mock_answer):
        resp = client.post(
            "/api/qa",
            json={
                "doc_id": seeded_session["doc_id"],
                "user_id": seeded_session["user_id"],
                "session_id": seeded_session["session_id"],
                "question": "What is a matrix?",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "mock answer from LLM"
    assert isinstance(data["sources"], list)
    assert len(data["sources"]) > 0

    # Assert ChatMessage has sources_json
    msgs = (
        db_session.query(ChatMessage)
        .filter(ChatMessage.session_id == seeded_session["session_id"])
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    assistant_msgs = [m for m in msgs if m.role == "assistant"]
    assert len(assistant_msgs) >= 1
    assert assistant_msgs[-1].sources_json is not None
    assert "snippet" in assistant_msgs[-1].sources_json

    # GET messages returns sources
    get_resp = client.get(
        f"/api/chat/sessions/{seeded_session['session_id']}/messages",
        params={"user_id": seeded_session["user_id"]},
    )
    assert get_resp.status_code == 200
    messages = get_resp.json()
    assert isinstance(messages, list)
    assistant_in_response = [m for m in messages if m.get("role") == "assistant"]
    assert len(assistant_in_response) >= 1
    assert assistant_in_response[-1].get("sources") is not None
    assert len(assistant_in_response[-1]["sources"]) > 0
