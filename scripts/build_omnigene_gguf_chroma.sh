#!/usr/bin/env bash
set -euo pipefail

TARGETS="${1:-protein_sequence}"
LIMIT="${2:-0}"
MODEL_ID="${MODEL_ID:-dnagpt/OmniGene-4-CPT-v2-GGUF}"
FILENAME="${FILENAME:-OmniGene-4-CPT-v2-Q4_K_M.gguf}"
HF_HOME="${HF_HOME:-/root/autodl-tmp/huggingface}"
MODEL_PATH="${MODEL_PATH:-}"

export HF_HOME
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
export DNARAG_GGUF_N_CTX="${DNARAG_GGUF_N_CTX:-1024}"
export DNARAG_GGUF_N_BATCH="${DNARAG_GGUF_N_BATCH:-64}"
export DNARAG_GGUF_N_UBATCH="${DNARAG_GGUF_N_UBATCH:-64}"
export DNARAG_GGUF_N_GPU_LAYERS="${DNARAG_GGUF_N_GPU_LAYERS:--1}"
export DNARAG_VECTOR_PROGRESS_EVERY="${DNARAG_VECTOR_PROGRESS_EVERY:-1000}"

if [ -z "$MODEL_PATH" ]; then
  SNAPSHOT_ROOT="$HF_HOME/models--${MODEL_ID/\//--}/snapshots"
  if [ -d "$SNAPSHOT_ROOT" ]; then
    MODEL_PATH="$(find "$SNAPSHOT_ROOT" -mindepth 2 -maxdepth 2 -name "$FILENAME" | sort | tail -n 1)"
  fi
fi

if [ -z "$MODEL_PATH" ]; then
  MODEL_PATH="$MODEL_ID"
fi

APPEND_ARGS=()
if [ "${APPEND:-0}" = "1" ]; then
  APPEND_ARGS+=(--append)
fi

python -m dnarag.cli build-vector \
  --config configs/standard.yaml \
  --backend gguf \
  --model "$MODEL_PATH" \
  --targets "$TARGETS" \
  --pooling mean \
  --batch-size "${BATCH_SIZE:-16}" \
  --limit "$LIMIT" \
  --store chroma \
  "${APPEND_ARGS[@]}"
