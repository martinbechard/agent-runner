// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Provide deterministic full-application data for browser development.
// Design: docs/design/components/CD-005-agent-report-dynamic-workspace.md

import type { AppCommandName, AppTransport } from "../app-transport";
import type { WorkspaceCommandName } from "../report-workspace";
import { FixtureWorkspaceTransport } from "../../tests/browser/fixture-workspace-transport";
import { FIXTURE_ROOT_ID } from "../../tests/browser/heatmap-fixtures";

const ROOT_REF = "fixture-root-ref";

export class FullAppFixtureTransport implements AppTransport {
  private readonly workspace = new FixtureWorkspaceTransport();

  invoke(command: WorkspaceCommandName, request: unknown): Promise<unknown> {
    const input = request as Record<string, unknown>;
    if (command === "list_agents" || command === "list_turns" || command === "list_events" || command === "query_coordination") {
      return Promise.resolve({
        snapshotId: input.snapshotId,
        revision: "fixture-revision-1",
        operation: command,
        items: [],
        appliedFilters: input.filters,
        appliedSort: input.sort,
        pageSize: input.pageSize,
        nextCursor: null,
      });
    }
    if (command === "query_sequence") {
      return Promise.resolve({ page: {
        snapshotId: input.snapshotId,
        revision: "fixture-revision-1",
        operation: command,
        items: [],
        appliedFilters: input.filters,
        appliedSort: input.sort,
        pageSize: input.pageSize,
        nextCursor: null,
      }, groups: [] });
    }
    if (command === "export_snapshot") {
      return Promise.resolve({
        operationId: input.operationId, snapshotId: input.snapshotId, revision: "fixture-revision-1",
        exportId: "fixture-report-export", displayName: "fixture-report", mode: input.mode,
        manifestSha256: null, fileCount: 5, totalByteCount: 4096, warnings: [], omissions: [],
      });
    }
    if (command === "cancel_report_operation" || command === "open_source_location" || command === "open_diagnostic_log" || command === "reopen_export") return Promise.resolve(null);
    return this.workspace.invoke(command, request);
  }

  subscribeProgress(_listener: (value: unknown) => void): () => void {
    return this.workspace.subscribeProgress();
  }

  async subscribeParentReport(): Promise<() => void> {
    return () => undefined;
  }

  async invokeApp(command: AppCommandName, _payload?: unknown, onProgress?: (value: unknown) => void): Promise<unknown> {
    if (command === "desktop_defaults") {
      return { roots: [{ rootRef: ROOT_REF, displayName: "Fixture sessions" }], diagnosticsAvailable: true };
    }
    if (command === "add_root") return [{ rootRef: ROOT_REF, displayName: "Fixture sessions" }];
    if (command === "search_rollouts") {
      onProgress?.({ completed_files: 1, candidate_files: 1, sourceLabel: "Canonical fixture", source: "scan" });
      return {
        entries: [{
          threadId: FIXTURE_ROOT_ID,
          parentThreadId: "",
          taskTitle: "Canonical Heatmap report",
          startedAt: "2026-08-12T12:00:00Z",
          lastActivityAt: "2026-08-12T16:00:00Z",
          workspaceLabel: "Fixture workspace",
          sourceRef: "fixture-source-ref",
          sourceLabel: "Synthetic rollout",
          agentLabel: "default",
          agentNickname: "",
          delegationCount: 0,
          diagnostic: null,
        }],
        stats: { candidate_files: 1, scanned_files: 1, cached_files: 0, unstable_files: 0, unreadable_files: 0, elapsed_ms: 4, workers: 1 },
      };
    }
    if (command === "export_catalog") return { exportId: "fixture-catalog-export", displayName: "fixture-index.html", entryCount: 1 };
    if (command === "open_report_window" || command === "open_diagnostic_log" || command === "record_client_error") return null;
    return this.workspace.invoke(command, _payload ?? {});
  }
}
