#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
cd "$repo_root"

prompt_file="docs/prompts/PR-024-ph002-architecture.md"
project_dir="tests/fixtures/ph002-hello-world-workspace"
run_dir="work/ph002-architecture-run"
prompt_runner_bin=".venv/bin/prompt-runner"

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

"$prompt_runner_bin" parse "$prompt_file"
"$prompt_runner_bin" run "$prompt_file" \
  --verbose \
  --project-dir "$project_dir" \
  --run-dir "$run_dir" \
  "$@"
