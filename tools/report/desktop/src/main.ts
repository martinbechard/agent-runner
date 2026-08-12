// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Integrate the bounded catalog and Dynamic Workspace with Tauri.
// Design: docs/design/components/CD-005-agent-report-dynamic-workspace.md

import { Channel, invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import {
  type CatalogEntry,
  type DiscoveryProgress,
  type ExportResult,
  type ProgressPresentation,
  type RootReferenceDto,
  type SearchRequest,
  type SearchResponse,
  dateRangeError,
  discoveryProgressPresentation,
  localDayDateRange,
  localDateHourToUtc,
  localExclusiveDateHourToInclusiveUtcHour,
  normalizeWorkerCount,
  parseDesktopDefaults,
  parseDiscoveryProgress,
  parseExportResult,
  parseRootReferences,
  parseSearchResponse,
} from "./contracts";
import {
  type ReportWorkspaceController,
  type WorkspaceCommandName,
  type WorkspaceElements,
  type WorkspaceTransport,
  createReportWorkspace,
} from "./report-workspace";
import "./styles.css";

type CatalogState =
  | { readonly kind: "idle" }
  | { readonly kind: "searching"; readonly progress: DiscoveryProgress | null }
  | { readonly kind: "ready"; readonly response: SearchResponse }
  | { readonly kind: "error"; readonly message: string };

interface ParentReportRequest {
  readonly threadId: string;
  readonly taskTitle: string;
  readonly sourceRef: string;
  readonly adapter?: "codex";
}

interface RememberedExport {
  readonly exportId: string;
  readonly displayName: string;
}

const ROW_HEIGHT = 118;
const OVERSCAN = 5;
const CATALOG_EXPORT_STORAGE_KEY = "agent-report:last-catalog-export-id:v2";
const WORKER_COUNT_STORAGE_KEY = "agent-report:worker-threads:v1";
const INCLUDE_CHILDREN_STORAGE_KEY = "agent-report:include-children:v1";
const INCLUDE_COLLABORATORS_STORAGE_KEY = "agent-report:include-collaborators:v1";
const DEFAULT_WORKER_COUNT = Math.min(8, Math.max(1, navigator.hardwareConcurrency || 4));

const roots = new Map<string, RootReferenceDto>();
let entries: readonly CatalogEntry[] = [];
let selectedThreadId: string | null = null;
let lastCatalogExport: RememberedExport | null = null;
let catalogState: CatalogState = { kind: "idle" };

function element<T extends HTMLElement>(id: string): T {
  const value = document.getElementById(id);
  if (!(value instanceof HTMLElement)) throw new Error(`Missing desktop interface element #${id}`);
  return value as T;
}

function dialog(id: string): HTMLDialogElement {
  const value = document.getElementById(id);
  if (!(value instanceof HTMLDialogElement)) throw new Error(`Missing desktop dialog #${id}`);
  return value;
}

const catalogRegion = element<HTMLElement>("catalog-workspace");
const workspaceRegion = element<HTMLElement>("report-workspace");
const addRootButton = element<HTMLButtonElement>("add-root");
const rootList = element<HTMLDivElement>("root-list");
const queryInput = element<HTMLInputElement>("query");
const fromDateInput = element<HTMLInputElement>("from-date");
const toDateInput = element<HTMLInputElement>("to-date");
const includeDescendantsInput = element<HTMLInputElement>("include-descendants");
const includeCollaboratorsInput = element<HTMLInputElement>("include-collaborators");
const workerThreadsInput = element<HTMLInputElement>("worker-threads");
const searchButton = element<HTMLButtonElement>("search");
const exportButton = element<HTMLButtonElement>("export-catalog");
const openLastExportButton = element<HTMLButtonElement>("open-last-export");
const lastExportLabel = element<HTMLParagraphElement>("last-export-label");
const openDiagnosticLogButton = element<HTMLButtonElement>("open-diagnostic-log");
const diagnosticLogLabel = element<HTMLParagraphElement>("diagnostic-log-label");
const reviewScopeButton = element<HTMLButtonElement>("review-scope");
const resultCount = element<HTMLParagraphElement>("result-count");
const statsPanel = element<HTMLDivElement>("stats");
const progressPanel = element<HTMLDivElement>("progress-panel");
const progressLabel = element<HTMLSpanElement>("progress-label");
const progressValue = element<HTMLOutputElement>("progress-value");
const progressBar = element<HTMLElement>("progress-bar");
const progressSource = element<HTMLParagraphElement>("progress-source");
const resultsViewport = element<HTMLDivElement>("results-viewport");
const resultsCanvas = element<HTMLDivElement>("results-canvas");
const emptyState = element<HTMLDivElement>("empty-state");
const detailTitle = element<HTMLHeadingElement>("detail-title");
const detailFields = element<HTMLDListElement>("detail-fields");
const status = element<HTMLParagraphElement>("status");
const statusDot = element<HTMLSpanElement>("status-dot");
const signalRail = element<HTMLDivElement>("signal-rail");
const workspaceTitle = element<HTMLHeadingElement>("report-workspace-title");
const workspaceObservation = element<HTMLParagraphElement>("report-workspace-observation");
const workspaceScope = element<HTMLParagraphElement>("report-scope-summary");
const workspaceCancel = element<HTMLButtonElement>("report-cancel");

const workspaceElements: WorkspaceElements = {
  catalogRegion,
  workspaceRegion,
  preflightDialog: dialog("report-preflight-dialog"),
  navigation: element<HTMLElement>("report-workspace-nav"),
  viewHeading: element<HTMLElement>("report-view-heading"),
  viewRegion: element<HTMLElement>("report-view"),
  statusRegion: element<HTMLElement>("report-view-status"),
  progressRegion: element<HTMLElement>("report-progress"),
  detailDialog: dialog("report-detail-dialog"),
};

class TauriWorkspaceTransport implements WorkspaceTransport {
  invoke(command: WorkspaceCommandName, request: unknown): Promise<unknown> {
    return invoke<unknown>(command, { request });
  }

  subscribeProgress(listener: (value: unknown) => void): () => void {
    let disposed = false;
    let unlisten: UnlistenFn | null = null;
    void listen<unknown>("report-operation-progress", (event) => {
      if (!disposed) listener(event.payload);
    }).then((registered) => {
      if (disposed) registered();
      else unlisten = registered;
    }).catch((error: unknown) => {
      if (!disposed) reportClientError("subscribe_report_progress", error);
    });
    return () => {
      disposed = true;
      unlisten?.();
      unlisten = null;
    };
  }
}

const workspace: ReportWorkspaceController = createReportWorkspace(
  workspaceElements,
  new TauriWorkspaceTransport(),
);

function selectedWorkerCount(): number {
  return normalizeWorkerCount(workerThreadsInput.value, DEFAULT_WORKER_COUNT);
}

function currentRequest(): SearchRequest {
  return {
    rootRefs: [...roots.keys()],
    query: queryInput.value.trim(),
    fromDate: localDateHourToUtc(fromDateInput.value),
    toDate: localExclusiveDateHourToInclusiveUtcHour(toDateInput.value),
    includeDescendants: includeDescendantsInput.checked,
    workers: selectedWorkerCount(),
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
  for (const root of roots.values()) {
    const row = document.createElement("div");
    row.className = "root-chip";
    const label = document.createElement("span");
    label.textContent = root.displayName;
    label.title = root.displayName;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `Remove ${root.displayName}`);
    remove.addEventListener("click", () => {
      roots.delete(root.rootRef);
      renderRoots();
    });
    row.append(label, remove);
    rootList.append(row);
  }
}

function setCatalogState(nextState: CatalogState): void {
  catalogState = nextState;
  const busy = nextState.kind === "searching";
  searchButton.disabled = busy;
  addRootButton.disabled = busy;
  reviewScopeButton.disabled = busy || !entries.some((entry) => entry.threadId === selectedThreadId);
  progressPanel.hidden = !busy;
  progressPanel.setAttribute("aria-busy", String(busy));
  signalRail.classList.toggle("is-live", busy);
  statusDot.className = busy ? "searching" : nextState.kind;
  if (nextState.kind === "idle") status.textContent = "Waiting for a search.";
  else if (nextState.kind === "searching") status.textContent = "Reading changed logs and reusing stable index rows.";
  else if (nextState.kind === "ready") status.textContent = `Index ready in ${formatDuration(nextState.response.stats.elapsed_ms)}.`;
  else status.textContent = nextState.message;
}

function renderProgress(progress: ProgressPresentation): void {
  progressLabel.textContent = progress.label;
  progressValue.value = progress.value;
  progressSource.textContent = progress.sourceLabel;
  const total = Math.max(1, progress.total ?? 1);
  const completed = Math.min(progress.completed ?? 0, total);
  progressBar.style.width = `${((completed / total) * 100).toFixed(1)}%`;
  progressPanel.setAttribute("aria-valuenow", String(progress.completed ?? 0));
  progressPanel.setAttribute("aria-valuemax", String(progress.total ?? 1));
}

function formatDuration(milliseconds: number): string {
  return milliseconds < 1_000 ? `${Math.round(milliseconds)} ms` : `${(milliseconds / 1_000).toFixed(2)} s`;
}

function formatTimestamp(timestamp: string): string {
  const instant = new Date(timestamp);
  return Number.isNaN(instant.getTime())
    ? "Time unavailable"
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(instant);
}

function renderWorkspaceObservation(): void {
  const snapshot = workspace.getState().snapshot;
  if (snapshot !== null) workspaceObservation.textContent = `${snapshot.mode === "live" ? "Live" : "Sealed"}; observed ${formatTimestamp(snapshot.observationTime)}.`;
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

function renderResponse(response: SearchResponse): void {
  entries = response.entries;
  if (selectedThreadId !== null && !entries.some((entry) => entry.threadId === selectedThreadId)) selectedThreadId = null;
  resultCount.textContent = `${entries.length.toLocaleString()} runs from ${response.stats.candidate_files.toLocaleString()} files`;
  statsPanel.replaceChildren(stat(`${response.stats.scanned_files}`, "read"), stat(`${response.stats.cached_files}`, "reused"), stat(`${response.stats.workers}`, "workers"));
  exportButton.disabled = false;
  emptyState.hidden = entries.length > 0;
  renderVirtualRows();
  renderSelection();
}

function renderVirtualRows(): void {
  resultsCanvas.replaceChildren();
  resultsCanvas.style.height = `${entries.length * ROW_HEIGHT}px`;
  const start = Math.max(0, Math.floor(resultsViewport.scrollTop / ROW_HEIGHT) - OVERSCAN);
  const visibleCount = Math.ceil(resultsViewport.clientHeight / ROW_HEIGHT) + OVERSCAN * 2;
  const end = Math.min(entries.length, start + visibleCount);
  for (let index = start; index < end; index += 1) {
    const entry = entries[index];
    if (entry === undefined) continue;
    const row = document.createElement("button");
    row.type = "button";
    row.className = "run-row";
    row.classList.toggle("is-selected", entry.threadId === selectedThreadId);
    row.style.transform = `translateY(${index * ROW_HEIGHT}px)`;
    row.setAttribute("aria-pressed", String(entry.threadId === selectedThreadId));
    const title = document.createElement("strong");
    title.textContent = entry.taskTitle || "Untitled Codex run";
    const time = document.createElement("time");
    time.textContent = formatTimestamp(entry.lastActivityAt);
    time.dateTime = entry.lastActivityAt;
    const context = document.createElement("span");
    context.className = "row-context";
    context.textContent = entry.workspaceLabel || entry.sourceLabel;
    const id = document.createElement("code");
    id.textContent = entry.threadId;
    row.append(time, title, context, id);
    row.addEventListener("click", () => {
      selectedThreadId = entry.threadId;
      renderVirtualRows();
      renderSelection();
    });
    resultsCanvas.append(row);
  }
}

function addDetail(label: string, value: string): void {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value;
  detailFields.append(term, description);
}

function renderSelection(): void {
  const selected = entries.find((entry) => entry.threadId === selectedThreadId) ?? null;
  detailFields.replaceChildren();
  reviewScopeButton.disabled = catalogState.kind === "searching" || selected === null;
  if (selected === null) {
    detailTitle.textContent = "No run selected";
    return;
  }
  detailTitle.textContent = selected.taskTitle || "Untitled Codex run";
  addDetail("Last activity", formatTimestamp(selected.lastActivityAt));
  addDetail("Started", formatTimestamp(selected.startedAt));
  addDetail("Thread", selected.threadId);
  addDetail("Workspace", selected.workspaceLabel || "Unavailable");
  addDetail("Source", selected.sourceLabel);
  if (selected.agentLabel || selected.agentNickname) addDetail("Agent", selected.agentNickname || selected.agentLabel);
  if (selected.delegationCount > 0) addDetail("Delegations", selected.delegationCount.toLocaleString());
  if (selected.diagnostic !== null) addDetail("Diagnostic", `${selected.diagnostic.code}: ${selected.diagnostic.message}`);
}

async function runSearch(): Promise<void> {
  if (roots.size === 0) {
    setCatalogState({ kind: "error", message: "Add at least one log folder before searching." });
    return;
  }
  const rangeError = dateRangeError(fromDateInput.value, toDateInput.value);
  fromDateInput.setCustomValidity(rangeError ?? "");
  toDateInput.setCustomValidity(rangeError ?? "");
  if (rangeError !== null) {
    fromDateInput.reportValidity();
    setCatalogState({ kind: "error", message: rangeError });
    return;
  }
  renderProgress({ label: "Preparing native index", value: "Starting", sourceLabel: "", completed: 0, total: 1 });
  setCatalogState({ kind: "searching", progress: null });
  const onEvent = new Channel<unknown>();
  onEvent.onmessage = (message: unknown) => {
    try {
      const progress = parseDiscoveryProgress(message);
      catalogState = { kind: "searching", progress };
      renderProgress(discoveryProgressPresentation(progress));
    } catch (error: unknown) {
      setCatalogState({ kind: "error", message: reportClientError("search_progress", error) });
    }
  };
  try {
    const response = parseSearchResponse(await invoke<unknown>("search_rollouts", { request: currentRequest(), onEvent }));
    setCatalogState({ kind: "ready", response });
    renderResponse(response);
  } catch (error: unknown) {
    setCatalogState({ kind: "error", message: reportClientError("search_rollouts", error) });
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function reportClientError(context: string, error: unknown): string {
  const message = errorMessage(error).slice(0, 4_096);
  void invoke<void>("record_client_error", { context, message }).catch(() => undefined);
  return message;
}

function parseRememberedExport(value: string | null): RememberedExport | null {
  if (value === null) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return null;
    const candidate = parsed as Record<string, unknown>;
    if (typeof candidate.exportId !== "string" || candidate.exportId === "" || typeof candidate.displayName !== "string" || candidate.displayName === "") return null;
    return { exportId: candidate.exportId, displayName: candidate.displayName };
  } catch {
    return null;
  }
}

function renderLastExport(): void {
  openLastExportButton.disabled = lastCatalogExport === null;
  lastExportLabel.textContent = lastCatalogExport === null ? "No previous catalog export on this device." : `Last export: ${lastCatalogExport.displayName}`;
}

function restoreLastExport(): void {
  lastCatalogExport = parseRememberedExport(localStorage.getItem(CATALOG_EXPORT_STORAGE_KEY));
  renderLastExport();
}

function rememberExport(result: ExportResult): void {
  lastCatalogExport = { exportId: result.exportId, displayName: result.displayName };
  localStorage.setItem(CATALOG_EXPORT_STORAGE_KEY, JSON.stringify(lastCatalogExport));
  renderLastExport();
}

async function openReportWindow(exportId: string): Promise<void> {
  await invoke<void>("open_report_window", { exportId });
}

async function openLastExport(): Promise<void> {
  if (lastCatalogExport === null) return;
  openLastExportButton.disabled = true;
  try {
    await openReportWindow(lastCatalogExport.exportId);
    statusDot.className = "ready";
    status.textContent = `Opened ${lastCatalogExport.displayName}.`;
  } catch (error: unknown) {
    statusDot.className = "error";
    status.textContent = `Unable to open the last export: ${reportClientError("open_last_export", error)}`;
  } finally {
    openLastExportButton.disabled = false;
  }
}

async function addRoot(): Promise<void> {
  try {
    const selected = parseRootReferences(await invoke<unknown>("add_root"));
    for (const root of selected) roots.set(root.rootRef, root);
    renderRoots();
  } catch (error: unknown) {
    setCatalogState({ kind: "error", message: reportClientError("add_root", error) });
  }
}

async function exportCatalog(): Promise<void> {
  try {
    const raw = await invoke<unknown>("export_catalog", { request: { search: currentRequest() } });
    if (raw === null) return;
    const result = parseExportResult(raw);
    rememberExport(result);
    await openReportWindow(result.exportId);
    statusDot.className = "ready";
    status.textContent = `Exported ${result.entryCount.toLocaleString()} runs to ${result.displayName}.`;
  } catch (error: unknown) {
    setCatalogState({ kind: "error", message: reportClientError("export_catalog", error) });
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
    status.textContent = `Unable to open the diagnostic log: ${reportClientError("open_diagnostic_log", error)}`;
  } finally {
    openDiagnosticLogButton.disabled = false;
  }
}

function applyWorkspaceScope(): void {
  workspace.updateScope(includeDescendantsInput.checked, includeCollaboratorsInput.checked);
  workspaceScope.textContent = `Root${includeDescendantsInput.checked ? ", children" : " only"}${includeCollaboratorsInput.checked ? ", and collaborators" : ""}.`;
}

async function reviewSelectedScope(trigger = reviewScopeButton): Promise<void> {
  const selected = entries.find((entry) => entry.threadId === selectedThreadId);
  if (selected === undefined) return;
  workspaceTitle.textContent = selected.taskTitle || "Untitled Codex run";
  workspaceObservation.textContent = "Snapshot not opened.";
  workspace.selectRoot({ rootThreadId: selected.threadId, title: selected.taskTitle, includeChildren: false, includeCollaborators: false }, trigger);
  applyWorkspaceScope();
  await workspace.preflight();
}

async function handleParentReport(request: ParentReportRequest): Promise<void> {
  const threadId = typeof request.threadId === "string" ? request.threadId.trim() : "";
  if (threadId === "") return;
  const selected = entries.find((entry) => entry.threadId === threadId);
  if (selected !== undefined) {
    selectedThreadId = threadId;
    renderVirtualRows();
    renderSelection();
    await reviewSelectedScope(reviewScopeButton);
    return;
  }
  if (typeof request.sourceRef !== "string" || request.sourceRef.trim() === "") return;
  const synthetic: CatalogEntry = {
    threadId,
    parentThreadId: "",
    taskTitle: request.taskTitle || "Parent task",
    startedAt: new Date(0).toISOString(),
    lastActivityAt: new Date(0).toISOString(),
    workspaceLabel: "",
    sourceRef: request.sourceRef,
    sourceLabel: "Parent source",
    agentLabel: "",
    agentNickname: "",
    delegationCount: 0,
    diagnostic: null,
  };
  entries = [...entries, synthetic];
  selectedThreadId = threadId;
  renderVirtualRows();
  renderSelection();
  await reviewSelectedScope(reviewScopeButton);
}

async function initialize(): Promise<void> {
  restoreLastExport();
  const localToday = localDayDateRange(new Date());
  fromDateInput.value = localToday.fromDate;
  toDateInput.value = localToday.toDate;
  workerThreadsInput.value = String(normalizeWorkerCount(localStorage.getItem(WORKER_COUNT_STORAGE_KEY), DEFAULT_WORKER_COUNT));
  includeDescendantsInput.checked = localStorage.getItem(INCLUDE_CHILDREN_STORAGE_KEY) === "true";
  includeCollaboratorsInput.checked = localStorage.getItem(INCLUDE_COLLABORATORS_STORAGE_KEY) === "true";
  try {
    await listen<ParentReportRequest>("view-parent-report", (event) => void handleParentReport(event.payload));
  } catch (error: unknown) {
    reportClientError("listen_view_parent_report", error);
  }
  try {
    const defaults = parseDesktopDefaults(await invoke<unknown>("desktop_defaults"));
    for (const root of defaults.roots) roots.set(root.rootRef, root);
    openDiagnosticLogButton.disabled = !defaults.diagnosticsAvailable;
    diagnosticLogLabel.textContent = defaults.diagnosticsAvailable ? "Diagnostic log available." : "Diagnostic log unavailable.";
    renderRoots();
    setCatalogState({ kind: "idle" });
  } catch (error: unknown) {
    renderRoots();
    setCatalogState({ kind: "error", message: reportClientError("initialize", error) });
  }
}

addRootButton.addEventListener("click", () => void addRoot());
searchButton.addEventListener("click", () => void runSearch());
exportButton.addEventListener("click", () => void exportCatalog());
openLastExportButton.addEventListener("click", () => void openLastExport());
openDiagnosticLogButton.addEventListener("click", () => void openDiagnosticLog());
reviewScopeButton.addEventListener("click", () => void reviewSelectedScope());
element<HTMLButtonElement>("report-preflight-continue").addEventListener("click", () => void workspace.openSnapshot().then(() => {
  renderWorkspaceObservation();
}));
element<HTMLButtonElement>("report-preflight-change").addEventListener("click", () => workspace.changeScope());
element<HTMLButtonElement>("report-preflight-cancel").addEventListener("click", () => workspace.changeScope());
workspaceElements.preflightDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  workspace.changeScope();
});
element<HTMLButtonElement>("report-refresh").addEventListener("click", () => void workspace.refreshSnapshot().then(() => {
  renderWorkspaceObservation();
}));
element<HTMLButtonElement>("report-export-directory").addEventListener("click", () => void workspace.exportSnapshot());
element<HTMLButtonElement>("report-export-summary").addEventListener("click", () => void workspace.exportSnapshot("summary"));
element<HTMLButtonElement>("report-open-diagnostics").addEventListener("click", () => void openDiagnosticLog());
element<HTMLButtonElement>("report-close").addEventListener("click", () => void workspace.closeSnapshot());
workspaceCancel.addEventListener("click", () => void workspace.cancelActiveOperation());
workerThreadsInput.addEventListener("change", () => {
  const workers = selectedWorkerCount();
  workerThreadsInput.value = String(workers);
  localStorage.setItem(WORKER_COUNT_STORAGE_KEY, String(workers));
});
includeDescendantsInput.addEventListener("change", () => {
  localStorage.setItem(INCLUDE_CHILDREN_STORAGE_KEY, String(includeDescendantsInput.checked));
  applyWorkspaceScope();
});
includeCollaboratorsInput.addEventListener("change", () => {
  localStorage.setItem(INCLUDE_COLLABORATORS_STORAGE_KEY, String(includeCollaboratorsInput.checked));
  applyWorkspaceScope();
});
for (const input of [queryInput, fromDateInput, toDateInput]) input.addEventListener("keydown", (event) => {
  if (event.key === "Enter") void runSearch();
});
for (const input of [fromDateInput, toDateInput]) input.addEventListener("input", () => {
  const rangeError = dateRangeError(fromDateInput.value, toDateInput.value);
  fromDateInput.setCustomValidity(rangeError ?? "");
  toDateInput.setCustomValidity(rangeError ?? "");
});
resultsViewport.addEventListener("scroll", renderVirtualRows, { passive: true });
window.addEventListener("resize", renderVirtualRows, { passive: true });
window.addEventListener("beforeunload", () => workspace.dispose());
window.addEventListener("error", (event) => reportClientError("window_error", event.error ?? event.message));
window.addEventListener("unhandledrejection", (event) => reportClientError("unhandled_rejection", event.reason));

void initialize();
