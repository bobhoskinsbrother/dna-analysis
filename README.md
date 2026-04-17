# DNA Analysis

A local-first DNA variant interpreter. Ingests a raw genotype export from MyHeritage, annotates each variant against curated public databases (GWAS Catalog, ClinVar), scores the strength of evidence, and presents findings with confidence tiers and actionability labels.

All processing runs locally in Docker. Your genetic data never leaves your machine.

## Prerequisites

- Docker

## Quick start

```bash
# 1. Download public annotation databases (~1GB download, ~4.5GB extracted)
./download_data.sh

# 2. Place your MyHeritage CSV export in data/raw/

# 3. Run the full pipeline
./import.sh data/raw/YourFile.csv
```

## Browsing results

```bash
# All findings, sorted by confidence (high → medium → low)
./dna findings

# Only actionable findings (worth discussing with a doctor)
./dna findings --actionable

# Filter by confidence tier
./dna findings -c high
./dna findings -c medium

# Filter by source database
./dna findings -s clinvar
./dna findings -s gwas

# Combine filters
./dna findings -a -c high -n 20

# Look up a specific variant
./dna match rs429358
```

## Explaining findings (Phase 2 — LLM)

```bash
# Get a plain-English explanation of a finding (uses the finding ID from the table above)
./dna explain <finding_id>

# Ask a follow-up question about a finding
./dna ask <finding_id> "What does this mean for my health?"
```

Requires LLM configuration in `.env`:

```
DNA_LLM_MODEL=gpt-4o-mini
DNA_LLM_API_BASE=                  # leave empty for OpenAI, or http://localhost:11434/v1 for Ollama
DNA_LLM_API_KEY=your-api-key
```

The LLM never sees your raw DNA data — it only receives pre-scored Finding objects with strict guardrails on what it can and cannot say.

## Individual pipeline steps

```bash
./dna init-db                                     # create database
./dna load data/raw/YourFile.csv                  # load genotype data
./dna import-gwas data/curated/gwas_catalog_associations.tsv   # import GWAS
./dna import-clinvar data/curated/variant_summary.txt           # import ClinVar
./dna run-all                                     # match + score all variants
```

## Reset and reload

```bash
./reset.sh                          # wipe the database
./import.sh data/raw/YourFile.csv   # reload from scratch
```

## Running tests

```bash
./test.sh
```

## How findings are scored

Each finding is assigned a **confidence tier** and **actionability label**:

| Confidence | Meaning |
|---|---|
| high | ClinVar expert panel or practice guideline (3-4 stars) |
| medium | ClinVar multiple submitters (2 stars) or GWAS genome-wide significant (p < 5e-8) |
| low | Single submitter, no criteria, or weak GWAS association |

| Actionability | Meaning |
|---|---|
| none | Informational only |
| discuss_with_clinician | Pathogenic or likely pathogenic — worth raising with a doctor |
| medication_relevance | May affect drug response — discuss with clinician or pharmacist |

GWAS associations are never assigned high confidence regardless of p-value, because statistical association is fundamentally different from clinical interpretation.

## Architecture

See [agents.md](agents.md) for the full specification including database schema, data flow, policy engine rules, and LLM guardrails.
