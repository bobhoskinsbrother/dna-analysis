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
docker compose run --rm app dna findings

# Only actionable findings (worth discussing with a doctor)
docker compose run --rm app dna findings --actionable

# Filter by confidence tier
docker compose run --rm app dna findings -c high
docker compose run --rm app dna findings -c medium

# Filter by source database
docker compose run --rm app dna findings -s clinvar
docker compose run --rm app dna findings -s gwas

# Combine filters
docker compose run --rm app dna findings -a -c high -n 20

# Look up a specific variant
docker compose run --rm app dna match rs429358
```

## Individual pipeline steps

```bash
docker compose run --rm app dna init-db                                     # create database
docker compose run --rm app dna load data/raw/YourFile.csv                  # load genotype data
docker compose run --rm app dna import-gwas data/curated/gwas_catalog_associations.tsv   # import GWAS
docker compose run --rm app dna import-clinvar data/curated/variant_summary.txt           # import ClinVar
docker compose run --rm app dna run-all                                     # match + score all variants
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

See [agents.md](agents.md) for the full specification including database schema, data flow, policy engine rules, and LLM integration plan (Phase 2).
