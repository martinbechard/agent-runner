// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify the Dynamic Workspace controller and its pure presentation rules.
// Design: docs/design/components/CD-005-agent-report-dynamic-workspace.md

import { describe, expect, it } from "vitest";

import {
  DEFAULT_OVERSCAN_ROWS,
  DEFAULT_PAGE_SIZE,
  DEFAULT_ROW_HEIGHT_PX,
  MAX_CURSOR_HISTORY,
  MAX_HEATMAP_ROWS,
  MAX_PAGE_SIZE,
  MAX_TIME_BUCKETS,
  SURFACE_DEFINITIONS,
  WORKSPACE_COMMANDS,
  computeVirtualWindow,
  formatLocalInstant,
  heatmapResolutionLabel,
} from "./report-workspace";

describe("ReportWorkspaceController", () => {
  it("publishes the accepted bounded defaults and native command names", () => {
    expect({
      DEFAULT_PAGE_SIZE,
      MAX_PAGE_SIZE,
      MAX_CURSOR_HISTORY,
      MAX_TIME_BUCKETS,
      MAX_HEATMAP_ROWS,
      DEFAULT_ROW_HEIGHT_PX,
      DEFAULT_OVERSCAN_ROWS,
    }).toEqual({
      DEFAULT_PAGE_SIZE: 100,
      MAX_PAGE_SIZE: 500,
      MAX_CURSOR_HISTORY: 100,
      MAX_TIME_BUCKETS: 2_000,
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
