"""Pytest fixtures for backend integration tests."""
import os
import pytest
import tempfile
import sys
from pathlib import Path

# Set DATA_DIR before any app imports so db/engine uses temp storage
_test_data_dir = tempfile.mkdtemp(prefix="gradtutor_test_")
os.environ["DATA_DIR"] = _test_data_dir

# Ensure backend is on path
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend.parent))

from fastapi.testclient import TestClient

from app.main import create_app
from app.db import SessionLocal, Base, engine, ensure_schema
from app.models import User, KnowledgeBase, Document, ChatSession


@pytest.fixture
def client():
    """FastAPI TestClient with fresh app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def db_session():
    """Fresh DB session. Yields session, closes after."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def seeded_session():
    """DB with user, kb, doc, chat session for QA tests. Runs once per test session."""
    user_id = "test_user_qa"
    kb_id = "kb-1"
    doc_id = "doc-1"

    user = User(id=user_id, name="Test")
    kb = KnowledgeBase(id=kb_id, user_id=user_id, name="Test KB")
    doc = Document(
        id=doc_id,
        user_id=user_id,
        kb_id=kb_id,
        filename="test.txt",
        file_type="txt",
        text_path=os.path.join(_test_data_dir, "test.txt"),
        num_chunks=1,
        num_pages=1,
        char_count=100,
        status="ready",
    )

    session_id = "session-1"
    chat_sess = ChatSession(
        id=session_id,
        user_id=user_id,
        kb_id=kb_id,
        doc_id=doc_id,
        title=None,
    )
    seed_db = SessionLocal()
    try:
        seed_db.add(user)
        seed_db.add(kb)
        seed_db.add(doc)
        seed_db.add(chat_sess)
        seed_db.commit()
    finally:
        seed_db.close()

    return {
        "user_id": user_id,
        "kb_id": kb_id,
        "doc_id": doc_id,
        "session_id": session_id,
    }
