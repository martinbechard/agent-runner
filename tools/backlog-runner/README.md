# Backlog Runner

backlog-runner scans typed backlog folders, runs claimed items through
methodology-runner in isolated feature worktrees, and serializes the final
target-branch merge.

The first implementation expects authored markdown backlog items in active
folders such as docs/feature-backlog and docs/defect-backlog. It calls
methodology-runner with --skip-target-merge so parallel workers do not mutate
the shared target branch.

## Commands

- backlog-runner run
- backlog-runner once
- backlog-runner status
- backlog-runner resume
- backlog-runner stop
