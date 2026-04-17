"""Functional tests for app/annotate/importer.py -- GWAS and ClinVar importers."""
from __future__ import annotations

import pytest

from app.annotate.importer import import_clinvar, import_gwas_catalog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_rows(con, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _select_all(con, table: str) -> list[tuple]:
    return con.execute(f"SELECT * FROM {table}").fetchall()


# ---------------------------------------------------------------------------
# U19: GWAS import returns correct row count
# ---------------------------------------------------------------------------

class TestGwasImportRowCount:
    def test_returns_three(self, db_connection, sample_gwas_tsv):
        """import_gwas_catalog returns 3 for a fixture with 3 data rows."""
        result = import_gwas_catalog(db_connection, sample_gwas_tsv)
        assert result == 3

    def test_three_rows_in_table(self, db_connection, sample_gwas_tsv):
        """After import, gwas_assoc table has 3 rows."""
        import_gwas_catalog(db_connection, sample_gwas_tsv)
        count = _count_rows(db_connection, "gwas_assoc")
        assert count == 3


# ---------------------------------------------------------------------------
# U20: GWAS rows have correct rsid, trait, p_value
# ---------------------------------------------------------------------------

class TestGwasRowValues:
    def test_rs429358_trait(self, db_connection, sample_gwas_tsv):
        """rs429358 row has the expected trait value."""
        import_gwas_catalog(db_connection, sample_gwas_tsv)

        row = db_connection.execute(
            "SELECT rsid, trait, p_value FROM gwas_assoc WHERE rsid = 'rs429358'"
        ).fetchone()
        assert row is not None
        assert row[0] == "rs429358"
        # trait should be populated (exact value depends on fixture)
        assert row[1] is not None and len(row[1]) > 0
        # p_value should be populated
        assert row[2] is not None and len(row[2]) > 0

    def test_rs1801133_exists(self, db_connection, sample_gwas_tsv):
        """rs1801133 should be present in gwas_assoc after import."""
        import_gwas_catalog(db_connection, sample_gwas_tsv)

        row = db_connection.execute(
            "SELECT rsid FROM gwas_assoc WHERE rsid = 'rs1801133'"
        ).fetchone()
        assert row is not None

    def test_rs9999999_exists(self, db_connection, sample_gwas_tsv):
        """rs9999999 should be present in gwas_assoc after import."""
        import_gwas_catalog(db_connection, sample_gwas_tsv)

        row = db_connection.execute(
            "SELECT rsid FROM gwas_assoc WHERE rsid = 'rs9999999'"
        ).fetchone()
        assert row is not None

    def test_study_accession_populated(self, db_connection, sample_gwas_tsv):
        """study_accession should be populated from the STUDY ACCESSION column."""
        import_gwas_catalog(db_connection, sample_gwas_tsv)

        rows = db_connection.execute(
            "SELECT study_accession FROM gwas_assoc WHERE study_accession IS NOT NULL"
        ).fetchall()
        assert len(rows) > 0

    def test_pubmed_id_populated(self, db_connection, sample_gwas_tsv):
        """pubmed_id should be populated from the PUBMEDID column."""
        import_gwas_catalog(db_connection, sample_gwas_tsv)

        rows = db_connection.execute(
            "SELECT pubmed_id FROM gwas_assoc WHERE pubmed_id IS NOT NULL"
        ).fetchall()
        assert len(rows) > 0


# ---------------------------------------------------------------------------
# U21: GWAS effect_allele parsed from STRONGEST SNP-RISK ALLELE
# ---------------------------------------------------------------------------

class TestGwasEffectAlleleParsing:
    def test_effect_allele_extracted(self, db_connection, sample_gwas_tsv):
        """effect_allele should be parsed from 'rs429358-T' -> 'T'."""
        import_gwas_catalog(db_connection, sample_gwas_tsv)

        row = db_connection.execute(
            "SELECT effect_allele FROM gwas_assoc WHERE rsid = 'rs429358'"
        ).fetchone()
        assert row is not None
        assert row[0] == "T"

    def test_effect_allele_for_rs1801133(self, db_connection, sample_gwas_tsv):
        """effect_allele should be parsed for rs1801133 as well."""
        import_gwas_catalog(db_connection, sample_gwas_tsv)

        row = db_connection.execute(
            "SELECT effect_allele FROM gwas_assoc WHERE rsid = 'rs1801133'"
        ).fetchone()
        assert row is not None
        # Should have an allele letter(s), not the full 'rsid-allele' string
        assert row[0] is not None
        assert not row[0].startswith("rs")


# ---------------------------------------------------------------------------
# U22: ClinVar imports rows with rsID (skips RS#=-1)
# ---------------------------------------------------------------------------

class TestClinvarImportRowCount:
    def test_imports_three_rows(self, db_connection, sample_clinvar_txt):
        """ClinVar import should include 3 rows (skip the row with RS#=-1)."""
        import_clinvar(db_connection, sample_clinvar_txt)
        count = _count_rows(db_connection, "clinvar_variants")
        assert count == 3

    def test_no_negative_rsid(self, db_connection, sample_clinvar_txt):
        """No row should have rsid '-1' or 'rs-1' in the table."""
        import_clinvar(db_connection, sample_clinvar_txt)

        row = db_connection.execute(
            "SELECT COUNT(*) FROM clinvar_variants WHERE rsid = '-1' OR rsid = 'rs-1'"
        ).fetchone()
        assert row[0] == 0


# ---------------------------------------------------------------------------
# U23: ClinVar rsid gets "rs" prefix
# ---------------------------------------------------------------------------

class TestClinvarRsidPrefix:
    def test_rs429358_has_prefix(self, db_connection, sample_clinvar_txt):
        """RS#=429358 in the file should become rsid='rs429358'."""
        import_clinvar(db_connection, sample_clinvar_txt)

        row = db_connection.execute(
            "SELECT rsid FROM clinvar_variants WHERE rsid = 'rs429358'"
        ).fetchone()
        assert row is not None
        assert row[0] == "rs429358"

    def test_rs7412_has_prefix(self, db_connection, sample_clinvar_txt):
        """RS#=7412 should become rsid='rs7412'."""
        import_clinvar(db_connection, sample_clinvar_txt)

        row = db_connection.execute(
            "SELECT rsid FROM clinvar_variants WHERE rsid = 'rs7412'"
        ).fetchone()
        assert row is not None
        assert row[0] == "rs7412"

    def test_rs334_has_prefix(self, db_connection, sample_clinvar_txt):
        """RS#=334 should become rsid='rs334'."""
        import_clinvar(db_connection, sample_clinvar_txt)

        row = db_connection.execute(
            "SELECT rsid FROM clinvar_variants WHERE rsid = 'rs334'"
        ).fetchone()
        assert row is not None
        assert row[0] == "rs334"

    def test_all_rsids_have_rs_prefix(self, db_connection, sample_clinvar_txt):
        """Every rsid in clinvar_variants should start with 'rs'."""
        import_clinvar(db_connection, sample_clinvar_txt)

        rows = db_connection.execute("SELECT rsid FROM clinvar_variants").fetchall()
        for row in rows:
            assert row[0].startswith("rs"), f"rsid {row[0]} missing 'rs' prefix"


# ---------------------------------------------------------------------------
# U24: ClinVar review_stars derived from ReviewStatus
# ---------------------------------------------------------------------------

class TestClinvarReviewStars:
    def test_rs429358_three_stars(self, db_connection, sample_clinvar_txt):
        """rs429358 is Pathogenic with 3 stars (reviewed by expert panel)."""
        import_clinvar(db_connection, sample_clinvar_txt)

        row = db_connection.execute(
            "SELECT review_stars, clinical_significance "
            "FROM clinvar_variants WHERE rsid = 'rs429358'"
        ).fetchone()
        assert row is not None
        assert row[0] == 3
        assert row[1] == "Pathogenic"

    def test_rs7412_two_stars(self, db_connection, sample_clinvar_txt):
        """rs7412 is Benign with 2 stars (criteria provided, multiple submitters)."""
        import_clinvar(db_connection, sample_clinvar_txt)

        row = db_connection.execute(
            "SELECT review_stars, clinical_significance "
            "FROM clinvar_variants WHERE rsid = 'rs7412'"
        ).fetchone()
        assert row is not None
        assert row[0] == 2
        assert row[1] == "Benign"

    def test_rs334_four_stars(self, db_connection, sample_clinvar_txt):
        """rs334 is Pathogenic with 4 stars (practice guideline)."""
        import_clinvar(db_connection, sample_clinvar_txt)

        row = db_connection.execute(
            "SELECT review_stars, clinical_significance "
            "FROM clinvar_variants WHERE rsid = 'rs334'"
        ).fetchone()
        assert row is not None
        assert row[0] == 4
        assert row[1] == "Pathogenic"

    def test_review_stars_are_integers(self, db_connection, sample_clinvar_txt):
        """All review_stars values should be integers between 0 and 4."""
        import_clinvar(db_connection, sample_clinvar_txt)

        rows = db_connection.execute(
            "SELECT review_stars FROM clinvar_variants"
        ).fetchall()
        for row in rows:
            assert isinstance(row[0], int)
            assert 0 <= row[0] <= 4


# ---------------------------------------------------------------------------
# U25: Return values match row counts
# ---------------------------------------------------------------------------

class TestReturnValues:
    def test_gwas_return_matches_count(self, db_connection, sample_gwas_tsv):
        """import_gwas_catalog return value == rows in gwas_assoc."""
        result = import_gwas_catalog(db_connection, sample_gwas_tsv)
        count = _count_rows(db_connection, "gwas_assoc")
        assert result == count

    def test_clinvar_return_matches_count(self, db_connection, sample_clinvar_txt):
        """import_clinvar return value == rows in clinvar_variants."""
        result = import_clinvar(db_connection, sample_clinvar_txt)
        count = _count_rows(db_connection, "clinvar_variants")
        assert result == count


# ---------------------------------------------------------------------------
# BVA: Boundary value analysis for annotation importers
# ---------------------------------------------------------------------------

class TestImporterBVA:
    """Boundary value analysis for annotation importers."""

    def test_gwas_empty_file(self, db_connection, tmp_path):
        """GWAS file with only header, no data rows, should import 0."""
        # Create a minimal TSV with just the header
        # The GWAS file has many columns; the key ones are SNPS and DISEASE/TRAIT
        header = "DATE ADDED TO CATALOG\tPUBMEDID\tFIRST AUTHOR\tDATE\tJOURNAL\tLINK\tSTUDY\tDISEASE/TRAIT\tINITIAL SAMPLE SIZE\tREPLICATION SAMPLE SIZE\tREGION\tCHR_ID\tCHR_POS\tREPORTED GENE(S)\tMAPPED_GENE\tUPSTREAM_GENE_ID\tDOWNSTREAM_GENE_ID\tSNP_GENE_IDS\tUPSTREAM_GENE_DISTANCE\tDOWNSTREAM_GENE_DISTANCE\tSTRONGEST SNP-RISK ALLELE\tSNPS\tMERGED\tSNP_ID_CURRENT\tCONTEXT\tINTERGENIC\tRISK ALLELE FREQUENCY\tP-VALUE\tPVALUE_MLOG\tP-VALUE (TEXT)\tOR or BETA\t95% CI (TEXT)\tPLATFORM [SNPS PASSING QC]\tCNV\tMAPPED_TRAIT\tMAPPED_TRAIT_URI\tSTUDY ACCESSION\tGENOTYPING TECHNOLOGY"
        tsv_file = tmp_path / "empty_gwas.tsv"
        tsv_file.write_text(header + "\n")
        count = import_gwas_catalog(db_connection, tsv_file)
        assert count == 0

    def test_clinvar_empty_file(self, db_connection, tmp_path):
        """ClinVar file with only header, no data rows, should import 0."""
        header = "#AlleleID\tType\tName\tGeneID\tGeneSymbol\tHGNC_ID\tClinicalSignificance\tClinSigSimple\tLastEvaluated\tRS# (dbSNP)\tnsv/esv (dbVar)\tRCVaccession\tPhenotypeIDS\tPhenotypeList\tOrigin\tOriginSimple\tAssembly\tChromosomeAccession\tChromosome\tStart\tStop\tReferenceAllele\tAlternateAllele\tCytogenetic\tReviewStatus\tNumberOfSubmitters\tGuidelines\tTestedInGTR\tOtherIDs\tSubmitterCategories\tVariationID\tPositionVCF\tReferenceAlleleVCF\tAlternateAlleleVCF\tRS# (dbSNP)\tVariantLength\tRecordStatus\tSourceDatabase\tSource\tAlleleSource"
        txt_file = tmp_path / "empty_clinvar.txt"
        txt_file.write_text(header + "\n")
        count = import_clinvar(db_connection, txt_file)
        assert count == 0

    def test_clinvar_unknown_review_status_gets_zero_stars(self, db_connection, tmp_path):
        """ClinVar entry with unknown ReviewStatus should get 0 stars."""
        # Write a minimal ClinVar file with an unknown ReviewStatus
        header = "#AlleleID\tType\tName\tGeneID\tGeneSymbol\tHGNC_ID\tClinicalSignificance\tClinSigSimple\tLastEvaluated\tRS# (dbSNP)\tnsv/esv (dbVar)\tRCVaccession\tPhenotypeIDS\tPhenotypeList\tOrigin\tOriginSimple\tAssembly\tChromosomeAccession\tChromosome\tStart\tStop\tReferenceAllele\tAlternateAllele\tCytogenetic\tReviewStatus\tNumberOfSubmitters\tGuidelines\tTestedInGTR\tOtherIDs\tSubmitterCategories\tVariationID\tPositionVCF\tReferenceAlleleVCF\tAlternateAlleleVCF\tRS# (dbSNP)\tVariantLength\tRecordStatus\tSourceDatabase\tSource\tAlleleSource"
        # Use a known RS# (429358) but an unknown ReviewStatus
        data = "100\tsingle nucleotide variant\tTestName\t123\tFOO\tHGNC:1\tPathogenic\t1\t2025-01-01\t429358\t-\tRCV1\tMedGen:C1\tTest condition\tgermline\tgermline\tGRCh37\tNC1\t19\t44908684\t44908684\tT\tC\t19p13.2\tcompletely_unknown_status\t1\t-\tN\t-\t1\t100\t44908684\tT\tC\t429358\t1\tcurrent\tClinVar\tClinVar\tSubmitter"
        txt_file = tmp_path / "unknown_review.txt"
        txt_file.write_text(header + "\n" + data + "\n")
        count = import_clinvar(db_connection, txt_file)
        assert count == 1
        rows = db_connection.execute("SELECT review_stars FROM clinvar_variants WHERE rsid = 'rs429358'").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 0  # Unknown status maps to 0 stars

    def test_gwas_nonexistent_file_raises(self, db_connection, tmp_path):
        """Non-existent GWAS file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            import_gwas_catalog(db_connection, tmp_path / "nonexistent.tsv")

    def test_clinvar_nonexistent_file_raises(self, db_connection, tmp_path):
        """Non-existent ClinVar file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            import_clinvar(db_connection, tmp_path / "nonexistent.txt")


# ---------------------------------------------------------------------------
# Wrong-type coverage for importers
# ---------------------------------------------------------------------------

class TestImporterWrongType:
    """Wrong-type coverage for importers."""

    def test_gwas_none_path_raises(self, db_connection):
        """None path for GWAS import should raise."""
        with pytest.raises((TypeError, AttributeError)):
            import_gwas_catalog(db_connection, None)

    def test_clinvar_none_path_raises(self, db_connection):
        """None path for ClinVar import should raise."""
        with pytest.raises((TypeError, AttributeError)):
            import_clinvar(db_connection, None)
