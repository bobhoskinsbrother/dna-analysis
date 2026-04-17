"""Typer CLI application for the DNA variant interpreter."""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="dna", help="DNA variant interpreter")
console = Console()


@app.command()
def init_db() -> None:
    """Initialize the local DuckDB schema."""
    from app.config import get_settings
    from app.db import get_connection, init_schema

    settings = get_settings()
    con = get_connection(settings)
    init_schema(con)
    con.close()
    console.print("[green]Database schema initialised successfully.[/green]")


@app.command()
def load(file: Path = typer.Argument(..., help="Path to MyHeritage CSV file")) -> None:
    """Load a MyHeritage CSV file into sample_variants."""
    from app.config import get_settings
    from app.db import get_connection
    from app.ingest.loader import load_file

    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(code=1)

    settings = get_settings()
    con = get_connection(settings)
    count = load_file(con, file, settings.batch_size)
    con.close()
    console.print(f"Loaded {count} rows from {file.name}")


@app.command()
def import_gwas(file: Path = typer.Argument(..., help="Path to GWAS Catalog TSV file")) -> None:
    """Import GWAS Catalog associations from a TSV file."""
    from app.config import get_settings
    from app.db import get_connection
    from app.annotate.importer import import_gwas_catalog

    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(code=1)

    settings = get_settings()
    con = get_connection(settings)
    count = import_gwas_catalog(con, file)
    con.close()
    console.print(f"Imported {count} GWAS associations")


@app.command()
def import_clinvar(file: Path = typer.Argument(..., help="Path to ClinVar variant_summary file")) -> None:
    """Import ClinVar variant_summary data."""
    from app.config import get_settings
    from app.db import get_connection
    from app.annotate.importer import import_clinvar as _import_clinvar

    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(code=1)

    settings = get_settings()
    con = get_connection(settings)
    count = _import_clinvar(con, file)
    con.close()
    console.print(f"Imported {count} ClinVar variants")


@app.command()
def match(rsid: str = typer.Argument(..., help="rsID to match, e.g. rs429358")) -> None:
    """Match a single rsID against annotation tables and show findings."""
    from app.config import get_settings
    from app.db import get_connection
    from app.annotate.matcher import match_rsid
    from app.policy.engine import evaluate

    settings = get_settings()
    con = get_connection(settings)
    records = match_rsid(con, rsid)
    con.close()

    if not records:
        console.print("No matches found")
        return

    for record in records:
        finding = evaluate(record)
        table = Table(title=f"Finding: {finding.rsid}")
        table.add_column("Field", style="bold")
        table.add_column("Value")
        table.add_row("rsid", finding.rsid)
        table.add_row("trait", finding.trait_or_condition)
        table.add_row("confidence", finding.confidence_tier)
        table.add_row("actionability", finding.actionability)
        table.add_row("evidence_type", finding.evidence_type)
        table.add_row("source_type", finding.source_type)
        table.add_row("genotype", finding.genotype)
        if finding.effect_allele:
            table.add_row("effect_allele", finding.effect_allele)
        if finding.clinical_significance:
            table.add_row("clinical_significance", finding.clinical_significance)
        console.print(table)


@app.command()
def run_all() -> None:
    """Match all variants, score them, and persist findings to the database."""
    import json
    from app.config import get_settings
    from app.db import get_connection
    from app.annotate.matcher import match_all
    from app.policy.engine import evaluate

    settings = get_settings()
    con = get_connection(settings)

    console.print("Matching variants against annotation databases...")
    records = match_all(con)
    console.print(f"Found {len(records)} annotation matches")

    if not records:
        con.close()
        console.print("No matches found. Make sure you have loaded genotype data and imported annotations.")
        return

    console.print("Scoring findings through policy engine...")
    count = 0
    for record in records:
        finding = evaluate(record)
        con.execute(
            """INSERT OR REPLACE INTO findings
            (finding_id, rsid, genotype, source_type, evidence_type,
             trait_or_condition, effect_allele, effect_direction,
             effect_size_type, effect_size_value, clinical_significance,
             review_status, confidence_tier, actionability,
             allowed_claims, forbidden_claims, user_visible_notes,
             source_refs, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                finding.finding_id, finding.rsid, finding.genotype,
                finding.source_type, finding.evidence_type,
                finding.trait_or_condition, finding.effect_allele,
                finding.effect_direction, finding.effect_size_type,
                finding.effect_size_value, finding.clinical_significance,
                finding.review_status, finding.confidence_tier,
                finding.actionability,
                json.dumps(finding.allowed_claims),
                json.dumps(finding.forbidden_claims),
                json.dumps(finding.user_visible_notes),
                json.dumps([r.model_dump() for r in finding.source_refs]),
                finding.created_at.isoformat(),
            ],
        )
        count += 1

    con.close()

    console.print(f"\n[green]Persisted {count} findings to database.[/green]")
    console.print("Run [bold]dna findings[/bold] to browse results.")


@app.command(name="findings")
def list_findings(
    confidence: str = typer.Option(None, "--confidence", "-c", help="Filter by confidence tier: high, medium, low"),
    actionable: bool = typer.Option(False, "--actionable", "-a", help="Show only actionable findings (discuss_with_clinician or medication_relevance)"),
    source: str = typer.Option(None, "--source", "-s", help="Filter by source: gwas or clinvar"),
    limit: int = typer.Option(0, "--limit", "-n", help="Max rows to show (0 = all)"),
) -> None:
    """Browse persisted findings with optional filters."""
    from app.config import get_settings
    from app.db import get_connection

    settings = get_settings()
    con = get_connection(settings)

    query = 'SELECT * FROM "findings" WHERE 1=1'
    params: list = []

    if confidence:
        query += " AND confidence_tier = ?"
        params.append(confidence)
    if actionable:
        query += " AND actionability != 'none'"
    if source:
        query += " AND source_type = ?"
        params.append(source)

    query += " ORDER BY CASE confidence_tier WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, trait_or_condition"

    if limit > 0:
        query += f" LIMIT {limit}"

    rows = con.execute(query, params).fetchall()
    columns = [desc[0] for desc in con.description]
    con.close()

    if not rows:
        console.print("No findings found. Run [bold]dna run-all[/bold] first to generate findings.")
        return

    table = Table(title=f"Findings ({len(rows)} results)")
    table.add_column("rsid", style="bold")
    table.add_column("gene/trait")
    table.add_column("confidence", style="bold")
    table.add_column("actionability")
    table.add_column("evidence")
    table.add_column("source")
    table.add_column("genotype")
    table.add_column("clinical_significance")

    col_idx = {name: i for i, name in enumerate(columns)}
    for row in rows:
        conf = row[col_idx["confidence_tier"]]
        conf_style = {"high": "[red]high[/red]", "medium": "[yellow]medium[/yellow]", "low": "low"}.get(conf, conf)

        act = row[col_idx["actionability"]]
        act_style = "[red]discuss_with_clinician[/red]" if act == "discuss_with_clinician" else act

        table.add_row(
            row[col_idx["rsid"]],
            row[col_idx["trait_or_condition"]],
            conf_style,
            act_style,
            row[col_idx["evidence_type"]],
            row[col_idx["source_type"]],
            row[col_idx["genotype"]],
            row[col_idx["clinical_significance"]] or "-",
        )

    console.print(table)
