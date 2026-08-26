// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Verify the authenticated browser-to-loopback command boundary.

import { afterEach, describe, expect, it, vi } from "vitest";

import { LoopbackTransport } from "./loopback-transport";

afterEach(() => vi.unstubAllGlobals());

describe("LoopbackTransport", () => {
  it("posts commands with the launch token and rejects non-loopback endpoints", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true, result: { roots: [], diagnosticsAvailable: false } }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    const transport = new LoopbackTransport("http://127.0.0.1:43127", "launch-token");
    await expect(transport.invokeApp("desktop_defaults")).resolves.toEqual({ roots: [], diagnosticsAvailable: false });
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:43127/api/command", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ authorization: "Bearer launch-token" }),
    }));
    expect(() => new LoopbackTransport("http://0.0.0.0:43127", "launch-token")).toThrow("loopback");
    expect(() => new LoopbackTransport("https://example.com", "launch-token")).toThrow("loopback");
  });

  it("surfaces the bridge error payload", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ ok: false, error: { code: "REPORT_UNAVAILABLE", message: "offline" } }), { status: 503 }));
    const transport = new LoopbackTransport("http://localhost:43127", "launch-token");
    await expect(transport.invokeApp("desktop_defaults")).rejects.toMatchObject({ code: "REPORT_UNAVAILABLE", message: "offline" });
  });
});
