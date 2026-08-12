# Use Blue Gradients for Wall-Time Waiting States

Status: Ready

Type: Feature

Provider: file

Work Item ID: wall-time-waiting-heatmap

Completion: UNSET

## Summary

Render every waiting category in the Agent Report wall-time heat map with a
blue gradient, including time spent waiting for the user and waiting for an
agent.

## Context

The offline Agent Report wall-time heat map uses one row for each runtime
activity. Its current presentation applies the blue inactivity scale to the
`user_pause` row but leaves `agent_wait` under the default red activity scale.
The report labels these states as user pause and waiting for agent.

Both states represent waiting rather than active execution and should share a
consistent blue visual semantic. The change must preserve the duration values,
row-specific normalization, period controls, selection, drill-down behavior,
and accessible labels.

## Source Evidence

On 2026-08-12, the user requested in the current Codex task: "in the wall time
heatmap, any waiting should use a blue gradient i.e. waiting for user or waiting
for agent." The user introduced the request as another work item, explicitly
authorizing its creation in the project backlog.

## Requirements

- Apply a blue sequential gradient to the wall-time row representing waiting
  for the user, currently classified as `user_pause`.
- Apply the same blue waiting-state color semantic to the wall-time row
  representing waiting for an agent, currently classified as `agent_wait`.
- Ensure any wall-time activity classified as waiting uses the blue waiting
  gradient rather than the red active-work gradient.
- Continue deriving each waiting cell's intensity from its wall-time duration
  using the existing row-specific normalization behavior.
- Preserve legible zero-duration and low-intensity waiting cells.
- Preserve the red gradient for active wall-time states and the independent
  color semantics of non-wall-time heat maps.
- Preserve existing period selection, navigation, cell selection, drill-down,
  accessible labels, and event-range behavior.
- Update Agent Report documentation so the wall-time heat-map description says
  that both user and agent waiting use blue gradients.

## Acceptance Criteria

- Wall-time cells for waiting for the user render with a blue gradient.
- Wall-time cells for waiting for an agent render with a blue gradient.
- Neither waiting category uses the default red active-work gradient.
- Non-waiting wall-time activity cells retain their existing active-state
  gradient semantics.
- Waiting-cell intensity remains proportional to visible wall-time duration
  within the row and is not based on token count or cost.
- Both waiting categories remain distinguishable by row label and accessible
  cell text even though they share the same color family.
- Existing wall-time heat-map period controls and drill-down interactions
  continue to work for waiting cells.
- Automated tests cover the waiting-state classification and blue styling for
  both `user_pause` and `agent_wait`.

## Dependencies

None.

## Verification

- Run the focused Agent Report heat-map and HTML rendering tests.
- Add assertions that both known waiting rows receive the blue waiting-state
  class or equivalent color semantic.
- Add a regression assertion that an active wall-time row does not receive the
  blue waiting-state semantic.
- Generate an HTML report containing both user and agent waiting intervals and
  inspect the resulting gradient colors, labels, and drill-down behavior.
- Run the complete `tools/report/tests` suite.
- Run `git diff --check`.

## Open Questions

None.

## Notes

- This work changes presentation semantics only. It does not change how
  waiting intervals or all-agents-waiting duration are calculated.
- The agent/model cost heat-map enhancement is related UI work but is not a
  dependency because its green cost semantics are independent of wall-time
  waiting colors.
