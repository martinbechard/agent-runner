// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Drive local run search, virtualized browsing, report export, and diagnostic interactions.
// Design: docs/design/components/CD-001-codex-rollout-metrics.md

import { Channel, invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";

import {
  type CatalogEntry,
  type DiscoveryProgress,
  type ExportResult,
  type ReportHistory,
  type SearchRequest,
  type SearchResponse,
  buildReportFilename,
  dateRangeError,
  parseDesktopDefaults,
  parseDiscoveryProgress,
  parseExportResult,
  parseReportHistory,
  parseSearchResponse,
  rememberReportForSource,
  rememberedOutputPath,
} from "./contracts";
import "./styles.css";

type ViewState =
  | { readonly kind: "idle" }
  | { readonly kind: "searching"; readonly progress: DiscoveryProgress | null }
  | { readonly kind: "ready"; readonly response: SearchResponse }
  | { readonly kind: "error"; readonly message: string };

const ROW_HEIGHT = 118;
const OVERSCAN = 5;
const LAST_EXPORT_STORAGE_KEY = "agent-report:last-export-path:v1";
const REPORT_HISTORY_STORAGE_KEY = "agent-report:last-report-by-source:v1";

const roots = new Set<string>();
let indexPath: string | null = null;
let entries: readonly CatalogEntry[] = [];
let selectedThreadId: string | null = null;
let lastExportPath: string | null = null;
let reportHistory: ReportHistory = {};
let state: ViewState = { kind: "idle" };

function element<T extends HTMLElement>(id: string): T {
  const value = document.getElementById(id);
  if (!(value instanceof HTMLElement)) {
    throw new Error(`Missing desktop interface element #${id}`);
  }
  return value as T;
}

const addRootButton = element<HTMLButtonElement>("add-root");
const rootList = element<HTMLDivElement>("root-list");
const queryInput = element<HTMLInputElement>("query");
const fromDateInput = element<HTMLInputElement>("from-date");
const toDateInput = element<HTMLInputElement>("to-date");
const includeDescendantsInput = element<HTMLInputElement>("include-descendants");
const searchButton = element<HTMLButtonElement>("search");
const exportButton = element<HTMLButtonElement>("export-catalog");
const openLastExportButton = element<HTMLButtonElement>("open-last-export");
const lastExportLabel = element<HTMLParagraphElement>("last-export-path");
const openDiagnosticLogButton = element<HTMLButtonElement>("open-diagnostic-log");
const diagnosticLogLabel = element<HTMLParagraphElement>("diagnostic-log-path");
const generateButton = element<HTMLButtonElement>("generate-report");
const resultCount = element<HTMLParagraphElement>("result-count");
const statsPanel = element<HTMLDivElement>("stats");
const progressPanel = element<HTMLDivElement>("progress-panel");
const progressLabel = element<HTMLSpanElement>("progress-label");
const progressValue = element<HTMLOutputElement>("progress-value");
const progressBar = element<HTMLElement>("progress-bar");
const progressPath = element<HTMLParagraphElement>("progress-path");
const resultsViewport = element<HTMLDivElement>("results-viewport");
const resultsCanvas = element<HTMLDivElement>("results-canvas");
const emptyState = element<HTMLDivElement>("empty-state");
const detailTitle = element<HTMLHeadingElement>("detail-title");
const detailFields = element<HTMLDListElement>("detail-fields");
const status = element<HTMLParagraphElement>("status");
const statusDot = element<HTMLSpanElement>("status-dot");
const signalRail = element<HTMLDivElement>("signal-rail");

function currentRequest(): SearchRequest {
  return {
    roots: [...roots],
    indexPath,
    query: queryInput.value.trim(),
    fromDate: fromDateInput.value,
    toDate: toDateInput.value,
    includeDescendants: includeDescendantsInput.checked,
    workers: null,
  };
}

function renderRoots(): void {
  rootList.replaceChildren();
  if (roots.size === 0) {
    const empty = document.createElement("p");
    empty.className = "root-empty";
    empty.textContent = "No log folders selected.";
    rootList.append(empty);
    return;
  }
  for (const path of roots) {
    const row = document.createElement("div");
    row.className = "root-chip";
    const label = document.createElement("span");
    label.textContent = path;
    label.title = path;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.title = `Remove ${path}`;
    remove.setAttribute("aria-label", `Remove ${path}`);
    remove.addEventListener("click", () => {
      roots.delete(path);
      renderRoots();
    });
    row.append(label, remove);
    rootList.append(row);
  }
}

function setState(nextState: ViewState): void {
  state = nextState;
  const searching = state.kind === "searching";
  searchButton.disabled = searching;
  addRootButton.disabled = searching;
  progressPanel.hidden = !searching;
  signalRail.classList.toggle("is-live", searching);
  statusDot.className = state.kind;
  if (state.kind === "idle") {
    status.textContent = "Waiting for a search.";
  } else if (state.kind === "searching") {
    status.textContent = "Native workers are reading changed logs and reusing stable index rows.";
  } else if (state.kind === "ready") {
    status.textContent = `Index ready in ${formatDuration(state.response.stats.elapsed_ms)}.`;
  } else {
    status.textContent = state.message;
  }
}

function renderProgress(progress: DiscoveryProgress): void {
  const total = Math.max(1, progress.candidate_files);
  const ratio = Math.min(1, progress.completed_files / total);
  progressLabel.textContent = progress.source === "cache" ? "Reusing stable metadata" : "Reading changed rollout";
  progressValue.value = `${progress.completed_files} / ${progress.candidate_files}`;
  progressBar.style.width = `${(ratio * 100).toFixed(1)}%`;
  progressPath.textContent = progress.path;
  progressPath.title = progress.path;
}

function formatDuration(milliseconds: number): string {
  if (milliseconds < 1_000) {
    return `${Math.round(milliseconds)} ms`;
  }
  return `${(milliseconds / 1_000).toFixed(2)} s`;
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp || "Time unavailable";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function renderResponse(response: SearchResponse): void {
  entries = response.entries;
  if (selectedThreadId !== null && !entries.some((entry) => entry.threadId === selectedThreadId)) {
    selectedThreadId = null;
  }
  resultCount.textContent = `${entries.length.toLocaleString()} runs from ${response.stats.candidate_files.toLocaleString()} files`;
  statsPanel.replaceChildren(
    stat(`${response.stats.scanned_files}`, "read"),
    stat(`${response.stats.cached_files}`, "reused"),
    stat(`${response.stats.workers}`, "workers"),
  );
  exportButton.disabled = false;
  emptyState.hidden = entries.length > 0;
  renderVirtualRows();
  renderSelection();
}

function stat(value: string, label: string): HTMLElement {
  const wrapper = document.createElement("span");
  const strong = document.createElement("strong");
  strong.textContent = value;
  const caption = document.createElement("small");
  caption.textContent = label;
  wrapper.append(strong, caption);
  return wrapper;
}

function renderVirtualRows(): void {
  resultsCanvas.replaceChildren();
  resultsCanvas.style.height = `${entries.length * ROW_HEIGHT}px`;
  if (entries.length === 0) {
    return;
  }
  const start = Math.max(0, Math.floor(resultsViewport.scrollTop / ROW_HEIGHT) - OVERSCAN);
  const visibleCount = Math.ceil(resultsViewport.clientHeight / ROW_HEIGHT) + OVERSCAN * 2;
  const end = Math.min(entries.length, start + visibleCount);
  for (let index = start; index < end; index += 1) {
    const entry = entries[index];
    if (entry === undefined) {
      continue;
    }
    const row = document.createElement("button");
    row.type = "button";
    row.className = "run-row";
    row.classList.toggle("is-selected", entry.threadId === selectedThreadId);
    row.style.transform = `translateY(${index * ROW_HEIGHT}px)`;
    row.setAttribute("aria-pressed", String(entry.threadId === selectedThreadId));
    const title = document.createElement("strong");
    title.textContent = entry.taskTitle || "Untitled Codex run";
    title.title = title.textContent;
    const time = document.createElement("time");
    time.textContent = formatTimestamp(entry.startedAt);
    time.dateTime = entry.startedAt;
    const context = document.createElement("span");
    context.className = "row-context";
    context.textContent = entry.workspace || entry.sourcePath;
    context.title = context.textContent;
    const id = document.createElement("code");
    id.textContent = entry.threadId;
    id.title = entry.threadId;
    row.append(time, title, context, id);
    row.addEventListener("click", () => {
      selectedThreadId = entry.threadId;
      renderVirtualRows();
      renderSelection();
    });
    resultsCanvas.append(row);
  }
}

function renderSelection(): void {
  const selected = entries.find((entry) => entry.threadId === selectedThreadId) ?? null;
  detailFields.replaceChildren();
  generateButton.disabled = selected === null || selected.parentThreadId !== "";
  if (selected === null) {
    detailTitle.textContent = "No run selected";
    return;
  }
  detailTitle.textContent = selected.taskTitle || "Untitled Codex run";
  detailTitle.title = detailTitle.textContent;
  addDetail("Observed", formatTimestamp(selected.startedAt));
  addDetail("Thread", selected.threadId, true);
  addDetail("Workspace", selected.workspace || "Unavailable", true);
  addDetail("Source", selected.sourcePath, true);
  const reportPath = reportHistory[selected.sourcePath];
  if (reportPath !== undefined) {
    addReportDetail(reportPath);
  }
  if (selected.agentNickname) {
    addDetail("Agent", selected.agentNickname);
  }
  if (selected.delegationCount > 0) {
    addDetail("Delegations", selected.delegationCount.toLocaleString());
  }
}

function addDetail(label: string, value: string, tooltip = false): void {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value;
  if (tooltip) {
    description.title = value;
  }
  detailFields.append(term, description);
}

function addReportDetail(outputPath: string): void {
  const term = document.createElement("dt");
  term.textContent = "Last report";
  const description = document.createElement("dd");
  const reportLink = document.createElement("button");
  reportLink.type = "button";
  reportLink.className = "detail-report-link";
  reportLink.textContent = outputPath;
  reportLink.title = outputPath;
  reportLink.setAttribute("aria-label", `Open last report: ${outputPath}`);
  reportLink.addEventListener("click", () => {
    void openRememberedReport(outputPath, reportLink);
  });
  description.append(reportLink);
  detailFields.append(term, description);
}

async function runSearch(): Promise<void> {
  if (roots.size === 0) {
    setState({ kind: "error", message: "Add at least one log folder before searching." });
    return;
  }
  const rangeError = dateRangeError(fromDateInput.value, toDateInput.value);
  fromDateInput.setCustomValidity(rangeError ?? "");
  toDateInput.setCustomValidity(rangeError ?? "");
  if (rangeError !== null) {
    fromDateInput.reportValidity();
    setState({ kind: "error", message: rangeError });
    return;
  }
  progressBar.style.width = "0%";
  progressValue.value = "0 / 0";
  progressPath.textContent = "";
  setState({ kind: "searching", progress: null });
  const onEvent = new Channel<unknown>();
  onEvent.onmessage = (message: unknown) => {
    try {
      const progress = parseDiscoveryProgress(message);
      state = { kind: "searching", progress };
      renderProgress(progress);
    } catch (error: unknown) {
      setState({
        kind: "error",
        message: reportClientError("search_progress", error),
      });
    }
  };
  try {
    const response = parseSearchResponse(
      await invoke<unknown>("search_rollouts", {
        request: currentRequest(),
        onEvent,
      }),
    );
    setState({ kind: "ready", response });
    renderResponse(response);
  } catch (error: unknown) {
    setState({ kind: "error", message: reportClientError("search_rollouts", error) });
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function reportClientError(context: string, error: unknown): string {
  const message = errorMessage(error);
  void invoke<void>("record_client_error", { context, message }).catch(() => undefined);
  return message;
}

function renderLastExport(): void {
  openLastExportButton.disabled = lastExportPath === null;
  lastExportLabel.textContent =
    lastExportPath === null ? "No previous export on this device." : `Last export: ${lastExportPath}`;
  lastExportLabel.title = lastExportPath ?? "";
}

function restoreLastExport(): void {
  try {
    const storedPath = window.localStorage.getItem(LAST_EXPORT_STORAGE_KEY)?.trim();
    lastExportPath = storedPath ? storedPath : null;
  } catch (error: unknown) {
    reportClientError("restore_last_export", error);
    lastExportPath = null;
  }
  renderLastExport();
}

function rememberExport(outputPath: string): boolean {
  lastExportPath = outputPath;
  renderLastExport();
  try {
    window.localStorage.setItem(LAST_EXPORT_STORAGE_KEY, outputPath);
    return true;
  } catch (error: unknown) {
    reportClientError("remember_export", error);
    return false;
  }
}

function restoreReportHistory(): void {
  try {
    reportHistory = parseReportHistory(
      window.localStorage.getItem(REPORT_HISTORY_STORAGE_KEY),
    );
  } catch (error: unknown) {
    reportClientError("restore_report_history", error);
    reportHistory = {};
  }
}

function rememberGeneratedReport(sourcePath: string, outputPath: string): boolean {
  reportHistory = rememberReportForSource(reportHistory, sourcePath, outputPath);
  renderSelection();
  try {
    window.localStorage.setItem(
      REPORT_HISTORY_STORAGE_KEY,
      JSON.stringify(reportHistory),
    );
    return true;
  } catch (error: unknown) {
    reportClientError("remember_generated_report", error);
    return false;
  }
}

async function openDiagnosticLog(): Promise<void> {
  openDiagnosticLogButton.disabled = true;
  try {
    await invoke<void>("open_diagnostic_log");
    statusDot.className = "ready";
    status.textContent = "Opened the local diagnostic log.";
  } catch (error: unknown) {
    statusDot.className = "error";
    status.textContent = `Unable to open the diagnostic log: ${reportClientError(
      "open_diagnostic_log",
      error,
    )}`;
  } finally {
    openDiagnosticLogButton.disabled = false;
  }
}

async function openReportWindow(outputPath: string): Promise<void> {
  await invoke<void>("open_report_window", { outputPath });
}

async function presentSuccessfulCatalogExport(
  result: ExportResult,
  summary: string,
): Promise<void> {
  const remembered = rememberExport(result.outputPath);
  try {
    await openReportWindow(result.outputPath);
    statusDot.className = "ready";
    status.textContent = `${summary} Opened it in a new window.${
      remembered ? "" : " The export location could not be remembered."
    }`;
  } catch (error: unknown) {
    statusDot.className = "error";
    status.textContent = `${summary} The file was saved, but its window could not be opened: ${reportClientError("open_export", error)}`;
  }
}

async function openLastExport(): Promise<void> {
  if (lastExportPath === null) {
    return;
  }
  const outputPath = lastExportPath;
  openLastExportButton.disabled = true;
  status.textContent = `Opening ${outputPath}…`;
  try {
    await openReportWindow(outputPath);
    statusDot.className = "ready";
    status.textContent = `Opened ${outputPath} in a new window.`;
  } catch (error: unknown) {
    statusDot.className = "error";
    status.textContent = `Unable to open the last export: ${reportClientError("open_last_export", error)}`;
  } finally {
    openLastExportButton.disabled = false;
  }
}

async function openRememberedReport(
  outputPath: string,
  reportLink: HTMLButtonElement,
): Promise<void> {
  reportLink.disabled = true;
  status.textContent = `Opening ${outputPath}…`;
  try {
    await openReportWindow(outputPath);
    statusDot.className = "ready";
    status.textContent = `Opened ${outputPath} in a new window.`;
  } catch (error: unknown) {
    statusDot.className = "error";
    status.textContent = `Unable to open this run's last report: ${reportClientError("open_remembered_report", error)}`;
  } finally {
    reportLink.disabled = false;
  }
}

async function addRoot(): Promise<void> {
  try {
    const selected = await open({ directory: true, multiple: true, title: "Choose Codex log folders" });
    const paths = typeof selected === "string" ? [selected] : selected;
    if (Array.isArray(paths)) {
      for (const path of paths) {
        roots.add(path);
      }
      renderRoots();
    }
  } catch (error: unknown) {
    setState({ kind: "error", message: reportClientError("select_log_folders", error) });
  }
}

async function exportCatalog(): Promise<void> {
  const outputPath = await save({
    title: "Export run index",
    defaultPath: rememberedOutputPath(lastExportPath, "agent-report-index.html"),
    filters: [{ name: "HTML report", extensions: ["html"] }],
  });
  if (outputPath === null) {
    return;
  }
  try {
    const result = parseExportResult(
      await invoke<unknown>("export_catalog", {
        request: { search: currentRequest(), outputPath },
      }),
    );
    setState({ kind: "ready", response: state.kind === "ready" ? state.response : { entries, stats: emptyStats() } });
    await presentSuccessfulCatalogExport(
      result,
      `Exported ${result.entryCount.toLocaleString()} runs to ${result.outputPath}.`,
    );
  } catch (error: unknown) {
    setState({ kind: "error", message: reportClientError("export_catalog", error) });
  }
}

function emptyStats(): SearchResponse["stats"] {
  return {
    candidate_files: 0,
    scanned_files: 0,
    cached_files: 0,
    unstable_files: 0,
    unreadable_files: 0,
    elapsed_ms: 0,
    workers: 0,
  };
}

async function generateReport(): Promise<void> {
  const selected = entries.find((entry) => entry.threadId === selectedThreadId);
  if (selected === undefined || selected.parentThreadId !== "") {
    return;
  }
  const outputPath = await save({
    title: "Generate full agent report",
    defaultPath: rememberedOutputPath(
      reportHistory[selected.sourcePath] ?? lastExportPath,
      buildReportFilename(selected.taskTitle, selected.threadId),
    ),
    filters: [{ name: "HTML report", extensions: ["html"] }],
  });
  if (outputPath === null) {
    return;
  }
  generateButton.disabled = true;
  status.textContent = "Generating the full offline report…";
  try {
    const result = parseExportResult(
      await invoke<unknown>("generate_report", {
        request: {
          threadId: selected.threadId,
          roots: [...roots],
          outputPath,
          includeDelegations: true,
        },
      }),
    );
    const remembered = rememberGeneratedReport(selected.sourcePath, result.outputPath);
    const summary = `Generated full report at ${result.outputPath}.`;
    try {
      await openReportWindow(result.outputPath);
      statusDot.className = "ready";
      status.textContent = `${summary} Opened it in a new window.${
        remembered ? "" : " The per-log report location could not be remembered."
      }`;
    } catch (error: unknown) {
      statusDot.className = "error";
      status.textContent = `${summary} The file was saved, but its window could not be opened: ${reportClientError("open_generated_report", error)}`;
    }
  } catch (error: unknown) {
    setState({ kind: "error", message: reportClientError("generate_report", error) });
  } finally {
    generateButton.disabled = false;
  }
}

async function initialize(): Promise<void> {
  restoreLastExport();
  restoreReportHistory();
  try {
    const defaults = parseDesktopDefaults(await invoke<unknown>("desktop_defaults"));
    for (const root of defaults.roots) {
      roots.add(root);
    }
    indexPath = defaults.indexPath;
    diagnosticLogLabel.textContent = defaults.diagnosticLogPath;
    diagnosticLogLabel.title = defaults.diagnosticLogPath;
    openDiagnosticLogButton.disabled = false;
    renderRoots();
    setState({ kind: "idle" });
  } catch (error: unknown) {
    renderRoots();
    setState({ kind: "error", message: reportClientError("initialize", error) });
  }
}

addRootButton.addEventListener("click", () => void addRoot());
searchButton.addEventListener("click", () => void runSearch());
exportButton.addEventListener("click", () => void exportCatalog());
openLastExportButton.addEventListener("click", () => void openLastExport());
openDiagnosticLogButton.addEventListener("click", () => void openDiagnosticLog());
generateButton.addEventListener("click", () => void generateReport());
for (const input of [queryInput, fromDateInput, toDateInput]) {
  input.addEventListener("keydown", (event: KeyboardEvent) => {
    if (event.key === "Enter") {
      void runSearch();
    }
  });
}
for (const input of [fromDateInput, toDateInput]) {
  input.addEventListener("input", () => {
    const rangeError = dateRangeError(fromDateInput.value, toDateInput.value);
    fromDateInput.setCustomValidity(rangeError ?? "");
    toDateInput.setCustomValidity(rangeError ?? "");
  });
}
resultsViewport.addEventListener("scroll", renderVirtualRows, { passive: true });
window.addEventListener("resize", renderVirtualRows, { passive: true });
window.addEventListener("error", (event: ErrorEvent) => {
  reportClientError("window_error", event.error ?? event.message);
});
window.addEventListener("unhandledrejection", (event: PromiseRejectionEvent) => {
  reportClientError("unhandled_rejection", event.reason);
});

void initialize();
