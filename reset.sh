#!/usr/bin/env bash
set -e

echo "Removing database..."
rm -f dna_analysis.duckdb dna_analysis.duckdb.wal
echo "Done. Database wiped."
echo ""
echo "To reload, run:"
echo "  ./import.sh data/raw/YourFile.csv"
