#!/usr/bin/env bash
set -euo pipefail

RAW_FASTA_GZ="${RAW_FASTA_GZ:-/autodl-fs/data/open-rosalind-kb/standard/raw/ensembl/Homo_sapiens.GRCh38.cdna.all.fa.gz}"
OUT_FASTA="${OUT_FASTA:-/autodl-fs/data/open-rosalind-kb/standard/index/blast/ensembl_cdna.fasta}"
OUT_DB="${OUT_DB:-/autodl-fs/data/open-rosalind-kb/standard/index/blast/ensembl_cdna}"

mkdir -p "$(dirname "$OUT_FASTA")"

if [[ ! -s "$OUT_FASTA" ]]; then
  gzip -dc "$RAW_FASTA_GZ" > "$OUT_FASTA"
fi

makeblastdb \
  -in "$OUT_FASTA" \
  -dbtype nucl \
  -parse_seqids \
  -out "$OUT_DB"
