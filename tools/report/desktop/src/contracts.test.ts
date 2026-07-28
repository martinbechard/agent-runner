// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify strict narrowing of native desktop command responses.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

import { describe, expect, it } from "vitest";

import {
  buildReportFilename,
  dateRangeError,
  discoveryProgressPresentation,
  parseReportHistory,
  parseDesktopDefaults,
  parseDiscoveryProgress,
  parseSearchResponse,
  rememberReportForSource,
  rememberedOutputPath,
  reportGenerationProgress,
} from "./contracts";

describe("native command contracts", () => {
  it("requires the native diagnostic log path in desktop defaults", () => {
    const defaults = parseDesktopDefaults({
      roots: ["/logs"],
      indexPath: "/cache/index.sqlite3",
      stateDbPath: "/home/user/.codex/state_5.sqlite",
      diagnosticLogPath: "/logs/agent-report.log",
    });

    expect(defaults.stateDbPath).toBe("/home/user/.codex/state_5.sqlite");
    expect(defaults.diagnosticLogPath).toBe("/logs/agent-report.log");
    expect(() =>
      parseDesktopDefaults({ roots: [], indexPath: null, stateDbPath: null }),
    ).toThrow(
      "diagnosticLogPath",
    );
  });

  it("accepts a complete privacy-bounded search response", () => {
    const response = parseSearchResponse({
      entries: [
        {
          threadId: "root",
          parentThreadId: "",
          taskTitle: "Build native index",
          startedAt: "2026-07-21T12:00:00Z",
          workspace: "/work/example",
          sourcePath: "/logs/root.jsonl",
          agentPath: "",
          agentNickname: "",
          delegationCount: 0,
          diagnostic: null,
        },
      ],
      stats: {
        candidate_files: 1,
        scanned_files: 1,
        cached_files: 0,
        unstable_files: 0,
        unreadable_files: 0,
        elapsed_ms: 7,
        workers: 1,
      },
    });

    expect(response.entries[0]?.threadId).toBe("root");
    expect(response.stats.elapsed_ms).toBe(7);
  });

  it("rejects unknown entry and progress variants", () => {
    expect(() => parseSearchResponse({ entries: [{ threadId: "root" }], stats: {} })).toThrow();
    expect(() =>
      parseSearchResponse({
        entries: [],
        stats: {
          candidate_files: 1.5,
          scanned_files: 1,
          cached_files: 0,
          unstable_files: 0,
          unreadable_files: 0,
          elapsed_ms: 7,
          workers: 1,
        },
      }),
    ).toThrow("non-negative integer");
    expect(() =>
      parseDiscoveryProgress({
        completed_files: 1,
        candidate_files: 1,
        path: "/logs/root.jsonl",
        source: "network",
      }),
    ).toThrow("not cache or scan");
  });

  it("presents index progress as determinate and report generation as indeterminate", () => {
    expect(
      discoveryProgressPresentation({
        completed_files: 8,
        candidate_files: 32,
        path: "/logs/root.jsonl",
        source: "scan",
      }),
    ).toEqual({
      label: "Reading changed rollout",
      value: "8 / 32",
      path: "/logs/root.jsonl",
      completed: 8,
      total: 32,
    });
    expect(reportGenerationProgress("/reports/root.html")).toEqual({
      label: "Preparing full report",
      value: "Working",
      path: "/reports/root.html",
      completed: null,
      total: null,
    });
  });

  it("builds a bounded report filename without path separators", () => {
    const filename = buildReportFilename(
      "Act on backlog/feature: native report? *now*",
      "root-thread",
    );

    expect(filename).toMatch(/\.html$/);
    expect(filename).not.toMatch(/[<>:"/\\|?*]/);
    expect(filename.length).toBeLessThanOrEqual(101);
  });

  it("reuses the last export folder for the next suggested filename", () => {
    expect(rememberedOutputPath("/tmp/old report.html", "agent-report-index.html")).toBe(
      "/tmp/agent-report-index.html",
    );
    expect(rememberedOutputPath("C:\\Reports\\old-report.html", "new-report.html")).toBe(
      "C:\\Reports\\new-report.html",
    );
    expect(rememberedOutputPath(null, "new-report.html")).toBe("new-report.html");
    expect(rememberedOutputPath("old-report.html", "new-report.html")).toBe("new-report.html");
  });

  it("remembers a distinct last report for each source log", () => {
    const first = rememberReportForSource({}, "/logs/first.jsonl", "/reports/first.html");
    const second = rememberReportForSource(
      first,
      "/logs/second.jsonl",
      "/reports/second.html",
    );
    const replaced = rememberReportForSource(
      second,
      "/logs/first.jsonl",
      "/reports/first-latest.html",
    );

    expect(replaced).toEqual({
      "/logs/first.jsonl": "/reports/first-latest.html",
      "/logs/second.jsonl": "/reports/second.html",
    });
    expect(first).toEqual({ "/logs/first.jsonl": "/reports/first.html" });
  });

  it("restores only valid source-to-report history entries", () => {
    expect(
      parseReportHistory(
        JSON.stringify({
          "/logs/root.jsonl": "/reports/root.html",
          "": "/reports/missing-source.html",
          "/logs/missing-report.jsonl": "",
          "/logs/not-a-path.jsonl": 42,
        }),
      ),
    ).toEqual({ "/logs/root.jsonl": "/reports/root.html" });
    expect(parseReportHistory("not-json")).toEqual({});
    expect(parseReportHistory(null)).toEqual({});
  });

  it("accepts open and inclusive ranges while rejecting reversed date-hours", () => {
    expect(dateRangeError("", "")).toBeNull();
    expect(dateRangeError("2026-07-21", "")).toBeNull();
    expect(dateRangeError("", "2026-07-21")).toBeNull();
    expect(dateRangeError("2026-07-21", "2026-07-21")).toBeNull();
    expect(dateRangeError("2026-07-21T09:00", "2026-07-21T17:00")).toBeNull();
    expect(dateRangeError("2026-07-21T17:00", "2026-07-21T09:00")).toBe(
      "From date and hour must not be after To date and hour.",
    );
    expect(dateRangeError("2026-07-22", "2026-07-21")).toBe(
      "From date and hour must not be after To date and hour.",
    );
  });
});
