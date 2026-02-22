"""Tests for QA router."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from app.models import ChatMessage


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
