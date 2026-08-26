// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify the full-page browser fixture transport.

import { describe, expect, it } from "vitest";

import { FullAppFixtureTransport } from "./fixture-transport";

describe("FullAppFixtureTransport", () => {
  it("supports catalog discovery before opening the report workspace", async () => {
    const transport = new FullAppFixtureTransport();
    expect(await transport.invokeApp("desktop_defaults")).toEqual({
      roots: [{ rootRef: "fixture-root-ref", displayName: "Fixture sessions" }],
      diagnosticsAvailable: true,
    });
    const progress: unknown[] = [];
    const result = await transport.invokeApp("search_rollouts", {}, (value) => progress.push(value));
    expect(progress).toHaveLength(1);
    expect(result).toMatchObject({ entries: [{ threadId: "fixture-root-heatmap" }] });
  });

  it("delegates report commands to the canonical workspace fixture", async () => {
    const transport = new FullAppFixtureTransport();
    const result = await transport.invoke("preflight_report", {
      operationId: "op_fixture",
      rootThreadId: "fixture-root-heatmap",
      includeChildren: false,
      includeCollaborators: false,
    });
    expect(result).toMatchObject({ rootThreadId: "fixture-root-heatmap" });
  });
});
