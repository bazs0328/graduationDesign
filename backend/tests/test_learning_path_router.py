from unittest.mock import patch

from app.models import Document, Keypoint, KnowledgeBase, User


def _seed_router_fixture(db_session, *, user_id: str, kb_id: str, doc_id: str):
    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="KB"))
    db_session.add(
        Document(
            id=doc_id,
            user_id=user_id,
            kb_id=kb_id,
            filename="lp-router.txt",
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
                explanation=None,
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
                explanation=None,
                mastery_level=0.2,
                attempt_count=0,
                correct_count=0,
            ),
            Keypoint(
                id=f"{doc_id}-kp-3",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc_id,
                text="概念三",
                explanation=None,
                mastery_level=0.3,
                attempt_count=0,
                correct_count=0,
            ),
        ]
    )
    db_session.commit()


def test_learning_path_build_force_keeps_regular_get_available(client, db_session):
    user_id = "lp_router_user"
    kb_id = "lp_router_kb"
    doc_id = "lp_router_doc"
    _seed_router_fixture(db_session, user_id=user_id, kb_id=kb_id, doc_id=doc_id)

    with (
        patch("app.services.learning_path._infer_rule_dependency_edges", return_value=[]),
        patch("app.services.learning_path._invoke_prompt_json", side_effect=RuntimeError("llm down")),
        patch("app.services.learning_path._infer_stage_hints", return_value={}),
        patch("app.services.learning_path._infer_milestones", return_value=set()),
    ):
        first = client.get(f"/api/learning-path?user_id={user_id}&kb_id={kb_id}&limit=20")
        build = client.post(
            f"/api/learning-path/build?user_id={user_id}&kb_id={kb_id}&force=true"
        )
        second = client.get(f"/api/learning-path?user_id={user_id}&kb_id={kb_id}&limit=20")

    assert first.status_code == 200
    assert build.status_code == 200
    assert second.status_code == 200

    first_steps = [item["keypoint_id"] for item in first.json()["items"]]
    second_steps = [item["keypoint_id"] for item in second.json()["items"]]
    assert first_steps == second_steps
    assert isinstance(build.json()["edges_count"], int)
