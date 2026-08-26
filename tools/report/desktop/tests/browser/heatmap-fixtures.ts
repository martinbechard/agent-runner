// Copyright (c) 2026 Martin.Bechard@DevConsult.ca

import type {
  HeatmapCellEvidenceResultDto,
  HeatmapMatrixCellDto,
  HeatmapMatrixRequestDto,
  HeatmapMatrixResultDto,
  HeatmapMatrixRowDto,
  HeatmapMode,
  HeatmapRequestedResolutionMinutes,
  PreflightReportDto,
  ReportSummaryDto,
  SnapshotMetadataDto,
} from "../../src/contracts";

export const FIXTURE_ROOT_ID = "fixture-root-heatmap";
export const FIXTURE_SNAPSHOT_ID = "fixture-snapshot-heatmap";
export const FIXTURE_REVISION = "fixture-revision-1";
export const FIXTURE_SOURCE_REVISION = "fixture-source-revision-1";
export const FIXTURE_FROM_TIME = "2026-08-12T12:00:00Z";
export const FIXTURE_TO_TIME = "2026-08-12T16:00:00Z";
export const FIXTURE_AGENT_LABEL = "default (Trace Heatmap examples) · gpt-5.6-sol · effort high";

export const PREFLIGHT_FIXTURE = Object.freeze({
  preflightToken: "fixture-preflight-token",
  rootThreadId: FIXTURE_ROOT_ID,
  includeChildren: false,
  includeCollaborators: false,
  sourceRevision: FIXTURE_SOURCE_REVISION,
  logCount: 1,
  totalBytes: 48_640,
  childCount: 0,
  collaboratorCount: 0,
  cachedFileCount: 1,
  changedFileCount: 0,
  knownEventCount: 24,
  warnings: [],
} satisfies PreflightReportDto);

export const SNAPSHOT_FIXTURE = Object.freeze({
  protocolVersion: 1,
  snapshotId: FIXTURE_SNAPSHOT_ID,
  revision: FIXTURE_REVISION,
  rootThreadId: FIXTURE_ROOT_ID,
  includeChildren: false,
  includeCollaborators: false,
  sourceRevision: FIXTURE_SOURCE_REVISION,
  parserVersion: "fixture-parser-1",
  pricingDigest: "a".repeat(64),
  formatterDigest: "b".repeat(64),
  observationTime: "2026-08-12T12:21:00Z",
  mode: "live",
  warnings: [],
} satisfies SnapshotMetadataDto);

export const SUMMARY_FIXTURE = Object.freeze({
  snapshotId: FIXTURE_SNAPSHOT_ID,
  revision: FIXTURE_REVISION,
  title: "Canonical Heatmap report",
  goal: "Verify the interactive Report UI",
  state: "complete",
  scopeLabel: "Selected task",
  observedAt: SNAPSHOT_FIXTURE.observationTime,
  live: true,
  timeRange: { fromTime: FIXTURE_FROM_TIME, toTime: FIXTURE_TO_TIME },
  metricGroups: [{
    groupId: "overview",
    label: "Overview",
    metrics: [{ metricId: "events", label: "Events", displayValue: "24", evidence: "measured", description: null }],
  }],
  recentActivity: [],
  warnings: [],
} satisfies ReportSummaryDto);

interface Period {
  readonly startTime: string;
  readonly endTime: string;
}

interface CellValue {
  readonly value: number | null;
  readonly formattedValue: string;
  readonly valueState: HeatmapMatrixCellDto["valueState"];
  readonly applicableZero?: boolean;
  readonly normalizedIntensity: number | null;
  readonly supportingText?: string | null;
}

function periods(fromTime: string, toTime: string, minutes: HeatmapRequestedResolutionMinutes): readonly Period[] {
  const from = Date.parse(fromTime);
  const to = Date.parse(toTime);
  const width = minutes * 60_000;
  const result: Period[] = [];
  for (let cursor = from; cursor < to; cursor += width) {
    result.push({ startTime: new Date(cursor).toISOString(), endTime: new Date(Math.min(to, cursor + width)).toISOString() });
  }
  return result;
}

function cells(periodValues: readonly Period[], values: readonly CellValue[]): readonly HeatmapMatrixCellDto[] {
  return periodValues.map((period, index) => {
    const item = values[index % values.length];
    if (item === undefined) throw new Error("Heatmap fixture requires at least one value.");
    return Object.freeze({
      ...period,
      value: item.value,
      formattedValue: item.formattedValue,
      valueState: item.valueState,
      applicableZero: item.applicableZero ?? false,
      contributingEvidenceCount: item.valueState === "unavailable" ? 0 : 1,
      normalizedIntensity: item.normalizedIntensity,
      supportingText: item.supportingText ?? null,
    });
  });
}

function row(
  rowId: string,
  rowKey: string,
  rowOrderIndex: number,
  rowKind: HeatmapMatrixRowDto["rowKind"],
  label: string,
  scale: HeatmapMatrixRowDto["scale"],
  periodValues: readonly Period[],
  values: readonly CellValue[],
): HeatmapMatrixRowDto {
  return Object.freeze({ rowId, rowKey, rowOrderIndex, rowKind, label, scale, cells: cells(periodValues, values) });
}

const wallValues = Object.freeze([
  { value: 130_000, formattedValue: "2m 10s", valueState: "measured", normalizedIntensity: 0.537 },
  { value: 242_000, formattedValue: "Partial · 4m 2s", valueState: "partial", normalizedIntensity: 1 },
  { value: 0, formattedValue: "0ms", valueState: "derived", applicableZero: true, normalizedIntensity: 0 },
  { value: null, formattedValue: "Unavailable", valueState: "unavailable", normalizedIntensity: null },
] satisfies readonly CellValue[]);

function wallRows(periodValues: readonly Period[]): readonly HeatmapMatrixRowDto[] {
  const scale = { availability: "available", minimum: 0, maximum: 242_000, basis: "visible_row_maximum" } as const;
  return Object.freeze([
    row("wall-model-inference", "model_inference", 0, "runtime_state", "Model inference", scale, periodValues, wallValues),
    row("wall-tool-execution", "tool_execution", 1, "runtime_state", "Tool execution", scale, periodValues, [
      { value: 34_000, formattedValue: "34s", valueState: "derived", normalizedIntensity: 0.14 },
      { value: 71_000, formattedValue: "1m 11s", valueState: "derived", normalizedIntensity: 0.293 },
    ]),
  ]);
}

const visibleScale = { availability: "available", minimum: 0, maximum: 1_200_000, basis: "visible_row_maximum" } as const;
const contextScale = { availability: "available", minimum: 0, maximum: 128_000, basis: "context_window_capacity" } as const;

function tokenRows(periodValues: readonly Period[]): readonly HeatmapMatrixRowDto[] {
  return Object.freeze([
    row("token-uncached", "uncached_input_tokens", 0, "token_measure", "Uncached input", visibleScale, periodValues, [
      { value: 12_400, formattedValue: "12.4K", valueState: "measured", normalizedIntensity: 0.01 },
      { value: 0, formattedValue: "0", valueState: "derived", applicableZero: true, normalizedIntensity: 0 },
    ]),
    row("token-cached", "cached_input_tokens", 1, "token_measure", "Cached input", visibleScale, periodValues, [{ value: 1_200_000, formattedValue: "1.2M", valueState: "derived", normalizedIntensity: 1 }]),
    row("token-reasoning", "reasoning_tokens", 2, "token_measure", "Reasoning", visibleScale, periodValues, [{ value: 8_750, formattedValue: "8.8K", valueState: "derived", normalizedIntensity: 0.007 }]),
    row("token-output", "output_tokens", 3, "token_measure", "Output", visibleScale, periodValues, [{ value: 2_480, formattedValue: "2.5K", valueState: "derived", normalizedIntensity: 0.002 }]),
    row("token-tools", "tool_calls", 4, "token_measure", "Tool calls", visibleScale, periodValues, [{ value: 1_200, formattedValue: "1,200", valueState: "derived", normalizedIntensity: 1 }]),
    row("token-context-average", "context_average", 5, "token_measure", "Context size (avg)", contextScale, periodValues, [{ value: 64_000, formattedValue: "50%\n64K", valueState: "derived", normalizedIntensity: 0.5 }]),
    row("token-context-maximum", "context_maximum", 6, "token_measure", "Context size (max)", contextScale, periodValues, [{ value: 96_000, formattedValue: "75%\n96K", valueState: "measured", normalizedIntensity: 0.75 }]),
    row("token-cost", "cost", 7, "cost", "Cost", visibleScale, periodValues, [
      { value: 0.0075, formattedValue: "Partial · $0.0075", valueState: "partial", normalizedIntensity: 1 },
      { value: 0, formattedValue: "$0.00", valueState: "derived", applicableZero: true, normalizedIntensity: 0 },
    ]),
  ]);
}

function modelRows(periodValues: readonly Period[]): readonly HeatmapMatrixRowDto[] {
  return Object.freeze([
    row("model-sol-high", "model:0123456789abcdef01234567", 0, "model", "gpt-5.6-sol · effort high", visibleScale, periodValues, [{ value: 128_400, formattedValue: "128.4K", valueState: "derived", normalizedIntensity: 1 }]),
    row("model-terra-medium", "model:89abcdef0123456701234567", 1, "model", "gpt-5.6-terra · effort medium", visibleScale, periodValues, [{ value: 42_100, formattedValue: "42.1K", valueState: "derived", normalizedIntensity: 0.328 }]),
    row("model-unknown", "model:fedcba9876543210fedcba98", 2, "model", "Unknown model", visibleScale, periodValues, [{ value: null, formattedValue: "Unavailable", valueState: "unavailable", normalizedIntensity: null }]),
    row("model-cost", "cost", 3, "cost", "Cost", visibleScale, periodValues, [{ value: 0.0192, formattedValue: "$0.02", valueState: "derived", normalizedIntensity: 1 }]),
  ]);
}

export function buildHeatmapMatrix(
  request: HeatmapMatrixRequestDto,
  options: Readonly<{ coarsen?: boolean; unknownCapacity?: boolean }> = {},
): HeatmapMatrixResultDto {
  const actualResolutionMinutes = options.coarsen && request.requestedResolutionMinutes < 5
    ? 5
    : request.requestedResolutionMinutes;
  const periodValues = periods(request.fromTime, request.toTime, actualResolutionMinutes);
  let rows = request.mode === "wall_time" ? wallRows(periodValues) : request.mode === "tokens" ? tokenRows(periodValues) : modelRows(periodValues);
  if (request.mode === "tokens" && options.unknownCapacity) {
    rows = rows.map((candidate) => candidate.rowKey === "context_maximum" ? Object.freeze({
      ...candidate,
      scale: { availability: "unavailable", reason: "context_capacity_unavailable" } as const,
      cells: candidate.cells.map((cell) => Object.freeze({
        ...cell,
        value: null,
        formattedValue: "N/A",
        valueState: "unavailable" as const,
        applicableZero: false,
        contributingEvidenceCount: 1,
        normalizedIntensity: null,
        supportingText: "88K tokens observed",
      })),
    }) : candidate);
  }
  return Object.freeze({
    snapshotId: FIXTURE_SNAPSHOT_ID,
    revisionId: FIXTURE_REVISION,
    queryKind: "matrix",
    mode: request.mode,
    fromTime: request.fromTime,
    toTime: request.toTime,
    requestedResolutionMinutes: request.requestedResolutionMinutes,
    actualResolutionMinutes,
    maximumRows: request.maximumRows,
    omittedRowCount: 0,
    rowOrder: request.mode === "wall_time" ? "runtime_state_contract" : request.mode === "tokens" ? "token_contract" : "model_first_occurrence_then_cost",
    totalCellCount: rows.reduce((total, candidate) => total + candidate.cells.length, 0),
    rows,
    provenance: ["Synthetic canonical browser verification fixture"],
  });
}

export function buildHeatmapEvidence(
  mode: HeatmapMode,
  rowValue: HeatmapMatrixRowDto,
  cell: HeatmapMatrixCellDto,
  omittedEvidenceCount = 0,
): HeatmapCellEvidenceResultDto {
  const capacityUnavailable = rowValue.scale.availability === "unavailable";
  return Object.freeze({
    snapshotId: FIXTURE_SNAPSHOT_ID,
    revisionId: FIXTURE_REVISION,
    queryKind: "cell_evidence",
    mode,
    rowId: rowValue.rowId,
    rowKey: rowValue.rowKey,
    rowOrderIndex: rowValue.rowOrderIndex,
    rowLabel: rowValue.label,
    periodStartTime: cell.startTime,
    periodEndTime: cell.endTime,
    value: cell.value,
    formattedValue: cell.formattedValue,
    valueState: cell.valueState,
    applicableZero: cell.applicableZero,
    evidenceItems: [{
      eventId: "fixture-event-1",
      occurredAt: cell.startTime,
      value: capacityUnavailable ? 88_000 : cell.value,
      formattedValue: capacityUnavailable ? "88K tokens observed" : cell.formattedValue,
      durationMs: mode === "wall_time" && cell.value !== null ? cell.value : null,
      label: FIXTURE_AGENT_LABEL,
      preview: "Synthetic bounded evidence preview",
      evidenceMethod: capacityUnavailable ? "measured" as const : cell.value === null ? "unavailable" as const : "measured" as const,
      valueState: capacityUnavailable ? "measured" : cell.valueState,
      hasDetail: true,
    }],
    omittedEvidenceCount,
    provenance: ["Synthetic canonical browser verification fixture"],
  } satisfies HeatmapCellEvidenceResultDto);
}
