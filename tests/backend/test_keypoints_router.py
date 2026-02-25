"""Tests for keypoints KB grouped dedup behavior."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.models import Document, Keypoint, KnowledgeBase, User


def _seed_kb_with_docs(
    db_session,
    *,
    user_id: str,
    kb_id: str,
    docs: list[tuple[str, str]],
):
    db_session.add(User(id=user_id, username=user_id, password_hash="hash", name="User"))
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name=f"KB-{kb_id}"))
    for doc_id, filename in docs:
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
                char_count=100,
                status="ready",
            )
        )


def test_get_keypoints_by_kb_grouped_exact_dedup_and_vector_failure_fallback(client, db_session):
    user_id = "kp_grouped_exact_user"
    kb_id = "kp_grouped_exact_kb"
    doc1 = "kp_grouped_exact_doc_1"
    doc2 = "kp_grouped_exact_doc_2"
    _seed_kb_with_docs(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        docs=[(doc1, "a.txt"), (doc2, "b.txt")],
    )
    base = datetime.utcnow()
    db_session.add_all(
        [
            Keypoint(
                id="kp-grouped-exact-1",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc1,
                text="1. 矩阵定义",
                explanation=None,
                source="a.txt",
                page=1,
                chunk=1,
                mastery_level=0.2,
                attempt_count=1,
                correct_count=0,
                created_at=base,
            ),
            Keypoint(
                id="kp-grouped-exact-2",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc2,
                text="矩阵定义",
                explanation="矩阵概念的基础定义",
                source="b.txt",
                page=2,
                chunk=3,
                mastery_level=0.6,
                attempt_count=2,
                correct_count=2,
                created_at=base + timedelta(seconds=1),
            ),
            Keypoint(
                id="kp-grouped-exact-3",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc2,
                text="特征值定义",
                explanation="e3",
                source="b.txt",
                page=3,
                chunk=5,
                mastery_level=0.4,
                attempt_count=1,
                correct_count=1,
                created_at=base + timedelta(seconds=2),
            ),
        ]
    )
    db_session.commit()

    raw_resp = client.get(f"/api/keypoints/kb/{kb_id}", params={"user_id": user_id})
    assert raw_resp.status_code == 200
    raw_payload = raw_resp.json()
    assert raw_payload["grouped"] is False
    assert len(raw_payload["keypoints"]) == 3

    with patch("app.services.keypoint_dedup.get_vectorstore", side_effect=RuntimeError("boom")):
        grouped_resp = client.get(
            f"/api/keypoints/kb/{kb_id}",
            params={"user_id": user_id, "grouped": "true"},
        )

    assert grouped_resp.status_code == 200
    payload = grouped_resp.json()
    assert payload["grouped"] is True
    assert payload["raw_count"] == 3
    assert payload["group_count"] == 2
    assert len(payload["keypoints"]) == 2

    merged = next(item for item in payload["keypoints"] if item["member_count"] == 2)
    assert merged["id"] == "kp-grouped-exact-1"  # earliest representative
    assert merged["grouped"] is True
    assert merged["explanation"] == "矩阵概念的基础定义"  # fallback from non-representative member
    assert merged["mastery_level"] == 0.6
    assert merged["attempt_count"] == 3
    assert merged["correct_count"] == 2
    assert merged["member_keypoint_ids"] == ["kp-grouped-exact-1", "kp-grouped-exact-2"]
    assert set(merged["source_doc_ids"]) == {doc1, doc2}
    assert set(merged["source_doc_names"]) == {"a.txt", "b.txt"}
    assert len(merged["source_refs"]) == 2
    assert {ref["keypoint_id"] for ref in merged["source_refs"]} == {
        "kp-grouped-exact-1",
        "kp-grouped-exact-2",
    }


def test_get_keypoints_by_kb_grouped_semantic_dedup(client, db_session):
    user_id = "kp_grouped_sem_user"
    kb_id = "kp_grouped_sem_kb"
    doc1 = "kp_grouped_sem_doc_1"
    doc2 = "kp_grouped_sem_doc_2"
    _seed_kb_with_docs(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        docs=[(doc1, "m1.txt"), (doc2, "m2.txt")],
    )
    base = datetime.utcnow()
    db_session.add_all(
        [
            Keypoint(
                id="kp-grouped-sem-1",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc1,
                text="矩阵秩定义",
                explanation="e1",
                mastery_level=0.2,
                attempt_count=1,
                correct_count=0,
                created_at=base,
            ),
            Keypoint(
                id="kp-grouped-sem-2",
                user_id=user_id,
                kb_id=kb_id,
                doc_id=doc2,
                text="矩阵秩定义的含义",
                explanation="e2",
                mastery_level=0.5,
                attempt_count=2,
                correct_count=1,
                created_at=base + timedelta(seconds=1),
            ),
        ]
    )
    db_session.commit()

    vectorstore = Mock()

    def _search(query, k, filter):  # noqa: A002
        assert k == 6
        assert filter == {"kb_id": kb_id, "type": "keypoint"}
        if query == "矩阵秩定义":
            return [
                (
                    SimpleNamespace(
                        metadata={"keypoint_id": "kp-grouped-sem-2", "doc_id": doc2}
                    ),
                    0.1,
                )
            ]
        return []

    vectorstore.similarity_search_with_score.side_effect = _search

    with patch("app.services.keypoint_dedup.get_vectorstore", return_value=vectorstore):
        resp = client.get(
            f"/api/keypoints/kb/{kb_id}",
            params={"user_id": user_id, "grouped": "true"},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["grouped"] is True
    assert payload["raw_count"] == 2
    assert payload["group_count"] == 1
    assert len(payload["keypoints"]) == 1
    item = payload["keypoints"][0]
    assert item["member_count"] == 2
    assert item["id"] == "kp-grouped-sem-1"
    assert item["attempt_count"] == 3
    assert item["mastery_level"] == 0.5
