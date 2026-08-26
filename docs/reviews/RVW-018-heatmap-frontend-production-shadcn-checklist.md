# RVW-018: Heatmap Frontend Production shadcn Evidence Review

## Review metadata

- Review target: Dynamic Workspace Heatmap
- Detected framework and component stack: Vanilla TypeScript, semantic HTML, repository CSS, Vite browser host, Tauri desktop application. No React, Tailwind CSS, or shadcn/ui is present.
- Applicability decision: Apply general production-interface, state, responsive, data-grid, accessibility, and maintainability criteria. Mark only shadcn-specific criterion FPS-11 and form-specific criterion FPS-23 N/A; do not treat repository CSS as Tailwind/shadcn.
- Reviewer: `dev-ui-designer`
- Date: 2026-08-14
- Source revision: `d033754` with uncommitted workspace changes preserved
- Live URL or build: `http://127.0.0.1:1420/tests/browser/report-workspace.html`
- Viewports and states inspected: 1440×1000, 900×1000, 390×844; Wall time, Tokens, Models; direct zero, incomplete, unavailable, active modes/resolution, selection/evidence, keyboard focus, horizontal grid navigation.
- Evidence directory: None. Rendered observations are recorded directly below.

## Checklist

| ID | Criterion | Evidence | Score (0–4/N/A) | Finding or recommendation |
|---|---|---|---:|---|
| FPS-01 | The UI supports a clear user, decision, primary action, and product goal. | The operator selects metric and period, compares time buckets, then selects a cell for evidence. | 4 | Preserve the clear compare-then-inspect workflow. |
| FPS-02 | Information architecture prioritizes usefulness rather than symmetry or filler. | Controls, range, matrix, and evidence appear in task order with no filler panels. | 4 | Keep evidence progressive rather than eager. |
| FPS-03 | Existing repository tokens, components, layout primitives, and conventions are followed. | Live surface uses the same slate/paper/amber shell, buttons, state panels, and workspace navigation as surrounding Agent Report views. | 4 | Continue using repository primitives; no new library is warranted. |
| FPS-04 | The visual system is restrained, credible, dense enough, and free of demo-page ornament. | No glass, blobs, fake metrics, card grid, gratuitous shadow, or decorative iconography; realistic operational values fill the matrix. | 4 | Preserve the instrument-like restraint. |
| FPS-05 | Spacing is systematic, tight but breathable, and appropriate to app versus marketing UI. | Controls use compact 4–8px gaps; panel groups use about 12px; cells are dense but readable. | 3 | Add more separation between the three control concepts without making the surface spacious. |
| FPS-06 | Radius is restrained and meaningful rather than applied indiscriminately. | Controls use about 4px and cells about 3px radius; major regions are bordered rather than pill-shaped. | 4 | Preserve. |
| FPS-07 | Borders, surfaces, spacing, and typography establish hierarchy without random shadows. | Shell, panel, labels, cells, selection, and evidence use borders/backgrounds; no random Heatmap shadows observed. | 4 | Preserve. |
| FPS-08 | Typography uses practical product scales with readable labels, metadata, and data. | Values and controls render at 16px, while row labels/legends descend to roughly 10–12px. | 3 | Increase smallest utility text to a comfortable 12–13px minimum. |
| FPS-09 | Semantic theme tokens govern color and status is never communicated by color alone. | Repository CSS variables govern shell colors; cells print values; incomplete adds text/dashed border; unavailable adds text/hatching; selection uses outline plus ARIA state. | 3 | Add a visible legend for scale semantics and migrate remaining literal colours into named Heatmap tokens. |
| FPS-10 | Components represent meaningful reusable structures and the UI avoids card wrappers everywhere. | One Heatmap panel contains control groups, grid, and evidence; there is no card-per-row/cell wrapper pattern. | 4 | Preserve. |
| FPS-11 | shadcn/ui primitives are used only where they add structure or accessible behavior. | Target does not use React, Tailwind, or shadcn/ui. | N/A | Stack-specific criterion; do not introduce shadcn solely to satisfy this checklist. |
| FPS-12 | Icons clarify an action, status, or navigation target and icon-only controls have names. | −, +, ‹, › are functional and expose labels such as “Use coarser periods” and “Next periods”; no decorative icons are present. | 3 | Show coarser/finer wording visibly and pair mobile arrows with range position. |
| FPS-13 | Populated views use realistic data including long, missing, pending, and failed values. | Fixture includes long row labels, exact values, zero, “Incomplete,” “Unavailable,” “Unknown model,” cost, and evidence prose. | 4 | Preserve these regression fixtures. |
| FPS-14 | Hover and active states are visible, subtle, and consistent for interactive elements. | Pressed mode/resolution controls use slate fill and white text; selected cell uses outline and evidence. Hover was not systematically inspected. | 3 | Add explicit hover verification to the browser fixture checklist. |
| FPS-15 | Every keyboard-operable control has a visible focus state. | Focused grid cell showed a 3px solid outline with offset; native buttons provide keyboard operability. | 4 | Verify focus order and every compact/overlay control, not just the grid cell. |
| FPS-16 | Loading preserves layout shape and communicates progress without avoidable shift. | Live fixture did not expose loading. Source renderer uses `aria-busy`, but stable Heatmap loading geometry was not rendered. | 2 | Add a deterministic loading fixture and reserve the final matrix footprint. |
| FPS-17 | Empty, error, disabled, and permission/read-only states are distinct and actionable. | Populated zero/incomplete/unavailable states were clear. Empty/error/disabled boundary states exist in source but were not exposed by this live host; permission state is not meaningful for this read-only analysis surface. | 2 | Add browser fixtures for empty, recoverable error, and disabled previous/next boundaries. |
| FPS-18 | Long content, missing values, overflow, and many-column cases are handled deliberately. | Long model/activity labels remain in fixed row headers; missing/unavailable values are explicit; the grid scrolls locally with no page-level overflow. | 4 | Keep local scrolling, but add position/context to mobile range navigation. |
| FPS-19 | Mobile is deliberately composed rather than a compressed desktop layout. | At 390px navigation collapses and controls wrap; period buttons become 54px high; grid remains a comparison surface. The overlaid next arrow and tiny 28px −/+ controls weaken the composition. | 2 | Use a dedicated mobile range toolbar and enlarge all compact controls. |
| FPS-20 | Tablet and desktop layouts use available space without cramped or uncontrolled stretching. | At 900px and 1440px the side navigation and analysis panel remain stable with no page overflow; fixed 96px live cell widths leave unused desktop space. | 3 | Use responsive period columns such as `minmax(96px, 1fr)` when the visible range fits. |
| FPS-21 | Component boundaries are specific, composable, typed, and maintainable. | Source separates Heatmap presentation helpers, cell accessible naming, evidence rendering, and controller interaction in typed TypeScript. | 3 | Consider extracting the large Heatmap renderer if future variants increase; current boundary is coherent. |
| FPS-22 | Tables and lists support comparison, selection, actions, responsive transformation, and state variants. | Semantic grid supports row/time comparison, native-button cells, selection, evidence, incomplete/unavailable/zero states, and local mobile scrolling. | 3 | Add a persistent legend and clearer mobile period position/navigation. |
| FPS-23 | Forms provide labels, validation, helper text, action hierarchy, and submission/error states. | The reviewed Heatmap has selectors and a numeric setting in some runtime configurations, but no data-entry form or submission workflow is present in this fixture. | N/A | Form-specific criterion is outside this surface. |
| FPS-24 | Semantic HTML, keyboard navigation, accessible names, headers, dialog titles, and associated errors are present. | Grid has an accessible mode name; rows, column headers, gridcell buttons, ARIA pressed/selected states, and detailed cell names expose mode, row, period, value, and state. | 4 | Complete a screen-reader/arrow-key pass to confirm practical reading order. |
| FPS-25 | Render checks and relevant build, lint, typecheck, or test evidence support completion. | Review used the live Vite host at three viewports and all three modes. No build/lint/test run was authorized or needed for this read-only evidence review. | 3 | For implementation closeout, add build, Vitest, and packaged Tauri render evidence. |

## Result

- Raw score: 77/92
- Applicable maximum: 92 (FPS-11 and FPS-23 excluded)
- Critical production defects: No blocking defect. Mobile control sizing/navigation and missing Heatmap legend are the material production-quality gaps.
- Strong choices to preserve: Real operational data; direct values; semantic grid/button structure; truthful data states; local overflow; restrained visual system; progressive evidence.
- Recommended corrections, in priority order: (1) dedicated mobile period toolbar with position; (2) enlarge 28px/32px controls for touch; (3) persistent scale/state legend; (4) improve smallest label typography; (5) add deterministic loading/empty/error/disabled fixtures; (6) use desktop width more fully.
- Evidence and verification gaps: No screenshots by instruction. Hover, full keyboard order, screen reader, zoom/reflow, measured contrast, loading, empty, recoverable error, disabled bounds, packaged Tauri, build, and automated tests were not exercised.
