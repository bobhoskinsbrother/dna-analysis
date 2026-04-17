"""MyHeritage CSV parser."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

from app.models import SampleVariant

# Result values that represent no-calls and should be skipped.
_NOCALL_VALUES = {"--", "00", ""}


def parse_myheritage_csv(file_path: Path) -> Iterator[SampleVariant]:
    """Parse a MyHeritage raw DNA CSV file and yield SampleVariant objects.

    - Skips comment lines (starting with ``#``).
    - Skips rows where RESULT is ``--``, ``00``, or empty.
    - Raises ``FileNotFoundError`` if the file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    source = file_path.name

    with open(file_path, newline="") as fh:
        # Filter out comment lines before handing to DictReader.
        filtered = (line for line in fh if not line.startswith("#"))
        reader = csv.DictReader(filtered, fieldnames=["RSID", "CHROMOSOME", "POSITION", "RESULT"])

        # Skip the real header row (RSID,CHROMOSOME,POSITION,RESULT).
        next(reader, None)

        for row in reader:
            result = row["RESULT"].strip() if row["RESULT"] else ""
            if result in _NOCALL_VALUES:
                continue

            yield SampleVariant(
                rsid=row["RSID"].strip(),
                chromosome=row["CHROMOSOME"].strip(),
                position=int(row["POSITION"].strip()),
                result=result,
                source_file=source,
            )
