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
  localDateTimeToUtc,
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
    expect(dateRangeError("2026-08-12", "17:30", "2026-08-12", "09:15")).not.toBeNull();
    expect(dateRangeError("2026-08-12", "00:30", "2026-08-12", "01:00")).toBeNull();
    expect(localDateTimeToUtc("2026-08-12", "00:30")).toBe(new Date("2026-08-12T00:30").toISOString());
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

  it("accepts reordered turn filter and sort object keys from native serialization", () => {
    const reorderedFilters = { state: null, agentId: null };
    const reorderedSort = { tieBreakDirection: "ascending", tieBreakKey: "turn_id", direction: "ascending", key: "started_at" };
    const result = parseTurnPageDto(
      page("list_turns", reorderedFilters, reorderedSort, [{ turnId: "turn-1", agentId: "agent-1", startedAt: "2026-08-12T12:00:00Z", endedAt: null, state: "running", eventCount: 2, summary: null }]),
      { snapshotId: "snapshot-1", revision: "revision-1", operation: "list_turns", filters: turnFilters, sort: turnSort },
    );
    expect(result.appliedFilters).toBe(turnFilters);
    expect(result.appliedSort).toBe(turnSort);
  });

  it("accepts reordered event metadata while retaining exact array order and value types", () => {
    const reorderedFilters = { toTime: null, fromTime: null, kind: null, turnId: null, agentId: null };
    const reorderedSort = { tieBreakDirection: "ascending", tieBreakKey: "event_id", direction: "ascending", key: "occurred_at" };
    expect(parseEventPageDto(
      page("list_events", reorderedFilters, reorderedSort, []),
      { snapshotId: "snapshot-1", revision: "revision-1", operation: "list_events", filters: eventFilters, sort: eventSort },
    ).items).toEqual([]);

    const orderedSequenceFilters: SequenceFiltersDto = { ...sequenceFilters, eventKinds: ["message", "tool"] };
    expect(() => parseSequencePageDto(
      { page: page("query_sequence", { ...orderedSequenceFilters, eventKinds: ["tool", "message"] }, sequenceSort, []), groups: [] },
      { snapshotId: "snapshot-1", revision: "revision-1", operation: "query_sequence", filters: orderedSequenceFilters, sort: sequenceSort },
    )).toThrow("applied metadata");
    expect(() => parseTurnPageDto(
      page("list_turns", { state: null, agentId: "null" }, turnSort, []),
      { snapshotId: "snapshot-1", revision: "revision-1", operation: "list_turns", filters: turnFilters, sort: turnSort },
    )).toThrow("applied metadata");
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
  const matrixRequest = {
    operationId: "operation-1",
    snapshotId: "snapshot-1",
    queryKind: "matrix" as const,
    fromTime: "2026-08-12T12:00:00Z",
    toTime: "2026-08-12T13:00:00Z",
    mode: "tokens" as const,
    requestedResolutionMinutes: 5 as const,
    maximumRows: 100,
  };
  const matrixResult = {
    snapshotId: "snapshot-1",
    revisionId: "revision-1",
    queryKind: "matrix" as const,
    mode: "tokens" as const,
    fromTime: "2026-08-12T12:00:00Z",
    toTime: "2026-08-12T13:00:00Z",
    requestedResolutionMinutes: 5,
    actualResolutionMinutes: 5,
    maximumRows: 100,
    omittedRowCount: 7,
    rowOrder: "token_contract",
    totalCellCount: 2,
    rows: [
      {
        rowId: "token:uncached-input",
        rowKey: "uncached_input_tokens",
        rowOrderIndex: 0,
        rowKind: "token_measure",
        label: "Uncached input",
        scale: { availability: "available", minimum: 0, maximum: 2_000, basis: "visible_row_maximum" },
        cells: [
          { startTime: "2026-08-12T12:00:00Z", endTime: "2026-08-12T12:05:00Z", value: 0, formattedValue: "0", valueState: "derived", applicableZero: true, contributingEvidenceCount: 1, normalizedIntensity: 0, supportingText: null },
          { startTime: "2026-08-12T12:05:00Z", endTime: "2026-08-12T12:10:00Z", value: 1_200, formattedValue: "Partial · 1.2K", valueState: "partial", applicableZero: false, contributingEvidenceCount: 2, normalizedIntensity: 0.6, supportingText: null },
        ],
      },
    ],
    provenance: ["Recorded usage"],
  };
  const evidenceRequest = {
    operationId: "operation-2",
    snapshotId: "snapshot-1",
    queryKind: "cell_evidence" as const,
    mode: "tokens" as const,
    rowId: "token:context-maximum",
    periodStartTime: "2026-08-12T12:00:00Z",
    periodEndTime: "2026-08-12T12:05:00Z",
  };
  const evidenceResult = {
    snapshotId: "snapshot-1",
    revisionId: "revision-1",
    queryKind: "cell_evidence" as const,
    mode: "tokens" as const,
    rowId: "token:context-maximum",
    rowKey: "context_maximum",
    rowOrderIndex: 6,
    rowLabel: "Context size (max)",
    periodStartTime: "2026-08-12T12:00:00Z",
    periodEndTime: "2026-08-12T12:05:00Z",
    value: null,
    formattedValue: "N/A — capacity unavailable",
    valueState: "unavailable",
    applicableZero: false,
    evidenceItems: [
      { eventId: "event-1", occurredAt: "2026-08-12T12:01:00Z", value: 1_200, formattedValue: "1.2K tokens", durationMs: null, label: "main · gpt-5.6-sol · high", preview: "Recorded token use", evidenceMethod: "measured", valueState: "measured", hasDetail: true },
      { eventId: null, occurredAt: "2026-08-12T12:02:00Z", value: null, formattedValue: "Unavailable", durationMs: null, label: "Capacity evidence", preview: null, evidenceMethod: "unavailable", valueState: "unavailable", hasDetail: false },
    ],
    omittedEvidenceCount: 3,
    provenance: ["Recorded responses"],
  };
  const tokenRowKeys = ["uncached_input_tokens", "cached_input_tokens", "reasoning_tokens", "output_tokens", "tool_calls", "context_average", "context_maximum", "cost"] as const;
  const emptyTokenRows = () => tokenRowKeys.map((rowKey, rowOrderIndex) => ({
    rowId: `row-${rowOrderIndex}`,
    rowKey,
    rowOrderIndex,
    rowKind: rowKey === "cost" ? "cost" as const : "token_measure" as const,
    label: `Row ${rowOrderIndex}`,
    scale: rowKey === "context_average" || rowKey === "context_maximum"
      ? { availability: "available" as const, minimum: 0, maximum: 1, basis: "context_window_capacity" as const }
      : { availability: "available" as const, minimum: 0, maximum: 1, basis: "visible_row_maximum" as const },
    cells: [],
  }));

  it("accepts exact matrix and cell-evidence variants plus adjacent result contracts", () => {
    const parsedMatrix = parseHeatmapResultDto(matrixResult, { ...matrixRequest, revisionId: "revision-1" });
    expect(parsedMatrix).toMatchObject({ queryKind: "matrix", revisionId: "revision-1", rowOrder: "token_contract", totalCellCount: 2 });
    if (parsedMatrix.queryKind !== "matrix") throw new Error("Expected a matrix result");
    expect(parsedMatrix.rows[0]?.cells[1]).toMatchObject({ valueState: "partial", applicableZero: false, normalizedIntensity: 0.6 });

    const parsedEvidence = parseHeatmapResultDto(evidenceResult, { ...evidenceRequest, revisionId: "revision-1", rowKey: "context_maximum", rowOrderIndex: 6 });
    expect(parsedEvidence).toMatchObject({ queryKind: "cell_evidence", revisionId: "revision-1", value: null, omittedEvidenceCount: 3 });
    if (parsedEvidence.queryKind !== "cell_evidence") throw new Error("Expected a cell-evidence result");
    expect(parsedEvidence.evidenceItems.map((item) => item.evidenceMethod)).toEqual(["measured", "unavailable"]);

    expect(parseEventDetailDto({ snapshotId: "snapshot-1", revision: "revision-1", eventId: "event-1", occurredAt: "2026-08-12T12:00:00Z", kind: "tool", title: "Test run", evidence: "measured", provenance: ["Event log"], summary: null, disclosures: [{ label: "Output", content: "18 tests passed", redacted: false }], sourceRef: "source-1" }).disclosures[0]?.content).toBe("18 tests passed");
    expect(parseExportSnapshotResultDto({ operationId: "operation-1", snapshotId: "snapshot-1", revision: "revision-1", exportId: "export-1", displayName: "agent-report", mode: "directory", manifestSha256: "c".repeat(64), fileCount: 4, totalByteCount: 2048, warnings, omissions: [] }, { operationId: "operation-1", snapshotId: "snapshot-1", revision: "revision-1", mode: "directory" })).toMatchObject({ exportId: "export-1", totalByteCount: 2048 });
    expect(parseRefreshSnapshotResultDto({ changed: false, snapshot }, "snapshot-1")).toEqual({ changed: false, snapshot });
    expect(parseCloseSnapshotResultDto({ snapshotId: "snapshot-1", closed: true }, "snapshot-1")).toEqual({ snapshotId: "snapshot-1", closed: true });
    expect(parseWorkspaceProgressDto({ protocolVersion: 1, operationId: "operation-1", operation: "export_snapshot", snapshotId: "snapshot-1", phase: "rendering", completed: 2, total: 4, message: "Rendering pages" }, "operation-1", "export_snapshot").completed).toBe(2);
  });

  it("rejects mixed variants, binding errors, invalid scales, and unavailable-value lies", () => {
    expect(() => parseHeatmapResultDto({ ...matrixResult, evidenceItems: [] }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("unexpected");
    expect(() => parseHeatmapResultDto({ ...matrixResult, revisionId: "revision-2" }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("active request");
    expect(() => parseHeatmapResultDto({ ...matrixResult, rowOrder: "runtime_state_contract" }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("rowOrder");
    expect(() => parseHeatmapResultDto({ ...matrixResult, rows: [{ ...matrixResult.rows[0], scale: { availability: "unavailable", reason: "context_capacity_unavailable", minimum: 0 } }] }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("unexpected");
    expect(() => parseHeatmapResultDto({ ...matrixResult, rows: [{ ...matrixResult.rows[0], cells: [{ ...matrixResult.rows[0]!.cells[0]!, value: null, valueState: "unavailable", applicableZero: true }] }], totalCellCount: 1 }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("applicableZero");
    expect(() => parseHeatmapResultDto({ ...matrixResult, rows: [{ ...matrixResult.rows[0], cells: [{ ...matrixResult.rows[0]!.cells[0]!, normalizedIntensity: null }] }], totalCellCount: 1 }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("required for a usable value");
    const contextRow = { ...matrixResult.rows[0], rowId: "token:context-maximum", rowKey: "context_maximum", rowOrderIndex: 0, label: "Context size (max)", scale: { availability: "unavailable", reason: "context_capacity_unavailable" } as const };
    expect(() => parseHeatmapResultDto({ ...matrixResult, rows: [{ ...contextRow, cells: [{ ...matrixResult.rows[0]!.cells[0]!, normalizedIntensity: 0.1 }] }], omittedRowCount: 7, totalCellCount: 1 }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("normalizedIntensity");
    expect(() => parseHeatmapResultDto({ ...matrixResult, rows: [{ ...contextRow, cells: [{ ...matrixResult.rows[0]!.cells[0]!, value: null, formattedValue: "50%", valueState: "unavailable", applicableZero: false, normalizedIntensity: null }] }], omittedRowCount: 7, totalCellCount: 1 }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("percentage");
    expect(() => parseHeatmapResultDto({ ...matrixResult, rows: [{ ...contextRow, cells: [{ ...matrixResult.rows[0]!.cells[0]!, value: null, formattedValue: "Unavailable", valueState: "unavailable", applicableZero: false, normalizedIntensity: null, supportingText: "50%" }] }], omittedRowCount: 7, totalCellCount: 1 }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("percentage");
    const evidenceBinding = { ...evidenceRequest, revisionId: "revision-1", rowKey: "context_maximum", rowOrderIndex: 6 } as const;
    expect(() => parseHeatmapResultDto({ ...evidenceResult, rowKey: "context_average" }, evidenceBinding)).toThrow("rowKey");
    expect(() => parseHeatmapResultDto({ ...evidenceResult, rowOrderIndex: 5 }, evidenceBinding)).toThrow("rowOrderIndex");
    expect(() => parseHeatmapResultDto({ ...evidenceResult, evidenceItems: [{ ...evidenceResult.evidenceItems[1], hasDetail: true }] }, evidenceBinding)).toThrow("eventId");
    expect(() => parseHeatmapResultDto({ ...evidenceResult, evidenceItems: [{ ...evidenceResult.evidenceItems[0], durationMs: 1.5 }] }, evidenceBinding)).toThrow("non-negative integer");
    expect(() => parseHeatmapResultDto({ ...evidenceResult, value: 0, formattedValue: "0", valueState: "derived", applicableZero: false }, evidenceBinding)).toThrow("complete zero");
    expect(() => parseHeatmapResultDto({ ...evidenceResult, evidenceItems: [{ ...evidenceResult.evidenceItems[1], value: 1 }] }, evidenceBinding)).toThrow("null when unavailable");
    expect(() => parseHeatmapResultDto({ ...evidenceResult, evidenceItems: [...evidenceResult.evidenceItems].reverse() }, evidenceBinding)).toThrow("chronological");
  });

  it("correlates scale basis to semantic row keys without reading labels or opaque IDs", () => {
    const rows = emptyTokenRows();
    const base = { ...matrixResult, rows, omittedRowCount: 0, totalCellCount: 0 };
    expect(parseHeatmapResultDto(base, { ...matrixRequest, revisionId: "revision-1" }).queryKind).toBe("matrix");
    expect(() => parseHeatmapResultDto({ ...base, rows: rows.map((row, index) => index === 0 ? { ...row, scale: { availability: "available", minimum: 0, maximum: 1, basis: "context_window_capacity" } } : row) }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("scale basis");
    expect(() => parseHeatmapResultDto({ ...base, rows: rows.map((row, index) => index === 5 ? { ...row, scale: { availability: "available", minimum: 0, maximum: 1, basis: "visible_row_maximum" } } : row) }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("scale basis");
  });

  it("validates service order from rowKey and rowOrderIndex without sorting", () => {
    const tokenRows = emptyTokenRows();
    const tokenBase = { ...matrixResult, rows: tokenRows, omittedRowCount: 0, totalCellCount: 0 };
    expect(() => parseHeatmapResultDto({ ...tokenBase, rows: tokenRows.map((row, index) => index === 0 ? { ...row, rowKey: "cached_input_tokens" } : index === 1 ? { ...row, rowKey: "uncached_input_tokens" } : row) }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("exact contract order");
    expect(() => parseHeatmapResultDto({ ...tokenBase, rows: tokenRows.map((row, index) => index === 1 ? { ...row, rowOrderIndex: 0 } : row) }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("contiguous");
    expect(() => parseHeatmapResultDto({ ...tokenBase, rows: tokenRows.map((row, index) => index === 1 ? { ...row, rowId: tokenRows[0]!.rowId } : row) }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("duplicate row identity");

    const wallRequest = { ...matrixRequest, mode: "wall_time" as const };
    const wallRows = ["model_inference", "tool_execution", "runtime:alpha", "runtime:zeta"].map((rowKey, rowOrderIndex) => ({ ...tokenRows[0]!, rowId: `wall-${rowOrderIndex}`, rowKey, rowOrderIndex, rowKind: "runtime_state" as const }));
    const wallBase = { ...matrixResult, mode: "wall_time", rowOrder: "runtime_state_contract", rows: wallRows, omittedRowCount: 0, totalCellCount: 0 };
    expect(parseHeatmapResultDto(wallBase, { ...wallRequest, revisionId: "revision-1" }).queryKind).toBe("matrix");
    const customStateRows = [{ ...wallRows[0]!, rowKey: "runtime:custom state", rowOrderIndex: 0 }];
    const customStateBase = { ...wallBase, rows: customStateRows };
    expect(parseHeatmapResultDto(customStateBase, { ...wallRequest, revisionId: "revision-1" }).queryKind).toBe("matrix");
    for (const rowKey of ["runtime:custom\u0000state", "runtime:custom\u007fstate"]) {
      expect(() => parseHeatmapResultDto({ ...customStateBase, rows: [{ ...customStateRows[0]!, rowKey }] }, { ...wallRequest, revisionId: "revision-1" })).toThrow("lowercase runtime identity");
    }
    expect(() => parseHeatmapResultDto({ ...wallBase, rows: [wallRows[1], wallRows[0], wallRows[2], wallRows[3]].map((row, rowOrderIndex) => ({ ...row!, rowOrderIndex })) }, { ...wallRequest, revisionId: "revision-1" })).toThrow("runtime rows");
    expect(() => parseHeatmapResultDto({ ...wallBase, rows: [wallRows[0], wallRows[1], wallRows[3], wallRows[2]].map((row, rowOrderIndex) => ({ ...row!, rowOrderIndex })) }, { ...wallRequest, revisionId: "revision-1" })).toThrow("ascending");

    const modelRequest = { ...matrixRequest, mode: "models" as const };
    const modelRows = ["model:0123456789abcdef01234567", "model:89abcdef0123456701234567", "cost"].map((rowKey, rowOrderIndex) => ({ ...tokenRows[0]!, rowId: `model-${rowOrderIndex}`, rowKey, rowOrderIndex, rowKind: rowKey === "cost" ? "cost" as const : "model" as const }));
    const modelBase = { ...matrixResult, mode: "models", rowOrder: "model_first_occurrence_then_cost", rows: modelRows, omittedRowCount: 0, totalCellCount: 0 };
    expect(parseHeatmapResultDto(modelBase, { ...modelRequest, revisionId: "revision-1" }).queryKind).toBe("matrix");
    expect(() => parseHeatmapResultDto({ ...modelBase, rows: [modelRows[0], modelRows[2], modelRows[1]].map((row, rowOrderIndex) => ({ ...row!, rowOrderIndex })) }, { ...modelRequest, revisionId: "revision-1" })).toThrow("Cost row");
  });

  it("enforces escaped-content UTF-8 byte limits and the transport record bound", () => {
    const escaped = (bytes: number) => "\"".repeat(bytes / 2);
    const evidenceBinding = { ...evidenceRequest, revisionId: "revision-1", rowKey: "context_maximum", rowOrderIndex: 6 } as const;
    const boundedMatrix = {
      ...matrixResult,
      rows: [{
        ...matrixResult.rows[0],
        label: escaped(256),
        cells: [{ ...matrixResult.rows[0]!.cells[0]!, formattedValue: escaped(64), supportingText: escaped(80) }],
      }],
      totalCellCount: 1,
      provenance: Array.from({ length: 32 }, () => escaped(256)),
    };
    expect(parseHeatmapResultDto(boundedMatrix, { ...matrixRequest, revisionId: "revision-1" }).queryKind).toBe("matrix");
    expect(() => parseHeatmapResultDto({ ...boundedMatrix, rows: [{ ...boundedMatrix.rows[0]!, label: `${escaped(256)}a` }] }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("256-byte");
    expect(() => parseHeatmapResultDto({ ...boundedMatrix, rows: [{ ...boundedMatrix.rows[0]!, cells: [{ ...boundedMatrix.rows[0]!.cells[0]!, formattedValue: `${escaped(64)}a` }] }] }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("64-byte");
    expect(() => parseHeatmapResultDto({ ...boundedMatrix, rows: [{ ...boundedMatrix.rows[0]!, cells: [{ ...boundedMatrix.rows[0]!.cells[0]!, supportingText: `${escaped(80)}a` }] }] }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("80-byte");
    expect(() => parseHeatmapResultDto({ ...boundedMatrix, provenance: [...boundedMatrix.provenance, "extra"] }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("32-item");
    expect(() => parseHeatmapResultDto({ ...boundedMatrix, provenance: [`${escaped(256)}a`] }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("256-byte");

    const boundedEvidence = {
      ...evidenceResult,
      rowLabel: escaped(256),
      formattedValue: escaped(64),
      evidenceItems: [{ ...evidenceResult.evidenceItems[0]!, label: escaped(256), formattedValue: escaped(64), preview: escaped(4_096) }],
      provenance: Array.from({ length: 32 }, () => escaped(256)),
    };
    expect(parseHeatmapResultDto(boundedEvidence, evidenceBinding).queryKind).toBe("cell_evidence");
    expect(() => parseHeatmapResultDto({ ...boundedEvidence, rowLabel: `${escaped(256)}a` }, evidenceBinding)).toThrow("256-byte");
    expect(() => parseHeatmapResultDto({ ...boundedEvidence, formattedValue: `${escaped(64)}a` }, evidenceBinding)).toThrow("64-byte");
    expect(() => parseHeatmapResultDto({ ...boundedEvidence, evidenceItems: [{ ...boundedEvidence.evidenceItems[0]!, label: `${escaped(256)}a` }] }, evidenceBinding)).toThrow("256-byte");
    expect(() => parseHeatmapResultDto({ ...boundedEvidence, evidenceItems: [{ ...boundedEvidence.evidenceItems[0]!, formattedValue: `${escaped(64)}a` }] }, evidenceBinding)).toThrow("64-byte");
    expect(() => parseHeatmapResultDto({ ...boundedEvidence, evidenceItems: [{ ...boundedEvidence.evidenceItems[0]!, preview: `${escaped(4_096)}a` }] }, evidenceBinding)).toThrow("4096-byte");
    expect(() => parseHeatmapResultDto({ ...matrixResult, oversized: "x".repeat(1_048_576) }, { ...matrixRequest, revisionId: "revision-1" })).toThrow("transport record bound");
  });

  it("accepts exactly 2,000 matrix cells and 100 evidence items, then rejects one more", () => {
    const rangeStart = Date.parse("2026-08-01T00:00:00Z");
    const boundedCells = Array.from({ length: 2_001 }, (_, index) => ({
      startTime: new Date(rangeStart + index * 60_000).toISOString(),
      endTime: new Date(rangeStart + (index + 1) * 60_000).toISOString(),
      value: 1,
      formattedValue: "1",
      valueState: "measured",
      applicableZero: false,
      contributingEvidenceCount: 1,
      normalizedIntensity: 1,
      supportingText: null,
    }));
    const largeRequest = { ...matrixRequest, fromTime: boundedCells[0]?.startTime ?? "", toTime: boundedCells[2_000]?.endTime ?? "", requestedResolutionMinutes: 1 as const, maximumRows: 1 };
    const largeResult = { ...matrixResult, fromTime: largeRequest.fromTime, toTime: largeRequest.toTime, requestedResolutionMinutes: 1, actualResolutionMinutes: 1, maximumRows: 1, totalCellCount: 2_000, rows: [{ ...matrixResult.rows[0], cells: boundedCells.slice(0, 2_000) }] };
    expect(parseHeatmapResultDto(largeResult, { ...largeRequest, revisionId: "revision-1" }).queryKind).toBe("matrix");
    expect(() => parseHeatmapResultDto({ ...largeResult, totalCellCount: 2_001, rows: [{ ...largeResult.rows[0], cells: boundedCells }] }, { ...largeRequest, revisionId: "revision-1" })).toThrow("2,000");

    const evidenceItems = Array.from({ length: 101 }, (_, index) => ({ ...evidenceResult.evidenceItems[0], eventId: `event-${index}`, occurredAt: new Date(Date.parse(evidenceRequest.periodStartTime) + index * 1_000).toISOString() }));
    const evidenceBinding = { ...evidenceRequest, revisionId: "revision-1", rowKey: "context_maximum", rowOrderIndex: 6 } as const;
    expect(parseHeatmapResultDto({ ...evidenceResult, evidenceItems: evidenceItems.slice(0, 100) }, evidenceBinding).queryKind).toBe("cell_evidence");
    expect(() => parseHeatmapResultDto({ ...evidenceResult, evidenceItems }, evidenceBinding)).toThrow("100");
  });

  it("rejects export paths, progress mismatch, and disclosure overflow", () => {
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
