---
name: extract-design-md
description: Extract and reconcile a source-grounded design system from an existing frontend codebase. Use when Codex must inventory visual language, tokens, typography, spacing, layout, responsive rules, component anatomy, states, or styling inconsistencies before creating or revising a canonical design-system artifact.
---

# Extract Design System from Frontend Source

Recover the design system that the application actually implements. Distinguish
deliberate conventions from drift, duplication, legacy choices, and isolated
exceptions. Do not invent a new visual direction during extraction.

## Inputs

- The target frontend source tree and package metadata
- Existing token, theme, CSS, component, and asset files
- Existing design or review records when available
- Rendered evidence when the application can be run

## Framework routing

Detect the styling stack from source and load exactly one matching reference:

- React, Next.js, or Tailwind: `references/react-tailwind.md`
- Vue or Nuxt: `references/vue.md`
- Svelte or SvelteKit: `references/svelte.md`
- Angular: `references/angular.md`
- Plain CSS, Sass, Less, or framework-neutral styles: `references/plain-css.md`

Do not assume Tailwind, a component library, or a token framework merely
because the application is web-based.

## Workflow

### 1. Establish source authority

Identify the files that govern the rendered interface: package and build
configuration, global styles, CSS custom properties, theme or token files,
component styles, layout primitives, media queries, and font/icon assets.

Treat centralized theme and token definitions as intended design authority.
Treat rendered output and repeated component usage as shipped behavior. Record
conflicts between intent and implementation instead of silently choosing one.

### 2. Extract raw evidence

Inventory exact values and source locations for:

- colors and opacity
- font families, sizes, weights, line heights, and letter spacing
- spacing, sizing, radii, borders, shadows, and elevation
- layout widths, grids, breakpoints, sticky regions, and overflow behavior
- transition durations, easing, and reduced-motion behavior
- focus, hover, active, selected, disabled, loading, empty, error, permission,
  partial, and unavailable states
- icons, data visualizations, and product-specific visual encodings

Group near-duplicate values but retain their original locations so later
reconciliation is evidence-based.

### 3. Reconstruct semantic intent

Map raw values to functional roles: foundations and surfaces; content and
border hierarchy; accents and actions; statuses; typography roles; layout
roles; and component variants. For every inferred role, cite source evidence
and state confidence. Do not turn a one-off value into a canonical token
without repeated use or explicit design authority.

### 4. Analyze core components

For each core generic and product-specific component, record purpose, anatomy,
variants, sizes, states, content and overflow constraints, responsive
transformation, accessibility behavior, and current inconsistencies.

### 5. Judge current versus dated choices

Separate findings into deliberate choices to preserve, sound choices needing
consistent application, dated choices that no longer support the product,
accessibility or usability defects, and unresolved choices requiring product
input. Base “dated” judgments on user impact, contemporary platform
expectations, and product fit—not trend novelty alone.

### 6. Produce the extraction report

Use the repository's file-placement mechanism before writing. Include product
context, source authority, raw values with locations, reconstructed semantics,
typography/layout/motion/responsive findings, component/state inventory,
consistency gaps, dated-choice assessment, preserved strengths, recommended
reconciliation, and verification gaps.

The extraction report is evidence for a design-system decision; it is not
permission to change source files.

## Quality gate

- Every material claim cites source or rendered evidence.
- Intended authority and shipped behavior are distinguished.
- Near-duplicates and one-off values are identified.
- Responsive and interaction states are covered.
- Product-specific components are included.
- “Dated” is justified by product impact rather than taste alone.
- Missing evidence and unresolved decisions are explicit.

## Provenance

Adapted for project-local Codex use from Google Labs' Apache-2.0
`stitch::extract-design-md` Agent Skill. This version removes Stitch tooling and
output-path assumptions while preserving source-extraction methods.
