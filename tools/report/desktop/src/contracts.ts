// Copyright (c) 2026 Martin.Bechard@DevConsult.ca
// AI attribution: Generated with AI assistance.
// Responsibility: Validate native command results before they enter webview state.
// Design: docs/design/components/CD-005-agent-report-dynamic-workspace.md

const MAX_TEXT_LENGTH = 4_096;
const MAX_DISCLOSURE_LENGTH = 16_384;
const MAX_WARNING_COUNT = 100;
const MAX_PAGE_SIZE = 500;
const MAX_HEATMAP_CELLS = 2_000;
const MAX_SEQUENCE_GROUPS = 500;

export interface RootReferenceDto {
  readonly rootRef: string;
  readonly displayName: string;
}

export interface DesktopDefaults {
  readonly roots: readonly RootReferenceDto[];
  readonly diagnosticsAvailable: boolean;
}

export interface SearchRequest {
  readonly rootRefs: readonly string[];
  readonly query: string;
  readonly fromDate: string;
  readonly toDate: string;
  readonly includeDescendants: boolean;
  readonly workers: number | null;
}

export interface CatalogDiagnosticDto {
  readonly code: string;
  readonly message: string;
}

export interface CatalogEntry {
  readonly threadId: string;
  readonly parentThreadId: string;
  readonly taskTitle: string;
  readonly startedAt: string;
  readonly lastActivityAt: string;
  readonly workspaceLabel: string;
  readonly sourceRef: string;
  readonly sourceLabel: string;
  readonly agentLabel: string;
  readonly agentNickname: string;
  readonly delegationCount: number;
  readonly diagnostic: CatalogDiagnosticDto | null;
}

export interface DiscoveryStats {
  readonly candidate_files: number;
  readonly scanned_files: number;
  readonly cached_files: number;
  readonly unstable_files: number;
  readonly unreadable_files: number;
  readonly elapsed_ms: number;
  readonly workers: number;
}

export interface SearchResponse {
  readonly entries: readonly CatalogEntry[];
  readonly stats: DiscoveryStats;
}

export interface DiscoveryProgress {
  readonly completed_files: number;
  readonly candidate_files: number;
  readonly sourceLabel: string;
  readonly source: "cache" | "scan";
}

export interface ProgressPresentation {
  readonly label: string;
  readonly value: string;
  readonly sourceLabel: string;
  readonly completed: number | null;
  readonly total: number | null;
  readonly detail?: string;
}

export interface ReportGenerationProgress {
  readonly completed: number;
  readonly total: number;
  readonly itemCompleted: number | null;
  readonly itemTotal: number | null;
  readonly label: string;
  readonly detail: string;
  readonly worker: string | null;
}

export interface ExportResult {
  readonly exportId: string;
  readonly displayName: string;
  readonly entryCount: number;
}

export type ReportOperationName =
  | "preflight_report"
  | "open_snapshot"
  | "get_summary"
  | "list_agents"
  | "list_turns"
  | "list_events"
  | "query_time_range"
  | "query_sequence"
  | "query_coordination"
  | "get_event_details"
  | "refresh_snapshot"
  | "export_snapshot"
  | "close_snapshot";

export type EvidenceLabel = "measured" | "derived" | "inferred" | "unavailable" | "estimated";

export type ReportErrorCode =
  | "REPORT_CANCELLED"
  | "REPORT_CURSOR_CONFLICT"
  | "REPORT_DISCOVERY_FAILED"
  | "REPORT_EVENT_NOT_FOUND"
  | "REPORT_EXPORT_FAILED"
  | "REPORT_GENERATION_FAILED"
  | "REPORT_INTERNAL_ERROR"
  | "REPORT_INVALID_REQUEST"
  | "REPORT_NOT_FOUND"
  | "REPORT_PRIVACY_FAILED"
  | "REPORT_SCOPE_CONFLICT"
  | "REPORT_SNAPSHOT_CONFLICT"
  | "REPORT_SNAPSHOT_NOT_FOUND"
  | "REPORT_WRITE_FAILED"
  | "REPORT_PROTOCOL_ERROR"
  | "REPORT_UNAVAILABLE";

export interface WarningRecordDto {
  readonly code: string;
  readonly message: string;
}

export interface ReportErrorDto {
  readonly code: ReportErrorCode;
  readonly message: string;
  readonly operationId: string | null;
  readonly recoverable: boolean;
  readonly currentSourceRevision: string | null;
  readonly preflightRequired: boolean;
  readonly restartFromFirstPage: boolean;
}

export interface WorkspaceOperationRequestDto { readonly operationId: string }
export interface PreflightReportRequestDto extends WorkspaceOperationRequestDto {
  readonly rootThreadId: string;
  readonly includeChildren: boolean;
  readonly includeCollaborators: boolean;
}

export interface PreflightReportDto {
  readonly preflightToken: string;
  readonly rootThreadId: string;
  readonly includeChildren: boolean;
  readonly includeCollaborators: boolean;
  readonly sourceRevision: string;
  readonly logCount: number;
  readonly totalBytes: number;
  readonly childCount: number;
  readonly collaboratorCount: number;
  readonly cachedFileCount: number;
  readonly changedFileCount: number;
  readonly knownEventCount: number | null;
  readonly warnings: readonly WarningRecordDto[];
}

export interface OpenSnapshotRequestDto extends WorkspaceOperationRequestDto {
  readonly rootThreadId: string;
  readonly includeChildren: boolean;
  readonly includeCollaborators: boolean;
  readonly preflightToken: string;
  readonly sourceRevision: string;
}

export interface SnapshotMetadataDto {
  readonly protocolVersion: number;
  readonly snapshotId: string;
  readonly revision: string;
  readonly rootThreadId: string;
  readonly includeChildren: boolean;
  readonly includeCollaborators: boolean;
  readonly sourceRevision: string;
  readonly parserVersion: string;
  readonly pricingDigest: string;
  readonly formatterDigest: string;
  readonly observationTime: string;
  readonly mode: "live" | "sealed";
  readonly warnings: readonly WarningRecordDto[];
}

export type SummaryMetricGroupId =
  | "overview" | "model" | "context" | "inference" | "runtime"
  | "waits" | "work_items" | "claims" | "provenance";

export interface SummaryMetricDto {
  readonly metricId: string;
  readonly label: string;
  readonly displayValue: string;
  readonly evidence: EvidenceLabel;
  readonly description: string | null;
}
export interface SummaryMetricGroupDto {
  readonly groupId: SummaryMetricGroupId;
  readonly label: string;
  readonly metrics: readonly SummaryMetricDto[];
}
export interface SignificantActivityDto {
  readonly eventId: string;
  readonly occurredAt: string;
  readonly label: string;
  readonly evidence: EvidenceLabel;
}
export interface ReportTimeRangeDto { readonly fromTime: string; readonly toTime: string }
export interface ReportSummaryDto {
  readonly snapshotId: string;
  readonly revision: string;
  readonly title: string;
  readonly goal: string | null;
  readonly state: string;
  readonly scopeLabel: string;
  readonly observedAt: string;
  readonly live: boolean;
  readonly timeRange: ReportTimeRangeDto;
  readonly metricGroups: readonly SummaryMetricGroupDto[];
  readonly recentActivity: readonly SignificantActivityDto[];
  readonly warnings: readonly WarningRecordDto[];
}

export type SortDirection = "ascending" | "descending";
export interface StableSortDto<K extends string> {
  readonly key: K;
  readonly direction: SortDirection;
  readonly tieBreakKey: string;
  readonly tieBreakDirection: SortDirection;
}
export interface CursorPageRequestDto<F, S> extends WorkspaceOperationRequestDto {
  readonly snapshotId: string;
  readonly cursor: string | null;
  readonly pageSize: number;
  readonly filters: F;
  readonly sort: S;
}
export type CursorPageOperation = "list_agents" | "list_turns" | "list_events" | "query_sequence" | "query_coordination";
export interface CursorPageDto<T, F, S> {
  readonly snapshotId: string;
  readonly revision: string;
  readonly operation: CursorPageOperation;
  readonly items: readonly T[];
  readonly appliedFilters: F;
  readonly appliedSort: S;
  readonly pageSize: number;
  readonly nextCursor: string | null;
}
export interface ExpectedPageBinding<F, S, O extends CursorPageOperation> {
  readonly snapshotId: string;
  readonly revision: string;
  readonly operation: O;
  readonly filters: F;
  readonly sort: S;
}

export interface AgentFiltersDto { readonly query: string; readonly state: string | null }
export interface AgentSortDto extends StableSortDto<"last_activity_at" | "started_at" | "agent_id"> {
  readonly tieBreakKey: "agent_id";
  readonly tieBreakDirection: "ascending";
}
export interface AgentRowDto {
  readonly agentId: string;
  readonly nickname: string | null;
  readonly role: string | null;
  readonly state: string;
  readonly startedAt: string | null;
  readonly lastActivityAt: string | null;
  readonly turnCount: number;
  readonly eventCount: number;
}
export interface TurnFiltersDto { readonly agentId: string | null; readonly state: string | null }
export interface TurnSortDto extends StableSortDto<"started_at" | "ended_at" | "turn_id"> {
  readonly tieBreakKey: "turn_id";
  readonly tieBreakDirection: "ascending";
}
export interface TurnRowDto {
  readonly turnId: string;
  readonly agentId: string;
  readonly startedAt: string;
  readonly endedAt: string | null;
  readonly state: string;
  readonly eventCount: number;
  readonly summary: string | null;
}
export interface EventFiltersDto {
  readonly agentId: string | null;
  readonly turnId: string | null;
  readonly kind: string | null;
  readonly fromTime: string | null;
  readonly toTime: string | null;
}
export interface EventSortDto extends StableSortDto<"occurred_at" | "event_id"> {
  readonly tieBreakKey: "event_id";
  readonly tieBreakDirection: "ascending";
}
export interface EventRowDto {
  readonly eventId: string;
  readonly occurredAt: string;
  readonly agentId: string | null;
  readonly turnId: string | null;
  readonly kind: string;
  readonly label: string;
  readonly evidence: EvidenceLabel;
  readonly sourceRef: string | null;
  readonly hasDetail: boolean;
}

export type HeatmapGroupBy = "agent" | "event_kind" | "work_item";
export type HeatmapColorSemantic = "sequential_nonnegative" | "diverging_signed";
export type HeatmapRequestedResolutionMinutes = 1 | 5 | 15 | 30 | 60;
export type HeatmapScaleBasis = "visible_row_maximum" | "context_window_capacity";
export type TimeMeasure =
  | "wall_time"
  | "uncached_input_tokens"
  | "cached_input_tokens"
  | "output_tokens"
  | "reasoning_tokens"
  | "cost_usd";
export interface HeatmapRequestDto extends WorkspaceOperationRequestDto {
  readonly snapshotId: string;
  readonly fromTime: string;
  readonly toTime: string;
  readonly measure: TimeMeasure;
  readonly groupBy: HeatmapGroupBy;
  readonly requestedResolutionMinutes: HeatmapRequestedResolutionMinutes;
  readonly maximumRows: number;
}
export interface HeatmapCellDto {
  readonly startTime: string;
  readonly endTime: string;
  readonly value: number | null;
  readonly count: number;
  readonly evidence: EvidenceLabel;
  readonly primaryLabel: string;
  readonly secondaryLabel: string | null;
}
export interface HeatmapScaleDto {
  readonly minimum: number;
  readonly maximum: number;
  readonly colorSemantic: HeatmapColorSemantic;
  readonly basis: HeatmapScaleBasis;
}
export interface HeatmapRowDto {
  readonly rowId: string;
  readonly label: string;
  readonly scale: HeatmapScaleDto;
  readonly cells: readonly HeatmapCellDto[];
}
export interface HeatmapResultDto {
  readonly snapshotId: string;
  readonly revision: string;
  readonly measure: TimeMeasure;
  readonly groupBy: HeatmapGroupBy;
  readonly fromTime: string;
  readonly toTime: string;
  readonly requestedResolutionMinutes: HeatmapRequestedResolutionMinutes;
  readonly actualResolutionMinutes: number;
  readonly maximumRows: number;
  readonly omittedRowCount: number;
  readonly rowOrder: "activity_descending_id_ascending";
  readonly totalCellCount: number;
  readonly rows: readonly HeatmapRowDto[];
  readonly provenance: readonly string[];
}

export interface SequenceFiltersDto {
  readonly focusAgentId: string | null;
  readonly eventKinds: readonly string[];
  readonly grouping: "none" | "repeated_messages" | "delegation" | "agent";
  readonly includeReasoning: boolean;
}
export interface SequenceSortDto extends StableSortDto<"occurred_at" | "sequence_id"> {
  readonly direction: "ascending";
  readonly tieBreakKey: "sequence_id";
  readonly tieBreakDirection: "ascending";
}
export interface SequenceGroupDto {
  readonly groupId: string;
  readonly parentGroupId: string | null;
  readonly depth: number;
  readonly label: string;
  readonly collapsible: boolean;
}
export interface SequenceRowDto {
  readonly sequenceId: string;
  readonly groupId: string | null;
  readonly occurredAt: string;
  readonly fromAgentId: string | null;
  readonly fromAgentLabel: string | null;
  readonly toAgentId: string | null;
  readonly toAgentLabel: string | null;
  readonly kind: string;
  readonly label: string;
  readonly evidence: EvidenceLabel;
  readonly eventId: string | null;
  readonly repeatCount: number;
  readonly reasoningAvailable: boolean;
}
export interface SequencePageDto {
  readonly page: CursorPageDto<SequenceRowDto, SequenceFiltersDto, SequenceSortDto> & {
    readonly operation: "query_sequence";
  };
  readonly groups: readonly SequenceGroupDto[];
}

export interface CoordinationFiltersDto {
  readonly workItemId: string | null;
  readonly delegatedRootId: string | null;
  readonly agentId: string | null;
  readonly operation: string | null;
  readonly evidence: EvidenceLabel | null;
}
export interface CoordinationSortDto extends StableSortDto<"occurred_at" | "coordination_id"> {
  readonly direction: "ascending";
  readonly tieBreakKey: "coordination_id";
  readonly tieBreakDirection: "ascending";
}
export interface CoordinationRowDto {
  readonly coordinationId: string;
  readonly occurredAt: string;
  readonly workItemId: string | null;
  readonly delegatedRootId: string | null;
  readonly agentId: string | null;
  readonly operation: string;
  readonly label: string;
  readonly evidence: EvidenceLabel;
  readonly eventId: string | null;
}
export interface CoordinationPageDto extends CursorPageDto<CoordinationRowDto, CoordinationFiltersDto, CoordinationSortDto> {
  readonly operation: "query_coordination";
}

export interface DisclosureDto { readonly label: string; readonly content: string; readonly redacted: boolean }
export interface EventDetailDto {
  readonly snapshotId: string;
  readonly revision: string;
  readonly eventId: string;
  readonly occurredAt: string;
  readonly kind: string;
  readonly title: string;
  readonly evidence: EvidenceLabel;
  readonly provenance: readonly string[];
  readonly summary: string | null;
  readonly disclosures: readonly DisclosureDto[];
  readonly sourceRef: string | null;
}

export type ExportMode = "directory" | "summary";
export interface ExportSnapshotRequestDto extends WorkspaceOperationRequestDto {
  readonly snapshotId: string;
  readonly mode: ExportMode;
}
export interface ExportOmissionDto { readonly section: string; readonly reason: string; readonly recovery: string }
export interface ExportSnapshotResultDto {
  readonly operationId: string;
  readonly snapshotId: string;
  readonly revision: string;
  readonly exportId: string;
  readonly displayName: string;
  readonly mode: ExportMode;
  readonly manifestSha256: string | null;
  readonly fileCount: number;
  readonly totalByteCount: number;
  readonly warnings: readonly WarningRecordDto[];
  readonly omissions: readonly ExportOmissionDto[];
}
export interface RefreshSnapshotResultDto {
  readonly changed: boolean;
  readonly snapshot: SnapshotMetadataDto;
}
export interface CloseSnapshotResultDto {
  readonly snapshotId: string;
  readonly closed: boolean;
}
export interface WorkspaceProgressDto {
  readonly protocolVersion: number;
  readonly operationId: string;
  readonly operation: ReportOperationName;
  readonly snapshotId: string | null;
  readonly phase: string;
  readonly completed: number;
  readonly total: number | null;
  readonly message: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`${label} is not an object`);
  return value;
}

function scanBoundary(value: unknown, location = "result"): void {
  if (typeof value === "string") {
    if (/^(?:\/|\\|[A-Za-z]:[\\/]|file:)/i.test(value)) {
      throw new Error(`${location} contains a forbidden path-shaped value`);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => scanBoundary(item, `${location}[${index}]`));
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (["sourcePath", "outputPath", "cachePath", "filesystemPath", "rawRecord", "rawRollout"].includes(key) || key.endsWith("Path")) {
      throw new Error(`${location}.${key} is forbidden`);
    }
    scanBoundary(child, `${location}.${key}`);
  }
}

function exact(value: unknown, label: string, keys: readonly string[]): Record<string, unknown> {
  const result = record(value, label);
  for (const key of Object.keys(result)) {
    if (!keys.includes(key)) throw new Error(`${label}.${key} is unexpected`);
  }
  return result;
}

function text(source: Record<string, unknown>, key: string, label: string, options: { empty?: boolean; maximum?: number } = {}): string {
  const value = source[key];
  if (typeof value !== "string") throw new Error(`${label}.${key} is not a string`);
  if (options.empty !== true && value.length === 0) throw new Error(`${label}.${key} is empty`);
  if (value.length > (options.maximum ?? MAX_TEXT_LENGTH)) throw new Error(`${label}.${key} exceeds its client limit`);
  return value;
}

function nullableText(source: Record<string, unknown>, key: string, label: string): string | null {
  return source[key] === null ? null : text(source, key, label);
}

function bool(source: Record<string, unknown>, key: string, label: string): boolean {
  if (typeof source[key] !== "boolean") throw new Error(`${label}.${key} is not a boolean`);
  return source[key];
}

function count(source: Record<string, unknown>, key: string, label: string): number {
  const value = source[key];
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new Error(`${label}.${key} is not a non-negative integer`);
  return value;
}

function finite(source: Record<string, unknown>, key: string, label: string): number {
  const value = source[key];
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label}.${key} is not finite`);
  return value;
}

function nullableCount(source: Record<string, unknown>, key: string, label: string): number | null {
  return source[key] === null ? null : count(source, key, label);
}

function instant(source: Record<string, unknown>, key: string, label: string): string {
  const value = text(source, key, label);
  if (!/^\d{4}-\d{2}-\d{2}T/.test(value) || !Number.isFinite(Date.parse(value))) throw new Error(`${label}.${key} is not a valid ISO instant`);
  return value;
}

function nullableInstant(source: Record<string, unknown>, key: string, label: string): string | null {
  return source[key] === null ? null : instant(source, key, label);
}

function opaque(source: Record<string, unknown>, key: string, label: string): string {
  return text(source, key, label);
}

function digest(source: Record<string, unknown>, key: string, label: string): string {
  const value = text(source, key, label);
  if (!/^[0-9a-f]{64}$/u.test(value)) throw new Error(`${label}.${key} is not a lowercase SHA-256 digest`);
  return value;
}

function nullableDigest(source: Record<string, unknown>, key: string, label: string): string | null {
  return source[key] === null ? null : digest(source, key, label);
}

function stringArray(value: unknown, label: string, maximum = MAX_WARNING_COUNT): readonly string[] {
  if (!Array.isArray(value) || value.length > maximum) throw new Error(`${label} is not a bounded string array`);
  return value.map((item, index) => {
    if (typeof item !== "string" || item.length > MAX_TEXT_LENGTH) throw new Error(`${label}[${index}] is not bounded text`);
    return item;
  });
}

function warningArray(value: unknown, label: string): readonly WarningRecordDto[] {
  if (!Array.isArray(value) || value.length > MAX_WARNING_COUNT) throw new Error(`${label} is not a bounded warning array`);
  return value.map((item, index) => {
    const warningLabel = `${label}[${index}]`;
    const warning = exact(item, warningLabel, ["code", "message"]);
    return { code: text(warning, "code", warningLabel), message: text(warning, "message", warningLabel) };
  });
}

function evidence(value: unknown, label: string): EvidenceLabel {
  if (value !== "measured" && value !== "derived" && value !== "inferred" && value !== "unavailable" && value !== "estimated") throw new Error(`${label} has an unknown evidence label`);
  return value;
}

function oneOf<T extends string>(value: unknown, values: readonly T[], label: string): T {
  if (typeof value !== "string" || !values.includes(value as T)) throw new Error(`${label} has an unknown variant`);
  return value as T;
}

const MAX_STRUCTURAL_EQUALITY_DEPTH = 16;
const MAX_STRUCTURAL_EQUALITY_NODES = 1_024;

function boundedStructuralEqual(left: unknown, right: unknown): boolean {
  let remainingNodes = MAX_STRUCTURAL_EQUALITY_NODES;

  function compare(leftValue: unknown, rightValue: unknown, depth: number): boolean {
    remainingNodes -= 1;
    if (remainingNodes < 0 || depth > MAX_STRUCTURAL_EQUALITY_DEPTH) return false;
    if (Object.is(leftValue, rightValue)) return true;
    if (typeof leftValue !== typeof rightValue || leftValue === null || rightValue === null) return false;
    if (Array.isArray(leftValue) || Array.isArray(rightValue)) {
      if (!Array.isArray(leftValue) || !Array.isArray(rightValue) || leftValue.length !== rightValue.length) return false;
      for (let index = 0; index < leftValue.length; index += 1) {
        if ((index in leftValue) !== (index in rightValue) || !compare(leftValue[index], rightValue[index], depth + 1)) return false;
      }
      return true;
    }
    if (!isRecord(leftValue) || !isRecord(rightValue)) return false;
    if (Object.prototype.toString.call(leftValue) !== Object.prototype.toString.call(rightValue)) return false;
    const leftKeys = Object.keys(leftValue);
    const rightKeys = Object.keys(rightValue);
    if (leftKeys.length !== rightKeys.length) return false;
    return leftKeys.every((key) => Object.hasOwn(rightValue, key) && compare(leftValue[key], rightValue[key], depth + 1));
  }

  return compare(left, right, 0);
}

function parseNullableOpaque(value: unknown, key: string, source: Record<string, unknown>, label: string): string | null {
  return value === null ? null : opaque(source, key, label);
}

function parseExactTextRecord(value: unknown, label: string, keys: readonly string[]): Record<string, unknown> {
  return exact(value, label, keys);
}

export function dateRangeError(fromDate: string, fromTime: string, toDate: string, toTime: string): string | null {
  const from = localDateTime(fromDate, fromTime);
  const to = localDateTime(toDate, toTime);
  return from !== null && to !== null && from >= to
    ? "From date and time must be before To date and time."
    : null;
}

export function localDateTimeToUtc(date: string, time: string): string {
  const value = localDateTime(date, time);
  return value === null ? "" : value.toISOString();
}

export function localDayDateRange(now: Date): { readonly fromDate: string; readonly toDate: string } {
  const localMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const localTomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  return {
    fromDate: localDateValue(localMidnight),
    toDate: localDateValue(localTomorrow),
  };
}

function localDateTime(date: string, time: string): Date | null {
  if (date === "") return null;
  return new Date(`${date}T${time || "00:00"}`);
}

function localDateValue(value: Date): string {
  const year = String(value.getFullYear()).padStart(4, "0");
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function normalizeWorkerCount(value: unknown, fallback: number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 1 && parsed <= 64 ? parsed : fallback;
}

export function discoveryProgressPresentation(progress: DiscoveryProgress): ProgressPresentation {
  return {
    label: progress.source === "cache" ? "Reusing stable metadata" : "Reading changed rollout",
    value: `${progress.completed_files} / ${progress.candidate_files}`,
    sourceLabel: progress.sourceLabel,
    completed: progress.completed_files,
    total: progress.candidate_files,
  };
}

export function parseReportGenerationProgress(value: unknown): ReportGenerationProgress {
  scanBoundary(value);
  const result = record(value, "report generation progress");
  const completed = count(result, "completed", "report generation progress");
  const total = count(result, "total", "report generation progress");
  if (total === 0 || completed > total) throw new Error("report generation progress is outside its total");
  return {
    completed, total,
    itemCompleted: result.itemCompleted === undefined ? null : count(result, "itemCompleted", "report generation progress"),
    itemTotal: result.itemTotal === undefined ? null : count(result, "itemTotal", "report generation progress"),
    label: text(result, "label", "report generation progress"),
    detail: text(result, "detail", "report generation progress", { empty: true }),
    worker: result.worker === null || result.worker === undefined ? null : text(result, "worker", "report generation progress"),
  };
}

function parseRootReference(value: unknown, label: string): RootReferenceDto {
  const result = exact(value, label, ["rootRef", "displayName"]);
  const rootRef = opaque(result, "rootRef", label);
  const displayName = text(result, "displayName", label);
  if (/[\\/]|^[A-Za-z][A-Za-z0-9+.-]*:/.test(displayName) || displayName === rootRef) throw new Error(`${label}.displayName is not a bounded non-authority label`);
  return { rootRef, displayName };
}

export function parseRootReferences(value: unknown): readonly RootReferenceDto[] {
  scanBoundary(value);
  if (!Array.isArray(value)) throw new Error("root references is not an array");
  return value.map((item, index) => parseRootReference(item, `root references[${index}]`));
}

export function parseDesktopDefaults(value: unknown): DesktopDefaults {
  scanBoundary(value);
  const result = record(value, "desktop defaults");
  if (!Array.isArray(result.roots)) throw new Error("desktop defaults.roots is not an array");
  return {
    roots: result.roots.map((item, index) => parseRootReference(item, `desktop defaults.roots[${index}]`)),
    diagnosticsAvailable: bool(result, "diagnosticsAvailable", "desktop defaults"),
  };
}

function parseDiagnostic(value: unknown, label: string): CatalogDiagnosticDto | null {
  if (value === null) return null;
  const result = exact(value, label, ["code", "message"]);
  return { code: text(result, "code", label), message: text(result, "message", label) };
}

function parseCatalogEntry(value: unknown, index: number): CatalogEntry {
  const label = `search response.entries[${index}]`;
  const result = exact(value, label, ["threadId", "parentThreadId", "taskTitle", "startedAt", "lastActivityAt", "workspaceLabel", "sourceRef", "sourceLabel", "agentLabel", "agentNickname", "delegationCount", "diagnostic"]);
  const sourceRef = opaque(result, "sourceRef", label);
  const sourceLabel = text(result, "sourceLabel", label);
  const workspaceLabel = text(result, "workspaceLabel", label, { empty: true });
  const agentLabel = text(result, "agentLabel", label, { empty: true });
  for (const [key, display, reference] of [["sourceLabel", sourceLabel, sourceRef], ["workspaceLabel", workspaceLabel, ""], ["agentLabel", agentLabel, ""]] as const) {
    if (/[\\/]|^[A-Za-z][A-Za-z0-9+.-]*:/.test(display) || (reference !== "" && display === reference)) throw new Error(`${label}.${key} is not a bounded non-authority label`);
  }
  return {
    threadId: opaque(result, "threadId", label),
    parentThreadId: text(result, "parentThreadId", label, { empty: true }),
    taskTitle: text(result, "taskTitle", label, { empty: true }),
    startedAt: instant(result, "startedAt", label),
    lastActivityAt: instant(result, "lastActivityAt", label),
    workspaceLabel, sourceRef, sourceLabel, agentLabel,
    agentNickname: text(result, "agentNickname", label, { empty: true }),
    delegationCount: count(result, "delegationCount", label),
    diagnostic: parseDiagnostic(result.diagnostic, `${label}.diagnostic`),
  };
}

function parseStats(value: unknown): DiscoveryStats {
  const result = exact(value, "search response.stats", ["candidate_files", "scanned_files", "cached_files", "unstable_files", "unreadable_files", "elapsed_ms", "workers"]);
  return {
    candidate_files: count(result, "candidate_files", "search response.stats"),
    scanned_files: count(result, "scanned_files", "search response.stats"),
    cached_files: count(result, "cached_files", "search response.stats"),
    unstable_files: count(result, "unstable_files", "search response.stats"),
    unreadable_files: count(result, "unreadable_files", "search response.stats"),
    elapsed_ms: count(result, "elapsed_ms", "search response.stats"),
    workers: count(result, "workers", "search response.stats"),
  };
}

export function parseSearchResponse(value: unknown): SearchResponse {
  scanBoundary(value);
  const result = record(value, "search response");
  if (!Array.isArray(result.entries)) throw new Error("search response.entries is not an array");
  return { entries: result.entries.map(parseCatalogEntry), stats: parseStats(result.stats) };
}

export function parseDiscoveryProgress(value: unknown): DiscoveryProgress {
  scanBoundary(value);
  const result = record(value, "discovery progress");
  const source = oneOf(result.source, ["cache", "scan"] as const, "discovery progress.source");
  return {
    completed_files: count(result, "completed_files", "discovery progress"),
    candidate_files: count(result, "candidate_files", "discovery progress"),
    sourceLabel: text(result, "sourceLabel", "discovery progress", { empty: true }),
    source,
  };
}

export function parseExportResult(value: unknown): ExportResult {
  scanBoundary(value);
  const result = record(value, "export result");
  const exportId = opaque(result, "exportId", "export result");
  const displayName = text(result, "displayName", "export result");
  if (/[\\/]|^[A-Za-z][A-Za-z0-9+.-]*:/.test(displayName) || displayName === exportId) throw new Error("export result.displayName is not a bounded non-authority label");
  return { exportId, displayName, entryCount: count(result, "entryCount", "export result") };
}

export function parseReportErrorDto(value: unknown): ReportErrorDto {
  scanBoundary(value);
  const result = record(value, "report error");
  const code = oneOf(result.code, ["REPORT_CANCELLED", "REPORT_CURSOR_CONFLICT", "REPORT_DISCOVERY_FAILED", "REPORT_EVENT_NOT_FOUND", "REPORT_EXPORT_FAILED", "REPORT_GENERATION_FAILED", "REPORT_INTERNAL_ERROR", "REPORT_INVALID_REQUEST", "REPORT_NOT_FOUND", "REPORT_PRIVACY_FAILED", "REPORT_SCOPE_CONFLICT", "REPORT_SNAPSHOT_CONFLICT", "REPORT_SNAPSHOT_NOT_FOUND", "REPORT_WRITE_FAILED", "REPORT_PROTOCOL_ERROR", "REPORT_UNAVAILABLE"] as const, "report error.code");
  return {
    code,
    message: text(result, "message", "report error"),
    operationId: result.operationId === null ? null : opaque(result, "operationId", "report error"),
    recoverable: bool(result, "recoverable", "report error"),
    currentSourceRevision: result.currentSourceRevision === null ? null : opaque(result, "currentSourceRevision", "report error"),
    preflightRequired: bool(result, "preflightRequired", "report error"),
    restartFromFirstPage: bool(result, "restartFromFirstPage", "report error"),
  };
}

export function parsePreflightReportDto(value: unknown): PreflightReportDto {
  scanBoundary(value);
  const result = record(value, "preflight report");
  return {
    preflightToken: opaque(result, "preflightToken", "preflight report"), rootThreadId: opaque(result, "rootThreadId", "preflight report"),
    includeChildren: bool(result, "includeChildren", "preflight report"), includeCollaborators: bool(result, "includeCollaborators", "preflight report"),
    sourceRevision: opaque(result, "sourceRevision", "preflight report"), logCount: count(result, "logCount", "preflight report"), totalBytes: count(result, "totalBytes", "preflight report"),
    childCount: count(result, "childCount", "preflight report"), collaboratorCount: count(result, "collaboratorCount", "preflight report"), cachedFileCount: count(result, "cachedFileCount", "preflight report"), changedFileCount: count(result, "changedFileCount", "preflight report"),
    knownEventCount: nullableCount(result, "knownEventCount", "preflight report"), warnings: warningArray(result.warnings, "preflight report.warnings"),
  };
}

export function parseSnapshotMetadataDto(value: unknown): SnapshotMetadataDto {
  scanBoundary(value);
  const result = record(value, "snapshot metadata");
  return {
    protocolVersion: count(result, "protocolVersion", "snapshot metadata"), snapshotId: opaque(result, "snapshotId", "snapshot metadata"), revision: opaque(result, "revision", "snapshot metadata"), rootThreadId: opaque(result, "rootThreadId", "snapshot metadata"),
    includeChildren: bool(result, "includeChildren", "snapshot metadata"), includeCollaborators: bool(result, "includeCollaborators", "snapshot metadata"), sourceRevision: opaque(result, "sourceRevision", "snapshot metadata"), parserVersion: text(result, "parserVersion", "snapshot metadata"), pricingDigest: digest(result, "pricingDigest", "snapshot metadata"), formatterDigest: digest(result, "formatterDigest", "snapshot metadata"), observationTime: instant(result, "observationTime", "snapshot metadata"), mode: oneOf(result.mode, ["live", "sealed"] as const, "snapshot metadata.mode"), warnings: warningArray(result.warnings, "snapshot metadata.warnings"),
  };
}

function parseMetric(value: unknown, label: string): SummaryMetricDto {
  const result = exact(value, label, ["metricId", "label", "displayValue", "evidence", "description"]);
  return { metricId: opaque(result, "metricId", label), label: text(result, "label", label), displayValue: text(result, "displayValue", label), evidence: evidence(result.evidence, `${label}.evidence`), description: nullableText(result, "description", label) };
}

export function parseReportSummaryDto(value: unknown): ReportSummaryDto {
  scanBoundary(value);
  const result = record(value, "report summary");
  if (!Array.isArray(result.metricGroups) || !Array.isArray(result.recentActivity)) throw new Error("report summary collections are invalid");
  const timeRange = exact(result.timeRange, "report summary.timeRange", ["fromTime", "toTime"]);
  const groups = result.metricGroups.map((item, index): SummaryMetricGroupDto => {
    const label = `report summary.metricGroups[${index}]`;
    const group = exact(item, label, ["groupId", "label", "metrics"]);
    if (!Array.isArray(group.metrics)) throw new Error(`${label}.metrics is not an array`);
    return { groupId: oneOf(group.groupId, ["overview", "model", "context", "inference", "runtime", "waits", "work_items", "claims", "provenance"] as const, `${label}.groupId`), label: text(group, "label", label), metrics: group.metrics.map((metric, metricIndex) => parseMetric(metric, `${label}.metrics[${metricIndex}]`)) };
  });
  const recentActivity = result.recentActivity.map((item, index): SignificantActivityDto => {
    const label = `report summary.recentActivity[${index}]`;
    const activity = exact(item, label, ["eventId", "occurredAt", "label", "evidence"]);
    return { eventId: opaque(activity, "eventId", label), occurredAt: instant(activity, "occurredAt", label), label: text(activity, "label", label), evidence: evidence(activity.evidence, `${label}.evidence`) };
  });
  return {
    snapshotId: opaque(result, "snapshotId", "report summary"), revision: opaque(result, "revision", "report summary"), title: text(result, "title", "report summary"), goal: nullableText(result, "goal", "report summary"), state: text(result, "state", "report summary"), scopeLabel: text(result, "scopeLabel", "report summary"), observedAt: instant(result, "observedAt", "report summary"), live: bool(result, "live", "report summary"),
    timeRange: { fromTime: instant(timeRange, "fromTime", "report summary.timeRange"), toTime: instant(timeRange, "toTime", "report summary.timeRange") }, metricGroups: groups, recentActivity, warnings: warningArray(result.warnings, "report summary.warnings"),
  };
}

function parsePageBase<F, S, O extends CursorPageOperation, T>(value: unknown, expected: ExpectedPageBinding<F, S, O>, itemParser: (item: unknown, index: number) => T): CursorPageDto<T, F, S> {
  scanBoundary(value);
  const result = record(value, `${expected.operation} page`);
  if (result.snapshotId !== expected.snapshotId || result.revision !== expected.revision || result.operation !== expected.operation) throw new Error(`${expected.operation} page binding does not match the active request`);
  if (!boundedStructuralEqual(result.appliedFilters, expected.filters) || !boundedStructuralEqual(result.appliedSort, expected.sort)) throw new Error(`${expected.operation} page applied metadata does not match the active request`);
  const pageSize = count(result, "pageSize", `${expected.operation} page`);
  if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) throw new Error(`${expected.operation} page.pageSize is outside 1 through 500`);
  if (!Array.isArray(result.items) || result.items.length > pageSize) throw new Error(`${expected.operation} page.items exceeds pageSize`);
  return { snapshotId: expected.snapshotId, revision: expected.revision, operation: expected.operation, items: result.items.map(itemParser), appliedFilters: expected.filters, appliedSort: expected.sort, pageSize, nextCursor: result.nextCursor === null ? null : opaque(result, "nextCursor", `${expected.operation} page`) };
}

export function parseAgentPageDto(value: unknown, expected: ExpectedPageBinding<AgentFiltersDto, AgentSortDto, "list_agents">): CursorPageDto<AgentRowDto, AgentFiltersDto, AgentSortDto> {
  return parsePageBase(value, expected, (item, index) => {
    const label = `list_agents page.items[${index}]`; const row = exact(item, label, ["agentId", "nickname", "role", "state", "startedAt", "lastActivityAt", "turnCount", "eventCount"]);
    return { agentId: opaque(row, "agentId", label), nickname: nullableText(row, "nickname", label), role: nullableText(row, "role", label), state: text(row, "state", label), startedAt: nullableInstant(row, "startedAt", label), lastActivityAt: nullableInstant(row, "lastActivityAt", label), turnCount: count(row, "turnCount", label), eventCount: count(row, "eventCount", label) };
  });
}

export function parseTurnPageDto(value: unknown, expected: ExpectedPageBinding<TurnFiltersDto, TurnSortDto, "list_turns">): CursorPageDto<TurnRowDto, TurnFiltersDto, TurnSortDto> {
  return parsePageBase(value, expected, (item, index) => {
    const label = `list_turns page.items[${index}]`; const row = exact(item, label, ["turnId", "agentId", "startedAt", "endedAt", "state", "eventCount", "summary"]);
    return { turnId: opaque(row, "turnId", label), agentId: opaque(row, "agentId", label), startedAt: instant(row, "startedAt", label), endedAt: nullableInstant(row, "endedAt", label), state: text(row, "state", label), eventCount: count(row, "eventCount", label), summary: nullableText(row, "summary", label) };
  });
}

function chronological<T>(items: readonly T[], time: (item: T) => string, identity: (item: T) => string, label: string): void {
  for (let index = 1; index < items.length; index += 1) {
    const previous = items[index - 1]; const current = items[index];
    if (previous === undefined || current === undefined) continue;
    const timeOrder = time(previous).localeCompare(time(current));
    if (timeOrder > 0 || (timeOrder === 0 && identity(previous).localeCompare(identity(current)) > 0)) throw new Error(`${label} is not in stable chronological order`);
  }
}

export function parseEventPageDto(value: unknown, expected: ExpectedPageBinding<EventFiltersDto, EventSortDto, "list_events">): CursorPageDto<EventRowDto, EventFiltersDto, EventSortDto> {
  const page = parsePageBase(value, expected, (item, index): EventRowDto => {
    const label = `list_events page.items[${index}]`; const row = exact(item, label, ["eventId", "occurredAt", "agentId", "turnId", "kind", "label", "evidence", "sourceRef", "hasDetail"]);
    return { eventId: opaque(row, "eventId", label), occurredAt: instant(row, "occurredAt", label), agentId: parseNullableOpaque(row.agentId, "agentId", row, label), turnId: parseNullableOpaque(row.turnId, "turnId", row, label), kind: text(row, "kind", label), label: text(row, "label", label), evidence: evidence(row.evidence, `${label}.evidence`), sourceRef: parseNullableOpaque(row.sourceRef, "sourceRef", row, label), hasDetail: bool(row, "hasDetail", label) };
  });
  if (expected.sort.key === "occurred_at" && expected.sort.direction === "ascending") chronological(page.items, (item) => item.occurredAt, (item) => item.eventId, "list_events page.items");
  return page;
}

export function parseSequencePageDto(value: unknown, expected: ExpectedPageBinding<SequenceFiltersDto, SequenceSortDto, "query_sequence">): SequencePageDto {
  scanBoundary(value);
  const root = exact(value, "query_sequence result", ["page", "groups"]);
  const page = parsePageBase(root.page, expected, (item, index): SequenceRowDto => {
    const label = `query_sequence page.items[${index}]`; const row = exact(item, label, ["sequenceId", "groupId", "occurredAt", "fromAgentId", "fromAgentLabel", "toAgentId", "toAgentLabel", "kind", "label", "evidence", "eventId", "repeatCount", "reasoningAvailable"]);
    const repeatCount = count(row, "repeatCount", label); if (repeatCount < 1) throw new Error(`${label}.repeatCount must be positive`);
    return { sequenceId: opaque(row, "sequenceId", label), groupId: parseNullableOpaque(row.groupId, "groupId", row, label), occurredAt: instant(row, "occurredAt", label), fromAgentId: parseNullableOpaque(row.fromAgentId, "fromAgentId", row, label), fromAgentLabel: nullableText(row, "fromAgentLabel", label), toAgentId: parseNullableOpaque(row.toAgentId, "toAgentId", row, label), toAgentLabel: nullableText(row, "toAgentLabel", label), kind: text(row, "kind", label), label: text(row, "label", label), evidence: evidence(row.evidence, `${label}.evidence`), eventId: parseNullableOpaque(row.eventId, "eventId", row, label), repeatCount, reasoningAvailable: bool(row, "reasoningAvailable", label) };
  });
  if (!Array.isArray(root.groups) || root.groups.length > MAX_SEQUENCE_GROUPS) throw new Error("query_sequence page.groups is not bounded");
  const groups = root.groups.map((item, index): SequenceGroupDto => {
    const label = `query_sequence page.groups[${index}]`; const group = exact(item, label, ["groupId", "parentGroupId", "depth", "label", "collapsible"]);
    return { groupId: opaque(group, "groupId", label), parentGroupId: parseNullableOpaque(group.parentGroupId, "parentGroupId", group, label), depth: count(group, "depth", label), label: text(group, "label", label), collapsible: bool(group, "collapsible", label) };
  });
  const byId = new Map(groups.map((group) => [group.groupId, group]));
  if (byId.size !== groups.length) throw new Error("query_sequence page.groups contains duplicate identities");
  for (const group of groups) {
    if (group.parentGroupId !== null) {
      const parent = byId.get(group.parentGroupId); if (parent === undefined || parent.depth + 1 !== group.depth) throw new Error("query_sequence page.groups has an invalid hierarchy");
      const visited = new Set([group.groupId]); let cursor: SequenceGroupDto | undefined = parent;
      while (cursor !== undefined) { if (visited.has(cursor.groupId)) throw new Error("query_sequence page.groups contains a cycle"); visited.add(cursor.groupId); cursor = cursor.parentGroupId === null ? undefined : byId.get(cursor.parentGroupId); }
    } else if (group.depth !== 0) throw new Error("query_sequence page root group has nonzero depth");
  }
  if (page.items.some((row) => row.groupId !== null && !byId.has(row.groupId))) throw new Error("query_sequence page row references an unknown group");
  chronological(page.items, (item) => item.occurredAt, (item) => item.sequenceId, "query_sequence page.items");
  return { page: { ...page, operation: "query_sequence" }, groups };
}

export function parseCoordinationPageDto(value: unknown, expected: ExpectedPageBinding<CoordinationFiltersDto, CoordinationSortDto, "query_coordination">): CoordinationPageDto {
  const base = parsePageBase(value, expected, (item, index): CoordinationRowDto => {
    const label = `query_coordination page.items[${index}]`; const row = exact(item, label, ["coordinationId", "occurredAt", "workItemId", "delegatedRootId", "agentId", "operation", "label", "evidence", "eventId"]);
    return { coordinationId: opaque(row, "coordinationId", label), occurredAt: instant(row, "occurredAt", label), workItemId: parseNullableOpaque(row.workItemId, "workItemId", row, label), delegatedRootId: parseNullableOpaque(row.delegatedRootId, "delegatedRootId", row, label), agentId: parseNullableOpaque(row.agentId, "agentId", row, label), operation: text(row, "operation", label), label: text(row, "label", label), evidence: evidence(row.evidence, `${label}.evidence`), eventId: parseNullableOpaque(row.eventId, "eventId", row, label) };
  });
  chronological(base.items, (item) => item.occurredAt, (item) => item.coordinationId, "query_coordination page.items");
  return { ...base, operation: "query_coordination" };
}

export function parseHeatmapResultDto(value: unknown, expected: Readonly<Pick<HeatmapRequestDto, "snapshotId" | "fromTime" | "toTime" | "measure" | "groupBy" | "requestedResolutionMinutes" | "maximumRows">> & { readonly revision: string }): HeatmapResultDto {
  scanBoundary(value);
  const result = record(value, "heatmap result");
  for (const key of ["snapshotId", "revision", "fromTime", "toTime", "measure", "groupBy", "requestedResolutionMinutes", "maximumRows"] as const) if (result[key] !== expected[key]) throw new Error(`heatmap result.${key} does not match the active request`);
  if (!Array.isArray(result.rows) || result.rows.length > expected.maximumRows) throw new Error("heatmap result.rows exceeds maximumRows");
  const actualResolutionMinutes = finite(result, "actualResolutionMinutes", "heatmap result");
  if (!Number.isInteger(actualResolutionMinutes) || actualResolutionMinutes < expected.requestedResolutionMinutes) throw new Error("heatmap result.actualResolutionMinutes is invalid");
  const rows = result.rows.map((item, rowIndex): HeatmapRowDto => {
    const label = `heatmap result.rows[${rowIndex}]`; const row = exact(item, label, ["rowId", "label", "scale", "cells"]); const scale = exact(row.scale, `${label}.scale`, ["minimum", "maximum", "colorSemantic", "basis"]);
    const minimum = finite(scale, "minimum", `${label}.scale`); const maximum = finite(scale, "maximum", `${label}.scale`); const colorSemantic = oneOf(scale.colorSemantic, ["sequential_nonnegative", "diverging_signed"] as const, `${label}.scale.colorSemantic`); const basis = oneOf(scale.basis, ["visible_row_maximum", "context_window_capacity"] as const, `${label}.scale.basis`);
    if (minimum > maximum || (colorSemantic === "sequential_nonnegative" && minimum < 0) || (colorSemantic === "diverging_signed" && (minimum > 0 || maximum < 0))) throw new Error(`${label}.scale has an invalid domain`);
    if (!Array.isArray(row.cells)) throw new Error(`${label}.cells is not an array`);
    const cells = row.cells.map((cellValue, cellIndex): HeatmapCellDto => {
      const cellLabel = `${label}.cells[${cellIndex}]`; const cell = exact(cellValue, cellLabel, ["startTime", "endTime", "value", "count", "evidence", "primaryLabel", "secondaryLabel"]); const startTime = instant(cell, "startTime", cellLabel); const endTime = instant(cell, "endTime", cellLabel); if (startTime >= endTime || startTime < expected.fromTime || endTime > expected.toTime) throw new Error(`${cellLabel} is outside the requested half-open range`);
      const cellValueNumber = cell.value === null ? null : finite(cell, "value", cellLabel); if (cellValueNumber !== null && (cellValueNumber < minimum || cellValueNumber > maximum)) throw new Error(`${cellLabel}.value is outside its row scale`);
      return { startTime, endTime, value: cellValueNumber, count: count(cell, "count", cellLabel), evidence: evidence(cell.evidence, `${cellLabel}.evidence`), primaryLabel: text(cell, "primaryLabel", cellLabel), secondaryLabel: nullableText(cell, "secondaryLabel", cellLabel) };
    });
    for (let index = 1; index < cells.length; index += 1) if ((cells[index - 1]?.endTime ?? "") > (cells[index]?.startTime ?? "")) throw new Error(`${label}.cells overlap or are unordered`);
    return { rowId: opaque(row, "rowId", label), label: text(row, "label", label), scale: { minimum, maximum, colorSemantic, basis }, cells };
  });
  const totalCellCount = count(result, "totalCellCount", "heatmap result"); const actualCount = rows.reduce((total, row) => total + row.cells.length, 0);
  if (totalCellCount !== actualCount || totalCellCount > MAX_HEATMAP_CELLS) throw new Error("heatmap result.totalCellCount is invalid");
  const durationMinutes = (Date.parse(expected.toTime) - Date.parse(expected.fromTime)) / 60_000;
  if (rows.length > 0 && Math.ceil(durationMinutes / actualResolutionMinutes) * rows.length > MAX_HEATMAP_CELLS) throw new Error("heatmap result.actualResolutionMinutes does not satisfy coarsening");
  return { snapshotId: expected.snapshotId, revision: expected.revision, measure: expected.measure, groupBy: expected.groupBy, fromTime: expected.fromTime, toTime: expected.toTime, requestedResolutionMinutes: expected.requestedResolutionMinutes, actualResolutionMinutes, maximumRows: expected.maximumRows, omittedRowCount: count(result, "omittedRowCount", "heatmap result"), rowOrder: oneOf(result.rowOrder, ["activity_descending_id_ascending"] as const, "heatmap result.rowOrder"), totalCellCount, rows, provenance: stringArray(result.provenance, "heatmap result.provenance", MAX_WARNING_COUNT) };
}

export function parseEventDetailDto(value: unknown): EventDetailDto {
  scanBoundary(value);
  const result = record(value, "event detail");
  if (!Array.isArray(result.disclosures)) throw new Error("event detail.disclosures is not an array");
  const disclosures = result.disclosures.map((item, index): DisclosureDto => {
    const label = `event detail.disclosures[${index}]`; const disclosure = exact(item, label, ["label", "content", "redacted"]);
    return { label: text(disclosure, "label", label), content: text(disclosure, "content", label, { empty: true, maximum: MAX_DISCLOSURE_LENGTH }), redacted: bool(disclosure, "redacted", label) };
  });
  return { snapshotId: opaque(result, "snapshotId", "event detail"), revision: opaque(result, "revision", "event detail"), eventId: opaque(result, "eventId", "event detail"), occurredAt: instant(result, "occurredAt", "event detail"), kind: text(result, "kind", "event detail"), title: text(result, "title", "event detail"), evidence: evidence(result.evidence, "event detail.evidence"), provenance: stringArray(result.provenance, "event detail.provenance"), summary: nullableText(result, "summary", "event detail"), disclosures, sourceRef: parseNullableOpaque(result.sourceRef, "sourceRef", result, "event detail") };
}

export function parseExportSnapshotResultDto(value: unknown, expected: Readonly<Pick<ExportSnapshotRequestDto, "operationId" | "snapshotId" | "mode">> & { readonly revision: string }): ExportSnapshotResultDto {
  scanBoundary(value);
  const result = record(value, "export snapshot result");
  if (result.operationId !== expected.operationId || result.snapshotId !== expected.snapshotId || result.revision !== expected.revision || result.mode !== expected.mode) throw new Error("export snapshot result does not match the active request");
  if (!Array.isArray(result.omissions)) throw new Error("export snapshot result.omissions is not an array");
  const exportId = opaque(result, "exportId", "export snapshot result"); const displayName = text(result, "displayName", "export snapshot result");
  if (/[\\/]|^[A-Za-z][A-Za-z0-9+.-]*:/.test(displayName) || displayName === exportId) throw new Error("export snapshot result.displayName is not a bounded non-authority label");
  return { operationId: expected.operationId, snapshotId: expected.snapshotId, revision: expected.revision, exportId, displayName, mode: expected.mode, manifestSha256: nullableDigest(result, "manifestSha256", "export snapshot result"), fileCount: count(result, "fileCount", "export snapshot result"), totalByteCount: count(result, "totalByteCount", "export snapshot result"), warnings: warningArray(result.warnings, "export snapshot result.warnings"), omissions: result.omissions.map((item, index) => { const label = `export snapshot result.omissions[${index}]`; const omission = exact(item, label, ["section", "reason", "recovery"]); return { section: text(omission, "section", label), reason: text(omission, "reason", label), recovery: text(omission, "recovery", label) }; }) };
}

export function parseRefreshSnapshotResultDto(value: unknown, expectedSnapshotId: string): RefreshSnapshotResultDto {
  scanBoundary(value);
  const result = exact(value, "refresh snapshot result", ["changed", "snapshot"]);
  const snapshot = parseSnapshotMetadataDto(result.snapshot);
  if (snapshot.snapshotId !== expectedSnapshotId) throw new Error("refresh snapshot result does not match the active snapshot");
  return { changed: bool(result, "changed", "refresh snapshot result"), snapshot };
}

export function parseCloseSnapshotResultDto(value: unknown, expectedSnapshotId: string): CloseSnapshotResultDto {
  scanBoundary(value);
  const result = exact(value, "close snapshot result", ["snapshotId", "closed"]);
  if (result.snapshotId !== expectedSnapshotId) throw new Error("close snapshot result does not match the active snapshot");
  return { snapshotId: expectedSnapshotId, closed: bool(result, "closed", "close snapshot result") };
}

export function parseWorkspaceProgressDto(value: unknown, expectedOperationId: string, expectedOperation: ReportOperationName): WorkspaceProgressDto {
  scanBoundary(value);
  const result = record(value, "workspace progress");
  if (result.operationId !== expectedOperationId || result.operation !== expectedOperation) throw new Error("workspace progress identity does not match the active operation");
  const completed = count(result, "completed", "workspace progress"); const total = nullableCount(result, "total", "workspace progress");
  if (total !== null && completed > total) throw new Error("workspace progress is outside its total");
  return { protocolVersion: count(result, "protocolVersion", "workspace progress"), operationId: expectedOperationId, operation: expectedOperation, snapshotId: result.snapshotId === null ? null : opaque(result, "snapshotId", "workspace progress"), phase: text(result, "phase", "workspace progress"), completed, total, message: text(result, "message", "workspace progress") };
}
