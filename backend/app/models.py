from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, ForeignKey

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    kb_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=True, index=True)
    doc_id = Column(String, ForeignKey("documents.id"), nullable=True, index=True)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=True)  # JSON array of SourceSnippet-compatible dicts
    created_at = Column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    kb_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=True, index=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    text_path = Column(String, nullable=False)
    num_chunks = Column(Integer, default=0)
    num_pages = Column(Integer, default=0)
    char_count = Column(Integer, default=0)
    file_size = Column(Integer, default=0)
    file_hash = Column(String, nullable=True, index=True)
    status = Column(String, default="processing")
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    last_retry_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SummaryRecord(Base):
    __tablename__ = "summaries"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    doc_id = Column(String, ForeignKey("documents.id"))
    summary_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class KeypointRecord(Base):
    __tablename__ = "keypoints"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    doc_id = Column(String, ForeignKey("documents.id"))
    points_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Keypoint(Base):
    __tablename__ = "keypoints_v2"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    doc_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    kb_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=True, index=True)
    text = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    source = Column(String, nullable=True)
    page = Column(Integer, nullable=True)
    chunk = Column(Integer, nullable=True)
    mastery_level = Column(Float, default=0.0)
    attempt_count = Column(Integer, default=0)
    correct_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class QARecord(Base):
    __tablename__ = "qa_records"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    kb_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=True, index=True)
    doc_id = Column(String, ForeignKey("documents.id"))
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    kb_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=True, index=True)
    doc_id = Column(String, ForeignKey("documents.id"), nullable=True)
    difficulty = Column(String, default="medium")
    question_type = Column(String, default="mcq")
    questions_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    quiz_id = Column(String, ForeignKey("quizzes.id"))
    answers_json = Column(Text, nullable=False)
    score = Column(Float, nullable=False)
    total = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), unique=True, index=True, nullable=False)
    ability_level = Column(String, default="intermediate")
    theta = Column(Float, default=0.0)
    frustration_score = Column(Float, default=0.0)
    weak_concepts = Column(Text, nullable=True)
    recent_accuracy = Column(Float, default=0.5)
    total_attempts = Column(Integer, default=0)
    consecutive_low_scores = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KeypointDependency(Base):
    __tablename__ = "keypoint_dependencies"

    id = Column(String, primary_key=True, index=True)
    kb_id = Column(String, ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    from_keypoint_id = Column(String, ForeignKey("keypoints_v2.id"), nullable=False)
    to_keypoint_id = Column(String, ForeignKey("keypoints_v2.id"), nullable=False)
    relation = Column(String, default="prerequisite")
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)
