"""Tests for profile router (GET profile, GET difficulty-plan)."""

from unittest.mock import patch

from app.models import Document, Keypoint, KnowledgeBase, User
from app.services.learner_profile import get_weak_concepts_for_kb


def test_get_profile_returns_200_and_schema(client, seeded_session):
    """GET /api/profile with user_id returns 200 and LearnerProfileOut schema."""
    user_id = seeded_session["user_id"]
    resp = client.get(f"/api/profile?user_id={user_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert data["user_id"] == user_id
    assert "ability_level" in data
    assert data["ability_level"] in ("beginner", "intermediate", "advanced")
    assert "theta" in data
    assert isinstance(data["theta"], (int, float))
    assert "frustration_score" in data
    assert isinstance(data["frustration_score"], (int, float))
    assert "weak_concepts" in data
    assert isinstance(data["weak_concepts"], list)
    assert "recent_accuracy" in data
    assert isinstance(data["recent_accuracy"], (int, float))
    assert "total_attempts" in data
    assert isinstance(data["total_attempts"], int)
    assert "mastery_avg" in data
    assert isinstance(data["mastery_avg"], (int, float))
    assert "mastery_completion_rate" in data
    assert isinstance(data["mastery_completion_rate"], (int, float))
    assert "updated_at" in data


def test_get_profile_creates_default_when_missing(client):
    """GET /api/profile with new user_id creates default profile (200, intermediate, empty weak_concepts)."""
    user_id = "new_user_profile"
    resp = client.get(f"/api/profile?user_id={user_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user_id
    assert data["ability_level"] == "intermediate"
    assert data["weak_concepts"] == []
    assert data["total_attempts"] == 0


def test_get_difficulty_plan_returns_200_and_schema(client, seeded_session):
    """GET /api/profile/difficulty-plan returns 200 and DifficultyPlan (easy, medium, hard sum to 1)."""
    user_id = seeded_session["user_id"]
    resp = client.get(f"/api/profile/difficulty-plan?user_id={user_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "easy" in data
    assert "medium" in data
    assert "hard" in data
    assert isinstance(data["easy"], (int, float))
    assert isinstance(data["medium"], (int, float))
    assert isinstance(data["hard"], (int, float))
    total = data["easy"] + data["medium"] + data["hard"]
    assert abs(total - 1.0) < 1e-6


def test_get_profile_weak_concepts_derive_from_mastery_level(client, db_session, seeded_session):
    """Weak concepts should be selected from low-mastery keypoints, not untouched defaults."""
    user_id = seeded_session["user_id"]
    kb_id = seeded_session["kb_id"]
    doc_id = seeded_session["doc_id"]

    db_session.add(
        Keypoint(
            id="kp-profile-weak-1",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="矩阵求导",
            mastery_level=0.12,
            attempt_count=2,
            correct_count=0,
        )
    )
    db_session.add(
        Keypoint(
            id="kp-profile-weak-2",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="特征值分解",
            mastery_level=0.28,
            attempt_count=1,
            correct_count=0,
        )
    )
    db_session.add(
        Keypoint(
            id="kp-profile-mastered",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="线性变换",
            mastery_level=0.88,
            attempt_count=3,
            correct_count=3,
        )
    )
    db_session.add(
        Keypoint(
            id="kp-profile-untouched",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            text="未学习默认项",
            mastery_level=0.0,
            attempt_count=0,
            correct_count=0,
        )
    )
    db_session.commit()

    resp = client.get(f"/api/profile?user_id={user_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "weak_concepts" in data
    assert "矩阵求导" in data["weak_concepts"]
    assert "特征值分解" in data["weak_concepts"]
    assert "线性变换" not in data["weak_concepts"]
    assert "未学习默认项" not in data["weak_concepts"]


def test_get_weak_concepts_for_kb_filters_untouched_and_deduplicates(db_session):
    user_id = "weak_kb_user"
    kb_id = "weak_kb_1"
    doc_id = "weak_doc_1"
    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="KB"))
    db_session.add(
        Document(
            id=doc_id,
            user_id=user_id,
            kb_id=kb_id,
            filename="weak.txt",
            file_type="txt",
            text_path=f"/tmp/{doc_id}.txt",
            num_chunks=1,
            num_pages=1,
            char_count=100,
            status="ready",
        )
    )
    db_session.add_all(
        [
            Keypoint(
                id="weak-kp-1",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc_id,
                text="同名概念",
                mastery_level=0.05,
                attempt_count=2,
                correct_count=0,
            ),
            Keypoint(
                id="weak-kp-2",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc_id,
                text="同名概念",
                mastery_level=0.05,
                attempt_count=5,
                correct_count=0,
            ),
            Keypoint(
                id="weak-kp-3",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc_id,
                text="次弱概念",
                mastery_level=0.2,
                attempt_count=1,
                correct_count=0,
            ),
            Keypoint(
                id="weak-kp-4",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc_id,
                text="未学习默认项",
                mastery_level=0.0,
                attempt_count=0,
                correct_count=0,
            ),
            Keypoint(
                id="weak-kp-5",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc_id,
                text="已掌握概念",
                mastery_level=0.9,
                attempt_count=3,
                correct_count=3,
            ),
        ]
    )
    db_session.commit()

    weak = get_weak_concepts_for_kb(db_session, user_id, kb_id, limit=10)

    assert weak == ["同名概念", "次弱概念"]
    assert "未学习默认项" not in weak
    assert "已掌握概念" not in weak


def test_get_profile_mastery_metrics_use_aggregate_keypoints(client, db_session):
    user_id = "profile_agg_user"
    kb_id = "profile_agg_kb"
    doc1 = "profile-aggregate-doc-1"
    doc2 = "profile-aggregate-doc-2"

    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="KB"))
    db_session.add(
        Document(
            id=doc1,
            user_id=user_id,
            kb_id=kb_id,
            filename="profile-aggregate-1.txt",
            file_type="txt",
            text_path=f"/tmp/{doc1}.txt",
            num_chunks=1,
            num_pages=1,
            char_count=100,
            status="ready",
        )
    )
    db_session.add(
        Document(
            id=doc2,
            user_id=user_id,
            kb_id=kb_id,
            filename="profile-aggregate-2.txt",
            file_type="txt",
            text_path=f"/tmp/{doc2}.txt",
            num_chunks=1,
            num_pages=1,
            char_count=100,
            status="ready",
        )
    )
    db_session.add_all(
        [
            Keypoint(
                id="kp-profile-agg-1",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc1,
                text="聚合概念A",
                mastery_level=0.0,
                attempt_count=1,
                correct_count=0,
            ),
            Keypoint(
                id="kp-profile-agg-2",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc2,
                text="聚合概念A",
                mastery_level=0.9,
                attempt_count=3,
                correct_count=3,
            ),
            Keypoint(
                id="kp-profile-agg-3",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc1,
                text="聚合概念B",
                mastery_level=0.1,
                attempt_count=1,
                correct_count=0,
            ),
        ]
    )
    db_session.commit()

    with patch("app.services.keypoint_dedup.get_vectorstore", side_effect=RuntimeError("no vector")):
        resp = client.get(f"/api/profile?user_id={user_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert float(data["mastery_avg"]) == 0.5
    assert float(data["mastery_completion_rate"]) == 0.5
