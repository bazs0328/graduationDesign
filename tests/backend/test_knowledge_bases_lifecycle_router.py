"""Tests for knowledge base lifecycle endpoints."""

import os
from unittest.mock import patch

from app.core.paths import ensure_kb_dirs, kb_base_dir
from app.models import (
    ChatMessage,
    ChatSession,
    Document,
    KnowledgeBase,
    QARecord,
    Quiz,
    QuizAttempt,
    User,
)


def _seed_user_kb(db_session, *, user_id: str, kb_id: str, kb_name: str):
    os.makedirs("tmp", exist_ok=True)
    db_session.add(
        User(
            id=user_id,
            username=user_id,
            password_hash="test_hash",
            name="Test User",
        )
    )
    kb = KnowledgeBase(id=kb_id, user_id=user_id, name=kb_name)
    db_session.add(kb)
    db_session.commit()
    return kb


def _seed_user_only(db_session, *, user_id: str):
    os.makedirs("tmp", exist_ok=True)
    db_session.add(
        User(
            id=user_id,
            username=user_id,
            password_hash="test_hash",
            name="Test User",
        )
    )
    db_session.commit()


def test_list_kbs_does_not_auto_create_default(client, db_session):
    user_id = "kb_lifecycle_user_no_default"
    _seed_user_only(db_session, user_id=user_id)

    resp = client.get("/api/kb", params={"user_id": user_id})
    assert resp.status_code == 200
    assert resp.json() == []


def test_patch_kb_rename(client, db_session):
    user_id = "kb_lifecycle_user_1"
    kb_id = "kb_lifecycle_1"
    _seed_user_kb(db_session, user_id=user_id, kb_id=kb_id, kb_name="Old KB")

    resp = client.patch(
        f"/api/kb/{kb_id}",
        json={"user_id": user_id, "name": "New KB"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["name"] == "New KB"
    kb = db_session.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    assert kb is not None
    assert kb.name == "New KB"


def test_delete_non_empty_kb_without_cascade_returns_409(client, db_session):
    user_id = "kb_lifecycle_user_2"
    kb_id = "kb_lifecycle_2"
    _seed_user_kb(db_session, user_id=user_id, kb_id=kb_id, kb_name="Busy KB")
    db_session.add(
        Document(
            id="kb-doc-2",
            user_id=user_id,
            kb_id=kb_id,
            filename="a.txt",
            file_type="txt",
            text_path=os.path.join("tmp", "kb-doc-2.txt"),
            status="ready",
        )
    )
    db_session.commit()

    resp = client.delete(f"/api/kb/{kb_id}", params={"user_id": user_id})
    assert resp.status_code == 409


def test_delete_kb_with_cascade_removes_bound_data(client, db_session):
    user_id = "kb_lifecycle_user_3"
    kb_id = "kb_lifecycle_3"
    _seed_user_kb(db_session, user_id=user_id, kb_id=kb_id, kb_name="Cascade KB")

    doc_id = "kb-doc-3"
    doc = Document(
        id=doc_id,
        user_id=user_id,
        kb_id=kb_id,
        filename="a.txt",
        file_type="txt",
        text_path=os.path.join("tmp", "kb-doc-3.txt"),
        file_hash="hash-kb-doc-3",
        status="ready",
    )
    db_session.add(doc)
    db_session.add(
        QARecord(
            id="qa-kb-3",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=None,
            question="Q",
            answer="A",
        )
    )
    db_session.add(
        Quiz(
            id="quiz-kb-3",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=None,
            questions_json="[]",
        )
    )
    db_session.add(
        QuizAttempt(
            id="attempt-kb-3",
            user_id=user_id,
            quiz_id="quiz-kb-3",
            answers_json="[0]",
            score=1.0,
            total=1,
        )
    )
    db_session.add(
        ChatSession(
            id="chat-kb-3",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=None,
        )
    )
    db_session.add(
        ChatMessage(
            id="msg-kb-3",
            session_id="chat-kb-3",
            role="user",
            content="hello",
        )
    )
    db_session.commit()

    ensure_kb_dirs(user_id, kb_id)
    raw_path = os.path.join(kb_base_dir(user_id, kb_id), "raw", f"{doc_id}_{doc.filename}")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write("raw")
    with open(doc.text_path, "w", encoding="utf-8") as f:
        f.write("text")

    with (
        patch("app.routers.knowledge_bases.delete_doc_vectors", return_value=1),
        patch("app.routers.knowledge_bases.remove_doc_chunks", return_value=1),
    ):
        resp = client.delete(
            f"/api/kb/{kb_id}",
            params={"user_id": user_id, "cascade": "true"},
        )

    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert db_session.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first() is None
    assert db_session.query(Document).filter(Document.kb_id == kb_id).first() is None
    assert db_session.query(QARecord).filter(QARecord.kb_id == kb_id).first() is None
    assert db_session.query(Quiz).filter(Quiz.kb_id == kb_id).first() is None
    assert db_session.query(ChatSession).filter(ChatSession.kb_id == kb_id).first() is None
    assert not os.path.exists(raw_path)
    assert not os.path.exists(doc.text_path)


def test_get_and_patch_kb_parse_settings(client, db_session):
    user_id = "kb_settings_user_1"
    kb_id = "kb_settings_kb_1"
    _seed_user_kb(db_session, user_id=user_id, kb_id=kb_id, kb_name="Settings KB")

    get_resp = client.get(f"/api/kb/{kb_id}/settings", params={"user_id": user_id})
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["parse_policy"] == "balanced"
    assert data["preferred_parser"] == "auto"

    patch_resp = client.patch(
        f"/api/kb/{kb_id}/settings",
        json={"user_id": user_id, "parse_policy": "aggressive", "preferred_parser": "native"},
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["parse_policy"] == "aggressive"
    assert updated["preferred_parser"] == "native"


def test_get_and_patch_kb_rag_settings(client, db_session):
    user_id = "kb_settings_user_2"
    kb_id = "kb_settings_kb_2"
    _seed_user_kb(db_session, user_id=user_id, kb_id=kb_id, kb_name="RAG Settings KB")

    get_resp = client.get(f"/api/kb/{kb_id}/rag-settings", params={"user_id": user_id})
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["rag_backend"] == "raganything_mineru"
    assert data["query_mode"] == "hybrid"
    assert data["parser_preference"] == "mineru"

    patch_resp = client.patch(
        f"/api/kb/{kb_id}/rag-settings",
        json={
            "user_id": user_id,
            "rag_backend": "legacy",
            "query_mode": "local",
            "parser_preference": "docling",
        },
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["rag_backend"] == "legacy"
    assert updated["query_mode"] == "local"
    assert updated["parser_preference"] == "docling"
