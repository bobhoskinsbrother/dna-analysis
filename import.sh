#!/usr/bin/env bash
set -e

# ──────────────────────────────────────────────────────────────
# import.sh — Run the full DNA analysis pipeline in Docker
#
# Usage:
#   ./import.sh <path-to-myheritage-csv>
#
# Example:
#   ./import.sh data/raw/MyHeritage_raw_dna_data.csv
#
# Prerequisites:
#   - Docker running
#   - Annotation databases downloaded (run ./download_data.sh first)
# ──────────────────────────────────────────────────────────────

if [ -z "$1" ]; then
    echo "Usage: ./import.sh <path-to-myheritage-csv>"
    exit 1
fi

DNA_FILE="$1"

if [ ! -f "$DNA_FILE" ]; then
    echo "Error: File not found: $DNA_FILE"
    exit 1
fi

GWAS_FILE="data/curated/gwas_catalog_associations.tsv"
CLINVAR_FILE="data/curated/variant_summary.txt"

if [ ! -f "$GWAS_FILE" ]; then
    echo "Error: GWAS Catalog not found. Run ./download_data.sh first."
    exit 1
fi

if [ ! -f "$CLINVAR_FILE" ]; then
    echo "Error: ClinVar data not found. Run ./download_data.sh first."
    exit 1
fi

echo "Building container..."
docker compose build --quiet

echo ""
echo "Step 1/5: Initialising database..."
docker compose run --rm app dna init-db

echo ""
echo "Step 2/5: Loading genotype data..."
docker compose run --rm app dna load "$DNA_FILE"

echo ""
echo "Step 3/5: Importing GWAS Catalog (this may take a minute)..."
docker compose run --rm app dna import-gwas "$GWAS_FILE"

echo ""
echo "Step 4/5: Importing ClinVar (this may take several minutes)..."
docker compose run --rm app dna import-clinvar "$CLINVAR_FILE"

echo ""
echo "Step 5/5: Matching and scoring all variants..."
docker compose run --rm app dna run-all

echo ""
echo "Done. Database saved to dna_analysis.duckdb"
echo ""
echo "Browse your results:"
echo "  docker compose run --rm app dna findings                    # all findings (sorted by confidence)"
echo "  docker compose run --rm app dna findings --actionable       # only actionable findings"
echo "  docker compose run --rm app dna findings -c high            # high confidence only"
echo "  docker compose run --rm app dna findings -s clinvar         # ClinVar only"
echo "  docker compose run --rm app dna findings -a -n 20           # top 20 actionable"
echo "  docker compose run --rm app dna match rs429358              # look up a specific variant"
