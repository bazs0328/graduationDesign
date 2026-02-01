from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

DATABASE_URL = f"sqlite:///{settings.data_dir}/app.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_schema():
    if not engine.url.drivername.startswith("sqlite"):
        return

    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(documents)"))
        cols = {row[1] for row in result}
        if "kb_id" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN kb_id VARCHAR"))
        if "status" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN status VARCHAR"))
        if "error_message" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN error_message TEXT"))
        if "processed_at" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN processed_at DATETIME"))
        conn.execute(text("UPDATE documents SET status = 'ready' WHERE status IS NULL"))
        conn.commit()

        result = conn.execute(text("PRAGMA table_info(qa_records)"))
        cols = {row[1] for row in result}
        if "kb_id" not in cols:
            conn.execute(text("ALTER TABLE qa_records ADD COLUMN kb_id VARCHAR"))
            conn.execute(
                text(
                    "UPDATE qa_records "
                    "SET kb_id = (SELECT kb_id FROM documents WHERE documents.id = qa_records.doc_id) "
                    "WHERE kb_id IS NULL AND doc_id IS NOT NULL"
                )
            )
            conn.commit()

        result = conn.execute(text("PRAGMA table_info(chat_messages)"))
        cols = {row[1] for row in result}
        if "sources_json" not in cols:
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN sources_json TEXT"))
            conn.commit()

        result = conn.execute(text("PRAGMA table_info(quizzes)"))
        cols = {row[1] for row in result}
        if "kb_id" not in cols:
            conn.execute(text("ALTER TABLE quizzes ADD COLUMN kb_id VARCHAR"))
            conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
