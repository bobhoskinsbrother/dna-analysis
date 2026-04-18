"""Central configuration loaded from environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with DNA_ environment variable prefix."""

    db_path: Path = Path("dna_analysis.duckdb")
    default_build: str = "GRCh37"
    batch_size: int = 10_000
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key: str = "not-set"

    model_config = {"env_prefix": "DNA_"}


def get_settings() -> Settings:
    """Return a Settings instance."""
    return Settings()
