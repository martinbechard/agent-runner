# [Product] Design System

## Purpose And Status

[Name the product, audience, workflows, scope, lifecycle status, and the single authority this document provides.]

## Artifact Map

| Concern | Authority | Status and relationship |
|---|---|---|
| Canonical design system | [this document] | [active status] |
| Product/workflow authority | [requirement, architecture, or HLD] | [constraints inherited] |
| Executable tokens | [stack-owned path] | [implemented or planned] |
| Component specifications | [linked DSC documents or “embedded below”] | [relationship] |
| Visualization specifications | [linked DSV documents or “embedded below”] | [relationship] |
| Migration ledger | [section or standalone path] | [phase/status] |
| Review evidence | [RVW links] | [evidence only, not authority] |
| Superseded material | [paths or “none”] | [disposition] |

## Product Character And Principles

[Describe the product-specific visual character and 4–8 decision-making principles.]

## Source Evidence And Reconciliation

| Existing choice or value | Evidence | Disposition | Rationale and consumers |
|---|---|---|---|
| [choice] | [source/render path] | preserve / alias / consolidate / replace / deprecate / exception | [reason] |

## Foundations

### Primitive Tokens

| Family | Token | Value | Purpose and constraints |
|---|---|---|---|
| [color/type/space/etc.] | `[token]` | [value] | [use] |

### Semantic Tokens

| Role | Token | Primitive reference | Meaning and prohibited use |
|---|---|---|---|
| [role] | `[token]` | `[primitive]` | [contract] |

### Component Tokens

| Component | Token | Semantic reference | Contract |
|---|---|---|---|
| [component] | `[token]` | `[semantic]` | [contract] |

## Typography, Spacing, Shape, Iconography, And Motion

[Define roles, scales, minimums, formatting, icon rules, durations, easing, reduced motion, and documented exceptions.]

## Layout And Responsiveness

| Range or condition | Layout transformation | Overflow, sticky, and target rules |
|---|---|---|
| [breakpoint] | [behavior] | [constraints] |

## Components And State Matrix

[Embed core component contracts or link DSC documents. Cover anatomy, variants, sizes, content, tokens, responsive behavior, keyboard/assistive behavior, and prohibited ad hoc values.]

| Component | Default | Hover/focus/active | Disabled/loading/error | Empty/partial/unavailable | Specification |
|---|---|---|---|---|---|
| [component] | [state] | [state] | [state] | [state] | [embedded or DSC link] |

## Data Visualization

[Define scales, legends, units, comparison limits, exact values/tooltips, non-color encoding, uncertainty, unavailable data, selection, and evidence detail. Link DSV documents where needed.]

## Content And Terminology

[Define capitalization, action vocabulary, validation/error guidance, empty-state language, dates, times, numbers, units, and translation boundaries.]

## Accessibility

[Define contrast, focus, keyboard, semantics, announcements, zoom, reduced motion, touch targets, and verification requirements.]

## Migration And Deprecation

[Insert or link the migration-ledger template. Define ordered phases and completion signals.]

## Validation And Governance

[Define ownership, extension approval, review workflow, automated checks, render matrix, exceptions, and change triggers.]

## Verification Gaps

[List unavailable states, platforms, measurements, or evidence.]
