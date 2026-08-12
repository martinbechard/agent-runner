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
  SURFACE_DEFINITIONS,
  WORKSPACE_COMMANDS,
  computeVirtualWindow,
  describeBoundaryError,
  describeExportResult,
  formatLocalInstant,
  heatmapCellPresentation,
  heatmapResolutionLabel,
  nextHeatmapResolution,
  newOperationId,
  reportErrorRecovery,
  shiftHeatmapRange,
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
      DEFAULT_ROW_HEIGHT_PX,
      DEFAULT_OVERSCAN_ROWS,
    }).toEqual({
      DEFAULT_PAGE_SIZE: 100,
      MAX_PAGE_SIZE: 500,
      MAX_CURSOR_HISTORY: 100,
      MAX_HEATMAP_CELLS: 2_000,
      MAX_HEATMAP_ROWS: 200,
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
      queryTimeRange: "query_time_range",
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
    expect(SURFACE_DEFINITIONS.heatmap.operation).toBe("query_time_range");
    expect(SURFACE_DEFINITIONS.timeline.operation).toBe("list_events");
    expect(SURFACE_DEFINITIONS.tools.operation).toBe("list_events");
    expect(SURFACE_DEFINITIONS.detail.operation).toBe("get_event_details");
    expect(SURFACE_DEFINITIONS.diagnostics.operation).toBeNull();
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
      "Showing 17-minute buckets; requested 5-minute buckets.",
    );
    expect(() => heatmapResolutionLabel(0, 5)).toThrow("positive finite");
    expect(() => heatmapResolutionLabel(5, Number.NaN)).toThrow("positive finite");
  });

  it("moves a half-open range by one actual bucket without changing its duration", () => {
    expect(shiftHeatmapRange(
      { fromTime: "2026-08-12T12:00:00Z", toTime: "2026-08-12T13:00:00Z" },
      17,
      "next",
    )).toEqual({
      fromTime: "2026-08-12T12:17:00.000Z",
      toTime: "2026-08-12T13:17:00.000Z",
    });
    expect(shiftHeatmapRange(
      { fromTime: "2026-08-12T12:00:00Z", toTime: "2026-08-12T13:00:00Z" },
      5,
      "previous",
    )).toEqual({
      fromTime: "2026-08-12T11:55:00.000Z",
      toTime: "2026-08-12T12:55:00.000Z",
    });
  });

  it("zooms only through the accepted requested resolutions", () => {
    expect(nextHeatmapResolution(15, "in")).toBe(5);
    expect(nextHeatmapResolution(15, "out")).toBe(30);
    expect(nextHeatmapResolution(1, "in")).toBe(1);
    expect(nextHeatmapResolution(60, "out")).toBe(60);
  });

  it("uses each row domain independently and preserves non-color semantics", () => {
    expect(heatmapCellPresentation(
      { minimum: 0, maximum: 10, colorSemantic: "sequential_nonnegative", basis: "visible_row_maximum" },
      5,
    )).toEqual({ tone: "sequential", intensity: 0.5, label: "midpoint" });
    expect(heatmapCellPresentation(
      { minimum: 0, maximum: 100, colorSemantic: "sequential_nonnegative", basis: "context_window_capacity" },
      5,
    )).toEqual({ tone: "sequential", intensity: 0.05, label: "low" });
    expect(heatmapCellPresentation(
      { minimum: -20, maximum: 80, colorSemantic: "diverging_signed", basis: "visible_row_maximum" },
      -10,
    )).toEqual({ tone: "negative", intensity: 0.5, label: "negative" });
    expect(heatmapCellPresentation(
      { minimum: 3, maximum: 3, colorSemantic: "sequential_nonnegative", basis: "visible_row_maximum" },
      3,
    )).toEqual({ tone: "midpoint", intensity: 0.5, label: "midpoint" });
    expect(heatmapCellPresentation(
      { minimum: 0, maximum: 10, colorSemantic: "sequential_nonnegative", basis: "visible_row_maximum" },
      null,
    )).toEqual({ tone: "unavailable", intensity: 0, label: "unavailable" });
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
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(instant)),
    );
    expect(() => formatLocalInstant("not-an-instant")).toThrow("valid ISO instant");
  });
});
