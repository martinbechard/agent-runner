# Agent Report Design-System Conformance and Migration

## Purpose

This document tracks changes required for the Agent Report implementation to conform to the target-state [Agent Report Design System](../DS-001-agent-report/index.html). It records current gaps, priorities, affected surfaces, delivery order, and verification evidence. It does not define or override the visual target.

Status: **ACTIVE**. Target design-system version: **1.0.0**.

## Conformance baseline

The current application already provides a strong technical-instrument character, semantic HTML controls, explicit values in analytical cells, durable partial/unavailable treatments, accessible names, pressed states, and compact evidence ledgers. The largest whole-app consistency risks are literal styling values, uneven control grouping and sizing, insufficiently standardized state panels, and responsive behavior that varies by surface.

## Update ledger

| ID | Priority | Current implementation gap | Target design-system rule | Affected surfaces | Required update | Verification evidence | Status |
|---|---|---|---|---|---|---|---|
| DSM-001-01 | P1 | Legacy and literal colors, spacing, type sizes, radii, and timings coexist | Foundations use primitive, semantic, and component roles | Entire desktop app | Consolidate shared roles in `styles.css`; retain compatibility aliases only while consumed | Token audit plus desktop/mobile render comparison | In progress |
| DSM-001-02 | P1 | Control clusters vary in hierarchy and some compact actions rely on symbol recognition | Forms follow task order, use visible group labels, and meet target floors | Catalog scope/search, workspace header, Heatmap, paging, export | Normalize primary/secondary hierarchy, labels, grouping, focus, disabled/loading states | Keyboard pass and 390px target-size inspection | In progress |
| DSM-001-03 | P1 | Responsive behavior is surface-specific; some analytical content underuses wide space or clips narrow units | Shell has defined wide, constrained, and narrow transformations | Catalog, run browser, workspace nav, tables, Heatmap, dialogs | Apply shared breakpoints, bounded content, internal data overflow, 44px narrow controls | 1440px, 900px, 390px and 200% zoom matrix | In progress |
| DSM-001-04 | P1 | Heatmap scale interpretation was implicit and mobile paging overlaid data | Visible row-relative legend, labelled state key, separate visible-range controls | Dynamic Heatmap | Preserve implemented legend/control corrections and complete responsive paging behavior | Populated/selected/partial/unavailable renders in all modes | Mostly complete |
| DSM-001-05 | P2 | Loading, empty, error, cancelled, stale, partial, and unavailable presentations are implemented through several local patterns | Shared state semantics and recovery hierarchy | Catalog, every workspace query, export, detail, diagnostics | Standardize state panel anatomy, wording, prior-content preservation, and recovery actions | Fixture coverage for every state family | Planned |
| DSM-001-06 | P2 | Tables and ledgers share broad styling but lack one explicit density/overflow contract | 40px compact or 48px standard rows, aligned numbers, sticky headers where useful | Run browser, sequence, agents, turns, tools, model, context, waits, claims, provenance, diagnostics, evidence | Consolidate table/ledger selectors and numeric/identifier alignment | Representative wide/narrow table render and keyboard inspection | Planned |
| DSM-001-07 | P2 | Summary metrics, panel boundaries, and workspace composition use partially overlapping local conventions | Metrics and panels use shared anatomy and semantic borders | Summary, coordination, catalog statistics, report status | Normalize metric hierarchy and panel grouping without card proliferation | Visual diff across catalog and workspace | Planned |
| DSM-001-08 | P2 | Dialog styling and error placement vary between preflight, detail, and export flows | Dialogs share title, viewport, focus, error, and action anatomy | Preflight, event detail, export reopen | Consolidate dialog tokens and verify focus trap/restore and narrow viewport bounds | Keyboard and 390px dialog checks | Planned |
| DSM-001-09 | P2 | Persistent metadata can fall below the target reading floor | Persistent metadata ≥12px/1.35; body 14px | Row metadata, date summaries, control labels, Heatmap labels, diagnostics | Replace undersized text and tighten hierarchy through weight/color instead | Measured computed styles and contrast audit | In progress |
| DSM-001-10 | P3 | Static export and dynamic workspace do not yet share a reviewed semantic visual contract | Product semantics remain consistent across render targets without identical layout | Static export and Dynamic Workspace | Map colors, states, tables, terminology, and evidence semantics across both | Static/dynamic parity review | Planned |

## Delivery sequence

1. Establish semantic token roles and compatibility aliases in the existing global stylesheet.
2. Normalize shell, controls, focus, type floors, and responsive target sizes.
3. Consolidate panels, metrics, tables, ledgers, and state feedback.
4. Complete Heatmap range paging and remaining render-state coverage.
5. Standardize dialogs, exports, diagnostics, and static/dynamic semantics.
6. Run the whole-app conformance matrix and retain a new review artifact.

## Required verification matrix

- Viewports: 1440px desktop, 900px constrained desktop/tablet, 390px mobile, and 200% zoom/reflow.
- Input: pointer, full keyboard order, focus restoration, and Heatmap grid keys.
- Data: populated, selected, empty, partial, unavailable, loading, stale, cancelled, recoverable error, terminal error, and export/reopen states.
- Surfaces: catalog/search, run browser, workspace shell, all 17 registered workspace surfaces, dialogs, diagnostics, and static export.
- Accessibility: measured contrast, visible focus, target sizes, reduced motion, accessible names, live progress, and screen-reader spot checks.
- Engineering: relevant TypeScript tests, production build, link check for the design-system suite, and literal-token audit with documented exceptions.

## Completion rule

An item becomes complete only when its implementation is merged and its listed evidence is retained. When every item is complete, preserve this file as the 1.0.0 conformance baseline; subsequent system revisions receive a new `DSM-*` artifact rather than rewriting historical evidence.
