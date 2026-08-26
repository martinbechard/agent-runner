// Copyright (c) 2026 Martin.Bechard@DevConsult.ca

import type {
  HeatmapMatrixCellDto,
  HeatmapMatrixResultDto,
  HeatmapMatrixRowDto,
} from "../contracts";
import type { HeatmapSelectedCell } from "../report-workspace";

export function heatmapTimeLabel(isoInstant: string): string {
  const instant = new Date(isoInstant);
  if (isoInstant === "" || Number.isNaN(instant.getTime())) throw new Error("Heatmap time is not a valid ISO instant.");
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false }).format(instant);
}

export function heatmapRangeLabel(fromTime: string, toTime: string): string {
  const from = new Date(fromTime);
  const to = new Date(toTime);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) throw new Error("Heatmap range is not valid.");
  const day = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(from);
  const zone = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" }).formatToParts(from).find((part) => part.type === "timeZoneName")?.value;
  return `${day} · ${heatmapTimeLabel(fromTime)}–${heatmapTimeLabel(toTime)}${zone === undefined ? "" : ` ${zone}`}`;
}

export function heatmapRowRange(row: HeatmapMatrixRowDto): string {
  if (row.scale.availability === "unavailable") return "Capacity unavailable";
  const values = row.cells.filter((cell) => cell.value !== null).map((cell) => cell.value as number);
  if (values.length === 0) return "No values";
  const minimumCell = row.cells.find((cell) => cell.value === Math.min(...values));
  const maximumCell = row.cells.find((cell) => cell.value === Math.max(...values));
  if (minimumCell === undefined || maximumCell === undefined) return "No values";
  const compact = (value: string) => value.replace(/^Partial · /u, "");
  return minimumCell.formattedValue === maximumCell.formattedValue
    ? `Flat ${compact(minimumCell.formattedValue)}`
    : `${compact(minimumCell.formattedValue)}–${compact(maximumCell.formattedValue)}`;
}

export function heatmapSelection(
  row: HeatmapMatrixRowDto,
  cell: HeatmapMatrixCellDto,
): HeatmapSelectedCell {
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

export function heatmapMajorTick(index: number, result: Pick<HeatmapMatrixResultDto, "actualResolutionMinutes">): boolean {
  const labelEveryMinutes = result.actualResolutionMinutes <= 5 ? 15 : result.actualResolutionMinutes;
  return (index * result.actualResolutionMinutes) % labelEveryMinutes === 0;
}
