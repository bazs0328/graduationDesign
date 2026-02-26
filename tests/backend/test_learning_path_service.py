from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import Document, Keypoint, KeypointDependency, KnowledgeBase, User
from app.services import learning_path as learning_path_service
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


def _seed_single_doc_three_keypoints_fixture(db_session, *, user_id: str, kb_id: str, doc_id: str):
    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="KB"))
    db_session.add(
        Document(
            id=doc_id,
            user_id=user_id,
            kb_id=kb_id,
            filename="single.txt",
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
                text="1. 矩阵定义",
                explanation="基础概念",
                mastery_level=0.05,
                attempt_count=0,
                correct_count=0,
            ),
            Keypoint(
                id=f"{doc_id}-kp-2",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc_id,
                text="2. 特征值定义",
                explanation="依赖矩阵定义",
                mastery_level=0.15,
                attempt_count=0,
                correct_count=0,
            ),
            Keypoint(
                id=f"{doc_id}-kp-3",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc_id,
                text="3. 特征值应用",
                explanation="应用题",
                mastery_level=0.2,
                attempt_count=1,
                correct_count=0,
            ),
        ]
    )
    db_session.commit()


def _seed_single_doc_nonoverlap_fixture(db_session, *, user_id: str, kb_id: str, doc_id: str):
    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="KB"))
    db_session.add(
        Document(
            id=doc_id,
            user_id=user_id,
            kb_id=kb_id,
            filename="single.txt",
            file_type="txt",
            text_path=f"/tmp/{doc_id}.txt",
            num_chunks=1,
            num_pages=1,
            char_count=100,
            status="ready",
        )
    )
    for idx, text in enumerate(["alpha", "beta", "gamma"], start=1):
        db_session.add(
            Keypoint(
                id=f"{doc_id}-kp-{idx}",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc_id,
                text=text,
                explanation=None,
                mastery_level=0.1,
                attempt_count=0,
                correct_count=0,
            )
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


def test_build_dependency_graph_single_doc_uses_llm_edges_not_sequential(db_session):
    user_id = "lp_single_llm_user"
    kb_id = "lp_single_llm_kb"
    doc_id = "lp_single_llm_doc"
    _seed_single_doc_three_keypoints_fixture(db_session, user_id=user_id, kb_id=kb_id, doc_id=doc_id)

    with (
        patch("app.services.learning_path._infer_rule_dependency_edges", return_value=[]),
        patch(
            "app.services.learning_path._invoke_prompt_json",
            return_value={
                "edges": [
                    {"from_id": f"{doc_id}-kp-1", "to_id": f"{doc_id}-kp-3"},
                ]
            },
        ),
    ):
        deps = build_dependency_graph(db_session, user_id, kb_id, force=True)

    assert len(deps) == 1
    assert deps[0].from_keypoint_id == f"{doc_id}-kp-1"
    assert deps[0].to_keypoint_id == f"{doc_id}-kp-3"
    assert deps[0].relation == learning_path_service.DEPENDENCY_RELATION


def test_build_dependency_graph_single_doc_llm_failure_does_not_fallback_to_sequential(db_session):
    user_id = "lp_single_fail_user"
    kb_id = "lp_single_fail_kb"
    doc_id = "lp_single_fail_doc"
    _seed_single_doc_nonoverlap_fixture(db_session, user_id=user_id, kb_id=kb_id, doc_id=doc_id)

    with patch("app.services.learning_path._invoke_prompt_json", side_effect=RuntimeError("llm down")):
        deps = build_dependency_graph(db_session, user_id, kb_id, force=True)

    assert deps == []


def test_generate_learning_path_sets_dependency_metadata_and_confidence(db_session):
    user_id = "lp_meta_user"
    kb_id = "lp_meta_kb"
    doc_id = "lp_meta_doc"
    _seed_single_doc_three_keypoints_fixture(db_session, user_id=user_id, kb_id=kb_id, doc_id=doc_id)
    invalidate_learning_path_result_cache(None, kb_id)

    llm_dependency_payload = {
        "edges": [
            {"from_id": f"{doc_id}-kp-1", "to_id": f"{doc_id}-kp-2"},
            {"from_id": f"{doc_id}-kp-2", "to_id": f"{doc_id}-kp-3"},
        ]
    }

    with (
        patch("app.services.learning_path._infer_rule_dependency_edges", return_value=[]),
        patch("app.services.learning_path._invoke_prompt_json", return_value=llm_dependency_payload),
        patch("app.services.learning_path._infer_stage_hints", return_value={}),
        patch("app.services.learning_path._infer_milestones", return_value=set()),
    ):
        items, edges, _stages, _modules, _summary = generate_learning_path(
            db_session, user_id, kb_id, limit=10, force=True
        )

    item_map = {item.keypoint_id: item for item in items}
    step_map = {item.keypoint_id: item.step for item in items}
    assert edges
    for edge in edges:
        assert step_map[edge.from_id] < step_map[edge.to_id]
        assert edge.confidence > 0

    third = item_map[f"{doc_id}-kp-3"]
    assert third.prerequisite_ids == [f"{doc_id}-kp-2"]
    assert third.unmet_prerequisite_ids == [f"{doc_id}-kp-2"]
    assert third.is_unlocked is False
    assert third.path_level >= 1
    assert third.unlocks_count >= 0


def test_build_dependency_graph_rebuilds_legacy_relation_version(db_session):
    user_id = "lp_legacy_user"
    kb_id = "lp_legacy_kb"
    doc_id = "lp_legacy_doc"
    _seed_learning_path_fixture(db_session, user_id=user_id, kb_id=kb_id, doc_id=doc_id)

    db_session.add(
        KeypointDependency(
            id="dep-legacy-1",
            kb_id=kb_id,
            from_keypoint_id=f"{doc_id}-kp-1",
            to_keypoint_id=f"{doc_id}-kp-2",
            relation="prerequisite",
            confidence=1.0,
        )
    )
    db_session.commit()

    with patch(
        "app.services.learning_path._invoke_prompt_json",
        return_value={
            "edges": [
                {"from_id": f"{doc_id}-kp-1", "to_id": f"{doc_id}-kp-2"},
            ]
        },
    ) as invoke_mock:
        deps = build_dependency_graph(db_session, user_id, kb_id, force=False)

    assert invoke_mock.called
    assert len(deps) == 1
    assert all(dep.relation == learning_path_service.DEPENDENCY_RELATION for dep in deps)
