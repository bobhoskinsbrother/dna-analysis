"""Functional tests for app/db.py -- schema initialization and reset."""
from __future__ import annotations

import json

import duckdb
import pytest

from app.db import get_connection, init_schema, reset_schema
from app.models import Finding, SourceRef


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


# ---------------------------------------------------------------------------
# F5: get_finding_by_id retrieves and deserializes a Finding
# ---------------------------------------------------------------------------

def _insert_sample_finding(con, finding_id: str = "test-uuid-123") -> None:
    """Insert a well-known Finding row for test purposes."""
    con.execute(
        """INSERT INTO findings
        (finding_id, rsid, genotype, source_type, evidence_type,
         trait_or_condition, effect_allele, effect_direction,
         effect_size_type, effect_size_value, clinical_significance,
         review_status, confidence_tier, actionability,
         allowed_claims, forbidden_claims, user_visible_notes,
         source_refs, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            finding_id, "rs429358", "CT", "gwas", "association",
            "Alzheimer's disease", "T", "increased", "odds_ratio", "1.18",
            None, None, "medium", "none",
            json.dumps(["association_only", "not_diagnostic", "relative_odds_description"]),
            json.dumps(["diagnosis", "absolute_risk_estimate", "treatment_recommendation"]),
            json.dumps(["This is a population-level association.", "A single SNP explains only a small part."]),
            json.dumps([{"type": "gwas", "id": "GCST000001"}, {"type": "pubmed", "id": "19734902"}]),
            "2025-01-01T00:00:00+00:00",
        ],
    )


class TestGetFindingById:
    def test_get_finding_by_id_returns_finding(self, db_connection):
        """Retrieving an existing finding returns a Finding instance with correct fields."""
        from app.db import get_finding_by_id

        _insert_sample_finding(db_connection)
        result = get_finding_by_id(db_connection, "test-uuid-123")

        assert result is not None
        assert isinstance(result, Finding)
        assert result.finding_id == "test-uuid-123"
        assert result.rsid == "rs429358"
        assert result.genotype == "CT"
        assert result.source_type == "gwas"
        assert result.evidence_type == "association"
        assert result.trait_or_condition == "Alzheimer's disease"
        assert result.effect_allele == "T"
        assert result.effect_direction == "increased"
        assert result.effect_size_type == "odds_ratio"
        assert result.effect_size_value == "1.18"
        assert result.confidence_tier == "medium"
        assert result.actionability == "none"

    def test_get_finding_by_id_not_found_returns_none(self, db_connection):
        """Looking up a nonexistent finding_id returns None."""
        from app.db import get_finding_by_id

        result = get_finding_by_id(db_connection, "nonexistent-uuid")
        assert result is None

    def test_get_finding_by_id_json_fields_deserialized(self, db_connection):
        """JSON columns are deserialized into proper Python types."""
        from app.db import get_finding_by_id

        _insert_sample_finding(db_connection)
        finding = get_finding_by_id(db_connection, "test-uuid-123")

        assert finding is not None

        # allowed_claims is a list of strings
        assert isinstance(finding.allowed_claims, list)
        assert all(isinstance(c, str) for c in finding.allowed_claims)
        assert "association_only" in finding.allowed_claims
        assert "not_diagnostic" in finding.allowed_claims
        assert "relative_odds_description" in finding.allowed_claims

        # forbidden_claims is a list of strings
        assert isinstance(finding.forbidden_claims, list)
        assert all(isinstance(c, str) for c in finding.forbidden_claims)
        assert "diagnosis" in finding.forbidden_claims
        assert "absolute_risk_estimate" in finding.forbidden_claims
        assert "treatment_recommendation" in finding.forbidden_claims

        # user_visible_notes is a list of strings
        assert isinstance(finding.user_visible_notes, list)
        assert all(isinstance(n, str) for n in finding.user_visible_notes)
        assert len(finding.user_visible_notes) == 2

        # source_refs is a list of SourceRef objects
        assert isinstance(finding.source_refs, list)
        assert len(finding.source_refs) == 2
        assert all(isinstance(ref, SourceRef) for ref in finding.source_refs)
        assert finding.source_refs[0].type == "gwas"
        assert finding.source_refs[0].id == "GCST000001"
        assert finding.source_refs[1].type == "pubmed"
        assert finding.source_refs[1].id == "19734902"


# ---------------------------------------------------------------------------
# BVA: Boundary value analysis for get_finding_by_id
# ---------------------------------------------------------------------------

class TestGetFindingByIdBVA:
    def test_empty_string_finding_id(self, db_connection):
        """Empty string finding_id should return None without crashing."""
        from app.db import get_finding_by_id

        result = get_finding_by_id(db_connection, "")
        assert result is None

    def test_finding_with_null_optional_fields(self, db_connection):
        """Finding with NULL optional fields should deserialize those as None."""
        from app.db import get_finding_by_id

        db_connection.execute(
            """INSERT INTO findings
            (finding_id, rsid, genotype, source_type, evidence_type,
             trait_or_condition, effect_allele, effect_direction,
             effect_size_type, effect_size_value, clinical_significance,
             review_status, confidence_tier, actionability,
             allowed_claims, forbidden_claims, user_visible_notes,
             source_refs, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "null-fields-uuid", "rs111111", "GG", "gwas", "association",
                "Test trait", None, "unclear", "none", None,
                None, None, "low", "none",
                json.dumps([]), json.dumps([]), json.dumps([]),
                json.dumps([]),
                "2025-01-01T00:00:00+00:00",
            ],
        )

        finding = get_finding_by_id(db_connection, "null-fields-uuid")
        assert finding is not None
        assert finding.clinical_significance is None
        assert finding.review_status is None
        assert finding.effect_allele is None
        assert finding.effect_size_value is None

    def test_finding_with_empty_json_arrays(self, db_connection):
        """Finding with empty JSON arrays should deserialize to empty lists."""
        from app.db import get_finding_by_id

        db_connection.execute(
            """INSERT INTO findings
            (finding_id, rsid, genotype, source_type, evidence_type,
             trait_or_condition, effect_allele, effect_direction,
             effect_size_type, effect_size_value, clinical_significance,
             review_status, confidence_tier, actionability,
             allowed_claims, forbidden_claims, user_visible_notes,
             source_refs, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "empty-arrays-uuid", "rs111111", "GG", "gwas", "association",
                "Test trait", None, "unclear", "none", None,
                None, None, "low", "none",
                json.dumps([]), json.dumps([]), json.dumps([]),
                json.dumps([]),
                "2025-01-01T00:00:00+00:00",
            ],
        )

        finding = get_finding_by_id(db_connection, "empty-arrays-uuid")
        assert finding is not None
        assert finding.allowed_claims == []
        assert finding.forbidden_claims == []
        assert finding.user_visible_notes == []
        assert finding.source_refs == []

    def test_finding_with_special_characters_in_trait(self, db_connection):
        """Trait with special characters should round-trip correctly."""
        from app.db import get_finding_by_id

        special_trait = "Alzheimer's \"disease\" <test>"
        db_connection.execute(
            """INSERT INTO findings
            (finding_id, rsid, genotype, source_type, evidence_type,
             trait_or_condition, effect_allele, effect_direction,
             effect_size_type, effect_size_value, clinical_significance,
             review_status, confidence_tier, actionability,
             allowed_claims, forbidden_claims, user_visible_notes,
             source_refs, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "special-chars-uuid", "rs222222", "AA", "gwas", "association",
                special_trait, "A", "increased", "odds_ratio", "1.5",
                None, None, "medium", "none",
                json.dumps([]), json.dumps([]), json.dumps([]),
                json.dumps([]),
                "2025-01-01T00:00:00+00:00",
            ],
        )

        finding = get_finding_by_id(db_connection, "special-chars-uuid")
        assert finding is not None
        assert finding.trait_or_condition == special_trait
