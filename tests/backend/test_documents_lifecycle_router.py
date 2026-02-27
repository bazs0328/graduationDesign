"""Tests for document lifecycle endpoints."""

from datetime import datetime, timedelta
import io
import json
import os
from unittest.mock import patch

from app.core.paths import ensure_kb_dirs, kb_base_dir
from app.models import (
    ChatMessage,
    ChatSession,
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


def _seed_user_kbs_doc(db_session, *, user_id: str, kb_id: str, doc_id: str):
    os.makedirs("tmp", exist_ok=True)
    db_session.add(
        User(
            id=user_id,
            username=user_id,
            password_hash="test_hash",
            name="Test User",
        )
    )
    db_session.add(KnowledgeBase(id=kb_id, user_id=user_id, name=f"KB-{kb_id}"))
    doc = Document(
        id=doc_id,
        user_id=user_id,
        kb_id=kb_id,
        filename="origin.txt",
        file_type="txt",
        text_path=os.path.join("tmp", f"{doc_id}.txt"),
        num_chunks=1,
        num_pages=1,
        char_count=120,
        file_hash=f"hash-{doc_id}",
        status="ready",
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def test_patch_doc_supports_rename_and_move(client, db_session):
    user_id = "doc_lifecycle_user_1"
    old_kb = "doc_kb_old"
    new_kb = "doc_kb_new"
    doc_id = "doc_lifecycle_1"
    _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=old_kb,
        doc_id=doc_id,
    )
    db_session.add(KnowledgeBase(id=new_kb, user_id=user_id, name="Target KB"))
    db_session.add(
        Keypoint(
            id="kp-doc-1",
            user_id=user_id,
            doc_id=doc_id,
            kb_id=old_kb,
            text="矩阵定义",
        )
    )
    db_session.add(
        QARecord(
            id="qa-doc-1",
            user_id=user_id,
            kb_id=old_kb,
            doc_id=doc_id,
            question="Q",
            answer="A",
        )
    )
    db_session.add(
        Quiz(
            id="quiz-doc-1",
            user_id=user_id,
            kb_id=old_kb,
            doc_id=doc_id,
            questions_json="[]",
        )
    )
    db_session.add(
        ChatSession(
            id="chat-doc-1",
            user_id=user_id,
            kb_id=old_kb,
            doc_id=doc_id,
        )
    )
    db_session.commit()

    with (
        patch("app.routers.documents.update_doc_vector_metadata", return_value=1) as vector_mock,
        patch("app.routers.documents.move_doc_chunks", return_value=1) as lexical_move_mock,
    ):
        resp = client.patch(
            f"/api/docs/{doc_id}",
            json={
                "user_id": user_id,
                "filename": "renamed.txt",
                "kb_id": new_kb,
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["filename"] == "renamed.txt"
    assert payload["kb_id"] == new_kb
    vector_mock.assert_called_once()
    lexical_move_mock.assert_called_once()

    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc is not None
    assert doc.filename == "renamed.txt"
    assert doc.kb_id == new_kb
    keypoint = db_session.query(Keypoint).filter(Keypoint.doc_id == doc_id).first()
    assert keypoint is not None
    assert keypoint.kb_id == new_kb
    qa = db_session.query(QARecord).filter(QARecord.doc_id == doc_id).first()
    assert qa is not None
    assert qa.kb_id == new_kb
    quiz = db_session.query(Quiz).filter(Quiz.doc_id == doc_id).first()
    assert quiz is not None
    assert quiz.kb_id == new_kb
    session = db_session.query(ChatSession).filter(ChatSession.doc_id == doc_id).first()
    assert session is not None
    assert session.kb_id == new_kb


def test_reprocess_doc_changes_status_and_triggers_task(client, db_session):
    user_id = "doc_lifecycle_user_2"
    kb_id = "doc_kb_reprocess"
    doc_id = "doc_lifecycle_2"
    doc = _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
    )

    ensure_kb_dirs(user_id, kb_id)
    raw_dir = os.path.join(kb_base_dir(user_id, kb_id), "raw")
    raw_path = os.path.join(raw_dir, f"{doc_id}_{doc.filename}")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write("raw")

    with (
        patch("app.routers.documents.delete_doc_vectors", return_value=1),
        patch("app.routers.documents.remove_doc_chunks", return_value=1),
        patch("app.routers.documents.process_document_task") as task_mock,
    ):
        resp = client.post(
            f"/api/docs/{doc_id}/reprocess",
            params={"user_id": user_id},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "processing"
    task_mock.assert_called_once()
    called = task_mock.call_args.args
    assert called[0] == doc_id
    assert called[1] == user_id
    assert called[2] == kb_id
    assert called[3] == raw_path


def test_delete_doc_cleans_records_and_files(client, db_session):
    user_id = "doc_lifecycle_user_3"
    kb_id = "doc_kb_delete"
    doc_id = "doc_lifecycle_3"
    doc = _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
    )
    text_path = doc.text_path

    ensure_kb_dirs(user_id, kb_id)
    raw_dir = os.path.join(kb_base_dir(user_id, kb_id), "raw")
    raw_path = os.path.join(raw_dir, f"{doc_id}_{doc.filename}")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write("raw")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write("text")

    db_session.add(
        SummaryRecord(
            id="sum-doc-delete",
            user_id=user_id,
            doc_id=doc_id,
            summary_text="summary",
        )
    )
    db_session.add(
        KeypointRecord(
            id="kpr-doc-delete",
            user_id=user_id,
            doc_id=doc_id,
            points_json='["k1"]',
        )
    )
    db_session.add(
        Keypoint(
            id="kp-doc-delete",
            user_id=user_id,
            doc_id=doc_id,
            kb_id=kb_id,
            text="线性映射",
        )
    )
    db_session.add(
        QARecord(
            id="qa-doc-delete",
            user_id=user_id,
            doc_id=doc_id,
            kb_id=kb_id,
            question="Q",
            answer="A",
        )
    )
    db_session.add(
        Quiz(
            id="quiz-doc-delete",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
            questions_json="[]",
        )
    )
    db_session.add(
        QuizAttempt(
            id="attempt-doc-delete",
            user_id=user_id,
            quiz_id="quiz-doc-delete",
            answers_json="[0]",
            score=1.0,
            total=1,
        )
    )
    db_session.add(
        ChatSession(
            id="chat-doc-delete",
            user_id=user_id,
            kb_id=kb_id,
            doc_id=doc_id,
        )
    )
    db_session.add(
        ChatMessage(
            id="msg-doc-delete",
            session_id="chat-doc-delete",
            role="user",
            content="hello",
        )
    )
    db_session.commit()

    with (
        patch("app.routers.documents.delete_doc_vectors", return_value=1),
        patch("app.routers.documents.remove_doc_chunks", return_value=1),
    ):
        resp = client.delete(f"/api/docs/{doc_id}", params={"user_id": user_id})

    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert db_session.query(Document).filter(Document.id == doc_id).first() is None
    assert db_session.query(SummaryRecord).filter(SummaryRecord.doc_id == doc_id).first() is None
    assert db_session.query(KeypointRecord).filter(KeypointRecord.doc_id == doc_id).first() is None
    assert db_session.query(Keypoint).filter(Keypoint.doc_id == doc_id).first() is None
    assert db_session.query(QARecord).filter(QARecord.doc_id == doc_id).first() is None
    assert db_session.query(Quiz).filter(Quiz.doc_id == doc_id).first() is None
    assert (
        db_session.query(ChatSession).filter(ChatSession.doc_id == doc_id).first()
        is None
    )
    assert not os.path.exists(raw_path)
    assert not os.path.exists(text_path)


def test_doc_task_center_and_retry_failed(client, db_session):
    user_id = "doc_lifecycle_user_task"
    kb_id = "doc_kb_task"
    error_doc_id = "doc_task_error"
    processing_doc_id = "doc_task_processing"
    _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id="doc_task_ready",
    )
    error_doc = Document(
        id=error_doc_id,
        user_id=user_id,
        kb_id=kb_id,
        filename="error.txt",
        file_type="txt",
        text_path=os.path.join("tmp", f"{error_doc_id}.txt"),
        num_chunks=0,
        num_pages=0,
        char_count=0,
        file_hash=f"hash-{error_doc_id}",
        status="error",
        error_message="extract failed",
        retry_count=2,
    )
    processing_doc = Document(
        id=processing_doc_id,
        user_id=user_id,
        kb_id=kb_id,
        filename="processing.txt",
        file_type="txt",
        text_path=os.path.join("tmp", f"{processing_doc_id}.txt"),
        num_chunks=0,
        num_pages=0,
        char_count=0,
        file_hash=f"hash-{processing_doc_id}",
        status="processing",
    )
    db_session.add(error_doc)
    db_session.add(processing_doc)
    db_session.commit()

    tasks_resp = client.get("/api/docs/tasks", params={"user_id": user_id, "kb_id": kb_id})
    assert tasks_resp.status_code == 200
    payload = tasks_resp.json()
    assert payload["processing_count"] == 1
    assert payload["error_count"] == 1
    assert payload["processing"][0]["id"] == processing_doc_id
    assert payload["error"][0]["id"] == error_doc_id
    assert payload["error"][0]["retry_count"] == 2

    ensure_kb_dirs(user_id, kb_id)
    raw_dir = os.path.join(kb_base_dir(user_id, kb_id), "raw")
    raw_path = os.path.join(raw_dir, f"{error_doc_id}_{error_doc.filename}")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write("raw")

    with (
        patch("app.routers.documents.delete_doc_vectors", return_value=1),
        patch("app.routers.documents.remove_doc_chunks", return_value=1),
        patch("app.routers.documents.process_document_task"),
    ):
        retry_resp = client.post(
            "/api/docs/retry-failed",
            json={"user_id": user_id, "doc_ids": [error_doc_id]},
        )

    assert retry_resp.status_code == 200
    retry_payload = retry_resp.json()
    assert retry_payload["queued"] == [error_doc_id]
    assert retry_payload["skipped"] == []

    db_session.expire_all()
    refreshed = db_session.query(Document).filter(Document.id == error_doc_id).first()
    assert refreshed is not None
    assert refreshed.status == "processing"
    assert refreshed.retry_count == 3


def test_list_docs_supports_filter_search_and_sort(client, db_session):
    user_id = "doc_list_user_1"
    kb_id = "doc_list_kb_1"
    base_doc_id = "doc_list_base"
    base_doc = _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=base_doc_id,
    )
    base_doc.filename = "linear-algebra-notes.pdf"
    base_doc.file_type = "pdf"
    base_doc.status = "ready"
    base_doc.created_at = datetime.utcnow() - timedelta(days=2)
    db_session.add(base_doc)
    db_session.add(
        Document(
            id="doc_list_error",
            user_id=user_id,
            kb_id=kb_id,
            filename="matrix-exam.pdf",
            file_type="pdf",
            text_path=os.path.join("tmp", "doc_list_error.txt"),
            num_chunks=3,
            num_pages=2,
            char_count=300,
            file_hash="hash-doc-list-error",
            status="error",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
    )
    db_session.add(
        Document(
            id="doc_list_md",
            user_id=user_id,
            kb_id=kb_id,
            filename="calculus-guide.md",
            file_type="md",
            text_path=os.path.join("tmp", "doc_list_md.txt"),
            num_chunks=2,
            num_pages=1,
            char_count=200,
            file_hash="hash-doc-list-md",
            status="ready",
            created_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    filtered = client.get(
        "/api/docs",
        params={
            "user_id": user_id,
            "kb_id": kb_id,
            "file_type": "pdf",
            "status": "ready",
            "keyword": "linear",
            "sort_by": "filename",
            "sort_order": "asc",
        },
    )
    assert filtered.status_code == 200
    rows = filtered.json()
    assert len(rows) == 1
    assert rows[0]["id"] == base_doc_id

    sorted_resp = client.get(
        "/api/docs",
        params={
            "user_id": user_id,
            "kb_id": kb_id,
            "sort_by": "filename",
            "sort_order": "asc",
        },
    )
    assert sorted_resp.status_code == 200
    names = [item["filename"] for item in sorted_resp.json()]
    assert names == sorted(names)


def test_list_docs_page_returns_metadata_and_items(client, db_session):
    user_id = "doc_page_user_1"
    kb_id = "doc_page_kb_1"
    _seed_user_kbs_doc(db_session, user_id=user_id, kb_id=kb_id, doc_id="doc_page_a")
    db_session.add(
        Document(
            id="doc_page_b",
            user_id=user_id,
            kb_id=kb_id,
            filename="origin-b.txt",
            file_type="txt",
            text_path=os.path.join("tmp", "doc_page_b.txt"),
            num_chunks=1,
            num_pages=1,
            char_count=100,
            file_hash="hash-doc-page-b",
            status="ready",
        )
    )
    db_session.add(
        Document(
            id="doc_page_c",
            user_id=user_id,
            kb_id=kb_id,
            filename="origin-c.txt",
            file_type="txt",
            text_path=os.path.join("tmp", "doc_page_c.txt"),
            num_chunks=1,
            num_pages=1,
            char_count=100,
            file_hash="hash-doc-page-c",
            status="ready",
        )
    )
    db_session.commit()

    docs = db_session.query(Document).filter(Document.user_id == user_id).all()
    name_map = {
        "doc_page_a": ("alpha.pdf", datetime.utcnow() - timedelta(days=3)),
        "doc_page_b": ("beta.pdf", datetime.utcnow() - timedelta(days=2)),
        "doc_page_c": ("gamma.pdf", datetime.utcnow() - timedelta(days=1)),
    }
    for doc in docs:
        filename, created_at = name_map[doc.id]
        doc.filename = filename
        doc.file_type = "pdf"
        doc.created_at = created_at
        db_session.add(doc)
    db_session.commit()

    resp = client.get(
        "/api/docs/page",
        params={
            "user_id": user_id,
            "kb_id": kb_id,
            "sort_by": "filename",
            "sort_order": "asc",
            "offset": 1,
            "limit": 1,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 3
    assert payload["offset"] == 1
    assert payload["limit"] == 1
    assert payload["has_more"] is True
    assert [item["filename"] for item in payload["items"]] == ["beta.pdf"]

    last_page = client.get(
        "/api/docs/page",
        params={
            "user_id": user_id,
            "kb_id": kb_id,
            "sort_by": "filename",
            "sort_order": "asc",
            "offset": 2,
            "limit": 1,
        },
    )
    assert last_page.status_code == 200
    last_payload = last_page.json()
    assert last_payload["has_more"] is False
    assert [item["filename"] for item in last_payload["items"]] == ["gamma.pdf"]


def test_get_doc_returns_single_doc_and_enforces_user_scope(client, db_session):
    user_id = "doc_get_user_1"
    kb_id = "doc_get_kb_1"
    doc_id = "doc_get_1"
    _seed_user_kbs_doc(db_session, user_id=user_id, kb_id=kb_id, doc_id=doc_id)

    resp = client.get(f"/api/docs/{doc_id}", params={"user_id": user_id})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == doc_id
    assert payload["user_id"] == user_id

    wrong_user_resp = client.get(f"/api/docs/{doc_id}", params={"user_id": "doc_get_user_other"})
    assert wrong_user_resp.status_code == 404

    missing_resp = client.get("/api/docs/not-found", params={"user_id": user_id})
    assert missing_resp.status_code == 404


def test_preview_doc_source_returns_traceable_snippet(client, db_session):
    user_id = "doc_preview_user_1"
    kb_id = "doc_preview_kb_1"
    doc_id = "doc_preview_doc_1"
    doc = _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
    )
    with open(doc.text_path, "w", encoding="utf-8") as f:
        f.write("矩阵是一个按行列排列的数表。线性变换可以用矩阵表示。")

    vector_entries = [
        {
            "id": "v1",
            "content": "矩阵是一个按行列排列的数表。矩阵可表示线性变换。",
            "metadata": {"page": 2, "chunk": 7, "source": doc.filename, "doc_id": doc_id},
        }
    ]
    with patch("app.routers.documents.get_doc_vector_entries", return_value=vector_entries):
        resp = client.get(
            f"/api/docs/{doc_id}/preview",
            params={
                "user_id": user_id,
                "page": 2,
                "chunk": 7,
                "q": "矩阵",
            },
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["doc_id"] == doc_id
    assert payload["page"] == 2
    assert payload["chunk"] == 7
    assert payload["matched_by"] == "chunk"
    assert "矩阵" in payload["snippet"]


def test_preview_doc_source_uses_sidecar_summary_for_image_hits(client, db_session):
    user_id = "doc_preview_user_img_1"
    kb_id = "doc_preview_kb_img_1"
    doc_id = "doc_preview_img_1"
    doc = _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
    )

    ensure_kb_dirs(user_id, kb_id)
    sidecar_path = os.path.join(kb_base_dir(user_id, kb_id), "content_list", f"{doc_id}.layout.json")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "version": 1,
                "page_count": 1,
                "pages": [
                    {
                        "page": 1,
                        "ordered_blocks": [
                            {"block_id": "p1:t1", "kind": "text", "text": "上文介绍了对称变换。"},
                            {
                                "block_id": "p1:i1",
                                "kind": "image",
                                "caption_text": "图1 对称示意",
                                "nearby_text": "图像展示了 y 轴对称后的点位变化。",
                            },
                            {"block_id": "p1:t2", "kind": "text", "text": "下文继续讨论矩阵表示。"},
                        ],
                    }
                ],
                "chunk_manifest": [],
            },
            f,
            ensure_ascii=False,
        )

    image_entries = [
        {
            "id": "img-1",
            "content": "[图片块]\n邻近文字: 原始占位文本",
            "metadata": {
                "page": 1,
                "source": doc.filename,
                "doc_id": doc_id,
                "kb_id": kb_id,
                "modality": "image",
                "block_id": "p1:i1",
            },
        }
    ]
    with (
        patch("app.routers.documents.get_doc_vector_entries", return_value=[]),
        patch("app.routers.documents.get_doc_image_vector_entries", return_value=image_entries),
    ):
        resp = client.get(
            f"/api/docs/{doc_id}/preview",
            params={"user_id": user_id, "page": 1},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["matched_by"] == "image_sidecar"
    assert payload["block_id"] == "p1:i1"
    assert "图注: 图1 对称示意" in payload["snippet"]
    assert "邻近正文" in payload["snippet"]
    assert "[图片块]" not in payload["snippet"]


def test_preview_doc_source_prefers_ocr_override_vector_text(client, db_session):
    user_id = "doc_preview_user_ocr_1"
    kb_id = "doc_preview_kb_ocr_1"
    doc_id = "doc_preview_ocr_1"
    doc = _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
    )

    ensure_kb_dirs(user_id, kb_id)
    sidecar_path = os.path.join(kb_base_dir(user_id, kb_id), "content_list", f"{doc_id}.layout.json")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "version": 1,
                "page_count": 1,
                "pages": [
                    {
                        "page": 1,
                        "ordered_blocks": [
                            {"block_id": "p1:t1", "kind": "text", "text": "sidecar 旧文本内容"},
                        ],
                    }
                ],
                "chunk_manifest": [
                    {
                        "chunk": 1,
                        "page": 1,
                        "modality": "text",
                        "block_ids": json.dumps(["p1:t1"], ensure_ascii=False),
                    }
                ],
            },
            f,
            ensure_ascii=False,
        )

    vector_entries = [
        {
            "id": "txt-ocr-1",
            "content": "这是 OCR 修复后的最终文本内容。",
            "metadata": {
                "page": 1,
                "chunk": 1,
                "source": doc.filename,
                "doc_id": doc_id,
                "kb_id": kb_id,
                "modality": "text",
                "ocr_override": True,
                "block_ids": json.dumps(["p1:ocr"], ensure_ascii=False),
            },
        }
    ]
    with (
        patch("app.routers.documents.get_doc_vector_entries", return_value=vector_entries),
        patch("app.routers.documents.get_doc_image_vector_entries", return_value=[]),
    ):
        resp = client.get(
            f"/api/docs/{doc_id}/preview",
            params={"user_id": user_id, "page": 1, "chunk": 1},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["matched_by"] == "ocr_override_text"
    assert "OCR 修复后的最终文本内容" in payload["snippet"]
    assert "sidecar 旧文本内容" not in payload["snippet"]


def test_preview_doc_source_prefers_text_when_page_has_text_and_image(client, db_session):
    user_id = "doc_preview_user_page_text_first"
    kb_id = "doc_preview_kb_page_text_first"
    doc_id = "doc_preview_page_text_first"
    doc = _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
    )

    text_entries = [
        {
            "id": "txt-1",
            "content": "这是本页正文：矩阵定义与性质。",
            "metadata": {
                "page": 1,
                "chunk": 5,
                "source": doc.filename,
                "doc_id": doc_id,
                "kb_id": kb_id,
                "modality": "text",
            },
        }
    ]
    image_entries = [
        {
            "id": "img-1",
            "content": "[图片块]\n图注: 图1 对称示意",
            "metadata": {
                "page": 1,
                "source": doc.filename,
                "doc_id": doc_id,
                "kb_id": kb_id,
                "modality": "image",
                "block_id": "p1:i1",
            },
        }
    ]
    with (
        patch("app.routers.documents.get_doc_vector_entries", return_value=text_entries),
        patch("app.routers.documents.get_doc_image_vector_entries", return_value=image_entries),
    ):
        resp = client.get(
            f"/api/docs/{doc_id}/preview",
            params={"user_id": user_id, "page": 1},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["matched_by"] == "page"
    assert payload["modality"] == "text"
    assert "矩阵定义与性质" in payload["snippet"]


def test_preview_doc_source_prefers_text_when_query_hits_text_on_same_page(client, db_session):
    user_id = "doc_preview_user_page_query_text"
    kb_id = "doc_preview_kb_page_query_text"
    doc_id = "doc_preview_page_query_text"
    doc = _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
    )

    text_entries = [
        {
            "id": "txt-1",
            "content": "本页正文包含关键词：矩阵。",
            "metadata": {
                "page": 1,
                "chunk": 3,
                "source": doc.filename,
                "doc_id": doc_id,
                "kb_id": kb_id,
                "modality": "text",
            },
        }
    ]
    image_entries = [
        {
            "id": "img-1",
            "content": "[图片块]\n图注: 图1 对称示意",
            "metadata": {
                "page": 1,
                "source": doc.filename,
                "doc_id": doc_id,
                "kb_id": kb_id,
                "modality": "image",
                "block_id": "p1:i1",
            },
        }
    ]
    with (
        patch("app.routers.documents.get_doc_vector_entries", return_value=text_entries),
        patch("app.routers.documents.get_doc_image_vector_entries", return_value=image_entries),
    ):
        resp = client.get(
            f"/api/docs/{doc_id}/preview",
            params={"user_id": user_id, "page": 1, "q": "矩阵"},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["modality"] == "text"
    assert "矩阵" in payload["snippet"]


def test_preview_doc_source_allows_image_when_query_misses_text_on_same_page(client, db_session):
    user_id = "doc_preview_user_page_query_image"
    kb_id = "doc_preview_kb_page_query_image"
    doc_id = "doc_preview_page_query_image"
    doc = _seed_user_kbs_doc(
        db_session,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
    )

    text_entries = [
        {
            "id": "txt-1",
            "content": "本页正文讨论矩阵定义。",
            "metadata": {
                "page": 1,
                "chunk": 6,
                "source": doc.filename,
                "doc_id": doc_id,
                "kb_id": kb_id,
                "modality": "text",
            },
        }
    ]
    image_entries = [
        {
            "id": "img-1",
            "content": "[图片块]\n邻近文字: 图像展示了关于 y 轴对称的结果。",
            "metadata": {
                "page": 1,
                "source": doc.filename,
                "doc_id": doc_id,
                "kb_id": kb_id,
                "modality": "image",
                "block_id": "p1:i1",
            },
        }
    ]
    with (
        patch("app.routers.documents.get_doc_vector_entries", return_value=text_entries),
        patch("app.routers.documents.get_doc_image_vector_entries", return_value=image_entries),
    ):
        resp = client.get(
            f"/api/docs/{doc_id}/preview",
            params={"user_id": user_id, "page": 1, "q": "对称"},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["modality"] == "image"
    assert "对称" in payload["snippet"]


def test_upload_doc_accepts_docx_and_pptx(client):
    user_id = "doc_upload_office_user_1"
    cases = [
        (
            "lecture-notes.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        ),
        (
            "chapter-slides.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "pptx",
        ),
    ]

    for idx, (filename, mime, expected_type) in enumerate(cases, start=1):
        with patch("app.routers.documents.process_document_task") as task_mock:
            resp = client.post(
                "/api/docs/upload",
                data={"user_id": f"{user_id}_{idx}"},
                files={"file": (filename, io.BytesIO(f"office-{idx}".encode()), mime)},
            )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["filename"] == filename
        assert payload["file_type"] == expected_type
        assert payload["status"] == "processing"
        task_mock.assert_called_once()


def test_upload_doc_rejects_unsupported_legacy_office_format(client):
    resp = client.post(
        "/api/docs/upload",
        data={"user_id": "doc_upload_legacy_office_user"},
        files={"file": ("legacy.doc", io.BytesIO(b"legacy"), "application/msword")},
    )

    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]
