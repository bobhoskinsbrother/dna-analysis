"""GWAS Catalog and ClinVar importers."""
from __future__ import annotations

import csv
import uuid
from pathlib import Path


# ---------------------------------------------------------------------------
# ClinVar ReviewStatus -> star rating mapping
# ---------------------------------------------------------------------------

REVIEW_STARS: dict[str, int] = {
    "practice guideline": 4,
    "reviewed by expert panel": 3,
    "criteria provided, multiple submitters, no conflicts": 2,
    "criteria provided, multiple submitters": 2,
    "criteria provided, conflicting classifications": 1,
    "criteria provided, conflicting interpretations": 1,
    "criteria provided, single submitter": 1,
    "no assertion criteria provided": 0,
    "no classification provided": 0,
    "no classification for the individual variant": 0,
    "no assertion for the individual variant": 0,
}


# ---------------------------------------------------------------------------
# GWAS Catalog importer
# ---------------------------------------------------------------------------

def import_gwas_catalog(con, tsv_path: Path) -> int:
    """Import a GWAS Catalog TSV file into the gwas_assoc table.

    Uses DuckDB's native CSV reader for large files.
    Returns the number of rows inserted.
    """
    file_size = tsv_path.stat().st_size
    if file_size > 1_000_000:
        return _import_gwas_native(con, tsv_path)
    return _import_gwas_python(con, tsv_path)


def _import_gwas_native(con, tsv_path: Path) -> int:
    """Bulk-load GWAS Catalog using DuckDB's native CSV reader."""
    con.execute(f"""
        INSERT INTO gwas_assoc
        SELECT
            uuid()::VARCHAR AS id,
            TRIM(CAST("SNPS" AS VARCHAR)) AS rsid,
            NULLIF(TRIM(CAST("DISEASE/TRAIT" AS VARCHAR)), '') AS trait,
            NULLIF(TRIM(CAST("P-VALUE" AS VARCHAR)), '') AS p_value,
            NULLIF(TRIM(CAST("OR or BETA" AS VARCHAR)), '') AS odds_ratio,
            NULL AS beta,
            CASE WHEN CAST("STRONGEST SNP-RISK ALLELE" AS VARCHAR) LIKE '%-%'
                 THEN regexp_extract(CAST("STRONGEST SNP-RISK ALLELE" AS VARCHAR), '-([^-]+)$', 1)
                 ELSE NULL
            END AS effect_allele,
            NULLIF(TRIM(CAST("RISK ALLELE FREQUENCY" AS VARCHAR)), '') AS risk_frequency,
            NULLIF(TRIM(CAST("STUDY ACCESSION" AS VARCHAR)), '') AS study_accession,
            NULLIF(TRIM(CAST("PUBMEDID" AS VARCHAR)), '') AS pubmed_id,
            NULLIF(TRIM(CAST("MAPPED_GENE" AS VARCHAR)), '') AS mapped_gene
        FROM read_csv(
            '{tsv_path}',
            delim = '\t',
            header = true,
            ignore_errors = true,
            null_padding = true
        )
        WHERE TRIM(CAST("SNPS" AS VARCHAR)) LIKE 'rs%'
    """)
    return con.execute("SELECT COUNT(*) FROM gwas_assoc").fetchone()[0]


def _import_gwas_python(con, tsv_path: Path) -> int:
    """Import GWAS Catalog using Python CSV reader (for small/test files)."""
    sql = (
        "INSERT INTO gwas_assoc "
        "(id, rsid, trait, p_value, odds_ratio, beta, effect_allele, "
        "risk_frequency, study_accession, pubmed_id, mapped_gene) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )

    rows: list[tuple] = []

    with open(tsv_path, newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            snp = (row.get("SNPS") or "").strip()
            if not snp or not snp.startswith("rs"):
                continue

            strongest = (row.get("STRONGEST SNP-RISK ALLELE") or "").strip()
            effect_allele = strongest.rsplit("-", 1)[-1] if "-" in strongest else None

            rows.append((
                str(uuid.uuid4()),
                snp,
                (row.get("DISEASE/TRAIT") or "").strip() or None,
                (row.get("P-VALUE") or "").strip() or None,
                (row.get("OR or BETA") or "").strip() or None,
                None,
                effect_allele,
                (row.get("RISK ALLELE FREQUENCY") or "").strip() or None,
                (row.get("STUDY ACCESSION") or "").strip() or None,
                (row.get("PUBMEDID") or "").strip() or None,
                (row.get("MAPPED_GENE") or "").strip() or None,
            ))

    if rows:
        con.executemany(sql, rows)

    return len(rows)


# ---------------------------------------------------------------------------
# ClinVar importer
# ---------------------------------------------------------------------------

def import_clinvar(con, file_path: Path) -> int:
    """Import a ClinVar variant_summary.txt file into the clinvar_variants table.

    The first column header starts with '#' (#AlleleID).
    Rows with RS# (dbSNP) == -1 or empty are skipped.

    Uses DuckDB's native CSV reader for large files.
    Returns the number of rows inserted.
    """
    file_size = file_path.stat().st_size
    if file_size > 1_000_000:
        return _import_clinvar_native(con, file_path)
    return _import_clinvar_python(con, file_path)


def _import_clinvar_native(con, file_path: Path) -> int:
    """Bulk-load ClinVar using DuckDB's native CSV reader."""
    # Build the CASE WHEN for review_stars mapping in SQL.
    cases = "\n".join(
        f"            WHEN LOWER(TRIM(\"ReviewStatus\")) = '{status}' THEN {stars}"
        for status, stars in REVIEW_STARS.items()
    )

    # ClinVar header starts with '#AlleleID' — DuckDB reads it as column "#AlleleID".
    # We don't reference that column so it doesn't matter.
    con.execute(f"""
        INSERT OR REPLACE INTO clinvar_variants
        SELECT
            CAST("VariationID" AS VARCHAR) AS variation_id,
            'rs' || CAST("RS# (dbSNP)" AS VARCHAR) AS rsid,
            NULLIF(TRIM("GeneSymbol"), '') AS gene_symbol,
            NULLIF(TRIM("PhenotypeList"), '') AS condition_name,
            NULLIF(TRIM("ClinicalSignificance"), '') AS clinical_significance,
            NULLIF(TRIM("ReviewStatus"), '') AS review_status,
            CASE
{cases}
                ELSE 0
            END AS review_stars,
            NULLIF(TRIM("Type"), '') AS variation_type
        FROM read_csv(
            '{file_path}',
            delim = '\t',
            header = true,
            ignore_errors = true,
            null_padding = true
        )
        WHERE CAST("RS# (dbSNP)" AS VARCHAR) != '-1'
          AND CAST("RS# (dbSNP)" AS VARCHAR) != ''
          AND "RS# (dbSNP)" IS NOT NULL
    """)
    return con.execute("SELECT COUNT(*) FROM clinvar_variants").fetchone()[0]


def _import_clinvar_python(con, file_path: Path) -> int:
    """Import ClinVar using Python CSV reader (for small/test files)."""
    sql = (
        "INSERT INTO clinvar_variants "
        "(variation_id, rsid, gene_symbol, condition_name, "
        "clinical_significance, review_status, review_stars, variation_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )

    rows: list[tuple] = []

    with open(file_path, newline="") as fh:
        header_line = fh.readline()
        if header_line.startswith("#"):
            header_line = header_line[1:]
        headers = header_line.strip().split("\t")

        reader = csv.DictReader(fh, fieldnames=headers, delimiter="\t")

        for row in reader:
            rs_raw = (row.get("RS# (dbSNP)") or "").strip()
            if not rs_raw or rs_raw == "-1":
                continue

            rsid = f"rs{rs_raw}"

            review_status = (row.get("ReviewStatus") or "").strip()
            stars = REVIEW_STARS.get(review_status.lower(), 0)

            rows.append((
                (row.get("VariationID") or "").strip(),
                rsid,
                (row.get("GeneSymbol") or "").strip() or None,
                (row.get("PhenotypeList") or "").strip() or None,
                (row.get("ClinicalSignificance") or "").strip() or None,
                review_status or None,
                stars,
                (row.get("Type") or "").strip() or None,
            ))

    if rows:
        con.executemany(sql, rows)

    return len(rows)
