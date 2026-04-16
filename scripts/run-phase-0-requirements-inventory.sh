#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
cd "$repo_root"

prompt_file=".methodology/docs/prompts/PR-025-ph000-requirements-inventory.md"
project_dir="tests/fixtures/ph000-hello-world-workspace"
run_dir="work/ph000-requirements-inventory-run"
raw_requirements_path="docs/requirements/raw-requirements.md"
export PYTHONPATH=".prompt-runner/src/cli${PYTHONPATH:+:$PYTHONPATH}"
prompt_runner=(python -m prompt_runner)

preserve_run_dir=false
for arg in "$@"; do
  if [[ "$arg" == "--resume" || "$arg" == "--judge-only" ]]; then
    preserve_run_dir=true
  fi
done

if [[ "$preserve_run_dir" == false ]]; then
  rm -rf "$run_dir"
  git worktree prune >/dev/null 2>&1 || true
fi

"${prompt_runner[@]}" parse "$prompt_file"
"${prompt_runner[@]}" run "$prompt_file" \
  --verbose \
  --project-dir "$project_dir" \
  --run-dir "$run_dir" \
  --var "raw_requirements_path=$raw_requirements_path" \
  "$@"
