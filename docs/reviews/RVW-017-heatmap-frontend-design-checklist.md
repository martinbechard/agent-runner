# RVW-017: Heatmap Frontend Design Evidence Review

## Review metadata

- Review target: Dynamic Workspace Heatmap
- Product, audience, and single job: Agent Report for engineering leads and agent operators; compare where runtime, token, and model activity occurred across time, then inspect the evidence behind a cell.
- Reviewer: `dev-ui-designer`
- Date: 2026-08-14
- Source revision: `d033754` with uncommitted workspace changes preserved
- Live URL or build: `http://127.0.0.1:1420/tests/browser/report-workspace.html`
- Viewports and states inspected: 1440×1000 desktop, 900×1000 tablet, 390×844 mobile; Wall time, Tokens, Models; populated, zero, incomplete, unavailable, selected-cell evidence, pressed mode/resolution, keyboard focus, horizontal overflow, mobile next-period control.
- Evidence directory: None. Per review scope, rendered observations are recorded directly in this checklist.

## Checklist

| ID | Criterion | Evidence | Score (0–4/N/A) | Finding or recommendation |
|---|---|---|---:|---|
| FD-01 | The product, audience, and interface's single job are concrete and visible in the design. | Live heading “Canonical Heatmap report,” Heatmap view label, mode labels, period labels, and cell evidence make comparison and inspection concrete. | 4 | Preserve the task-centred naming. |
| FD-02 | Visual choices arise from the product's subject matter, artifacts, or working context. | Dense time-by-activity matrix, exact duration/token values, agent/model labels, and evidence ledger reflect observability work rather than generic dashboard cards. | 4 | Preserve the operational matrix metaphor. |
| FD-03 | The interface avoids an interchangeable template identity. | The matrix, incomplete hatching/dashing, local-time headers, and evidence drill-in are specific; the surrounding shell is conventional but quiet. | 3 | Strengthen identity through a clearer Heatmap legend, not decoration. |
| FD-04 | The primary surface opens with a clear visual or functional thesis. | “Heatmap” leads directly into Mode, Period, range, and the matrix; no filler cards precede it. | 4 | Keep the matrix as the first analytical surface. |
| FD-05 | The strongest visual emphasis supports the user's primary task. | High-intensity cells and selected-cell evidence carry the strongest contrast; active navigation/mode states are also clear. | 4 | Add a scale legend so emphasis is interpretable, not merely salient. |
| FD-06 | Typography has deliberate roles for display, body, utility, or data content. | 24.8px view title, 20px report title, 16px controls/cells, and smaller row/legend utility text form distinct roles. | 3 | Raise the smallest row/legend text from roughly 10–12px toward 12–13px. |
| FD-07 | Type scale, weight, width, spacing, and line length form a coherent hierarchy. | Titles, fieldset legends, row labels, exact values, and evidence text are consistently tiered across all viewports. | 3 | Small utility text is too compressed for prolonged analytical use. |
| FD-08 | Typography contributes appropriate product character without reducing legibility. | Narrow/utility styling supports a technical instrument feel; exact values remain 16px in the live render. | 3 | Preserve data legibility while increasing secondary-text size and line height. |
| FD-09 | Color choices form a compact, intentional palette rather than arbitrary decoration. | Slate shell, paper surface, blue sequential cells, warm incomplete cells, amber selection, and neutral unavailable hatch form a compact palette. | 3 | Explain the warm versus blue scales and row-relative intensity in a persistent legend. |
| FD-10 | Color and type decisions are consistently derived from the visual direction. | The same slate/paper/amber language repeats through navigation, pressed controls, selection, and evidence. | 3 | Consolidate the mixed heatmap hue meaning into an explicit encoding system. |
| FD-11 | Layout structure communicates information priority and relationships. | Mode and Period precede range, matrix, then evidence; row and column headers bind values to activity and time. | 4 | Keep this analysis-first sequence. |
| FD-12 | Labels, dividers, numbering, and other structural devices encode real meaning. | “Mode,” “Period,” local-time columns, row labels, dashed incomplete treatment, and evidence divider all encode state or hierarchy. | 4 | Replace ambiguous visible “−/+” with labelled text or a labelled resolution cluster. |
| FD-13 | Alignment, rhythm, density, and whitespace match the intended visual character. | Desktop/tablet use a precise grid and compact 8–12px grouping; mobile controls wrap but remain aligned. | 3 | Give the desktop matrix more flexible column width and add clearer separation between mode, resolution, and range navigation. |
| FD-14 | Complexity is appropriate to the chosen direction and executed precisely. | Six Wall time rows, eight Token rows, and four Model rows remain scannable with direct values and evidence on demand. | 4 | Preserve progressive disclosure rather than exposing evidence for every cell. |
| FD-15 | One restrained signature element gives the interface a memorable identity. | The colour-and-pattern matrix with direct values is the signature element. | 3 | A persistent legend would complete the signature and make it teachable. |
| FD-16 | Decorative elements serve the brief and unnecessary accessories have been removed. | No decorative icons, gradients, shadows, illustration, or metric-card filler appears in the Heatmap surface. | 4 | Preserve the restraint. |
| FD-17 | Motion, if present, has a deliberate role and avoids scattered generic effects. | No decorative motion was observed; only state changes and horizontal navigation are functional. | 3 | Keep motion limited to spatial/state continuity if navigation is refined. |
| FD-18 | Reduced-motion behavior preserves clarity and usability. | Source CSS includes a `prefers-reduced-motion: reduce` rule that suppresses animation/transition duration and disables indeterminate motion. | 4 | Retain this global safeguard. |
| FD-19 | Responsive layouts preserve the design's hierarchy and character on mobile. | At 390×844 the title, Mode, Period, range, and matrix remain in order; the grid uses local horizontal scrolling with a 44px next control and no page-level overflow. | 2 | Replace the overlapping arrow with a dedicated range toolbar and show “Periods 1–2 of 4” or equivalent context. |
| FD-20 | Keyboard focus is visible and integrated with the visual system. | Programmatic keyboard focus on a grid cell produced a 3px solid visible outline with 1px offset; cells are native buttons with gridcell roles. | 4 | Verify the full arrow/tab order in a future assistive-technology pass. |
| FD-21 | Interface copy uses plain, user-recognizable terms rather than implementation language. | “Wall time,” “Tokens,” “Models,” “Incomplete,” “Unavailable,” and “Shown time uses…” are concrete user language. | 4 | Preserve the distinction between zero, incomplete, and unavailable. |
| FD-22 | Actions use active, consistent vocabulary across controls and feedback. | Refresh report and mode/period labels are consistent; icon controls have accessible labels “Use coarser periods,” “Use finer periods,” and “Next periods.” | 3 | Make the accessible coarser/finer wording visible instead of relying on −/+. |
| FD-23 | Empty and failure content explains what happened and directs the next action. | The populated fixture did not expose Heatmap empty/error screens; source has an empty message and retry-oriented error renderer, but they were not render-verified. | 2 | Add fixture routes or controls for render-backed empty, loading, error, and recovery review. |
| FD-24 | Labels, examples, supporting text, and controls each perform one clear job. | Fieldset legends label control groups; range text reports time; cells report values; evidence explains provenance. | 4 | Separate range navigation from resolution controls to remove the current conceptual overlap. |
| FD-25 | A rendered self-critique identified and corrected or documented generic, excessive, or inconsistent choices. | This render-backed review documents mobile overlay, touch-size, legend, typography, and control-group issues while preserving the matrix’s strong direct-value design. | 4 | Use these findings as the correction list for the next design pass. |

## Result

- Raw score: 87/100
- Applicable maximum: 100
- Critical visual defects: No blocking visual defect. Material issues are the missing persistent encoding legend and the mobile period-navigation overlay/context.
- Strong choices to preserve: Direct values in every cell; product-specific matrix; truthful zero/incomplete/unavailable treatments; restrained shell; selection evidence; semantic row/column organization.
- Recommended corrections, in priority order: (1) add a persistent legend explaining row-relative intensity and unavailable/partial patterns; (2) replace the mobile overlay arrow with a dedicated labelled range toolbar and visible period position; (3) enlarge the 28×28 coarsening controls and 32px mode controls for touch; (4) increase smallest utility text; (5) let desktop period columns expand into unused width.
- Evidence and verification gaps: No saved screenshots by instruction. Loading, empty, error, disabled-boundary, hover, high-contrast theme, zoom/reflow, and screen-reader announcements were not render-verified.
