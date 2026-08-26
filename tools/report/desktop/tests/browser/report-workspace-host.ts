// Copyright (c) 2026 Martin.Bechard@DevConsult.ca

import type { ReportWorkspaceController, WorkspaceElements } from "../../src/report-workspace";
import { createReportWorkspace } from "../../src/report-workspace";
import "../../src/styles.css";
import { FixtureWorkspaceTransport, type FixtureScenario } from "./fixture-workspace-transport";
import { FIXTURE_ROOT_ID } from "./heatmap-fixtures";

function element<T extends HTMLElement>(id: string): T {
  const value = document.getElementById(id);
  if (!(value instanceof HTMLElement)) throw new Error(`Missing fixture host element ${id}.`);
  return value as T;
}

function dialog(id: string): HTMLDialogElement {
  const value = document.getElementById(id);
  if (!(value instanceof HTMLDialogElement)) throw new Error(`Missing fixture host dialog ${id}.`);
  return value;
}

const elements: WorkspaceElements = {
  catalogRegion: element("catalog-workspace"),
  workspaceRegion: element("report-workspace"),
  preflightDialog: dialog("report-preflight-dialog"),
  navigation: element("report-workspace-nav"),
  viewHeading: element("report-view-heading"),
  viewRegion: element("report-view"),
  statusRegion: element("report-view-status"),
  progressRegion: element("report-progress"),
  detailDialog: dialog("report-detail-dialog"),
};

const transport = new FixtureWorkspaceTransport();
const controller = createReportWorkspace(elements, transport);

export interface ReportBrowserTestHost {
  readonly controller: ReportWorkspaceController;
  readonly transport: FixtureWorkspaceTransport;
  setScenario(scenario: FixtureScenario): void;
}

declare global {
  interface Window {
    __reportTest: ReportBrowserTestHost;
  }
}

window.__reportTest = Object.freeze({
  controller,
  transport,
  setScenario(scenario: FixtureScenario) { transport.setScenario(scenario); },
});

element<HTMLButtonElement>("fixture-refresh").addEventListener("click", () => { void controller.refreshSnapshot(); });

async function boot(): Promise<void> {
  const trigger = element<HTMLHeadingElement>("report-view-heading");
  controller.selectRoot({ rootThreadId: FIXTURE_ROOT_ID, title: "Canonical Heatmap report", includeChildren: false, includeCollaborators: false }, trigger);
  await controller.preflight();
  await controller.openSnapshot();
  await controller.navigate("heatmap");
  document.body.dataset.reportFixtureReady = "true";
}

void boot().catch((error: unknown) => {
  document.body.dataset.reportFixtureError = error instanceof Error ? error.message : "Unknown fixture host error";
});
