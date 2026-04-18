"""rsID-based matcher against annotation tables."""
from __future__ import annotations

from app.models import AnnotationRecord, SourceType


def _gwas_records_for_rsid(con, rsid: str, genotype: str) -> list[AnnotationRecord]:
    """Query gwas_assoc for a single rsid and return AnnotationRecord list."""
    rows = con.execute(
        "SELECT rsid, trait, p_value, odds_ratio, effect_allele, "
        "risk_frequency, study_accession, pubmed_id, mapped_gene "
        "FROM gwas_assoc WHERE rsid = ?",
        [rsid],
    ).fetchall()

    return [
        AnnotationRecord(
            rsid=row[0],
            genotype=genotype,
            source_type=SourceType.GWAS,
            trait_or_condition=row[1] or "",
            p_value=row[2],
            odds_ratio=row[3],
            effect_allele=row[4],
            study_accession=row[6],
            pubmed_id=row[7],
            mapped_gene=row[8],
        )
        for row in rows
    ]


def _clinvar_records_for_rsid(con, rsid: str, genotype: str) -> list[AnnotationRecord]:
    """Query clinvar_variants for a single rsid and return AnnotationRecord list."""
    rows = con.execute(
        "SELECT rsid, condition_name, clinical_significance, review_status, "
        "review_stars, variation_id, gene_symbol, variation_type "
        "FROM clinvar_variants WHERE rsid = ?",
        [rsid],
    ).fetchall()

    return [
        AnnotationRecord(
            rsid=row[0],
            genotype=genotype,
            source_type=SourceType.CLINVAR,
            trait_or_condition=row[1] or "",
            clinical_significance=row[2],
            review_status=row[3],
            review_stars=row[4],
            variation_id=row[5],
            mapped_gene=row[6],
        )
        for row in rows
    ]


def match_rsid(con, rsid: str) -> list[AnnotationRecord]:
    """Match a single rsID against GWAS and ClinVar annotation tables.

    Joins with sample_variants to obtain the user's genotype.
    Returns an empty list if the rsid is not found in any annotation table.
    """
    # Get genotype from sample_variants
    sv_row = con.execute(
        "SELECT result FROM sample_variants WHERE rsid = ?",
        [rsid],
    ).fetchone()

    genotype = sv_row[0] if sv_row else ""

    records: list[AnnotationRecord] = []
    records.extend(_gwas_records_for_rsid(con, rsid, genotype))
    records.extend(_clinvar_records_for_rsid(con, rsid, genotype))
    return records


def match_all(con) -> list[AnnotationRecord]:
    """Match all rsIDs in sample_variants that have at least one annotation.

    Uses bulk JOINs. For small datasets only — large datasets should use
    match_all_chunked() to avoid OOM.
    """
    return list(match_all_chunked(con))


def match_count(con) -> int:
    """Return the total number of annotation matches without materializing them."""
    gwas = con.execute("""
        SELECT COUNT(*) FROM sample_variants sv
        JOIN gwas_assoc g ON g.rsid = sv.rsid
    """).fetchone()[0]
    clinvar = con.execute("""
        SELECT COUNT(*) FROM sample_variants sv
        JOIN clinvar_variants c ON c.rsid = sv.rsid
    """).fetchone()[0]
    return gwas + clinvar


def match_all_chunked(con, chunk: int = 5_000):
    """Yield AnnotationRecord objects in chunks to limit memory.

    Streams GWAS matches first, then ClinVar matches.
    """
    # GWAS matches
    result = con.execute("""
        SELECT sv.rsid, sv.result,
               g.trait, g.p_value, g.odds_ratio, g.effect_allele,
               g.risk_frequency, g.study_accession, g.pubmed_id, g.mapped_gene
        FROM sample_variants sv
        JOIN gwas_assoc g ON g.rsid = sv.rsid
    """)
    while True:
        rows = result.fetchmany(chunk)
        if not rows:
            break
        for row in rows:
            yield AnnotationRecord(
                rsid=row[0], genotype=row[1], source_type=SourceType.GWAS,
                trait_or_condition=row[2] or "",
                p_value=row[3], odds_ratio=row[4], effect_allele=row[5],
                study_accession=row[7], pubmed_id=row[8], mapped_gene=row[9],
            )

    # ClinVar matches
    result = con.execute("""
        SELECT sv.rsid, sv.result,
               c.condition_name, c.clinical_significance, c.review_status,
               c.review_stars, c.variation_id, c.gene_symbol, c.variation_type
        FROM sample_variants sv
        JOIN clinvar_variants c ON c.rsid = sv.rsid
    """)
    while True:
        rows = result.fetchmany(chunk)
        if not rows:
            break
        for row in rows:
            yield AnnotationRecord(
                rsid=row[0], genotype=row[1], source_type=SourceType.CLINVAR,
                trait_or_condition=row[2] or "",
                clinical_significance=row[3], review_status=row[4],
                review_stars=row[5], variation_id=row[6], mapped_gene=row[7],
            )
