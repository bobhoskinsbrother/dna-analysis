"""Functional tests for app/annotate/matcher.py -- rsID-based matching."""
from __future__ import annotations

import pytest

from app.annotate.importer import import_clinvar, import_gwas_catalog
from app.annotate.matcher import match_all, match_rsid
from app.ingest.loader import load_file
from app.models import AnnotationRecord, SourceType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def loaded_db(db_connection, sample_csv, sample_gwas_tsv, sample_clinvar_txt):
    """DB with sample variants and annotations loaded."""
    load_file(db_connection, sample_csv)
    import_gwas_catalog(db_connection, sample_gwas_tsv)
    import_clinvar(db_connection, sample_clinvar_txt)
    return db_connection


# ---------------------------------------------------------------------------
# F10: match_rsid("rs429358") finds GWAS match
# ---------------------------------------------------------------------------

class TestMatchRsidGwas:
    def test_finds_gwas_match(self, loaded_db):
        """match_rsid should return at least one AnnotationRecord with source_type=gwas."""
        records = match_rsid(loaded_db, "rs429358")
        gwas_records = [r for r in records if r.source_type == SourceType.GWAS]
        assert len(gwas_records) >= 1

    def test_gwas_record_has_trait(self, loaded_db):
        """GWAS AnnotationRecord should have a non-empty trait_or_condition."""
        records = match_rsid(loaded_db, "rs429358")
        gwas_records = [r for r in records if r.source_type == SourceType.GWAS]
        assert len(gwas_records) >= 1
        assert gwas_records[0].trait_or_condition is not None
        assert len(gwas_records[0].trait_or_condition) > 0

    def test_gwas_record_is_annotation_record(self, loaded_db):
        """Returned objects should be AnnotationRecord instances."""
        records = match_rsid(loaded_db, "rs429358")
        gwas_records = [r for r in records if r.source_type == SourceType.GWAS]
        assert len(gwas_records) >= 1
        assert isinstance(gwas_records[0], AnnotationRecord)


# ---------------------------------------------------------------------------
# F11: match_rsid("rs429358") finds ClinVar match
# ---------------------------------------------------------------------------

class TestMatchRsidClinvar:
    def test_finds_clinvar_match(self, loaded_db):
        """match_rsid should return at least one AnnotationRecord with source_type=clinvar."""
        records = match_rsid(loaded_db, "rs429358")
        clinvar_records = [r for r in records if r.source_type == SourceType.CLINVAR]
        assert len(clinvar_records) >= 1

    def test_clinvar_record_has_clinical_significance(self, loaded_db):
        """ClinVar AnnotationRecord should have clinical_significance populated."""
        records = match_rsid(loaded_db, "rs429358")
        clinvar_records = [r for r in records if r.source_type == SourceType.CLINVAR]
        assert len(clinvar_records) >= 1
        assert clinvar_records[0].clinical_significance is not None

    def test_clinvar_record_has_review_stars(self, loaded_db):
        """ClinVar AnnotationRecord should have review_stars populated."""
        records = match_rsid(loaded_db, "rs429358")
        clinvar_records = [r for r in records if r.source_type == SourceType.CLINVAR]
        assert len(clinvar_records) >= 1
        assert clinvar_records[0].review_stars is not None


# ---------------------------------------------------------------------------
# F12: match_rsid("rs429358") returns multiple records (>= 2)
# ---------------------------------------------------------------------------

class TestMatchRsidMultiple:
    def test_returns_at_least_two(self, loaded_db):
        """rs429358 should match both GWAS and ClinVar, returning >= 2 records."""
        records = match_rsid(loaded_db, "rs429358")
        assert len(records) >= 2

    def test_both_source_types_present(self, loaded_db):
        """Results should contain both gwas and clinvar source types."""
        records = match_rsid(loaded_db, "rs429358")
        source_types = {r.source_type for r in records}
        assert SourceType.GWAS in source_types
        assert SourceType.CLINVAR in source_types


# ---------------------------------------------------------------------------
# F13: match_rsid("rs000000") returns empty list (no match)
# ---------------------------------------------------------------------------

class TestMatchRsidNoMatch:
    def test_returns_empty_list(self, loaded_db):
        """An rsID not in any annotation table should return an empty list."""
        records = match_rsid(loaded_db, "rs000000")
        assert records == []

    def test_returns_list_type(self, loaded_db):
        """Even with no matches, the return value should be a list."""
        records = match_rsid(loaded_db, "rs000000")
        assert isinstance(records, list)


# ---------------------------------------------------------------------------
# F14: match_all returns records for all matching rsIDs
# ---------------------------------------------------------------------------

class TestMatchAll:
    def test_returns_records_for_multiple_rsids(self, loaded_db):
        """match_all should return records covering multiple rsIDs from sample data."""
        records = match_all(loaded_db)
        assert len(records) > 0

        matched_rsids = {r.rsid for r in records}
        # rs429358 is in both sample_variants and the annotation fixtures
        assert "rs429358" in matched_rsids

    def test_returns_annotation_records(self, loaded_db):
        """All returned objects should be AnnotationRecord instances."""
        records = match_all(loaded_db)
        for record in records:
            assert isinstance(record, AnnotationRecord)

    def test_includes_both_source_types(self, loaded_db):
        """match_all results should include records from both GWAS and ClinVar."""
        records = match_all(loaded_db)
        source_types = {r.source_type for r in records}
        assert SourceType.GWAS in source_types
        assert SourceType.CLINVAR in source_types

    def test_no_records_for_unmatched_rsids(self, loaded_db):
        """match_all should not return records for rsIDs absent from annotations."""
        records = match_all(loaded_db)
        matched_rsids = {r.rsid for r in records}
        # rs9999999 is in GWAS but not in sample_variants, so it should not appear
        # Only rsIDs present in sample_variants AND annotation tables should be returned
        for rsid in matched_rsids:
            # Confirm each matched rsid exists in sample_variants
            row = loaded_db.execute(
                "SELECT COUNT(*) FROM sample_variants WHERE rsid = ?", [rsid]
            ).fetchone()
            assert row[0] > 0, f"rsid {rsid} matched but not in sample_variants"


# ---------------------------------------------------------------------------
# F15: Matched records have genotype from sample_variants
# ---------------------------------------------------------------------------

class TestMatchedGenotype:
    def test_rs429358_genotype_is_ct(self, loaded_db):
        """rs429358 in the sample CSV has result='CT', so genotype should be 'CT'."""
        records = match_rsid(loaded_db, "rs429358")
        assert len(records) >= 1
        for record in records:
            assert record.genotype == "CT"

    def test_all_matched_records_have_genotype(self, loaded_db):
        """Every matched record should have a non-null genotype."""
        records = match_all(loaded_db)
        for record in records:
            assert record.genotype is not None
            assert len(record.genotype) > 0

    def test_genotype_matches_sample_variants_table(self, loaded_db):
        """Genotype on matched records should match the result column in sample_variants."""
        records = match_rsid(loaded_db, "rs429358")
        expected_row = loaded_db.execute(
            "SELECT result FROM sample_variants WHERE rsid = 'rs429358'"
        ).fetchone()
        assert expected_row is not None
        expected_genotype = expected_row[0]

        for record in records:
            assert record.genotype == expected_genotype
