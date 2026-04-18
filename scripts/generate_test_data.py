"""Generate a synthetic MyHeritage-format CSV for testing.

Creates ~700K rows with realistic rsIDs, chromosomes, positions, and
random genotypes. Includes known rsIDs from the test fixtures so the
pipeline produces real findings.

Usage:
    docker compose run --rm app python scripts/generate_test_data.py [rows]

Output: data/raw/synthetic_genotype.csv
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

# Known rsIDs that exist in our GWAS/ClinVar test fixtures — ensures findings.
KNOWN_RSIDS = [
    ("rs429358", "19", 44908684, "CT"),
    ("rs7412", "19", 44908822, "CC"),
    ("rs1801133", "1", 11856378, "AG"),
    ("rs334", "11", 5227002, "AA"),
    ("rs1234567", "2", 30000000, "GG"),
]

CHROMOSOMES = [str(c) for c in range(1, 23)] + ["X", "Y"]
ALLELES = "ACGT"
GENOTYPES = [a + b for a in ALLELES for b in ALLELES]
NO_CALLS = ["--", "00", ""]

# Approximate chromosome lengths (GRCh37) for realistic positions.
CHROM_LENGTHS = {
    "1": 249250621, "2": 243199373, "3": 198022430, "4": 191154276,
    "5": 180915260, "6": 171115067, "7": 159138663, "8": 146364022,
    "9": 141213431, "10": 135534747, "11": 135006516, "12": 133851895,
    "13": 115169878, "14": 107349540, "15": 102531392, "16": 90354753,
    "17": 81195210, "18": 78077248, "19": 59128983, "20": 63025520,
    "21": 48129895, "22": 51304566, "X": 155270560, "Y": 59373566,
}


def generate(num_rows: int = 700_000, seed: int = 42) -> Path:
    rng = random.Random(seed)
    out_dir = Path("data/raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "synthetic_genotype.csv"

    with open(out_path, "w", newline="\n") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["RSID", "CHROMOSOME", "POSITION", "RESULT"])

        # Write known rsIDs first.
        for rsid, chrom, pos, result in KNOWN_RSIDS:
            writer.writerow([rsid, chrom, pos, result])

        # Generate the rest.
        used_rsids = {r[0] for r in KNOWN_RSIDS}
        written = len(KNOWN_RSIDS)

        while written < num_rows:
            rsid_num = rng.randint(1, 50_000_000)
            rsid = f"rs{rsid_num}"
            if rsid in used_rsids:
                continue
            used_rsids.add(rsid)

            chrom = rng.choice(CHROMOSOMES)
            pos = rng.randint(1, CHROM_LENGTHS[chrom])

            # ~2% no-calls (matching real data patterns).
            if rng.random() < 0.02:
                result = rng.choice(NO_CALLS)
            else:
                result = rng.choice(GENOTYPES)

            writer.writerow([rsid, chrom, pos, result])
            written += 1

            if written % 100_000 == 0:
                print(f"  {written:,} / {num_rows:,} rows...")

    print(f"Wrote {written:,} rows to {out_path}")
    return out_path


if __name__ == "__main__":
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 700_000
    generate(rows)
