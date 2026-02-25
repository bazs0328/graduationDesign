from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import Document, Keypoint, KnowledgeBase, User
from app.services.learning_path import (
    build_dependency_graph,
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


def _seed_multi_doc_duplicate_fixture(db_session, *, user_id: str, kb_id: str):
    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="KB"))
    doc1 = f"{kb_id}_doc_1"
    doc2 = f"{kb_id}_doc_2"
    rep_id = f"{kb_id}_kp_1"
    duplicate_member_id = f"{kb_id}_kp_2"
    other_id = f"{kb_id}_kp_3"
    db_session.add_all(
        [
            Document(
                id=doc1,
                user_id=user_id,
                kb_id=kb_id,
                filename="doc1.txt",
                file_type="txt",
                text_path=f"/tmp/{doc1}.txt",
                num_chunks=1,
                num_pages=1,
                char_count=100,
                status="ready",
            ),
            Document(
                id=doc2,
                user_id=user_id,
                kb_id=kb_id,
                filename="doc2.txt",
                file_type="txt",
                text_path=f"/tmp/{doc2}.txt",
                num_chunks=1,
                num_pages=1,
                char_count=100,
                status="ready",
            ),
        ]
    )
    base = datetime.utcnow()
    db_session.add_all(
        [
            Keypoint(
                id=rep_id,
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc1,
                text="1. 矩阵定义",
                explanation=None,
                mastery_level=0.1,
                attempt_count=1,
                correct_count=0,
                created_at=base,
            ),
            Keypoint(
                id=duplicate_member_id,
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc2,
                text="矩阵定义",
                explanation="矩阵基础概念",
                mastery_level=0.8,
                attempt_count=3,
                correct_count=2,
                created_at=base + timedelta(seconds=1),
            ),
            Keypoint(
                id=other_id,
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc2,
                text="特征值定义",
                explanation="e3",
                mastery_level=0.2,
                attempt_count=1,
                correct_count=0,
                created_at=base + timedelta(seconds=2),
            ),
        ]
    )
    db_session.commit()
    return {
        "doc1": doc1,
        "doc2": doc2,
        "rep_id": rep_id,
        "duplicate_member_id": duplicate_member_id,
        "other_id": other_id,
    }


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


def test_generate_learning_path_deduplicates_multi_doc_keypoints(db_session):
    user_id = "lp_dedup_user_1"
    kb_id = "lp_dedup_kb_1"
    fixture = _seed_multi_doc_duplicate_fixture(db_session, user_id=user_id, kb_id=kb_id)
    invalidate_learning_path_result_cache(None, kb_id)

    with (
        patch("app.services.keypoint_dedup.get_vectorstore", side_effect=RuntimeError("no vector")),
        patch("app.services.learning_path._invoke_prompt_json", side_effect=RuntimeError("llm down")),
        patch("app.services.learning_path._infer_stage_hints", return_value={}),
        patch("app.services.learning_path._infer_milestones", return_value=set()),
    ):
        items, edges, stages, modules, summary = generate_learning_path(
            db_session, user_id, kb_id, limit=10, force=True
        )

    assert len(items) == 2  # 3 raw keypoints -> 2 after KB dedup
    assert len(edges) == 1
    assert stages
    assert modules
    assert summary["total_items"] == 2

    merged_item = next(item for item in items if item.keypoint_id == fixture["rep_id"])
    assert merged_item.member_count == 2
    assert set(merged_item.source_doc_ids) == {fixture["doc1"], fixture["doc2"]}
    assert set(merged_item.source_doc_names) == {"doc1.txt", "doc2.txt"}
    assert merged_item.mastery_level == 0.8


def test_build_dependency_graph_uses_representative_ids_after_dedup(db_session):
    user_id = "lp_dedup_user_2"
    kb_id = "lp_dedup_kb_2"
    fixture = _seed_multi_doc_duplicate_fixture(db_session, user_id=user_id, kb_id=kb_id)

    with (
        patch("app.services.keypoint_dedup.get_vectorstore", side_effect=RuntimeError("no vector")),
        patch("app.services.learning_path._invoke_prompt_json", side_effect=RuntimeError("llm down")),
    ):
        deps = build_dependency_graph(db_session, user_id, kb_id, force=True)

    assert len(deps) == 1
    dep = deps[0]
    assert dep.from_keypoint_id == fixture["rep_id"]
    assert dep.to_keypoint_id == fixture["other_id"]
    assert fixture["duplicate_member_id"] not in {dep.from_keypoint_id, dep.to_keypoint_id}
