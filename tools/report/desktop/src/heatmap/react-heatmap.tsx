// Copyright (c) 2026 Martin.Bechard@DevConsult.ca

import { useMemo, useState, type CSSProperties, type KeyboardEvent, type MouseEvent } from "react";

import type {
  HeatmapCellEvidenceResultDto,
  HeatmapMatrixCellDto,
  HeatmapMatrixResultDto,
  HeatmapMatrixRowDto,
  HeatmapMode,
  HeatmapRequestedResolutionMinutes,
} from "../contracts";
import {
  HEATMAP_MODES,
  HEATMAP_RESOLUTIONS,
  heatmapCellAccessibleName,
  heatmapCellPresentation,
  type HeatmapInteractionState,
  type HeatmapRenderActions,
  type LoadState,
} from "../report-workspace";
import {
  heatmapMajorTick,
  heatmapRangeLabel,
  heatmapRowRange,
  heatmapSelection,
  heatmapTimeLabel,
} from "./heatmap-view-model";
import "./heatmap.css";

const LABEL_WIDTH = 208;
const CELL_WIDTH = 58;
const CELL_GAP = 1;

interface ReactHeatmapProps {
  readonly result: HeatmapMatrixResultDto;
  readonly presentation: HeatmapInteractionState;
  readonly actions: HeatmapRenderActions;
}

interface ActiveCell {
  readonly row: HeatmapMatrixRowDto;
  readonly cell: HeatmapMatrixCellDto;
  readonly rowIndex: number;
  readonly columnIndex: number;
}

interface HeatmapRowGroup {
  readonly id: string;
  readonly label: string;
  readonly rows: readonly HeatmapMatrixRowDto[];
}

function groupRows(result: HeatmapMatrixResultDto): readonly HeatmapRowGroup[] {
  if (result.mode === "wall_time") return [{ id: "activity", label: "Activity", rows: result.rows }];
  if (result.mode === "models") {
    const cost = result.rows.filter((row) => row.rowKind === "cost");
    return [
      { id: "models", label: "Models", rows: result.rows.filter((row) => row.rowKind !== "cost") },
      ...(cost.length === 0 ? [] : [{ id: "cost", label: "Cost", rows: cost }]),
    ];
  }
  const tokens = result.rows.filter((row) => !row.rowKey.startsWith("context_") && row.rowKind !== "cost");
  const context = result.rows.filter((row) => row.rowKey.startsWith("context_"));
  const cost = result.rows.filter((row) => row.rowKind === "cost");
  return [
    { id: "tokens", label: "Tokens", rows: tokens },
    { id: "context", label: "Context window", rows: context },
    { id: "cost", label: "Cost", rows: cost },
  ].filter((group) => group.rows.length > 0);
}

function currentEvidence(state: LoadState<HeatmapCellEvidenceResultDto>): HeatmapCellEvidenceResultDto | null {
  if (state.kind === "ready" || state.kind === "empty" || state.kind === "stale") return state.value;
  if (state.kind === "loading" || state.kind === "error" || state.kind === "cancelled") return state.previous;
  return null;
}

function selectedCell(result: HeatmapMatrixResultDto, presentation: HeatmapInteractionState): ActiveCell | null {
  const selected = presentation.selectedCell;
  if (selected === null) return null;
  const rowIndex = result.rows.findIndex((row) => row.rowId === selected.rowId);
  const row = result.rows[rowIndex];
  if (row === undefined) return null;
  const columnIndex = row.cells.findIndex((cell) => cell.startTime === selected.periodStartTime && cell.endTime === selected.periodEndTime);
  const cell = row.cells[columnIndex];
  return cell === undefined ? null : { row, cell, rowIndex, columnIndex };
}

function HeatLegend(): React.JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[var(--ink-muted)]" aria-label="Heatmap legend">
      <span className="flex items-center gap-1.5">
        Low
        <span className="h-2.5 w-16 rounded-full bg-[linear-gradient(to_right,var(--heat-low),var(--heat-high))]" aria-hidden="true" />
        High <span className="opacity-70">per row</span>
      </span>
      <span className="flex items-center gap-1.5">
        <span className="relative size-3 rounded-[2px] bg-[var(--heat-flat)]" aria-hidden="true">
          <span className="absolute right-0 top-0 size-0 border-l-[5px] border-t-[5px] border-l-transparent border-t-[var(--heat-flag)]" />
        </span>
        Partial
      </span>
      <span className="flex items-center gap-1.5">
        <span className="react-heatmap-hatch inline-block size-3 rounded-[2px]" aria-hidden="true" />
        Unavailable
      </span>
    </div>
  );
}

function CellReadout({ active, pinned }: { readonly active: ActiveCell | null; readonly pinned: boolean }): React.JSX.Element {
  if (active === null) {
    return <div className="flex h-9 items-center border-y border-dashed border-[var(--line)] px-3 text-xs text-[var(--ink-muted)]">Hover or focus a cell to inspect it. Click to pin its evidence.</div>;
  }
  const state = active.cell.valueState === "partial" ? "Partial evidence" : active.cell.valueState === "unavailable" ? "Unavailable" : null;
  return (
    <div className="flex min-h-9 flex-wrap items-center gap-x-3 gap-y-1 border-y border-[var(--line)] px-3 py-1.5 text-xs">
      <strong className="font-semibold">{active.row.label}</strong>
      <span className="font-mono text-[var(--ink-muted)]">{heatmapTimeLabel(active.cell.startTime)}–{heatmapTimeLabel(active.cell.endTime)}</span>
      <span className="font-mono font-semibold">{active.cell.formattedValue}</span>
      {state === null ? null : <span className="text-[var(--amber)]">{state}</span>}
      <span className="ml-auto text-[11px] text-[var(--ink-muted)]">{pinned ? "Pinned" : "Preview"}</span>
    </div>
  );
}

function EvidencePanel({ state, actions }: { readonly state: LoadState<HeatmapCellEvidenceResultDto>; readonly actions: HeatmapRenderActions }): React.JSX.Element | null {
  const evidence = currentEvidence(state);
  if (state.kind === "not-requested") return null;
  if (state.kind === "loading" && evidence === null) return <section className="border-t border-[var(--line)] pt-3 text-sm text-[var(--ink-muted)]" aria-busy="true">Loading evidence…</section>;
  if (state.kind === "error" && evidence === null) return <section className="border-t border-[var(--danger)] pt-3 text-sm text-[var(--danger)]" role="alert">{state.error.message}</section>;
  if (evidence === null) return null;
  return (
    <section className="border-t border-[var(--line)] pt-3" aria-label="Selected cell evidence">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold">{evidence.rowLabel} evidence</h3>
        <span className="font-mono text-[11px] text-[var(--ink-muted)]">{heatmapTimeLabel(evidence.periodStartTime)}–{heatmapTimeLabel(evidence.periodEndTime)} · {evidence.formattedValue}</span>
        {state.kind === "loading" ? <span className="text-[11px] text-[var(--ink-muted)]">Refreshing…</span> : null}
      </div>
      <div className="overflow-x-auto border-y border-[var(--line)]">
        <table className="w-full min-w-[640px] border-collapse text-left text-xs">
          <thead className="bg-[var(--heat-muted-surface)] text-[var(--ink-muted)]">
            <tr><th className="px-3 py-2 font-medium">Time</th><th className="px-3 py-2 font-medium">Source</th><th className="px-3 py-2 font-medium">Value</th><th className="px-3 py-2 font-medium">Method</th><th className="px-3 py-2 font-medium">Detail</th></tr>
          </thead>
          <tbody>
            {evidence.evidenceItems.map((item, index) => (
              <tr key={`${item.eventId ?? "evidence"}-${index}`} className="border-b border-[color-mix(in_srgb,var(--line)_45%,transparent)] last:border-b-0">
                <td className="whitespace-nowrap px-3 py-2 font-mono text-[var(--ink-muted)]">{heatmapTimeLabel(item.occurredAt)}</td>
                <td className="max-w-[320px] px-3 py-2">{item.label}{item.preview === null ? null : <span className="block truncate text-[var(--ink-muted)]">{item.preview}</span>}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono">{item.formattedValue}</td>
                <td className="whitespace-nowrap px-3 py-2 text-[var(--ink-muted)]">{item.evidenceMethod}</td>
                <td className="px-3 py-2">{item.hasDetail && item.eventId !== null ? <button type="button" className="text-[var(--signal)] underline-offset-2 hover:underline" onClick={(event) => actions.openDetail(item.eventId ?? "", event.currentTarget)}>View detail</button> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {evidence.omittedEvidenceCount > 0 ? <p className="mt-2 text-xs text-[var(--ink-muted)]">{evidence.omittedEvidenceCount} additional records omitted.</p> : null}
    </section>
  );
}

function SegmentedControls({ result, actions }: Pick<ReactHeatmapProps, "result" | "actions">): React.JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div role="tablist" aria-label="Measure" className="flex items-center gap-0.5 rounded-md border border-[var(--line)] bg-[var(--heat-surface)] p-0.5">
        {HEATMAP_MODES.map((mode) => <button key={mode.value} type="button" role="tab" aria-selected={result.mode === mode.value} className={`rounded-[3px] px-2.5 py-1 text-xs font-medium transition-colors ${result.mode === mode.value ? "bg-[var(--slate)] text-white" : "text-[var(--ink-muted)] hover:text-[var(--ink)]"}`} onClick={() => actions.setMode(mode.value)}>{mode.label}</button>)}
      </div>
      <div role="radiogroup" aria-label="Resolution" className="flex items-center gap-0.5 rounded-md border border-[var(--line)] bg-[var(--heat-surface)] p-0.5">
        {HEATMAP_RESOLUTIONS.map((resolution) => <button key={resolution} type="button" role="radio" aria-checked={result.requestedResolutionMinutes === resolution} className={`rounded-[3px] px-2 py-1 font-mono text-xs transition-colors ${result.requestedResolutionMinutes === resolution ? "bg-[var(--slate)] text-white" : "text-[var(--ink-muted)] hover:text-[var(--ink)]"}`} onClick={() => actions.setResolution(resolution as HeatmapRequestedResolutionMinutes)}>{resolution}m</button>)}
      </div>
      <span className="font-mono text-[11px] text-[var(--ink-muted)]">{result.rows[0]?.cells.length ?? 0} cols · {heatmapRangeLabel(result.fromTime, result.toTime)}</span>
    </div>
  );
}

function cellStyle(cell: HeatmapMatrixCellDto): CSSProperties {
  if (cell.valueState === "unavailable" || cell.normalizedIntensity === null) return {};
  return { backgroundColor: `color-mix(in oklch, var(--heat-high) ${Math.round(cell.normalizedIntensity * 100)}%, var(--heat-low))` };
}

export function ReactHeatmap({ result, presentation, actions }: ReactHeatmapProps): React.JSX.Element {
  const [hovered, setHovered] = useState<ActiveCell | null>(null);
  const [showValues, setShowValues] = useState(true);
  const pinned = useMemo(() => selectedCell(result, presentation), [result, presentation]);
  const active = hovered ?? pinned;
  const groups = useMemo(() => groupRows(result), [result]);

  function onCellKeyDown(event: KeyboardEvent<HTMLButtonElement>, rowIndex: number, columnIndex: number): void {
    const keyOffsets: Partial<Record<string, readonly [number, number]>> = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] };
    const offset = keyOffsets[event.key];
    if (offset === undefined) return;
    event.preventDefault();
    const target = event.currentTarget.closest(".react-heatmap-grid")?.querySelector<HTMLButtonElement>(`button[data-row-index="${rowIndex + offset[0]}"][data-column-index="${columnIndex + offset[1]}"]`);
    target?.focus();
  }

  return (
    <section className="react-heatmap flex min-w-0 flex-col gap-3" aria-label="Activity heatmap">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedControls result={result} actions={actions} />
        <div className="flex flex-wrap items-center gap-4"><HeatLegend /><label className="flex cursor-pointer items-center gap-2 text-xs text-[var(--ink-muted)]"><input type="checkbox" checked={showValues} onChange={(event) => setShowValues(event.currentTarget.checked)} className="size-3.5 accent-[var(--slate)]" />Values</label></div>
      </div>
      <CellReadout active={active} pinned={hovered === null && pinned !== null} />
      <div className="react-heatmap-grid overflow-x-auto rounded-lg border border-[var(--line)] bg-[var(--heat-surface)]" onMouseLeave={() => setHovered(null)}>
        <div className="w-max min-w-full py-3 pr-3">
          <div className="flex items-end pb-1.5">
            <div className="sticky left-0 z-20 shrink-0 self-stretch bg-[var(--heat-surface)]" style={{ width: LABEL_WIDTH }} aria-hidden="true" />
            {(result.rows[0]?.cells ?? []).map((cell, index) => <div key={cell.startTime} className={`flex shrink-0 flex-col items-center gap-0.5 font-mono text-[10px] ${active?.columnIndex === index ? "text-[var(--ink)]" : "text-[var(--ink-muted)]"}`} style={{ width: CELL_WIDTH, marginRight: CELL_GAP }}>{heatmapMajorTick(index, result) ? <span>{heatmapTimeLabel(cell.startTime)}</span> : null}<span className={`w-px ${heatmapMajorTick(index, result) ? "h-2.5" : "h-1.5"} ${active?.columnIndex === index ? "bg-[var(--ink)]" : "bg-[var(--line)]"}`} aria-hidden="true" /></div>)}
          </div>
          {groups.map((group) => <div key={group.id} className="mt-1">
            <div className="flex items-end"><div className="sticky left-0 z-20 shrink-0 bg-[var(--heat-surface)] pb-1 pl-3 pt-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]" style={{ width: LABEL_WIDTH }}>{group.label}</div><div className="mb-0.5 grow border-b border-[color-mix(in_srgb,var(--line)_60%,transparent)]" /></div>
            {group.rows.map((row) => {
              const rowIndex = result.rows.findIndex((candidate) => candidate.rowId === row.rowId);
              return <div key={row.rowId} className="flex items-center py-px"><div className="sticky left-0 z-20 flex shrink-0 items-baseline justify-between gap-2 self-stretch overflow-hidden bg-[var(--heat-surface)] pl-3 pr-3" style={{ width: LABEL_WIDTH }}><span className="min-w-0 truncate text-xs">{row.label}</span><span className="max-w-[92px] shrink-0 truncate font-mono text-[10px] text-[var(--ink-muted)]">{heatmapRowRange(row)}</span></div>{row.cells.map((cell, columnIndex) => {
                const selected = pinned?.row.rowId === row.rowId && pinned.columnIndex === columnIndex;
                const activeCell = active?.row.rowId === row.rowId && active.columnIndex === columnIndex;
                const presentationCell = heatmapCellPresentation(row.scale, cell);
                const style = cellStyle(cell);
                return <button key={cell.startTime} type="button" role="gridcell" data-row-index={rowIndex} data-column-index={columnIndex} aria-selected={selected} aria-label={heatmapCellAccessibleName(result.mode, row.label, cell, row.scale, selected)} className={`relative h-8 shrink-0 overflow-hidden rounded-[2px] outline-offset-1 transition-[box-shadow] ${cell.valueState === "unavailable" ? "react-heatmap-hatch bg-transparent" : ""} ${selected ? "ring-2 ring-[var(--signal)]" : activeCell ? "ring-1 ring-[var(--ink)]/60" : ""}`} style={{ ...style, width: CELL_WIDTH, marginRight: CELL_GAP }} onMouseEnter={() => setHovered({ row, cell, rowIndex, columnIndex })} onFocus={() => setHovered({ row, cell, rowIndex, columnIndex })} onBlur={() => setHovered(null)} onClick={() => actions.select(heatmapSelection(row, cell))} onDoubleClick={() => actions.drillDown()} onContextMenu={(event: MouseEvent<HTMLButtonElement>) => { event.preventDefault(); actions.stepBack(); }} onKeyDown={(event) => onCellKeyDown(event, rowIndex, columnIndex)}>{cell.valueState === "partial" ? <span className="absolute right-0 top-0 size-0 border-l-[7px] border-t-[7px] border-l-transparent border-t-[var(--heat-flag)]" aria-hidden="true" /> : null}{showValues && cell.valueState !== "unavailable" ? <span className="pointer-events-none absolute inset-0 flex items-center justify-center px-0.5 font-mono text-[9px] font-medium leading-none" style={{ color: (cell.normalizedIntensity ?? 0) > 0.42 ? "var(--heat-value-dark)" : "var(--ink-muted)" }}>{presentationCell.visibleValue}</span> : null}</button>;
              })}</div>;
            })}
          </div>)}
        </div>
      </div>
      <EvidencePanel state={presentation.evidence} actions={actions} />
      {result.omittedRowCount > 0 ? <p className="text-xs text-[var(--ink-muted)]">Showing {result.rows.length} rows; {result.omittedRowCount} omitted.</p> : null}
    </section>
  );
}
