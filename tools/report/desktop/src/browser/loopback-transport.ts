// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Call the authenticated development-only Agent Report loopback host.
// Design: docs/design/components/CD-005-agent-report-dynamic-workspace.md

import type { AppCommandName, AppTransport } from "../app-transport";
import type { WorkspaceCommandName } from "../report-workspace";

interface BridgeResponse {
  readonly ok: boolean;
  readonly result?: unknown;
  readonly error?: unknown;
}

export class LoopbackTransport implements AppTransport {
  private readonly endpoint: string;
  private readonly token: string;

  constructor(endpoint: string, token: string) {
    const parsed = new URL(endpoint);
    if (parsed.protocol !== "http:" || (parsed.hostname !== "127.0.0.1" && parsed.hostname !== "localhost" && parsed.hostname !== "[::1]")) {
      throw new Error("The live Agent Report bridge must use an HTTP loopback endpoint.");
    }
    if (parsed.username !== "" || parsed.password !== "" || parsed.search !== "" || parsed.hash !== "" || token === "") {
      throw new Error("The live Agent Report bridge configuration is invalid.");
    }
    this.endpoint = parsed.origin;
    this.token = token;
  }

  invoke(command: WorkspaceCommandName, request: unknown): Promise<unknown> {
    return this.invokeApp(command, request);
  }

  subscribeProgress(_listener: (value: unknown) => void): () => void {
    return () => undefined;
  }

  async subscribeParentReport(): Promise<() => void> {
    return () => undefined;
  }

  async invokeApp(command: AppCommandName, payload?: unknown): Promise<unknown> {
    const response = await fetch(`${this.endpoint}/api/command`, {
      method: "POST",
      headers: { authorization: `Bearer ${this.token}`, "content-type": "application/json" },
      body: JSON.stringify({ command, payload: payload ?? null }),
    });
    const value = await response.json() as BridgeResponse;
    if (!response.ok || !value.ok) throw value.error ?? new Error(`Agent Report bridge returned HTTP ${response.status}.`);
    return value.result;
  }
}
