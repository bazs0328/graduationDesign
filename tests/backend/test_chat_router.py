"""Tests for chat router."""
from datetime import datetime, timedelta
from uuid import uuid4

from app.models import ChatMessage, ChatSession, Document, KnowledgeBase, User


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


def test_list_sessions_page_returns_metadata_and_stable_order(client, db_session):
    user_id = "chat_page_user_1"
    kb_id = "chat_page_kb_1"
    doc_id = "chat_page_doc_1"
    db_session.add(User(id=user_id, username=user_id, password_hash="test_hash", name="Chat Page User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="Chat Page KB"))
    db_session.add(
        Document(
            id=doc_id,
            user_id=user_id,
            kb_id=kb_id,
            filename="chat-page.txt",
            file_type="txt",
            text_path="tmp/chat_page_doc_1.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
        )
    )
    base_time = datetime.utcnow()
    db_session.add(
        ChatSession(
            id="sess-a",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            title="A",
            created_at=base_time,
        )
    )
    db_session.add(
        ChatSession(
            id="sess-b",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            title="B",
            created_at=base_time,
        )
    )
    db_session.add(
        ChatSession(
            id="sess-c",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            title="C",
            created_at=base_time - timedelta(minutes=1),
        )
    )
    db_session.commit()

    first_page = client.get(
        "/api/chat/sessions/page",
        params={"user_id": user_id, "offset": 0, "limit": 2},
    )
    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert first_payload["total"] == 3
    assert first_payload["offset"] == 0
    assert first_payload["limit"] == 2
    assert first_payload["has_more"] is True
    assert [item["id"] for item in first_payload["items"]] == ["sess-b", "sess-a"]

    second_page = client.get(
        "/api/chat/sessions/page",
        params={"user_id": user_id, "offset": 2, "limit": 2},
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["has_more"] is False
    assert [item["id"] for item in second_payload["items"]] == ["sess-c"]


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
