"""Functional tests for app/ingest/loader.py -- variant loading into DuckDB."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.ingest.loader import load_file, load_variants
from app.ingest.parser import parse_myheritage_csv
from app.models import SampleVariant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_variant(rsid: str, chrom: str = "1", pos: int = 100, result: str = "AA") -> SampleVariant:
    """Create a SampleVariant with minimal required fields."""
    return SampleVariant(
        rsid=rsid,
        chromosome=chrom,
        position=pos,
        result=result,
        source_file="test.csv",
    )


def _count_sample_variants(con) -> int:
    return con.execute("SELECT COUNT(*) FROM sample_variants").fetchone()[0]


# ---------------------------------------------------------------------------
# F5: load_variants inserts rows
# ---------------------------------------------------------------------------

class TestLoadVariantsInserts:
    def test_inserts_five_rows(self, db_connection):
        """Create 5 SampleVariant objects, load them, SELECT COUNT(*) == 5."""
        variants = [_make_variant(f"rs{i}") for i in range(1, 6)]
        load_variants(db_connection, variants)

        count = _count_sample_variants(db_connection)
        assert count == 5

    def test_inserted_data_readable(self, db_connection):
        """Loaded variants can be queried back with correct values."""
        variants = [
            _make_variant("rs100", chrom="7", pos=54321, result="GC"),
        ]
        load_variants(db_connection, variants)

        row = db_connection.execute(
            "SELECT rsid, chromosome, position, result FROM sample_variants WHERE rsid = 'rs100'"
        ).fetchone()
        assert row is not None
        assert row[0] == "rs100"
        assert row[1] == "7"
        assert row[2] == 54321
        assert row[3] == "GC"


# ---------------------------------------------------------------------------
# F6: Batch size respected (all rows inserted regardless of batch_size)
# ---------------------------------------------------------------------------

class TestBatchSizeRespected:
    def test_small_batch_still_inserts_all(self, db_connection):
        """5 variants with batch_size=2 still inserts all 5."""
        variants = [_make_variant(f"rs{i}") for i in range(1, 6)]
        load_variants(db_connection, variants, batch_size=2)

        count = _count_sample_variants(db_connection)
        assert count == 5

    def test_batch_size_one(self, db_connection):
        """Batch size of 1 still inserts all rows."""
        variants = [_make_variant(f"rs{i}") for i in range(1, 4)]
        load_variants(db_connection, variants, batch_size=1)

        count = _count_sample_variants(db_connection)
        assert count == 3


# ---------------------------------------------------------------------------
# F7: load_file end-to-end with sample CSV
# ---------------------------------------------------------------------------

class TestLoadFileEndToEnd:
    def test_returns_correct_count(self, db_connection, sample_csv):
        """load_file with sample_myheritage.csv returns 5."""
        result = load_file(db_connection, sample_csv)
        assert result == 5

    def test_rows_exist_in_db(self, db_connection, sample_csv):
        """After load_file, rows exist in the sample_variants table."""
        load_file(db_connection, sample_csv)

        count = _count_sample_variants(db_connection)
        assert count == 5

    def test_source_file_recorded(self, db_connection, sample_csv):
        """The source_file column should contain the filename."""
        load_file(db_connection, sample_csv)

        row = db_connection.execute(
            "SELECT DISTINCT source_file FROM sample_variants"
        ).fetchone()
        assert row is not None
        # source_file should contain the fixture filename
        assert "sample_myheritage" in row[0] or "myheritage" in row[0].lower()


# ---------------------------------------------------------------------------
# F8: Duplicate rsID handling (load same file twice)
# ---------------------------------------------------------------------------

class TestDuplicateHandling:
    def test_second_load_no_error(self, db_connection, sample_csv):
        """Loading the same file twice should not raise an error."""
        load_file(db_connection, sample_csv)
        load_file(db_connection, sample_csv)  # should not raise

    def test_count_stays_same_after_double_load(self, db_connection, sample_csv):
        """INSERT OR REPLACE means count stays 5 after loading twice."""
        load_file(db_connection, sample_csv)
        count_first = _count_sample_variants(db_connection)

        load_file(db_connection, sample_csv)
        count_second = _count_sample_variants(db_connection)

        assert count_first == 5
        assert count_second == 5


# ---------------------------------------------------------------------------
# F9: Data integrity (load + SELECT specific rsid, verify columns)
# ---------------------------------------------------------------------------

class TestDataIntegrity:
    def test_rs429358_values(self, db_connection, sample_csv):
        """Load sample CSV and verify rs429358 has correct column values."""
        load_file(db_connection, sample_csv)

        row = db_connection.execute(
            "SELECT rsid, chromosome, position, result "
            "FROM sample_variants WHERE rsid = 'rs429358'"
        ).fetchone()

        assert row is not None, "rs429358 should exist in sample_variants"
        assert row[0] == "rs429358"
        assert row[1] == "19"
        assert row[2] == 44908684
        assert row[3] == "CT"

    def test_build_guess_default(self, db_connection, sample_csv):
        """build_guess should default to GRCh37."""
        load_file(db_connection, sample_csv)

        row = db_connection.execute(
            "SELECT build_guess FROM sample_variants WHERE rsid = 'rs429358'"
        ).fetchone()
        assert row is not None
        assert row[0] == "GRCh37"

    def test_imported_at_populated(self, db_connection, sample_csv):
        """imported_at should be a non-null timestamp."""
        load_file(db_connection, sample_csv)

        row = db_connection.execute(
            "SELECT imported_at FROM sample_variants WHERE rsid = 'rs429358'"
        ).fetchone()
        assert row is not None
        assert row[0] is not None


# ---------------------------------------------------------------------------
# BVA: Boundary value analysis for variant loader
# ---------------------------------------------------------------------------

class TestLoaderBVA:
    """Boundary value analysis for variant loader."""

    def test_empty_iterator_returns_zero(self, db_connection):
        """Loading an empty iterator should return 0 and not crash."""
        count = load_variants(db_connection, iter([]), batch_size=10)
        assert count == 0

    def test_single_variant(self, db_connection):
        """Loading a single variant should return 1."""
        from app.models import SampleVariant
        variant = SampleVariant(rsid="rs1", chromosome="1", position=100, result="AA")
        count = load_variants(db_connection, iter([variant]), batch_size=10)
        assert count == 1

    def test_batch_size_larger_than_data(self, db_connection, sample_csv):
        """batch_size > number of variants should still work."""
        count = load_file(db_connection, sample_csv, batch_size=100_000)
        assert count > 0

    def test_duplicate_rsid_last_write_wins(self, db_connection):
        """Loading duplicate rsids should use INSERT OR REPLACE — last value wins."""
        from app.models import SampleVariant
        v1 = SampleVariant(rsid="rs1", chromosome="1", position=100, result="AA")
        v2 = SampleVariant(rsid="rs1", chromosome="1", position=100, result="GG")
        load_variants(db_connection, iter([v1, v2]), batch_size=10)
        rows = db_connection.execute("SELECT result FROM sample_variants WHERE rsid = 'rs1'").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "GG"


# ---------------------------------------------------------------------------
# Wrong-type coverage for loader functions
# ---------------------------------------------------------------------------

class TestLoaderWrongType:
    """Wrong-type coverage for loader functions."""

    def test_load_file_none_path_raises(self, db_connection):
        """None file_path should raise an error."""
        with pytest.raises((TypeError, AttributeError, FileNotFoundError)):
            load_file(db_connection, None)

    def test_load_file_nonexistent_raises(self, db_connection, tmp_path):
        """Non-existent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_file(db_connection, tmp_path / "nonexistent.csv")
