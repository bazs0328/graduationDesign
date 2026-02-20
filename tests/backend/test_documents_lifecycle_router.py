"""Tests for document lifecycle endpoints."""

import os
from unittest.mock import patch

from app.core.paths import ensure_kb_dirs, kb_base_dir
from app.models import (
    ChatMessage,
    ChatSession,
    Document,
    Keypoint,
    KeypointRecord,
    KnowledgeBase,
    QARecord,
    Quiz,
    QuizAttempt,
    SummaryRecord,
    User,
)


def _seed_user_kbs_doc(db_session, *, user_id: str, kb_id: str, doc_id: str):
    os.makedirs("tmp", exist_ok=True)
    db_session.add(
        User(
            id=user_id,
            username=user_id,
            password_hash="test_hash",
            name="Test User",
        )
    )
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name=f"KB-{kb_id}"))
    doc = Document(
        id=doc_id,
        user_id=user_id,
        kb_id=kb_id,
        filename="origin.txt",
        file_type="txt",
        text_path=os.path.join("tmp", f"{doc_id}.txt"),
        num_chunks=1,
        num_pages=1,
        char_count=120,
        file_hash=f"hash-{doc_id}",
        status="ready",
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def test_patch_doc_supports_rename_and_move(client, db_session):
    user_id = "doc_lifecycle_user_1"
    old_kb = "doc_kb_old"
    new_kb = "doc_kb_new"
    doc_id = "doc_lifecycle_1"
    _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=old_kb,
        doc_id=doc_id,
    )
    db_session.add(KnowledgeBase(id=new_kb, user_id=user_id, name="Target KB"))
    db_session.add(
        Keypoint(
            id="kp-doc-1",
            user_id=user_id,
            doc_id=doc_id,
            kb_id=old_kb,
            text="矩阵定义",
        )
    )
    db_session.add(
        QARecord(
            id="qa-doc-1",
            user_id=user_id,
            kb_id=old_kb,
            doc_id=doc_id,
            question="Q",
            answer="A",
        )
    )
    db_session.add(
        Quiz(
            id="quiz-doc-1",
            user_id=user_id,
            kb_id=old_kb,
            doc_id=doc_id,
            questions_json="[]",
        )
    )
    db_session.add(
        ChatSession(
            id="chat-doc-1",
            user_id=user_id,
            kb_id=old_kb,
            doc_id=doc_id,
        )
    )
    db_session.commit()

    with (
        patch("app.routers.documents.update_doc_vector_metadata", return_value=1) as vector_mock,
        patch("app.routers.documents.move_doc_chunks", return_value=1) as lexical_move_mock,
    ):
        resp = client.patch(
            f"/api/docs/{doc_id}",
            json={
                "user_id": user_id,
                "filename": "renamed.txt",
                "kb_id": new_kb,
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["filename"] == "renamed.txt"
    assert payload["kb_id"] == new_kb
    vector_mock.assert_called_once()
    lexical_move_mock.assert_called_once()

    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc is not None
    assert doc.filename == "renamed.txt"
    assert doc.kb_id == new_kb
    keypoint = db_session.query(Keypoint).filter(Keypoint.doc_id == doc_id).first()
    assert keypoint is not None
    assert keypoint.kb_id == new_kb
    qa = db_session.query(QARecord).filter(QARecord.doc_id == doc_id).first()
    assert qa is not None
    assert qa.kb_id == new_kb
    quiz = db_session.query(Quiz).filter(Quiz.doc_id == doc_id).first()
    assert quiz is not None
    assert quiz.kb_id == new_kb
    session = db_session.query(ChatSession).filter(ChatSession.doc_id == doc_id).first()
    assert session is not None
    assert session.kb_id == new_kb


def test_reprocess_doc_changes_status_and_triggers_task(client, db_session):
    user_id = "doc_lifecycle_user_2"
    kb_id = "doc_kb_reprocess"
    doc_id = "doc_lifecycle_2"
    doc = _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
    )

    ensure_kb_dirs(user_id, kb_id)
    raw_dir = os.path.join(kb_base_dir(user_id, kb_id), "raw")
    raw_path = os.path.join(raw_dir, f"{doc_id}_{doc.filename}")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write("raw")

    with (
        patch("app.routers.documents.delete_doc_vectors", return_value=1),
        patch("app.routers.documents.remove_doc_chunks", return_value=1),
        patch("app.routers.documents.process_document_task") as task_mock,
    ):
        resp = client.post(
            f"/api/docs/{doc_id}/reprocess",
            params={"user_id": user_id},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "processing"
    task_mock.assert_called_once()
    called = task_mock.call_args.args
    assert called[0] == doc_id
    assert called[1] == user_id
    assert called[2] == kb_id
    assert called[3] == raw_path


def test_delete_doc_cleans_records_and_files(client, db_session):
    user_id = "doc_lifecycle_user_3"
    kb_id = "doc_kb_delete"
    doc_id = "doc_lifecycle_3"
    doc = _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
    )
    text_path = doc.text_path

    ensure_kb_dirs(user_id, kb_id)
    raw_dir = os.path.join(kb_base_dir(user_id, kb_id), "raw")
    raw_path = os.path.join(raw_dir, f"{doc_id}_{doc.filename}")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write("raw")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write("text")

    db_session.add(
        SummaryRecord(
            id="sum-doc-delete",
            user_id=user_id,
            doc_id=doc_id,
            summary_text="summary",
        )
    )
    db_session.add(
        KeypointRecord(
            id="kpr-doc-delete",
            user_id=user_id,
            doc_id=doc_id,
            points_json='["k1"]',
        )
    )
    db_session.add(
        Keypoint(
            id="kp-doc-delete",
            user_id=user_id,
            doc_id=doc_id,
            kb_id=kb_id,
            text="线性映射",
        )
    )
    db_session.add(
        QARecord(
            id="qa-doc-delete",
            user_id=user_id,
            doc_id=doc_id,
            kb_id=kb_id,
            question="Q",
            answer="A",
        )
    )
    db_session.add(
        Quiz(
            id="quiz-doc-delete",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            questions_json="[]",
        )
    )
    db_session.add(
        QuizAttempt(
            id="attempt-doc-delete",
            user_id=user_id,
            quiz_id="quiz-doc-delete",
            answers_json="[0]",
            score=1.0,
            total=1,
        )
    )
    db_session.add(
        ChatSession(
            id="chat-doc-delete",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
        )
    )
    db_session.add(
        ChatMessage(
            id="msg-doc-delete",
            session_id="chat-doc-delete",
            role="user",
            content="hello",
        )
    )
    db_session.commit()

    with (
        patch("app.routers.documents.delete_doc_vectors", return_value=1),
        patch("app.routers.documents.remove_doc_chunks", return_value=1),
    ):
        resp = client.delete(f"/api/docs/{doc_id}", params={"user_id": user_id})

    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert db_session.query(Document).filter(Document.id == doc_id).first() is None
    assert db_session.query(SummaryRecord).filter(SummaryRecord.doc_id == doc_id).first() is None
    assert db_session.query(KeypointRecord).filter(KeypointRecord.doc_id == doc_id).first() is None
    assert db_session.query(Keypoint).filter(Keypoint.doc_id == doc_id).first() is None
    assert db_session.query(QARecord).filter(QARecord.doc_id == doc_id).first() is None
    assert db_session.query(Quiz).filter(Quiz.doc_id == doc_id).first() is None
    assert (
        db_session.query(ChatSession).filter(ChatSession.doc_id == doc_id).first()
        is None
    )
    assert not os.path.exists(raw_path)
    assert not os.path.exists(text_path)


def test_doc_task_center_and_retry_failed(client, db_session):
    user_id = "doc_lifecycle_user_task"
    kb_id = "doc_kb_task"
    error_doc_id = "doc_task_error"
    processing_doc_id = "doc_task_processing"
    _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id="doc_task_ready",
    )
    error_doc = Document(
        id=error_doc_id,
        user_id=user_id,
        kb_id=kb_id,
        filename="error.txt",
        file_type="txt",
        text_path=os.path.join("tmp", f"{error_doc_id}.txt"),
        num_chunks=0,
        num_pages=0,
        char_count=0,
        file_hash=f"hash-{error_doc_id}",
        status="error",
        error_message="extract failed",
        retry_count=2,
    )
    processing_doc = Document(
        id=processing_doc_id,
        user_id=user_id,
        kb_id=kb_id,
        filename="processing.txt",
        file_type="txt",
        text_path=os.path.join("tmp", f"{processing_doc_id}.txt"),
        num_chunks=0,
        num_pages=0,
        char_count=0,
        file_hash=f"hash-{processing_doc_id}",
        status="processing",
    )
    db_session.add(error_doc)
    db_session.add(processing_doc)
    db_session.commit()

    tasks_resp = client.get("/api/docs/tasks", params={"user_id": user_id, "kb_id": kb_id})
    assert tasks_resp.status_code == 200
    payload = tasks_resp.json()
    assert payload["processing_count"] == 1
    assert payload["error_count"] == 1
    assert payload["processing"][0]["id"] == processing_doc_id
    assert payload["error"][0]["id"] == error_doc_id
    assert payload["error"][0]["retry_count"] == 2

    ensure_kb_dirs(user_id, kb_id)
    raw_dir = os.path.join(kb_base_dir(user_id, kb_id), "raw")
    raw_path = os.path.join(raw_dir, f"{error_doc_id}_{error_doc.filename}")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write("raw")

    with (
        patch("app.routers.documents.delete_doc_vectors", return_value=1),
        patch("app.routers.documents.remove_doc_chunks", return_value=1),
        patch("app.routers.documents.process_document_task"),
    ):
        retry_resp = client.post(
            "/api/docs/retry-failed",
            json={"user_id": user_id, "doc_ids": [error_doc_id]},
        )

    assert retry_resp.status_code == 200
    retry_payload = retry_resp.json()
    assert retry_payload["queued"] == [error_doc_id]
    assert retry_payload["skipped"] == []

    db_session.expire_all()
    refreshed = db_session.query(Document).filter(Document.id == error_doc_id).first()
    assert refreshed is not None
    assert refreshed.status == "processing"
    assert refreshed.retry_count == 3
