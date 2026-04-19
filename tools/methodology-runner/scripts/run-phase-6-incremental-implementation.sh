#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
cd "$repo_root"

prompt_file="${PROMPT_FILE:-tools/methodology-runner/docs/prompts/PR-029-ph006-incremental-implementation.md}"
project_dir="${PROJECT_DIR:-sample/hello-world/fixtures/ph006-hello-world-workspace}"
run_dir="${RUN_DIR:-work/ph006-incremental-implementation-run}"
export PYTHONPATH="tools/prompt-runner/src${PYTHONPATH:+:$PYTHONPATH}"
prompt_runner=(python -m prompt_runner)
python_bin="$(command -v python3 || command -v python)"
child_prompt_runner_command="PYTHONPATH=\"$repo_root/tools/prompt-runner/src\" \"$python_bin\" -m prompt_runner"

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
  --var "prompt_runner_command=$child_prompt_runner_command" \
  "$@"
