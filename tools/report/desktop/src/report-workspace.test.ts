// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify the Dynamic Workspace controller and its pure presentation rules.
// Design: docs/design/components/CD-005-agent-report-dynamic-workspace.md

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_OVERSCAN_ROWS,
  DEFAULT_PAGE_SIZE,
  DEFAULT_ROW_HEIGHT_PX,
  MAX_CURSOR_HISTORY,
  MAX_HEATMAP_ROWS,
  MAX_PAGE_SIZE,
  MAX_HEATMAP_CELLS,
  MAX_HEATMAP_EVIDENCE_ITEMS,
  HEATMAP_MODES,
  SURFACE_DEFINITIONS,
  WORKSPACE_COMMANDS,
  computeVirtualWindow,
  describeBoundaryError,
  describeExportResult,
  formatLocalInstant,
  heatmapCellAccessibleName,
  heatmapCellPresentation,
  heatmapEvidenceMatchesSelection,
  heatmapInteractionForMatrixRequest,
  heatmapResolutionLabel,
  moveHeatmapGridFocus,
  nextHeatmapResolution,
  newOperationId,
  reportErrorRecovery,
  scopeSelectionForEditing,
  snapshotTitleAsOf,
} from "./report-workspace";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReportWorkspaceController", () => {
  it("publishes the accepted bounded defaults and native command names", () => {
    expect({
      DEFAULT_PAGE_SIZE,
      MAX_PAGE_SIZE,
      MAX_CURSOR_HISTORY,
      MAX_HEATMAP_CELLS,
      MAX_HEATMAP_ROWS,
      MAX_HEATMAP_EVIDENCE_ITEMS,
      DEFAULT_ROW_HEIGHT_PX,
      DEFAULT_OVERSCAN_ROWS,
    }).toEqual({
      DEFAULT_PAGE_SIZE: 100,
      MAX_PAGE_SIZE: 500,
      MAX_CURSOR_HISTORY: 100,
      MAX_HEATMAP_CELLS: 2_000,
      MAX_HEATMAP_ROWS: 200,
      MAX_HEATMAP_EVIDENCE_ITEMS: 100,
      DEFAULT_ROW_HEIGHT_PX: 44,
      DEFAULT_OVERSCAN_ROWS: 8,
    });
    expect(WORKSPACE_COMMANDS).toEqual({
      preflightReport: "preflight_report",
      openSnapshot: "open_snapshot",
      getSummary: "get_summary",
      listAgents: "list_agents",
      listTurns: "list_turns",
      listEvents: "list_events",
      querySnapshotTimeRange: "query_snapshot_time_range",
      querySequence: "query_sequence",
      queryCoordination: "query_coordination",
      getEventDetails: "get_event_details",
      refreshSnapshot: "refresh_snapshot",
      exportSnapshot: "export_snapshot",
      closeSnapshot: "close_snapshot",
      cancelOperation: "cancel_report_operation",
      openSourceLocation: "open_source_location",
      openDiagnosticLog: "open_diagnostic_log",
      reopenExport: "reopen_export",
    });
  });

  it("creates lowercase cryptographic 96-bit operation identities", () => {
    const getRandomValues = vi.fn((values: Uint8Array) => {
      values.set([0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef, 0x10, 0x32, 0x54, 0x76]);
      return values;
    });
    vi.stubGlobal("crypto", { getRandomValues });

    expect(newOperationId()).toBe("op_0123456789abcdef10325476");
    expect(getRandomValues).toHaveBeenCalledOnce();
    expect(getRandomValues.mock.calls[0]?.[0]).toHaveLength(12);
  });

  it("does not return the reserved all-zero operation identity", () => {
    let call = 0;
    vi.stubGlobal("crypto", {
      getRandomValues(values: Uint8Array) {
        if (call++ > 0) values[11] = 1;
        return values;
      },
    });

    expect(newOperationId()).toBe("op_000000000000000000000001");
  });

  it("binds every stable surface to an accessible definition", () => {
    expect(Object.keys(SURFACE_DEFINITIONS)).toEqual([
      "summary",
      "coordination",
      "heatmap",
      "timeline",
      "sequence",
      "agents",
      "turns",
      "tools",
      "model",
      "context",
      "inference",
      "runtime-waits",
      "work-items-claims",
      "detail",
      "provenance",
      "diagnostics",
    ]);
    for (const [surface, definition] of Object.entries(SURFACE_DEFINITIONS)) {
      expect(definition.label, surface).not.toBe("");
      expect(definition.emptyMessage, surface).not.toBe("");
      expect(definition.headingId, surface).toBe(`report-view-heading-${surface}`);
    }
    expect(SURFACE_DEFINITIONS.summary.operation).toBe("get_summary");
    expect(SURFACE_DEFINITIONS.heatmap.operation).toBe("query_snapshot_time_range");
    expect(SURFACE_DEFINITIONS.timeline.operation).toBe("list_events");
    expect(SURFACE_DEFINITIONS.tools.operation).toBe("list_events");
    expect(SURFACE_DEFINITIONS.detail.operation).toBe("get_event_details");
    expect(SURFACE_DEFINITIONS.diagnostics.operation).toBeNull();
  });

  it("preserves the selected run and relationship choices when scope editing resumes", () => {
    const selection = scopeSelectionForEditing({
      rootThreadId: "thread-1",
      title: "Investigate report",
      includeChildren: true,
      includeCollaborators: false,
    });
    expect(selection).toEqual({
      rootThreadId: "thread-1",
      title: "Investigate report",
      includeChildren: true,
      includeCollaborators: false,
    });
    expect(Object.isFrozen(selection)).toBe(true);
  });
});

describe("cursor pagination and virtualization", () => {
  it("returns an empty window for an empty page", () => {
    expect(
      computeVirtualWindow({
        itemCount: 0,
        rowHeightPx: 44,
        scrollTopPx: 0,
        viewportHeightPx: 440,
        overscanRows: 8,
      }),
    ).toEqual({
      startIndex: 0,
      endIndexExclusive: 0,
      offsetTopPx: 0,
      totalHeightPx: 0,
    });
  });

  it("overscans and clamps first, middle, and final viewports", () => {
    expect(
      computeVirtualWindow({
        itemCount: 100,
        rowHeightPx: 10,
        scrollTopPx: 0,
        viewportHeightPx: 30,
        overscanRows: 2,
      }),
    ).toEqual({ startIndex: 0, endIndexExclusive: 5, offsetTopPx: 0, totalHeightPx: 1_000 });
    expect(
      computeVirtualWindow({
        itemCount: 100,
        rowHeightPx: 10,
        scrollTopPx: 500,
        viewportHeightPx: 30,
        overscanRows: 2,
      }),
    ).toEqual({
      startIndex: 48,
      endIndexExclusive: 55,
      offsetTopPx: 480,
      totalHeightPx: 1_000,
    });
    expect(
      computeVirtualWindow({
        itemCount: 100,
        rowHeightPx: 10,
        scrollTopPx: 990,
        viewportHeightPx: 30,
        overscanRows: 2,
      }),
    ).toEqual({
      startIndex: 97,
      endIndexExclusive: 100,
      offsetTopPx: 970,
      totalHeightPx: 1_000,
    });
  });

  it("normalizes unsafe inputs and never exceeds one maximum page", () => {
    expect(
      computeVirtualWindow({
        itemCount: 999,
        rowHeightPx: Number.NaN,
        scrollTopPx: Number.NEGATIVE_INFINITY,
        viewportHeightPx: Number.POSITIVE_INFINITY,
        overscanRows: -3,
      }),
    ).toEqual({
      startIndex: 0,
      endIndexExclusive: 0,
      offsetTopPx: 0,
      totalHeightPx: MAX_PAGE_SIZE * DEFAULT_ROW_HEIGHT_PX,
    });
  });
});

describe("heatmap bounds", () => {
  it("labels service coarsening without claiming client reaggregation", () => {
    expect(heatmapResolutionLabel(5, 5)).toBe("");
    expect(heatmapResolutionLabel(5, 17)).toBe(
      "Showing 17-minute periods; requested 5-minute periods.",
    );
    expect(() => heatmapResolutionLabel(0, 5)).toThrow("positive finite");
    expect(() => heatmapResolutionLabel(5, Number.NaN)).toThrow("positive finite");
  });

  it("zooms only through the accepted requested resolutions", () => {
    expect(nextHeatmapResolution(15, "in")).toBe(5);
    expect(nextHeatmapResolution(15, "out")).toBe(30);
    expect(nextHeatmapResolution(1, "in")).toBe(1);
    expect(nextHeatmapResolution(60, "out")).toBe(60);
  });

  const completeCell = {
    startTime: "2026-08-12T12:00:00Z",
    endTime: "2026-08-12T12:05:00Z",
    value: 0,
    formattedValue: "0",
    valueState: "derived" as const,
    applicableZero: true,
    contributingEvidenceCount: 1,
    normalizedIntensity: 0,
    supportingText: null,
  };

  it("exposes exactly three modes and exact evidence-state wording", () => {
    expect(HEATMAP_MODES).toEqual([
      { value: "wall_time", label: "Wall time" },
      { value: "tokens", label: "Tokens" },
      { value: "models", label: "Models" },
    ]);
    const scale = { availability: "available" as const, minimum: 0, maximum: 10, basis: "visible_row_maximum" as const };
    expect(heatmapCellPresentation(scale, completeCell)).toEqual({ tone: "derived", intensity: 0, visibleValue: "0", explanation: null });
    expect(heatmapCellPresentation(scale, { ...completeCell, value: 4, formattedValue: "Partial · 4", valueState: "partial", applicableZero: false, normalizedIntensity: 0.4 })).toEqual({
      tone: "partial",
      intensity: 0.4,
      visibleValue: "Partial · 4",
      explanation: "Some data for this period is unavailable. The value shown is the available subtotal.",
    });
    expect(heatmapCellPresentation(scale, { ...completeCell, value: null, formattedValue: "Unavailable", valueState: "unavailable", applicableZero: false, normalizedIntensity: null })).toEqual({
      tone: "unavailable",
      intensity: null,
      visibleValue: "Unavailable",
      explanation: "No usable data is available for this period.",
    });
  });

  it("uses true unavailable-capacity semantics without intensity, percentage, or fallback", () => {
    const unavailableScale = { availability: "unavailable" as const, reason: "context_capacity_unavailable" as const };
    const cell = { ...completeCell, value: null, formattedValue: "N/A", valueState: "unavailable" as const, applicableZero: false, normalizedIntensity: null, supportingText: "1.2K observed tokens" };
    expect(heatmapCellPresentation(unavailableScale, cell)).toEqual({
      tone: "capacity-unavailable",
      intensity: null,
      visibleValue: "N/A — capacity unavailable",
      explanation: "Capacity is unavailable. No percentage or color comparison is available.",
    });
    const accessibleName = heatmapCellAccessibleName("tokens", "Context size (max)", cell, unavailableScale, true);
    expect(accessibleName).toContain("N/A — capacity unavailable");
    expect(accessibleName).toContain("intensity N/A");
    expect(accessibleName).not.toContain("%");
    expect(accessibleName).not.toContain("visible row maximum");
  });

  it("resolves bounded roving-grid coordinates without a DOM harness", () => {
    expect(moveHeatmapGridFocus([3, 2], { rowIndex: 0, columnIndex: 1 }, "ArrowDown")).toEqual({ rowIndex: 1, columnIndex: 1 });
    expect(moveHeatmapGridFocus([3, 2], { rowIndex: 1, columnIndex: 1 }, "ArrowRight")).toEqual({ rowIndex: 1, columnIndex: 1 });
    expect(moveHeatmapGridFocus([3, 2], { rowIndex: 1, columnIndex: 1 }, "Home")).toEqual({ rowIndex: 1, columnIndex: 0 });
    expect(moveHeatmapGridFocus([3, 2], { rowIndex: 0, columnIndex: 0 }, "End")).toEqual({ rowIndex: 0, columnIndex: 2 });
  });

  it("accepts synchronized evidence only for the exact selected matrix cell", () => {
    const selection = {
      rowId: "row-1",
      rowKey: "uncached_input_tokens",
      rowOrderIndex: 0,
      rowLabel: "Uncached input",
      periodStartTime: completeCell.startTime,
      periodEndTime: completeCell.endTime,
      formattedValue: completeCell.formattedValue,
      valueState: completeCell.valueState,
      applicableZero: completeCell.applicableZero,
      scale: { availability: "available" as const, minimum: 0, maximum: 1, basis: "visible_row_maximum" as const },
      supportingText: null,
    };
    const evidence = {
      snapshotId: "snapshot-1",
      revisionId: "revision-1",
      queryKind: "cell_evidence" as const,
      mode: "tokens" as const,
      rowId: selection.rowId,
      rowKey: selection.rowKey,
      rowOrderIndex: selection.rowOrderIndex,
      rowLabel: selection.rowLabel,
      periodStartTime: selection.periodStartTime,
      periodEndTime: selection.periodEndTime,
      value: completeCell.value,
      formattedValue: selection.formattedValue,
      valueState: selection.valueState,
      applicableZero: selection.applicableZero,
      evidenceItems: [],
      omittedEvidenceCount: 0,
      provenance: [],
    };
    expect(heatmapEvidenceMatchesSelection(selection, evidence)).toBe(true);
    expect(heatmapEvidenceMatchesSelection(selection, { ...evidence, formattedValue: "1" })).toBe(false);
  });

  it("creates a coherent matrix transition without carrying cell-scoped state", () => {
    const evidence = {
      snapshotId: "snapshot-1",
      revisionId: "revision-1",
      queryKind: "cell_evidence" as const,
      mode: "tokens" as const,
      rowId: "row-1",
      rowKey: "uncached_input_tokens",
      rowOrderIndex: 0,
      rowLabel: "Uncached input",
      periodStartTime: completeCell.startTime,
      periodEndTime: completeCell.endTime,
      value: completeCell.value,
      formattedValue: completeCell.formattedValue,
      valueState: completeCell.valueState,
      applicableZero: completeCell.applicableZero,
      evidenceItems: [],
      omittedEvidenceCount: 0,
      provenance: [],
    };
    const interaction = {
      mode: "tokens" as const,
      visibleFromTime: completeCell.startTime,
      visibleToTime: completeCell.endTime,
      requestedResolutionMinutes: 5 as const,
      maximumRows: 100,
      selectedCell: null,
      history: [],
      evidence: { kind: "loading" as const, previous: evidence, operationId: "operation-1" },
    };
    expect(heatmapInteractionForMatrixRequest(interaction, { mode: "models" })).toMatchObject({
      mode: "models",
      selectedCell: null,
      evidence: { kind: "not-requested" },
    });
  });
});

describe("boundary errors", () => {
  it("retains safe parser detail and gives the operator a recovery action", () => {
    expect(describeBoundaryError(new Error("heatmap result.totalCellCount does not match its rows"))).toBe(
      "The report response was invalid: heatmap result.totalCellCount does not match its rows. Retry this view. If the problem continues, open Diagnostics.",
    );
  });

  it("does not expose path-shaped exception detail", () => {
    expect(describeBoundaryError(new Error("invalid record at /private/operator/log.jsonl"))).toBe(
      "The report response was invalid. Retry this view. If the problem continues, open Diagnostics.",
    );
  });

  it("maps structured recovery flags to one explicit operator action", () => {
    const base = {
      code: "REPORT_UNAVAILABLE" as const,
      message: "Unavailable",
      operationId: null,
      recoverable: true,
      currentSourceRevision: null,
      preflightRequired: false,
      restartFromFirstPage: false,
    };
    expect(reportErrorRecovery({ ...base, restartFromFirstPage: true })).toEqual({ label: "First page", message: "Return to the first page and try again." });
    expect(reportErrorRecovery({ ...base, preflightRequired: true })).toEqual({ label: null, message: "Review the report scope again before retrying." });
    expect(reportErrorRecovery({ ...base, recoverable: false })).toEqual({ label: null, message: "Open Diagnostics for more information." });
  });
});

describe("export presentation", () => {
  it("describes a successful opaque export without revealing authority", () => {
    expect(describeExportResult({
      displayName: "agent-report-2026-08-12",
      mode: "directory",
      fileCount: 14,
      totalByteCount: 12_345,
    })).toBe("agent-report-2026-08-12 · complete directory · 14 files · 12,345 bytes");
  });
});

describe("workspace accessibility", () => {
  it("formats valid UTC instants in the browser locale and rejects invalid values", () => {
    const instant = "2026-08-12T12:30:00Z";
    expect(formatLocalInstant(instant)).toBe(
      new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short",
      }).format(new Date(instant)),
    );
    expect(() => formatLocalInstant("not-an-instant")).toThrow("valid ISO instant");
  });

  it("adds the browser-local snapshot observation time to the visible report title", () => {
    const observationTime = "2026-08-12T12:30:00Z";
    expect(snapshotTitleAsOf("Investigate report", observationTime)).toBe(
      `Investigate report as of ${new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short",
      }).format(new Date(observationTime))}`,
    );
    expect(snapshotTitleAsOf("  ", observationTime)).toMatch(/^Untitled run as of /);
  });
});
