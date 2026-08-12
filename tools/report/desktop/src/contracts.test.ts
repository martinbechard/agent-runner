// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify strict desktop and Dynamic Workspace boundary parsing.
// Design: docs/design/components/CD-005-agent-report-dynamic-workspace.md

import { describe, expect, it } from "vitest";

import {
  type AgentFiltersDto,
  type AgentSortDto,
  type CoordinationFiltersDto,
  type CoordinationSortDto,
  type EventFiltersDto,
  type EventSortDto,
  type SequenceFiltersDto,
  type SequenceSortDto,
  type TurnFiltersDto,
  type TurnSortDto,
  dateRangeError,
  discoveryProgressPresentation,
  localDayDateRange,
  localDateHourToUtc,
  localExclusiveDateHourToInclusiveUtcHour,
  normalizeWorkerCount,
  parseAgentPageDto,
  parseCoordinationPageDto,
  parseCloseSnapshotResultDto,
  parseDesktopDefaults,
  parseDiscoveryProgress,
  parseEventDetailDto,
  parseEventPageDto,
  parseExportResult,
  parseExportSnapshotResultDto,
  parseHeatmapResultDto,
  parsePreflightReportDto,
  parseReportErrorDto,
  parseReportGenerationProgress,
  parseReportSummaryDto,
  parseRefreshSnapshotResultDto,
  parseRootReferences,
  parseSearchResponse,
  parseSequencePageDto,
  parseSnapshotMetadataDto,
  parseTurnPageDto,
  parseWorkspaceProgressDto,
} from "./contracts";

const agentFilters: AgentFiltersDto = { query: "", state: null };
const agentSort: AgentSortDto = { key: "last_activity_at", direction: "descending", tieBreakKey: "agent_id", tieBreakDirection: "ascending" };
const turnFilters: TurnFiltersDto = { agentId: null, state: null };
const turnSort: TurnSortDto = { key: "started_at", direction: "ascending", tieBreakKey: "turn_id", tieBreakDirection: "ascending" };
const eventFilters: EventFiltersDto = { agentId: null, turnId: null, kind: null, fromTime: null, toTime: null };
const eventSort: EventSortDto = { key: "occurred_at", direction: "ascending", tieBreakKey: "event_id", tieBreakDirection: "ascending" };
const sequenceFilters: SequenceFiltersDto = { focusAgentId: null, eventKinds: [], grouping: "none", includeReasoning: false };
const sequenceSort: SequenceSortDto = { key: "occurred_at", direction: "ascending", tieBreakKey: "sequence_id", tieBreakDirection: "ascending" };
const coordinationFilters: CoordinationFiltersDto = { workItemId: null, delegatedRootId: null, agentId: null, operation: null, evidence: null };
const coordinationSort: CoordinationSortDto = { key: "occurred_at", direction: "ascending", tieBreakKey: "coordination_id", tieBreakDirection: "ascending" };

const warnings = [{ code: "PARTIAL_SOURCE", message: "One source was unavailable." }];

const snapshot = {
  protocolVersion: 1,
  snapshotId: "snapshot-1",
  revision: "revision-1",
  rootThreadId: "thread-1",
  includeChildren: true,
  includeCollaborators: false,
  sourceRevision: "source-revision-1",
  parserVersion: "1",
  pricingDigest: "a".repeat(64),
  formatterDigest: "b".repeat(64),
  observationTime: "2026-08-12T12:00:00Z",
  mode: "live",
  warnings,
} as const;

function page(operation: string, filters: unknown, sort: unknown, items: readonly unknown[]) {
  return { snapshotId: "snapshot-1", revision: "revision-1", operation, items, appliedFilters: filters, appliedSort: sort, pageSize: 100, nextCursor: null };
}

describe("catalog boundary contracts", () => {
  it("accepts opaque defaults, catalog labels, and exports", () => {
    expect(parseDesktopDefaults({ roots: [{ rootRef: "root-1", displayName: "Codex logs" }], diagnosticsAvailable: true })).toEqual({ roots: [{ rootRef: "root-1", displayName: "Codex logs" }], diagnosticsAvailable: true });
    expect(parseRootReferences([{ rootRef: "root-2", displayName: "Archive" }])).toHaveLength(1);
    expect(parseSearchResponse({
      entries: [{ threadId: "thread-1", parentThreadId: "", taskTitle: "Build workspace", startedAt: "2026-08-12T12:00:00Z", lastActivityAt: "2026-08-12T12:30:00Z", workspaceLabel: "agent-runner", sourceRef: "source-1", sourceLabel: "root.jsonl", agentLabel: "primary", agentNickname: "Codex", delegationCount: 2, diagnostic: { code: "PARTIAL", message: "One log was unreadable." } }],
      stats: { candidate_files: 2, scanned_files: 1, cached_files: 1, unstable_files: 0, unreadable_files: 0, elapsed_ms: 7, workers: 2 },
    }).entries[0]?.sourceRef).toBe("source-1");
    expect(parseExportResult({ exportId: "export-1", displayName: "agent-report-index.html", entryCount: 1 })).toEqual({ exportId: "export-1", displayName: "agent-report-index.html", entryCount: 1 });
  });

  it("rejects authority-bearing labels, references reused as labels, and old path fields", () => {
    expect(() => parseDesktopDefaults({ roots: [{ rootRef: "root-1", displayName: "/logs" }], diagnosticsAvailable: true })).toThrow("path-shaped");
    expect(() => parseRootReferences([{ rootRef: "root-1", displayName: "root-1" }])).toThrow("non-authority");
    expect(() => parseExportResult({ exportId: "export-1", displayName: "C:\\report.html", entryCount: 1 })).toThrow();
    expect(() => parseExportResult({ outputPath: "hidden", entryCount: 1 })).toThrow("forbidden");
  });

  it("keeps local time conversion, worker bounds, and safe discovery progress", () => {
    expect(dateRangeError("2026-08-12T17:00", "2026-08-12T09:00")).not.toBeNull();
    expect(localDateHourToUtc("2026-08-12")).toBe(new Date("2026-08-12T00:00").toISOString().slice(0, 13));
    expect(localExclusiveDateHourToInclusiveUtcHour("2026-08-13")).toBe(new Date(new Date("2026-08-13T00:00").getTime() - 1).toISOString().slice(0, 13));
    expect(localDayDateRange(new Date(2026, 7, 12, 12, 30))).toEqual({
      fromDate: "2026-08-12",
      toDate: "2026-08-13",
    });
    expect(normalizeWorkerCount("64", 4)).toBe(64);
    expect(normalizeWorkerCount("65", 4)).toBe(4);
    const progress = parseDiscoveryProgress({ completed_files: 1, candidate_files: 2, sourceLabel: "root.jsonl", source: "scan" });
    expect(discoveryProgressPresentation(progress)).toMatchObject({ value: "1 / 2", sourceLabel: "root.jsonl" });
  });
});

describe("snapshot and summary contracts", () => {
  it.each([
    "REPORT_CANCELLED",
    "REPORT_CURSOR_CONFLICT",
    "REPORT_DISCOVERY_FAILED",
    "REPORT_EVENT_NOT_FOUND",
    "REPORT_EXPORT_FAILED",
    "REPORT_GENERATION_FAILED",
    "REPORT_INTERNAL_ERROR",
    "REPORT_INVALID_REQUEST",
    "REPORT_NOT_FOUND",
    "REPORT_PRIVACY_FAILED",
    "REPORT_SCOPE_CONFLICT",
    "REPORT_SNAPSHOT_CONFLICT",
    "REPORT_SNAPSHOT_NOT_FOUND",
    "REPORT_WRITE_FAILED",
    "REPORT_PROTOCOL_ERROR",
    "REPORT_UNAVAILABLE",
  ] as const)("accepts the shared report error code %s", (code) => {
    expect(parseReportErrorDto({ code, message: "Safe error.", operationId: null, recoverable: false, currentSourceRevision: null, preflightRequired: false, restartFromFirstPage: false }).code).toBe(code);
  });

  it("accepts complete errors, preflight, snapshot, and summary records", () => {
    expect(parseReportErrorDto({ code: "REPORT_CURSOR_CONFLICT", message: "Restart from the first page.", operationId: "operation-1", recoverable: true, currentSourceRevision: "source-revision-2", preflightRequired: false, restartFromFirstPage: true }).currentSourceRevision).toBe("source-revision-2");
    expect(parseReportErrorDto({ code: "REPORT_PRIVACY_FAILED", message: "Privacy validation failed.", operationId: null, recoverable: false, currentSourceRevision: null, preflightRequired: false, restartFromFirstPage: false }).code).toBe("REPORT_PRIVACY_FAILED");
    expect(parsePreflightReportDto({ preflightToken: "preflight-1", rootThreadId: "thread-1", includeChildren: true, includeCollaborators: false, sourceRevision: "source-revision-1", logCount: 2, totalBytes: 2048, childCount: 1, collaboratorCount: 0, cachedFileCount: 1, changedFileCount: 1, knownEventCount: 12, warnings }).warnings).toEqual(warnings);
    expect(parseSnapshotMetadataDto(snapshot)).toMatchObject({ sourceRevision: "source-revision-1", pricingDigest: "a".repeat(64), formatterDigest: "b".repeat(64), observationTime: "2026-08-12T12:00:00Z", mode: "live" });
    expect(parseReportSummaryDto({ snapshotId: "snapshot-1", revision: "revision-1", title: "Run", goal: null, state: "complete", scopeLabel: "Root and children", observedAt: "2026-08-12T12:00:00Z", live: true, timeRange: { fromTime: "2026-08-12T11:00:00Z", toTime: "2026-08-12T13:00:00Z" }, metricGroups: [{ groupId: "work_items", label: "Work items", metrics: [{ metricId: "events", label: "Events", displayValue: "12", evidence: "measured", description: null }] }], recentActivity: [{ eventId: "event-1", occurredAt: "2026-08-12T12:00:00Z", label: "Completed", evidence: "measured" }], warnings }).metricGroups[0]?.groupId).toBe("work_items");
  });

  it("rejects invalid variants, instants, counts, and unbounded warnings", () => {
    expect(() => parseReportErrorDto({ code: "UNKNOWN", message: "x", operationId: null, recoverable: false, currentSourceRevision: null, preflightRequired: false, restartFromFirstPage: false })).toThrow("unknown variant");
    expect(() => parsePreflightReportDto({ preflightToken: "p", rootThreadId: "t", includeChildren: false, includeCollaborators: false, sourceRevision: "r", logCount: -1, totalBytes: 0, childCount: 0, collaboratorCount: 0, cachedFileCount: 0, changedFileCount: 0, knownEventCount: null, warnings: [] })).toThrow("non-negative integer");
    expect(() => parseSnapshotMetadataDto({ ...snapshot, observationTime: "invalid" })).toThrow("ISO instant");
    expect(() => parsePreflightReportDto({ preflightToken: "p", rootThreadId: "t", includeChildren: false, includeCollaborators: false, sourceRevision: "r", logCount: 0, totalBytes: 0, childCount: 0, collaboratorCount: 0, cachedFileCount: 0, changedFileCount: 0, knownEventCount: null, warnings: ["not structured"] })).toThrow();
  });
});

describe("paged workspace contracts", () => {
  it("accepts a complete agent and turn page at the active binding", () => {
    expect(parseAgentPageDto(page("list_agents", agentFilters, agentSort, [{ agentId: "agent-1", nickname: null, role: "coder", state: "running", startedAt: "2026-08-12T12:00:00Z", lastActivityAt: "2026-08-12T12:10:00Z", turnCount: 1, eventCount: 2 }]), { snapshotId: "snapshot-1", revision: "revision-1", operation: "list_agents", filters: agentFilters, sort: agentSort }).items).toHaveLength(1);
    expect(parseTurnPageDto(page("list_turns", turnFilters, turnSort, [{ turnId: "turn-1", agentId: "agent-1", startedAt: "2026-08-12T12:00:00Z", endedAt: null, state: "running", eventCount: 2, summary: null }]), { snapshotId: "snapshot-1", revision: "revision-1", operation: "list_turns", filters: turnFilters, sort: turnSort }).items[0]?.turnId).toBe("turn-1");
  });

  it("accepts chronological event, sequence, and coordination pages", () => {
    expect(parseEventPageDto(page("list_events", eventFilters, eventSort, [{ eventId: "event-1", occurredAt: "2026-08-12T12:00:00Z", agentId: "agent-1", turnId: "turn-1", kind: "tool", label: "Ran tests", evidence: "measured", sourceRef: "source-1", hasDetail: true }]), { snapshotId: "snapshot-1", revision: "revision-1", operation: "list_events", filters: eventFilters, sort: eventSort }).items[0]?.sourceRef).toBe("source-1");
    expect(parseSequencePageDto({ page: page("query_sequence", sequenceFilters, sequenceSort, [{ sequenceId: "sequence-1", groupId: "group-1", occurredAt: "2026-08-12T12:00:00Z", fromAgentId: "agent-1", fromAgentLabel: "Coder", toAgentId: "agent-2", toAgentLabel: "Reviewer", kind: "message", label: "Review", evidence: "measured", eventId: "event-1", repeatCount: 1, reasoningAvailable: false }]), groups: [{ groupId: "group-1", parentGroupId: null, depth: 0, label: "Root", collapsible: true }] }, { snapshotId: "snapshot-1", revision: "revision-1", operation: "query_sequence", filters: sequenceFilters, sort: sequenceSort }).groups).toHaveLength(1);
    expect(parseCoordinationPageDto(page("query_coordination", coordinationFilters, coordinationSort, [{ coordinationId: "coordination-1", occurredAt: "2026-08-12T12:00:00Z", workItemId: "item-1", delegatedRootId: null, agentId: "agent-1", operation: "claim", label: "Claimed", evidence: "inferred", eventId: "event-1" }]), { snapshotId: "snapshot-1", revision: "revision-1", operation: "query_coordination", filters: coordinationFilters, sort: coordinationSort }).items[0]?.evidence).toBe("inferred");
  });

  it("rejects response binding mismatch, oversized pages, chronology, and hierarchy defects", () => {
    expect(() => parseAgentPageDto(page("list_agents", { ...agentFilters, query: "changed" }, agentSort, []), { snapshotId: "snapshot-1", revision: "revision-1", operation: "list_agents", filters: agentFilters, sort: agentSort })).toThrow("applied metadata");
    expect(() => parseAgentPageDto({ ...page("list_agents", agentFilters, agentSort, []), pageSize: 501 }, { snapshotId: "snapshot-1", revision: "revision-1", operation: "list_agents", filters: agentFilters, sort: agentSort })).toThrow("outside 1 through 500");
    expect(() => parseEventPageDto(page("list_events", eventFilters, eventSort, [
      { eventId: "event-2", occurredAt: "2026-08-12T12:01:00Z", agentId: null, turnId: null, kind: "message", label: "Second", evidence: "measured", sourceRef: null, hasDetail: false },
      { eventId: "event-1", occurredAt: "2026-08-12T12:00:00Z", agentId: null, turnId: null, kind: "message", label: "First", evidence: "measured", sourceRef: null, hasDetail: false },
    ]), { snapshotId: "snapshot-1", revision: "revision-1", operation: "list_events", filters: eventFilters, sort: eventSort })).toThrow("chronological");
    expect(() => parseSequencePageDto({ page: page("query_sequence", sequenceFilters, sequenceSort, []), groups: [{ groupId: "group-1", parentGroupId: "missing", depth: 1, label: "Child", collapsible: true }] }, { snapshotId: "snapshot-1", revision: "revision-1", operation: "query_sequence", filters: sequenceFilters, sort: sequenceSort })).toThrow("hierarchy");
  });
});

describe("heatmap, detail, export, and progress contracts", () => {
  it("accepts bounded heatmap, detail, export, and matching progress results", () => {
    const expectedHeatmap = { snapshotId: "snapshot-1", revision: "revision-1", fromTime: "2026-08-12T12:00:00Z", toTime: "2026-08-12T13:00:00Z", measure: "wall_time" as const, groupBy: "agent" as const, requestedResolutionMinutes: 5 as const, maximumRows: 100 };
    expect(parseHeatmapResultDto({ ...expectedHeatmap, actualResolutionMinutes: 5, omittedRowCount: 0, rowOrder: "activity_descending_id_ascending", totalCellCount: 1, rows: [{ rowId: "agent-1", label: "Coder", scale: { minimum: 0, maximum: 2, colorSemantic: "sequential_nonnegative", basis: "visible_row_maximum" }, cells: [{ startTime: "2026-08-12T12:00:00Z", endTime: "2026-08-12T12:05:00Z", value: 2, count: 1, evidence: "measured", primaryLabel: "2 events", secondaryLabel: null }] }], provenance: ["Recorded events"] }, expectedHeatmap).totalCellCount).toBe(1);
    expect(parseEventDetailDto({ snapshotId: "snapshot-1", revision: "revision-1", eventId: "event-1", occurredAt: "2026-08-12T12:00:00Z", kind: "tool", title: "Test run", evidence: "measured", provenance: ["Event log"], summary: null, disclosures: [{ label: "Output", content: "18 tests passed", redacted: false }], sourceRef: "source-1" }).disclosures[0]?.content).toBe("18 tests passed");
    expect(parseExportSnapshotResultDto({ operationId: "operation-1", snapshotId: "snapshot-1", revision: "revision-1", exportId: "export-1", displayName: "agent-report", mode: "directory", manifestSha256: "c".repeat(64), fileCount: 4, totalByteCount: 2048, warnings, omissions: [] }, { operationId: "operation-1", snapshotId: "snapshot-1", revision: "revision-1", mode: "directory" })).toMatchObject({ exportId: "export-1", totalByteCount: 2048 });
    expect(parseRefreshSnapshotResultDto({ changed: false, snapshot }, "snapshot-1")).toEqual({ changed: false, snapshot });
    expect(parseCloseSnapshotResultDto({ snapshotId: "snapshot-1", closed: true }, "snapshot-1")).toEqual({ snapshotId: "snapshot-1", closed: true });
    expect(parseWorkspaceProgressDto({ protocolVersion: 1, operationId: "operation-1", operation: "export_snapshot", snapshotId: "snapshot-1", phase: "rendering", completed: 2, total: 4, message: "Rendering pages" }, "operation-1", "export_snapshot").completed).toBe(2);
  });

  it("rejects heatmap overflow, export paths, progress mismatch, and disclosure overflow", () => {
    const expected = { snapshotId: "snapshot-1", revision: "revision-1", fromTime: "2026-08-12T12:00:00Z", toTime: "2026-08-12T13:00:00Z", measure: "wall_time" as const, groupBy: "agent" as const, requestedResolutionMinutes: 5 as const, maximumRows: 100 };
    const cells = Array.from({ length: 2_001 }, (_, index) => ({ startTime: `2026-08-12T12:${String(index % 60).padStart(2, "0")}:00Z`, endTime: "2026-08-12T13:00:00Z", value: 1, count: 1, evidence: "measured", primaryLabel: "1", secondaryLabel: null }));
    expect(() => parseHeatmapResultDto({ ...expected, actualResolutionMinutes: 5, omittedRowCount: 0, rowOrder: "activity_descending_id_ascending", totalCellCount: 2_001, rows: [{ rowId: "agent-1", label: "Coder", scale: { minimum: 0, maximum: 1, colorSemantic: "sequential_nonnegative", basis: "visible_row_maximum" }, cells }], provenance: [] }, expected)).toThrow();
    expect(() => parseExportSnapshotResultDto({ operationId: "operation-1", snapshotId: "snapshot-1", revision: "revision-1", exportId: "export-1", displayName: "report", mode: "directory", manifestSha256: null, fileCount: 1, totalByteCount: 1, warnings: [], omissions: [], outputPath: "hidden" }, { operationId: "operation-1", snapshotId: "snapshot-1", revision: "revision-1", mode: "directory" })).toThrow("forbidden");
    expect(() => parseWorkspaceProgressDto({ protocolVersion: 1, operationId: "wrong", operation: "export_snapshot", snapshotId: null, phase: "x", completed: 0, total: null, message: "x" }, "operation-1", "export_snapshot")).toThrow("identity");
    expect(() => parseEventDetailDto({ snapshotId: "snapshot-1", revision: "revision-1", eventId: "event-1", occurredAt: "2026-08-12T12:00:00Z", kind: "tool", title: "Test", evidence: "measured", provenance: [], summary: null, disclosures: [{ label: "Output", content: "x".repeat(16_385), redacted: false }], sourceRef: null })).toThrow("client limit");
    expect(() => parseExportSnapshotResultDto({ operationId: "operation-1", snapshotId: "snapshot-1", revision: "revision-1", exportId: "export-1", displayName: "report", mode: "directory", manifestSha256: null, fileCount: 1, byteCount: 1, warnings: [], omissions: [] }, { operationId: "operation-1", snapshotId: "snapshot-1", revision: "revision-1", mode: "directory" })).toThrow();
    expect(() => parseRefreshSnapshotResultDto({ changed: false, snapshot, revision: "unexpected" }, "snapshot-1")).toThrow("unexpected");
    expect(() => parseCloseSnapshotResultDto({ snapshotId: "snapshot-1", closed: true, revision: "unexpected" }, "snapshot-1")).toThrow("unexpected");
  });

  it("accepts bounded legacy worker progress only as adjacent catalog progress", () => {
    expect(parseReportGenerationProgress({ completed: 30, total: 100, itemCompleted: 1, itemTotal: 10, label: "Static adapter", detail: "Working", worker: "1" })).toMatchObject({ itemCompleted: 1, itemTotal: 10 });
  });
});

describe("recursive privacy enforcement", () => {
  it.each([
    { sourcePath: "redacted" },
    { nested: { cachePath: "redacted" } },
    { nested: [{ filesystemPath: "redacted" }] },
    { rawRecord: "redacted" },
    { rawRollout: "redacted" },
    { arbitraryPath: "redacted" },
  ])("rejects forbidden keys without exposing values", (extra) => {
    expect(() => parseReportErrorDto({ code: "REPORT_PROTOCOL_ERROR", message: "Safe", operationId: null, recoverable: false, currentSourceRevision: null, preflightRequired: false, restartFromFirstPage: false, ...extra })).toThrow(/forbidden/);
  });

  it.each(["/private/log", "\\\\server\\share", "C:\\private\\log", "file:///private/log"])("rejects path-shaped values: %s", (message) => {
    expect(() => parseReportErrorDto({ code: "REPORT_PROTOCOL_ERROR", message, operationId: null, recoverable: false, currentSourceRevision: null, preflightRequired: false, restartFromFirstPage: false })).toThrow("path-shaped");
  });
});
