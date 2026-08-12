# Add Agent and Model Cost Heat Maps

Status: Ready

Type: Feature

Provider: file

Work Item ID: agent-and-model-cost-heatmaps

Completion: UNSET

## Summary

Add an agent-level cost heat map and revise the model heat map so both views
use cost-based green intensity while displaying cost and token count in every
cell.

## Context

The Agent Report offline HTML currently provides execution heat-map views for
wall time, token metrics, and models. Model rows currently sum processed tokens
and use token totals for their cell values, with aggregate cost presented as a
separate row. Cost rows already use a green scale.

The requested enhancement makes cost the primary visual measure for both agent
and model comparisons while retaining token volume as visible context. It must
preserve the existing time-period controls, selection, drill-down, compact
number formatting, accessibility labels, and privacy safeguards.

## Source Evidence

On 2026-08-12, the user requested in the current Codex task: "add a heat map of
agent cost - each line is an agent and the cost & token count for that agent.
Use green gradients. For the heat map of models, make it model costs and in
each cell display the cost as well as the token count." The user then explicitly
directed Codex to log the request as a backlog enhancement.

## Requirements

- Add an agent cost heat map with one row for each agent identity represented
  in the selected report data.
- Aggregate cost and processed token count for each agent in every visible
  time-period cell.
- Display both the formatted cost and compact token count directly in every
  agent heat-map cell.
- Use cost, not token count, to calculate agent-cell color intensity.
- Use a green sequential gradient for agent cost cells, including a legible
  zero-cost state.
- Change model heat-map cell intensity from processed-token volume to model
  cost.
- Display both the formatted model cost and compact processed-token count
  directly in every model heat-map cell.
- Use a green sequential gradient for model cost cells.
- Preserve model and reasoning-effort distinctions where the existing model
  heat map treats them as separate rows.
- Preserve existing heat-map period selection, navigation, drill-down,
  accessible labels, and event-range behavior.
- Update Agent Report documentation to describe the agent and model cost heat
  maps and their dual cost-and-token cell labels.

## Acceptance Criteria

- The generated Agent Report contains an agent cost heat map with one visible
  row per represented agent identity.
- Every populated agent cell visibly contains its cost and token count, and
  its green intensity is derived from cost.
- Every populated model cell visibly contains its cost and token count, and
  its green intensity is derived from cost rather than token count.
- Two cells with equal token counts but different costs receive different
  intensities consistent with their costs.
- Zero-cost cells remain readable and do not imply nonzero spend.
- Agent and model cells expose both measures in their accessible names or
  equivalent assistive-technology text.
- Existing period controls and heat-map drill-down interactions continue to
  work for the revised views.
- Existing report fixtures without billable cost data render without errors
  and show an unambiguous zero or unavailable cost state.
- Updated automated tests cover aggregation, formatting, cost normalization,
  green styling, and accessible cell labels for both views.

## Dependencies

None.

## Verification

- Run the focused Agent Report heat-map and HTML rendering tests.
- Add fixtures or focused assertions covering multiple agents, multiple model
  and reasoning-effort rows, differing token-to-cost ratios, and missing cost
  data.
- Verify generated HTML cells show both cost and token count and use green
  cost-based intensity.
- Verify keyboard selection, drill-down, and accessible labels for both heat
  maps.
- Run the complete `tools/report/tests` suite.
- Run `git diff --check`.

## Open Questions

- During implementation, confirm whether repeated uses of the same agent role
  in separate threads remain distinct rows or follow the report's existing
  concise agent-identity grouping.

## Notes

- This enhancement changes heat-map presentation and aggregation semantics; it
  does not request changes to pricing configuration or token accounting.
- Cost should be the sole color-scale input. Token count is supporting text and
  must not influence gradient intensity.
