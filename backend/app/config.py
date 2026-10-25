from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://candidate:candidate@localhost:5432/candidate"

    # Local LLM served by Ollama. "auto": use the server started by the docker compose llm service
    # (llm/launcher.sh), which writes address, model and accelerator to llm_runtime_file.
    # "ollama": use llm_base_url and llm_model, handy for development without Docker.
    llm_provider: Literal["auto", "ollama"] = "ollama"
    llm_runtime_file: Path = Path("/runtime/llm.json")
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    llm_timeout_seconds: float = 600.0
    llm_num_ctx: int = 8192

    # Embeddings for skill matching
    embedding_model: str = "intfloat/multilingual-e5-small"
    # Cosine similarity thresholds (e5 scores high even for loosely related texts)
    match_threshold: float = 0.90
    partial_match_threshold: float = 0.85

    # Shared with the updater service (docker compose)
    updates_dir: Path = Path("/updates")

    upload_dir: Path = Path("data/uploads")
    max_upload_mb: int = 10

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
