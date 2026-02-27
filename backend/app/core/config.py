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
    index_text_cleanup_enabled: bool = True
    index_text_cleanup_mode: str = "conservative"
    ocr_enabled: bool = True
    ocr_engine: str = "rapidocr"
    ocr_fallback_engines: str = "rapidocr"
    ocr_language: str = "chi_sim+eng"
    ocr_tesseract_language: str | None = None
    ocr_min_text_length: int = 10
    ocr_render_dpi: int = 360
    ocr_check_pages: int = 3
    ocr_preprocess_enabled: bool = True
    ocr_deskew_enabled: bool = True
    ocr_low_confidence_threshold: float = 0.78
    pdf_parser_mode: str = "auto"
    pdf_layout_engine: str = "pymupdf"
    pdf_garbled_ocr_enabled: bool = True
    pdf_garbled_ocr_force: bool = True
    pdf_garbled_ocr_min_len_ratio: float = 0.30
    pdf_garbled_single_char_line_ratio: float = 0.45
    pdf_garbled_short_line_ratio: float = 0.65
    pdf_extract_images: bool = True
    pdf_image_min_area_ratio: float = 0.01
    pdf_image_max_per_page: int = 12
    mm_image_index_enabled: bool = True
    mm_image_collection_name: str = "documents_images"

    quiz_context_reconstruct_enabled: bool = True
    quiz_context_seed_k_multiplier: float = 2.0
    quiz_context_neighbor_window: int = 2
    quiz_context_passage_target_chars: int = 900
    quiz_context_fragment_filter_enabled: bool = True
    quiz_image_figure_ref_rerank_enabled: bool = True
    quiz_image_figure_ref_top_k: int = 5

    qa_top_k: int = 4
    qa_fetch_k: int = 12
    qa_bm25_k: int = 6
    rag_mode: str = "hybrid"  # dense, hybrid
    rag_dense_weight: float = 0.7
    rag_bm25_weight: float = 0.3

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
