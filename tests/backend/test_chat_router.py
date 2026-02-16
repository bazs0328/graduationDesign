"""Tests for chat router."""


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
