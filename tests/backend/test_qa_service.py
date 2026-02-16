"""Tests for adaptive QA prompt behavior."""

from app.services.qa import build_adaptive_system_prompt


def test_adaptive_system_prompt_differs_by_ability_level():
    """Different ability levels should produce clearly different prompts."""
    beginner_prompt = build_adaptive_system_prompt(ability_level="beginner")
    advanced_prompt = build_adaptive_system_prompt(ability_level="advanced")

    assert beginner_prompt != advanced_prompt
    assert "初学者" in beginner_prompt
    assert "高水平学习者" in advanced_prompt


def test_adaptive_system_prompt_includes_weak_concepts():
    """Weak concepts should be included in system prompt hints."""
    prompt = build_adaptive_system_prompt(
        ability_level="intermediate",
        weak_concepts=["矩阵", "特征值"],
    )

    assert "薄弱知识点" in prompt
    assert "矩阵" in prompt
    assert "特征值" in prompt
