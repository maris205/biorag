#!/usr/bin/env bash
set -euo pipefail

TARGETS="${1:-text}"
LIMIT="${2:-1000}"
MODEL_ID="${MODEL_ID:-dnagpt/OmniGene-4-CPT-v2-merged}"
DTYPE="${DTYPE:-bf16}"
HF_HOME="${HF_HOME:-/root/autodl-tmp/huggingface}"
USE_AUTODL_PROXY="${USE_AUTODL_PROXY:-1}"
HF_PROXY="${HF_PROXY:-}"

if [ "$USE_AUTODL_PROXY" = "1" ] && [ -f /etc/network_turbo ]; then
  # AutoDL proxy for Hugging Face downloads/cache misses.
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

if [ "${USE_LOCAL_SNAPSHOT:-1}" = "1" ] && [[ "$MODEL_ID" == */* ]]; then
  SNAPSHOT_ROOT="$HF_HOME/models--${MODEL_ID/\//--}/snapshots"
  if [ -d "$SNAPSHOT_ROOT" ]; then
    SNAPSHOT_PATH="$(find "$SNAPSHOT_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
    if [ -n "$SNAPSHOT_PATH" ]; then
      MODEL_ID="$SNAPSHOT_PATH"
      export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
      export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
    fi
  fi
fi

python -m dnarag.cli build-vector \
  --config configs/standard.yaml \
  --backend omnigene \
  --model "$MODEL_ID" \
  --targets "$TARGETS" \
  --pooling mean \
  --dtype "$DTYPE" \
  --batch-size "${BATCH_SIZE:-1}" \
  --limit "$LIMIT"
