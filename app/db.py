"""DuckDB connection and schema initialisation."""
from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from app.config import Settings
    from app.models import Finding, SourceRef


def get_connection(settings: Settings | None = None) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection to the configured database path."""
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    con = duckdb.connect(str(settings.db_path))
    con.execute("SET memory_limit = '4GB'")
    con.execute("SET threads = 2")
    con.execute("SET preserve_insertion_order = false")
    return con


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


def get_finding_by_id(
    con: duckdb.DuckDBPyConnection,
    finding_id: str,
) -> Finding | None:
    """Fetch a single Finding by its UUID, or None if not found."""
    from app.models import Finding, SourceRef

    row = con.execute(
        "SELECT * FROM findings WHERE finding_id = ? OR finding_id LIKE ? || '%'",
        [finding_id, finding_id],
    ).fetchone()
    if row is None:
        return None

    columns = [desc[0] for desc in con.description]
    row_dict = dict(zip(columns, row))

    for col in ("allowed_claims", "forbidden_claims", "user_visible_notes"):
        row_dict[col] = json.loads(row_dict[col])

    raw_refs = json.loads(row_dict["source_refs"])
    row_dict["source_refs"] = [SourceRef(**r) for r in raw_refs]

    raw_ts = row_dict["created_at"]
    if isinstance(raw_ts, str):
        row_dict["created_at"] = datetime.fromisoformat(raw_ts)
    # else: DuckDB already returned a datetime object

    return Finding(**row_dict)
