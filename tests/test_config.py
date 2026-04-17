"""Unit tests for app/config.py — application settings."""
from __future__ import annotations

from pathlib import Path

import pytest

from pydantic import ValidationError

from app.config import Settings, get_settings


# ---------------------------------------------------------------------------
# U8: Default settings
# ---------------------------------------------------------------------------

class TestDefaultSettings:
    def test_default_db_path(self):
        settings = Settings()
        assert settings.db_path == Path("dna_analysis.duckdb")

    def test_default_batch_size(self):
        settings = Settings()
        assert settings.batch_size == 10_000


# ---------------------------------------------------------------------------
# U9: Settings from environment variables
# ---------------------------------------------------------------------------

class TestSettingsFromEnv:
    def test_db_path_from_env(self, monkeypatch):
        monkeypatch.setenv("DNA_DB_PATH", "/tmp/test.db")
        settings = Settings()
        assert settings.db_path == Path("/tmp/test.db")

    def test_batch_size_from_env(self, monkeypatch):
        monkeypatch.setenv("DNA_BATCH_SIZE", "5000")
        settings = Settings()
        assert settings.batch_size == 5000

    def test_get_settings_returns_settings_instance(self):
        result = get_settings()
        assert isinstance(result, Settings)


# ---------------------------------------------------------------------------
# BVA: Settings boundary values
# ---------------------------------------------------------------------------

class TestSettingsBVA:
    """Boundary value analysis for Settings."""

    def test_batch_size_default(self):
        """Default batch_size is 10_000."""
        s = Settings(db_path=Path("/tmp/test.duckdb"))
        assert s.batch_size == 10_000

    def test_batch_size_one(self):
        """batch_size=1 is a valid minimum."""
        s = Settings(db_path=Path("/tmp/test.duckdb"), batch_size=1)
        assert s.batch_size == 1

    def test_batch_size_zero(self):
        """batch_size=0 is accepted by Settings (no validation)."""
        s = Settings(db_path=Path("/tmp/test.duckdb"), batch_size=0)
        assert s.batch_size == 0

    def test_llm_model_default(self):
        """Default llm_model is gpt-4o-mini."""
        s = Settings(db_path=Path("/tmp/test.duckdb"))
        assert s.llm_model == "gpt-4o-mini"

    def test_llm_api_base_default_none(self):
        """Default llm_api_base is None."""
        s = Settings(db_path=Path("/tmp/test.duckdb"))
        assert s.llm_api_base is None

    def test_llm_api_key_default(self):
        """Default llm_api_key is 'not-set'."""
        s = Settings(db_path=Path("/tmp/test.duckdb"))
        assert s.llm_api_key == "not-set"


# ---------------------------------------------------------------------------
# Wrong-type: Settings type rejection
# ---------------------------------------------------------------------------

class TestSettingsWrongType:
    """Wrong-type coverage for Settings."""

    def test_batch_size_non_numeric_string(self):
        """Non-numeric string for batch_size should raise ValidationError."""
        with pytest.raises(ValidationError):
            Settings(db_path=Path("/tmp/test.duckdb"), batch_size="not_a_number")

    def test_db_path_int(self):
        """Int db_path should raise ValidationError."""
        with pytest.raises(ValidationError):
            Settings(db_path=12345)
