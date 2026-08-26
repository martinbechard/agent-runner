// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Prepare and launch the authenticated live browser development host.

import { spawn, spawnSync } from "node:child_process";
import { homedir } from "node:os";
import { delimiter, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const rustcProxy = join(homedir(), ".cargo", "bin", process.platform === "win32" ? "rustc.exe" : "rustc");
const rustc = spawnSync(rustcProxy, ["--version"], { stdio: "ignore" }).status === 0 ? rustcProxy : "rustc";

const triple = spawnSync(rustc, ["--print", "host-tuple"], { encoding: "utf8" });
if (triple.status !== 0 || triple.stdout.trim() === "") process.exit(triple.status ?? 1);
const suffix = process.platform === "win32" ? ".exe" : "";
const worker = join(desktopRoot, "src-tauri", "binaries", `agent-report-${triple.stdout.trim()}${suffix}`);
const child = spawn(pnpm, ["exec", "tauri", "dev", "--config", "src-tauri/tauri.sidecar.conf.json"], {
  cwd: desktopRoot,
  env: {
    ...process.env,
    PATH: `${dirname(rustcProxy)}${delimiter}${process.env.PATH ?? ""}`,
    AGENT_REPORT_WEB_BRIDGE: "1",
    AGENT_REPORT_COMMAND: worker,
  },
  stdio: "inherit",
});
child.once("error", (error) => { console.error(error.message); process.exit(1); });
child.once("exit", (code, signal) => process.exitCode = signal === null ? (code ?? 1) : 1);
