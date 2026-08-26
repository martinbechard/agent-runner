---
name: design-system
description: Create, revise, implement, and validate complete frontend design systems using primitive, semantic, and component tokens; typography, spacing, layout, responsive, motion, data-visualization, component-state, accessibility, governance, and migration contracts. Use when Codex must turn an approved visual direction or extracted UI evidence into a durable system that keeps an application consistent.
---

# Design System

Turn approved product and visual decisions into a durable implementation
contract. Use extracted source evidence and rendered review findings as inputs;
do not infer a new brand direction from generic defaults.

## Required inputs

- Product, audience, and primary workflows
- Approved visual direction and choices to preserve
- Source-grounded extraction or equivalent evidence
- Current frontend stack and existing token/component conventions
- Accessibility and platform requirements

If the visual direction is unresolved, establish it with the applicable design
skill before defining canonical tokens.

## Token architecture

Use three explicit layers:

```text
primitive values
    ↓
semantic purpose aliases
    ↓
component-specific contracts
```

Load references progressively:

- `references/token-architecture.md` for naming, aliasing, and theme structure
- `references/primitive-tokens.md` for raw scales
- `references/semantic-tokens.md` for purpose-based roles
- `references/component-tokens.md` for component contracts
- `references/component-specs.md` for anatomy and specification format
- `references/states-and-variants.md` for interaction and data states
- `references/tailwind-integration.md` only when Tailwind is actually present

Do not expose primitive values directly in product components when a semantic
role exists. Do not create component tokens that merely rename one hardcoded
value without representing a stable component decision.

## System coverage

Define all applicable areas:

1. **Foundations** — color, opacity, typography, spacing, sizing, radii,
   borders, shadows/elevation, icons, and motion.
2. **Semantic roles** — surfaces, content hierarchy, borders, actions, focus,
   selection, status, partial data, unavailable data, and data visualization.
3. **Layout** — content widths, grids, density, breakpoints, sticky behavior,
   overflow, and responsive transformations.
4. **Components** — purpose, anatomy, variants, sizes, states, content rules,
   responsive behavior, accessibility, and usage boundaries.
5. **Product-specific visualization** — scales, legends, units, comparison
   semantics, selection, uncertainty, unavailable values, and evidence detail.
6. **Content** — terminology, capitalization, action labels, validation,
   empty/error guidance, and numeric formatting.
7. **Governance** — source of truth, allowed extension process, validation,
   ownership, and change review. Keep migration status in a separate artifact.

## Workflow

### 0. Discover the current authority

Before creating an artifact:

1. Use the repository's file-placement mechanism and inspect its design-system
   category when one exists.
2. Search the selected design roots for `DS-*`, design-system titles, token
   authorities, component specifications, visualization specifications, and
   migration ledgers.
3. Inspect the stack-owned token or global-style source and completed UI review
   evidence.
4. Build an authority map naming the canonical system document, optional child
   specifications, executable token source, review evidence, and superseded
   material.

Update a suitable existing authority. Never create a second canonical design
system for the same product or surface. When relocating a misclassified
authority, preserve its creation provenance and update inbound links; do not
represent the move as a new design decision.

### 1. Reconcile extraction evidence

Classify every material existing value as preserve, alias, consolidate,
replace, deprecate, or retain as a documented exception. Record the rationale
and affected consumers.

### 2. Define foundations and semantic tokens

Choose coherent scales with explicit names, values, purposes, supported
themes, and accessibility constraints. Prefer a small complete system to a
large speculative catalog.

### 3. Specify components and states

For every core component, define purpose and anatomy; variants and sizes;
content constraints; applicable interaction and data states; keyboard and
assistive-technology behavior; responsive behavior; tokens consumed; and
prohibited ad hoc values.

### 4. Define product-specific visualizations

For data displays, specify quantitative scale semantics, legends, units,
direct values or tooltips, accessible non-color encodings, comparison limits,
selection behavior, and uncertainty or unavailable-data treatment.

### 5. Plan migration separately

Create or update a separate conformance-and-migration artifact. Map current values and components to the new contract. Order changes so token
introduction, shared primitives, product components, and page cleanup can be
verified incrementally. Preserve intentional behavior and avoid broad visual
rewrites without rendered comparison.

### 6. Implement when authorized

Keep source-of-truth tokens in the stack's existing canonical style location.
Use `scripts/generate-tokens.cjs` only when JSON-to-CSS generation fits the
repository. Use `scripts/validate-tokens.cjs` as a starting point for
hardcoded-value audits, adapting it instead of assuming its defaults are right.

### 7. Verify

- Inspect representative desktop, tablet, and mobile renders.
- Exercise applicable interaction and data states.
- Check contrast, focus visibility, keyboard behavior, reduced motion, zoom,
  overflow, and touch targets.
- Run relevant build, lint, typecheck, component, and end-to-end checks.
- Search for deprecated values and undocumented component-local overrides.
- Record intentional exceptions and residual verification gaps.

## Canonical artifact contract

Use the repository's file-placement mechanism before creating the artifact.
The complete design-system suite must include:

1. Purpose, principles, and product character
2. Source authority and maintenance ownership
3. Primitive, semantic, and component token tables
4. Typography, spacing, layout, responsive, motion, and icon rules
5. Component specifications and state matrices
6. Data-visualization rules
7. Accessibility requirements
8. Content and terminology rules
9. Live visual specimens for the whole applicable product surface
10. Validation and change-governance process

Use `templates/rendered-html-suite/` for a new canonical authority. Its HTML
index and linked pages are the target-state authority and must be directly
browsable without a build step. Use
`templates/design-system-conformance-migration.md` for current-state gaps and
migration status; never mix those notes into target-state specimens.

## Artifact selection and templates

Create the smallest durable set that keeps one clear authority:

| Artifact | Create when | Template |
|---|---|---|
| Canonical design system | Always, unless a suitable authority already exists | `templates/rendered-html-suite/` |
| Component specification | A reusable or product-critical component needs more detail than the canonical document can carry clearly | `templates/component-specification.md` |
| Visualization specification | A chart or data display has non-trivial scale, uncertainty, comparison, selection, or evidence semantics | `templates/visualization-specification.md` |
| Conformance and migration ledger | When implementation does not yet conform fully | `templates/design-system-conformance-migration.md` |

The canonical document owns product character, foundations, shared rules, and
governance. Child specifications elaborate it and cannot silently override it.
Review artifacts are evidence, not design authority. Executable token files
remain in the frontend stack's canonical source location rather than under the
documentation tree.

When the repository defines design-system filename prefixes, follow them. In
this repository, the taxonomy uses `DS-NNN`, `DSC-NNN`, and `DSV-NNN`; other
repositories may choose different names through their placement authority.

Repository-local discovery and placement:

| Concern | Search/create location |
|---|---|
| Canonical product design system | `docs/design/system/DS-NNN-<product-or-surface>/index.html` |
| Conformance and migration | `docs/design/system/conformance/DSM-NNN-<product-or-surface>-conformance-and-migration.md` |
| Detailed component specification | `docs/design/system/components/DSC-NNN-<component>.md` |
| Detailed visualization specification | `docs/design/system/visualizations/DSV-NNN-<visualization>.md` |
| Executable tokens | Existing owning frontend token/global-style path |
| Completed review evidence | `docs/reviews/RVW-NNN-<scope>.md` |

Search the canonical parent location first, then linked child specifications,
then executable source, and finally review evidence. Do not infer design
authority from the newest review file.

## Completion criteria

- Tokens cover current product needs without undocumented raw-value escape
  hatches.
- Components reference semantic or component roles consistently.
- Responsive and state behavior is specified and render-verified.
- Data visualization has explicit scale and non-color semantics.
- Accessibility requirements are testable.
- Existing values have a migration or exception disposition.
- Future changes have an ownership and validation path.

## Provenance

Adapted for project-local Codex use from the MIT-licensed UI UX Pro Max
`design-system` skill. This version removes presentation-generation material
and focuses on application design-system creation and governance.
