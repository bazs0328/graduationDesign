from sqlalchemy import text

from app.db import engine, ensure_schema


def _index_names(conn, table: str):
    rows = conn.execute(text(f"PRAGMA index_list('{table}')")).all()
    return {row[1]: row for row in rows}


def _index_columns(conn, index_name: str):
    rows = conn.execute(text(f"PRAGMA index_info('{index_name}')")).all()
    rows = sorted(rows, key=lambda row: row[0])
    return [row[2] for row in rows]


def test_quiz_attempts_unique_index_exists():
    ensure_schema()
    with engine.connect() as conn:
        indexes = _index_names(conn, "quiz_attempts")
        assert "uq_quiz_attempts_user_quiz" in indexes
        assert int(indexes["uq_quiz_attempts_user_quiz"][2]) == 1
        assert _index_columns(conn, "uq_quiz_attempts_user_quiz") == ["user_id", "quiz_id"]


def test_hot_path_non_unique_indexes_exist():
    ensure_schema()
    with engine.connect() as conn:
        doc_indexes = _index_names(conn, "documents")
        qa_indexes = _index_names(conn, "qa_records")
        summary_indexes = _index_names(conn, "summaries")
        keypoints_v2_indexes = _index_names(conn, "keypoints_v2")
        dependency_indexes = _index_names(conn, "keypoint_dependencies")

    assert "idx_documents_user_kb_id" in doc_indexes
    assert "idx_documents_user_kb_status_created_at" in doc_indexes
    assert "idx_qa_records_user_kb_id" in qa_indexes
    assert "idx_summaries_user_doc_id" in summary_indexes
    assert "idx_keypoints_v2_user_doc" in keypoints_v2_indexes
    assert "idx_keypoints_v2_user_kb_doc_created_id" in keypoints_v2_indexes
    assert "idx_keypoint_dependencies_kb_relation" in dependency_indexes


def test_new_composite_hot_path_index_columns_match_expected_order():
    ensure_schema()
    with engine.connect() as conn:
        assert _index_columns(conn, "idx_documents_user_kb_status_created_at") == [
            "user_id",
            "kb_id",
            "status",
            "created_at",
        ]
        assert _index_columns(conn, "idx_keypoints_v2_user_kb_doc_created_id") == [
            "user_id",
            "kb_id",
            "doc_id",
            "created_at",
            "id",
        ]
        assert _index_columns(conn, "idx_keypoints_v2_user_doc") == [
            "user_id",
            "doc_id",
        ]
        assert _index_columns(conn, "idx_keypoint_dependencies_kb_relation") == [
            "kb_id",
            "relation",
        ]
