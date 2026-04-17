"""Functional tests for app/db.py -- schema initialization and reset."""
from __future__ import annotations

import duckdb
import pytest

from app.db import get_connection, init_schema, reset_schema


# ---------------------------------------------------------------------------
# F1: init_schema creates all required tables
# ---------------------------------------------------------------------------

class TestInitSchemaCreatesTables:
    def test_all_tables_exist(self, db_connection):
        """init_schema creates sample_variants, gwas_assoc, clinvar_variants, findings."""
        result = db_connection.execute("SHOW TABLES").fetchall()
        table_names = {row[0] for row in result}

        assert "sample_variants" in table_names
        assert "gwas_assoc" in table_names
        assert "clinvar_variants" in table_names
        assert "findings" in table_names

    def test_exactly_four_core_tables(self, db_connection):
        """At minimum the four core tables exist."""
        result = db_connection.execute("SHOW TABLES").fetchall()
        table_names = {row[0] for row in result}
        expected = {"sample_variants", "gwas_assoc", "clinvar_variants", "findings"}
        assert expected.issubset(table_names)


# ---------------------------------------------------------------------------
# F2: init_schema is idempotent (call twice, no error)
# ---------------------------------------------------------------------------

class TestInitSchemaIdempotent:
    def test_double_init_no_error(self):
        """Calling init_schema twice on the same connection must not raise."""
        con = duckdb.connect(":memory:")
        init_schema(con)
        init_schema(con)  # second call should not raise

        result = con.execute("SHOW TABLES").fetchall()
        table_names = {row[0] for row in result}
        assert "sample_variants" in table_names
        assert "gwas_assoc" in table_names
        assert "clinvar_variants" in table_names
        assert "findings" in table_names
        con.close()

    def test_data_preserved_across_double_init(self):
        """Existing data must survive a second init_schema call."""
        con = duckdb.connect(":memory:")
        init_schema(con)
        con.execute(
            "INSERT INTO sample_variants (rsid, chromosome, position, result, source_file) "
            "VALUES ('rs1', '1', 100, 'AA', 'test.csv')"
        )
        init_schema(con)  # second call
        count = con.execute("SELECT COUNT(*) FROM sample_variants").fetchone()[0]
        assert count == 1
        con.close()


# ---------------------------------------------------------------------------
# F3: Table columns match spec for each table
# ---------------------------------------------------------------------------

class TestTableColumnsMatchSpec:
    """Verify column names and types against the schema defined in agents.md."""

    def _get_columns(self, con, table_name: str) -> dict[str, str]:
        """Return {column_name: column_type} for a table using DESCRIBE."""
        rows = con.execute(f"DESCRIBE {table_name}").fetchall()
        return {row[0]: row[1] for row in rows}

    def test_sample_variants_columns(self, db_connection):
        cols = self._get_columns(db_connection, "sample_variants")
        expected = {
            "rsid": "VARCHAR",
            "chromosome": "VARCHAR",
            "position": "BIGINT",
            "result": "VARCHAR",
            "source_file": "VARCHAR",
            "build_guess": "VARCHAR",
            "imported_at": "TIMESTAMP",
        }
        for col_name, col_type in expected.items():
            assert col_name in cols, f"Missing column: {col_name}"
            assert cols[col_name] == col_type, (
                f"Column {col_name}: expected {col_type}, got {cols[col_name]}"
            )

    def test_gwas_assoc_columns(self, db_connection):
        cols = self._get_columns(db_connection, "gwas_assoc")
        expected = {
            "id": "VARCHAR",
            "rsid": "VARCHAR",
            "trait": "VARCHAR",
            "p_value": "VARCHAR",
            "odds_ratio": "VARCHAR",
            "beta": "VARCHAR",
            "effect_allele": "VARCHAR",
            "risk_frequency": "VARCHAR",
            "study_accession": "VARCHAR",
            "pubmed_id": "VARCHAR",
            "mapped_gene": "VARCHAR",
        }
        for col_name, col_type in expected.items():
            assert col_name in cols, f"Missing column: {col_name}"
            assert cols[col_name] == col_type, (
                f"Column {col_name}: expected {col_type}, got {cols[col_name]}"
            )

    def test_clinvar_variants_columns(self, db_connection):
        cols = self._get_columns(db_connection, "clinvar_variants")
        expected = {
            "variation_id": "VARCHAR",
            "rsid": "VARCHAR",
            "gene_symbol": "VARCHAR",
            "condition_name": "VARCHAR",
            "clinical_significance": "VARCHAR",
            "review_status": "VARCHAR",
            "review_stars": "INTEGER",
            "variation_type": "VARCHAR",
        }
        for col_name, col_type in expected.items():
            assert col_name in cols, f"Missing column: {col_name}"
            assert cols[col_name] == col_type, (
                f"Column {col_name}: expected {col_type}, got {cols[col_name]}"
            )

    def test_findings_columns(self, db_connection):
        cols = self._get_columns(db_connection, "findings")
        expected = {
            "finding_id": "VARCHAR",
            "rsid": "VARCHAR",
            "genotype": "VARCHAR",
            "source_type": "VARCHAR",
            "evidence_type": "VARCHAR",
            "trait_or_condition": "VARCHAR",
            "effect_allele": "VARCHAR",
            "effect_direction": "VARCHAR",
            "effect_size_type": "VARCHAR",
            "effect_size_value": "VARCHAR",
            "clinical_significance": "VARCHAR",
            "review_status": "VARCHAR",
            "confidence_tier": "VARCHAR",
            "actionability": "VARCHAR",
            "allowed_claims": "JSON",
            "forbidden_claims": "JSON",
            "user_visible_notes": "JSON",
            "source_refs": "JSON",
            "created_at": "TIMESTAMP",
        }
        for col_name, col_type in expected.items():
            assert col_name in cols, f"Missing column: {col_name}"
            assert cols[col_name] == col_type, (
                f"Column {col_name}: expected {col_type}, got {cols[col_name]}"
            )

    def test_sample_variants_no_extra_columns(self, db_connection):
        cols = self._get_columns(db_connection, "sample_variants")
        expected_names = {
            "rsid", "chromosome", "position", "result",
            "source_file", "build_guess", "imported_at",
        }
        assert set(cols.keys()) == expected_names

    def test_gwas_assoc_no_extra_columns(self, db_connection):
        cols = self._get_columns(db_connection, "gwas_assoc")
        expected_names = {
            "id", "rsid", "trait", "p_value", "odds_ratio", "beta",
            "effect_allele", "risk_frequency", "study_accession",
            "pubmed_id", "mapped_gene",
        }
        assert set(cols.keys()) == expected_names

    def test_clinvar_variants_no_extra_columns(self, db_connection):
        cols = self._get_columns(db_connection, "clinvar_variants")
        expected_names = {
            "variation_id", "rsid", "gene_symbol", "condition_name",
            "clinical_significance", "review_status", "review_stars",
            "variation_type",
        }
        assert set(cols.keys()) == expected_names

    def test_findings_no_extra_columns(self, db_connection):
        cols = self._get_columns(db_connection, "findings")
        expected_names = {
            "finding_id", "rsid", "genotype", "source_type", "evidence_type",
            "trait_or_condition", "effect_allele", "effect_direction",
            "effect_size_type", "effect_size_value", "clinical_significance",
            "review_status", "confidence_tier", "actionability",
            "allowed_claims", "forbidden_claims", "user_visible_notes",
            "source_refs", "created_at",
        }
        assert set(cols.keys()) == expected_names


# ---------------------------------------------------------------------------
# F4: reset_schema drops and recreates (insert a row, reset, table empty)
# ---------------------------------------------------------------------------

class TestResetSchema:
    def test_reset_clears_data(self):
        """Insert a row, reset, table exists but is empty."""
        con = duckdb.connect(":memory:")
        init_schema(con)

        con.execute(
            "INSERT INTO sample_variants (rsid, chromosome, position, result, source_file) "
            "VALUES ('rs1', '1', 100, 'AA', 'test.csv')"
        )
        count_before = con.execute("SELECT COUNT(*) FROM sample_variants").fetchone()[0]
        assert count_before == 1

        reset_schema(con)

        # Tables should still exist
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        assert "sample_variants" in tables

        # But data should be gone
        count_after = con.execute("SELECT COUNT(*) FROM sample_variants").fetchone()[0]
        assert count_after == 0
        con.close()

    def test_reset_clears_all_tables(self):
        """All four tables are empty after reset."""
        con = duckdb.connect(":memory:")
        init_schema(con)

        con.execute(
            "INSERT INTO sample_variants (rsid, chromosome, position, result, source_file) "
            "VALUES ('rs1', '1', 100, 'AA', 'test.csv')"
        )
        con.execute(
            "INSERT INTO gwas_assoc (id, rsid, trait) VALUES ('g1', 'rs1', 'test trait')"
        )
        con.execute(
            "INSERT INTO clinvar_variants (variation_id, rsid) VALUES ('v1', 'rs1')"
        )

        reset_schema(con)

        for table in ["sample_variants", "gwas_assoc", "clinvar_variants", "findings"]:
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, f"Table {table} should be empty after reset"
        con.close()
