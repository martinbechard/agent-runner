#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
cd "$repo_root"

prompt_file="${PROMPT_FILE:-.methodology/docs/prompts/PR-030-ph007-verification-sweep.md}"
project_dir="${PROJECT_DIR:-tests/fixtures/ph007-hello-world-workspace}"
run_dir="${RUN_DIR:-work/ph007-verification-sweep-run}"
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
  "$@"
