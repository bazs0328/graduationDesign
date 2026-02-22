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

