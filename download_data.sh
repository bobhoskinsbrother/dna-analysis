#!/usr/bin/env bash
set -e

DATA_DIR="data/curated"
mkdir -p "$DATA_DIR"

echo "Downloading GWAS Catalog associations..."
curl -L "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/gwas-catalog-associations_ontology-annotated-full.zip" \
    -o "$DATA_DIR/gwas-catalog.zip"
unzip -o "$DATA_DIR/gwas-catalog.zip" -d "$DATA_DIR"
mv "$DATA_DIR/gwas-catalog-download-associations-alt-full.tsv" "$DATA_DIR/gwas_catalog_associations.tsv"
rm "$DATA_DIR/gwas-catalog.zip"
echo "GWAS: $(wc -l < "$DATA_DIR/gwas_catalog_associations.tsv") rows"

echo ""
echo "Downloading ClinVar variant_summary..."
curl -L "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz" \
    -o "$DATA_DIR/variant_summary.txt.gz"
gunzip -f "$DATA_DIR/variant_summary.txt.gz"
echo "ClinVar: $(wc -l < "$DATA_DIR/variant_summary.txt") rows"

echo ""
echo "Done. Files in $DATA_DIR:"
ls -lh "$DATA_DIR"
