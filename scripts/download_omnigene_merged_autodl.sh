#!/usr/bin/env bash
set -euo pipefail

MODEL_ID="${MODEL_ID:-dnagpt/OmniGene-4-CPT-v2-merged}"
HF_HOME="${HF_HOME:-/root/autodl-tmp/huggingface}"
USE_AUTODL_PROXY="${USE_AUTODL_PROXY:-1}"
HF_PROXY="${HF_PROXY:-}"

if [ "$USE_AUTODL_PROXY" = "1" ] && [ -f /etc/network_turbo ]; then
  # AutoDL proxy for Hugging Face downloads.
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
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
export HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-120}"
export HF_HUB_ETAG_TIMEOUT="${HF_HUB_ETAG_TIMEOUT:-30}"
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"

mkdir -p "$HF_HOME"

python - <<'PY'
import os
import sys
import time
from huggingface_hub import hf_hub_download

model_id = os.environ.get("MODEL_ID", "dnagpt/OmniGene-4-CPT-v2-merged")
cache_dir = os.environ.get("HF_HOME", "/root/autodl-tmp/huggingface")
max_retries = int(os.environ.get("HF_DOWNLOAD_RETRIES", "12"))
files = [
    ".gitattributes",
    "README.md",
    "chat_template.jinja",
    "config.json",
    "cpt_meta.json",
    "generation_config.json",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
    *[f"model-{idx:05d}-of-00011.safetensors" for idx in range(1, 12)],
]

started = time.monotonic()
last_path = None
for number, filename in enumerate(files, start=1):
    file_started = time.monotonic()
    print(f"[{number:02d}/{len(files):02d}] start {filename}", flush=True)
    for attempt in range(1, max_retries + 1):
        try:
            last_path = hf_hub_download(
                repo_id=model_id,
                filename=filename,
                cache_dir=cache_dir,
                resume_download=True,
                etag_timeout=int(os.environ.get("HF_HUB_ETAG_TIMEOUT", "30")),
            )
            break
        except Exception as exc:
            print(
                f"[{number:02d}/{len(files):02d}] retry {attempt}/{max_retries} {filename}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            if attempt == max_retries:
                raise
            time.sleep(min(60, 5 * attempt))
    size = os.path.getsize(last_path) if last_path else 0
    elapsed = time.monotonic() - file_started
    print(f"[{number:02d}/{len(files):02d}] done {filename} {size / 1024**2:.1f} MiB in {elapsed:.1f}s", flush=True)

elapsed = time.monotonic() - started
if last_path:
    print(os.path.dirname(last_path))
else:
    print(cache_dir)
print(f"download_elapsed_s={elapsed:.1f}", flush=True)
PY
