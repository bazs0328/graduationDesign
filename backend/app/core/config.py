from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GradTutor"
    data_dir: str = "data"
    auth_secret_key: str = "gradtutor-dev-secret"
    auth_token_ttl_hours: int = 72
    auth_require_login: bool = True
    auth_allow_legacy_user_id: bool = False

    llm_provider: str = "openai"  # openai, gemini, deepseek, qwen
    embedding_provider: str = "dashscope"  # openai, gemini, deepseek, qwen, dashscope

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    google_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    gemini_embedding_model: str = "text-embedding-004"

    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    deepseek_embedding_model: str | None = None

    qwen_api_key: str | None = None
    qwen_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    qwen_embedding_model: str = "text-embedding-v4"
    dashscope_embedding_model: str = "qwen3-vl-embedding"
    dashscope_base_url: str | None = None  # If None, uses default. Set to "https://dashscope-intl.aliyuncs.com/api/v1" for international

    chunk_size: int = 1000
    chunk_overlap: int = 150
    ocr_enabled: bool = True
    ocr_language: str = "chi_sim+eng"
    ocr_min_text_length: int = 10
    ocr_low_quality_score: int = 45
    ocr_full_scan_empty_ratio: float = 0.60
    ocr_full_scan_low_quality_ratio: float = 0.50
    ocr_page_workers: int = 4
    ocr_batch_size: int = 8

    ingest_workers: int = 4
    ingest_vector_batch_size: int = 64
    doc_parser_enable_docling: bool = True
    rag_default_backend: str = "raganything_mineru"
    rag_query_mode: str = "hybrid"
    rag_fallback_to_legacy: bool = True
    rag_doc_parser_primary: str = "mineru"
    rag_doc_parser_fallback: str = "docling"
    raganything_enabled: bool = True
    raganything_timeout_sec: int = 120

    qa_top_k: int = 4
    qa_fetch_k: int = 12
    qa_bm25_k: int = 6
    rag_mode: str = "hybrid"  # dense, hybrid
    rag_dense_weight: float = 0.7
    rag_bm25_weight: float = 0.3

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
