// Copyright (c) 2026 Martin.Bechard@DevConsult.ca

import type {
  HeatmapCellEvidenceRequestDto,
  HeatmapMatrixRequestDto,
  HeatmapMode,
  ReportErrorDto,
} from "../../src/contracts";
import type { WorkspaceCommandName, WorkspaceTransport } from "../../src/report-workspace";
import {
  FIXTURE_FROM_TIME,
  FIXTURE_REVISION,
  FIXTURE_SNAPSHOT_ID,
  FIXTURE_TO_TIME,
  PREFLIGHT_FIXTURE,
  SNAPSHOT_FIXTURE,
  SUMMARY_FIXTURE,
  buildHeatmapEvidence,
  buildHeatmapMatrix,
} from "./heatmap-fixtures";

export type FixtureScenario = "success" | "query-error" | "refresh-conflict" | "coarsened" | "unknown-capacity" | "omitted-evidence";

interface RequestRecord {
  readonly operationId?: unknown;
  readonly snapshotId?: unknown;
  readonly queryKind?: unknown;
  readonly fromTime?: unknown;
  readonly toTime?: unknown;
  readonly mode?: unknown;
  readonly requestedResolutionMinutes?: unknown;
  readonly maximumRows?: unknown;
  readonly rowId?: unknown;
  readonly periodStartTime?: unknown;
  readonly periodEndTime?: unknown;
}

function requestRecord(value: unknown): RequestRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("Fixture request must be an object.");
  return value;
}

function resolutionField(value: unknown): HeatmapMatrixRequestDto["requestedResolutionMinutes"] {
  if (value === 1 || value === 5 || value === 15 || value === 30 || value === 60) return value;
  throw new Error("Fixture requestedResolutionMinutes is invalid.");
}

function maximumRowsField(value: unknown): number {
  if (typeof value === "number" && Number.isSafeInteger(value) && value >= 1 && value <= 200) return value;
  throw new Error("Fixture maximumRows is invalid.");
}

function stringField(value: unknown, label: string): string {
  if (typeof value !== "string" || value === "") throw new Error(`Fixture ${label} must be a non-empty string.`);
  return value;
}

function reportError(code: ReportErrorDto["code"], message: string, operationId: string | null): ReportErrorDto {
  return Object.freeze({ code, message, operationId, recoverable: true, currentSourceRevision: null, preflightRequired: false, restartFromFirstPage: false });
}

export class FixtureWorkspaceTransport implements WorkspaceTransport {
  private scenario: FixtureScenario = "success";
  private lastMatrices = new Map<HeatmapMode, ReturnType<typeof buildHeatmapMatrix>>();
  readonly calls: { readonly command: WorkspaceCommandName; readonly request: unknown }[] = [];

  setScenario(scenario: FixtureScenario): void {
    this.scenario = scenario;
  }

  subscribeProgress(): () => void {
    return () => undefined;
  }

  async invoke(command: WorkspaceCommandName, request: unknown): Promise<unknown> {
    this.calls.push(Object.freeze({ command, request }));
    const input = requestRecord(request);
    const operationId = typeof input.operationId === "string" ? input.operationId : null;
    if (command === "preflight_report") return PREFLIGHT_FIXTURE;
    if (command === "open_snapshot") return SNAPSHOT_FIXTURE;
    if (command === "get_summary") return SUMMARY_FIXTURE;
    if (command === "close_snapshot") return { snapshotId: FIXTURE_SNAPSHOT_ID, closed: true };
    if (command === "refresh_snapshot") {
      if (this.scenario === "refresh-conflict") throw reportError("REPORT_SNAPSHOT_CONFLICT", "The fixture snapshot changed during refresh.", operationId);
      return { changed: false, snapshot: SNAPSHOT_FIXTURE };
    }
    if (command !== "query_snapshot_time_range") throw reportError("REPORT_INVALID_REQUEST", `Fixture command ${command} is not available.`, operationId);
    if (this.scenario === "query-error") throw reportError("REPORT_UNAVAILABLE", "The canonical Heatmap fixture is temporarily unavailable.", operationId);
    if (input.queryKind === "matrix") {
      const mode = stringField(input.mode, "mode");
      if (mode !== "wall_time" && mode !== "tokens" && mode !== "models") throw new Error("Fixture mode is invalid.");
      const requestDto = {
        operationId: stringField(input.operationId, "operationId"),
        snapshotId: stringField(input.snapshotId, "snapshotId"),
        queryKind: "matrix",
        fromTime: stringField(input.fromTime, "fromTime"),
        toTime: stringField(input.toTime, "toTime"),
        mode,
        requestedResolutionMinutes: resolutionField(input.requestedResolutionMinutes),
        maximumRows: maximumRowsField(input.maximumRows),
      } satisfies HeatmapMatrixRequestDto;
      const matrix = buildHeatmapMatrix(requestDto, {
        coarsen: this.scenario === "coarsened",
        unknownCapacity: this.scenario === "unknown-capacity",
      });
      this.lastMatrices.set(mode, matrix);
      return matrix;
    }
    if (input.queryKind === "cell_evidence") {
      const mode = stringField(input.mode, "mode");
      if (mode !== "wall_time" && mode !== "tokens" && mode !== "models") throw new Error("Fixture mode is invalid.");
      const requestDto = {
        operationId: stringField(input.operationId, "operationId"),
        snapshotId: stringField(input.snapshotId, "snapshotId"),
        queryKind: "cell_evidence",
        mode,
        rowId: stringField(input.rowId, "rowId"),
        periodStartTime: stringField(input.periodStartTime, "periodStartTime"),
        periodEndTime: stringField(input.periodEndTime, "periodEndTime"),
      } satisfies HeatmapCellEvidenceRequestDto;
      const matrix = this.lastMatrices.get(mode) ?? buildHeatmapMatrix({
        operationId: requestDto.operationId,
        snapshotId: requestDto.snapshotId,
        queryKind: "matrix",
        fromTime: FIXTURE_FROM_TIME,
        toTime: FIXTURE_TO_TIME,
        mode,
        requestedResolutionMinutes: 5,
        maximumRows: 100,
      }, { unknownCapacity: this.scenario === "unknown-capacity" });
      const row = matrix.rows.find((candidate) => candidate.rowId === requestDto.rowId);
      const cell = row?.cells.find((candidate) => candidate.startTime === requestDto.periodStartTime && candidate.endTime === requestDto.periodEndTime);
      if (row === undefined || cell === undefined) throw reportError("REPORT_NOT_FOUND", "The fixture Heatmap cell was not found.", operationId);
      return buildHeatmapEvidence(mode, row, cell, this.scenario === "omitted-evidence" ? 101 : 0);
    }
    throw reportError("REPORT_INVALID_REQUEST", "The fixture Heatmap query kind is invalid.", operationId);
  }
}
