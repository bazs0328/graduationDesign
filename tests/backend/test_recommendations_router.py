"""Tests for recommendations router (stateful recommendations + next step)."""

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
