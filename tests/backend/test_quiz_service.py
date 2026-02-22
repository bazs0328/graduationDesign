"""Tests for quiz service quality guardrails."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services.quiz import _apply_quality_guardrails, generate_quiz


def test_quality_guardrails_filter_invalid_duplicates_and_concept_overload():
    raw_questions = [
        {
            "question": "什么是矩阵？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 0,
            "explanation": "解释1",
            "concepts": ["矩阵"],
        },
        {
            "question": "什么是矩阵？ ",  # exact duplicate after normalization
            "options": ["A", "B", "C", "D"],
            "answer_index": 1,
            "explanation": "解释2",
            "concepts": ["矩阵"],
        },
        {
            "question": "矩阵的定义是？",
            "options": ["A", "A", "C", "D"],  # invalid duplicate options
            "answer_index": 0,
            "explanation": "解释3",
            "concepts": ["矩阵"],
        },
        {
            "question": "矩阵的秩表示什么？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 2,
            "explanation": "解释4",
            "concepts": ["矩阵"],
        },
        {
            "question": "矩阵乘法满足什么条件？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 3,
            "explanation": "解释5",
            "concepts": ["矩阵"],
        },
        {
            "question": "矩阵转置有什么性质？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 0,
            "explanation": "解释6",
            "concepts": ["矩阵"],
        },
        {
            "question": "特征值的定义是什么？",
            "options": ["A", "B", "C", "D"],
            "answer_index": 1,
            "explanation": "解释7",
            "concepts": ["特征值"],
        },
    ]

    kept, report = _apply_quality_guardrails(
        raw_questions,
        target_count=5,
        focus_concepts=None,
    )

    assert len(kept) >= 3
    assert report["dropped_duplicate_exact"] >= 1
    assert report["dropped_invalid"] >= 1
    assert report["dropped_concept_overload"] >= 1
    assert any(q["question"] == "特征值的定义是什么？" for q in kept)


def test_generate_quiz_resamples_once_when_guardrails_reduce_count():
    first_round = [
        {
            "question": "题目1",
            "options": ["A", "B", "C", "D"],
            "answer_index": 0,
            "explanation": "解析1",
            "concepts": ["概念A"],
        },
        {
            "question": "题目1",  # duplicate
            "options": ["A", "B", "C", "D"],
            "answer_index": 1,
            "explanation": "解析2",
            "concepts": ["概念A"],
        },
        {
            "question": "题目3",
            "options": ["A", "B", "C"],  # invalid options length
            "answer_index": 1,
            "explanation": "解析3",
            "concepts": ["概念B"],
        },
    ]
    second_round = [
        {
            "question": "题目2",
            "options": ["A", "B", "C", "D"],
            "answer_index": 1,
            "explanation": "解析2",
            "concepts": ["概念B"],
        },
        {
            "question": "题目3",
            "options": ["A", "B", "C", "D"],
            "answer_index": 2,
            "explanation": "解析3",
            "concepts": ["概念C"],
        },
    ]

    llm = Mock()
    llm.invoke.side_effect = [
        SimpleNamespace(content=json.dumps(first_round, ensure_ascii=False)),
        SimpleNamespace(content=json.dumps(second_round, ensure_ascii=False)),
    ]

    with (
        patch("app.services.quiz._build_context", return_value=("mock context", ["kp-1"])),
        patch("app.services.quiz.get_llm", return_value=llm),
    ):
        questions = generate_quiz(
            user_id="u1",
            doc_id=None,
            kb_id="kb-1",
            count=3,
            difficulty="medium",
        )

    assert len(questions) == 3
    assert llm.invoke.call_count == 2
    stems = [q["question"] for q in questions]
    assert stems == ["题目1", "题目2", "题目3"]
    assert all(q.get("keypoint_ids") == ["kp-1"] for q in questions)
