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

    Returns the number of rows inserted.
    """
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

            # Parse effect allele from "rs429358-T" -> "T"
            strongest = (row.get("STRONGEST SNP-RISK ALLELE") or "").strip()
            effect_allele = strongest.rsplit("-", 1)[-1] if "-" in strongest else None

            rows.append((
                str(uuid.uuid4()),
                snp,
                (row.get("DISEASE/TRAIT") or "").strip() or None,
                (row.get("P-VALUE") or "").strip() or None,
                (row.get("OR or BETA") or "").strip() or None,
                None,  # beta stored separately if needed; spec says OR or BETA -> odds_ratio
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

    Returns the number of rows inserted.
    """
    sql = (
        "INSERT INTO clinvar_variants "
        "(variation_id, rsid, gene_symbol, condition_name, "
        "clinical_significance, review_status, review_stars, variation_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )

    rows: list[tuple] = []

    with open(file_path, newline="") as fh:
        # The header line starts with '#', e.g. '#AlleleID\tType\t...'
        # Strip the leading '#' from the first header so DictReader works.
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
