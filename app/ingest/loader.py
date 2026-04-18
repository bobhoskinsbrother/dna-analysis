"""Batch loader into DuckDB sample_variants table."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator

from app.ingest.parser import parse_myheritage_csv
from app.models import SampleVariant


def load_variants(
    con,
    variants: Iterator[SampleVariant],
    batch_size: int = 10_000,
    on_batch: Callable[[int], None] | None = None,
) -> int:
    """Insert variants into sample_variants in batches, using INSERT OR REPLACE.

    Returns the total number of rows inserted.
    *on_batch* is called after each batch with the running total.
    """
    sql = (
        "INSERT OR REPLACE INTO sample_variants "
        "(rsid, chromosome, position, result, source_file, build_guess, imported_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    commit_every = batch_size * 10  # commit every ~100K rows

    total = 0
    batch: list[tuple] = []
    since_commit = 0

    con.begin()
    for variant in variants:
        batch.append((
            variant.rsid,
            variant.chromosome,
            variant.position,
            variant.result,
            variant.source_file,
            variant.build_guess,
            variant.imported_at,
        ))
        if len(batch) >= batch_size:
            con.executemany(sql, batch)
            total += len(batch)
            since_commit += len(batch)
            batch = []
            if since_commit >= commit_every:
                con.commit()
                con.begin()
                since_commit = 0
            if on_batch:
                on_batch(total)

    # Flush remaining rows.
    if batch:
        con.executemany(sql, batch)
        total += len(batch)
        if on_batch:
            on_batch(total)

    con.commit()
    return total


def load_file(
    con,
    file_path: Path,
    batch_size: int = 10_000,
) -> int:
    """Parse a MyHeritage CSV and load all variants into DuckDB.

    Uses DuckDB's native CSV reader for large files (>1MB) and falls back
    to the Python iterator path for small files and tests.

    Returns the total number of rows loaded.
    """
    file_size = file_path.stat().st_size
    if file_size > 1_000_000:
        return _load_file_native(con, file_path)
    variants = parse_myheritage_csv(file_path)
    return load_variants(con, variants, batch_size=batch_size)


def _load_file_native(con, file_path: Path) -> int:
    """Use DuckDB's native CSV reader for fast bulk loading."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    filename = file_path.name

    con.execute(f"""
        INSERT OR REPLACE INTO sample_variants
        SELECT
            "RSID" AS rsid,
            "CHROMOSOME" AS chromosome,
            CAST("POSITION" AS BIGINT) AS position,
            "RESULT" AS result,
            '{filename}' AS source_file,
            'GRCh37' AS build_guess,
            CAST('{now}' AS TIMESTAMP) AS imported_at
        FROM read_csv(
            '{file_path}',
            delim = ',',
            header = true,
            comment = '#',
            ignore_errors = true
        )
        WHERE "RESULT" IS NOT NULL
          AND "RESULT" != ''
          AND "RESULT" != '--'
          AND "RESULT" != '00'
          AND TRIM("RESULT") != ''
    """)

    count = con.execute("SELECT COUNT(*) FROM sample_variants").fetchone()[0]
    return count
