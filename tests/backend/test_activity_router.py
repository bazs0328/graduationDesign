"""Tests for activity router pagination behavior."""

from datetime import datetime, timedelta

from app.models import (
    Document,
    KeypointRecord,
    KnowledgeBase,
    QARecord,
    Quiz,
    QuizAttempt,
    SummaryRecord,
    User,
)


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


def test_activity_supports_offset_pagination_with_metadata(client, db_session):
    user_id = "activity_page_user_1"
    kb_id = "activity_page_kb_1"
    doc_id = "activity_page_doc_1"
    quiz_id = "activity_page_quiz_1"
    base_time = datetime.utcnow()

    db_session.add(User(id=user_id, username=user_id, password_hash="test_hash", name="Activity User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="Activity KB"))
    db_session.add(
        Document(
            id=doc_id,
            user_id=user_id,
            kb_id=kb_id,
            filename="activity.txt",
            file_type="txt",
            text_path="tmp/activity_page_doc_1.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
            created_at=base_time - timedelta(minutes=4),
        )
    )
    db_session.add(
        SummaryRecord(
            id="activity_summary_1",
            user_id=user_id,
            doc_id=doc_id,
            summary_text="summary",
            created_at=base_time - timedelta(minutes=3),
        )
    )
    db_session.add(
        KeypointRecord(
            id="activity_keypoints_1",
            user_id=user_id,
            doc_id=doc_id,
            points_json="[]",
            created_at=base_time - timedelta(minutes=2),
        )
    )
    db_session.add(
        QARecord(
            id="activity_qa_1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            question="What is a matrix?",
            answer="A matrix is ...",
            created_at=base_time - timedelta(minutes=1),
        )
    )
    db_session.add(
        Quiz(
            id=quiz_id,
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            questions_json="[]",
            created_at=base_time - timedelta(seconds=40),
        )
    )
    db_session.add(
        QuizAttempt(
            id="activity_attempt_1",
            user_id=user_id,
            quiz_id=quiz_id,
            answers_json="[]",
            score=0.8,
            total=5,
            created_at=base_time,
        )
    )
    db_session.commit()

    resp = client.get(
        "/api/activity",
        params={"user_id": user_id, "limit": 2, "offset": 1},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 5
    assert payload["offset"] == 1
    assert payload["limit"] == 2
    assert payload["has_more"] is True
    assert [item["type"] for item in payload["items"]] == ["question_asked", "keypoints_generated"]

    tail_resp = client.get(
        "/api/activity",
        params={"user_id": user_id, "limit": 2, "offset": 4},
    )
    assert tail_resp.status_code == 200
    tail_payload = tail_resp.json()
    assert tail_payload["has_more"] is False
    assert [item["type"] for item in tail_payload["items"]] == ["document_upload"]


def test_activity_uses_authenticated_user_context_without_user_id(client, db_session):
    user_a = _register_or_login(client, "activity_auth_user_a")
    user_b = _register_or_login(client, "activity_auth_user_b")
    user_a_id = user_a["user_id"]
    user_b_id = user_b["user_id"]

    base_time = datetime.utcnow()
    db_session.add(
        Document(
            id="activity-auth-doc-a",
            user_id=user_a_id,
            kb_id=None,
            filename="a.txt",
            file_type="txt",
            text_path="tmp/activity_auth_a.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
            created_at=base_time - timedelta(seconds=1),
        )
    )
    db_session.add(
        Document(
            id="activity-auth-doc-b",
            user_id=user_b_id,
            kb_id=None,
            filename="b.txt",
            file_type="txt",
            text_path="tmp/activity_auth_b.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
            created_at=base_time,
        )
    )
    db_session.commit()

    resp = client.get(
        "/api/activity",
        headers={"Authorization": f"Bearer {user_a['access_token']}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["doc_id"] == "activity-auth-doc-a"


def test_activity_resolves_doc_name_for_quiz_attempt_and_other_sources(client, db_session):
    user_id = "activity_map_user_1"
    kb_id = "activity_map_kb_1"
    doc_id = "activity_map_doc_1"
    quiz_id = "activity_map_quiz_1"
    base_time = datetime.utcnow()

    db_session.add(User(id=user_id, username=user_id, password_hash="test_hash", name="Map User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="Map KB"))
    db_session.add(
        Document(
            id=doc_id,
            user_id=user_id,
            kb_id=kb_id,
            filename="mapped.txt",
            file_type="txt",
            text_path="tmp/mapped.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
            created_at=base_time - timedelta(minutes=2),
        )
    )
    db_session.add(
        SummaryRecord(
            id="activity-map-summary",
            user_id=user_id,
            doc_id=doc_id,
            summary_text="summary",
            created_at=base_time - timedelta(minutes=1),
        )
    )
    db_session.add(
        Quiz(
            id=quiz_id,
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            questions_json="[]",
            created_at=base_time - timedelta(seconds=30),
        )
    )
    db_session.add(
        QuizAttempt(
            id="activity-map-attempt",
            user_id=user_id,
            quiz_id=quiz_id,
            answers_json="[]",
            score=1.0,
            total=1,
            created_at=base_time,
        )
    )
    db_session.commit()

    resp = client.get("/api/activity", params={"user_id": user_id, "limit": 10, "offset": 0})
    assert resp.status_code == 200
    items = resp.json()["items"]
    summary_item = next(item for item in items if item["type"] == "summary_generated")
    attempt_item = next(item for item in items if item["type"] == "quiz_attempt")

    assert summary_item["doc_id"] == doc_id
    assert summary_item["doc_name"] == "mapped.txt"
    assert attempt_item["doc_id"] == doc_id
    assert attempt_item["doc_name"] == "mapped.txt"
    assert attempt_item["detail"] == "Quiz submitted"
