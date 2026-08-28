"""Externally configurable runtime settings."""

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchored to the repo root, not the caller's cwd: pydantic-settings resolves a
# relative env_file against the current working directory at instantiation
# time, so running the CLI from any other directory would otherwise silently
# fall back to class defaults (cloud_enabled=False) instead of .env's values.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Settings with local-first safe defaults required by the SDD contracts."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    fast_model: str = "qwen3.5:4b"
    deep_model: str = "qwen3.5:9b"
    coding_model: str = "qwen3.5:9b"
    local_first: bool = True
    cloud_enabled: bool = False
    max_local_retries: int = Field(default=1, ge=0)
    max_local_repairs: int = Field(default=1, ge=0)
    max_cloud_escalations_per_agent: int = Field(default=1, ge=0)
    max_cloud_escalations_per_run: int = Field(default=3, ge=0)
    ollama_base_url: str = "http://localhost:11434"
    llm_timeout_seconds: float = Field(default=60, gt=0)
    ollama_timeout_seconds: float = Field(default=600, gt=0)
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    # Ordered Gemini fallback chain, tried left to right when a model answers with an
    # error. Set GEMINI_MODELS to reorder or extend it. The role's mapped model always
    # leads regardless of where it appears here.
    gemini_models: str = "gemini-3.6-flash,gemini-3.5-flash,gemini-3.1-flash-lite,gemini-2.5-flash"
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LANGFUSE_BASE_URL", "LANGFUSE_HOST"),
    )
    workspace_root: str = "workspace/runs"
    rag_chunk_size: int = Field(default=800, ge=1)
    rag_chunk_overlap: int = Field(default=160, ge=0)
    rag_top_k: int = Field(default=4, ge=1)
    rag_fetch_k: int = Field(default=8, ge=1)
    rag_min_relevance: float = Field(default=0.55, ge=0, le=1)
    rag_persist_directory: str = "rag/chroma"
