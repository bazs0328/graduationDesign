"""Tests for chat router."""
from uuid import uuid4

from app.models import ChatMessage, ChatSession, User


def _create_temp_session(db_session, seeded_session, *, title=None):
    session_id = f"session-{uuid4()}"
    db_session.add(
        ChatSession(
            id=session_id,
            user_id=seeded_session["user_id"],
            kb_id=seeded_session["kb_id"],
            doc_id=seeded_session["doc_id"],
            title=title,
        )
    )
    db_session.commit()
    return session_id


def test_create_session_returns_id(client, seeded_session):
    """POST /api/chat/sessions returns session with id."""
    resp = client.post(
        "/api/chat/sessions",
        json={
            "user_id": seeded_session["user_id"],
            "doc_id": seeded_session["doc_id"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data.get("doc_id") == seeded_session["doc_id"]


def test_create_session_without_kb_returns_404(client, db_session):
    user_id = f"chat_no_kb_user_{uuid4()}"
    db_session.add(
        User(
            id=user_id,
            username=user_id,
            password_hash="test_hash",
            name="No KB User",
        )
    )
    db_session.commit()

    resp = client.post(
        "/api/chat/sessions",
        json={
            "user_id": user_id,
            "name": "No KB",
        },
    )
    assert resp.status_code == 404
    assert "No knowledge base found" in resp.json().get("detail", "")


def test_list_messages_empty_for_new_session(client, seeded_session):
    """GET /api/chat/sessions/{id}/messages returns empty list for new session."""
    resp = client.get(
        f"/api/chat/sessions/{seeded_session['session_id']}/messages",
        params={"user_id": seeded_session["user_id"]},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_messages_404_for_invalid_session(client, seeded_session):
    """GET /api/chat/sessions/{id}/messages returns 404 for non-existent session."""
    resp = client.get(
        "/api/chat/sessions/00000000-0000-0000-0000-000000000000/messages",
        params={"user_id": seeded_session["user_id"]},
    )
    assert resp.status_code == 404


def test_update_session_title(client, seeded_session, db_session):
    """PATCH /api/chat/sessions/{id} updates session title."""
    session_id = _create_temp_session(db_session, seeded_session)
    resp = client.patch(
        f"/api/chat/sessions/{session_id}",
        json={
            "user_id": seeded_session["user_id"],
            "name": "线性代数复习",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "线性代数复习"

    session = (
        db_session.query(ChatSession)
        .filter(ChatSession.id == session_id)
        .first()
    )
    assert session is not None
    assert session.title == "线性代数复习"


def test_clear_session_messages(client, seeded_session, db_session):
    """DELETE /api/chat/sessions/{id}/messages removes messages but keeps session."""
    session_id = _create_temp_session(db_session, seeded_session)
    db_session.add(
        ChatMessage(
            id=str(uuid4()),
            session_id=session_id,
            role="user",
            content="hello",
        )
    )
    db_session.add(
        ChatMessage(
            id=str(uuid4()),
            session_id=session_id,
            role="assistant",
            content="world",
        )
    )
    db_session.commit()

    resp = client.delete(
        f"/api/chat/sessions/{session_id}/messages",
        params={"user_id": seeded_session["user_id"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cleared"] == 2

    messages = (
        db_session.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .all()
    )
    assert messages == []
    session = (
        db_session.query(ChatSession)
        .filter(ChatSession.id == session_id)
        .first()
    )
    assert session is not None


def test_delete_session_removes_session_and_messages(client, seeded_session, db_session):
    """DELETE /api/chat/sessions/{id} removes session and child messages."""
    session_id = _create_temp_session(db_session, seeded_session)
    db_session.add(
        ChatMessage(
            id=str(uuid4()),
            session_id=session_id,
            role="user",
            content="hello",
        )
    )
    db_session.commit()

    resp = client.delete(
        f"/api/chat/sessions/{session_id}",
        params={"user_id": seeded_session["user_id"]},
    )
    assert resp.status_code == 200

    list_resp = client.get(
        f"/api/chat/sessions/{session_id}/messages",
        params={"user_id": seeded_session["user_id"]},
    )
    assert list_resp.status_code == 404
