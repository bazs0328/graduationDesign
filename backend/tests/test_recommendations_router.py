"""Tests for recommendations router (stateful recommendations + next step)."""

import json
from unittest.mock import patch

from app.models import (
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
from app.schemas import LearningPathItem


def _seed_user_kb_doc(db_session, *, user_id: str, kb_id: str, doc_id: str, filename: str):
    db_session.add(
        User(
            id=user_id,
            username=user_id,
            password_hash="test_hash",
            name="Test User",
        )
    )
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name=f"KB-{kb_id}"))
    db_session.add(
        Document(
            id=doc_id,
            user_id=user_id,
            kb_id=kb_id,
            filename=filename,
            file_type="txt",
            text_path=f"/tmp/{doc_id}.txt",
            num_chunks=1,
            num_pages=1,
            char_count=120,
            status="ready",
        )
    )


def test_recommendations_blocked_doc_has_next_step(client, db_session):
    user_id = "rec_user_blocked"
    kb_id = "rec_kb_blocked"
    doc_id = "rec_doc_blocked"
    _seed_user_kb_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        filename="blocked.txt",
    )
    db_session.commit()

    with patch("app.routers.recommendations.generate_learning_path", return_value=([], [], [], [], {})):
        resp = client.get(
            f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["generated_at"]
    assert data["items"]
    item = data["items"][0]
    assert item["doc_id"] == doc_id
    assert item["status"] == "blocked"
    assert item["primary_action"]["type"] == "summary"
    assert item["primary_action"]["priority"] >= 90
    assert item["urgency_score"] >= 60
    assert data["next_step"]["doc_id"] == doc_id
    assert data["next_step"]["action"]["type"] == "summary"


def test_recommendations_ready_for_practice_prioritizes_initial_quiz(client, db_session):
    user_id = "rec_user_ready_practice"
    kb_id = "rec_kb_ready_practice"
    doc_id = "rec_doc_ready_practice"
    _seed_user_kb_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        filename="ready-practice.txt",
    )

    db_session.add(
        SummaryRecord(
            id="sum-ready-practice",
            user_id=user_id,
            doc_id=doc_id,
            summary_text="summary",
        )
    )
    db_session.add(
        KeypointRecord(
            id="kp-ready-practice-record",
            user_id=user_id,
            doc_id=doc_id,
            points_json='["A","B"]',
        )
    )
    db_session.add(
        Keypoint(
            id="kp-ready-practice-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="牛顿第二定律",
            explanation="e1",
            mastery_level=0.2,
            attempt_count=0,
            correct_count=0,
        )
    )
    db_session.commit()

    with patch("app.routers.recommendations.generate_learning_path", return_value=([], [], [], [], {})):
        resp = client.get(
            f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5"
        )

    assert resp.status_code == 200
    data = resp.json()
    item = data["items"][0]
    assert item["status"] == "ready_for_practice"
    actions = {action["type"]: action for action in item["actions"]}
    assert "review" in actions
    assert "quiz" in actions
    assert actions["quiz"]["priority"] > actions["review"]["priority"]
    assert item["primary_action"]["type"] == "quiz"
    assert data["next_step"]["action"]["type"] == "quiz"


def test_recommendations_need_practice_include_review_and_quiz(client, db_session):
    user_id = "rec_user_practice"
    kb_id = "rec_kb_practice"
    doc_id = "rec_doc_practice"
    _seed_user_kb_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        filename="practice.txt",
    )

    db_session.add(
        SummaryRecord(
            id="sum-practice",
            user_id=user_id,
            doc_id=doc_id,
            summary_text="summary",
        )
    )
    db_session.add(
        KeypointRecord(
            id="kp-practice-record",
            user_id=user_id,
            doc_id=doc_id,
            points_json='["A","B"]',
        )
    )
    db_session.add(
        Keypoint(
            id="kp-practice-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="链式法则",
            explanation="e1",
            mastery_level=0.25,
            attempt_count=1,
            correct_count=0,
        )
    )
    db_session.add(
        Keypoint(
            id="kp-practice-2",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="极限定义",
            explanation="e2",
            mastery_level=0.5,
            attempt_count=1,
            correct_count=1,
        )
    )
    db_session.add(
        Quiz(
            id="quiz-practice-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            difficulty="medium",
            question_type="mcq",
            questions_json="[]",
        )
    )
    db_session.add(
        QuizAttempt(
            id="attempt-practice-1",
            user_id=user_id,
            quiz_id="quiz-practice-1",
            answers_json="[0,1]",
            score=0.4,
            total=2,
        )
    )
    db_session.commit()

    with patch("app.routers.recommendations.generate_learning_path", return_value=([], [], [], [], {})):
        resp = client.get(
            f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5"
        )

    assert resp.status_code == 200
    data = resp.json()
    item = data["items"][0]
    assert item["status"] == "needs_practice"
    assert item["completion_score"] > 0

    actions = {action["type"]: action for action in item["actions"]}
    assert "review" in actions
    assert "quiz" in actions
    assert "qa" in actions
    assert actions["review"]["params"]["focus_concepts"]
    assert actions["quiz"]["params"]["difficulty"] in ("easy", "medium")


def test_recommendations_ready_for_challenge_prioritizes_challenge(client, db_session):
    user_id = "rec_user_challenge"
    kb_id = "rec_kb_challenge"
    doc_id = "rec_doc_challenge"
    _seed_user_kb_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        filename="challenge.txt",
    )

    db_session.add(
        SummaryRecord(
            id="sum-challenge",
            user_id=user_id,
            doc_id=doc_id,
            summary_text="summary",
        )
    )
    db_session.add(
        KeypointRecord(
            id="kp-challenge-record",
            user_id=user_id,
            doc_id=doc_id,
            points_json='["A","B"]',
        )
    )
    db_session.add(
        Keypoint(
            id="kp-challenge-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="矩阵求导",
            explanation="e1",
            mastery_level=0.9,
            attempt_count=3,
            correct_count=3,
        )
    )
    db_session.add(
        Keypoint(
            id="kp-challenge-2",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="特征分解",
            explanation="e2",
            mastery_level=0.85,
            attempt_count=3,
            correct_count=3,
        )
    )
    db_session.add(
        Quiz(
            id="quiz-challenge-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            difficulty="medium",
            question_type="mcq",
            questions_json="[]",
        )
    )
    db_session.add(
        Quiz(
            id="quiz-challenge-2",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            difficulty="medium",
            question_type="mcq",
            questions_json="[]",
        )
    )
    db_session.add(
        QuizAttempt(
            id="attempt-challenge-1",
            user_id=user_id,
            quiz_id="quiz-challenge-1",
            answers_json="[0,1]",
            score=0.9,
            total=2,
        )
    )
    db_session.add(
        QuizAttempt(
            id="attempt-challenge-2",
            user_id=user_id,
            quiz_id="quiz-challenge-2",
            answers_json="[0,1]",
            score=0.95,
            total=2,
        )
    )
    db_session.add(
        QARecord(
            id="qa-challenge-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            question="Q",
            answer="A",
        )
    )
    db_session.commit()

    with patch("app.routers.recommendations.generate_learning_path", return_value=([], [], [], [], {})):
        resp = client.get(
            f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5"
        )

    assert resp.status_code == 200
    data = resp.json()
    item = data["items"][0]
    assert item["status"] == "ready_for_challenge"
    assert item["primary_action"]["type"] == "challenge"
    challenge = next(action for action in item["actions"] if action["type"] == "challenge")
    assert challenge["params"]["difficulty"] in ("medium", "hard")


def test_recommendations_can_skip_learning_path_for_fast_first_paint(client, db_session):
    user_id = "rec_user_skip_lp"
    kb_id = "rec_kb_skip_lp"
    doc_id = "rec_doc_skip_lp"
    _seed_user_kb_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        filename="skip-lp.txt",
    )
    db_session.add(
        SummaryRecord(
            id="sum-skip-lp",
            user_id=user_id,
            doc_id=doc_id,
            summary_text="summary",
        )
    )
    db_session.add(
        KeypointRecord(
            id="kp-skip-lp-record",
            user_id=user_id,
            doc_id=doc_id,
            points_json='["A","B"]',
        )
    )
    db_session.add(
        Keypoint(
            id="kp-skip-lp-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="概念一",
            explanation="e1",
            mastery_level=0.2,
            attempt_count=0,
            correct_count=0,
        )
    )
    db_session.commit()

    with patch("app.routers.recommendations.generate_learning_path") as path_mock:
        resp = client.get(
            f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5&include_learning_path=false"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["items"]
    assert data["learning_path"] == []
    assert data["learning_path_edges"] == []
    assert data["learning_path_stages"] == []
    assert data["learning_path_modules"] == []
    assert data["learning_path_summary"] == {}
    path_mock.assert_not_called()


def test_recommendations_are_independent_from_learning_path_focus(client, db_session):
    user_id = "rec_user_decouple"
    kb_id = "rec_kb_decouple"
    doc_id = "rec_doc_decouple"
    _seed_user_kb_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        filename="decouple.txt",
    )
    db_session.add(
        SummaryRecord(
            id="sum-decouple",
            user_id=user_id,
            doc_id=doc_id,
            summary_text="summary",
        )
    )
    db_session.add(
        KeypointRecord(
            id="kp-decouple-record",
            user_id=user_id,
            doc_id=doc_id,
            points_json='["A"]',
        )
    )
    db_session.add(
        Keypoint(
            id="kp-decouple-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="掌握概念",
            explanation="e1",
            mastery_level=0.92,
            attempt_count=2,
            correct_count=2,
        )
    )
    db_session.commit()

    fake_learning_path = [
        LearningPathItem(
            keypoint_id="lp-decouple-1",
            text="路径概念",
            doc_id=doc_id,
            doc_name="decouple.txt",
            mastery_level=0.3,
            priority="high",
        )
    ]
    with (
        patch("app.routers.recommendations.get_weak_concepts_for_kb", return_value=[]),
        patch(
            "app.routers.recommendations.generate_learning_path",
            return_value=(fake_learning_path, [], [], [], {}),
        ),
    ):
        with_path_resp = client.get(
            f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5&include_learning_path=true"
        )
        without_path_resp = client.get(
            f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5&include_learning_path=false"
        )

    assert with_path_resp.status_code == 200
    assert without_path_resp.status_code == 200

    with_path_data = with_path_resp.json()
    without_path_data = without_path_resp.json()
    with_item = with_path_data["items"][0]
    without_item = without_path_data["items"][0]

    assert with_path_data["learning_path"]
    assert without_path_data["learning_path"] == []
    assert with_item["status"] == without_item["status"]
    assert with_item["summary"] == without_item["summary"]
    assert with_item["primary_action"]["type"] == without_item["primary_action"]["type"]
    assert [action["type"] for action in with_item["actions"]] == [
        action["type"] for action in without_item["actions"]
    ]
    assert "review" not in {action["type"] for action in with_item["actions"]}
    quiz_with_path = next(
        action for action in with_item["actions"] if action["type"] == "quiz"
    )
    quiz_without_path = next(
        action for action in without_item["actions"] if action["type"] == "quiz"
    )
    assert quiz_with_path["params"] == quiz_without_path["params"]


def test_recommendations_learning_path_cache_invalidates_after_build_force(client, db_session):
    user_id = "rec_user_cache"
    kb_id = "rec_kb_cache"
    doc_id = "rec_doc_cache"
    _seed_user_kb_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        filename="cache.txt",
    )
    db_session.add(
        Keypoint(
            id="kp-cache-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="概念一",
            explanation="e1",
            mastery_level=0.2,
            attempt_count=0,
            correct_count=0,
        )
    )
    db_session.add(
        Keypoint(
            id="kp-cache-2",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="概念二",
            explanation="e2",
            mastery_level=0.4,
            attempt_count=1,
            correct_count=1,
        )
    )
    db_session.commit()

    stage_calls = {"count": 0}

    def fake_stage_hints(*args, **kwargs):
        stage_calls["count"] += 1
        return {}

    with (
        patch("app.services.learning_path._infer_stage_hints", side_effect=fake_stage_hints),
        patch("app.services.learning_path._infer_milestones", return_value=set()),
    ):
        first = client.get(f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5")
        second = client.get(f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5")
        build = client.post(
            f"/api/learning-path/build?user_id={user_id}&kb_id={kb_id}&force=true"
        )
        third = client.get(f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5")

    assert first.status_code == 200
    assert second.status_code == 200
    assert build.status_code == 200
    assert third.status_code == 200
    assert stage_calls["count"] == 2


def test_recommendations_uses_kb_weak_concepts_without_aggregate_call(client, db_session):
    user_id = "rec_user_kb_weak"
    kb_id = "rec_kb_kb_weak"
    doc_id = "rec_doc_kb_weak"
    _seed_user_kb_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        filename="kb-weak.txt",
    )
    db_session.add(
        SummaryRecord(
            id="sum-kb-weak",
            user_id=user_id,
            doc_id=doc_id,
            summary_text="summary",
        )
    )
    db_session.add(
        KeypointRecord(
            id="kp-kb-weak-record",
            user_id=user_id,
            doc_id=doc_id,
            points_json='["A"]',
        )
    )
    db_session.add(
        Keypoint(
            id="kp-kb-weak-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="已存在概念",
            explanation="e1",
            mastery_level=0.7,
            attempt_count=1,
            correct_count=1,
        )
    )
    db_session.commit()

    with (
        patch(
            "app.services.aggregate_mastery.list_kb_aggregate_mastery_points"
        ) as aggregate_mock,
        patch("app.routers.recommendations.get_weak_concepts_for_kb", return_value=["外部薄弱点"]) as weak_mock,
        patch("app.routers.recommendations.generate_learning_path", return_value=([], [], [], [], {})),
    ):
        resp = client.get(
            f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5"
        )

    assert resp.status_code == 200
    data = resp.json()
    item = data["items"][0]
    actions = {action["type"]: action for action in item["actions"]}
    assert "review" in actions
    assert "外部薄弱点" in actions["review"]["params"]["focus_concepts"]
    weak_mock.assert_called_once()
    assert weak_mock.call_args.args[1:] == (user_id, kb_id)
    assert aggregate_mock.call_count == 0


def test_recommendations_learning_path_cache_survives_quiz_and_qa_updates(client, db_session):
    user_id = "rec_user_cache_warm"
    kb_id = "rec_kb_cache_warm"
    doc_id = "rec_doc_cache_warm"
    _seed_user_kb_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        filename="cache-warm.txt",
    )
    db_session.add(
        Keypoint(
            id="kp-cache-warm-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="概念一",
            explanation="e1",
            mastery_level=0.2,
            attempt_count=0,
            correct_count=0,
        )
    )
    db_session.add(
        Keypoint(
            id="kp-cache-warm-2",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="概念二",
            explanation="e2",
            mastery_level=0.4,
            attempt_count=1,
            correct_count=1,
        )
    )
    db_session.add(
        Quiz(
            id="quiz-cache-warm-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            difficulty="medium",
            question_type="mcq",
            questions_json=json.dumps(
                [
                    {
                        "question": "q1",
                        "options": ["A", "B", "C", "D"],
                        "answer_index": 0,
                        "explanation": "e1",
                        "concepts": ["概念一"],
                        "keypoint_ids": ["kp-cache-warm-1"],
                        "primary_keypoint_id": "kp-cache-warm-1",
                    }
                ]
            ),
        )
    )
    db_session.commit()

    stage_calls = {"count": 0}

    def fake_stage_hints(*args, **kwargs):
        stage_calls["count"] += 1
        return {}

    with (
        patch("app.services.learning_path._infer_stage_hints", side_effect=fake_stage_hints),
        patch("app.services.learning_path._infer_milestones", return_value=set()),
    ):
        first = client.get(f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5")
        second = client.get(f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5")

        submit = client.post(
            "/api/quiz/submit",
            json={
                "quiz_id": "quiz-cache-warm-1",
                "user_id": user_id,
                "answers": [0],
            },
        )
        third = client.get(f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5")

        with (
            patch(
                "app.routers.qa.prepare_qa_answer",
                return_value={
                    "no_results": True,
                    "sources": [],
                    "formatted_messages": None,
                    "retrieved_count": 0,
                    "mode": "normal",
                },
            ),
            patch("app.routers.qa._update_mastery_from_qa"),
        ):
            qa_resp = client.post(
                "/api/qa",
                json={
                    "doc_id": doc_id,
                    "user_id": user_id,
                    "question": "这是什么概念？",
                },
            )
        fourth = client.get(f"/api/recommendations?user_id={user_id}&kb_id={kb_id}&limit=5")

    assert first.status_code == 200
    assert second.status_code == 200
    assert submit.status_code == 200
    assert third.status_code == 200
    assert qa_resp.status_code == 200
    assert fourth.status_code == 200
    assert stage_calls["count"] == 1
