// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Isolate Agent Report UI commands from the desktop or browser host.
// Design: docs/design/components/CD-005-agent-report-dynamic-workspace.md

import type { WorkspaceCommandName, WorkspaceTransport } from "./report-workspace";

export type AppRuntimeMode = "tauri" | "fixture" | "live";
export type AppCommandName = WorkspaceCommandName
  | "desktop_defaults"
  | "add_root"
  | "search_rollouts"
  | "export_catalog"
  | "open_report_window"
  | "open_diagnostic_log"
  | "record_client_error";

export interface AppTransport extends WorkspaceTransport {
  invokeApp(command: AppCommandName, payload?: unknown, onProgress?: (value: unknown) => void): Promise<unknown>;
  subscribeParentReport(listener: (value: unknown) => void): Promise<() => void>;
}

export function browserRuntimeMode(search: string): AppRuntimeMode {
  const mode = new URLSearchParams(search).get("transport");
  return mode === "fixture" || mode === "live" ? mode : "tauri";
}

export function resolveRuntimeMode(search: string, development: boolean, hasTauriHost: boolean): AppRuntimeMode {
  const explicit = browserRuntimeMode(search);
  return explicit === "tauri" && development && !hasTauriHost ? "fixture" : explicit;
}

export function commandRequest(command: AppCommandName, payload?: unknown): Record<string, unknown> {
  if (payload === undefined) return {};
  if (command === "search_rollouts" || command === "export_catalog") return { request: payload };
  if (command === "desktop_defaults" || command === "add_root" || command === "open_diagnostic_log") return {};
  return payload as Record<string, unknown>;
}

export async function createTauriTransport(): Promise<AppTransport> {
  const [{ Channel, invoke }, { listen }] = await Promise.all([
    import("@tauri-apps/api/core"),
    import("@tauri-apps/api/event"),
  ]);
  const progressListeners = new Set<(value: unknown) => void>();
  let progressUnlisten: (() => void) | null = null;

  return {
    invoke(command, request) {
      return invoke(command, { request });
    },
    async invokeApp(command, payload, onProgress) {
      if (command === "search_rollouts" && onProgress !== undefined) {
        const onEvent = new Channel<unknown>();
        onEvent.onmessage = onProgress;
        return invoke(command, { ...commandRequest(command, payload), onEvent });
      }
      return invoke(command, commandRequest(command, payload));
    },
    subscribeProgress(listener) {
      progressListeners.add(listener);
      if (progressUnlisten === null) {
        void listen<unknown>("report-operation-progress", (event) => {
          for (const subscriber of progressListeners) subscriber(event.payload);
        }).then((unlisten) => { progressUnlisten = unlisten; });
      }
      return () => {
        progressListeners.delete(listener);
        if (progressListeners.size === 0) {
          progressUnlisten?.();
          progressUnlisten = null;
        }
      };
    },
    async subscribeParentReport(listener) {
      return listen<unknown>("view-parent-report", (event) => listener(event.payload));
    },
  };
}
