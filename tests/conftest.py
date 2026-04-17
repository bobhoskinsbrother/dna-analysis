"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.config import Settings
from app.db import init_schema


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_csv(fixtures_dir) -> Path:
    return fixtures_dir / "sample_myheritage.csv"


@pytest.fixture
def sample_gwas_tsv(fixtures_dir) -> Path:
    return fixtures_dir / "sample_gwas.tsv"


@pytest.fixture
def sample_clinvar_txt(fixtures_dir) -> Path:
    return fixtures_dir / "sample_clinvar.txt"


@pytest.fixture
def db_connection(tmp_path) -> duckdb.DuckDBPyConnection:
    """Fresh in-memory DuckDB with schema initialised."""
    con = duckdb.connect(":memory:")
    init_schema(con)
    yield con
    con.close()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(db_path=tmp_path / "test.duckdb")
