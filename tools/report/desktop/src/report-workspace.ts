// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Present and control one bounded interactive report snapshot.
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
  type HeatmapCellEvidenceResultDto,
  type HeatmapMatrixCellDto,
  type HeatmapMatrixResultDto,
  type HeatmapMode,
  type HeatmapPeriodHistoryEntry,
  type HeatmapRequestedResolutionMinutes,
  type HeatmapScaleDto,
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
import { createReactHeatmapHost } from "./heatmap/react-heatmap-host";

export const DEFAULT_PAGE_SIZE = 100;
export const MAX_PAGE_SIZE = 500;
export const MAX_CURSOR_HISTORY = 100;
export const MAX_HEATMAP_CELLS = 2_000;
export const MAX_HEATMAP_ROWS = 200;
export const MAX_HEATMAP_EVIDENCE_ITEMS = 100;
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

/** Preserve the current run and relationship choices when preflight returns to editing. */
export function scopeSelectionForEditing(selection: WorkspaceSelection): WorkspaceSelection {
  return Object.freeze({ ...selection });
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
  querySnapshotTimeRange: "query_snapshot_time_range",
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
  changeScope(focusTarget?: HTMLElement): void;
  cancelActiveOperation(): Promise<void>;
  navigate(surface: WorkspaceSurfaceId, trigger?: HTMLElement): Promise<void>;
  nextPage(): Promise<void>;
  previousPage(): Promise<void>;
  selectHeatmapCell(rowId: string, periodStartTime: string, periodEndTime: string): Promise<void>;
  drillDownHeatmap(): Promise<void>;
  stepBackHeatmap(): Promise<void>;
  moveHeatmapPeriod(direction: "previous" | "next"): Promise<void>;
  setHeatmapPeriod(minutes: HeatmapRequestedResolutionMinutes): Promise<void>;
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
  readonly timeSeries: LoadState<HeatmapMatrixResultDto>;
  readonly heatmapInteraction: HeatmapInteractionState;
  readonly detail: LoadState<EventDetailDto>;
  readonly exportState: LoadState<ExportSnapshotResultDto>;
  readonly sequencePresentation: SequencePresentationState;
  readonly activeOperationId: string | null;
  readonly activeOperation: WorkspaceOperationName | null;
  readonly requestSequence: number;
}

export interface HeatmapSelectedCell {
  readonly rowId: string;
  readonly rowKey: string;
  readonly rowOrderIndex: number;
  readonly rowLabel: string;
  readonly periodStartTime: string;
  readonly periodEndTime: string;
  readonly formattedValue: string;
  readonly valueState: HeatmapMatrixCellDto["valueState"];
  readonly applicableZero: boolean;
  readonly scale: HeatmapScaleDto;
  readonly supportingText: string | null;
}

export interface HeatmapInteractionState {
  readonly mode: HeatmapMode;
  readonly visibleFromTime: string;
  readonly visibleToTime: string;
  readonly requestedResolutionMinutes: HeatmapRequestedResolutionMinutes;
  readonly maximumRows: number;
  readonly selectedCell: HeatmapSelectedCell | null;
  readonly history: readonly HeatmapPeriodHistoryEntry[];
  readonly evidence: LoadState<HeatmapCellEvidenceResultDto>;
}

/** Confirm that a lazy evidence result still describes the selected matrix cell. */
export function heatmapEvidenceMatchesSelection(selection: HeatmapSelectedCell, result: HeatmapCellEvidenceResultDto): boolean {
  return selection.rowId === result.rowId
    && selection.rowKey === result.rowKey
    && selection.rowOrderIndex === result.rowOrderIndex
    && selection.rowLabel === result.rowLabel
    && selection.periodStartTime === result.periodStartTime
    && selection.periodEndTime === result.periodEndTime
    && selection.formattedValue === result.formattedValue
    && selection.valueState === result.valueState
    && selection.applicableZero === result.applicableZero;
}

/** Remove a superseded evidence loading shell without pairing it to another cell. */
export function coherentHeatmapInteraction(interaction: HeatmapInteractionState): HeatmapInteractionState {
  if (interaction.evidence.kind !== "loading") return interaction;
  const previous = interaction.evidence.previous;
  return Object.freeze({
    ...interaction,
    evidence: previous === null
      ? Object.freeze({ kind: "not-requested" })
      : loadStateFor(previous, previous.evidenceItems.length === 0),
  });
}

/** Create the next matrix binding while clearing cell-scoped state. */
export function heatmapInteractionForMatrixRequest(
  interaction: HeatmapInteractionState,
  patch: Partial<HeatmapInteractionState>,
): HeatmapInteractionState {
  return Object.freeze({
    ...coherentHeatmapInteraction(interaction),
    ...patch,
    selectedCell: null,
    evidence: Object.freeze({ kind: "not-requested" }),
  });
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
    heatmap: surface("heatmap", "Heatmap", "evidence", "query_snapshot_time_range", "No activity falls within the visible time range."),
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
    heatmapInteraction: initialHeatmapInteraction(),
    detail: Object.freeze({ kind: "not-requested" }),
    exportState: Object.freeze({ kind: "not-requested" }),
    sequencePresentation: Object.freeze({ zoomScale: 1, fitMode: "fit-all", collapsedGroupIds: new Set<string>(), focusedAgentId: null, selectedEndpoint: null }),
    activeOperationId: null,
    activeOperation: null,
    requestSequence: 0,
  });
}

function initialHeatmapInteraction(): HeatmapInteractionState {
  return Object.freeze({
    mode: "wall_time",
    visibleFromTime: "",
    visibleToTime: "",
    requestedResolutionMinutes: 5,
    maximumRows: 100,
    selectedCell: null,
    history: Object.freeze([]),
    evidence: Object.freeze({ kind: "not-requested" }),
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
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(instant);
}

/** Pair the report identity with the snapshot's browser-local observation time. */
export function snapshotTitleAsOf(title: string, observationTime: string): string {
  return `${title.trim() || "Untitled run"} as of ${formatLocalInstant(observationTime)}`;
}

/** Describe server-selected heatmap coarsening while preserving requested resolution. */
export function heatmapResolutionLabel(requestedMinutes: number, actualMinutes: number): string {
  if (!Number.isFinite(requestedMinutes) || requestedMinutes <= 0 || !Number.isFinite(actualMinutes) || actualMinutes <= 0) {
    throw new Error("Heatmap resolutions must be positive finite values.");
  }
  return actualMinutes === requestedMinutes ? "" : `Showing ${actualMinutes}-minute periods; requested ${requestedMinutes}-minute periods.`;
}

export interface HeatmapRange {
  readonly fromTime: string;
  readonly toTime: string;
}

export interface HeatmapCellPresentation {
  readonly tone: "measured" | "derived" | "partial" | "unavailable" | "capacity-unavailable";
  readonly intensity: number | null;
  readonly visibleValue: string;
  readonly explanation: string | null;
}

function heatmapStateText(scale: HeatmapScaleDto, valueState: HeatmapMatrixCellDto["valueState"], formattedValue: string): Pick<HeatmapCellPresentation, "visibleValue" | "explanation"> {
  if (scale.availability === "unavailable") return { visibleValue: "N/A — capacity unavailable", explanation: "Capacity is unavailable. No percentage or color comparison is available." };
  if (valueState === "unavailable") return { visibleValue: "Unavailable", explanation: "No usable data is available for this period." };
  if (valueState === "partial") return { visibleValue: formattedValue, explanation: "Some data for this period is unavailable. The value shown is the available subtotal." };
  return { visibleValue: formattedValue, explanation: null };
}

export const HEATMAP_RESOLUTIONS = Object.freeze([1, 5, 15, 30, 60] as const);
export const HEATMAP_MODES: readonly Readonly<{ value: HeatmapMode; label: string }>[] = Object.freeze([
  Object.freeze({ value: "wall_time", label: "Wall time" }),
  Object.freeze({ value: "tokens", label: "Tokens" }),
  Object.freeze({ value: "models", label: "Models" }),
]);

/** Select the adjacent accepted service resolution for a zoom action. */
export function nextHeatmapResolution(current: HeatmapRequestedResolutionMinutes, direction: "in" | "out"): HeatmapRequestedResolutionMinutes {
  const index = HEATMAP_RESOLUTIONS.indexOf(current);
  if (index < 0) throw new Error("Heatmap resolution is not supported.");
  const nextIndex = Math.max(0, Math.min(HEATMAP_RESOLUTIONS.length - 1, index + (direction === "in" ? -1 : 1)));
  return HEATMAP_RESOLUTIONS[nextIndex] ?? current;
}

/** Present service-owned Heatmap evidence without inventing a value or scale. */
export function heatmapCellPresentation(scale: HeatmapScaleDto, cell: HeatmapMatrixCellDto): HeatmapCellPresentation {
  const text = heatmapStateText(scale, cell.valueState, cell.formattedValue);
  const tone = scale.availability === "unavailable" ? "capacity-unavailable" : cell.valueState;
  return Object.freeze({ tone, intensity: scale.availability === "unavailable" ? null : cell.normalizedIntensity, ...text });
}

/** Create the complete non-color description for one matrix cell. */
export function heatmapCellAccessibleName(
  mode: HeatmapMode,
  rowLabel: string,
  cell: HeatmapMatrixCellDto,
  scale: HeatmapScaleDto,
  selected: boolean,
): string {
  const presentation = heatmapCellPresentation(scale, cell);
  const scaleText = scale.availability === "available"
    ? `scale available, ${scale.basis.replaceAll("_", " ")}`
    : "scale unavailable, capacity unavailable, intensity N/A";
  const zeroText = cell.applicableZero ? "; complete applicable zero" : "";
  const support = cell.supportingText === null ? "" : `; ${cell.supportingText}`;
  const explanation = presentation.explanation === null ? "" : `; ${presentation.explanation}`;
  return `${HEATMAP_MODES.find((item) => item.value === mode)?.label ?? mode}; ${rowLabel}; ${formatLocalInstant(cell.startTime)} to ${formatLocalInstant(cell.endTime)}; ${presentation.visibleValue}; ${cell.valueState}${zeroText}; ${scaleText}${support}${explanation}; ${selected ? "selected" : "not selected"}`;
}

export interface HeatmapGridCoordinate { readonly rowIndex: number; readonly columnIndex: number }

export interface HeatmapPeriodBounds { readonly left: number; readonly width: number }
export interface HeatmapVisiblePeriodWindow { readonly firstIndex: number; readonly lastIndex: number; readonly total: number }

/** Describe the period columns intersecting the non-sticky part of a scrolled grid viewport. */
export function visibleHeatmapPeriodWindow(
  periods: readonly HeatmapPeriodBounds[],
  viewportStart: number,
  viewportEnd: number,
): HeatmapVisiblePeriodWindow | null {
  if (periods.length === 0 || !Number.isFinite(viewportStart) || !Number.isFinite(viewportEnd) || viewportEnd <= viewportStart) return null;
  const visible = periods
    .map((period, index) => ({ ...period, index }))
    .filter((period) => period.width > 0 && period.left < viewportEnd && period.left + period.width > viewportStart);
  if (visible.length === 0) return null;
  return Object.freeze({ firstIndex: visible[0]?.index ?? 0, lastIndex: visible.at(-1)?.index ?? 0, total: periods.length });
}

/** Resolve roving-grid intent without requiring a DOM test environment. */
export function moveHeatmapGridFocus(
  rowLengths: readonly number[],
  current: HeatmapGridCoordinate,
  key: "ArrowLeft" | "ArrowRight" | "ArrowUp" | "ArrowDown" | "Home" | "End",
): HeatmapGridCoordinate {
  if (rowLengths.length === 0 || (rowLengths[current.rowIndex] ?? 0) === 0) return Object.freeze({ ...current });
  let rowIndex = current.rowIndex;
  let columnIndex = current.columnIndex;
  if (key === "ArrowLeft") columnIndex -= 1;
  else if (key === "ArrowRight") columnIndex += 1;
  else if (key === "ArrowUp") rowIndex -= 1;
  else if (key === "ArrowDown") rowIndex += 1;
  else if (key === "Home") columnIndex = 0;
  else columnIndex = (rowLengths[rowIndex] ?? 1) - 1;
  rowIndex = Math.max(0, Math.min(rowLengths.length - 1, rowIndex));
  columnIndex = Math.max(0, Math.min((rowLengths[rowIndex] ?? 1) - 1, columnIndex));
  return Object.freeze({ rowIndex, columnIndex });
}

function safeBoundaryDetail(value: unknown): string | null {
  if (!(value instanceof Error)) return null;
  const detail = value.message.trim();
  if (
    detail === ""
    || detail.length > 512
    || /(?:^|\s)(?:[A-Za-z]:[\\/]|[\\/]|file:)/iu.test(detail)
    || /(?:api[_ -]?key|authorization|bearer|password|private[_ -]?key|secret|ciphertext)/iu.test(detail)
  ) return null;
  return detail;
}

/** Convert a rejected response into safe, actionable report wording. */
export function describeBoundaryError(value: unknown): string {
  const detail = safeBoundaryDetail(value);
  const recovery = "Retry this view. If the problem continues, open Diagnostics.";
  return detail === null ? `The report response was invalid. ${recovery}` : `The report response was invalid: ${detail}. ${recovery}`;
}

export interface ReportErrorRecovery {
  readonly label: "Retry" | "First page" | null;
  readonly message: string;
}

/** Resolve structured recovery flags without weakening service authority. */
export function reportErrorRecovery(error: ReportErrorDto): ReportErrorRecovery {
  if (error.restartFromFirstPage) return Object.freeze({ label: "First page", message: "Return to the first page and try again." });
  if (error.preflightRequired) return Object.freeze({ label: null, message: "Review the report scope again before retrying." });
  if (error.recoverable) return Object.freeze({ label: "Retry", message: "Retry this action. If the problem continues, open Diagnostics." });
  return Object.freeze({ label: null, message: "Open Diagnostics for more information." });
}

/** Describe a bounded opaque export result for the report surface. */
export function describeExportResult(result: Readonly<Pick<ExportSnapshotResultDto, "displayName" | "mode" | "fileCount" | "totalByteCount">>): string {
  const mode = result.mode === "directory" ? "complete directory" : "bounded summary";
  return `${result.displayName} · ${mode} · ${result.fileCount.toLocaleString()} files · ${result.totalByteCount.toLocaleString()} bytes`;
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
  catch { return protocolError(describeBoundaryError(value)); }
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

function renderLoadState<T>(host: HTMLElement, loadState: LoadState<T>, renderValue: (value: T) => Node, emptyMessage: string, retry?: () => void): void {
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
      const alert = document.createElement("div");
      alert.setAttribute("role", "alert");
      alert.className = "report-error";
      alert.dataset.errorCode = loadState.error.code;
      alert.append(textElement("strong", `${loadState.error.code}: ${loadState.error.message}`));
      const recovery = reportErrorRecovery(loadState.error);
      const recoveryMessage = loadState.error.code === "REPORT_PROTOCOL_ERROR" ? null : recovery.message;
      if (recoveryMessage !== null) alert.append(textElement("p", recoveryMessage));
      if (retry !== undefined && recovery.label !== null) {
        const retryButton = textElement("button", recovery.label) as HTMLButtonElement;
        retryButton.type = "button";
        retryButton.addEventListener("click", retry);
        alert.append(retryButton);
      }
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

export interface HeatmapRenderActions {
  select(selection: HeatmapSelectedCell): void;
  drillDown(): void;
  stepBack(): void;
  restoreHistory(index: number): void;
  movePeriod(direction: "previous" | "next"): void;
  setMode(mode: HeatmapMode): void;
  setResolution(resolution: HeatmapRequestedResolutionMinutes): void;
  setMaximumRows(maximumRows: number): void;
  openDetail(eventId: string, trigger: HTMLElement): void;
}

function heatmapRangeLabel(range: HeatmapRange): string {
  return `${formatLocalInstant(range.fromTime)} to ${formatLocalInstant(range.toTime)}`;
}

function heatmapColumnTime(isoInstant: string): string {
  const instant = new Date(isoInstant);
  if (isoInstant === "" || Number.isNaN(instant.getTime())) throw new Error("Workspace instant is not a valid ISO instant.");
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false }).format(instant);
}

function heatmapSequentialColor(intensity: number): string {
  const value = Math.max(0, Math.min(1, intensity));
  const stops = value <= 0.5
    ? { from: [255, 243, 208], to: [245, 154, 58], position: value * 2 }
    : { from: [245, 154, 58], to: [180, 35, 47], position: (value - 0.5) * 2 };
  const channel = (index: number) => Math.round((stops.from[index] ?? 0) + ((stops.to[index] ?? 0) - (stops.from[index] ?? 0)) * stops.position);
  return `rgb(${channel(0)} ${channel(1)} ${channel(2)})`;
}

function heatmapSelectionFor(row: HeatmapMatrixResultDto["rows"][number], cell: HeatmapMatrixCellDto): HeatmapSelectedCell {
  return Object.freeze({
    rowId: row.rowId,
    rowKey: row.rowKey,
    rowOrderIndex: row.rowOrderIndex,
    rowLabel: row.label,
    periodStartTime: cell.startTime,
    periodEndTime: cell.endTime,
    formattedValue: cell.formattedValue,
    valueState: cell.valueState,
    applicableZero: cell.applicableZero,
    scale: row.scale,
    supportingText: cell.supportingText,
  });
}

function renderHeatmapEvidence(
  loadState: LoadState<HeatmapCellEvidenceResultDto>,
  actions: HeatmapRenderActions,
  selectedCell: HeatmapSelectedCell | null,
): Node {
  const host = document.createElement("section");
  host.className = "heatmap-evidence";
  host.setAttribute("aria-label", "Selected cell evidence");
  renderLoadState(host, loadState, (result) => {
    const fragment = document.createDocumentFragment();
    const stateText = selectedCell === null
      ? { visibleValue: result.formattedValue, explanation: null }
      : heatmapStateText(selectedCell.scale, result.valueState, result.formattedValue);
    const explanation = stateText.explanation === null ? "" : ` ${stateText.explanation}`;
    fragment.append(
      textElement("h4", `${result.rowLabel} evidence`),
      textElement("p", `${heatmapRangeLabel({ fromTime: result.periodStartTime, toTime: result.periodEndTime })} · ${stateText.visibleValue} · ${result.valueState}.${explanation}`),
    );
    const table = document.createElement("table");
    table.className = "heatmap-evidence-ledger";
    const body = document.createElement("tbody");
    for (const item of result.evidenceItems) {
      const row = document.createElement("tr");
      const occurred = document.createElement("td");
      occurred.append(timeElement(item.occurredAt));
      row.append(
        occurred,
        textElement("td", `${item.label} · ${item.formattedValue} · ${item.valueState} · ${item.evidenceMethod}${item.durationMs === null ? "" : ` · ${item.durationMs} ms`}${item.preview === null ? "" : ` · ${item.preview}`}`),
      );
      if (item.hasDetail && item.eventId !== null) {
        const action = document.createElement("td");
        const detail = textElement("button", "View detail") as HTMLButtonElement;
        detail.type = "button";
        detail.setAttribute("aria-label", `View detail for ${item.label}`);
        detail.addEventListener("click", () => actions.openDetail(item.eventId ?? "", detail));
        action.append(detail);
        row.append(action);
      }
      body.append(row);
    }
    table.append(body);
    fragment.append(table);
    if (result.omittedEvidenceCount > 0) fragment.append(textElement("p", `${result.omittedEvidenceCount} additional evidence items omitted.`));
    return fragment;
  }, "Select a Heatmap cell to load its evidence.");
  return host;
}

function renderHeatmap(result: HeatmapMatrixResultDto, presentation: HeatmapInteractionState, actions: HeatmapRenderActions): Node {
  return createReactHeatmapHost({ result, presentation, actions });
}

function renderLegacyHeatmap(result: HeatmapMatrixResultDto, presentation: HeatmapInteractionState, actions: HeatmapRenderActions): Node {
  const section = document.createElement("section");
  section.className = "heatmap-panel";

  const controls = document.createElement("div");
  controls.className = "heatmap-controls";
  controls.setAttribute("aria-label", "Heatmap controls");
  const selectedRow = presentation.selectedCell === null ? undefined : result.rows.find((row) => row.rowId === presentation.selectedCell?.rowId);
  const selectedColumn = selectedRow?.cells.findIndex((cell) => cell.startTime === presentation.selectedCell?.periodStartTime && cell.endTime === presentation.selectedCell?.periodEndTime) ?? -1;
  const previous = textElement("button", "‹") as HTMLButtonElement;
  previous.type = "button";
  previous.title = "Previous selected period";
  previous.setAttribute("aria-label", "Previous selected period");
  previous.disabled = selectedColumn <= 0;
  previous.addEventListener("click", () => actions.movePeriod("previous"));
  const next = textElement("button", "›") as HTMLButtonElement;
  next.type = "button";
  next.title = "Next selected period";
  next.setAttribute("aria-label", "Next selected period");
  next.disabled = selectedColumn < 0 || selectedColumn >= (selectedRow?.cells.length ?? 0) - 1;
  next.addEventListener("click", () => actions.movePeriod("next"));
  const drillIn = textElement("button", "Drill down") as HTMLButtonElement;
  drillIn.type = "button";
  drillIn.disabled = presentation.selectedCell === null || presentation.requestedResolutionMinutes === 1;
  drillIn.addEventListener("click", actions.drillDown);
  const stepBack = textElement("button", "Step back") as HTMLButtonElement;
  stepBack.type = "button";
  stepBack.disabled = presentation.history.length === 0;
  stepBack.addEventListener("click", actions.stepBack);
  const scrollLeft = textElement("button", "‹") as HTMLButtonElement;
  scrollLeft.type = "button";
  scrollLeft.title = "Previous visible periods";
  scrollLeft.setAttribute("aria-label", "Previous visible periods");
  scrollLeft.disabled = true;
  scrollLeft.addEventListener("click", () => {
    const grid = section.querySelector<HTMLElement>(".heatmap-grid");
    const stickyWidth = grid?.querySelector<HTMLElement>('.heatmap-time-row [role="columnheader"]:first-child')?.offsetWidth ?? 0;
    grid?.scrollBy({ left: -Math.max(136, grid.clientWidth - stickyWidth) });
  });
  const scrollRight = textElement("button", "›") as HTMLButtonElement;
  scrollRight.type = "button";
  scrollRight.title = "Next visible periods";
  scrollRight.setAttribute("aria-label", "Next visible periods");
  scrollRight.disabled = true;
  scrollRight.addEventListener("click", () => {
    const grid = section.querySelector<HTMLElement>(".heatmap-grid");
    const stickyWidth = grid?.querySelector<HTMLElement>('.heatmap-time-row [role="columnheader"]:first-child')?.offsetWidth ?? 0;
    grid?.scrollBy({ left: Math.max(136, grid.clientWidth - stickyWidth) });
  });
  const visiblePeriods = textElement("span", "Periods —");
  visiblePeriods.className = "heatmap-period-position";
  visiblePeriods.setAttribute("aria-live", "polite");
  const selectionControls = document.createElement("div");
  selectionControls.className = "heatmap-control-group heatmap-selection-controls";
  selectionControls.hidden = presentation.selectedCell === null;
  selectionControls.append(previous, next, drillIn);
  const detailControls = document.createElement("div");
  detailControls.className = "heatmap-control-group heatmap-history-controls";
  detailControls.hidden = presentation.history.length === 0;
  detailControls.append(stepBack);
  const viewportControls = document.createElement("div");
  viewportControls.className = "heatmap-control-group heatmap-viewport-controls";
  viewportControls.hidden = true;
  viewportControls.append(scrollLeft, visiblePeriods, scrollRight);
  controls.append(selectionControls, detailControls, viewportControls);

  const settings = document.createElement("div");
  settings.className = "heatmap-settings";
  const modes = document.createElement("fieldset");
  modes.className = "heatmap-modes";
  modes.append(textElement("legend", "Measure"));
  for (const item of HEATMAP_MODES) {
    const button = textElement("button", item.label) as HTMLButtonElement;
    button.type = "button";
    button.setAttribute("aria-pressed", String(item.value === presentation.mode));
    button.addEventListener("click", () => actions.setMode(item.value));
    modes.append(button);
  }
  settings.append(modes);
  const period = document.createElement("fieldset");
  period.className = "heatmap-granularity";
  period.append(textElement("legend", "Resolution"));
  for (const value of HEATMAP_RESOLUTIONS) {
    const button = textElement("button", `${value} min`) as HTMLButtonElement;
    button.type = "button";
    button.dataset.heatmapMinutes = String(value);
    button.setAttribute("aria-pressed", String(value === presentation.requestedResolutionMinutes));
    button.addEventListener("click", () => actions.setResolution(value));
    period.append(button);
  }
  settings.append(period);
  section.append(settings, controls);

  const breadcrumb = document.createElement("nav");
  breadcrumb.className = "heatmap-breadcrumbs";
  breadcrumb.setAttribute("aria-label", "Heatmap range history");
  presentation.history.forEach((range, index) => {
    const button = textElement("button", index === 0 ? "Initial range" : `Range ${index + 1}`) as HTMLButtonElement;
    button.type = "button";
    button.title = heatmapRangeLabel(range);
    button.addEventListener("click", () => actions.restoreHistory(index));
    breadcrumb.append(button, document.createTextNode(" / "));
  });
  const currentRange = textElement("span", heatmapRangeLabel({ fromTime: presentation.visibleFromTime, toTime: presentation.visibleToTime }));
  currentRange.setAttribute("aria-current", "location");
  breadcrumb.append(currentRange);
  section.append(breadcrumb);

  const resolution = heatmapResolutionLabel(result.requestedResolutionMinutes, result.actualResolutionMinutes);
  const visualLegend = document.createElement("aside");
  visualLegend.className = "heatmap-visual-legend";
  visualLegend.setAttribute("aria-label", "Heatmap visual legend");
  const scaleKey = document.createElement("div");
  scaleKey.className = "heatmap-scale-key";
  scaleKey.setAttribute("aria-label", "Low to high intensity within each row");
  const scaleSwatch = document.createElement("i");
  scaleSwatch.setAttribute("aria-hidden", "true");
  scaleKey.append(textElement("span", "Low"), scaleSwatch, textElement("span", "High per row"));
  const stateKey = document.createElement("div");
  stateKey.className = "heatmap-state-key";
  for (const [className, label] of [["is-partial", "Partial"], ["is-unavailable", "Unavailable"]] as const) {
    const item = document.createElement("span");
    const swatch = document.createElement("i");
    swatch.className = className;
    swatch.setAttribute("aria-hidden", "true");
    item.append(swatch, document.createTextNode(label));
    stateKey.append(item);
  }
  visualLegend.append(scaleKey, stateKey);
  section.append(visualLegend);
  if (resolution !== "") {
    const resolutionNote = textElement("p", resolution);
    resolutionNote.className = "heatmap-resolution-note";
    section.append(resolutionNote);
  }
  if (result.omittedRowCount > 0) section.append(textElement("p", `Showing ${result.rows.length} rows; ${result.omittedRowCount} rows omitted.`));
  const grid = document.createElement("div");
  grid.className = "heatmap-grid";
  grid.setAttribute("role", "grid");
  grid.setAttribute("aria-label", `${HEATMAP_MODES.find((item) => item.value === result.mode)?.label ?? result.mode} Heatmap`);
  const timeRow = document.createElement("div");
  timeRow.className = "heatmap-time-row";
  timeRow.setAttribute("role", "row");
  const corner = textElement("span", "Metric");
  corner.setAttribute("role", "columnheader");
  timeRow.append(corner);
  for (const cell of result.rows[0]?.cells ?? []) {
    const heading = document.createElement("time");
    heading.setAttribute("role", "columnheader");
    heading.dateTime = cell.startTime;
    heading.textContent = heatmapColumnTime(cell.startTime);
    heading.title = `${formatLocalInstant(cell.startTime)} to ${formatLocalInstant(cell.endTime)}`;
    timeRow.append(heading);
  }
  grid.append(timeRow);
  for (const [rowIndex, row] of result.rows.entries()) {
    const rowElement = document.createElement("div");
    rowElement.setAttribute("role", "row");
    rowElement.setAttribute("aria-label", `${row.label}; ${row.scale.availability} scale`);
    const label = textElement("div", row.label);
    label.className = "heatmap-row-label";
    label.setAttribute("role", "rowheader");
    rowElement.append(label);
    for (const [columnIndex, cell] of row.cells.entries()) {
      const selection = heatmapSelectionFor(row, cell);
      const isSelected = presentation.selectedCell?.rowId === selection.rowId && presentation.selectedCell.periodStartTime === selection.periodStartTime;
      const cellPresentation = heatmapCellPresentation(row.scale, cell);
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "gridcell");
      button.className = `heatmap-cell is-${cellPresentation.tone}`;
      button.dataset.rowIndex = String(rowIndex);
      button.dataset.columnIndex = String(columnIndex);
      button.dataset.scaleAvailability = row.scale.availability;
      if (row.scale.availability === "available") button.dataset.scaleBasis = row.scale.basis;
      if (cellPresentation.intensity !== null) {
        button.dataset.intensity = cellPresentation.intensity.toFixed(3);
        button.style.setProperty("--heatmap-color", heatmapSequentialColor(cellPresentation.intensity));
        button.style.setProperty("--heatmap-cell-ink", cellPresentation.intensity >= 0.78 ? "#ffffff" : "var(--ink)");
      }
      button.tabIndex = isSelected || (presentation.selectedCell === null && rowIndex === 0 && columnIndex === 0) ? 0 : -1;
      button.setAttribute("aria-selected", String(isSelected));
      const value = textElement("strong", cellPresentation.visibleValue);
      button.append(value);
      if (cell.supportingText !== null) button.append(textElement("span", cell.supportingText));
      button.setAttribute("aria-label", heatmapCellAccessibleName(result.mode, row.label, cell, row.scale, isSelected));
      button.addEventListener("click", () => actions.select(selection));
      button.addEventListener("dblclick", actions.drillDown);
      button.addEventListener("contextmenu", (event) => { event.preventDefault(); actions.stepBack(); });
      button.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          actions.select(selection);
          return;
        }
        if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const targetCoordinate = moveHeatmapGridFocus(result.rows.map((candidate) => candidate.cells.length), { rowIndex, columnIndex }, event.key as "ArrowLeft" | "ArrowRight" | "ArrowUp" | "ArrowDown" | "Home" | "End");
        const target = [...grid.querySelectorAll<HTMLButtonElement>('[role="gridcell"]')].find(
          (candidate) => candidate.dataset.rowIndex === String(targetCoordinate.rowIndex) && candidate.dataset.columnIndex === String(targetCoordinate.columnIndex),
        );
        if (target !== undefined) {
          grid.querySelectorAll<HTMLButtonElement>('[role="gridcell"]').forEach((candidate) => { candidate.tabIndex = candidate === target ? 0 : -1; });
          target.focus();
        }
      });
      rowElement.append(button);
    }
    grid.append(rowElement);
  }
  const updateVisiblePeriods = () => {
    const headings = [...grid.querySelectorAll<HTMLElement>(".heatmap-time-row time")];
    const stickyWidth = grid.querySelector<HTMLElement>('.heatmap-time-row [role="columnheader"]:first-child')?.offsetWidth ?? 0;
    const gridBounds = grid.getBoundingClientRect();
    const periodWindow = visibleHeatmapPeriodWindow(
      headings.map((heading) => {
        const bounds = heading.getBoundingClientRect();
        return { left: bounds.left, width: bounds.width };
      }),
      gridBounds.left + stickyWidth,
      gridBounds.right,
    );
    visiblePeriods.textContent = periodWindow === null
      ? `Periods 0 of ${headings.length}`
      : `Periods ${periodWindow.firstIndex + 1}–${periodWindow.lastIndex + 1} of ${periodWindow.total}`;
    scrollLeft.disabled = grid.scrollLeft <= 1;
    scrollRight.disabled = grid.scrollLeft >= grid.scrollWidth - grid.clientWidth - 1;
    viewportControls.hidden = grid.scrollWidth <= grid.clientWidth + 1;
  };
  grid.addEventListener("scroll", updateVisiblePeriods, { passive: true });
  section.append(grid, renderHeatmapEvidence(presentation.evidence, actions, presentation.selectedCell));
  globalThis.requestAnimationFrame?.(updateVisiblePeriods);
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

interface ExportRenderActions {
  reopen(exportId: string): void;
  retry(): void;
}

function renderExportState(loadState: LoadState<ExportSnapshotResultDto>, reopenError: ReportErrorDto | null, actions: ExportRenderActions): Node | null {
  if (loadState.kind === "not-requested" && reopenError === null) return null;
  const section = document.createElement("section");
  section.className = "report-export-state state-panel";
  section.setAttribute("aria-label", "Latest report export");
  const previous = valueFrom(loadState);
  if (previous !== null) {
    section.append(textElement("strong", `Export ready: ${describeExportResult(previous)}.`));
    const reopen = textElement("button", "Reopen export") as HTMLButtonElement;
    reopen.type = "button";
    reopen.addEventListener("click", () => actions.reopen(previous.exportId));
    section.append(reopen);
    for (const warning of previous.warnings) section.append(textElement("p", `Warning ${warning.code}: ${warning.message}`));
    for (const omission of previous.omissions) section.append(textElement("p", `${omission.section} omitted: ${omission.reason} ${omission.recovery}`));
  }
  if (loadState.kind === "loading") {
    section.setAttribute("aria-busy", "true");
    section.append(textElement("p", "Preparing the selected report export…"));
  } else if (loadState.kind === "cancelled") {
    section.append(textElement("p", "Export cancelled; no new export was published."));
  } else if (loadState.kind === "error") {
    const alert = document.createElement("div");
    alert.setAttribute("role", "alert");
    alert.append(textElement("strong", `${loadState.error.code}: ${loadState.error.message}`));
    const recovery = reportErrorRecovery(loadState.error);
    alert.append(textElement("p", recovery.message));
    if (recovery.label !== null) {
      const retry = textElement("button", recovery.label) as HTMLButtonElement;
      retry.type = "button";
      retry.addEventListener("click", actions.retry);
      alert.append(retry);
    }
    section.append(alert);
  }
  if (reopenError !== null) {
    const alert = document.createElement("div");
    alert.setAttribute("role", "alert");
    alert.append(
      textElement("strong", `${reopenError.code}: ${reopenError.message}`),
      textElement("p", "This retained export could not be opened. Export the report again if it is no longer available."),
    );
    section.append(alert);
  }
  return section;
}

function assertElements(elements: WorkspaceElements): void {
  for (const [name, element] of Object.entries(elements)) {
    if (typeof element !== "object" || element === null || typeof element.addEventListener !== "function" || typeof element.replaceChildren !== "function") {
      throw new Error(`Missing interactive report element ${name}.`);
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
  let lastRequestedExportMode: ExportMode = "directory";
  let reopenExportError: ReportErrorDto | null = null;
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
    reopenExportError = null;
    state = Object.freeze({ ...initialState(), lifecycle: "selected", route: Object.freeze({ kind: "preflight", rootThreadId: normalized.rootThreadId }), selection: normalized, requestSequence: state.requestSequence + 1 });
    scheduleRender();
  }

  async function loadSummary(focusHeading: boolean, force = false): Promise<void> {
    const snapshot = state.snapshot;
    if (snapshot === null) return;
    const existing = valueFrom(state.summary);
    if (!force && existing?.snapshotId === snapshot.snapshotId && existing.revision === snapshot.revision) {
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

  function currentHeatmapInteraction(summary: ReportSummaryDto): HeatmapInteractionState {
    if (state.heatmapInteraction.visibleFromTime !== "" && state.heatmapInteraction.visibleToTime !== "") return state.heatmapInteraction;
    const interaction: HeatmapInteractionState = Object.freeze({
      ...state.heatmapInteraction,
      visibleFromTime: summary.timeRange.fromTime,
      visibleToTime: summary.timeRange.toTime,
    });
    commit({ heatmapInteraction: interaction });
    return interaction;
  }

  function updateHeatmapInteraction(patch: Partial<HeatmapInteractionState>): HeatmapInteractionState {
    const interaction = Object.freeze({ ...state.heatmapInteraction, ...patch });
    commit({ heatmapInteraction: interaction });
    return interaction;
  }

  async function loadHeatmap(force = false, requestedInteraction?: HeatmapInteractionState): Promise<void> {
    const snapshot = state.snapshot;
    const summary = valueFrom(state.summary);
    if (snapshot === null || summary === null) return;
    const interaction = requestedInteraction ?? currentHeatmapInteraction(summary);
    const requestBinding = {
      snapshotId: snapshot.snapshotId,
      queryKind: "matrix" as const,
      fromTime: interaction.visibleFromTime,
      toTime: interaction.visibleToTime,
      mode: interaction.mode,
      requestedResolutionMinutes: interaction.requestedResolutionMinutes,
      maximumRows: interaction.maximumRows,
    };
    const previous = valueFrom(state.timeSeries);
    if (!force && previous?.revisionId === snapshot.revision && previous.fromTime === requestBinding.fromTime && previous.toTime === requestBinding.toTime && previous.mode === requestBinding.mode && previous.requestedResolutionMinutes === requestBinding.requestedResolutionMinutes && previous.maximumRows === requestBinding.maximumRows) return;
    const operation = nextOperation("query_snapshot_time_range");
    commit({ lifecycle: "querying", timeSeries: Object.freeze({ kind: "loading", previous, operationId: operation.id }) });
    try {
      const request = { operationId: operation.id, ...requestBinding };
      const result = parseHeatmapResultDto(await invoke(WORKSPACE_COMMANDS.querySnapshotTimeRange, request), { ...request, revisionId: snapshot.revision });
      if (!isCurrent(operation.sequence, operation.id) || result.queryKind !== "matrix") return;
      commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null, timeSeries: loadStateFor(result, result.rows.length === 0), heatmapInteraction: interaction });
    } catch (error) { fail(operation.sequence, operation.id, "timeSeries", error, "ready"); }
  }

  async function loadHeatmapEvidence(selection: HeatmapSelectedCell): Promise<void> {
    const snapshot = state.snapshot;
    if (snapshot === null) return;
    const priorInteraction = state.heatmapInteraction;
    const sameSelection = priorInteraction.selectedCell?.rowId === selection.rowId
      && priorInteraction.selectedCell.periodStartTime === selection.periodStartTime
      && priorInteraction.selectedCell.periodEndTime === selection.periodEndTime;
    const previous = sameSelection ? valueFrom(priorInteraction.evidence) : null;
    const operation = nextOperation("query_snapshot_time_range");
    updateHeatmapInteraction({ selectedCell: Object.freeze({ ...selection }), evidence: Object.freeze({ kind: "loading", previous, operationId: operation.id }) });
    const request = {
      operationId: operation.id,
      snapshotId: snapshot.snapshotId,
      queryKind: "cell_evidence" as const,
      mode: state.heatmapInteraction.mode,
      rowId: selection.rowId,
      periodStartTime: selection.periodStartTime,
      periodEndTime: selection.periodEndTime,
    };
    try {
      const result = parseHeatmapResultDto(await invoke(WORKSPACE_COMMANDS.querySnapshotTimeRange, request), {
        ...request,
        revisionId: snapshot.revision,
        rowKey: selection.rowKey,
        rowOrderIndex: selection.rowOrderIndex,
      });
      if (!isCurrent(operation.sequence, operation.id) || result.queryKind !== "cell_evidence") return;
      const selected = state.heatmapInteraction.selectedCell;
      if (selected === null) return;
      if (!heatmapEvidenceMatchesSelection(selected, result)) {
        throw new Error("Heatmap evidence does not match the selected matrix cell.");
      }
      updateHeatmapInteraction({ evidence: loadStateFor(result, result.evidenceItems.length === 0) });
      commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null });
    } catch (error) {
      if (!isCurrent(operation.sequence, operation.id)) return;
      const reportError = safeError(error);
      const priorEvidence = valueFrom(priorInteraction.evidence);
      commit({
        lifecycle: "ready",
        activeOperationId: null,
        activeOperation: null,
        heatmapInteraction: Object.freeze({
          ...priorInteraction,
          evidence: reportError.code === "REPORT_CANCELLED"
            ? Object.freeze({ kind: "cancelled", previous: priorEvidence, operationId: operation.id })
            : Object.freeze({ kind: "error", previous: priorEvidence, error: reportError }),
        }),
      });
    }
  }

  function queryHeatmapWith(patch: Partial<HeatmapInteractionState>): Promise<void> {
    const coherentInteraction = coherentHeatmapInteraction(state.heatmapInteraction);
    if (coherentInteraction !== state.heatmapInteraction) commit({ heatmapInteraction: coherentInteraction });
    const interaction = heatmapInteractionForMatrixRequest(coherentInteraction, patch);
    return loadHeatmap(true, interaction);
  }

  function rememberHeatmapRange(interaction: HeatmapInteractionState): readonly HeatmapPeriodHistoryEntry[] {
    const entry = Object.freeze({ fromTime: interaction.visibleFromTime, toTime: interaction.visibleToTime, requestedResolutionMinutes: interaction.requestedResolutionMinutes });
    return Object.freeze([...interaction.history, entry].slice(-MAX_CURSOR_HISTORY));
  }

  async function drillDownHeatmap(): Promise<void> {
    const interaction = state.heatmapInteraction;
    const selected = interaction.selectedCell;
    if (selected === null || interaction.requestedResolutionMinutes === 1) return;
    await queryHeatmapWith({
      visibleFromTime: selected.periodStartTime,
      visibleToTime: selected.periodEndTime,
      requestedResolutionMinutes: nextHeatmapResolution(interaction.requestedResolutionMinutes, "in"),
      history: rememberHeatmapRange(interaction),
    });
  }

  async function stepBackHeatmap(): Promise<void> {
    const interaction = state.heatmapInteraction;
    if (interaction.history.length === 0) return;
    const history = [...interaction.history];
    const entry = history.pop();
    if (entry !== undefined) await queryHeatmapWith({ visibleFromTime: entry.fromTime, visibleToTime: entry.toTime, requestedResolutionMinutes: entry.requestedResolutionMinutes, history: Object.freeze(history) });
  }

  async function moveHeatmapPeriod(direction: "previous" | "next"): Promise<void> {
    const matrix = valueFrom(state.timeSeries);
    const selected = state.heatmapInteraction.selectedCell;
    if (matrix === null || selected === null) return;
    const row = matrix.rows.find((candidate) => candidate.rowId === selected.rowId);
    const index = row?.cells.findIndex((cell) => cell.startTime === selected.periodStartTime && cell.endTime === selected.periodEndTime) ?? -1;
    const target = row?.cells[index + (direction === "previous" ? -1 : 1)];
    if (row !== undefined && target !== undefined) await loadHeatmapEvidence(heatmapSelectionFor(row, target));
  }

  async function setHeatmapPeriod(requestedResolutionMinutes: HeatmapRequestedResolutionMinutes): Promise<void> {
    if (HEATMAP_RESOLUTIONS.includes(requestedResolutionMinutes)) await queryHeatmapWith({ requestedResolutionMinutes });
  }

  function heatmapActions(): HeatmapRenderActions {
    return {
      select(selection) { void loadHeatmapEvidence(selection); },
      drillDown() { void drillDownHeatmap(); },
      stepBack() { void stepBackHeatmap(); },
      restoreHistory(index) {
        const interaction = state.heatmapInteraction;
        const entry = interaction.history[index];
        if (entry === undefined) return;
        void queryHeatmapWith({ visibleFromTime: entry.fromTime, visibleToTime: entry.toTime, requestedResolutionMinutes: entry.requestedResolutionMinutes, history: Object.freeze(interaction.history.slice(0, index)) });
      },
      movePeriod(direction) { void moveHeatmapPeriod(direction); },
      setMode(mode) {
        if (HEATMAP_MODES.some((item) => item.value === mode)) void queryHeatmapWith({ mode, history: Object.freeze([]) });
      },
      setResolution(requestedResolutionMinutes) { void setHeatmapPeriod(requestedResolutionMinutes); },
      setMaximumRows(maximumRows) {
        if (Number.isSafeInteger(maximumRows) && maximumRows >= 1 && maximumRows <= MAX_HEATMAP_ROWS) void queryHeatmapWith({ maximumRows });
        else elements.statusRegion.textContent = `Maximum rows must be between 1 and ${MAX_HEATMAP_ROWS}.`;
      },
      openDetail(eventId, trigger) { void controller.openDetail(eventId, trigger); },
    };
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

  function retryPage(name: PagerName): void {
    const pager = state.pagers[name];
    const restart = pager.page.kind === "error" && pager.page.error.restartFromFirstPage;
    void loadPage(name, restart ? null : pager.currentCursor, restart ? [] : pager.previousCursors);
  }

  function render(): void {
    const route = state.route;
    const activeGridCell = route.kind === "snapshot" && route.surface === "heatmap"
      && document.activeElement instanceof HTMLButtonElement
      && document.activeElement.getAttribute("role") === "gridcell"
      && elements.viewRegion.contains(document.activeElement)
      ? Object.freeze({ rowIndex: document.activeElement.dataset.rowIndex, columnIndex: document.activeElement.dataset.columnIndex })
      : null;
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
      elements.statusRegion.textContent = state.lifecycle === "no-selection" ? "Select a run to view." : "Choose what to include in the report.";
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
        () => { void loadSummary(false, true); },
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
        () => retryPage("coordination"),
      );
      elements.viewRegion.replaceChildren(metricsHost, evidenceHost);
    } else if (metricGroupsFor(route.surface).length > 0 || route.surface === "summary") {
      renderLoadState(elements.viewRegion, state.summary, (value) => renderSummary(value, metricGroupsFor(route.surface)), definition.emptyMessage, () => { void loadSummary(false, true); });
    } else if (route.surface === "heatmap") {
      renderLoadState(
        elements.viewRegion,
        state.timeSeries,
        (value) => renderHeatmap(value, state.heatmapInteraction, heatmapActions()),
        definition.emptyMessage,
        () => { void loadHeatmap(true); },
      );
      if (activeGridCell !== null) {
        [...elements.viewRegion.querySelectorAll<HTMLButtonElement>('[role="gridcell"]')].find(
          (cell) => cell.dataset.rowIndex === activeGridCell.rowIndex && cell.dataset.columnIndex === activeGridCell.columnIndex,
        )?.focus();
      }
    }
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
        () => retryPage(pagerName),
      );
    }
    const exportPresentation = renderExportState(state.exportState, reopenExportError, {
      reopen(exportId) { void controller.reopenExport(exportId); },
      retry() { void controller.exportSnapshot(lastRequestedExportMode); },
    });
    if (exportPresentation !== null) elements.viewRegion.append(exportPresentation);
    const heatmap = route.surface === "heatmap" ? valueFrom(state.timeSeries) : null;
    const resolutionStatus = heatmap === null ? "" : heatmapResolutionLabel(heatmap.requestedResolutionMinutes, heatmap.actualResolutionMinutes);
    elements.statusRegion.hidden = route.surface === "heatmap" && !busy && resolutionStatus === "";
    elements.statusRegion.textContent = busy
      ? `Loading ${definition.label}.`
      : resolutionStatus === "" ? `${definition.label} ready.` : `${definition.label} ready. ${resolutionStatus}`;
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
      reopenExportError = null;
      commit({ lifecycle: "selected", selection: Object.freeze({ ...state.selection, includeChildren, includeCollaborators }), preflight: Object.freeze({ kind: "not-requested" }), snapshot: null, summary: Object.freeze({ kind: "not-requested" }), pagers: createPagers(), timeSeries: Object.freeze({ kind: "not-requested" }), heatmapInteraction: initialHeatmapInteraction(), detail: Object.freeze({ kind: "not-requested" }) });
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
    changeScope(focusTarget) {
      if (disposed || state.selection === null) return;
      closeModal(elements.preflightDialog, focusTarget ?? selectionTrigger);
      commit({ lifecycle: "selected", selection: scopeSelectionForEditing(state.selection), preflight: Object.freeze({ kind: "not-requested" }) });
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
    async selectHeatmapCell(rowId, periodStartTime, periodEndTime) {
      const matrix = valueFrom(state.timeSeries);
      if (disposed || matrix === null) return;
      const row = matrix.rows.find((candidate) => candidate.rowId === rowId);
      const cell = row?.cells.find((candidate) => candidate.startTime === periodStartTime && candidate.endTime === periodEndTime);
      if (row !== undefined && cell !== undefined) await loadHeatmapEvidence(heatmapSelectionFor(row, cell));
    },
    async drillDownHeatmap() { if (!disposed) await drillDownHeatmap(); },
    async stepBackHeatmap() { if (!disposed) await stepBackHeatmap(); },
    async moveHeatmapPeriod(direction) { if (!disposed) await moveHeatmapPeriod(direction); },
    async setHeatmapPeriod(minutes) { if (!disposed) await setHeatmapPeriod(minutes); },
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
        commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null, snapshot: refreshed, ...(revisionChanged ? { summary: Object.freeze({ kind: "not-requested" as const }), pagers: createPagers(), timeSeries: Object.freeze({ kind: "not-requested" as const }), heatmapInteraction: Object.freeze({ ...state.heatmapInteraction, selectedCell: null, evidence: Object.freeze({ kind: "not-requested" as const }) }), detail: Object.freeze({ kind: "not-requested" as const }) } : {
          summary: clearStaleLoadState(state.summary, false),
          pagers: clearStalePagers(state.pagers),
          timeSeries: clearStaleLoadState(state.timeSeries, valueFrom(state.timeSeries)?.rows.length === 0),
          heatmapInteraction: Object.freeze({ ...state.heatmapInteraction, evidence: clearStaleLoadState(state.heatmapInteraction.evidence, valueFrom(state.heatmapInteraction.evidence)?.evidenceItems.length === 0) }),
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
            ? { timeSeries: staleLoadState(state.timeSeries, reason), heatmapInteraction: Object.freeze({ ...state.heatmapInteraction, evidence: staleLoadState(state.heatmapInteraction.evidence, reason) }) }
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
      lastRequestedExportMode = mode;
      reopenExportError = null;
      const previous = valueFrom(state.exportState);
      const operation = nextOperation("export_snapshot");
      commit({ lifecycle: "exporting", exportState: Object.freeze({ kind: "loading", previous, operationId: operation.id }) });
      try {
        const raw = await invoke(WORKSPACE_COMMANDS.exportSnapshot, { operationId: operation.id, snapshotId: snapshot.snapshotId, mode });
        if (!isCurrent(operation.sequence, operation.id)) return;
        if (raw === null) {
          commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null, exportState: Object.freeze({ kind: "cancelled", previous, operationId: operation.id }) });
          return;
        }
        const result = parseExportSnapshotResultDto(raw, { operationId: operation.id, snapshotId: snapshot.snapshotId, revision: snapshot.revision, mode });
        commit({ lifecycle: "ready", activeOperationId: null, activeOperation: null, exportState: loadStateFor(result, false) });
      } catch (error) { fail(operation.sequence, operation.id, "exportState", error, "ready"); }
    },
    async reopenExport(exportId) {
      if (disposed) return;
      const normalizedExportId = requireOpaqueId(exportId, "exportId");
      reopenExportError = null;
      elements.statusRegion.textContent = "Opening the retained report export.";
      try {
        await invoke(WORKSPACE_COMMANDS.reopenExport, { exportId: normalizedExportId });
        if (disposed) return;
        elements.statusRegion.textContent = "Opened the retained report export.";
      } catch (error) {
        if (disposed) return;
        reopenExportError = safeError(error);
        scheduleRender();
      }
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
      } catch (error) {
        if (!isCurrent(operation.sequence, operation.id)) return;
        const reportError = safeError(error);
        fail(operation.sequence, operation.id, "detail", error, "ready");
        const heading = textElement("h2", "Event detail unavailable");
        heading.id = "report-detail-heading";
        heading.dataset.dialogHeading = "";
        heading.tabIndex = -1;
        const alert = document.createElement("div");
        alert.setAttribute("role", "alert");
        alert.append(textElement("strong", `${reportError.code}: ${reportError.message}`), textElement("p", reportErrorRecovery(reportError).message));
        const retry = textElement("button", "Retry") as HTMLButtonElement;
        retry.type = "button";
        retry.addEventListener("click", () => { void controller.openDetail(normalizedEventId, trigger); });
        const close = textElement("button", "Close detail") as HTMLButtonElement;
        close.type = "button";
        close.addEventListener("click", () => controller.closeDetail());
        elements.detailDialog.replaceChildren(heading, alert, retry, close);
        heading.focus();
      }
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
        reopenExportError = null;
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
      reopenExportError = null;
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
