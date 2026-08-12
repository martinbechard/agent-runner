// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Present and control one privacy-bounded Dynamic Workspace snapshot.
// Design: docs/design/components/CD-005-agent-report-dynamic-workspace.md

import {
  type AgentFiltersDto,
  type AgentSortDto,
  type CoordinationFiltersDto,
  type CoordinationSortDto,
  type CursorPageDto,
  type EventDetailDto,
  type EventFiltersDto,
  type EventSortDto,
  type ExportMode,
  type ExportSnapshotResultDto,
  type HeatmapGroupBy,
  type HeatmapRequestedResolutionMinutes,
  type HeatmapResultDto,
  type PreflightReportDto,
  type ReportErrorDto,
  type ReportOperationName,
  type ReportSummaryDto,
  type SequenceFiltersDto,
  type SequenceSortDto,
  type SnapshotMetadataDto,
  type SummaryMetricGroupId,
  type TurnFiltersDto,
  type TurnSortDto,
  parseAgentPageDto,
  parseCoordinationPageDto,
  parseCloseSnapshotResultDto,
  parseEventDetailDto,
  parseEventPageDto,
  parseExportSnapshotResultDto,
  parseHeatmapResultDto,
  parsePreflightReportDto,
  parseReportErrorDto,
  parseReportSummaryDto,
  parseRefreshSnapshotResultDto,
  parseSequencePageDto,
  parseSnapshotMetadataDto,
  parseTurnPageDto,
  parseWorkspaceProgressDto,
} from "./contracts";

export const DEFAULT_PAGE_SIZE = 100;
export const MAX_PAGE_SIZE = 500;
export const MAX_CURSOR_HISTORY = 100;
export const MAX_HEATMAP_CELLS = 2_000;
export const MAX_HEATMAP_ROWS = 200;
export const DEFAULT_ROW_HEIGHT_PX = 44;
export const DEFAULT_OVERSCAN_ROWS = 8;

export type WorkspaceSurfaceId =
  | "summary"
  | "coordination"
  | "heatmap"
  | "timeline"
  | "sequence"
  | "agents"
  | "turns"
  | "tools"
  | "model"
  | "context"
  | "inference"
  | "runtime-waits"
  | "work-items-claims"
  | "detail"
  | "provenance"
  | "diagnostics";

export type WorkspaceLifecycle =
  | "no-selection"
  | "selected"
  | "preflighting"
  | "awaiting-confirmation"
  | "opening"
  | "ready"
  | "querying"
  | "refreshing"
  | "exporting"
  | "cancelling"
  | "failed"
  | "closed";

export type WorkspaceRoute =
  | { readonly kind: "catalog" }
  | { readonly kind: "preflight"; readonly rootThreadId: string }
  | {
      readonly kind: "snapshot";
      readonly snapshotId: string;
      readonly surface: WorkspaceSurfaceId;
    };

export type LoadState<T> =
  | { readonly kind: "not-requested" }
  | { readonly kind: "loading"; readonly previous: T | null; readonly operationId: string }
  | { readonly kind: "ready"; readonly value: T }
  | { readonly kind: "empty"; readonly value: T }
  | { readonly kind: "stale"; readonly value: T; readonly reason: string }
  | { readonly kind: "error"; readonly previous: T | null; readonly error: ReportErrorDto }
  | { readonly kind: "cancelled"; readonly previous: T | null; readonly operationId: string };

export interface WorkspaceSelection {
  readonly rootThreadId: string;
  readonly title: string;
  readonly includeChildren: boolean;
  readonly includeCollaborators: boolean;
}

export interface CursorPagerState<T, F, S> {
  readonly pageSize: number;
  readonly currentCursor: string | null;
  readonly previousCursors: readonly (string | null)[];
  readonly nextCursor: string | null;
  readonly page: LoadState<CursorPageDto<T, F, S>>;
  readonly virtualWindow: VirtualWindow;
}

export interface VirtualWindow {
  readonly startIndex: number;
  readonly endIndexExclusive: number;
  readonly offsetTopPx: number;
  readonly totalHeightPx: number;
}

export interface WorkspaceElements {
  readonly catalogRegion: HTMLElement;
  readonly workspaceRegion: HTMLElement;
  readonly preflightDialog: HTMLDialogElement;
  readonly navigation: HTMLElement;
  readonly viewHeading: HTMLElement;
  readonly viewRegion: HTMLElement;
  readonly statusRegion: HTMLElement;
  readonly progressRegion: HTMLElement;
  readonly detailDialog: HTMLDialogElement;
}

export const WORKSPACE_COMMANDS = {
  preflightReport: "preflight_report",
  openSnapshot: "open_snapshot",
  getSummary: "get_summary",
  listAgents: "list_agents",
  listTurns: "list_turns",
  listEvents: "list_events",
  queryTimeRange: "query_time_range",
  querySequence: "query_sequence",
  queryCoordination: "query_coordination",
  getEventDetails: "get_event_details",
  refreshSnapshot: "refresh_snapshot",
  exportSnapshot: "export_snapshot",
  closeSnapshot: "close_snapshot",
  cancelOperation: "cancel_report_operation",
  openSourceLocation: "open_source_location",
  openDiagnosticLog: "open_diagnostic_log",
  reopenExport: "reopen_export",
} as const;

export type WorkspaceCommandName =
  (typeof WORKSPACE_COMMANDS)[keyof typeof WORKSPACE_COMMANDS];
export type WorkspaceOperationName = ReportOperationName;

export interface WorkspaceTransport {
  invoke(command: WorkspaceCommandName, request: unknown): Promise<unknown>;
  subscribeProgress(listener: (value: unknown) => void): () => void;
}

export interface ReportWorkspaceController {
  selectRoot(selection: WorkspaceSelection, trigger: HTMLElement): void;
  updateScope(includeChildren: boolean, includeCollaborators: boolean): void;
  preflight(): Promise<void>;
  openSnapshot(): Promise<void>;
  changeScope(): void;
  cancelActiveOperation(): Promise<void>;
  navigate(surface: WorkspaceSurfaceId, trigger?: HTMLElement): Promise<void>;
  nextPage(): Promise<void>;
  previousPage(): Promise<void>;
  refreshSnapshot(): Promise<void>;
  exportSnapshot(mode?: ExportMode): Promise<void>;
  reopenExport(exportId: string): Promise<void>;
  openDetail(eventId: string, trigger: HTMLElement): Promise<void>;
  closeDetail(): void;
  closeSnapshot(): Promise<void>;
  getState(): Readonly<WorkspaceState>;
  dispose(): void;
}

export interface CreateReportWorkspaceOptions {
  readonly now?: () => number;
  readonly requestAnimationFrame?: (callback: FrameRequestCallback) => number;
  readonly cancelAnimationFrame?: (handle: number) => void;
  readonly resizeObserverFactory?: (callback: ResizeObserverCallback) => ResizeObserver;
}

export interface SequencePresentationState {
  readonly zoomScale: number;
  readonly fitMode: "fit-all" | "fit-width" | "manual";
  readonly collapsedGroupIds: ReadonlySet<string>;
  readonly focusedAgentId: string | null;
  readonly selectedEndpoint: {
    readonly sequenceId: string;
    readonly endpoint: "from" | "to";
  } | null;
}

type PagerName = "agents" | "turns" | "events" | "sequence" | "coordination";
type UnknownPager = CursorPagerState<unknown, unknown, unknown>;

export interface WorkspaceState {
  readonly lifecycle: WorkspaceLifecycle;
  readonly route: WorkspaceRoute;
  readonly selection: WorkspaceSelection | null;
  readonly preflight: LoadState<PreflightReportDto>;
  readonly snapshot: SnapshotMetadataDto | null;
  readonly summary: LoadState<ReportSummaryDto>;
  readonly pagers: Readonly<Record<PagerName, UnknownPager>>;
  readonly timeSeries: LoadState<HeatmapResultDto>;
  readonly detail: LoadState<EventDetailDto>;
  readonly exportState: LoadState<ExportSnapshotResultDto>;
  readonly sequencePresentation: SequencePresentationState;
  readonly activeOperationId: string | null;
  readonly activeOperation: WorkspaceOperationName | null;
  readonly requestSequence: number;
}

interface SurfaceDefinition {
  readonly label: string;
  readonly group: "overview" | "evidence" | "metrics" | "support";
  readonly operation: WorkspaceOperationName | null;
  readonly emptyMessage: string;
  readonly headingId: string;
}

function surface(
  id: WorkspaceSurfaceId,
  label: string,
  group: SurfaceDefinition["group"],
  operation: WorkspaceOperationName | null,
  emptyMessage: string,
): SurfaceDefinition {
  return Object.freeze({
    label,
    group,
    operation,
    emptyMessage,
    headingId: `report-view-heading-${id}`,
  });
}

/** Stable navigation and service-operation binding for every workspace surface. */
export const SURFACE_DEFINITIONS: Readonly<Record<WorkspaceSurfaceId, SurfaceDefinition>> =
  Object.freeze({
    summary: surface("summary", "Summary", "overview", "get_summary", "No summary is available."),
    coordination: surface("coordination", "Coordination", "evidence", "query_coordination", "No coordination evidence matches the active filters."),
    heatmap: surface("heatmap", "Heatmap", "evidence", "query_time_range", "No activity falls within the visible time range."),
    timeline: surface("timeline", "Timeline", "evidence", "list_events", "No timeline events match the active filters."),
    sequence: surface("sequence", "Sequence", "evidence", "query_sequence", "No sequence evidence matches the active filters."),
    agents: surface("agents", "Agents", "evidence", "list_agents", "No agents match the active filters."),
    turns: surface("turns", "Turns", "evidence", "list_turns", "No turns match the active filters."),
    tools: surface("tools", "Tools", "evidence", "list_events", "No tool events match the active filters."),
    model: surface("model", "Model", "metrics", "get_summary", "Model metrics are unavailable."),
    context: surface("context", "Context", "metrics", "get_summary", "Context metrics are unavailable."),
    inference: surface("inference", "Inference", "metrics", "get_summary", "Inference metrics are unavailable."),
    "runtime-waits": surface("runtime-waits", "Runtime and waits", "metrics", "get_summary", "Runtime and wait metrics are unavailable."),
    "work-items-claims": surface("work-items-claims", "Work items and claims", "metrics", "get_summary", "Work-item and claim metrics are unavailable."),
    detail: surface("detail", "Event detail", "evidence", "get_event_details", "Event detail is unavailable."),
    provenance: surface("provenance", "Provenance", "support", "get_summary", "Provenance is unavailable."),
    diagnostics: surface("diagnostics", "Diagnostics", "support", null, "No diagnostic state is available."),
  });

const NAVIGATION_SURFACES = (Object.keys(SURFACE_DEFINITIONS) as WorkspaceSurfaceId[]).filter(
  (id) => id !== "detail",
);

const AGENT_FILTERS: AgentFiltersDto = Object.freeze({ query: "", state: null });
const AGENT_SORT: AgentSortDto = Object.freeze({ key: "last_activity_at", direction: "descending", tieBreakKey: "agent_id", tieBreakDirection: "ascending" });
const TURN_FILTERS: TurnFiltersDto = Object.freeze({ agentId: null, state: null });
const TURN_SORT: TurnSortDto = Object.freeze({ key: "started_at", direction: "ascending", tieBreakKey: "turn_id", tieBreakDirection: "ascending" });
const EVENT_FILTERS: EventFiltersDto = Object.freeze({ agentId: null, turnId: null, kind: null, fromTime: null, toTime: null });
const EVENT_SORT: EventSortDto = Object.freeze({ key: "occurred_at", direction: "ascending", tieBreakKey: "event_id", tieBreakDirection: "ascending" });
const SEQUENCE_FILTERS: SequenceFiltersDto = Object.freeze({ focusAgentId: null, eventKinds: Object.freeze([]), grouping: "none", includeReasoning: false });
const SEQUENCE_SORT: SequenceSortDto = Object.freeze({ key: "occurred_at", direction: "ascending", tieBreakKey: "sequence_id", tieBreakDirection: "ascending" });
const COORDINATION_FILTERS: CoordinationFiltersDto = Object.freeze({ workItemId: null, delegatedRootId: null, agentId: null, operation: null, evidence: null });
const COORDINATION_SORT: CoordinationSortDto = Object.freeze({ key: "occurred_at", direction: "ascending", tieBreakKey: "coordination_id", tieBreakDirection: "ascending" });

const EMPTY_WINDOW: VirtualWindow = Object.freeze({ startIndex: 0, endIndexExclusive: 0, offsetTopPx: 0, totalHeightPx: 0 });

function createPager(pageSize = DEFAULT_PAGE_SIZE): UnknownPager {
  return Object.freeze({
    pageSize,
    currentCursor: null,
    previousCursors: Object.freeze([]),
    nextCursor: null,
    page: Object.freeze({ kind: "not-requested" }),
    virtualWindow: EMPTY_WINDOW,
  });
}

function createPagers(): Readonly<Record<PagerName, UnknownPager>> {
  return Object.freeze({ agents: createPager(), turns: createPager(), events: createPager(), sequence: createPager(), coordination: createPager() });
}

function initialState(): WorkspaceState {
  return Object.freeze({
    lifecycle: "no-selection",
    route: Object.freeze({ kind: "catalog" }),
    selection: null,
    preflight: Object.freeze({ kind: "not-requested" }),
    snapshot: null,
    summary: Object.freeze({ kind: "not-requested" }),
    pagers: createPagers(),
    timeSeries: Object.freeze({ kind: "not-requested" }),
    detail: Object.freeze({ kind: "not-requested" }),
    exportState: Object.freeze({ kind: "not-requested" }),
    sequencePresentation: Object.freeze({ zoomScale: 1, fitMode: "fit-all", collapsedGroupIds: new Set<string>(), focusedAgentId: null, selectedEndpoint: null }),
    activeOperationId: null,
    activeOperation: null,
    requestSequence: 0,
  });
}

function finiteOr(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

/** Calculate the bounded current-page render window without changing row data. */
export function computeVirtualWindow(input: {
  readonly itemCount: number;
  readonly rowHeightPx: number;
  readonly scrollTopPx: number;
  readonly viewportHeightPx: number;
  readonly overscanRows: number;
}): VirtualWindow {
  const itemCount = Math.min(MAX_PAGE_SIZE, Math.max(0, Math.floor(finiteOr(input.itemCount, 0))));
  if (itemCount === 0) return { ...EMPTY_WINDOW };
  const rowHeightPx = Math.max(1, finiteOr(input.rowHeightPx, DEFAULT_ROW_HEIGHT_PX));
  const scrollTopPx = Math.max(0, finiteOr(input.scrollTopPx, 0));
  const viewportHeightPx = Math.max(0, finiteOr(input.viewportHeightPx, 0));
  const overscanRows = Math.max(0, Math.floor(finiteOr(input.overscanRows, 0)));
  const firstVisible = Math.min(itemCount, Math.floor(scrollTopPx / rowHeightPx));
  const visibleCount = Math.ceil(viewportHeightPx / rowHeightPx);
  const startIndex = Math.max(0, firstVisible - overscanRows);
  const endIndexExclusive = Math.min(itemCount, firstVisible + visibleCount + overscanRows);
  return { startIndex, endIndexExclusive, offsetTopPx: startIndex * rowHeightPx, totalHeightPx: itemCount * rowHeightPx };
}

/** Format one parser-validated instant in the operator's browser timezone. */
export function formatLocalInstant(isoInstant: string): string {
  const instant = new Date(isoInstant);
  if (isoInstant === "" || Number.isNaN(instant.getTime())) throw new Error("Workspace instant is not a valid ISO instant.");
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(instant);
}

/** Describe server-selected heatmap coarsening while preserving requested resolution. */
export function heatmapResolutionLabel(requestedMinutes: number, actualMinutes: number): string {
  if (!Number.isFinite(requestedMinutes) || requestedMinutes <= 0 || !Number.isFinite(actualMinutes) || actualMinutes <= 0) {
    throw new Error("Heatmap resolutions must be positive finite values.");
  }
  return actualMinutes === requestedMinutes ? "" : `Showing ${actualMinutes}-minute buckets; requested ${requestedMinutes}-minute buckets.`;
}

/** Create one unpredictable operation identity without using process or clock state. */
export function newOperationId(): string {
  let bytes: Uint8Array;
  do {
    bytes = globalThis.crypto.getRandomValues(new Uint8Array(12));
  } while (bytes.every((value) => value === 0));
  return `op_${[...bytes].map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

function valueFrom<T>(loadState: LoadState<T>): T | null {
  switch (loadState.kind) {
    case "ready": case "empty": case "stale": return loadState.value;
    case "loading": case "error": case "cancelled": return loadState.previous;
    case "not-requested": return null;
  }
}

function protocolError(message: string): ReportErrorDto {
  return { code: "REPORT_PROTOCOL_ERROR", message, operationId: null, recoverable: true, currentSourceRevision: null, preflightRequired: false, restartFromFirstPage: false };
}

function safeError(value: unknown): ReportErrorDto {
  try { return parseReportErrorDto(value); }
  catch { return protocolError("The operation result failed boundary validation."); }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function assertNoPathAuthority(value: unknown, location = "request"): void {
  if (typeof value === "string") {
    if (value.startsWith("/") || value.startsWith("\\") || /^[A-Za-z]:[\\/]/u.test(value) || /^file:/iu.test(value)) {
      throw new Error(`${location} contains a path-shaped value`);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoPathAuthority(item, `${location}[${index}]`));
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, item] of Object.entries(value)) {
    if (key.endsWith("Path") || key === "rawRecord" || key === "rawRollout") throw new Error(`${location}.${key} is forbidden`);
    assertNoPathAuthority(item, `${location}.${key}`);
  }
}

function requireOpaqueId(value: string, label: string): string {
  const normalized = value.trim();
  if (normalized === "") throw new Error(`${label} must not be empty.`);
  assertNoPathAuthority(normalized, label);
  return normalized;
}

function loadStateFor<T>(value: T, empty: boolean): LoadState<T> {
  return Object.freeze(empty ? { kind: "empty", value } : { kind: "ready", value });
}

function replacePager(pagers: WorkspaceState["pagers"], name: PagerName, pager: UnknownPager): WorkspaceState["pagers"] {
  return Object.freeze({ ...pagers, [name]: Object.freeze(pager) });
}

function staleLoadState<T>(loadState: LoadState<T>, reason: string): LoadState<T> {
  const value = valueFrom(loadState);
  return value === null ? loadState : Object.freeze({ kind: "stale", value, reason });
}

function clearStaleLoadState<T>(loadState: LoadState<T>, empty: boolean): LoadState<T> {
  return loadState.kind === "stale" ? loadStateFor(loadState.value, empty) : loadState;
}

function clearStalePagers(pagers: WorkspaceState["pagers"]): WorkspaceState["pagers"] {
  let result = pagers;
  for (const name of ["agents", "turns", "events", "sequence", "coordination"] as const) {
    const pager = result[name];
    const page = valueFrom(pager.page);
    result = replacePager(result, name, {
      ...pager,
      page: clearStaleLoadState(pager.page, page?.items.length === 0),
    });
  }
  return result;
}

function metricGroupsFor(surfaceId: WorkspaceSurfaceId): readonly SummaryMetricGroupId[] {
  switch (surfaceId) {
    case "summary": return ["overview"];
    case "model": return ["model"];
    case "context": return ["context"];
    case "inference": return ["inference"];
    case "runtime-waits": return ["runtime", "waits"];
    case "work-items-claims": return ["work_items", "claims"];
    case "provenance": return ["provenance"];
    default: return [];
  }
}

function renderLoadState<T>(host: HTMLElement, loadState: LoadState<T>, renderValue: (value: T) => Node, emptyMessage: string): void {
  const previous = valueFrom(loadState);
  host.replaceChildren();
  if (previous !== null) host.append(renderValue(previous));
  if (loadState.kind === "not-requested") host.append(document.createTextNode(emptyMessage));
  else if (loadState.kind === "loading") {
    host.setAttribute("aria-busy", "true");
    host.append(document.createTextNode("Loading…"));
  } else {
    host.removeAttribute("aria-busy");
    if (loadState.kind === "empty") host.append(document.createTextNode(emptyMessage));
    if (loadState.kind === "stale") host.append(document.createTextNode(` Stale: ${loadState.reason}`));
    if (loadState.kind === "cancelled") host.append(document.createTextNode(" Operation cancelled."));
    if (loadState.kind === "error") {
      const alert = document.createElement("p");
      alert.setAttribute("role", "alert");
      alert.textContent = `${loadState.error.code}: ${loadState.error.message}`;
      host.append(alert);
    }
  }
}

function textElement(tag: keyof HTMLElementTagNameMap, text: string): HTMLElement {
  const element = document.createElement(tag);
  element.textContent = text;
  return element;
}

function timeElement(isoInstant: string): HTMLTimeElement {
  const element = document.createElement("time");
  element.dateTime = isoInstant;
  element.textContent = formatLocalInstant(isoInstant);
  return element;
}

function renderSummary(summary: ReportSummaryDto, groups: readonly SummaryMetricGroupId[]): Node {
  const article = document.createElement("article");
  article.append(textElement("h3", summary.title));
  if (summary.goal !== null) article.append(textElement("p", summary.goal));
  article.append(textElement("p", `${summary.state} · ${summary.scopeLabel}`));
  const observed = textElement("p", "Observed ");
  observed.append(timeElement(summary.observedAt));
  article.append(observed);
  const selectedGroups = groups.length === 0
    ? summary.metricGroups
    : summary.metricGroups.filter(
        (group: ReportSummaryDto["metricGroups"][number]) => groups.includes(group.groupId),
      );
  if (selectedGroups.length === 0) article.append(textElement("p", "Metrics are unavailable for this view."));
  for (const group of selectedGroups) {
    const section = document.createElement("section");
    section.append(textElement("h4", group.label));
    const list = document.createElement("dl");
    for (const metric of group.metrics) list.append(textElement("dt", metric.label), textElement("dd", `${metric.displayValue} (${metric.evidence})`));
    section.append(list);
    article.append(section);
  }
  for (const warning of summary.warnings) article.append(textElement("p", `Warning ${warning.code}: ${warning.message}`));
  if (groups.length === 0 || groups.includes("overview")) {
    const list = document.createElement("ol");
    for (const activity of summary.recentActivity) {
      const item = document.createElement("li");
      item.append(timeElement(activity.occurredAt), document.createTextNode(` — ${activity.label} (${activity.evidence})`));
      list.append(item);
    }
    article.append(list);
  }
  return article;
}

function rowLabel(value: unknown): string {
  if (!isRecord(value)) return "Row";
  if (typeof value.sequenceId === "string") {
    const from = typeof value.fromAgentLabel === "string"
      ? value.fromAgentLabel
      : typeof value.fromAgentId === "string" ? value.fromAgentId : "unknown source";
    const to = typeof value.toAgentLabel === "string"
      ? value.toAgentLabel
      : typeof value.toAgentId === "string" ? value.toAgentId : "unknown destination";
    const repeated = typeof value.repeatCount === "number" ? `; repeated ${value.repeatCount} times` : "";
    const reasoning = value.reasoningAvailable === true ? "; reasoning available" : "";
    return `${from} to ${to}; ${String(value.kind)}; ${String(value.label)}; ${String(value.evidence)}${repeated}${reasoning}`;
  }
  if (typeof value.coordinationId === "string") {
    const scope = typeof value.workItemId === "string"
      ? `work item ${value.workItemId}`
      : typeof value.delegatedRootId === "string"
        ? `delegated root ${value.delegatedRootId}`
        : "ungrouped";
    return `${scope}; ${String(value.operation)}; ${String(value.label)}; evidence ${String(value.evidence)}`;
  }
  for (const key of ["label", "nickname", "summary", "operation", "state", "kind", "agentId", "turnId", "eventId", "sequenceId", "coordinationId"]) {
    const candidate = value[key];
    if (typeof candidate === "string" && candidate !== "") return candidate;
  }
  return "Row";
}

interface PageRenderActions {
  readonly hasPrevious: boolean;
  readonly hasNext: boolean;
  previous(): void;
  next(): void;
  openDetail(eventId: string, trigger: HTMLElement): void;
}

function renderPage(
  page: CursorPageDto<unknown, unknown, unknown>,
  window: VirtualWindow,
  actions?: PageRenderActions,
): Node {
  const fragment = document.createDocumentFragment();
  if (actions !== undefined) {
    const controls = document.createElement("div");
    controls.className = "workspace-page-actions";
    const previous = document.createElement("button");
    previous.type = "button";
    previous.textContent = "Previous page";
    previous.disabled = !actions.hasPrevious;
    previous.addEventListener("click", actions.previous);
    const next = document.createElement("button");
    next.type = "button";
    next.textContent = "Next page";
    next.disabled = !actions.hasNext;
    next.addEventListener("click", actions.next);
    controls.append(previous, next);
    fragment.append(controls);
  }
  const container = document.createElement("div");
  container.style.height = `${window.totalHeightPx}px`;
  if (page.operation === "query_sequence") container.className = "sequence-ledger";
  const table = document.createElement("table");
  table.className = "workspace-table";
  table.style.transform = `translateY(${window.offsetTopPx}px)`;
  const body = document.createElement("tbody");
  let coordinationSection = "";
  for (const item of page.items.slice(window.startIndex, window.endIndexExclusive)) {
    if (page.operation === "query_coordination" && isRecord(item)) {
      const section = typeof item.workItemId === "string"
        ? `Work item ${item.workItemId}`
        : typeof item.delegatedRootId === "string"
          ? `Delegated root ${item.delegatedRootId}`
          : "Ungrouped coordination";
      if (section !== coordinationSection) {
        coordinationSection = section;
        const headingRow = document.createElement("tr");
        const heading = document.createElement("th");
        heading.scope = "rowgroup";
        heading.textContent = section;
        headingRow.append(heading);
        body.append(headingRow);
      }
    }
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.textContent = rowLabel(item);
    if (actions !== undefined && isRecord(item) && item.hasDetail === true && typeof item.eventId === "string") {
      const detail = document.createElement("button");
      detail.type = "button";
      detail.textContent = "View detail";
      detail.setAttribute("aria-label", `View detail for ${rowLabel(item)}`);
      detail.addEventListener("click", () => actions.openDetail(String(item.eventId), detail));
      cell.append(document.createTextNode(" "), detail);
    }
    row.append(cell);
    body.append(row);
  }
  table.append(body);
  container.append(table);
  const metadata = textElement("p", `Applied filters and stable sort verified for ${page.operation}; ${page.items.length} rows.`);
  metadata.className = "visually-hidden";
  fragment.append(metadata, container);
  return fragment;
}

function renderHeatmap(result: HeatmapResultDto): Node {
  const section = document.createElement("section");
  const resolution = heatmapResolutionLabel(result.requestedResolutionMinutes, result.actualResolutionMinutes);
  if (resolution !== "") section.append(textElement("p", resolution));
  if (result.omittedRowCount > 0) section.append(textElement("p", `Showing ${result.rows.length} rows; ${result.omittedRowCount} lower-activity rows omitted.`));
  const grid = document.createElement("div");
  grid.className = "heatmap-grid";
  grid.setAttribute("role", "grid");
  for (const row of result.rows) {
    const rowElement = document.createElement("div");
    rowElement.setAttribute("role", "row");
    rowElement.setAttribute("aria-label", `${row.label}; ${row.scale.colorSemantic}`);
    for (const cell of row.cells) {
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "gridcell");
      button.textContent = `${cell.primaryLabel}${cell.secondaryLabel === null ? "" : `; ${cell.secondaryLabel}`} (${cell.evidence}, count ${cell.count})`;
      button.setAttribute("aria-label", `${row.label}; ${cell.startTime} to ${cell.endTime}; ${button.textContent}`);
      rowElement.append(button);
    }
    grid.append(rowElement);
  }
  section.append(grid);
  return section;
}

function renderDetail(detail: EventDetailDto): Node {
  const article = document.createElement("article");
  article.append(textElement("h3", detail.title), timeElement(detail.occurredAt));
  if (detail.summary !== null) article.append(textElement("p", detail.summary));
  for (const disclosure of detail.disclosures) {
    const details = document.createElement("details");
    const label = disclosure.redacted ? `${disclosure.label} — redacted` : disclosure.label;
    details.append(textElement("summary", label), textElement("pre", disclosure.content));
    article.append(details);
  }
  return article;
}

function assertElements(elements: WorkspaceElements): void {
  for (const [name, element] of Object.entries(elements)) {
    if (typeof element !== "object" || element === null || typeof element.addEventListener !== "function" || typeof element.replaceChildren !== "function") {
      throw new Error(`Missing Dynamic Workspace element ${name}.`);
    }
  }
}

/** Construct one controller over an injected native-command transport. */
export function createReportWorkspace(elements: WorkspaceElements, transport: WorkspaceTransport, options: CreateReportWorkspaceOptions = {}): ReportWorkspaceController {
  assertElements(elements);
  let state = initialState();
  let disposed = false;
  let cancelRequestedFor: string | null = null;
  let selectionTrigger: HTMLElement | null = null;
  let detailTrigger: HTMLElement | null = null;
  let frameHandle: number | null = null;
  const requestFrame = options.requestAnimationFrame ?? window.requestAnimationFrame.bind(window);
  const cancelFrame = options.cancelAnimationFrame ?? window.cancelAnimationFrame.bind(window);

  function commit(patch: Partial<WorkspaceState>): void {
    if (disposed) return;
    state = Object.freeze({ ...state, ...patch });
    scheduleRender();
  }

  function scheduleRender(): void {
    if (disposed || frameHandle !== null) return;
    frameHandle = requestFrame(() => {
      frameHandle = null;
      if (!disposed) render();
    });
  }

  function nextOperation(operation: WorkspaceOperationName): { id: string; sequence: number } {
    const sequence = state.requestSequence + 1;
    const id = newOperationId();
    cancelRequestedFor = null;
    commit({ requestSequence: sequence, activeOperationId: id, activeOperation: operation });
    return { id, sequence };
  }

  function isCurrent(sequence: number, operationId: string): boolean {
    return !disposed && state.requestSequence === sequence && state.activeOperationId === operationId;
  }

  function fail(sequence: number, operationId: string, target: "preflight" | "summary" | "timeSeries" | "detail" | "exportState" | PagerName, value: unknown, lifecycle: WorkspaceLifecycle): void {
    if (!isCurrent(sequence, operationId)) return;
    const error = safeError(value);
    if (target in state.pagers) {
      const name = target as PagerName;
      const pager = state.pagers[name];
      const previous = valueFrom(pager.page);
      commit({
        lifecycle,
        activeOperationId: null,
        activeOperation: null,
        pagers: replacePager(state.pagers, name, {
          ...pager,
          nextCursor: error.restartFromFirstPage ? null : pager.nextCursor,
          page: error.code === "REPORT_CANCELLED"
            ? Object.freeze({ kind: "cancelled", previous, operationId })
            : Object.freeze({ kind: "error", previous, error }),
        }),
      });
      return;
    }
    const dataTarget = target as Exclude<typeof target, PagerName>;
    const previous = valueFrom(state[dataTarget] as LoadState<unknown>);
    commit({
      lifecycle,
      activeOperationId: null,
      activeOperation: null,
      [dataTarget]: error.code === "REPORT_CANCELLED"
        ? Object.freeze({ kind: "cancelled", previous, operationId })
        : Object.freeze({ kind: "error", previous, error }),
    } as Partial<WorkspaceState>);
  }

  async function invoke(command: WorkspaceCommandName, request: unknown): Promise<unknown> {
    assertNoPathAuthority(request);
    return transport.invoke(command, request);
  }

  function showModal(dialog: HTMLDialogElement): void {
    if (!dialog.open) dialog.showModal();
    dialog.querySelector<HTMLElement>("h1, h2, h3, [data-dialog-heading]")?.focus();
  }

  function closeModal(dialog: HTMLDialogElement, trigger: HTMLElement | null): void {
    if (dialog.open) dialog.close();
    if (trigger?.isConnected) trigger.focus();
    else if (state.route.kind === "snapshot") elements.viewHeading.focus();
  }

  function resetForSelection(selection: WorkspaceSelection): void {
    const normalized: WorkspaceSelection = Object.freeze({
      rootThreadId: requireOpaqueId(selection.rootThreadId, "rootThreadId"),
      title: selection.title.trim() || "Untitled run",
      includeChildren: false,
      includeCollaborators: false,
    });
    state = Object.freeze({ ...initialState(), lifecycle: "selected", route: Object.freeze({ kind: "preflight", rootThreadId: normalized.rootThreadId }), selection: normalized, requestSequence: state.requestSequence + 1 });
    scheduleRender();
  }

  async function loadSummary(focusHeading: boolean): Promise<void> {
    const snapshot = state.snapshot;
    if (snapshot === null) return;
    const existing = valueFrom(state.summary);
    if (existing?.snapshotId === snapshot.snapshotId && existing.revision === snapshot.revision) {
      if (focusHeading) elements.viewHeading.focus();
      return;
    }
    const operation = nextOperation("get_summary");
    commit({ lifecycle: "querying", summary: Object.freeze({ kind: "loading", previous: existing, operationId: operation.id }) });
    try {
      const result = parseReportSummaryDto(await invoke(WORKSPACE_COMMANDS.getSummary, { operationId: operation.id, snapshotId: snapshot.snapshotId }));
      if (!isCurrent(operation.sequence, operation.id)) return;
      if (result.snapshotId !== snapshot.snapshotId || result.revision !== snapshot.revision) throw new Error("Summary identity does not match the current snapshot.");
      commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null, summary: loadStateFor(result, false) });
      if (focusHeading) elements.viewHeading.focus();
    } catch (error) { fail(operation.sequence, operation.id, "summary", error, "ready"); }
  }

  function pagerForSurface(surfaceId: WorkspaceSurfaceId): PagerName | null {
    if (surfaceId === "agents") return "agents";
    if (surfaceId === "turns") return "turns";
    if (surfaceId === "timeline" || surfaceId === "tools") return "events";
    if (surfaceId === "sequence") return "sequence";
    if (surfaceId === "coordination" || surfaceId === "work-items-claims") return "coordination";
    return null;
  }

  async function loadPage(name: PagerName, cursor: string | null, previousCursors: readonly (string | null)[]): Promise<void> {
    const snapshot = state.snapshot;
    if (snapshot === null) return;
    const pager = state.pagers[name];
    if (!Number.isSafeInteger(pager.pageSize) || pager.pageSize < 1 || pager.pageSize > MAX_PAGE_SIZE) throw new Error(`Page size must be between 1 and ${MAX_PAGE_SIZE}.`);
    const command = name === "agents" ? WORKSPACE_COMMANDS.listAgents : name === "turns" ? WORKSPACE_COMMANDS.listTurns : name === "events" ? WORKSPACE_COMMANDS.listEvents : name === "sequence" ? WORKSPACE_COMMANDS.querySequence : WORKSPACE_COMMANDS.queryCoordination;
    const operation = nextOperation(command);
    const previousPage = valueFrom(pager.page);
    commit({ lifecycle: "querying", pagers: replacePager(state.pagers, name, { ...pager, currentCursor: cursor, previousCursors, page: Object.freeze({ kind: "loading", previous: previousPage, operationId: operation.id }) }) });
    const eventFilters: EventFiltersDto = state.route.kind === "snapshot" && state.route.surface === "tools" ? Object.freeze({ ...EVENT_FILTERS, kind: "tool" }) : EVENT_FILTERS;
    const binding = name === "agents" ? { filters: AGENT_FILTERS, sort: AGENT_SORT } : name === "turns" ? { filters: TURN_FILTERS, sort: TURN_SORT } : name === "events" ? { filters: eventFilters, sort: EVENT_SORT } : name === "sequence" ? { filters: SEQUENCE_FILTERS, sort: SEQUENCE_SORT } : { filters: COORDINATION_FILTERS, sort: COORDINATION_SORT };
    try {
      const raw = await invoke(command, { operationId: operation.id, snapshotId: snapshot.snapshotId, cursor, pageSize: pager.pageSize, filters: binding.filters, sort: binding.sort });
      let parsed: CursorPageDto<unknown, unknown, unknown>;
      if (name === "agents") parsed = parseAgentPageDto(raw, { snapshotId: snapshot.snapshotId, revision: snapshot.revision, operation: "list_agents", filters: AGENT_FILTERS, sort: AGENT_SORT });
      else if (name === "turns") parsed = parseTurnPageDto(raw, { snapshotId: snapshot.snapshotId, revision: snapshot.revision, operation: "list_turns", filters: TURN_FILTERS, sort: TURN_SORT });
      else if (name === "events") parsed = parseEventPageDto(raw, { snapshotId: snapshot.snapshotId, revision: snapshot.revision, operation: "list_events", filters: eventFilters, sort: EVENT_SORT });
      else if (name === "sequence") parsed = parseSequencePageDto(raw, { snapshotId: snapshot.snapshotId, revision: snapshot.revision, operation: "query_sequence", filters: SEQUENCE_FILTERS, sort: SEQUENCE_SORT }).page;
      else parsed = parseCoordinationPageDto(raw, { snapshotId: snapshot.snapshotId, revision: snapshot.revision, operation: "query_coordination", filters: COORDINATION_FILTERS, sort: COORDINATION_SORT });
      if (!isCurrent(operation.sequence, operation.id)) return;
      const virtualWindow = computeVirtualWindow({ itemCount: parsed.items.length, rowHeightPx: DEFAULT_ROW_HEIGHT_PX, scrollTopPx: elements.viewRegion.scrollTop, viewportHeightPx: elements.viewRegion.clientHeight, overscanRows: DEFAULT_OVERSCAN_ROWS });
      commit({
        lifecycle: "ready", activeOperationId: null, activeOperation: null,
        pagers: replacePager(state.pagers, name, { pageSize: pager.pageSize, currentCursor: cursor, previousCursors: Object.freeze([...previousCursors]), nextCursor: parsed.nextCursor, page: loadStateFor(parsed, parsed.items.length === 0), virtualWindow }),
      });
    } catch (error) { fail(operation.sequence, operation.id, name, error, "ready"); }
  }

  async function loadHeatmap(): Promise<void> {
    const snapshot = state.snapshot;
    const summary = valueFrom(state.summary);
    if (snapshot === null || summary === null) return;
    const requestBinding = { snapshotId: snapshot.snapshotId, fromTime: summary.timeRange.fromTime, toTime: summary.timeRange.toTime, measure: "wall_time" as const, groupBy: "agent" as HeatmapGroupBy, requestedResolutionMinutes: 5 as HeatmapRequestedResolutionMinutes, maximumRows: 100 };
    const previous = valueFrom(state.timeSeries);
    if (previous?.revision === snapshot.revision && previous.fromTime === requestBinding.fromTime && previous.toTime === requestBinding.toTime && previous.measure === requestBinding.measure && previous.groupBy === requestBinding.groupBy && previous.requestedResolutionMinutes === requestBinding.requestedResolutionMinutes && previous.maximumRows === requestBinding.maximumRows) return;
    const operation = nextOperation("query_time_range");
    commit({ lifecycle: "querying", timeSeries: Object.freeze({ kind: "loading", previous, operationId: operation.id }) });
    try {
      const result = parseHeatmapResultDto(await invoke(WORKSPACE_COMMANDS.queryTimeRange, { operationId: operation.id, ...requestBinding }), { ...requestBinding, revision: snapshot.revision });
      if (!isCurrent(operation.sequence, operation.id)) return;
      commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null, timeSeries: loadStateFor(result, result.rows.length === 0) });
    } catch (error) { fail(operation.sequence, operation.id, "timeSeries", error, "ready"); }
  }

  async function loadSurface(surfaceId: WorkspaceSurfaceId, focusHeading: boolean): Promise<void> {
    const summaryGroups = metricGroupsFor(surfaceId);
    if (surfaceId === "summary" || summaryGroups.length > 0) {
      await loadSummary(focusHeading);
      if (surfaceId === "work-items-claims") await loadPage("coordination", null, []);
      return;
    }
    if (surfaceId === "heatmap") { await loadSummary(false); await loadHeatmap(); }
    else {
      const pagerName = pagerForSurface(surfaceId);
      if (pagerName !== null) await loadPage(pagerName, state.pagers[pagerName].currentCursor, state.pagers[pagerName].previousCursors);
    }
    if (focusHeading) elements.viewHeading.focus();
  }

  function renderNavigation(): void {
    elements.navigation.replaceChildren();
    elements.navigation.setAttribute("aria-label", "Report views");
    const active = state.route.kind === "snapshot" ? state.route.surface : null;
    for (const surfaceId of NAVIGATION_SURFACES) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.surface = surfaceId;
      button.textContent = SURFACE_DEFINITIONS[surfaceId].label;
      button.tabIndex = surfaceId === active || (active === null && surfaceId === "summary") ? 0 : -1;
      button.setAttribute("aria-current", surfaceId === active ? "page" : "false");
      button.addEventListener("click", () => void controller.navigate(surfaceId, button));
      elements.navigation.append(button);
    }
  }

  function pageActions(pager: UnknownPager): PageRenderActions {
    return {
      hasPrevious: pager.previousCursors.length > 0,
      hasNext: pager.nextCursor !== null,
      previous: () => { void controller.previousPage(); },
      next: () => { void controller.nextPage(); },
      openDetail: (eventId, trigger) => { void controller.openDetail(eventId, trigger); },
    };
  }

  function render(): void {
    const route = state.route;
    const inWorkspace = route.kind === "snapshot";
    elements.catalogRegion.hidden = inWorkspace;
    elements.workspaceRegion.hidden = !inWorkspace;
    elements.statusRegion.setAttribute("role", "status");
    const busy = state.activeOperationId !== null;
    elements.progressRegion.setAttribute("aria-busy", String(busy));
    elements.progressRegion.hidden = !busy;
    if (busy) {
      elements.progressRegion.setAttribute("role", "status");
      elements.progressRegion.removeAttribute("aria-valuemin");
      elements.progressRegion.removeAttribute("aria-valuenow");
      elements.progressRegion.removeAttribute("aria-valuemax");
      elements.progressRegion.removeAttribute("aria-label");
      elements.progressRegion.textContent = `Working: ${state.activeOperation?.replaceAll("_", " ") ?? "report operation"}.`;
    } else {
      elements.progressRegion.removeAttribute("aria-valuemin");
      elements.progressRegion.removeAttribute("aria-valuenow");
      elements.progressRegion.removeAttribute("aria-valuemax");
      elements.progressRegion.removeAttribute("aria-label");
    }
    renderNavigation();
    if (!inWorkspace) {
      elements.statusRegion.textContent = state.lifecycle === "no-selection" ? "Select a run to review." : "Review the selected report scope.";
      return;
    }
    if (route.kind !== "snapshot") return;
    const definition = SURFACE_DEFINITIONS[route.surface];
    elements.viewHeading.id = definition.headingId;
    elements.viewHeading.textContent = definition.label;
    elements.viewHeading.tabIndex = -1;
    if (route.surface === "work-items-claims") {
      const metricsHost = document.createElement("section");
      const evidenceHost = document.createElement("section");
      renderLoadState(
        metricsHost,
        state.summary,
        (value) => renderSummary(value, metricGroupsFor(route.surface)),
        definition.emptyMessage,
      );
      renderLoadState(
        evidenceHost,
        state.pagers.coordination.page,
        (page) => renderPage(
          page,
          state.pagers.coordination.virtualWindow,
          pageActions(state.pagers.coordination),
        ),
        "No matching work-item or claim evidence is available.",
      );
      elements.viewRegion.replaceChildren(metricsHost, evidenceHost);
    } else if (metricGroupsFor(route.surface).length > 0 || route.surface === "summary") {
      renderLoadState(elements.viewRegion, state.summary, (value) => renderSummary(value, metricGroupsFor(route.surface)), definition.emptyMessage);
    } else if (route.surface === "heatmap") renderLoadState(elements.viewRegion, state.timeSeries, renderHeatmap, definition.emptyMessage);
    else {
      const pagerName = pagerForSurface(route.surface);
      if (route.surface === "diagnostics") {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Open diagnostic log";
        button.addEventListener("click", () => {
          void invoke(WORKSPACE_COMMANDS.openDiagnosticLog, {})
            .then(() => { elements.statusRegion.textContent = "Opened the current diagnostic log."; })
            .catch(() => { elements.statusRegion.textContent = "The diagnostic log is unavailable."; });
        });
        elements.viewRegion.replaceChildren(button);
      } else if (pagerName === null) elements.viewRegion.replaceChildren(textElement("p", definition.emptyMessage));
      else renderLoadState(
        elements.viewRegion,
        state.pagers[pagerName].page,
        (page) => renderPage(
          page,
          state.pagers[pagerName].virtualWindow,
          pageActions(state.pagers[pagerName]),
        ),
        definition.emptyMessage,
      );
    }
    elements.statusRegion.textContent = busy ? `Loading ${definition.label}.` : `${definition.label} ready.`;
  }

  function onNavigationKeydown(event: KeyboardEvent): void {
    const buttons = [...elements.navigation.querySelectorAll<HTMLButtonElement>("button[data-surface]")];
    if (buttons.length === 0 || !(event.target instanceof HTMLButtonElement)) return;
    const index = buttons.indexOf(event.target);
    if (index < 0) return;
    let targetIndex: number | null = null;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") targetIndex = (index + 1) % buttons.length;
    if (event.key === "ArrowUp" || event.key === "ArrowLeft") targetIndex = (index - 1 + buttons.length) % buttons.length;
    if (event.key === "Home") targetIndex = 0;
    if (event.key === "End") targetIndex = buttons.length - 1;
    if (targetIndex !== null) {
      event.preventDefault();
      buttons.forEach((button, buttonIndex) => { button.tabIndex = buttonIndex === targetIndex ? 0 : -1; });
      buttons[targetIndex]?.focus();
    }
  }

  function updateVirtualWindow(): void {
    if (state.route.kind !== "snapshot") return;
    const pagerName = pagerForSurface(state.route.surface);
    if (pagerName === null) return;
    const pager = state.pagers[pagerName];
    const page = valueFrom(pager.page);
    if (page === null) return;
    commit({ pagers: replacePager(state.pagers, pagerName, { ...pager, virtualWindow: computeVirtualWindow({ itemCount: page.items.length, rowHeightPx: DEFAULT_ROW_HEIGHT_PX, scrollTopPx: elements.viewRegion.scrollTop, viewportHeightPx: elements.viewRegion.clientHeight, overscanRows: DEFAULT_OVERSCAN_ROWS }) }) });
  }

  const controller: ReportWorkspaceController = {
    selectRoot(selection, trigger) {
      if (disposed) return;
      selectionTrigger = trigger;
      resetForSelection(selection);
    },
    updateScope(includeChildren, includeCollaborators) {
      if (disposed || state.selection === null) return;
      commit({ lifecycle: "selected", selection: Object.freeze({ ...state.selection, includeChildren, includeCollaborators }), preflight: Object.freeze({ kind: "not-requested" }), snapshot: null, summary: Object.freeze({ kind: "not-requested" }), pagers: createPagers(), timeSeries: Object.freeze({ kind: "not-requested" }), detail: Object.freeze({ kind: "not-requested" }) });
    },
    async preflight() {
      const selection = state.selection;
      if (disposed || selection === null) return;
      const operation = nextOperation("preflight_report");
      commit({ lifecycle: "preflighting", preflight: Object.freeze({ kind: "loading", previous: null, operationId: operation.id }) });
      try {
        const result = parsePreflightReportDto(await invoke(WORKSPACE_COMMANDS.preflightReport, { operationId: operation.id, rootThreadId: selection.rootThreadId, includeChildren: selection.includeChildren, includeCollaborators: selection.includeCollaborators }));
        if (!isCurrent(operation.sequence, operation.id)) return;
        if (result.rootThreadId !== selection.rootThreadId || result.includeChildren !== selection.includeChildren || result.includeCollaborators !== selection.includeCollaborators) throw new Error("Preflight scope does not match the selected scope.");
        commit({ lifecycle: "awaiting-confirmation", activeOperationId: null, activeOperation: null, preflight: loadStateFor(result, false) });
        const summaryHost = elements.preflightDialog.querySelector<HTMLElement>(
          "#report-preflight-summary, [data-preflight-summary]",
        );
        if (summaryHost !== null) {
          summaryHost.replaceChildren(
            textElement("p", `${result.logCount} logs; ${result.totalBytes} bytes; ${result.knownEventCount ?? "unknown"} known events.`),
            textElement("p", `${result.childCount} children; ${result.collaboratorCount} collaborators; ${result.changedFileCount} changed files; ${result.cachedFileCount} cached files.`),
            ...result.warnings.map((warning) => textElement("p", `Warning ${warning.code}: ${warning.message}`)),
          );
        }
        const continueButton = elements.preflightDialog.querySelector<HTMLButtonElement>(
          "#report-preflight-continue, [data-preflight-continue]",
        );
        if (continueButton !== null) continueButton.disabled = false;
        showModal(elements.preflightDialog);
      } catch (error) {
        fail(operation.sequence, operation.id, "preflight", error, "selected");
        const summaryHost = elements.preflightDialog.querySelector<HTMLElement>(
          "#report-preflight-summary, [data-preflight-summary]",
        );
        if (summaryHost !== null) {
          const alert = textElement("p", safeError(error).message);
          alert.setAttribute("role", "alert");
          summaryHost.replaceChildren(alert);
        }
        const continueButton = elements.preflightDialog.querySelector<HTMLButtonElement>(
          "#report-preflight-continue, [data-preflight-continue]",
        );
        if (continueButton !== null) continueButton.disabled = true;
        showModal(elements.preflightDialog);
      }
    },
    async openSnapshot() {
      const preflight = valueFrom(state.preflight);
      if (disposed || preflight === null || state.lifecycle !== "awaiting-confirmation") return;
      closeModal(elements.preflightDialog, null);
      const operation = nextOperation("open_snapshot");
      commit({ lifecycle: "opening" });
      try {
        const snapshot = parseSnapshotMetadataDto(await invoke(WORKSPACE_COMMANDS.openSnapshot, {
          operationId: operation.id,
          rootThreadId: preflight.rootThreadId,
          includeChildren: preflight.includeChildren,
          includeCollaborators: preflight.includeCollaborators,
          preflightToken: preflight.preflightToken,
          sourceRevision: preflight.sourceRevision,
        }));
        if (!isCurrent(operation.sequence, operation.id)) return;
        if (snapshot.rootThreadId !== preflight.rootThreadId || snapshot.includeChildren !== preflight.includeChildren || snapshot.includeCollaborators !== preflight.includeCollaborators || snapshot.sourceRevision !== preflight.sourceRevision) throw new Error("Snapshot scope does not match the accepted preflight.");
        commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null, snapshot, preflight: Object.freeze({ kind: "not-requested" }), route: Object.freeze({ kind: "snapshot", snapshotId: snapshot.snapshotId, surface: "summary" }) });
        await loadSummary(true);
      } catch (error) {
        if (!isCurrent(operation.sequence, operation.id)) return;
        commit({ lifecycle: "selected", activeOperationId: null, activeOperation: null, snapshot: null, preflight: Object.freeze({ kind: "error", previous: preflight, error: safeError(error) }) });
        const summaryHost = elements.preflightDialog.querySelector<HTMLElement>(
          "#report-preflight-summary, [data-preflight-summary]",
        );
        if (summaryHost !== null) {
          const alert = textElement("p", safeError(error).message);
          alert.setAttribute("role", "alert");
          summaryHost.replaceChildren(alert);
        }
        const continueButton = elements.preflightDialog.querySelector<HTMLButtonElement>(
          "#report-preflight-continue, [data-preflight-continue]",
        );
        if (continueButton !== null) continueButton.disabled = true;
        showModal(elements.preflightDialog);
      }
    },
    changeScope() {
      if (disposed || state.selection === null) return;
      closeModal(elements.preflightDialog, selectionTrigger);
      commit({ lifecycle: "selected", preflight: Object.freeze({ kind: "not-requested" }) });
    },
    async cancelActiveOperation() {
      const operationId = state.activeOperationId;
      if (disposed || operationId === null || cancelRequestedFor === operationId) return;
      cancelRequestedFor = operationId;
      commit({ lifecycle: "cancelling" });
      try { await invoke(WORKSPACE_COMMANDS.cancelOperation, { operationId }); }
      catch (error) {
        if (state.activeOperationId === operationId) {
          commit({ lifecycle: "ready" });
          elements.statusRegion.textContent = safeError(error).message;
        }
      }
    },
    async navigate(surfaceId, trigger) {
      if (disposed || state.snapshot === null || !(surfaceId in SURFACE_DEFINITIONS) || surfaceId === "detail") return;
      commit({ route: Object.freeze({ kind: "snapshot", snapshotId: state.snapshot.snapshotId, surface: surfaceId }) });
      await loadSurface(surfaceId, trigger !== undefined);
    },
    async nextPage() {
      if (disposed || state.route.kind !== "snapshot") return;
      const name = pagerForSurface(state.route.surface);
      if (name === null) return;
      const pager = state.pagers[name];
      if (pager.nextCursor === null) return;
      await loadPage(name, pager.nextCursor, [...pager.previousCursors, pager.currentCursor].slice(-MAX_CURSOR_HISTORY));
    },
    async previousPage() {
      if (disposed || state.route.kind !== "snapshot") return;
      const name = pagerForSurface(state.route.surface);
      if (name === null) return;
      const pager = state.pagers[name];
      if (pager.previousCursors.length === 0) return;
      const history = [...pager.previousCursors];
      const cursor = history.pop() ?? null;
      await loadPage(name, cursor, history);
    },
    async refreshSnapshot() {
      const snapshot = state.snapshot;
      if (disposed || snapshot === null || snapshot.mode !== "live" || state.activeOperationId !== null) return;
      const operation = nextOperation("refresh_snapshot");
      commit({ lifecycle: "refreshing" });
      try {
        const refreshResult = parseRefreshSnapshotResultDto(await invoke(WORKSPACE_COMMANDS.refreshSnapshot, { operationId: operation.id, snapshotId: snapshot.snapshotId }), snapshot.snapshotId);
        if (!isCurrent(operation.sequence, operation.id)) return;
        const refreshed = refreshResult.snapshot;
        const revisionChanged = refreshed.revision !== snapshot.revision;
        if (refreshResult.changed !== revisionChanged) throw new Error("Refresh change status does not match its snapshot revision.");
        const activeSurface = state.route.kind === "snapshot" ? state.route.surface : "summary";
        commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null, snapshot: refreshed, ...(revisionChanged ? { summary: Object.freeze({ kind: "not-requested" as const }), pagers: createPagers(), timeSeries: Object.freeze({ kind: "not-requested" as const }), detail: Object.freeze({ kind: "not-requested" as const }) } : {
          summary: clearStaleLoadState(state.summary, false),
          pagers: clearStalePagers(state.pagers),
          timeSeries: clearStaleLoadState(state.timeSeries, valueFrom(state.timeSeries)?.rows.length === 0),
          detail: clearStaleLoadState(state.detail, false),
        }) });
        if (revisionChanged) await loadSurface(activeSurface, false);
      } catch (error) {
        if (!isCurrent(operation.sequence, operation.id)) return;
        const reason = safeError(error).message;
        const activeSurface = state.route.kind === "snapshot" ? state.route.surface : "summary";
        const activePager = pagerForSurface(activeSurface);
        commit({
          lifecycle: "ready",
          activeOperationId: null,
          activeOperation: null,
          ...(activeSurface === "heatmap"
            ? { timeSeries: staleLoadState(state.timeSeries, reason) }
            : activePager === null
              ? { summary: staleLoadState(state.summary, reason) }
              : {
                  pagers: replacePager(state.pagers, activePager, {
                    ...state.pagers[activePager],
                    page: staleLoadState(state.pagers[activePager].page, reason),
                  }),
                }),
        });
      }
    },
    async exportSnapshot(mode = "directory") {
      const snapshot = state.snapshot;
      if (disposed || snapshot === null) return;
      if (mode !== "directory" && mode !== "summary") throw new Error("Export mode must be directory or summary.");
      const previous = valueFrom(state.exportState);
      const operation = nextOperation("export_snapshot");
      commit({ lifecycle: "exporting", exportState: Object.freeze({ kind: "loading", previous, operationId: operation.id }) });
      try {
        const raw = await invoke(WORKSPACE_COMMANDS.exportSnapshot, { operationId: operation.id, snapshotId: snapshot.snapshotId, mode });
        if (!isCurrent(operation.sequence, operation.id)) return;
        if (raw === null) {
          commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null, exportState: previous === null ? Object.freeze({ kind: "not-requested" }) : loadStateFor(previous, false) });
          return;
        }
        const result = parseExportSnapshotResultDto(raw, { operationId: operation.id, snapshotId: snapshot.snapshotId, revision: snapshot.revision, mode });
        commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null, exportState: loadStateFor(result, false) });
      } catch (error) { fail(operation.sequence, operation.id, "exportState", error, "ready"); }
    },
    async reopenExport(exportId) {
      if (disposed) return;
      await invoke(WORKSPACE_COMMANDS.reopenExport, { exportId: requireOpaqueId(exportId, "exportId") });
    },
    async openDetail(eventId, trigger) {
      const snapshot = state.snapshot;
      if (disposed || snapshot === null) return;
      const normalizedEventId = requireOpaqueId(eventId, "eventId");
      detailTrigger = trigger;
      const previous = valueFrom(state.detail);
      const operation = nextOperation("get_event_details");
      commit({ lifecycle: "querying", detail: Object.freeze({ kind: "loading", previous, operationId: operation.id }) });
      showModal(elements.detailDialog);
      try {
        const result = parseEventDetailDto(await invoke(WORKSPACE_COMMANDS.getEventDetails, { operationId: operation.id, snapshotId: snapshot.snapshotId, eventId: normalizedEventId }));
        if (!isCurrent(operation.sequence, operation.id)) return;
        if (result.snapshotId !== snapshot.snapshotId || result.revision !== snapshot.revision || result.eventId !== normalizedEventId) throw new Error("Event detail does not match the active selection.");
        commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null, detail: loadStateFor(result, false) });
        const detailContent = renderDetail(result);
        const detailHeading = textElement("h2", "Event detail");
        detailHeading.id = "report-detail-heading";
        detailHeading.dataset.dialogHeading = "";
        detailHeading.tabIndex = -1;
        elements.detailDialog.replaceChildren(detailHeading, detailContent);
        if (result.sourceRef !== null) {
          const sourceButton = document.createElement("button");
          sourceButton.type = "button";
          sourceButton.textContent = "Open source location";
          sourceButton.addEventListener("click", () => {
            void invoke(WORKSPACE_COMMANDS.openSourceLocation, {
              snapshotId: snapshot.snapshotId,
              sourceRef: result.sourceRef,
            }).then(
              () => { elements.statusRegion.textContent = "Opened the authorized source location."; },
              () => { elements.statusRegion.textContent = "The source location is unavailable."; },
            );
          });
          elements.detailDialog.append(sourceButton);
        }
        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.textContent = "Close detail";
        closeButton.addEventListener("click", () => controller.closeDetail());
        elements.detailDialog.append(closeButton);
      } catch (error) { fail(operation.sequence, operation.id, "detail", error, "ready"); }
    },
    closeDetail() {
      if (disposed) return;
      closeModal(elements.detailDialog, detailTrigger);
      detailTrigger = null;
      commit({ detail: Object.freeze({ kind: "not-requested" }) });
    },
    async closeSnapshot() {
      const snapshot = state.snapshot;
      if (disposed || snapshot === null) return;
      const operation = nextOperation("close_snapshot");
      try {
        const result = parseCloseSnapshotResultDto(await invoke(WORKSPACE_COMMANDS.closeSnapshot, { operationId: operation.id, snapshotId: snapshot.snapshotId }), snapshot.snapshotId);
        if (!isCurrent(operation.sequence, operation.id)) return;
        if (!result.closed) throw new Error("The native snapshot remained open.");
        state = Object.freeze({ ...initialState(), lifecycle: "closed", requestSequence: state.requestSequence + 1 });
        scheduleRender();
        if (selectionTrigger?.isConnected) selectionTrigger.focus();
      } catch (error) {
        if (!isCurrent(operation.sequence, operation.id)) return;
        commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null });
        elements.statusRegion.textContent = safeError(error).message;
      }
    },
    getState() { return state; },
    dispose() {
      if (disposed) return;
      disposed = true;
      unsubscribeProgress();
      resizeObserver?.disconnect();
      elements.navigation.removeEventListener("keydown", onNavigationKeydown);
      elements.viewRegion.removeEventListener("scroll", updateVirtualWindow);
      elements.detailDialog.removeEventListener("cancel", onDetailCancel);
      if (frameHandle !== null) cancelFrame(frameHandle);
      frameHandle = null;
      state = Object.freeze({ ...state, lifecycle: "closed", activeOperationId: null, activeOperation: null, requestSequence: state.requestSequence + 1 });
      selectionTrigger = null;
      detailTrigger = null;
    },
  };

  elements.navigation.addEventListener("keydown", onNavigationKeydown);
  elements.viewRegion.addEventListener("scroll", updateVirtualWindow, { passive: true });
  const onDetailCancel = (event: Event): void => { event.preventDefault(); controller.closeDetail(); };
  elements.detailDialog.addEventListener("cancel", onDetailCancel);
  const resizeObserver = options.resizeObserverFactory?.(() => updateVirtualWindow()) ?? (typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => updateVirtualWindow()));
  resizeObserver?.observe(elements.viewRegion);
  const unsubscribeProgress = transport.subscribeProgress((value) => {
    if (disposed || state.activeOperationId === null || state.activeOperation === null) return;
    try {
      const progress = parseWorkspaceProgressDto(value, state.activeOperationId, state.activeOperation);
      elements.progressRegion.hidden = false;
      elements.progressRegion.setAttribute("aria-busy", "true");
      if (progress.total === null) {
        elements.progressRegion.setAttribute("role", "status");
        elements.progressRegion.removeAttribute("aria-valuemin");
        elements.progressRegion.removeAttribute("aria-valuenow");
        elements.progressRegion.removeAttribute("aria-valuemax");
        elements.progressRegion.removeAttribute("aria-label");
        elements.progressRegion.textContent = progress.message;
      } else {
        elements.progressRegion.setAttribute("role", "progressbar");
        elements.progressRegion.setAttribute("aria-valuemin", "0");
        elements.progressRegion.setAttribute("aria-valuenow", String(progress.completed));
        elements.progressRegion.setAttribute("aria-valuemax", String(progress.total));
        elements.progressRegion.setAttribute("aria-label", progress.message);
        elements.progressRegion.textContent = `${progress.message} ${progress.completed} of ${progress.total}.`;
      }
    } catch {
      // A mismatched progress event cannot change active operation or presentation state.
    }
  });
  render();
  return controller;
}
