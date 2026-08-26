// Copyright (c) 2026 Martin.Bechard@DevConsult.ca

import { describe, expect, it } from "vitest";

import type { HeatmapMatrixRowDto } from "../contracts";
import { heatmapMajorTick, heatmapRowRange, heatmapTimeLabel } from "./heatmap-view-model";

describe("React Heatmap view model", () => {
  it("formats compact time labels", () => {
    expect(heatmapTimeLabel("2026-08-12T12:05:00Z")).toMatch(/^\d{2}:05$/u);
  });

  it("describes row ranges from service-formatted values", () => {
    const row = {
      rowId: "wall-model-inference",
      rowKey: "model_inference",
      rowOrderIndex: 0,
      rowKind: "runtime_state",
      label: "Model inference",
      scale: { availability: "available", minimum: 0, maximum: 130_000, basis: "visible_row_maximum" },
      cells: [
        { startTime: "2026-08-12T12:00:00Z", endTime: "2026-08-12T12:05:00Z", value: 0, formattedValue: "0ms", valueState: "derived", applicableZero: true, contributingEvidenceCount: 1, normalizedIntensity: 0, supportingText: null },
        { startTime: "2026-08-12T12:05:00Z", endTime: "2026-08-12T12:10:00Z", value: 130_000, formattedValue: "2m 10s", valueState: "measured", applicableZero: false, contributingEvidenceCount: 1, normalizedIntensity: 1, supportingText: null },
      ],
    } satisfies HeatmapMatrixRowDto;
    expect(heatmapRowRange(row)).toBe("0ms–2m 10s");
  });

  it("labels 15-minute major ticks at five-minute resolution", () => {
    const result = { actualResolutionMinutes: 5 } as const;
    expect(heatmapMajorTick(0, result)).toBe(true);
    expect(heatmapMajorTick(1, result)).toBe(false);
    expect(heatmapMajorTick(3, result)).toBe(true);
  });
});
