from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class AuthRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6)
    name: Optional[str] = None


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    user_id: str
    username: str
    name: Optional[str] = None


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
    ability_level: Optional[str] = None


class QuizGenerateRequest(BaseModel):
    doc_id: Optional[str] = None
    kb_id: Optional[str] = None
    count: int = Field(default=5, ge=1, le=20)
    difficulty: Optional[str] = None
    auto_adapt: bool = True
    user_id: Optional[str] = None
    focus_concepts: Optional[List[str]] = None
    style_prompt: Optional[str] = None
    reference_questions: Optional[str] = None


class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    answer_index: int
    explanation: str
    concepts: List[str] = []


class QuizGenerateResponse(BaseModel):
    quiz_id: str
    questions: List[QuizQuestion]


class QuizSubmitRequest(BaseModel):
    quiz_id: str
    answers: List[Optional[int]]
    user_id: Optional[str] = None


class QuizFeedback(BaseModel):
    type: str
    message: str


class NextQuizRecommendation(BaseModel):
    difficulty: str
    focus_concepts: List[str] = []


class ProfileDelta(BaseModel):
    theta_delta: float
    frustration_delta: float
    recent_accuracy_delta: float
    ability_level_changed: bool


class WrongQuestionGroup(BaseModel):
    concept: str
    question_indices: List[int]


class QuizSubmitResponse(BaseModel):
    score: float
    correct: int
    total: int
    results: List[bool]
    explanations: List[str]
    feedback: Optional[QuizFeedback] = None
    next_quiz_recommendation: Optional[NextQuizRecommendation] = None
    profile_delta: Optional[ProfileDelta] = None
    wrong_questions_by_concept: List[WrongQuestionGroup] = []


class DifficultyPlan(BaseModel):
    easy: float
    medium: float
    hard: float
    message: Optional[str] = None


class LearnerProfileOut(BaseModel):
    user_id: str
    ability_level: str
    theta: float
    frustration_score: float
    weak_concepts: List[str]
    recent_accuracy: float
    total_attempts: int
    updated_at: datetime


class ParseReferenceResponse(BaseModel):
    text: str


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


class KeypointItem(BaseModel):
    text: str
    explanation: Optional[str] = None
    source: Optional[str] = None
    page: Optional[int] = None
    chunk: Optional[int] = None


class KeypointItemV2(BaseModel):
    id: str
    text: str
    explanation: Optional[str] = None
    source: Optional[str] = None
    page: Optional[int] = None
    chunk: Optional[int] = None
    mastery_level: float = 0.0
    attempt_count: int = 0
    correct_count: int = 0


class KeypointsResponse(BaseModel):
    doc_id: str
    keypoints: List[KeypointItemV2]
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
    sources: Optional[List[SourceSnippet]] = None  # only assistant messages have value

    model_config = ConfigDict(from_attributes=True)


class RecommendationAction(BaseModel):
    type: str
    reason: Optional[str] = None
    params: Optional[dict] = None


class RecommendationItem(BaseModel):
    doc_id: str
    doc_name: Optional[str] = None
    actions: List[RecommendationAction]


class LearningPathItem(BaseModel):
    keypoint_id: str
    text: str
    doc_id: str
    doc_name: Optional[str] = None
    mastery_level: float
    priority: str


class RecommendationsResponse(BaseModel):
    kb_id: str
    kb_name: Optional[str] = None
    items: List[RecommendationItem]
    learning_path: List[LearningPathItem] = []
