#!/usr/bin/env bash
set -euo pipefail

TARGETS="${1:-protein_sequence_window,dna_sequence_window}"
LIMIT="${2:-1024}"
WINDOW_SIZE="${3:-128}"
STRIDE="${4:-64}"
BATCH_SIZE="${5:-1}"
SOURCE_LIMIT="${6:-0}"
MODEL="${MODEL:-dnagpt/OmniGene-4-CPT-v2-4bit}"
CONFIG="${CONFIG:-configs/standard.yaml}"

export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export DNARAG_VECTOR_PROGRESS_EVERY="${DNARAG_VECTOR_PROGRESS_EVERY:-16}"

python -m dnarag.cli build-vector \
  --config "$CONFIG" \
  --targets "$TARGETS" \
  --backend transformers4bit \
  --model "$MODEL" \
  --pooling mean \
  --dtype auto \
  --batch-size "$BATCH_SIZE" \
  --limit "$LIMIT" \
  --store chroma \
  --sequence-window-size "$WINDOW_SIZE" \
  --sequence-stride "$STRIDE" \
  --sequence-source-limit "$SOURCE_LIMIT"
