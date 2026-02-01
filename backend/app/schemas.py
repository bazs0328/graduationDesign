from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class DocumentOut(BaseModel):
    id: str
    user_id: str
    kb_id: Optional[str] = None
    filename: str
    file_type: str
    num_chunks: int
    num_pages: int
    char_count: int
    status: Optional[str] = None
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeBaseCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    user_id: Optional[str] = None


class KnowledgeBaseOut(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SummaryRequest(BaseModel):
    doc_id: str
    user_id: Optional[str] = None
    force: bool = False


class SummaryResponse(BaseModel):
    doc_id: str
    summary: str
    cached: bool = False


class QARequest(BaseModel):
    doc_id: Optional[str] = None
    kb_id: Optional[str] = None
    session_id: Optional[str] = None
    question: str
    user_id: Optional[str] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    fetch_k: Optional[int] = Field(default=None, ge=1, le=50)


class SourceSnippet(BaseModel):
    source: str
    snippet: str
    doc_id: Optional[str] = None
    kb_id: Optional[str] = None
    page: Optional[int] = None
    chunk: Optional[int] = None


class QAResponse(BaseModel):
    answer: str
    sources: List[SourceSnippet] = []
    session_id: Optional[str] = None


class QuizGenerateRequest(BaseModel):
    doc_id: str
    count: int = Field(default=5, ge=1, le=20)
    difficulty: str = Field(default="medium")
    user_id: Optional[str] = None


class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    answer_index: int
    explanation: str


class QuizGenerateResponse(BaseModel):
    quiz_id: str
    questions: List[QuizQuestion]


class QuizSubmitRequest(BaseModel):
    quiz_id: str
    answers: List[Optional[int]]
    user_id: Optional[str] = None


class QuizSubmitResponse(BaseModel):
    score: float
    correct: int
    total: int
    results: List[bool]
    explanations: List[str]


class ProgressByKb(BaseModel):
    kb_id: str
    kb_name: Optional[str] = None
    total_docs: int
    total_quizzes: int
    total_attempts: int
    total_questions: int
    total_summaries: int
    total_keypoints: int
    avg_score: float
    last_activity: Optional[datetime]


class ProgressResponse(BaseModel):
    total_docs: int
    total_quizzes: int
    total_attempts: int
    total_questions: int
    total_summaries: int
    total_keypoints: int
    avg_score: float
    last_activity: Optional[datetime]
    by_kb: List[ProgressByKb] = []


class KeypointsRequest(BaseModel):
    doc_id: str
    user_id: Optional[str] = None
    force: bool = False


class KeypointsResponse(BaseModel):
    doc_id: str
    keypoints: List[str]
    cached: bool = False


class ActivityItem(BaseModel):
    type: str
    timestamp: datetime
    doc_id: Optional[str] = None
    doc_name: Optional[str] = None
    detail: Optional[str] = None
    score: Optional[float] = None
    total: Optional[int] = None


class ActivityResponse(BaseModel):
    items: List[ActivityItem]


class ChatSessionCreateRequest(BaseModel):
    user_id: Optional[str] = None
    name: Optional[str] = None
    kb_id: Optional[str] = None
    doc_id: Optional[str] = None


class ChatSessionOut(BaseModel):
    id: str
    user_id: str
    kb_id: Optional[str] = None
    doc_id: Optional[str] = None
    title: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatMessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecommendationAction(BaseModel):
    type: str
    reason: Optional[str] = None


class RecommendationItem(BaseModel):
    doc_id: str
    doc_name: Optional[str] = None
    actions: List[RecommendationAction]


class RecommendationsResponse(BaseModel):
    kb_id: str
    kb_name: Optional[str] = None
    items: List[RecommendationItem]
