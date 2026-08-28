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
    # Ordered Gemini pool, tried left to right. Position 1 leads; the cross-provider
    # escape is inserted at position 2 by CloudRouter where it is viable.
    #
    # Ordered by what was measured against this account, not by version number.
    # Verified answering: gemini-3.6-flash and gemini-3.5-flash.
    # Currently never answering, kept after the proven ones so they cost nothing while
    # down and get used if they recover: 3.7-flash and flash-latest (HTTP 503 on six
    # probes), the pro tier (HTTP 429 on every probe and in a live run).
    # Removed outright: gemini-2.5-flash returns HTTP 404 "no longer available to new
    # users" for every request shape, and gemini-3.1-flash-lite failed schema
    # validation on 40% of the responses it did deliver.
    gemini_models: str = (
        "gemini-3.6-flash,gemini-3.5-flash,gemini-3.7-flash,gemini-flash-latest"
    )
    # The Developer carries the hardest contract, so the pro tier stays in its pool —
    # but behind the two models that actually answer, because leading with a model that
    # returns 429 on every call spends a round trip per run for nothing.
    gemini_developer_models: str = (
        "gemini-3.6-flash,gemini-3.5-flash,gemini-3.1-pro-preview,"
        "gemini-pro-latest,gemini-3.7-flash"
    )
    # Sits at position 2 of a Google chain. Gemini quota is per project, so a 429 on one
    # Gemini model predicts a 429 on the next; leaving the provider is what recovers it.
    cloud_escape_model: str = "openai/gpt-oss-120b"
    # Roles whose payload is too large for the escape provider. Groq's on_demand tier
    # rejects requests above its tokens-per-minute cap with HTTP 413 from about 8k
    # tokens up, and the Developer ships file contents, so for that role the escape is
    # a guaranteed wasted attempt.
    cloud_escape_excluded_roles: str = "developer"
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
