"""DuckDB connection and schema initialisation."""
from __future__ import annotations

from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from app.config import Settings


def get_connection(settings: Settings | None = None) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection to the configured database path."""
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    return duckdb.connect(str(settings.db_path))


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create all tables if they do not already exist."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS sample_variants (
            rsid VARCHAR PRIMARY KEY,
            chromosome VARCHAR,
            position BIGINT,
            result VARCHAR,
            source_file VARCHAR,
            build_guess VARCHAR,
            imported_at TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS gwas_assoc (
            id VARCHAR PRIMARY KEY,
            rsid VARCHAR,
            trait VARCHAR,
            p_value VARCHAR,
            odds_ratio VARCHAR,
            beta VARCHAR,
            effect_allele VARCHAR,
            risk_frequency VARCHAR,
            study_accession VARCHAR,
            pubmed_id VARCHAR,
            mapped_gene VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS clinvar_variants (
            variation_id VARCHAR PRIMARY KEY,
            rsid VARCHAR,
            gene_symbol VARCHAR,
            condition_name VARCHAR,
            clinical_significance VARCHAR,
            review_status VARCHAR,
            review_stars INTEGER,
            variation_type VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS findings (
            finding_id VARCHAR PRIMARY KEY,
            rsid VARCHAR,
            genotype VARCHAR,
            source_type VARCHAR,
            evidence_type VARCHAR,
            trait_or_condition VARCHAR,
            effect_allele VARCHAR,
            effect_direction VARCHAR,
            effect_size_type VARCHAR,
            effect_size_value VARCHAR,
            clinical_significance VARCHAR,
            review_status VARCHAR,
            confidence_tier VARCHAR,
            actionability VARCHAR,
            allowed_claims JSON,
            forbidden_claims JSON,
            user_visible_notes JSON,
            source_refs JSON,
            created_at TIMESTAMP
        )
    """)


def reset_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Drop all tables and recreate from scratch."""
    for table in ("findings", "clinvar_variants", "gwas_assoc", "sample_variants"):
        con.execute(f"DROP TABLE IF EXISTS {table}")
    init_schema(con)
