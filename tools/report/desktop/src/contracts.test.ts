// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify strict narrowing of native desktop command responses.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

import { describe, expect, it } from "vitest";

import {
  buildReportFilename,
  parseDiscoveryProgress,
  parseSearchResponse,
  rememberedOutputPath,
} from "./contracts";

describe("native command contracts", () => {
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
});
