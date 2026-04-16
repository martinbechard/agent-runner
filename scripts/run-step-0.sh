#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
cd "$repo_root"

prompt_file=".methodology/docs/prompts/PR-021-hello-world-requirements-inventory-and-checklist.md"
run_dir="work/pr-021-run"
prompt_runner_bin=".venv/bin/prompt-runner"
request_path="docs/requests/hello-world-python-app.md"
artifact_prefix="requirements-inventory"

rm -rf "$run_dir"
git worktree prune >/dev/null 2>&1 || true

"$prompt_runner_bin" parse "$prompt_file"
"$prompt_runner_bin" run "$prompt_file" \
  --verbose \
  --project-dir "$repo_root" \
  --run-dir "$run_dir" \
  --var "request_path=$request_path" \
  --var "artifact_prefix=$artifact_prefix" \
  "$@"
