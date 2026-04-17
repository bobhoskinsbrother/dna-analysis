"""Batch loader into DuckDB sample_variants table."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from app.ingest.parser import parse_myheritage_csv
from app.models import SampleVariant


def load_variants(
    con,
    variants: Iterator[SampleVariant],
    batch_size: int = 10_000,
) -> int:
    """Insert variants into sample_variants in batches, using INSERT OR REPLACE.

    Returns the total number of rows inserted.
    """
    sql = (
        "INSERT OR REPLACE INTO sample_variants "
        "(rsid, chromosome, position, result, source_file, build_guess, imported_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    total = 0
    batch: list[tuple] = []

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
            batch = []

    # Flush remaining rows.
    if batch:
        con.executemany(sql, batch)
        total += len(batch)

    return total


def load_file(
    con,
    file_path: Path,
    batch_size: int = 10_000,
) -> int:
    """Parse a MyHeritage CSV and load all variants into DuckDB.

    Returns the total number of rows loaded.
    """
    variants = parse_myheritage_csv(file_path)
    return load_variants(con, variants, batch_size=batch_size)
