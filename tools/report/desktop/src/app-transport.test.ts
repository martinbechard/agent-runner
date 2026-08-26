// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify runtime transport selection for desktop and browser development.

import { describe, expect, it } from "vitest";

import { browserRuntimeMode, commandRequest, resolveRuntimeMode } from "./app-transport";

describe("application transport", () => {
  it("selects fixture and live browser modes explicitly", () => {
    expect(browserRuntimeMode("?transport=fixture")).toBe("fixture");
    expect(browserRuntimeMode("?transport=live")).toBe("live");
    expect(browserRuntimeMode("")).toBe("tauri");
  });

  it("uses fixtures for a plain Vite page but preserves Tauri inside the desktop host", () => {
    expect(resolveRuntimeMode("", true, false)).toBe("fixture");
    expect(resolveRuntimeMode("", true, true)).toBe("tauri");
    expect(resolveRuntimeMode("?transport=live", true, false)).toBe("live");
    expect(resolveRuntimeMode("", false, false)).toBe("tauri");
  });

  it("preserves Tauri command argument shapes", () => {
    expect(commandRequest("desktop_defaults")).toEqual({});
    expect(commandRequest("search_rollouts", { rootRefs: ["root-1"] })).toEqual({
      request: { rootRefs: ["root-1"] },
    });
    expect(commandRequest("open_report_window", { exportId: "export-1" })).toEqual({ exportId: "export-1" });
  });
});
