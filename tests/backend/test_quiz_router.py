"""Tests for quiz router (generate + submit, including mimic style/reference)."""
from unittest.mock import patch

import pytest


def _mock_generate_quiz(*args, **kwargs):
    """Return a fixed list of questions in the expected schema."""
    return [
        {
            "question": "Mock question 1?",
            "options": ["A", "B", "C", "D"],
            "answer_index": 0,
            "explanation": "Mock explanation 1",
        },
        {
            "question": "Mock question 2?",
            "options": ["W", "X", "Y", "Z"],
            "answer_index": 1,
            "explanation": "Mock explanation 2",
        },
    ]


def test_quiz_generate_requires_at_least_one_input(client):
    """POST /api/quiz/generate without doc_id, reference_questions, or style_prompt returns 400."""
    resp = client.post(
        "/api/quiz/generate",
        json={"count": 3, "difficulty": "medium", "user_id": "u1"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "detail" in data
    assert "doc_id" in data["detail"] or "reference_questions" in data["detail"] or "style_prompt" in data["detail"]


def test_quiz_generate_with_doc_id_success(client, seeded_session):
    """POST /api/quiz/generate with doc_id returns quiz_id and questions (mocked)."""
    with patch("app.routers.quiz.generate_quiz", side_effect=_mock_generate_quiz):
        resp = client.post(
            "/api/quiz/generate",
            json={
                "doc_id": seeded_session["doc_id"],
                "user_id": seeded_session["user_id"],
                "count": 2,
                "difficulty": "easy",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "quiz_id" in data
    assert data["quiz_id"]
    assert "questions" in data
    assert len(data["questions"]) == 2
    for q in data["questions"]:
        assert "question" in q and "options" in q and "answer_index" in q and "explanation" in q
        assert len(q["options"]) == 4


def test_quiz_generate_with_style_prompt_only(client, seeded_session):
    """POST /api/quiz/generate with only style_prompt (no doc_id) returns quiz (mocked)."""
    with patch("app.routers.quiz.generate_quiz", side_effect=_mock_generate_quiz):
        resp = client.post(
            "/api/quiz/generate",
            json={
                "user_id": seeded_session["user_id"],
                "count": 2,
                "difficulty": "medium",
                "style_prompt": "High school math multiple-choice style.",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["quiz_id"]
    assert len(data["questions"]) == 2


def test_quiz_generate_with_reference_questions_only(client, seeded_session):
    """POST /api/quiz/generate with only reference_questions returns quiz (mocked)."""
    with patch("app.routers.quiz.generate_quiz", side_effect=_mock_generate_quiz):
        resp = client.post(
            "/api/quiz/generate",
            json={
                "user_id": seeded_session["user_id"],
                "count": 2,
                "difficulty": "hard",
                "reference_questions": "1. What is 2+2? (A) 3 (B) 4 (C) 5 (D) 6\n2. What is 3*3? ...",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["quiz_id"]
    assert len(data["questions"]) == 2


def test_quiz_generate_doc_id_plus_style_prompt(client, seeded_session):
    """POST /api/quiz/generate with doc_id and style_prompt returns quiz (mocked)."""
    with patch("app.routers.quiz.generate_quiz", side_effect=_mock_generate_quiz):
        resp = client.post(
            "/api/quiz/generate",
            json={
                "doc_id": seeded_session["doc_id"],
                "user_id": seeded_session["user_id"],
                "count": 2,
                "style_prompt": "Exam-style wording.",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["quiz_id"]
    assert len(data["questions"]) == 2


def test_quiz_submit_after_generate(client, seeded_session):
    """Generate quiz (mocked), then submit; response has score/results/explanations."""
    with patch("app.routers.quiz.generate_quiz", side_effect=_mock_generate_quiz):
        gen = client.post(
            "/api/quiz/generate",
            json={
                "doc_id": seeded_session["doc_id"],
                "user_id": seeded_session["user_id"],
                "count": 2,
                "difficulty": "easy",
            },
        )
    assert gen.status_code == 200
    quiz_id = gen.json()["quiz_id"]
    submit = client.post(
        "/api/quiz/submit",
        json={
            "quiz_id": quiz_id,
            "user_id": seeded_session["user_id"],
            "answers": [0, 1],
        },
    )
    assert submit.status_code == 200
    sub = submit.json()
    assert "score" in sub
    assert sub["correct"] in (0, 1, 2)
    assert sub["total"] == 2
    assert len(sub["results"]) == 2
    assert len(sub["explanations"]) == 2


def test_quiz_generate_with_nonexistent_doc_returns_404(client, seeded_session):
    """POST /api/quiz/generate with invalid doc_id returns 404."""
    resp = client.post(
        "/api/quiz/generate",
        json={
            "doc_id": "nonexistent-doc-id",
            "user_id": seeded_session["user_id"],
            "count": 2,
        },
    )
    assert resp.status_code == 404
    assert "detail" in resp.json()
