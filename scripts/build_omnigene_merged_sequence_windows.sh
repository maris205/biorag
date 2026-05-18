#!/usr/bin/env bash
set -euo pipefail

TARGETS="${1:-protein_sequence_window,dna_sequence_window}"
LIMIT="${2:-10000}"
WINDOW_SIZE="${3:-128}"
STRIDE="${4:-64}"
BATCH_SIZE="${5:-8}"
SOURCE_LIMIT="${6:-0}"
MODEL="${MODEL:-dnagpt/OmniGene-4-CPT-v2-merged}"
CONFIG="${CONFIG:-configs/standard.yaml}"
HF_HOME="${HF_HOME:-/root/autodl-tmp/huggingface}"
USE_AUTODL_PROXY="${USE_AUTODL_PROXY:-1}"
HF_PROXY="${HF_PROXY:-}"

if [ "$USE_AUTODL_PROXY" = "1" ] && [ -f /etc/network_turbo ]; then
  # AutoDL proxy for Hugging Face cache misses.
  # shellcheck disable=SC1091
  source /etc/network_turbo
fi

if [ -n "$HF_PROXY" ]; then
  export http_proxy="$HF_PROXY"
  export https_proxy="$HF_PROXY"
  export HTTP_PROXY="$HF_PROXY"
  export HTTPS_PROXY="$HF_PROXY"
fi

export HF_HOME
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
export DNARAG_VECTOR_PROGRESS_EVERY="${DNARAG_VECTOR_PROGRESS_EVERY:-100}"

if [ "${USE_LOCAL_SNAPSHOT:-1}" = "1" ] && [[ "$MODEL" == */* ]]; then
  SNAPSHOT_ROOT="$HF_HOME/models--${MODEL/\//--}/snapshots"
  if [ -d "$SNAPSHOT_ROOT" ]; then
    SNAPSHOT_PATH="$(find "$SNAPSHOT_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
    if [ -n "$SNAPSHOT_PATH" ]; then
      MODEL="$SNAPSHOT_PATH"
      export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
      export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
    fi
  fi
fi

python -m dnarag.cli build-vector \
  --config "$CONFIG" \
  --targets "$TARGETS" \
  --backend omnigene \
  --model "$MODEL" \
  --pooling mean \
  --dtype bf16 \
  --batch-size "$BATCH_SIZE" \
  --limit "$LIMIT" \
  --store chroma \
  --sequence-window-size "$WINDOW_SIZE" \
  --sequence-stride "$STRIDE" \
  --sequence-source-limit "$SOURCE_LIMIT"
