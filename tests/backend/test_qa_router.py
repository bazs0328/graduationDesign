"""Tests for QA router."""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models import ChatMessage, Document, Keypoint, KnowledgeBase, User
from app.routers.qa import QA_HISTORY_TOTAL_CHAR_BUDGET, _update_mastery_from_qa
from app.utils.chroma_filters import build_chroma_eq_filter


MOCK_SOURCES = [{"source": "doc p.1 c.0", "snippet": "snippet text", "doc_id": "doc-1"}]


def _mock_prepare(*args, **kwargs):
    return {
        "no_results": False,
        "sources": MOCK_SOURCES,
        "formatted_messages": ["mock-message"],
        "retrieved_count": len(MOCK_SOURCES),
        "mode": "normal",
    }


def _mock_prepare_no_results(*args, **kwargs):
    return {
        "no_results": True,
        "sources": [],
        "formatted_messages": None,
        "retrieved_count": 0,
        "mode": "normal",
    }


def _parse_sse_events(raw_text: str):
    events = []
    blocks = [block.strip() for block in raw_text.split("\n\n") if block.strip()]
    for block in blocks:
        event_name = None
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        payload = {}
        if data_lines:
            payload = json.loads("\n".join(data_lines))
        events.append((event_name, payload))
    return events


def _read_sse(client, method, url, **kwargs):
    with client.stream(method, url, **kwargs) as resp:
        body = "".join(resp.iter_text())
        return resp, _parse_sse_events(body)


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
    with (
        patch("app.routers.qa.prepare_qa_answer", side_effect=_mock_prepare),
        patch("app.routers.qa.get_llm", return_value=object()),
        patch("app.routers.qa.generate_qa_answer", return_value="mock answer from LLM"),
        patch("app.routers.qa._update_mastery_from_qa"),
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
    assert data["answer"] == "mock answer from LLM"
    assert isinstance(data["sources"], list)
    assert len(data["sources"]) > 0
    assert data["mode"] == "normal"


def test_qa_explain_mode_passed_and_returned(client, seeded_session):
    profile = SimpleNamespace(ability_level="intermediate")
    explain_prepare = {
        "no_results": False,
        "sources": MOCK_SOURCES,
        "formatted_messages": ["mock-message"],
        "retrieved_count": 1,
        "mode": "explain",
    }
    with (
        patch("app.routers.qa.get_or_create_profile", return_value=profile),
        patch("app.routers.qa.get_weak_concepts_by_mastery", return_value=[]),
        patch("app.routers.qa.prepare_qa_answer", return_value=explain_prepare) as mocked_prepare,
        patch("app.routers.qa.get_llm", return_value=object()),
        patch("app.routers.qa.generate_qa_answer", return_value="## 题意理解\n...\n## 分步解答\n..."),
        patch("app.routers.qa._update_mastery_from_qa"),
    ):
        resp = client.post(
            "/api/qa",
            json={
                "kb_id": seeded_session["kb_id"],
                "user_id": seeded_session["user_id"],
                "question": "请讲解这道题",
                "mode": "explain",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "explain"
    assert mocked_prepare.call_args.kwargs["mode"] == "explain"


def test_qa_passes_adaptive_profile_to_service(client, seeded_session):
    """POST /api/qa passes profile ability/weak concepts and returns ability_level."""
    profile = SimpleNamespace(ability_level="advanced")
    with (
        patch("app.routers.qa.get_or_create_profile", return_value=profile),
        patch("app.routers.qa.get_weak_concepts_by_mastery", return_value=["矩阵", "特征值"]),
        patch("app.routers.qa.prepare_qa_answer", side_effect=_mock_prepare) as mocked_prepare,
        patch("app.routers.qa.get_llm", return_value=object()),
        patch("app.routers.qa.generate_qa_answer", return_value="mock answer from LLM"),
        patch("app.routers.qa._update_mastery_from_qa"),
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
    kwargs = mocked_prepare.call_args.kwargs
    assert kwargs["ability_level"] == "advanced"
    assert kwargs["weak_concepts"] == ["矩阵", "特征值"]


def test_qa_with_invalid_session_id_returns_404(client, seeded_session):
    """POST /api/qa with non-existent session_id returns 404."""
    with patch("app.routers.qa._update_mastery_from_qa"):
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
    with (
        patch("app.routers.qa.prepare_qa_answer", side_effect=_mock_prepare),
        patch("app.routers.qa.get_llm", return_value=object()),
        patch("app.routers.qa.generate_qa_answer", return_value="mock answer from LLM"),
        patch("app.routers.qa._update_mastery_from_qa"),
    ):
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

    get_resp = client.get(
        f"/api/chat/sessions/{seeded_session['session_id']}/messages",
        params={"user_id": seeded_session["user_id"]},
    )
    assert get_resp.status_code == 200
    messages = get_resp.json()
    assistant_in_response = [m for m in messages if m.get("role") == "assistant"]
    assert len(assistant_in_response) >= 1
    assert assistant_in_response[-1].get("sources") is not None
    assert len(assistant_in_response[-1]["sources"]) > 0


def test_qa_session_history_is_budgeted_and_keeps_recent_messages(client, seeded_session, db_session):
    session_id = seeded_session["session_id"]
    user_id = seeded_session["user_id"]
    doc_id = seeded_session["doc_id"]
    base_time = datetime.utcnow() - timedelta(minutes=20)

    for idx in range(14):
        role = "user" if idx % 2 == 0 else "assistant"
        content = f"msg-{idx}-" + ("very long content " * 30)
        db_session.add(
            ChatMessage(
                id=f"history-budget-{idx}",
                session_id=session_id,
                role=role,
                content=content,
                created_at=base_time + timedelta(minutes=idx),
            )
        )
    db_session.commit()

    with (
        patch("app.routers.qa.prepare_qa_answer", side_effect=_mock_prepare) as mocked_prepare,
        patch("app.routers.qa.get_llm", return_value=object()),
        patch("app.routers.qa.generate_qa_answer", return_value="mock answer from LLM"),
        patch("app.routers.qa._update_mastery_from_qa"),
    ):
        resp = client.post(
            "/api/qa",
            json={
                "doc_id": doc_id,
                "user_id": user_id,
                "session_id": session_id,
                "question": "Summarize context",
            },
        )

    assert resp.status_code == 200
    history = mocked_prepare.call_args.kwargs["history"]
    assert history is not None
    assert len(history) <= QA_HISTORY_TOTAL_CHAR_BUDGET
    assert "[Recent messages]" in history
    assert "[Earlier conversation summary]" in history
    assert "msg-13-" in history


def test_qa_stream_post_success_sends_ordered_events(client, seeded_session):
    with (
        patch("app.routers.qa.prepare_qa_answer", side_effect=_mock_prepare),
        patch("app.routers.qa.get_llm", return_value=object()),
        patch("app.routers.qa.stream_qa_answer", return_value=iter(["mock ", "answer"])),
        patch("app.routers.qa._update_mastery_from_qa"),
    ):
        resp, events = _read_sse(
            client,
            "POST",
            "/api/qa/stream",
            json={
                "doc_id": seeded_session["doc_id"],
                "user_id": seeded_session["user_id"],
                "session_id": seeded_session["session_id"],
                "question": "What is a matrix?",
            },
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    names = [name for name, _ in events]
    assert "status" in names
    assert "sources" in names
    assert "chunk" in names
    assert names[-1] == "done"
    done_payload = [payload for name, payload in events if name == "done"][-1]
    assert done_payload["result"] == "ok"
    assert "ability_level" in done_payload
    assert done_payload["mode"] == "normal"
    assert "timings" in done_payload
    assert done_payload["retrieved_count"] == 1


def test_qa_stream_post_no_results_returns_done_without_chunks(client, seeded_session):
    with (
        patch("app.routers.qa.prepare_qa_answer", side_effect=_mock_prepare_no_results),
        patch("app.routers.qa._update_mastery_from_qa"),
    ):
        resp, events = _read_sse(
            client,
            "POST",
            "/api/qa/stream",
            json={
                "kb_id": seeded_session["kb_id"],
                "user_id": seeded_session["user_id"],
                "question": "unknown",
            },
        )

    assert resp.status_code == 200
    names = [name for name, _ in events]
    assert "chunk" not in names
    done_payload = [payload for name, payload in events if name == "done"][-1]
    assert done_payload["result"] == "no_results"
    error_payloads = [payload for name, payload in events if name == "error"]
    assert not error_payloads


def test_qa_stream_get_available(client, seeded_session):
    with (
        patch("app.routers.qa.prepare_qa_answer", side_effect=_mock_prepare_no_results),
        patch("app.routers.qa._update_mastery_from_qa"),
    ):
        resp, _events = _read_sse(
            client,
            "GET",
            "/api/qa/stream",
            params={
                "question": "What is a matrix?",
                "user_id": seeded_session["user_id"],
                "kb_id": seeded_session["kb_id"],
            },
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")


def test_qa_stream_persists_sources_in_session(client, seeded_session, db_session):
    with (
        patch("app.routers.qa.prepare_qa_answer", side_effect=_mock_prepare),
        patch("app.routers.qa.get_llm", return_value=object()),
        patch("app.routers.qa.stream_qa_answer", return_value=iter(["mock answer"])),
        patch("app.routers.qa._update_mastery_from_qa"),
    ):
        resp, events = _read_sse(
            client,
            "POST",
            "/api/qa/stream",
            json={
                "doc_id": seeded_session["doc_id"],
                "user_id": seeded_session["user_id"],
                "session_id": seeded_session["session_id"],
                "question": "What is a matrix?",
            },
        )
    assert resp.status_code == 200
    assert [name for name, _ in events][-1] == "done"

    msgs = (
        db_session.query(ChatMessage)
        .filter(ChatMessage.session_id == seeded_session["session_id"])
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    assistant_msgs = [m for m in msgs if m.role == "assistant"]
    assert assistant_msgs
    assert assistant_msgs[-1].sources_json is not None
    assert "doc p.1 c.0" in assistant_msgs[-1].sources_json


def test_qa_stream_generation_error_emits_retryable_error(client, seeded_session):
    with (
        patch("app.routers.qa.prepare_qa_answer", side_effect=_mock_prepare),
        patch("app.routers.qa.get_llm", return_value=object()),
        patch("app.routers.qa.stream_qa_answer", side_effect=RuntimeError("stream boom")),
        patch("app.routers.qa._update_mastery_from_qa"),
    ):
        resp, events = _read_sse(
            client,
            "POST",
            "/api/qa/stream",
            json={
                "kb_id": seeded_session["kb_id"],
                "user_id": seeded_session["user_id"],
                "question": "What is a matrix?",
            },
        )
    assert resp.status_code == 200
    error_payload = [payload for name, payload in events if name == "error"][-1]
    assert error_payload["retryable"] is True
    assert error_payload["code"] == "generation_failed"


def test_update_mastery_from_qa_kb_vector_hits_collapse_to_representative(db_session):
    user_id = "qa_kb_dedup_user"
    kb_id = "qa_kb_dedup_kb"
    doc1 = "qa_kb_dedup_doc1"
    doc2 = "qa_kb_dedup_doc2"
    rep_id = "qa_kb_dedup_kp1"
    dup_id = "qa_kb_dedup_kp2"
    base = datetime.utcnow()

    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="KB"))
    db_session.add_all(
        [
            Document(
                id=doc1,
                user_id=user_id,
                kb_id=kb_id,
                filename="d1.txt",
                file_type="txt",
                text_path=f"/tmp/{doc1}.txt",
                num_chunks=1,
                num_pages=1,
                char_count=100,
                status="ready",
            ),
            Document(
                id=doc2,
                user_id=user_id,
                kb_id=kb_id,
                filename="d2.txt",
                file_type="txt",
                text_path=f"/tmp/{doc2}.txt",
                num_chunks=1,
                num_pages=1,
                char_count=100,
                status="ready",
            ),
            Keypoint(
                id=rep_id,
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc1,
                text="1. 矩阵定义",
                mastery_level=0.0,
                created_at=base,
            ),
            Keypoint(
                id=dup_id,
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc2,
                text="矩阵定义",
                mastery_level=0.0,
                created_at=base + timedelta(seconds=1),
            ),
        ]
    )
    db_session.commit()

    def _search(question, k, filter):  # noqa: A002
        assert k == 3
        assert filter == build_chroma_eq_filter(type="keypoint", kb_id=kb_id)
        return [
            (SimpleNamespace(metadata={"keypoint_id": dup_id, "doc_id": doc2}), 0.1),
            (SimpleNamespace(metadata={"keypoint_id": rep_id, "doc_id": doc1}), 0.2),
        ]

    vectorstore = SimpleNamespace(similarity_search_with_score=_search)

    with patch("app.routers.qa.get_vectorstore", return_value=vectorstore):
        with patch("app.services.keypoint_dedup.get_vectorstore", side_effect=RuntimeError("no vector")):
            _update_mastery_from_qa(
                db_session,
                user_id=user_id,
                question="什么是矩阵定义？",
                doc_id=None,
                kb_id=kb_id,
            )

    db_session.expire_all()
    rep = db_session.query(Keypoint).filter(Keypoint.id == rep_id).first()
    dup = db_session.query(Keypoint).filter(Keypoint.id == dup_id).first()
    assert rep is not None and dup is not None
    assert float(rep.mastery_level or 0.0) > 0.0
    assert float(dup.mastery_level or 0.0) == pytest.approx(0.0)


def test_update_mastery_from_qa_doc_vector_hits_collapse_to_kb_representative(db_session):
    user_id = "qa_doc_dedup_user"
    kb_id = "qa_doc_dedup_kb"
    doc1 = "qa_doc_dedup_doc1"
    doc2 = "qa_doc_dedup_doc2"
    rep_id = "qa_doc_dedup_kp1"
    dup_id = "qa_doc_dedup_kp2"
    base = datetime.utcnow()

    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="KB"))
    db_session.add_all(
        [
            Document(
                id=doc1,
                user_id=user_id,
                kb_id=kb_id,
                filename="d1.txt",
                file_type="txt",
                text_path=f"/tmp/{doc1}.txt",
                num_chunks=1,
                num_pages=1,
                char_count=100,
                status="ready",
            ),
            Document(
                id=doc2,
                user_id=user_id,
                kb_id=kb_id,
                filename="d2.txt",
                file_type="txt",
                text_path=f"/tmp/{doc2}.txt",
                num_chunks=1,
                num_pages=1,
                char_count=100,
                status="ready",
            ),
            Keypoint(
                id=rep_id,
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc2,
                text="线性变换定义",
                mastery_level=0.0,
                created_at=base,
            ),
            Keypoint(
                id=dup_id,
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc1,
                text="线性变换定义",
                mastery_level=0.0,
                created_at=base + timedelta(seconds=1),
            ),
        ]
    )
    db_session.commit()

    def _search(question, k, filter):  # noqa: A002
        assert k == 3
        assert filter == build_chroma_eq_filter(type="keypoint", doc_id=doc1)
        return [(SimpleNamespace(metadata={"keypoint_id": dup_id, "doc_id": doc1}), 0.1)]

    vectorstore = SimpleNamespace(similarity_search_with_score=_search)

    with patch("app.routers.qa.get_vectorstore", return_value=vectorstore):
        with patch("app.services.keypoint_dedup.get_vectorstore", side_effect=RuntimeError("no vector")):
            _update_mastery_from_qa(
                db_session,
                user_id=user_id,
                question="解释线性变换定义",
                doc_id=doc1,
                kb_id=None,
            )

    db_session.expire_all()
    rep = db_session.query(Keypoint).filter(Keypoint.id == rep_id).first()
    dup = db_session.query(Keypoint).filter(Keypoint.id == dup_id).first()
    assert rep is not None and dup is not None
    assert float(rep.mastery_level or 0.0) > 0.0
    assert float(dup.mastery_level or 0.0) == pytest.approx(0.0)
