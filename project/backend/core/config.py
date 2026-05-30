"""Pydantic Settings configuration for the Agent system."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _resolve_sqlite_url(url: str) -> str:
    """Resolve relative SQLite database URLs against the backend directory."""
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if not url.startswith(prefix):
            continue
        db_path = url[len(prefix):]
        if not db_path or db_path == ":memory:":
            return url
        path = Path(db_path)
        if path.is_absolute():
            return url
        return f"{prefix}{(BACKEND_DIR / path).resolve().as_posix()}"
    return url


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://user:pass@localhost:5432/agent_db",
        alias="DATABASE_URL",
    )

    # Model API Keys
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_api_base: str = Field(
        default="https://api.deepseek.com",
        alias="DEEPSEEK_API_BASE",
    )
    kimi_api_key: str = Field(default="", alias="KIMI_API_KEY")
    kimi_api_base: str = Field(
        default="https://api.moonshot.cn/v1",
        alias="KIMI_API_BASE",
    )
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Workspace
    workspace_root: str = Field(
        default="/mnt/agents/output/project/workspaces",
        alias="WORKSPACE_ROOT",
    )
    workspace_local_cache: str = Field(
        default="/mnt/agents/output/project/workspace_cache",
        alias="WORKSPACE_LOCAL_CACHE",
    )

    # Optional: Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )

    # Optional: Sentry
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Security
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        alias="SECRET_KEY",
    )
    access_token_expire_minutes: int = Field(
        default=60 * 24 * 7,  # 7 days
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    # Server
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    reload: bool = Field(default=False, alias="RELOAD")

    @property
    def async_database_url(self) -> str:
        """Ensure async driver is used."""
        url = _resolve_sqlite_url(self.database_url)
        if url.startswith("sqlite:///"):
            url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        if url.startswith("postgresql://") and "asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def sync_database_url(self) -> str:
        """Get sync database URL for Alembic."""
        url = _resolve_sqlite_url(self.database_url)
        if url.startswith("sqlite+aiosqlite:///"):
            url = url.replace("sqlite+aiosqlite:///", "sqlite:///", 1)
        if "asyncpg" in url:
            url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
        return url


# Global settings instance
settings = Settings()


# ---------------------------------------------------------------------------
# Model Configurations (SPEC.md Section 8)
# ---------------------------------------------------------------------------

class ModelConfig(BaseModel):
    """Configuration for a specific model."""

    provider: str
    context_window: int
    max_output_tokens: int
    supports_vision: bool
    supports_json_mode: bool
    supports_thinking: bool
    supports_context_cache: bool
    default_thinking_effort: str = "high"


MODEL_CONFIGS: dict[str, ModelConfig] = {
    "deepseek-v4-pro": ModelConfig(
        provider="deepseek",
        context_window=1_000_000,
        max_output_tokens=8192,
        supports_vision=False,
        supports_json_mode=True,
        supports_thinking=True,
        supports_context_cache=True,
        default_thinking_effort="max",
    ),
    "deepseek-v4-flash": ModelConfig(
        provider="deepseek",
        context_window=1_000_000,
        max_output_tokens=8192,
        supports_vision=False,
        supports_json_mode=True,
        supports_thinking=True,
        supports_context_cache=True,
        default_thinking_effort="high",
    ),
    "kimi-k2-6": ModelConfig(
        provider="kimi",
        context_window=256_000,
        max_output_tokens=8192,
        supports_vision=True,
        supports_json_mode=True,
        supports_thinking=True,
        supports_context_cache=True,
        default_thinking_effort="high",
    ),
    "kimi-k2-5": ModelConfig(
        provider="kimi",
        context_window=256_000,
        max_output_tokens=8192,
        supports_vision=True,
        supports_json_mode=True,
        supports_thinking=True,
        supports_context_cache=True,
        default_thinking_effort="high",
    ),
}


# ---------------------------------------------------------------------------
# Context Profile Configurations (SPEC.md Section 7)
# ---------------------------------------------------------------------------

class ContextProfile(BaseModel):
    """Context profile defining resource allocation strategy."""

    max_input_tokens: int
    recent_turns: int
    tool_result_mode: str  # "summary" | "hybrid" | "verbose"
    multimodal_mode: str  # "caption_only" | "caption_plus_refs" | "rich"
    memory_recall_top_k: int
    compression_strategy: str  # "aggressive" | "balanced" | "minimal"


CONTEXT_PROFILES: dict[str, ContextProfile] = {
    "cheap": ContextProfile(
        max_input_tokens=32000,
        recent_turns=6,
        tool_result_mode="summary",
        multimodal_mode="caption_only",
        memory_recall_top_k=5,
        compression_strategy="aggressive",
    ),
    "balanced": ContextProfile(
        max_input_tokens=96000,
        recent_turns=16,
        tool_result_mode="hybrid",
        multimodal_mode="caption_plus_refs",
        memory_recall_top_k=12,
        compression_strategy="balanced",
    ),
    "max": ContextProfile(
        max_input_tokens=256000,
        recent_turns=50,
        tool_result_mode="verbose",
        multimodal_mode="rich",
        memory_recall_top_k=30,
        compression_strategy="minimal",
    ),
    "custom": ContextProfile(
        max_input_tokens=96000,
        recent_turns=16,
        tool_result_mode="hybrid",
        multimodal_mode="caption_plus_refs",
        memory_recall_top_k=12,
        compression_strategy="balanced",
    ),
}


def get_model_config(model_id: str) -> ModelConfig:
    """Get model configuration by model ID."""
    if model_id not in MODEL_CONFIGS:
        raise ValueError(f"Unknown model: {model_id}")
    return MODEL_CONFIGS[model_id]


def get_context_profile(name: str) -> ContextProfile:
    """Get context profile by name."""
    if name not in CONTEXT_PROFILES:
        raise ValueError(f"Unknown context profile: {name}")
    return CONTEXT_PROFILES[name]
