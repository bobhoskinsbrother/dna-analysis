"""Unit tests for app/config.py — application settings."""
from __future__ import annotations

from pathlib import Path

import pytest

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
