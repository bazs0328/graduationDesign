from unittest.mock import patch

from app.models import Document, Keypoint, KnowledgeBase, User
from app.services.learning_path import (
    generate_learning_path,
    invalidate_learning_path_result_cache,
)


def _seed_learning_path_fixture(db_session, *, user_id: str, kb_id: str, doc_id: str):
    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="KB"))
    db_session.add(
        Document(
            id=doc_id,
            user_id=user_id,
            kb_id=kb_id,
            filename="lp.txt",
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
                id=f"{doc_id}-kp-1",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc_id,
                text="概念一",
                explanation="e1",
                mastery_level=0.1,
                attempt_count=0,
                correct_count=0,
            ),
            Keypoint(
                id=f"{doc_id}-kp-2",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc_id,
                text="概念二",
                explanation="e2",
                mastery_level=0.2,
                attempt_count=1,
                correct_count=0,
            ),
        ]
    )
    db_session.commit()


def test_generate_learning_path_result_cache_hits_and_invalidates(db_session):
    user_id = "lp_cache_user_1"
    kb_id = "lp_cache_kb_1"
    doc_id = "lp_cache_doc_1"
    _seed_learning_path_fixture(db_session, user_id=user_id, kb_id=kb_id, doc_id=doc_id)
    invalidate_learning_path_result_cache(None, kb_id)

    stage_calls = {"count": 0}

    def fake_stage_hints(*args, **kwargs):
        stage_calls["count"] += 1
        return {}

    with (
        patch("app.services.learning_path._infer_stage_hints", side_effect=fake_stage_hints),
        patch("app.services.learning_path._infer_milestones", return_value=set()),
    ):
        first = generate_learning_path(db_session, user_id, kb_id, limit=15)
        second = generate_learning_path(db_session, user_id, kb_id, limit=15)

    assert stage_calls["count"] == 1
    assert first[0] and second[0]
    assert first[0] is not second[0]
    assert first[0][0].keypoint_id == second[0][0].keypoint_id

    removed = invalidate_learning_path_result_cache(None, kb_id)
    assert removed >= 1

    with (
        patch("app.services.learning_path._infer_stage_hints", side_effect=fake_stage_hints),
        patch("app.services.learning_path._infer_milestones", return_value=set()),
    ):
        generate_learning_path(db_session, user_id, kb_id, limit=15)

    assert stage_calls["count"] == 2
