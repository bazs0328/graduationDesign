import json

from app.core.config import settings
from app.models import Document, KnowledgeBase, User
from app.services.ingest_tasks import process_document_task


def test_process_document_task_uses_requesting_user_runtime_config(db_session, monkeypatch, tmp_path):
    user = User(
        id="ingest-runtime-user",
        username="ingest-runtime-user",
        password_hash="hash",
        advanced_config_json=json.dumps({"chunk_size": 2048}, ensure_ascii=False),
    )
    kb = KnowledgeBase(id="ingest-runtime-kb", user_id=user.id, name="Runtime KB")
    doc = Document(
        id="ingest-runtime-doc",
        user_id=user.id,
        kb_id=kb.id,
        filename="runtime.txt",
        file_type="txt",
        text_path=str(tmp_path / "runtime.txt"),
        status="processing",
    )
    db_session.add_all([user, kb, doc])
    db_session.commit()

    captured = {}

    def fake_ingest_document(file_path, filename, doc_id, user_id, kb_id):
        captured["chunk_size"] = settings.chunk_size
        return str(tmp_path / "out.txt"), 3, 1, 42

    monkeypatch.setattr("app.services.ingest_tasks.ingest_document", fake_ingest_document)

    process_document_task(doc.id, user.id, kb.id, str(tmp_path / "raw.txt"), doc.filename, "")

    db_session.expire_all()
    refreshed = db_session.query(Document).filter(Document.id == doc.id).first()
    assert refreshed is not None
    assert refreshed.status == "ready"
    assert refreshed.num_chunks == 3
    assert captured["chunk_size"] == 2048
