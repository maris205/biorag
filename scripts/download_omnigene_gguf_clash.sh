#!/usr/bin/env bash
set -euo pipefail

MODEL_ID="${MODEL_ID:-dnagpt/OmniGene-4-CPT-v2-GGUF}"
FILENAME="${FILENAME:-OmniGene-4-CPT-v2-Q4_K_M.gguf}"
HF_HOME="${HF_HOME:-/root/autodl-tmp/huggingface}"
HF_PROXY="${HF_PROXY:-http://127.0.0.1:7890}"
HF_DOWNLOAD_RETRIES="${HF_DOWNLOAD_RETRIES:-8}"

export HF_HOME
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
export HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-120}"
export HF_HUB_ETAG_TIMEOUT="${HF_HUB_ETAG_TIMEOUT:-30}"

if [ -n "$HF_PROXY" ]; then
  export http_proxy="$HF_PROXY"
  export https_proxy="$HF_PROXY"
  export HTTP_PROXY="$HF_PROXY"
  export HTTPS_PROXY="$HF_PROXY"
fi

mkdir -p "$HF_HOME"

python - <<'PY'
import os
import sys
import time

from huggingface_hub import hf_hub_download

model_id = os.environ.get("MODEL_ID", "dnagpt/OmniGene-4-CPT-v2-GGUF")
filename = os.environ.get("FILENAME", "OmniGene-4-CPT-v2-Q4_K_M.gguf")
cache_dir = os.environ.get("HF_HOME", "/root/autodl-tmp/huggingface")
max_retries = int(os.environ.get("HF_DOWNLOAD_RETRIES", "8"))

for attempt in range(1, max_retries + 1):
    started = time.monotonic()
    print(f"[{attempt}/{max_retries}] start {model_id}/{filename}", flush=True)
    try:
        path = hf_hub_download(
            repo_id=model_id,
            filename=filename,
            cache_dir=cache_dir,
            resume_download=True,
            etag_timeout=int(os.environ.get("HF_HUB_ETAG_TIMEOUT", "30")),
        )
        elapsed = time.monotonic() - started
        size = os.path.getsize(path)
        print(f"done {path}", flush=True)
        print(f"size {size / 1024**3:.2f} GiB in {elapsed:.1f}s", flush=True)
        break
    except Exception as exc:
        print(f"retry {attempt}/{max_retries}: {exc}", file=sys.stderr, flush=True)
        if attempt == max_retries:
            raise
        time.sleep(min(30, attempt * 3))
PY
