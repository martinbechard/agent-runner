// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Validate the desktop application's native command results at the webview boundary.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

/** Native startup paths for local Codex stores, the incremental index, and diagnostics. */
export interface DesktopDefaults {
  readonly roots: readonly string[];
  readonly indexPath: string | null;
  readonly stateDbPath: string | null;
  readonly diagnosticLogPath: string;
}

/** User-selected search scope sent to the native command boundary. */
export interface SearchRequest {
  readonly roots: readonly string[];
  readonly indexPath: string | null;
  readonly stateDbPath: string | null;
  readonly query: string;
  readonly fromDate: string;
  readonly toDate: string;
  readonly includeDescendants: boolean;
  readonly workers: number | null;
}

/** Return the user-facing error for a reversed optional ISO date range. */
export function dateRangeError(fromDate: string, toDate: string): string | null {
  if (fromDate !== "" && toDate !== "" && fromDate > toDate) {
    return "From date and hour must not be after To date and hour.";
  }
  return null;
}

/** Convert a browser-local whole-hour value to the UTC boundary expected by native search. */
export function localDateHourToUtc(value: string): string {
  if (value === "") {
    return "";
  }
  return new Date(value).toISOString().slice(0, 13);
}

/** Privacy-bounded metadata for one discovered Codex rollout. */
export interface CatalogEntry {
  readonly threadId: string;
  readonly parentThreadId: string;
  readonly taskTitle: string;
  readonly startedAt: string;
  readonly lastActivityAt: string;
  readonly workspace: string;
  readonly sourcePath: string;
  readonly agentPath: string;
  readonly agentNickname: string;
  readonly delegationCount: number;
  readonly diagnostic: string | null;
}

/** Reconciled native scan, cache, and worker counts. */
export interface DiscoveryStats {
  readonly candidate_files: number;
  readonly scanned_files: number;
  readonly cached_files: number;
  readonly unstable_files: number;
  readonly unreadable_files: number;
  readonly elapsed_ms: number;
  readonly workers: number;
}

/** Filtered catalog entries plus the statistics for their discovery pass. */
export interface SearchResponse {
  readonly entries: readonly CatalogEntry[];
  readonly stats: DiscoveryStats;
}

/** Bounded progress update emitted while native workers scan or reuse a file. */
export interface DiscoveryProgress {
  readonly completed_files: number;
  readonly candidate_files: number;
  readonly path: string;
  readonly source: "cache" | "scan";
}

/** User-visible copy and completion bounds for the shared progress panel. */
export interface ProgressPresentation {
  readonly label: string;
  readonly value: string;
  readonly path: string;
  readonly completed: number | null;
  readonly total: number | null;
  readonly detail?: string;
}

/** Determinate phase progress emitted by the full-report renderer. */
export interface ReportGenerationProgress {
  readonly completed: number;
  readonly total: number;
  readonly label: string;
  readonly detail: string;
  readonly worker: string | null;
}

/** Clamp persisted or user-entered worker counts to the supported renderer range. */
export function normalizeWorkerCount(value: unknown, fallback: number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 1 && parsed <= 64 ? parsed : fallback;
}

/** Present native discovery events as determinate progress. */
export function discoveryProgressPresentation(
  progress: DiscoveryProgress,
): ProgressPresentation {
  return {
    label: progress.source === "cache" ? "Reusing stable metadata" : "Reading changed rollout",
    value: `${progress.completed_files} / ${progress.candidate_files}`,
    path: progress.path,
    completed: progress.completed_files,
    total: progress.candidate_files,
  };
}

/** Present the initial full-report rendering phase as determinate progress. */
export function reportGenerationProgress(outputPath: string): ProgressPresentation {
  return {
    label: "Starting report generation",
    value: "0%",
    path: outputPath,
    completed: 0,
    total: 100,
    detail: "Preparing the renderer process.",
  };
}

export function parseReportGenerationProgress(value: unknown): ReportGenerationProgress {
  const record = requireRecord(value, "report generation progress");
  const completed = requireNumber(record, "completed", "report generation progress");
  const total = requireNumber(record, "total", "report generation progress");
  if (total === 0 || completed > total) {
    throw new Error("report generation progress is outside its total");
  }
  return {
    completed,
    total,
    label: requireString(record, "label", "report generation progress"),
    detail: requireString(record, "detail", "report generation progress"),
    worker:
      record.worker === null
        ? null
        : requireString(record, "worker", "report generation progress"),
  };
}

/** Result returned after the native layer writes a catalog export. */
export interface ExportResult {
  readonly outputPath: string;
  readonly entryCount: number;
}

/** Latest generated full-report path indexed by the exact source JSONL path. */
export type ReportHistory = Readonly<Record<string, string>>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error(`${label} is not an object`);
  }
  return value;
}

function requireString(record: Record<string, unknown>, key: string, label: string): string {
  const value = record[key];
  if (!isString(value)) {
    throw new Error(`${label}.${key} is not a string`);
  }
  return value;
}

function requireNumber(record: Record<string, unknown>, key: string, label: string): number {
  const value = record[key];
  if (!isNonNegativeInteger(value)) {
    throw new Error(`${label}.${key} is not a non-negative integer`);
  }
  return value;
}

/**
 * Narrow unknown native defaults before any filesystem paths reach application state.
 *
 * @throws {Error} When a root, local database, or diagnostic path has an unsupported shape.
 */
export function parseDesktopDefaults(value: unknown): DesktopDefaults {
  const record = requireRecord(value, "desktop defaults");
  const roots = record.roots;
  const indexPath = record.indexPath;
  const stateDbPath = record.stateDbPath;
  const diagnosticLogPath = record.diagnosticLogPath;
  if (!Array.isArray(roots) || !roots.every(isString)) {
    throw new Error("desktop defaults.roots is not a string array");
  }
  if (indexPath !== null && !isString(indexPath)) {
    throw new Error("desktop defaults.indexPath is not a string or null");
  }
  if (stateDbPath !== null && !isString(stateDbPath)) {
    throw new Error("desktop defaults.stateDbPath is not a string or null");
  }
  if (!isString(diagnosticLogPath) || diagnosticLogPath === "") {
    throw new Error("desktop defaults.diagnosticLogPath is not a non-empty string");
  }
  return { roots, indexPath, stateDbPath, diagnosticLogPath };
}

function parseCatalogEntry(value: unknown, index: number): CatalogEntry {
  const label = `search response.entries[${index}]`;
  const record = requireRecord(value, label);
  const diagnostic = record.diagnostic;
  if (diagnostic !== null && !isString(diagnostic)) {
    throw new Error(`${label}.diagnostic is not a string or null`);
  }
  return {
    threadId: requireString(record, "threadId", label),
    parentThreadId: requireString(record, "parentThreadId", label),
    taskTitle: requireString(record, "taskTitle", label),
    startedAt: requireString(record, "startedAt", label),
    lastActivityAt: requireString(record, "lastActivityAt", label),
    workspace: requireString(record, "workspace", label),
    sourcePath: requireString(record, "sourcePath", label),
    agentPath: requireString(record, "agentPath", label),
    agentNickname: requireString(record, "agentNickname", label),
    delegationCount: requireNumber(record, "delegationCount", label),
    diagnostic,
  };
}

function parseStats(value: unknown): DiscoveryStats {
  const record = requireRecord(value, "search response.stats");
  return {
    candidate_files: requireNumber(record, "candidate_files", "search response.stats"),
    scanned_files: requireNumber(record, "scanned_files", "search response.stats"),
    cached_files: requireNumber(record, "cached_files", "search response.stats"),
    unstable_files: requireNumber(record, "unstable_files", "search response.stats"),
    unreadable_files: requireNumber(record, "unreadable_files", "search response.stats"),
    elapsed_ms: requireNumber(record, "elapsed_ms", "search response.stats"),
    workers: requireNumber(record, "workers", "search response.stats"),
  };
}

/**
 * Narrow one unknown search response into the catalog contract.
 *
 * @throws {Error} When entries, diagnostics, or statistics violate the native protocol.
 */
export function parseSearchResponse(value: unknown): SearchResponse {
  const record = requireRecord(value, "search response");
  if (!Array.isArray(record.entries)) {
    throw new Error("search response.entries is not an array");
  }
  return {
    entries: record.entries.map(parseCatalogEntry),
    stats: parseStats(record.stats),
  };
}

/**
 * Narrow one unknown progress payload, including its exhaustive cache-or-scan source.
 *
 * @throws {Error} When counts, path, or source are invalid.
 */
export function parseDiscoveryProgress(value: unknown): DiscoveryProgress {
  const record = requireRecord(value, "discovery progress");
  const source = record.source;
  if (source !== "cache" && source !== "scan") {
    throw new Error("discovery progress.source is not cache or scan");
  }
  return {
    completed_files: requireNumber(record, "completed_files", "discovery progress"),
    candidate_files: requireNumber(record, "candidate_files", "discovery progress"),
    path: requireString(record, "path", "discovery progress"),
    source,
  };
}

/**
 * Narrow the bounded result of a native catalog export.
 *
 * @throws {Error} When the output path or entry count is invalid.
 */
export function parseExportResult(value: unknown): ExportResult {
  const record = requireRecord(value, "export result");
  return {
    outputPath: requireString(record, "outputPath", "export result"),
    entryCount: requireNumber(record, "entryCount", "export result"),
  };
}

/** Build a portable HTML filename from a display title without path traversal characters. */
export function buildReportFilename(taskTitle: string, threadId: string): string {
  const source = taskTitle.trim() || threadId.trim() || "agent-report";
  const safeStem = source
    .normalize("NFKC")
    .replace(/[<>:"/\\|?*\u0000-\u001F\u007F]+/g, "-")
    .replace(/\s+/g, " ")
    .replace(/-+/g, "-")
    .replace(/^[ .-]+|[ .-]+$/g, "")
    .slice(0, 96)
    .replace(/[ .-]+$/g, "");
  return `${safeStem || "agent-report"}.html`;
}

/** Reuse the folder of the last export while allowing the next filename to change. */
export function rememberedOutputPath(
  lastExportPath: string | null,
  fallbackFilename: string,
): string {
  const normalizedPath = lastExportPath?.trim();
  if (!normalizedPath) {
    return fallbackFilename;
  }
  const separatorIndex = Math.max(
    normalizedPath.lastIndexOf("/"),
    normalizedPath.lastIndexOf("\\"),
  );
  if (separatorIndex < 0) {
    return fallbackFilename;
  }
  return `${normalizedPath.slice(0, separatorIndex + 1)}${fallbackFilename}`;
}

/**
 * Restore per-source report history from local storage without trusting its JSON shape.
 *
 * Malformed JSON and entries with empty or non-string paths are ignored so corrupt local
 * preferences cannot prevent the desktop application from starting.
 */
export function parseReportHistory(serializedHistory: string | null): ReportHistory {
  if (serializedHistory === null) {
    return {};
  }
  try {
    const value: unknown = JSON.parse(serializedHistory);
    if (!isRecord(value)) {
      return {};
    }
    const history: Record<string, string> = {};
    for (const [sourcePath, reportPath] of Object.entries(value)) {
      if (sourcePath.trim() !== "" && isString(reportPath) && reportPath.trim() !== "") {
        history[sourcePath] = reportPath;
      }
    }
    return history;
  } catch {
    return {};
  }
}

/**
 * Return a new history mapping with one source log associated with its latest full report.
 *
 * Empty paths are ignored and the supplied mapping is never mutated.
 */
export function rememberReportForSource(
  history: ReportHistory,
  sourcePath: string,
  reportPath: string,
): ReportHistory {
  if (sourcePath.trim() === "" || reportPath.trim() === "") {
    return history;
  }
  return { ...history, [sourcePath]: reportPath };
}
