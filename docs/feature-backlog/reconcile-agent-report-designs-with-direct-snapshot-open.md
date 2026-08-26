# Reconcile Agent Report Designs With Direct Snapshot Opening

Status: Ready

Type: Feature

Provider: file

Work Item ID: reconcile-agent-report-designs-with-direct-snapshot-open

Completion: UNSET

## Summary

Reconcile the remaining Agent Report component designs with the accepted direct snapshot-opening and desktop-configuration model.

## Context

FR-001, ARC-001, HLD-003, and CD-005 now remove preflight, open snapshots directly, and place discovery, scope, report-output, and normalized-database settings in desktop configuration. CD-002, CD-003, and CD-004 still describe the superseded preflight and fixed-database contracts.

## Source Evidence

The user requested this work item in the current Codex task after reviewing the Agent Report documentation changes.

## Requirements

- Reconcile CD-002, CD-003, and CD-004 with FR-001, ARC-001, HLD-003, and CD-005.
- Remove the superseded preflight contracts and use direct `open_snapshot` behavior.
- Align configuration and normalized-database ownership with the accepted Tauri configuration model.
- Restore cross-document consistency and documentation acceptance.

## Acceptance Criteria

- CD-002, CD-003, and CD-004 no longer define preflight as a product operation or workflow.
- Their snapshot, worker, cache, MCP, configuration, error, and verification contracts agree with the accepted parent documents.
- Documentation review confirms the Agent Report design set is internally consistent.

## Dependencies

None.

## Verification

- Run the applicable documentation reviews and page verification.
- Search the active Agent Report design set for stale preflight and fixed normalized-database assumptions.
- Run `git diff --check`.

## Open Questions

None.
