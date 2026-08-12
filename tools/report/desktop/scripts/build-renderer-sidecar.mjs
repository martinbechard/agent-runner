// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Build the self-contained report renderer sidecar consumed by Tauri.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

import { constants } from "node:fs";
import { access, mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { delimiter, dirname, join, resolve } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(scriptDirectory, "..");
const reportRoot = resolve(desktopRoot, "..");
const repositoryRoot = resolve(reportRoot, "../..");
const tauriRoot = join(desktopRoot, "src-tauri");
const binariesRoot = join(tauriRoot, "binaries");
const pyinstallerRoot = join(reportRoot, "target", "pyinstaller");
const pythonPackageRoot = join(reportRoot, "src");
const pythonEntryPoint = join(pythonPackageRoot, "agent_report", "cli.py");
const reportScript = join(reportRoot, "scripts", "run-timeline.py");
const formatterConfig = join(reportRoot, "tool-formatters.json");
const pricingConfig = join(
  repositoryRoot,
  "docs",
  "reference",
  "openai-model-pricing.json",
);

function executableSuffix() {
  return process.platform === "win32" ? ".exe" : "";
}

function rustCommand(name) {
  const configured = process.env[name.toUpperCase()];
  if (configured) {
    return configured;
  }
  const rustupProxy = join(homedir(), ".cargo", "bin", `${name}${executableSuffix()}`);
  return spawnSync(rustupProxy, ["--version"], { stdio: "ignore" }).status === 0
    ? rustupProxy
    : name;
}

function pythonCandidates() {
  const virtualEnvironmentPython =
    process.platform === "win32"
      ? join(reportRoot, ".venv", "Scripts", "python.exe")
      : join(reportRoot, ".venv", "bin", "python");
  return [
    process.env.AGENT_REPORT_PYTHON,
    virtualEnvironmentPython,
    "python3.15",
    "python3.14",
    "python3.13",
    "python3.12",
    "python3.11",
    "python3",
  ].filter(Boolean);
}

function selectBuildPython() {
  for (const candidate of pythonCandidates()) {
    const probe = spawnSync(
      candidate,
      [
        "-c",
        "import sys; import PyInstaller; " +
          "raise SystemExit(0 if sys.version_info >= (3, 11) and PyInstaller.__version__ == '6.21.0' else 1)",
      ],
      { stdio: "ignore" },
    );
    if (probe.status === 0) {
      return candidate;
    }
  }
  throw new Error(
    "No Python 3.11+ interpreter with PyInstaller 6.21.0 was found. " +
      "Install tools/report with its desktop extra or set AGENT_REPORT_PYTHON.",
  );
}

function capture(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8" });
  if (result.status !== 0) {
    const diagnostic = (result.stderr || result.stdout || "command failed").trim();
    throw new Error(`${command} ${args.join(" ")} failed: ${diagnostic}`);
  }
  return result.stdout.trim();
}

async function run(command, args) {
  await new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, { stdio: "inherit" });
    child.once("error", rejectPromise);
    child.once("exit", (code, signal) => {
      if (code === 0) {
        resolvePromise();
        return;
      }
      rejectPromise(
        new Error(
          `${command} failed${signal ? ` with signal ${signal}` : ` with exit code ${code}`}`,
        ),
      );
    });
  });
}

async function requireFile(path) {
  await access(path, constants.R_OK);
}

const cargo = rustCommand("cargo");
const rustc = rustCommand("rustc");
const python = selectBuildPython();
const targetTriple = capture(rustc, ["--print", "host-tuple"]);
const sidecarName = `agent-report-${targetTriple}`;
const engineName = `agent-report-engine${executableSuffix()}`;
const enginePath = join(reportRoot, "target", "release", engineName);

await Promise.all([
  requireFile(pythonEntryPoint),
  requireFile(reportScript),
  requireFile(formatterConfig),
  requireFile(pricingConfig),
  mkdir(binariesRoot, { recursive: true }),
  mkdir(join(pyinstallerRoot, "work"), { recursive: true }),
  mkdir(join(pyinstallerRoot, "spec"), { recursive: true }),
]);

await run(cargo, [
  "build",
  "--locked",
  "--release",
  "--manifest-path",
  join(reportRoot, "Cargo.toml"),
  "-p",
  "agent-report-engine",
]);
await requireFile(enginePath);

const hiddenImports = [
  "agent_report.application_service",
  "agent_report.event_cache",
  "agent_report.mcp_report",
  "agent_report.report_worker",
  "agent_report.static_export",
  "argparse",
  "bisect",
  "collections",
  "concurrent.futures",
  "copy",
  "csv",
  "dataclasses",
  "datetime",
  "hashlib",
  "io",
  "json",
  "re",
  "shutil",
  "sqlite3",
  "subprocess",
  "threading",
];
const pyinstallerArguments = [
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name",
  sidecarName,
  "--distpath",
  binariesRoot,
  "--workpath",
  join(pyinstallerRoot, "work"),
  "--specpath",
  join(pyinstallerRoot, "spec"),
  "--paths",
  pythonPackageRoot,
  "--add-data",
  `${reportScript}${delimiter}share/agent-report`,
  "--add-data",
  `${formatterConfig}${delimiter}share/agent-report`,
  "--add-data",
  `${pricingConfig}${delimiter}share/agent-report`,
  "--add-binary",
  `${enginePath}${delimiter}agent_report/native`,
  ...hiddenImports.flatMap((moduleName) => ["--hidden-import", moduleName]),
  pythonEntryPoint,
];

await run(python, pyinstallerArguments);
console.log(`Built renderer sidecar: ${join(binariesRoot, sidecarName + executableSuffix())}`);
