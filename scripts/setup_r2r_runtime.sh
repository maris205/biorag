#!/usr/bin/env bash
set -euo pipefail

# R2R 3.6.6 has mutually incompatible published OpenAI/LiteLLM constraints.
# Reuse the upstream v3.6.5 frozen lock, then overlay only the 3.6.6 package.
workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${1:-${workspace_root}/.venv-r2r}"
lock_checkout="${R2R_LOCK_CHECKOUT:-${workspace_root}/.cache/R2R-v3.6.5}"
lock_commit="191501190864e0762b9084ba96d066372456012c"

command -v git >/dev/null
command -v uv >/dev/null

if [[ ! -d "${lock_checkout}/.git" ]]; then
  mkdir -p "$(dirname "${lock_checkout}")"
  git clone --branch v3.6.5 --depth 1 https://github.com/SciPhi-AI/R2R.git "${lock_checkout}"
fi

if [[ "$(git -C "${lock_checkout}" rev-parse HEAD)" != "${lock_commit}" ]]; then
  git -C "${lock_checkout}" fetch --depth 1 origin "${lock_commit}"
fi
git -C "${lock_checkout}" checkout --detach "${lock_commit}"
runtime_dir="$(realpath -m "${runtime_dir}")"
mkdir -p "$(dirname "${runtime_dir}")"

(
  cd "${lock_checkout}"
  UV_PROJECT_ENVIRONMENT="${runtime_dir}" uv sync --frozen --extra core --no-dev
)
uv pip install --python "${runtime_dir}/bin/python" --no-deps --reinstall 'r2r==3.6.6'
"${runtime_dir}/bin/python" -c 'import r2r; print(f"R2R runtime ready: {r2r.__version__}")'
