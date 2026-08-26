// Copyright (c) 2026 Martin.Bechard@DevConsult.ca

import { createRoot } from "react-dom/client";

import type { HeatmapMatrixResultDto } from "../contracts";
import type { HeatmapInteractionState, HeatmapRenderActions } from "../report-workspace";
import { ReactHeatmap } from "./react-heatmap";

interface ReactHeatmapHostProps {
  readonly result: HeatmapMatrixResultDto;
  readonly presentation: HeatmapInteractionState;
  readonly actions: HeatmapRenderActions;
}

export function createReactHeatmapHost(props: ReactHeatmapHostProps): HTMLElement {
  const host = document.createElement("div");
  host.className = "block min-w-0";
  const root = createRoot(host);
  root.render(<ReactHeatmap {...props} />);
  queueMicrotask(() => {
    if (!host.isConnected) return;
    const observer = new MutationObserver(() => {
      if (host.isConnected) return;
      observer.disconnect();
      root.unmount();
    });
    observer.observe(document, { childList: true, subtree: true });
  });
  return host;
}
