"""Tests for profile router (GET profile, GET difficulty-plan)."""


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
