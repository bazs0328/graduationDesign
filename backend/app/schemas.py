from datetime import datetime
from typing import Any, Dict, List, Optional, Literal

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
    access_token: str
    token_type: str = "bearer"


class QASettings(BaseModel):
    mode: Optional[Literal["normal", "explain"]] = None
    retrieval_preset: Optional[Literal["fast", "balanced", "deep"]] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    fetch_k: Optional[int] = Field(default=None, ge=1, le=50)

    model_config = ConfigDict(extra="forbid")


class QuizSettings(BaseModel):
    count_default: Optional[int] = Field(default=None, ge=1, le=20)
    auto_adapt_default: Optional[bool] = None
    difficulty_default: Optional[Literal["easy", "medium", "hard"]] = None

    model_config = ConfigDict(extra="forbid")


class UISettings(BaseModel):
    show_advanced_controls: Optional[bool] = None
    density: Optional[Literal["comfortable", "compact"]] = None

    model_config = ConfigDict(extra="forbid")


class UploadSettings(BaseModel):
    post_upload_suggestions: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class UserSettingsPayload(BaseModel):
    qa: Optional[QASettings] = None
    quiz: Optional[QuizSettings] = None
    ui: Optional[UISettings] = None
    upload: Optional[UploadSettings] = None

    model_config = ConfigDict(extra="forbid")


class KbSettingsPayload(BaseModel):
    qa: Optional[QASettings] = None
    quiz: Optional[QuizSettings] = None

    model_config = ConfigDict(extra="forbid")


class SettingsPatchRequest(BaseModel):
    user_id: Optional[str] = None
    qa: Optional[QASettings] = None
    quiz: Optional[QuizSettings] = None
    ui: Optional[UISettings] = None
    upload: Optional[UploadSettings] = None

    model_config = ConfigDict(extra="forbid")


class SettingsResetRequest(BaseModel):
    scope: Literal["user", "kb"]
    kb_id: Optional[str] = None
    user_id: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class SettingsSystemStatus(BaseModel):
    llm_provider: str
    embedding_provider: str
    llm_provider_configured: Optional[str] = None
    embedding_provider_configured: Optional[str] = None
    llm_provider_source: Optional[Literal["auto", "manual"]] = None
    embedding_provider_source: Optional[Literal["auto", "manual"]] = None
    qa_defaults_from_env: Dict[str, Any] = {}
    ocr_enabled: bool
    pdf_parser_mode: str
    auth_require_login: bool
    secrets_configured: Dict[str, bool] = {}
    version_info: Dict[str, Any] = {}


class SettingsMeta(BaseModel):
    qa_modes: List[str] = []
    retrieval_presets: List[str] = []
    quiz_difficulty_options: List[str] = []
    preset_map: Dict[str, Dict[str, int]] = {}
    ranges: Dict[str, Dict[str, int]] = {}
    defaults: Dict[str, Any] = {}


class SettingsResponse(BaseModel):
    system_status: SettingsSystemStatus
    user_defaults: UserSettingsPayload
    kb_overrides: Optional[KbSettingsPayload] = None
    effective: UserSettingsPayload
    meta: SettingsMeta


class SystemSettingOption(BaseModel):
    value: Any
    label: str


class SystemSettingField(BaseModel):
    key: str
    label: str
    group: str
    input_type: Literal["switch", "number", "select", "text"]
    nullable: bool = False
    description: Optional[str] = None
    options: List[SystemSettingOption] = []
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None


class SystemSettingGroup(BaseModel):
    id: str
    label: str


class SystemSettingsSchema(BaseModel):
    groups: List[SystemSettingGroup] = []
    fields: List[SystemSettingField] = []


class SystemSettingsResponse(BaseModel):
    editable_keys: List[str] = []
    overrides: Dict[str, Any] = {}
    effective: Dict[str, Any] = {}
    settings_schema: Optional[SystemSettingsSchema] = Field(default=None, alias="schema")

    model_config = ConfigDict(populate_by_name=True)


class SystemSettingsPatchRequest(BaseModel):
    values: Dict[str, Any]

    model_config = ConfigDict(extra="forbid")


class SystemSettingsResetRequest(BaseModel):
    keys: Optional[List[str]] = None

    model_config = ConfigDict(extra="forbid")


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
    retry_count: int = 0
    last_retry_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentPageResponse(BaseModel):
    items: List[DocumentOut] = []
    total: int = 0
    offset: int = 0
    limit: int = 20
    has_more: bool = False


class DocumentTaskCenterResponse(BaseModel):
    processing: List[DocumentOut] = []
    error: List[DocumentOut] = []
    processing_count: int = 0
    error_count: int = 0
    auto_refresh_ms: int = 2000


class DocumentRetryRequest(BaseModel):
    user_id: Optional[str] = None
    doc_ids: Optional[List[str]] = None


class DocumentRetryResponse(BaseModel):
    queued: List[str] = []
    skipped: List[str] = []


class SourcePreviewResponse(BaseModel):
    doc_id: str
    filename: str
    page: Optional[int] = None
    chunk: Optional[int] = None
    source: Optional[str] = None
    snippet: str
    matched_by: str


class DocumentUpdateRequest(BaseModel):
    user_id: Optional[str] = None
    filename: Optional[str] = None
    kb_id: Optional[str] = None


class KnowledgeBaseCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    user_id: Optional[str] = None


class KnowledgeBaseUpdateRequest(BaseModel):
    user_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None


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
    focus: Optional[str] = None  # Target keypoint text from learning path
    mode: Optional[str] = "normal"


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
    mode: Optional[str] = None


QuizQuestionType = Literal[
    "single_choice",
    "multiple_choice",
    "true_false",
    "fill_blank",
]
QuizSectionDifficulty = Literal["easy", "medium", "hard", "adaptive"]


class PaperSectionBlueprint(BaseModel):
    section_id: str
    type: QuizQuestionType
    count: int = Field(default=1, ge=1, le=20)
    score_per_question: float = Field(default=1.0, gt=0.0, le=100.0)
    difficulty: Optional[QuizSectionDifficulty] = None

    model_config = ConfigDict(extra="forbid")


class PaperBlueprint(BaseModel):
    title: str = "自动组卷"
    duration_minutes: int = Field(default=20, ge=5, le=240)
    sections: List[PaperSectionBlueprint] = Field(default_factory=list, min_length=1, max_length=20)

    model_config = ConfigDict(extra="forbid")


class PaperSectionMeta(BaseModel):
    section_id: str
    type: QuizQuestionType
    requested_count: int = 0
    generated_count: int = 0
    score_per_question: float = 1.0
    difficulty: Optional[QuizSectionDifficulty] = None


class PaperMeta(BaseModel):
    title: str = "自动组卷"
    duration_minutes: int = 20
    total_score: float = 0.0
    sections: List[PaperSectionMeta] = []


class QuizGenerateRequest(BaseModel):
    doc_id: Optional[str] = None
    kb_id: Optional[str] = None
    count: int = Field(default=5, ge=1, le=20)
    difficulty: Optional[str] = None
    auto_adapt: bool = True
    user_id: Optional[str] = None
    scope_concepts: Optional[List[str]] = None
    focus_concepts: Optional[List[str]] = None
    style_prompt: Optional[str] = None
    reference_questions: Optional[str] = None
    paper_blueprint: Optional[PaperBlueprint] = None


class QuizQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question_id: str = ""
    type: QuizQuestionType = "single_choice"
    question: str
    options: List[str] = []
    answer: Optional[Any] = None
    answer_index: Optional[int] = None
    answer_indexes: List[int] = []
    answer_bool: Optional[bool] = None
    answer_blanks: List[str] = []
    blank_count: int = 1
    explanation: str
    concepts: List[str] = []
    score: float = 1.0
    section_id: str = "section-1"


class QuizGenerateResponse(BaseModel):
    quiz_id: str
    questions: List[QuizQuestion]
    paper_meta: Optional[PaperMeta] = None


class QuizSubmitRequest(BaseModel):
    quiz_id: str
    answers: List[Any]
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


class MasteryUpdate(BaseModel):
    keypoint_id: str
    text: str
    old_level: float
    new_level: float


class QuizSectionScore(BaseModel):
    section_id: str
    earned: float
    total: float


class QuizQuestionResult(BaseModel):
    question_id: str
    correct: bool
    earned: float
    total: float
    explanation: str


class MasteryGuardStats(BaseModel):
    updated_count: int = 0
    skipped_locked: int = 0
    skipped_missing_binding: int = 0


class QuizSubmitResponse(BaseModel):
    score: float
    correct: int
    total: int
    results: List[bool]
    explanations: List[str]
    total_score: float = 0.0
    earned_score: float = 0.0
    section_scores: List[QuizSectionScore] = []
    question_results: List[QuizQuestionResult] = []
    feedback: Optional[QuizFeedback] = None
    next_quiz_recommendation: Optional[NextQuizRecommendation] = None
    profile_delta: Optional[ProfileDelta] = None
    wrong_questions_by_concept: List[WrongQuestionGroup] = []
    mastery_updates: List[MasteryUpdate] = []
    mastery_guard: Optional[MasteryGuardStats] = None


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
    mastery_avg: float = 0.0
    mastery_completion_rate: float = 0.0
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
    study_keypoint_text: Optional[str] = None  # If provided, record study interaction for matching keypoint


class KeypointItem(BaseModel):
    text: str
    explanation: Optional[str] = None
    source: Optional[str] = None
    page: Optional[int] = None
    chunk: Optional[int] = None


class KeypointSourceRef(BaseModel):
    keypoint_id: str
    doc_id: str
    doc_name: Optional[str] = None
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
    member_count: int = 1
    member_keypoint_ids: List[str] = []
    source_doc_ids: List[str] = []
    source_doc_names: List[str] = []
    source_refs: List[KeypointSourceRef] = []
    grouped: bool = False


class KeypointsResponse(BaseModel):
    doc_id: str
    keypoints: List[KeypointItemV2]
    cached: bool = False
    grouped: bool = False
    raw_count: Optional[int] = None
    group_count: Optional[int] = None


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
    total: int = 0
    offset: int = 0
    limit: int = 20
    has_more: bool = False


class ChatSessionCreateRequest(BaseModel):
    user_id: Optional[str] = None
    name: Optional[str] = None
    kb_id: Optional[str] = None
    doc_id: Optional[str] = None


class ChatSessionUpdateRequest(BaseModel):
    user_id: Optional[str] = None
    name: Optional[str] = None


class ChatSessionOut(BaseModel):
    id: str
    user_id: str
    kb_id: Optional[str] = None
    doc_id: Optional[str] = None
    title: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatSessionPageResponse(BaseModel):
    items: List[ChatSessionOut] = []
    total: int = 0
    offset: int = 0
    limit: int = 20
    has_more: bool = False


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
    priority: int = 0
    cta: Optional[str] = None


class RecommendationItem(BaseModel):
    doc_id: str
    doc_name: Optional[str] = None
    actions: List[RecommendationAction]
    primary_action: Optional[RecommendationAction] = None
    urgency_score: float = 0.0
    completion_score: float = 0.0
    status: str = "needs_attention"
    summary: Optional[str] = None


class RecommendationNextStep(BaseModel):
    doc_id: str
    doc_name: Optional[str] = None
    action: RecommendationAction
    reason: Optional[str] = None


class LearningPathItem(BaseModel):
    keypoint_id: str
    text: str
    doc_id: str
    doc_name: Optional[str] = None
    mastery_level: float
    priority: str
    step: int = 0
    prerequisites: List[str] = []
    prerequisite_ids: List[str] = []
    unmet_prerequisite_ids: List[str] = []
    is_unlocked: bool = True
    action: str = "study"
    stage: str = "foundation"
    module: str = "module-1"
    difficulty: float = 0.5
    importance: float = 0.5
    path_level: int = 0
    unlocks_count: int = 0
    estimated_time: int = 10
    milestone: bool = False
    member_count: int = 1
    source_doc_ids: List[str] = []
    source_doc_names: List[str] = []


class LearningPathEdge(BaseModel):
    from_id: str
    to_id: str
    relation: str = "prerequisite"
    confidence: float = 1.0


class LearningPathStage(BaseModel):
    stage_id: str
    name: str
    description: str
    keypoint_ids: List[str] = []
    milestone_keypoint_id: Optional[str] = None
    estimated_time: int = 0


class LearningPathModule(BaseModel):
    module_id: str
    name: str
    description: str
    keypoint_ids: List[str] = []
    prerequisite_modules: List[str] = []
    estimated_time: int = 0


class RecommendationsResponse(BaseModel):
    kb_id: str
    kb_name: Optional[str] = None
    items: List[RecommendationItem]
    learning_path: List[LearningPathItem] = []
    learning_path_edges: List[LearningPathEdge] = []
    learning_path_stages: List[LearningPathStage] = []
    learning_path_modules: List[LearningPathModule] = []
    learning_path_summary: Dict[str, Any] = {}
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    next_step: Optional[RecommendationNextStep] = None
