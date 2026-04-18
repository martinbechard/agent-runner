#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
cd "$repo_root"

seed_workspace="${SEED_WORKSPACE:-tools/methodology-runner/fixtures/ph000-hello-world-workspace}"
workspace="${WORKSPACE:-work/full-pipeline-workspace}"
runs_root="${RUNS_ROOT:-work/full-pipeline-runs}"

preserve_state=false
for arg in "$@"; do
  if [[ "$arg" == "--resume" || "$arg" == "--judge-only" ]]; then
    preserve_state=true
  fi
done

if [[ "$preserve_state" == false ]]; then
  rm -rf "$workspace" "$runs_root"
  mkdir -p "$(dirname "$workspace")" "$runs_root"
  cp -R "$seed_workspace" "$workspace"
  git worktree prune >/dev/null 2>&1 || true
fi

run_phase() {
  local phase_name="$1"
  local run_dir="$2"
  local script_path="$3"
  shift 3
  echo
  echo "===== $phase_name ====="
  PROJECT_DIR="$workspace" RUN_DIR="$run_dir" "$script_path" "$@"
  rsync -a --delete --exclude '.run-files/' --exclude '.git/' "$run_dir"/ "$workspace"/
}

run_phase "PH-000 requirements inventory" "$runs_root/ph000" ./tools/methodology-runner/scripts/run-phase-0-requirements-inventory.sh "$@"
run_phase "PH-001 feature specification" "$runs_root/ph001" ./tools/methodology-runner/scripts/run-phase-1-feature-specification.sh "$@"
run_phase "PH-002 architecture" "$runs_root/ph002" ./tools/methodology-runner/scripts/run-phase-2-architecture.sh "$@"
run_phase "PH-003 solution design" "$runs_root/ph003" ./tools/methodology-runner/scripts/run-phase-3-solution-design.sh "$@"
run_phase "PH-004 interface contracts" "$runs_root/ph004" ./tools/methodology-runner/scripts/run-phase-4-interface-contracts.sh "$@"
run_phase "PH-005 intelligent simulations" "$runs_root/ph005" ./tools/methodology-runner/scripts/run-phase-5-intelligent-simulations.sh "$@"
run_phase "PH-006 incremental implementation" "$runs_root/ph006" ./tools/methodology-runner/scripts/run-phase-6-incremental-implementation.sh "$@"
run_phase "PH-007 verification sweep" "$runs_root/ph007" ./tools/methodology-runner/scripts/run-phase-7-verification-sweep.sh "$@"

echo
echo "Full methodology pipeline completed."
echo "Workspace: $workspace"
echo "Run directories: $runs_root"
