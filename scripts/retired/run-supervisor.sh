#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_ROOT="${WORK_ROOT:-/tmp/ar-supervisor-work}"
PROMPT_FILE="${1:-.methodology/docs/prompts/PR-014-methodology-autopilot-supervisor.md}"
if [[ $# -gt 0 ]]; then
  shift
fi

mkdir -p "$WORK_ROOT"

rsync -a --delete \
  --exclude '.git/' \
  --exclude 'runs/' \
  --exclude 'tmp/' \
  --exclude '.venv/' \
  --exclude '.pytest_cache/' \
  --exclude '__pycache__/' \
  "$REPO_ROOT/" "$WORK_ROOT/"

cd "$WORK_ROOT"
PYTHONPATH=src/cli:.prompt-runner/src/cli python -m prompt_runner run "$PROMPT_FILE" "$@"
