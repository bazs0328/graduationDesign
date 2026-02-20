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
        result = conn.execute(text("PRAGMA table_info(users)"))
        cols = {row[1] for row in result}
        if "username" not in cols:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN username VARCHAR(255) NOT NULL DEFAULT ''")
            )
            conn.commit()
        if "password_hash" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''"
                )
            )
            conn.commit()
        result = conn.execute(text("PRAGMA table_info(users)"))
        cols = {row[1] for row in result}
        if "username" in cols and "password_hash" in cols:
            conn.execute(
                text("UPDATE users SET username = id WHERE username = '' OR username IS NULL")
            )
            conn.commit()

        result = conn.execute(text("PRAGMA table_info(documents)"))
        cols = {row[1] for row in result}
        if "kb_id" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN kb_id VARCHAR"))
        if "status" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN status VARCHAR"))
        if "error_message" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN error_message TEXT"))
        if "retry_count" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN retry_count INTEGER DEFAULT 0"))
        if "last_retry_at" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN last_retry_at DATETIME"))
        if "stage" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN stage VARCHAR"))
        if "progress_percent" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN progress_percent INTEGER DEFAULT 0"))
        if "parser_provider" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN parser_provider VARCHAR"))
        if "extract_method" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN extract_method VARCHAR"))
        if "quality_score" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN quality_score FLOAT"))
        if "diagnostics_json" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN diagnostics_json TEXT"))
        if "timing_json" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN timing_json TEXT"))
        if "processed_at" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN processed_at DATETIME"))
        if "rag_backend" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN rag_backend VARCHAR"))
        if "asset_count" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN asset_count INTEGER DEFAULT 0"))
        if "visual_coverage" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN visual_coverage FLOAT DEFAULT 0.0"))
        if "multimodal_status" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN multimodal_status VARCHAR"))
        conn.execute(text("UPDATE documents SET status = 'ready' WHERE status IS NULL"))
        conn.execute(text("UPDATE documents SET retry_count = 0 WHERE retry_count IS NULL"))
        conn.execute(text("UPDATE documents SET progress_percent = 0 WHERE progress_percent IS NULL"))
        conn.execute(text("UPDATE documents SET asset_count = 0 WHERE asset_count IS NULL"))
        conn.execute(text("UPDATE documents SET visual_coverage = 0.0 WHERE visual_coverage IS NULL"))
        conn.execute(
            text(
                "UPDATE documents SET stage = CASE "
                "WHEN status = 'ready' THEN 'done' "
                "WHEN status = 'error' THEN 'error' "
                "ELSE 'extract' END "
                "WHERE stage IS NULL OR stage = ''"
            )
        )
        conn.execute(
            text(
                "UPDATE documents SET progress_percent = 100 "
                "WHERE status = 'ready' AND (progress_percent IS NULL OR progress_percent < 100)"
            )
        )
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

        result = conn.execute(text("PRAGMA table_info(learner_profiles)"))
        cols = {row[1] for row in result}
        if not cols:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS learner_profiles ("
                    "id VARCHAR PRIMARY KEY, "
                    "user_id VARCHAR UNIQUE NOT NULL, "
                    "ability_level VARCHAR, "
                    "theta FLOAT, "
                    "frustration_score FLOAT, "
                    "weak_concepts TEXT, "
                    "recent_accuracy FLOAT, "
                    "total_attempts INTEGER, "
                    "consecutive_low_scores INTEGER, "
                    "updated_at DATETIME, "
                    "FOREIGN KEY(user_id) REFERENCES users(id)"
                    ")"
                )
            )
            conn.commit()
        else:
            if "ability_level" not in cols:
                conn.execute(
                    text("ALTER TABLE learner_profiles ADD COLUMN ability_level VARCHAR")
                )
            if "theta" not in cols:
                conn.execute(text("ALTER TABLE learner_profiles ADD COLUMN theta FLOAT"))
            if "frustration_score" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE learner_profiles ADD COLUMN frustration_score FLOAT"
                    )
                )
            if "weak_concepts" not in cols:
                conn.execute(
                    text("ALTER TABLE learner_profiles ADD COLUMN weak_concepts TEXT")
                )
            if "recent_accuracy" not in cols:
                conn.execute(
                    text("ALTER TABLE learner_profiles ADD COLUMN recent_accuracy FLOAT")
                )
            if "total_attempts" not in cols:
                conn.execute(
                    text("ALTER TABLE learner_profiles ADD COLUMN total_attempts INTEGER")
                )
            if "consecutive_low_scores" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE learner_profiles ADD COLUMN consecutive_low_scores INTEGER"
                    )
                )
            if "updated_at" not in cols:
                conn.execute(
                    text("ALTER TABLE learner_profiles ADD COLUMN updated_at DATETIME")
                )
            conn.commit()

        result = conn.execute(text("PRAGMA table_info(keypoints_v2)"))
        cols = {row[1] for row in result}
        if not cols:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS keypoints_v2 ("
                    "id VARCHAR PRIMARY KEY, "
                    "user_id VARCHAR NOT NULL, "
                    "doc_id VARCHAR NOT NULL, "
                    "kb_id VARCHAR, "
                    "text TEXT NOT NULL, "
                    "explanation TEXT, "
                    "source VARCHAR, "
                    "page INTEGER, "
                    "chunk INTEGER, "
                    "mastery_level FLOAT DEFAULT 0.0, "
                    "attempt_count INTEGER DEFAULT 0, "
                    "correct_count INTEGER DEFAULT 0, "
                    "created_at DATETIME, "
                    "updated_at DATETIME, "
                    "FOREIGN KEY(user_id) REFERENCES users(id), "
                    "FOREIGN KEY(doc_id) REFERENCES documents(id), "
                    "FOREIGN KEY(kb_id) REFERENCES knowledge_bases(id)"
                    ")"
                )
            )
            conn.commit()
        else:
            if "kb_id" not in cols:
                conn.execute(text("ALTER TABLE keypoints_v2 ADD COLUMN kb_id VARCHAR"))
                conn.execute(
                    text(
                        "UPDATE keypoints_v2 SET kb_id = ("
                        "SELECT kb_id FROM documents WHERE documents.id = keypoints_v2.doc_id"
                        ") WHERE kb_id IS NULL"
                    )
                )
            if "source" not in cols:
                conn.execute(text("ALTER TABLE keypoints_v2 ADD COLUMN source VARCHAR"))
            if "page" not in cols:
                conn.execute(text("ALTER TABLE keypoints_v2 ADD COLUMN page INTEGER"))
            if "chunk" not in cols:
                conn.execute(text("ALTER TABLE keypoints_v2 ADD COLUMN chunk INTEGER"))
            if "mastery_level" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE keypoints_v2 ADD COLUMN mastery_level FLOAT DEFAULT 0.0"
                    )
                )
            if "attempt_count" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE keypoints_v2 ADD COLUMN attempt_count INTEGER DEFAULT 0"
                    )
                )
            if "correct_count" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE keypoints_v2 ADD COLUMN correct_count INTEGER DEFAULT 0"
                    )
                )
            if "created_at" not in cols:
                conn.execute(
                    text("ALTER TABLE keypoints_v2 ADD COLUMN created_at DATETIME")
                )
            if "updated_at" not in cols:
                conn.execute(
                    text("ALTER TABLE keypoints_v2 ADD COLUMN updated_at DATETIME")
                )
            conn.commit()

        # -- keypoint_dependencies table --
        result = conn.execute(text("PRAGMA table_info(keypoint_dependencies)"))
        cols = {row[1] for row in result}
        if not cols:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS keypoint_dependencies ("
                    "id VARCHAR PRIMARY KEY, "
                    "kb_id VARCHAR NOT NULL, "
                    "from_keypoint_id VARCHAR NOT NULL, "
                    "to_keypoint_id VARCHAR NOT NULL, "
                    "relation VARCHAR DEFAULT 'prerequisite', "
                    "confidence FLOAT DEFAULT 1.0, "
                    "created_at DATETIME, "
                    "FOREIGN KEY(kb_id) REFERENCES knowledge_bases(id), "
                    "FOREIGN KEY(from_keypoint_id) REFERENCES keypoints_v2(id), "
                    "FOREIGN KEY(to_keypoint_id) REFERENCES keypoints_v2(id)"
                    ")"
                )
            )
            conn.commit()

        result = conn.execute(text("PRAGMA table_info(document_assets)"))
        cols = {row[1] for row in result}
        if not cols:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS document_assets ("
                    "id VARCHAR PRIMARY KEY, "
                    "doc_id VARCHAR NOT NULL, "
                    "user_id VARCHAR NOT NULL, "
                    "kb_id VARCHAR, "
                    "page INTEGER, "
                    "asset_type VARCHAR NOT NULL, "
                    "image_path VARCHAR, "
                    "caption_text TEXT, "
                    "ocr_text TEXT, "
                    "quality_score FLOAT, "
                    "metadata_json TEXT, "
                    "created_at DATETIME, "
                    "FOREIGN KEY(doc_id) REFERENCES documents(id), "
                    "FOREIGN KEY(user_id) REFERENCES users(id), "
                    "FOREIGN KEY(kb_id) REFERENCES knowledge_bases(id)"
                    ")"
                )
            )
            conn.commit()

        result = conn.execute(text("PRAGMA table_info(ingest_runs)"))
        cols = {row[1] for row in result}
        if not cols:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS ingest_runs ("
                    "id VARCHAR PRIMARY KEY, "
                    "doc_id VARCHAR NOT NULL, "
                    "user_id VARCHAR NOT NULL, "
                    "kb_id VARCHAR, "
                    "backend VARCHAR NOT NULL, "
                    "parser_engine VARCHAR, "
                    "status VARCHAR NOT NULL, "
                    "mode VARCHAR, "
                    "stage VARCHAR, "
                    "timing_json TEXT, "
                    "diagnostics_json TEXT, "
                    "error_message TEXT, "
                    "created_at DATETIME, "
                    "FOREIGN KEY(doc_id) REFERENCES documents(id), "
                    "FOREIGN KEY(user_id) REFERENCES users(id), "
                    "FOREIGN KEY(kb_id) REFERENCES knowledge_bases(id)"
                    ")"
                )
            )
            conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
