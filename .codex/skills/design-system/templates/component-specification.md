# [Component] Design-System Component Specification

## Authority And Scope

- Governing design system: [DS link]
- Implemented component/source: [path]
- Purpose and user goal: [purpose]
- In scope / out of scope: [boundaries]

## Anatomy

| Part | Required | Content or behavior | Token roles |
|---|---|---|---|
| [part] | yes/no | [contract] | [tokens] |

## Variants And Sizes

| Variant or size | Use | Visual and content contract | Prohibited use |
|---|---|---|---|
| [variant] | [use] | [contract] | [boundary] |

## State Matrix

| State | Trigger | Visual change | Semantics/announcement | Recovery or next action |
|---|---|---|---|---|
| default | none | [appearance] | [semantics] | n/a |
| hover | pointer | [appearance] | n/a | n/a |
| focus-visible | keyboard | [appearance] | [semantics] | n/a |
| active/selected | [trigger] | [appearance] | [state] | [action] |
| disabled | [condition] | [appearance] | [state] | [explanation] |
| loading | [condition] | [appearance] | [announcement] | [cancel/retry] |
| empty/error/partial/unavailable | [condition] | [appearance] | [announcement] | [recovery] |

## Content And Overflow

[Labels, lengths, wrapping, truncation, localization, numeric formatting, and long-content behavior.]

## Responsive Behavior

| Condition | Transformation | Target, focus, overflow, and sticky behavior |
|---|---|---|
| [range] | [behavior] | [constraints] |

## Accessibility And Interaction

[Native semantics, keyboard model, focus order, accessible names, announcements, contrast, motion, and touch.]

## Implementation And Verification

- Executable source: [paths]
- Tests and fixtures: [paths]
- Render matrix: [viewports/states]
- Known exceptions or gaps: [items]
