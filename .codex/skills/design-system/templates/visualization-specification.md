# [Visualization] Design-System Visualization Specification

## Authority And Analytical Job

- Governing design system: [DS link]
- Product/data contract: [requirement or design link]
- Implemented source: [path]
- User question answered: [single analytical job]

## Data And Comparison Contract

| Concern | Contract |
|---|---|
| Measures and units | [values] |
| Scale and domain | [linear/log/ordinal/relative; bounds] |
| Comparison permitted | [within/across groups and limitations] |
| Aggregation and interval | [rules] |
| Missing, partial, uncertain, unavailable | [truthful semantics] |
| Omission and truncation | [disclosure] |

## Visual Encoding And Legend

| Meaning | Primary encoding | Non-color reinforcement | Visible legend/copy |
|---|---|---|---|
| [meaning] | [hue/intensity/position/etc.] | [text/pattern/shape] | [label] |

## Anatomy And Interaction

[Headers, axes, labels, cells/marks, legend, controls, selection, details/evidence, tooltips, navigation, and empty/error states.]

## Responsive And Overflow Behavior

| Condition | Visible comparison window | Navigation | Sticky behavior |
|---|---|---|---|
| [range] | [behavior] | [controls] | [labels/axes] |

## Accessibility

[Semantic structure, accessible names, keyboard navigation, focus, announcements, direct values, contrast, and color-independent meaning.]

## Verification

- Fixtures and states: [paths/states]
- Viewports: [dimensions]
- Tests: [commands/paths]
- Residual gaps: [items]
