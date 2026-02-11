from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/rav_itamar"
    database_url_sync: str = "postgresql://postgres:postgres@localhost:5432/rav_itamar"

    # Storage
    storage_backend: str = "local"  # "local" or "s3"
    local_storage_path: str = "./storage/pdfs"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # LLM backend: "ollama" (default, no API key) or "openai"
    llm_backend: str = "ollama"

    # Ollama settings (local, no API key needed)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # OpenAI settings (only used if llm_backend="openai")
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Embeddings: local sentence-transformers (no API key needed)
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimensions: int = 384

    # Chunking
    chunk_size_tokens: int = 900
    chunk_overlap_tokens: int = 100

    # Retrieval
    top_k: int = 8
    evidence_budget_tokens: int = 10000
    relevance_threshold: float = 0.3

    # Restudy
    restudy_interval_sessions: int = 7
    restudy_top_principles: int = 30
    restudy_scenario_tests: int = 10

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
