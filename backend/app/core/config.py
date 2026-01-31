from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GradTutor"
    data_dir: str = "data"

    llm_provider: str = "openai"  # openai, gemini, deepseek
    embedding_provider: str = "openai"  # openai, gemini, deepseek, bgem3

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

    bge_m3_model: str = "BAAI/bge-m3"
    embeddings_device: str = "cpu"

    chunk_size: int = 1000
    chunk_overlap: int = 150

    qa_top_k: int = 4
    qa_fetch_k: int = 12
    qa_bm25_k: int = 6
    rag_mode: str = "hybrid"  # dense, hybrid
    rag_dense_weight: float = 0.7
    rag_bm25_weight: float = 0.3

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
