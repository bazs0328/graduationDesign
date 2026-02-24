"""Tests for progress router aggregate behavior and auth scoping."""

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


def test_progress_uses_authenticated_user_context_without_user_id(client, db_session):
    user_a = _register_or_login(client, "progress_auth_user_a")
    user_b = _register_or_login(client, "progress_auth_user_b")
    user_a_id = user_a["user_id"]
    user_b_id = user_b["user_id"]

    db_session.add(KnowledgeBase(id="progress-kb-a", user_id=user_a_id, name="KB A"))
    db_session.add(KnowledgeBase(id="progress-kb-b", user_id=user_b_id, name="KB B"))
    db_session.add(
        Document(
            id="progress-auth-doc-a-1",
            user_id=user_a_id,
            kb_id="progress-kb-a",
            filename="a.txt",
            file_type="txt",
            text_path="tmp/progress_a.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
        )
    )
    db_session.add(
        Document(
            id="progress-auth-doc-b-1",
            user_id=user_b_id,
            kb_id="progress-kb-b",
            filename="b.txt",
            file_type="txt",
            text_path="tmp/progress_b.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
        )
    )
    db_session.commit()

    resp = client.get(
        "/api/progress",
        headers={"Authorization": f"Bearer {user_a['access_token']}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_docs"] == 1
    by_kb = {item["kb_id"]: item for item in payload["by_kb"]}
    assert "progress-kb-a" in by_kb
    assert by_kb["progress-kb-a"]["total_docs"] == 1
    assert "progress-kb-b" not in by_kb


def test_progress_kb_branch_returns_expected_aggregates_without_doc_id_list_leakage(client, db_session):
    user_id = "progress_user_agg"
    kb_id = "progress_kb_agg"
    other_kb = "progress_kb_other"
    base_time = datetime.utcnow()
    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="Progress User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="主KB"))
    db_session.add(KnowledgeBase(id=other_kb, user_id=user_id, name="其他KB"))

    db_session.add(
        Document(
            id="progress-doc-1",
            user_id=user_id,
            kb_id=kb_id,
            filename="d1.txt",
            file_type="txt",
            text_path="tmp/d1.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
            created_at=base_time - timedelta(minutes=10),
        )
    )
    db_session.add(
        Document(
            id="progress-doc-2",
            user_id=user_id,
            kb_id=kb_id,
            filename="d2.txt",
            file_type="txt",
            text_path="tmp/d2.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
            created_at=base_time - timedelta(minutes=9),
        )
    )
    db_session.add(
        Document(
            id="progress-doc-3",
            user_id=user_id,
            kb_id=other_kb,
            filename="d3.txt",
            file_type="txt",
            text_path="tmp/d3.txt",
            num_chunks=1,
            num_pages=1,
            char_count=10,
            status="ready",
            created_at=base_time - timedelta(minutes=8),
        )
    )

    db_session.add(
        SummaryRecord(
            id="progress-sum-1",
            user_id=user_id,
            doc_id="progress-doc-1",
            summary_text="s1",
            created_at=base_time - timedelta(minutes=7),
        )
    )
    db_session.add(
        KeypointRecord(
            id="progress-kp-1",
            user_id=user_id,
            doc_id="progress-doc-2",
            points_json="[]",
            created_at=base_time - timedelta(minutes=6),
        )
    )

    db_session.add(
        Quiz(
            id="progress-quiz-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id="progress-doc-1",
            questions_json="[]",
            created_at=base_time - timedelta(minutes=5),
        )
    )
    db_session.add(
        Quiz(
            id="progress-quiz-2",
            user_id=user_id,
            kb_id=other_kb,
            doc_id="progress-doc-3",
            questions_json="[]",
            created_at=base_time - timedelta(minutes=4),
        )
    )
    db_session.add(
        QuizAttempt(
            id="progress-attempt-1",
            user_id=user_id,
            quiz_id="progress-quiz-1",
            answers_json="[]",
            score=0.75,
            total=4,
            created_at=base_time - timedelta(minutes=3),
        )
    )
    db_session.add(
        QARecord(
            id="progress-qa-kb",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=None,
            question="q kb",
            answer="a",
            created_at=base_time - timedelta(minutes=2),
        )
    )
    db_session.add(
        QARecord(
            id="progress-qa-doc",
            user_id=user_id,
            kb_id=None,
            doc_id="progress-doc-2",
            question="q doc",
            answer="a",
            created_at=base_time - timedelta(minutes=1),
        )
    )
    db_session.commit()

    resp = client.get("/api/progress", params={"user_id": user_id, "kb_id": kb_id})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_docs"] == 2
    assert payload["total_summaries"] == 1
    assert payload["total_keypoints"] == 1
    assert payload["total_quizzes"] == 1
    assert payload["total_attempts"] == 1
    assert payload["total_questions"] == 2
    assert payload["avg_score"] == 0.75
    assert len(payload["by_kb"]) == 1
    assert payload["by_kb"][0]["kb_id"] == kb_id
    assert payload["by_kb"][0]["total_questions"] == 2


def test_progress_kb_branch_empty_kb_returns_zero_counts(client, db_session):
    user_id = "progress_user_empty"
    kb_id = "progress_kb_empty"
    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="Empty User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="Empty KB"))
    db_session.commit()

    resp = client.get("/api/progress", params={"user_id": user_id, "kb_id": kb_id})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_docs"] == 0
    assert payload["total_quizzes"] == 0
    assert payload["total_attempts"] == 0
    assert payload["total_questions"] == 0
    assert payload["total_summaries"] == 0
    assert payload["total_keypoints"] == 0
    assert payload["avg_score"] == 0.0
    assert len(payload["by_kb"]) == 1
    assert payload["by_kb"][0]["kb_id"] == kb_id
