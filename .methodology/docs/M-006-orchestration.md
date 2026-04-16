```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline Orchestrator — Implementable Design
# ═══════════════════════════════════════════════════════════════════════════════
#
# The orchestrator is the control-flow and state-management backbone of the
# AI-driven development pipeline. It sequences phases, drives revision loops,
# enforces escalation policies, persists project state, and produces reports.
#
# It does NOT generate content, evaluate quality, extract checklists, or make
# architectural decisions. It is a conductor: it ensures each agent runs at the
# right time, with the right inputs, and it acts on verdicts according to
# configured policies.
#
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PHASE SEQUENCING
# ═══════════════════════════════════════════════════════════════════════════════
#
# The pipeline consists of seven phases (PH-000 through PH-006) arranged in a
# fixed dependency chain. Each phase produces artifacts consumed by downstream
# phases. The orchestrator builds the execution plan from declared dependencies,
# not from hard-coded ordering — the dependency graph happens to be linear for
# phases 0-4 and 6, with phase 5 having an internal sub-graph.
#
# ═══════════════════════════════════════════════════════════════════════════════

phase_sequencing:

  # ---------------------------------------------------------------------------
  # 1.1 Dependency Graph
  # ---------------------------------------------------------------------------
  #
  # Each phase declares the artifacts it reads (input_sources) and the artifact
  # it writes (phase_output). The orchestrator derives the execution order from
  # these declarations by building a DAG:
  #
  #   PH-000 ──► PH-001 ──► PH-002 ──► PH-003 ──► PH-004
  #                │                                  │
  #                │                                  ▼
  #                └──────────────────────────────► PH-005
  #                                                  │
  #    PH-000 ──────────────────────────────────────►│
  #    PH-001 ──────────────────────────────────────►│
  #                                                  ▼
  #                                               PH-006
  #
  # The orchestrator resolves this at startup by:
  #   1. Collecting all phase definitions.
  #   2. For each phase, extracting the artifact refs from input_sources.
  #   3. Matching each ref to the phase that produces it (via phase_output.artifact.path).
  #   4. Building an adjacency list: phase X depends on phase Y if X reads Y's output.
  #   5. Topologically sorting the adjacency list to produce execution order.
  #   6. Verifying the graph is acyclic (it must be — cycles are a configuration error).

  dependency_graph:
    description: |
      The canonical dependency graph derived from input_sources declarations.
      Each entry lists a phase and its direct predecessors (phases whose
      artifacts it reads).

    phases:
      - phase_id: "PH-000-requirements-inventory"
        predecessors: []
        artifacts_produced:
          - "docs/requirements/requirements-inventory.yaml"
        ready_when: "pipeline_started"

      - phase_id: "PH-001-feature-specification"
        predecessors: ["PH-000"]
        artifacts_consumed:
          - path: "docs/requirements/requirements-inventory.yaml"
            produced_by: "PH-000"
            role: "primary"
          - path: "docs/requirements/raw-requirements.md"
            produced_by: "external"
            role: "validation-reference"
        artifacts_produced:
          - "docs/features/feature-specification.yaml"
        ready_when: "PH-000 completed or escalated-with-flag"

      - phase_id: "PH-002-solution-design"
        predecessors: ["PH-001"]
        artifacts_consumed:
          - path: "docs/features/feature-specification.yaml"
            produced_by: "PH-001"
            role: "primary"
          - path: "docs/requirements/requirements-inventory.yaml"
            produced_by: "PH-000"
            role: "upstream-traceability"
        artifacts_produced:
          - "docs/design/solution-design.yaml"
        ready_when: "PH-001 completed or escalated-with-flag"

      - phase_id: "PH-003-contract-first-interfaces"
        predecessors: ["PH-002"]
        artifacts_consumed:
          - path: "docs/design/solution-design.yaml"
            produced_by: "PH-002"
            role: "primary"
          - path: "docs/features/feature-specification.yaml"
            produced_by: "PH-001"
            role: "validation-reference"
        artifacts_produced:
          - "docs/design/interface-contracts.yaml"
        ready_when: "PH-002 completed or escalated-with-flag"

      - phase_id: "PH-004-intelligent-simulations"
        predecessors: ["PH-003"]
        artifacts_consumed:
          - path: "docs/design/interface-contracts.yaml"
            produced_by: "PH-003"
            role: "primary"
          - path: "docs/design/solution-design.yaml"
            produced_by: "PH-002"
            role: "validation-reference"
          - path: "docs/features/feature-specification.yaml"
            produced_by: "PH-001"
            role: "validation-reference"
        artifacts_produced:
          - "docs/simulations/simulation-definitions.yaml"
        ready_when: "PH-003 completed or escalated-with-flag"

      - phase_id: "PH-005-incremental-implementation"
        predecessors: ["PH-003", "PH-004", "PH-001"]
        artifacts_consumed:
          - path: "docs/design/interface-contracts.yaml"
            produced_by: "PH-003"
            role: "primary"
          - path: "docs/simulations/simulation-definitions.yaml"
            produced_by: "PH-004"
            role: "primary"
          - path: "docs/features/feature-specification.yaml"
            produced_by: "PH-001"
            role: "validation-reference"
          - path: "docs/design/solution-design.yaml"
            produced_by: "PH-002"
            role: "validation-reference"
        artifacts_produced:
          - "docs/implementation/implementation-plan.yaml"
        ready_when: "PH-003 AND PH-004 AND PH-001 all completed or escalated-with-flag"

      - phase_id: "PH-006-verification-sweep"
        predecessors: ["PH-005", "PH-001", "PH-000"]
        artifacts_consumed:
          - path: "docs/features/feature-specification.yaml"
            produced_by: "PH-001"
            role: "primary"
          - path: "docs/requirements/requirements-inventory.yaml"
            produced_by: "PH-000"
            role: "primary"
          - path: "docs/design/solution-design.yaml"
            produced_by: "PH-002"
            role: "validation-reference"
          - path: "docs/implementation/implementation-plan.yaml"
            produced_by: "PH-005"
            role: "upstream-traceability"
        artifacts_produced:
          - "docs/verification/verification-report.yaml"
        ready_when: "PH-005 AND PH-001 AND PH-000 all completed or escalated-with-flag"

  # ---------------------------------------------------------------------------
  # 1.2 Phase Start Conditions
  # ---------------------------------------------------------------------------
  #
  # A phase may begin only when ALL of the following are true:
  #
  #   (a) Every predecessor phase has terminal status "completed" or
  #       "escalated" (with escalation_policy == flag-and-continue).
  #       A predecessor with status "halted" or "human-review-pending"
  #       blocks the downstream phase.
  #
  #   (b) Every artifact declared in artifacts_consumed exists on disk
  #       at the declared path and is non-empty.
  #
  #   (c) Every artifact with a non-empty content_hash in the phase's
  #       input_sources has a current hash matching the declared value.
  #       A mismatch means the input changed after the phase was
  #       configured. The orchestrator halts the phase and reports
  #       staleness. (If content_hash is empty, skip this check but
  #       log a warning that staleness is not monitored for this input.)
  #
  #   (d) Every predecessor's traceability link file
  #       (docs/traceability/phase-{N}-links.yaml) exists and the
  #       latest traceability validation report shows no broken
  #       references for that phase.
  #
  # The orchestrator evaluates these conditions in order. The first
  # failing condition is reported as the blocker.

  start_condition_evaluation:
    algorithm: |
      function can_start_phase(phase_id, project_state):
          phase_def = load_phase_definition(phase_id)
          blockers = []

          # (a) Predecessor status check
          for pred_id in phase_def.predecessors:
              pred_state = project_state.phases[pred_id]
              if pred_state.status not in ["completed", "escalated"]:
                  blockers.append({
                      check: "predecessor_status",
                      phase: pred_id,
                      current_status: pred_state.status,
                      required: "completed or escalated"
                  })
              elif pred_state.status == "escalated":
                  if pred_state.escalation_policy_applied != "flag-and-continue":
                      blockers.append({
                          check: "predecessor_escalation",
                          phase: pred_id,
                          escalation_policy: pred_state.escalation_policy_applied,
                          required: "flag-and-continue for downstream to proceed"
                      })

          # (b) Artifact existence check
          for artifact in phase_def.artifacts_consumed:
              if not file_exists(artifact.path):
                  blockers.append({
                      check: "artifact_existence",
                      path: artifact.path,
                      produced_by: artifact.produced_by
                  })

          # (c) Content hash check
          for source in phase_def.input_sources.artifacts:
              if source.content_hash != "":
                  current_hash = sha256(read_file(source.ref))
                  if current_hash != source.content_hash:
                      blockers.append({
                          check: "content_staleness",
                          path: source.ref,
                          declared_hash: source.content_hash,
                          current_hash: current_hash
                      })
              else:
                  log_warning("No content_hash for {source.ref}; staleness not monitored")

          # (d) Traceability integrity check
          for pred_id in phase_def.predecessors:
              pred_number = extract_phase_number(pred_id)
              link_file = "docs/traceability/phase-{pred_number}-links.yaml"
              if not file_exists(link_file):
                  blockers.append({
                      check: "traceability_missing",
                      phase: pred_id,
                      expected_file: link_file
                  })

          return {
              can_start: len(blockers) == 0,
              blockers: blockers
          }

  # ---------------------------------------------------------------------------
  # 1.3 Phase 5 Internal Ordering
  # ---------------------------------------------------------------------------
  #
  # Phase 5 (Incremental Implementation) is unique: its artifact is an
  # implementation plan that defines an internal execution order for
  # components. The orchestrator does not execute component implementations
  # (that is the generator's job), but it does determine the component
  # implementation order that the generator must follow.
  #
  # The ordering is derived from the Phase 2 solution design's interaction
  # graph. The orchestrator computes this at Phase 5 start time and passes
  # it to the Phase 5 generator as an additional input.

  phase_5_component_ordering:

    algorithm: |
      function compute_component_order(solution_design):
          # 1. Build adjacency list from interactions
          # Direction: from_component depends on to_component
          #   (from_component initiates; to_component provides)
          dependencies = {}  # CMP-* -> set of CMP-* it depends on
          dependents = {}    # CMP-* -> set of CMP-* that depend on it

          for component in solution_design.components:
              dependencies[component.component_id] = set()
              dependents[component.component_id] = set()

          for interaction in solution_design.interactions:
              caller = interaction.from_component
              provider = interaction.to_component
              dependencies[caller].add(provider)
              dependents[provider].add(caller)

          # 2. Topological sort (Kahn's algorithm)
          in_degree = { c: len(deps) for c, deps in dependencies.items() }
          queue = [c for c, d in in_degree.items() if d == 0]  # leaf components
          order = []

          # Within the same depth level, sort by:
          #   (a) number of downstream dependents (descending) — unblocks more
          #   (b) number of features served (descending) — delivers more value
          #   (c) component_id (ascending) — deterministic tiebreaker

          while queue:
              # Sort candidates at this level
              queue.sort(key=lambda c: (
                  -len(dependents[c]),
                  -count_features_served(c, solution_design),
                  c
              ))

              next_queue = []
              for component in queue:
                  order.append(component)
                  for dependent in dependents[component]:
                      in_degree[dependent] -= 1
                      if in_degree[dependent] == 0:
                          next_queue.append(dependent)
              queue = next_queue

          # 3. Cycle detection
          if len(order) != len(dependencies):
              remaining = set(dependencies.keys()) - set(order)
              raise CycleDetectedError(
                  "Circular dependency among components: " + str(remaining)
              )

          return order

    output_format: |
      The computed order is a list of component IDs with step numbers
      and rationale. This is passed to the Phase 5 generator as the
      "component_implementation_order" input alongside the standard
      inputs.

      component_implementation_order:
        - step: 1
          component_id: "CMP-003"
          rationale: "Leaf component — no dependencies on other internal components. Serves 3 features. 4 downstream dependents."
          dependencies_resolved_by: []

        - step: 2
          component_id: "CMP-005"
          rationale: "Depends only on CMP-003 (implemented in step 1). Serves 2 features."
          dependencies_resolved_by: ["CMP-003"]

    simulation_composition: |
      At each step in the component order, the orchestrator also computes
      the dependency resolution map: which dependencies are simulated and
      which are real at that point.

      For step N implementing component C:
        - Dependencies implemented in steps 1..N-1: resolved as "real"
        - Dependencies NOT yet implemented: resolved as "simulated"
          (using the simulation from Phase 4's simulation registry)

      This resolution map is included in the component_implementation_order
      output so the generator can design integration tests accordingly.

  # ---------------------------------------------------------------------------
  # 1.4 Phase Lifecycle State Machine
  # ---------------------------------------------------------------------------
  #
  # Each phase transitions through a well-defined set of states. The
  # orchestrator enforces that transitions follow the state machine — no
  # state is skipped, and only valid transitions are permitted.
  #
  # State machine (text diagram):
  #
  #   ┌─────────────┐
  #   │ not_started  │
  #   └──────┬───────┘
  #          │ start_conditions_met
  #          ▼
  #   ┌─────────────────────┐
  #   │ checklist_extraction │◄────────────────────────┐
  #   └──────┬──────────────┘                          │
  #          │ checklist produced                       │
  #          ▼                                         │
  #   ┌─────────────────────┐                          │
  #   │ checklist_validation │                          │
  #   └──────┬──────┬───────┘                          │
  #          │      │ validation failed                │
  #          │      │ (within budget)                   │
  #          │      └──────────────────────────────────┘
  #          │ validation passed
  #          │      │ validation failed (budget exhausted)
  #          │      ▼
  #          │  ┌───────────────────────┐
  #          │  │ validation_escalation  │──► [halted | human_review | flagged]
  #          │  └───────────────────────┘         │
  #          │                                    │ (flagged: continue with
  #          │◄───────────────────────────────────┘  best-effort checklist)
  #          ▼
  #   ┌─────────────────────┐
  #   │ artifact_generation  │◄────────────────────────┐
  #   └──────┬──────────────┘                          │
  #          │ artifact produced                       │
  #          ▼                                         │
  #   ┌─────────────────────┐                          │
  #   │      judgment        │                          │
  #   └──────┬──────┬───────┘                          │
  #          │      │ verdict: revise                   │
  #          │      │ (within budget, no oscillation)   │
  #          │      └──────────────────────────────────┘
  #          │ verdict: pass
  #          │      │ verdict: revise (budget exhausted or oscillation)
  #          │      ▼
  #          │  ┌───────────────────────┐
  #          │  │ revision_escalation    │──► [halted | human_review | flagged | restructure]
  #          │  └───────────────────────┘         │
  #          │                                    │ (flagged: continue
  #          │◄───────────────────────────────────┘  with best artifact)
  #          ▼
  #   ┌───────────────────────────┐
  #   │ traceability_validation    │
  #   └──────┬──────┬─────────────┘
  #          │      │ broken refs (counts against revision budget)
  #          │      └──► back to artifact_generation
  #          │ passed (or orphans/uncovereds logged as warnings)
  #          ▼
  #   ┌─────────────┐
  #   │  completed   │  (terminal — success)
  #   └─────────────┘
  #
  #   Terminal states: completed, escalated, halted, human_review_pending
  #
  #   "escalated" is reached via flag-and-continue from any escalation node.
  #   "halted" is reached via halt from any escalation node.
  #   "human_review_pending" is reached via human-review from any escalation.
  #   "restructure_pending" is reached via restructure from revision_escalation.

  phase_states:
    - name: "not_started"
      description: "Phase has not begun. Waiting for start conditions."
      valid_transitions:
        - to: "checklist_extraction"
          trigger: "start_conditions_met"

    - name: "checklist_extraction"
      description: "Checklist Extractor agent is producing checklist items."
      valid_transitions:
        - to: "checklist_validation"
          trigger: "checklist_produced"

    - name: "checklist_validation"
      description: "Checklist Validator agent is verifying the checklist."
      valid_transitions:
        - to: "artifact_generation"
          trigger: "validation_passed"
        - to: "checklist_extraction"
          trigger: "validation_failed_within_budget"
        - to: "validation_escalation"
          trigger: "validation_budget_exhausted"

    - name: "validation_escalation"
      description: "Checklist validation loop exhausted. Applying escalation policy."
      valid_transitions:
        - to: "halted"
          trigger: "policy_halt"
        - to: "human_review_pending"
          trigger: "policy_human_review"
        - to: "artifact_generation"
          trigger: "policy_flag_and_continue"

    - name: "artifact_generation"
      description: "Artifact Generator agent is producing or revising the artifact."
      valid_transitions:
        - to: "judgment"
          trigger: "artifact_produced"

    - name: "judgment"
      description: "Judge agent is evaluating the artifact against the checklist."
      valid_transitions:
        - to: "traceability_validation"
          trigger: "verdict_pass"
        - to: "artifact_generation"
          trigger: "verdict_revise_within_budget"
        - to: "revision_escalation"
          trigger: "verdict_revise_budget_exhausted"
        - to: "revision_escalation"
          trigger: "oscillation_detected"

    - name: "revision_escalation"
      description: "Revision loop exhausted or oscillation detected. Applying escalation policy."
      valid_transitions:
        - to: "halted"
          trigger: "policy_halt"
        - to: "human_review_pending"
          trigger: "policy_human_review"
        - to: "traceability_validation"
          trigger: "policy_flag_and_continue"
        - to: "restructure_pending"
          trigger: "policy_restructure"

    - name: "traceability_validation"
      description: "Traceability Validator checking intra-phase links."
      valid_transitions:
        - to: "completed"
          trigger: "validation_passed"
        - to: "completed"
          trigger: "orphans_or_uncovereds_only"
        - to: "artifact_generation"
          trigger: "broken_refs_found_within_revision_budget"
        - to: "revision_escalation"
          trigger: "broken_refs_found_revision_budget_exhausted"

    - name: "completed"
      description: "Phase finished successfully. Artifact approved."
      terminal: true

    - name: "escalated"
      description: "Phase finished with flag-and-continue. Artifact is best-effort."
      terminal: true

    - name: "halted"
      description: "Phase stopped due to halt policy. No usable artifact."
      terminal: true

    - name: "human_review_pending"
      description: "Phase paused awaiting external human input."
      terminal: false
      resumable: true
      valid_transitions:
        - to: "checklist_extraction"
          trigger: "human_directs_restart_checklist"
        - to: "artifact_generation"
          trigger: "human_directs_restart_generation"
        - to: "halted"
          trigger: "human_directs_halt"
        - to: "completed"
          trigger: "human_approves_artifact"

    - name: "restructure_pending"
      description: "Phase identified a problem requiring upstream rework. See section 3.4."
      terminal: false
      resumable: true
      valid_transitions:
        - to: "not_started"
          trigger: "upstream_rework_completed"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. REVISION LOOP MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════
#
# Within each phase, the orchestrator drives the inner processing unit loop.
# The loop has two sub-loops:
#   (A) Checklist extraction ↔ validation (bounded by max_validation_iterations)
#   (B) Artifact generation ↔ judgment (bounded by revision_loop.max_iterations)
#
# The orchestrator tracks both counters independently and enforces both budgets.
#
# ═══════════════════════════════════════════════════════════════════════════════

revision_loop_management:

  # ---------------------------------------------------------------------------
  # 2.1 Revision Loop State Machine
  # ---------------------------------------------------------------------------
  #
  #   ┌───────────────────────────────┐
  #   │  CHECKLIST SUB-LOOP           │
  #   │                               │
  #   │  iteration = 0                │
  #   │       │                       │
  #   │       ▼                       │
  #   │  ┌─────────┐                  │
  #   │  │ Extract  │                  │
  #   │  └────┬─────┘                  │
  #   │       ▼                       │
  #   │  ┌──────────┐    fail &       │
  #   │  │ Validate  │──► iter < max ──►─┐
  #   │  └────┬─────┘    (feedback)    │  │
  #   │       │ pass                   │  │ iter++
  #   │       │                       │  │ pass feedback
  #   │       │    fail & iter >= max  │  │ to extractor
  #   │       │   ◄── escalate ────────│──┘
  #   │       ▼                       │
  #   └───────┼───────────────────────┘
  #           │ validated checklist
  #           ▼
  #   ┌───────────────────────────────┐
  #   │  ARTIFACT SUB-LOOP            │
  #   │                               │
  #   │  iteration = 0                │
  #   │       │                       │
  #   │       ▼                       │
  #   │  ┌──────────┐                  │
  #   │  │ Generate  │◄───────────────┐│
  #   │  └────┬─────┘                 ││
  #   │       ▼                       ││
  #   │  ┌──────────┐   revise &     ││
  #   │  │  Judge    │──► iter < max ──┘│
  #   │  └────┬─────┘   & no oscil.    │
  #   │       │ pass                   │
  #   │       │                       │
  #   │       │   revise &             │
  #   │       │   (iter >= max         │
  #   │       │    OR oscillation)     │
  #   │       │   ──► escalate         │
  #   │       ▼                       │
  #   └───────┼───────────────────────┘
  #           │ approved artifact
  #           ▼
  #     Traceability Validation

  # ---------------------------------------------------------------------------
  # 2.2 Checklist Sub-Loop Protocol
  # ---------------------------------------------------------------------------

  checklist_sub_loop:
    description: |
      Drives the extraction-validation cycle until the checklist passes
      all three validation checks or the iteration budget is exhausted.

    protocol:
      - step: 1
        name: "invoke_extractor"
        action: |
          Assemble extractor inputs:
            - input_sources: from phase definition (artifact content loaded from disk)
            - extraction_focus: from phase definition
            - artifact_schema: from phase definition (so extractor knows the target shape)
            - phase_context: { phase_id, phase_name, iteration: checklist_iteration }
            - validation_feedback: from previous validation (null on first iteration)

          Invoke the checklist-extractor agent.
          Receive: checklist_items (YAML list).
          Validate structural integrity:
            - Every item has id, source_ref, criterion, verification_method.
            - IDs are unique.
            - IDs match the expected prefix for this phase.
          If structurally invalid: retry once with error details. If still invalid: halt.

      - step: 2
        name: "invoke_validator"
        action: |
          Assemble validator inputs:
            - input_sources: same as extractor received
            - checklist_items: from step 1
            - validation_checks: from phase definition (grounding, coverage, specificity)
            - phase_context: { phase_id, extraction_focus }

          Invoke the checklist-validator agent.
          Receive: validation_result (YAML).

      - step: 3
        name: "evaluate_validation"
        action: |
          If validation_result.overall_status == "pass":
            Store the validated checklist.
            Transition to artifact sub-loop.

          If validation_result.overall_status == "fail":
            Increment checklist_iteration.
            If checklist_iteration > max_validation_iterations:
              Transition to validation_escalation.
              Apply validation_escalation_policy.
            Else:
              Extract validation_feedback from the result.
              Return to step 1 with feedback.

  # ---------------------------------------------------------------------------
  # 2.3 Artifact Sub-Loop Protocol
  # ---------------------------------------------------------------------------

  artifact_sub_loop:
    description: |
      Drives the generation-judgment cycle until the judge passes all
      checklist items or the iteration budget is exhausted.

    protocol:
      - step: 1
        name: "invoke_generator"
        action: |
          Assemble generator inputs:
            - input_sources: from phase definition (content loaded from disk)
            - validated_checklist: the full checklist (ALL items, not filtered)
            - generation_instructions: from phase definition
            - artifact_schema: from phase definition
            - output_format: from phase definition
            - output_path: from phase definition
            - artifact_element_id_format: from phase definition
            - phase_context: { phase_id, revision_iteration }

          On revision cycles (iteration > 0), also include:
            - previous_artifact: the complete artifact from the prior attempt
            - judge_evaluations: the FULL evaluation list from the judge
              (all items — pass, fail, and partial — so the generator sees
              the complete picture and avoids regressions)

          Invoke the artifact-generator agent.
          Receive: { artifact_content, traceability_mapping } (YAML).

          Validate structural integrity:
            - artifact_content conforms to the artifact_schema top-level keys.
            - traceability_mapping is a non-empty list.
            - Every traceability entry has artifact_element_ref, checklist_item_ids,
              input_source_refs.
          If structurally invalid: retry once. If still invalid: halt.

          Write artifact to output_path.
          Store traceability_mapping in memory for the judge.

      - step: 2
        name: "invoke_judge"
        action: |
          Assemble judge inputs:
            - validated_checklist: the full checklist
            - artifact: the generated artifact (loaded from output_path)
            - traceability_mapping: from step 1
            - input_sources: from phase definition (content loaded from disk)
            - phase_context: { phase_id, revision_iteration }

          NOTE: The judge does NOT receive generation_instructions.
          It judges against the checklist contract, not the generator's brief.

          If this is the final allowed iteration (revision_iteration == max_iterations):
            Include a flag: allow_escalate_verdict = true.
            This permits the judge to return verdict "escalate" if appropriate.

          Invoke the artifact-judge agent.
          Receive: { evaluations, uncovered_concerns, verdict } (YAML).

          Validate structural integrity:
            - evaluations list has one entry per checklist item (count match).
            - Every evaluation has checklist_item_id, result, evidence, reason,
              artifact_location.
            - verdict is one of: pass, revise, escalate.
          If structurally invalid: retry once. If still invalid: halt.

      - step: 3
        name: "record_iteration"
        action: |
          Record in iteration_log:
            iteration: revision_iteration
            timestamp: current ISO 8601 datetime
            verdict: judge's verdict
            failed_item_count: count of evaluations with result "fail"
            partial_item_count: count of evaluations with result "partial"
            passed_item_count: count of evaluations with result "pass"
            duration_seconds: wall-clock time for steps 1 + 2
            failed_item_ids: list of CL-* IDs that failed
            partial_item_ids: list of CL-* IDs that are partial

      - step: 4
        name: "evaluate_verdict"
        action: |
          If verdict == "pass":
            Proceed to traceability validation.

          If verdict == "revise" or verdict == "escalate":
            Increment revision_iteration.

            # Check oscillation BEFORE checking budget
            oscillation = detect_oscillation(iteration_log)
            if oscillation.detected:
              Transition to revision_escalation with reason "oscillation".

            if revision_iteration > max_iterations:
              Transition to revision_escalation with reason "budget_exhausted".

            # Within budget, no oscillation
            Return to step 1 with the full evaluations for the generator.

  # ---------------------------------------------------------------------------
  # 2.4 Oscillation Detection
  # ---------------------------------------------------------------------------
  #
  # Oscillation occurs when the generator "fixes" item A but breaks item B,
  # then fixes B but breaks A again. The loop makes no net progress.
  #
  # Detection algorithm: compare the set of failing/partial item IDs across
  # the last three iterations. If an item alternates between pass and fail
  # (or partial) across three consecutive iterations, oscillation is declared.
  #
  # Specifically:
  #   - Let F(i) = set of non-passing item IDs at iteration i.
  #   - Oscillation is detected when:
  #     (a) There exist at least 3 iterations (i-2, i-1, i).
  #     (b) There exists an item X such that:
  #         X in F(i-2) AND X not in F(i-1) AND X in F(i)
  #         (X failed, then passed, then failed again — regression cycle)
  #     (c) OR: F(i) == F(i-2) and F(i) != F(i-1) — the exact same set of
  #         items fail in iterations i-2 and i, with a different failure
  #         pattern in between.
  #
  # Additional heuristic: if |F(i)| >= |F(i-1)| for two consecutive iterations
  # (failure count is not decreasing), flag "stagnation" — not an immediate
  # escalation trigger, but logged as a warning. If stagnation persists for
  # max_iterations - 1 iterations, escalate early rather than exhausting
  # remaining budget.

  oscillation_detection:
    algorithm: |
      function detect_oscillation(iteration_log):
          if len(iteration_log) < 3:
              return { detected: false }

          # Get the last three iterations' non-passing item sets
          f_current = set(iteration_log[-1].failed_item_ids + iteration_log[-1].partial_item_ids)
          f_prev = set(iteration_log[-2].failed_item_ids + iteration_log[-2].partial_item_ids)
          f_prev2 = set(iteration_log[-3].failed_item_ids + iteration_log[-3].partial_item_ids)

          # Check for individual item oscillation
          regressing_items = (f_current & f_prev2) - f_prev
          if len(regressing_items) > 0:
              return {
                  detected: true,
                  type: "regression_cycle",
                  oscillating_items: sorted(regressing_items),
                  message: "Items {regressing_items} passed in iteration {i-1} but "
                           "failed again in iteration {i}, matching their state in "
                           "iteration {i-2}. The generator is oscillating."
              }

          # Check for set-level oscillation
          if f_current == f_prev2 and f_current != f_prev:
              return {
                  detected: true,
                  type: "set_oscillation",
                  oscillating_items: sorted(f_current),
                  message: "The exact same items fail in iterations {i-2} and {i} "
                           "with a different pattern in iteration {i-1}. The generator "
                           "is cycling between two failure states."
              }

          # Check for stagnation (warning, not immediate escalation)
          if len(f_current) >= len(f_prev) and len(f_prev) >= len(f_prev2):
              return {
                  detected: false,
                  stagnation_warning: true,
                  message: "Failure count is not decreasing across last 3 iterations "
                           "({len(f_prev2)} -> {len(f_prev)} -> {len(f_current)}). "
                           "Generator may be stuck."
              }

          return { detected: false }

  # ---------------------------------------------------------------------------
  # 2.5 Generator Input Assembly
  # ---------------------------------------------------------------------------
  #
  # On revision cycles, the generator receives the COMPLETE evaluations from
  # the judge — all items, not just failures. This is critical because:
  #   (a) The generator needs to know what is already passing to avoid
  #       regressions.
  #   (b) The generator needs the full evidence from passing items to
  #       understand what the judge considers satisfactory.
  #   (c) The generator needs the full picture to make informed tradeoffs
  #       when a fix for one item might affect another.
  #
  # The orchestrator also passes the complete current artifact (not a diff)
  # so the generator has the full context of what it is revising.

  generator_input_assembly:
    first_iteration:
      inputs:
        - name: "input_sources"
          content: "All input source artifacts loaded from disk"
        - name: "validated_checklist"
          content: "The full validated checklist (all items)"
        - name: "generation_instructions"
          content: "From phase definition"
        - name: "artifact_schema"
          content: "From phase definition"
        - name: "output_format"
          content: "From phase definition"
        - name: "output_path"
          content: "From phase definition"
        - name: "artifact_element_id_format"
          content: "From phase definition"

    revision_iteration:
      additional_inputs:
        - name: "previous_artifact"
          content: "The complete artifact from the previous iteration (loaded from output_path)"
        - name: "judge_evaluations"
          content: |
            The COMPLETE evaluation list from the judge. All items are included:
              - pass items with their evidence and artifact_location
              - fail items with their reason and artifact_location
              - partial items with their evidence, reason, and artifact_location
            The generator is expected to:
              1. Fix every fail and partial item.
              2. Not regress any pass item.
              3. Use the evidence from pass items to understand the judge's standards.
        - name: "uncovered_concerns"
          content: |
            The judge's uncovered concerns list. The generator should be aware of
            these but is NOT required to address them (they are not on the checklist).
            However, if addressing a concern would not conflict with any checklist
            item, the generator may choose to address it.
        - name: "iteration_context"
          content: |
            iteration_number: current revision iteration
            remaining_iterations: max_iterations - current iteration
            oscillation_warning: true/false (from stagnation detection)
            previously_oscillating_items: list of item IDs (if any)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ESCALATION HANDLING
# ═══════════════════════════════════════════════════════════════════════════════
#
# Escalation is triggered when a loop cannot converge. The orchestrator does
# not decide HOW to fix the problem — it applies the configured policy and
# records the event for auditing. Four escalation policies exist; the fourth
# (restructure) is the most complex because it requires upstream rework.
#
# ═══════════════════════════════════════════════════════════════════════════════

escalation_handling:

  # ---------------------------------------------------------------------------
  # 3.1 Escalation Triggers
  # ---------------------------------------------------------------------------

  triggers:
    - trigger_id: "ESC-CHECKLIST-BUDGET"
      description: "Checklist validation loop exceeded max_validation_iterations."
      source: "checklist sub-loop"
      data_captured:
        - "Current checklist (best effort)"
        - "Last validation_feedback from the validator"
        - "Number of iterations completed"
        - "Specific checks that failed on the final iteration"

    - trigger_id: "ESC-REVISION-BUDGET"
      description: "Artifact revision loop exceeded max_iterations."
      source: "artifact sub-loop"
      data_captured:
        - "Current artifact (best effort)"
        - "Last judge evaluations (all items)"
        - "Complete iteration_log"
        - "Uncovered concerns from the last judgment"

    - trigger_id: "ESC-OSCILLATION"
      description: "Oscillation detected in the revision loop."
      source: "oscillation detector"
      data_captured:
        - "Oscillation detection result (type, oscillating items, message)"
        - "Current artifact"
        - "Last three iterations of evaluations"
        - "Complete iteration_log"

    - trigger_id: "ESC-TRACEABILITY-BROKEN"
      description: "Traceability validation found broken references that cannot be resolved within revision budget."
      source: "traceability validation step"
      data_captured:
        - "Traceability validation report"
        - "Specific broken references"
        - "Current artifact and traceability mapping"

    - trigger_id: "ESC-CRITICAL-CONCERN"
      description: "Judge flagged an uncovered concern with severity 'high' that implies the checklist itself is insufficient."
      source: "judgment step"
      data_captured:
        - "The uncovered concern (id, description, severity, artifact_location)"
        - "Current artifact"
        - "Current checklist"
      note: |
        This trigger is advisory. The orchestrator logs it and checks the
        phase's escalation configuration for critical_concern_policy. If
        the policy is "ignore", the concern is logged but does not trigger
        escalation. If the policy is "escalate", it is treated like a
        revision budget exhaustion.

    - trigger_id: "ESC-AGENT-FAILURE"
      description: "An agent failed to produce valid output after one retry."
      source: "any agent invocation"
      data_captured:
        - "Agent role ID"
        - "Error details (timeout, crash, malformed output)"
        - "The inputs that were sent to the agent"
      policy_override: "always halt"

  # ---------------------------------------------------------------------------
  # 3.2 Escalation Policies
  # ---------------------------------------------------------------------------

  policies:

    - policy_id: "halt"
      description: |
        Stop the pipeline immediately. No artifact is produced for this
        phase. All downstream phases are blocked.
      behavior:
        - Set phase status to "halted".
        - Set pipeline status to "halted".
        - Write escalation event to the escalation log.
        - Emit pipeline report with event "phase_halted" and full details.
        - Do NOT delete any work product — the artifact (if any) remains
          on disk for inspection, but is NOT marked as approved.
      when_to_use: |
        Default for early phases (PH-000, PH-001) where getting the
        foundation wrong compounds downstream. Also appropriate when the
        failure indicates a fundamental problem (e.g., the raw
        requirements are self-contradictory and the checklist validator
        cannot produce a sound checklist).

    - policy_id: "flag-and-continue"
      description: |
        Record the issue, proceed with the best available artifact. The
        artifact is marked as "escalated" (not "approved") so downstream
        phases can see the flag.
      behavior:
        - Set phase status to "escalated".
        - Set phase_output.artifact.status to "escalated".
        - Set escalation_status to "flagged".
        - Write escalation event to the escalation log with:
            - The trigger ID
            - The specific items that failed/oscillated
            - The best-effort artifact path
        - Write the artifact to its output_path (overwriting any prior version).
        - Write the completed checklist with evaluations (including failures).
        - Write the traceability mapping (which may have gaps).
        - Proceed to the next phase.
      downstream_visibility: |
        When a downstream phase loads an input with status "escalated":
          - The orchestrator logs a warning: "Input {path} from {phase_id}
            is escalated (not approved). Downstream results may inherit gaps."
          - The escalation flag propagates: if a downstream artifact depends
            on escalated input, its own status cannot be higher than "escalated"
            even if it passes all checklist items.
      when_to_use: |
        Appropriate for later phases (PH-004, PH-005) where partial
        results have value, or when the failure is isolated to a few
        checklist items that do not affect the majority of downstream work.

    - policy_id: "human-review"
      description: |
        Pause the pipeline and present the issue to a human for decision.
        The human can direct the pipeline to restart, halt, or approve
        the current artifact.
      behavior:
        - Set phase status to "human_review_pending".
        - Write escalation event to the escalation log.
        - Emit pipeline report with event "human_review_requested".
        - Present to the human:
            - The trigger and its context
            - The current artifact (if any)
            - The last judge evaluations
            - The uncovered concerns
            - The oscillation detection result (if applicable)
            - Options: restart_checklist, restart_generation, approve, halt, restructure
        - Wait for human input. Do not proceed until input is received.
        - On human input:
            - "restart_checklist": reset checklist_iteration to 0, return to
              checklist extraction with the human's guidance as additional context.
            - "restart_generation": reset revision_iteration to 0, return to
              artifact generation with the human's guidance.
            - "approve": set phase status to "completed", artifact status to
              "approved" (human override).
            - "halt": set phase status to "halted".
            - "restructure": transition to restructure_pending.
      when_to_use: |
        Appropriate for critical phases (PH-001, PH-002) when the failure
        is ambiguous and automated policies cannot determine the right
        course. Also used when oscillation is detected — a human can often
        spot the root cause that the generator and judge are circling.

    - policy_id: "restructure"
      description: |
        The current phase has identified a problem that originates in an
        upstream phase's artifact. Rather than working around it, go back
        and fix the source.
      behavior: "See section 3.4 for the full restructure protocol."
      when_to_use: |
        Appropriate when the judge's failure reasons or uncovered concerns
        point to a deficiency in the input sources, not in the current
        phase's artifact. For example:
          - Phase 3 (contracts) fails because Phase 2 (design) has
            overlapping component responsibilities that make unambiguous
            contract boundaries impossible.
          - Phase 5 (implementation plan) fails because Phase 3 (contracts)
            has type holes that prevent conformance testing.
          - Phase 6 (verification) fails because Phase 1 (features) has
            acceptance criteria too vague to derive end-to-end tests.

  # ---------------------------------------------------------------------------
  # 3.3 Escalation Policy Configuration
  # ---------------------------------------------------------------------------
  #
  # Each phase configures its preferred policies for each escalation type.
  # The orchestrator reads this configuration at phase start time and applies
  # the configured policy when a trigger fires.

  policy_configuration_schema:
    description: |
      Added to each phase_processing_unit definition as a top-level field
      alongside revision_loop and checklist_extraction.

    schema:
      escalation_policies:
        checklist_validation_exhausted:
          type: string
          enum: ["halt", "flag-and-continue", "human-review"]
          description: "Policy when max_validation_iterations is exceeded."

        revision_loop_exhausted:
          type: string
          enum: ["halt", "flag-and-continue", "human-review", "restructure"]
          description: "Policy when revision_loop.max_iterations is exceeded."

        oscillation_detected:
          type: string
          enum: ["halt", "flag-and-continue", "human-review", "restructure"]
          description: "Policy when oscillation is detected in the revision loop."

        critical_concern_policy:
          type: string
          enum: ["ignore", "escalate"]
          default: "ignore"
          description: |
            What to do when the judge flags a high-severity uncovered concern.
            'ignore' logs it but does not trigger escalation.
            'escalate' treats it like revision_loop_exhausted.

        agent_failure:
          type: string
          enum: ["halt"]
          default: "halt"
          description: "Always halt on agent failure. Not configurable."

    recommended_defaults:
      - phase: "PH-000"
        checklist_validation_exhausted: "halt"
        revision_loop_exhausted: "halt"
        oscillation_detected: "halt"
        critical_concern_policy: "ignore"

      - phase: "PH-001"
        checklist_validation_exhausted: "human-review"
        revision_loop_exhausted: "human-review"
        oscillation_detected: "human-review"
        critical_concern_policy: "escalate"

      - phase: "PH-002"
        checklist_validation_exhausted: "human-review"
        revision_loop_exhausted: "human-review"
        oscillation_detected: "restructure"
        critical_concern_policy: "escalate"

      - phase: "PH-003"
        checklist_validation_exhausted: "halt"
        revision_loop_exhausted: "restructure"
        oscillation_detected: "restructure"
        critical_concern_policy: "escalate"

      - phase: "PH-004"
        checklist_validation_exhausted: "flag-and-continue"
        revision_loop_exhausted: "flag-and-continue"
        oscillation_detected: "human-review"
        critical_concern_policy: "ignore"

      - phase: "PH-005"
        checklist_validation_exhausted: "halt"
        revision_loop_exhausted: "restructure"
        oscillation_detected: "restructure"
        critical_concern_policy: "escalate"

      - phase: "PH-006"
        checklist_validation_exhausted: "halt"
        revision_loop_exhausted: "human-review"
        oscillation_detected: "human-review"
        critical_concern_policy: "escalate"

  # ---------------------------------------------------------------------------
  # 3.4 Restructure Protocol
  # ---------------------------------------------------------------------------
  #
  # Restructure is the most complex escalation because it rewinds the pipeline
  # to an earlier phase, invalidates downstream artifacts, and re-runs affected
  # phases. It exists to handle the case where a downstream phase discovers
  # that the upstream artifact is fundamentally inadequate.
  #
  # Restructure is expensive — it may re-run multiple phases. It should only
  # be triggered when the alternative (flag-and-continue) would propagate a
  # known deficiency that will compound downstream.
  #
  # Key constraint: restructure MUST NOT create infinite loops. A phase that
  # has already been restructured once cannot trigger another restructure to
  # the same upstream phase for the same reason. If the same problem recurs
  # after restructure, the pipeline halts.

  restructure_protocol:

    trigger_conditions: |
      Restructure is triggered when:
        1. The revision loop is exhausted or oscillation is detected.
        2. The judge's failure reasons or uncovered concerns identify a
           deficiency in an input source artifact (not in the current
           phase's generation).
        3. The phase's escalation policy for the trigger is "restructure".

      The orchestrator determines the target phase (the upstream phase
      to re-run) by:
        a. Reading the judge's evaluations for failed/partial items.
        b. For each failed item, checking if the reason references an
           input source artifact.
        c. Identifying which phase produced that input source.
        d. The target phase is the earliest producer phase cited in
           failure reasons.

    protocol_steps:
      - step: 1
        name: "identify_target_phase"
        action: |
          Parse the judge's evaluations for failed/partial items.
          For each failure reason:
            Extract any artifact path references.
            Map each path to its producing phase via the dependency graph.

          The target phase is the earliest (lowest phase number) among
          the producing phases. If multiple phases are cited, start with
          the earliest — fixing it may cascade fixes to later ones.

          Record:
            restructure_request:
              triggering_phase: "PH-XXX"
              target_phase: "PH-YYY"
              reason: "summary of the deficiency"
              failed_items: [list of CL-* IDs]
              evidence: [list of judge evaluations for those items]

      - step: 2
        name: "loop_guard"
        action: |
          Check the restructure history in the project state.
          If the same (triggering_phase, target_phase, reason_category)
          triple has been executed before:
            HALT. The same restructure was already attempted and the
            problem recurred. This indicates a fundamental issue that
            automated restructure cannot resolve.

          reason_category is a normalized form of the reason — not the
          exact text, but the category of deficiency (e.g., "overlapping
          responsibilities", "vague acceptance criteria", "missing
          interaction").

      - step: 3
        name: "invalidate_downstream"
        action: |
          Mark all phases from target_phase through triggering_phase
          (inclusive) as "invalidated":
            - Set their status to "not_started".
            - Reset their checklist_iteration and revision_iteration to 0.
            - Clear their iteration_logs.
            - Do NOT delete their artifacts — rename them with a
              ".invalidated.{timestamp}" suffix for audit purposes.
            - Clear their traceability link files
              (docs/traceability/phase-{N}-links.yaml).

          This cascade is necessary because all intermediate phases
          consumed artifacts that are now being revised.

      - step: 4
        name: "augment_target_inputs"
        action: |
          The target phase will be re-run. To avoid repeating the same
          failure, augment its inputs with the restructure context:

          restructure_context:
            triggering_phase: "PH-XXX"
            deficiency_summary: "Description of the problem"
            failed_items: [list of CL-* IDs with their failure reasons]
            guidance: |
              The downstream phase (PH-XXX) could not produce a valid
              artifact because this phase's output has the following
              deficiency: {deficiency_summary}.

              Specific failures:
              {formatted list of failed items and reasons}

              When generating the revised artifact, ensure that:
              {specific guidance derived from the failure reasons}

          This context is passed to the target phase's checklist
          extractor (as additional extraction focus) and to its
          artifact generator (as additional generation instructions).
          The checklist extractor should produce new checklist items
          that specifically address the identified deficiency.

      - step: 5
        name: "re_execute"
        action: |
          Re-run the target phase from the beginning (checklist
          extraction). The phase receives:
            - Its original input sources (unchanged)
            - The restructure_context as an additional input
            - A fresh iteration budget (counters reset)

          After the target phase completes (or escalates), re-run
          each subsequent phase in order through the triggering phase.
          Each re-run starts fresh with the revised upstream artifacts.

      - step: 6
        name: "record_restructure"
        action: |
          Record in the project state:
            restructure_log:
              - timestamp: ISO 8601
                triggering_phase: "PH-XXX"
                target_phase: "PH-YYY"
                reason_category: "normalized reason"
                reason_detail: "full reason text"
                phases_invalidated: ["PH-YYY", ..., "PH-XXX"]
                result: "success" | "failed" | "halted"

    safeguards:
      max_restructures_per_pipeline: 3
      description: |
        The pipeline allows at most 3 restructure events across its
        entire lifetime. This prevents unbounded restructuring where
        phases keep blaming each other. After the third restructure,
        any further restructure trigger is converted to "halt".

      same_target_limit: 1
      description: |
        A specific target phase can be restructured at most once.
        If the same phase is targeted again (by any triggering phase),
        the pipeline halts. The rationale: if restructuring a phase
        once did not fix the problem, automated restructuring will
        not fix it on a second pass.


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PROJECT STATE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════
#
# The project state is the single source of truth for the pipeline's progress.
# It is persisted to disk after every state transition so that work survives
# interruptions. Any agent or human can read the state file to understand
# exactly where the pipeline stands.
#
# ═══════════════════════════════════════════════════════════════════════════════

project_state:

  # ---------------------------------------------------------------------------
  # 4.1 State Schema
  # ---------------------------------------------------------------------------

  storage_path: "docs/pipeline/project-state.yaml"

  schema:
    project_metadata:
      project_name:
        type: string
        description: "Human-readable project name"
      pipeline_version:
        type: string
        description: "Version of the pipeline definition being executed"
      created_at:
        type: string
        format: "ISO 8601"
        description: "When the pipeline was first initialized"
      last_updated:
        type: string
        format: "ISO 8601"
        description: "When the state was last written to disk"

    pipeline_status:
      type: string
      enum:
        - "not_started"
        - "in_progress"
        - "completed"
        - "halted"
        - "paused_for_human_review"
        - "restructuring"
      description: "Top-level pipeline status"

    current_phase:
      type: string
      description: "Phase ID of the currently executing phase, or empty if not in progress"

    phases:
      type: "map<phase_id, phase_state>"
      description: "Per-phase state. Keyed by phase_id."

    escalation_log:
      type: "list of escalation_event"
      description: "Chronological log of all escalation events across all phases"

    restructure_log:
      type: "list of restructure_event"
      description: "Chronological log of all restructure events"

    cross_phase_traceability:
      last_validated_at:
        type: string
        format: "ISO 8601"
      validation_result:
        type: string
        enum: ["not_run", "pass", "fail"]
      report_path:
        type: string
        description: "Path to the latest cross-phase validation report"

  # ---------------------------------------------------------------------------
  # 4.2 Per-Phase State
  # ---------------------------------------------------------------------------

  phase_state_schema:
    phase_id:
      type: string
    phase_name:
      type: string
    status:
      type: string
      enum:
        - "not_started"
        - "checklist_extraction"
        - "checklist_validation"
        - "validation_escalation"
        - "artifact_generation"
        - "judgment"
        - "revision_escalation"
        - "traceability_validation"
        - "completed"
        - "escalated"
        - "halted"
        - "human_review_pending"
        - "restructure_pending"

    started_at:
      type: string
      format: "ISO 8601"
      description: "When the phase first entered a non-not_started state"
    completed_at:
      type: string
      format: "ISO 8601"
      description: "When the phase reached a terminal state. Empty if still running."

    # Sub-loop counters
    checklist_validation_iteration:
      type: integer
      description: "Current iteration of the checklist validation sub-loop (0-based)"
    checklist_max_validation_iterations:
      type: integer
      description: "Budget for checklist validation iterations"
    revision_iteration:
      type: integer
      description: "Current iteration of the artifact revision sub-loop (0-based)"
    revision_max_iterations:
      type: integer
      description: "Budget for artifact revision iterations"

    # Escalation state
    escalation_status:
      type: string
      enum: ["none", "flagged", "halted", "human-review-pending", "restructure-pending"]
    escalation_policy_applied:
      type: string
      description: "The policy that was applied if escalation occurred"
    escalation_trigger:
      type: string
      description: "The trigger that caused escalation, if any"
    escalation_details:
      type: string
      description: "Human-readable summary of the escalation cause"

    # Current artifacts
    current_checklist:
      status:
        type: string
        enum: ["not_extracted", "validating", "validated", "flagged"]
      item_count:
        type: integer
      path:
        type: string
        description: "Path to the current checklist YAML on disk"

    current_artifact:
      status:
        type: string
        enum: ["not_generated", "generating", "under_judgment", "approved", "escalated"]
      path:
        type: string
        description: "Path to the current artifact on disk"

    current_traceability_mapping:
      status:
        type: string
        enum: ["not_generated", "generated", "validated", "has_warnings"]
      path:
        type: string

    # Iteration history
    iteration_log:
      type: "list of iteration_record"
      description: "Full history of generation-judgment iterations"

    iteration_record_schema:
      iteration:
        type: integer
      timestamp:
        type: string
        format: "ISO 8601"
      verdict:
        type: string
        enum: ["pass", "revise", "escalate"]
      failed_item_count:
        type: integer
      partial_item_count:
        type: integer
      passed_item_count:
        type: integer
      failed_item_ids:
        type: "list of string"
      partial_item_ids:
        type: "list of string"
      duration_seconds:
        type: number

    # Judgment results (latest)
    latest_evaluations:
      type: "list of evaluation objects"
      description: "The full evaluation list from the most recent judgment"
    latest_uncovered_concerns:
      type: "list of uncovered concern objects"

    # Phase output (populated on completion)
    phase_output:
      artifact:
        path: string
        format: string
        status: string  # "approved" | "escalated"
      completed_checklist:
        path: string
      traceability_mapping:
        path: string
      traceability_link_file:
        path: string
        description: "docs/traceability/phase-{N}-links.yaml"
      phase_summary:
        total_iterations: integer
        final_verdict: string
        checklist_item_count: integer
        passed_count: integer
        failed_count: integer
        partial_count: integer
        uncovered_concern_count: integer
        escalation_status: string

  # ---------------------------------------------------------------------------
  # 4.3 Escalation Event Schema
  # ---------------------------------------------------------------------------

  escalation_event_schema:
    event_id:
      type: string
      format: "ESC-{four-digit-sequence}"
      description: "Unique sequential ID across all escalation events"
    timestamp:
      type: string
      format: "ISO 8601"
    phase_id:
      type: string
    trigger_id:
      type: string
      description: "ESC-CHECKLIST-BUDGET | ESC-REVISION-BUDGET | ESC-OSCILLATION | ESC-TRACEABILITY-BROKEN | ESC-CRITICAL-CONCERN | ESC-AGENT-FAILURE"
    policy_applied:
      type: string
      description: "halt | flag-and-continue | human-review | restructure"
    details:
      type: string
      description: "Human-readable summary"
    failed_items:
      type: "list of string"
      description: "CL-* IDs that failed, if applicable"
    oscillating_items:
      type: "list of string"
      description: "CL-* IDs that oscillated, if applicable"
    resolution:
      type: string
      enum: ["pending", "resolved_by_human", "resolved_by_restructure", "pipeline_halted", "flagged_and_continued"]
    resolution_details:
      type: string
    resolution_timestamp:
      type: string
      format: "ISO 8601"

  # ---------------------------------------------------------------------------
  # 4.4 Checkpointing Protocol
  # ---------------------------------------------------------------------------
  #
  # The project state is checkpointed (written to disk) after every state
  # transition. This ensures that work is not lost on interruption.
  #
  # Checkpoint granularity: one checkpoint per state transition, not per
  # agent invocation. Agent invocations that do not cause a state transition
  # (e.g., an agent producing output that has not yet been evaluated) are
  # covered by the next state transition's checkpoint.
  #
  # The checkpoint is atomic: the state file is written to a temporary file
  # first, then renamed to the target path. This prevents corruption from
  # partial writes.

  checkpointing:
    trigger: "Every state transition (status change in any phase or in the pipeline)"

    protocol:
      - step: 1
        action: "Update the in-memory state object with the new state."
      - step: 2
        action: "Set last_updated to current ISO 8601 datetime."
      - step: 3
        action: "Serialize the state to YAML."
      - step: 4
        action: "Write to a temporary file: {storage_path}.tmp"
      - step: 5
        action: "Atomically rename {storage_path}.tmp to {storage_path}."
      - step: 6
        action: |
          If the transition is a phase completion (status -> completed or escalated),
          also create a snapshot: {storage_path}.{phase_id}.{timestamp}.yaml
          These snapshots are immutable — they record the state at each milestone.

    recovery_on_startup:
      action: |
        When the orchestrator starts:
        1. If {storage_path} exists, load it.
        2. If {storage_path} does not exist but {storage_path}.tmp exists,
           the previous write was interrupted. Rename .tmp to the main file.
        3. If neither exists, initialize a fresh state.
        4. Validate the loaded state:
           - All referenced artifact paths exist on disk.
           - Phase statuses are consistent with the state machine
             (no invalid transitions).
           - Iteration counters are within budgets.
        5. Resume from the current state. If a phase was in a non-terminal
           state (e.g., "judgment"), retry the last agent invocation.

  # ---------------------------------------------------------------------------
  # 4.5 Artifact Storage
  # ---------------------------------------------------------------------------
  #
  # All artifacts, checklists, traceability mappings, and reports are stored
  # on disk in a well-defined directory structure. The project state references
  # these paths but does not contain the artifact content itself (to keep the
  # state file manageable).

  artifact_storage:
    directory_structure: |
      docs/
        requirements/
          raw-requirements.md                     # External input (not pipeline-managed)
          requirements-inventory.yaml             # PH-000 artifact
          requirements-inventory-checklist.yaml   # PH-000 completed checklist
          requirements-inventory-traceability.yaml # PH-000 traceability mapping
        features/
          feature-specification.yaml              # PH-001 artifact
          feature-specification-checklist.yaml    # PH-001 completed checklist
          feature-specification-traceability.yaml # PH-001 traceability mapping
        design/
          solution-design.yaml                    # PH-002 artifact
          solution-design-checklist.yaml          # PH-002 completed checklist
          solution-design-traceability.yaml       # PH-002 traceability mapping
          interface-contracts.yaml                # PH-003 artifact
          interface-contracts-checklist.yaml      # PH-003 completed checklist
          interface-contracts-traceability.yaml   # PH-003 traceability mapping
        simulations/
          simulation-definitions.yaml             # PH-004 artifact
          simulation-definitions-checklist.yaml   # PH-004 completed checklist
          simulation-definitions-traceability.yaml # PH-004 traceability mapping
          simulation-registry.yaml                # Runtime registry
          simulation-health-report.yaml           # Periodic health report
        implementation/
          implementation-plan.yaml                # PH-005 artifact
          implementation-plan-checklist.yaml      # PH-005 completed checklist
          implementation-plan-traceability.yaml   # PH-005 traceability mapping
        verification/
          verification-report.yaml                # PH-006 artifact
          verification-sweep-checklist.yaml       # PH-006 completed checklist
          verification-sweep-traceability.yaml    # PH-006 traceability mapping
        traceability/
          registry.yaml                           # Element type registry
          phase-0-links.yaml through phase-6-links.yaml
          graph-index.yaml                        # Merged traceability index
          validation-report.yaml                  # Latest traceability validation
        pipeline/
          project-state.yaml                      # Current pipeline state
          project-state.PH-000-*.yaml             # Completion snapshots
          ...
          pipeline-report.yaml                    # Latest pipeline report
          dashboard.yaml                          # Project dashboard (section 5)
          escalation-log.yaml                     # Standalone escalation log

    invalidated_artifacts: |
      When a restructure invalidates artifacts, they are renamed:
        {original_path} -> {original_path}.invalidated.{ISO8601_timestamp}
      Example:
        docs/design/solution-design.yaml
          -> docs/design/solution-design.yaml.invalidated.2026-04-08T16-30-00Z
      These files are preserved for audit purposes and are never automatically
      deleted.


# ═══════════════════════════════════════════════════════════════════════════════
# 5. REPORTING
# ═══════════════════════════════════════════════════════════════════════════════
#
# The orchestrator produces reports at three granularities:
#   (a) Phase completion reports — emitted when a phase reaches a terminal state
#   (b) Pipeline completion report — emitted when all phases are done
#   (c) Project dashboard — a live view updated on every state transition
#
# ═══════════════════════════════════════════════════════════════════════════════

reporting:

  # ---------------------------------------------------------------------------
  # 5.1 Phase Completion Report
  # ---------------------------------------------------------------------------

  phase_completion_report:
    emitted_when: "A phase reaches any terminal state (completed, escalated, halted)"
    storage_path: "docs/pipeline/reports/phase-{phase_id}-report.yaml"

    schema:
      report_metadata:
        phase_id: string
        phase_name: string
        final_status: string  # completed | escalated | halted
        started_at: string
        completed_at: string
        total_wall_clock_seconds: number

      checklist_summary:
        total_items: integer
        extraction_iterations: integer
        extraction_max_iterations: integer
        validation_passed: boolean
        validation_escalated: boolean

      artifact_summary:
        output_path: string
        output_format: string
        artifact_status: string  # approved | escalated
        revision_iterations: integer
        revision_max_iterations: integer

      judgment_summary:
        final_verdict: string  # pass | revise | escalate
        passed_items: integer
        failed_items: integer
        partial_items: integer
        pass_rate_pct: number
        failed_item_details:
          type: "list of {id, criterion_summary, reason_summary}"
          description: "One-line summary for each failed/partial item"

      iteration_progression:
        description: |
          Shows how the pass/fail/partial counts changed across iterations.
          Useful for diagnosing whether the revision loop was making progress.
        iterations:
          type: "list of {iteration, passed, failed, partial, verdict}"

      traceability_summary:
        intra_phase_validation: string  # pass | fail | warnings
        orphaned_elements: integer
        uncovered_items: integer
        broken_references: integer

      escalation_summary:
        escalation_occurred: boolean
        trigger: string
        policy_applied: string
        details: string

      uncovered_concerns:
        total: integer
        high_severity: integer
        medium_severity: integer
        low_severity: integer
        items:
          type: "list of {id, concern_summary, severity}"

      coverage_statistics:
        description: |
          How many upstream elements this phase covers. Derived from
          the traceability link file.
        upstream_elements_total: integer
        upstream_elements_covered: integer
        coverage_pct: number
        uncovered_upstream_elements:
          type: "list of string"

  # ---------------------------------------------------------------------------
  # 5.2 Pipeline Completion Report
  # ---------------------------------------------------------------------------

  pipeline_completion_report:
    emitted_when: "All phases have reached terminal states (or pipeline is halted)"
    storage_path: "docs/pipeline/reports/pipeline-report.yaml"

    schema:
      report_metadata:
        pipeline_status: string  # completed | halted
        started_at: string
        completed_at: string
        total_wall_clock_seconds: number
        total_agent_invocations: integer
        total_revision_iterations: integer

      phase_summary_table:
        description: |
          One row per phase with key metrics.
        phases:
          type: "list of phase_row"
          phase_row:
            phase_id: string
            phase_name: string
            status: string
            iterations: integer
            pass_rate_pct: number
            escalation: string  # none | flagged | halted | human-reviewed | restructured
            duration_seconds: number

      traceability_report:
        cross_phase_validation: string  # pass | fail
        end_to_end_chain_completeness:
          total_ri_items: integer
          in_scope_items: integer
          complete_chains: integer
          incomplete_chains: integer
          chain_completeness_pct: number
          incomplete_chain_details:
            type: "list of {ri_id, terminal_phase, break_point}"
        phase_boundary_coverage:
          type: "list of {upstream_phase, downstream_phase, coverage_pct}"

      escalation_summary:
        total_escalation_events: integer
        events_by_type:
          type: "map<trigger_id, count>"
        events_by_policy:
          type: "map<policy_id, count>"
        restructure_events: integer
        restructure_details:
          type: "list of {triggering_phase, target_phase, result}"

      uncovered_concerns_aggregate:
        total_across_all_phases: integer
        by_severity:
          high: integer
          medium: integer
          low: integer
        by_phase:
          type: "map<phase_id, count>"
        notable_concerns:
          type: "list of {phase_id, concern_id, concern, severity}"
          description: "All high-severity concerns across all phases"

      quality_indicators:
        first_pass_rate:
          description: |
            Percentage of phases that passed on their first revision
            iteration (no revisions needed). Indicates how well the
            checklist-guided generation is working.
          value: number

        average_iterations_to_pass:
          description: |
            Average number of revision iterations across phases that
            eventually passed. Lower is better.
          value: number

        escalation_rate:
          description: |
            Percentage of phases that required escalation (any policy
            other than normal completion).
          value: number

        requirements_coverage:
          description: |
            Percentage of in-scope RI-* items that have a complete
            traceability chain to Phase 6.
          value: number

  # ---------------------------------------------------------------------------
  # 5.3 Project Dashboard
  # ---------------------------------------------------------------------------
  #
  # A continuously-updated view of the pipeline's status. Written to disk on
  # every state transition (alongside the checkpoint). Designed for both
  # programmatic consumption and human reading.

  project_dashboard:
    storage_path: "docs/pipeline/dashboard.yaml"
    updated_on: "Every state transition (same trigger as checkpointing)"

    schema:
      dashboard_metadata:
        last_updated: string  # ISO 8601
        pipeline_status: string

      phase_status_board:
        description: |
          One entry per phase showing current status, key metrics,
          and any outstanding issues. This is the primary at-a-glance view.
        phases:
          - phase_id: "PH-000-requirements-inventory"
            phase_name: "Requirements Inventory"
            status: "completed"  # current state machine state
            status_emoji_free_indicator: "[DONE]"  # [DONE] | [RUN] | [WAIT] | [HALT] | [FLAG] | [REVIEW] | [RSTRT]
            progress:
              checklist: "validated (10 items, 2 iterations)"
              artifact: "approved (42 inventory items)"
              traceability: "validated (0 warnings)"
            metrics:
              checklist_items: 10
              pass_rate_pct: 100.0
              revision_iterations: 2
              duration_seconds: 120
            issues: []  # list of one-line issue summaries

          - phase_id: "PH-001-feature-specification"
            phase_name: "Feature Specification"
            status: "judgment"
            status_emoji_free_indicator: "[RUN]"
            progress:
              checklist: "validated (9 items, 1 iteration)"
              artifact: "revision 2 of 3"
              traceability: "pending"
            metrics:
              checklist_items: 9
              pass_rate_pct: 77.8  # from latest judgment
              revision_iterations: 2
              duration_seconds: 95  # so far
            issues:
              - "CL-FS-001: 3 inventory items not yet mapped to features (RI-017, RI-038, RI-042)"
              - "CL-FS-004: 2 acceptance criteria are too vague (FT-003, FT-005)"

          # ... entries for PH-002 through PH-006

      active_issues:
        description: |
          Consolidated list of all outstanding issues across all phases.
          Issues are: failed/partial checklist items in the current phase,
          escalation events pending resolution, and high-severity
          uncovered concerns.
        items:
          type: "list of active_issue"
          active_issue:
            phase_id: string
            issue_type: string  # "checklist_failure" | "escalation" | "uncovered_concern"
            summary: string
            severity: string  # "high" | "medium" | "low"
            since: string  # ISO 8601, when first observed

      timeline:
        description: |
          Chronological event log for the last N events (default 50).
          Provides a scrollback view of what happened recently.
        events:
          type: "list of timeline_event"
          timeline_event:
            timestamp: string
            phase_id: string
            event: string  # e.g., "judgment: verdict=revise (2 failed, 1 partial)"
            severity: string  # "info" | "warning" | "error"

      next_actions:
        description: |
          What the orchestrator will do next. Useful for understanding
          what is coming and for human operators deciding whether to
          intervene.
        items:
          type: "list of string"
          examples:
            - "PH-001: Revision iteration 3 of 3 — invoking artifact generator with feedback on CL-FS-001 and CL-FS-004"
            - "PH-002: Waiting for PH-001 to complete"
            - "PH-003: Not started (blocked by PH-002)"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. IMPLEMENTATION APPROACH
# ═══════════════════════════════════════════════════════════════════════════════

implementation_approach:

  # ---------------------------------------------------------------------------
  # 6.1 Technology Stack
  # ---------------------------------------------------------------------------

  technology_stack:
    language: "TypeScript"
    runtime: "Node.js"
    rationale: |
      Matches the project's existing server-side stack. TypeScript's type
      system enforces the state machine transitions at compile time via
      discriminated unions. The async/await model supports sequential agent
      invocations cleanly.

    dependencies:
      core:
        - package: "yaml"
          purpose: "Parse and serialize all YAML state files and reports"
        - package: "@anthropic-ai/sdk"
          purpose: "Invoke Claude-based agents (extractor, validator, generator, judge)"

      state_management:
        - package: "none (custom)"
          purpose: |
            State management is simple enough to implement directly:
            in-memory state object + YAML serialization + atomic file writes.
            No database or external state store is needed — the project
            state file is the source of truth.

      testing:
        - package: "vitest"
          purpose: "Unit tests for state machine transitions, oscillation detection, component ordering"

  # ---------------------------------------------------------------------------
  # 6.2 Module Structure
  # ---------------------------------------------------------------------------

  module_structure:
    - path: "src/server/orchestrator/index.ts"
      exports:
        - "PipelineOrchestrator"
        - "runPipeline"
      description: |
        Entry point. PipelineOrchestrator is the main class.
        runPipeline is a convenience function that creates an
        orchestrator and runs all phases.

    - path: "src/server/orchestrator/types.ts"
      description: |
        All type definitions: PipelineState, PhaseState, EscalationEvent,
        IterationRecord, PhaseStatus (discriminated union), PhaseTransition,
        EscalationPolicy, RestructureRequest, DashboardState, etc.

    - path: "src/server/orchestrator/state-machine.ts"
      description: |
        Phase lifecycle state machine implementation. Exports a
        PhaseStateMachine class that enforces valid transitions and
        tracks the current state. The state machine is parameterized
        by the phase configuration (iteration budgets, escalation
        policies).

        Key function: transition(current_state, trigger) -> new_state | error
        The transition function is a pure function — no side effects.
        Side effects (agent invocations, file writes) are handled by
        the orchestrator, not the state machine.

    - path: "src/server/orchestrator/phase-runner.ts"
      description: |
        Implements the per-phase execution protocol: the checklist
        sub-loop, the artifact sub-loop, and traceability validation.
        Owns the loop counters and the generator input assembly logic.

        Key class: PhaseRunner
        Key method: runPhase(phase_config, project_state) -> PhaseResult
        PhaseResult includes the terminal state, the artifact, the
        completed checklist, the traceability mapping, and any
        escalation events.

    - path: "src/server/orchestrator/oscillation-detector.ts"
      description: |
        Implements the oscillation detection algorithm from section 2.4.
        Pure function: detectOscillation(iteration_log) -> OscillationResult.

    - path: "src/server/orchestrator/component-orderer.ts"
      description: |
        Implements the Phase 5 component ordering algorithm from
        section 1.3. Pure function:
        computeComponentOrder(solution_design) -> ComponentOrder[].

    - path: "src/server/orchestrator/dependency-resolver.ts"
      description: |
        Resolves the phase dependency graph from phase definitions.
        Computes topological sort for phase execution order.
        Evaluates start conditions for a given phase.

    - path: "src/server/orchestrator/escalation-handler.ts"
      description: |
        Implements escalation policy application. Given a trigger and
        a policy configuration, produces the state transitions and
        side effects (halt, flag, restructure, human-review).

        The restructure protocol (section 3.4) is implemented here,
        including the loop guard and the artifact invalidation cascade.

    - path: "src/server/orchestrator/state-persistence.ts"
      description: |
        Handles reading, writing, and checkpointing the project state.
        Implements the atomic write protocol (write-to-temp, rename).
        Implements recovery on startup (section 4.4).

    - path: "src/server/orchestrator/reporter.ts"
      description: |
        Generates phase completion reports, the pipeline completion
        report, and the project dashboard. All reports are YAML files
        written to docs/pipeline/reports/.

    - path: "src/server/orchestrator/agent-invoker.ts"
      description: |
        Wraps agent invocations: assembles inputs per the agent's
        input specification, invokes the agent (via Claude API or
        sub-agent mechanism), validates the output structure, and
        handles retries on structural failures.

        Key function: invokeAgent(role_id, inputs) -> AgentOutput
        Supports a single retry with error feedback on structural
        failure.

  # ---------------------------------------------------------------------------
  # 6.3 Key Implementation Patterns
  # ---------------------------------------------------------------------------

  implementation_patterns:

    - pattern: "Discriminated union for phase states"
      description: |
        TypeScript's discriminated unions enforce valid state transitions
        at compile time. Each phase state is a tagged union variant with
        type-specific fields:

        type PhaseState =
          | { status: "not_started" }
          | { status: "checklist_extraction"; iteration: number }
          | { status: "checklist_validation"; iteration: number; checklist: ChecklistItems }
          | { status: "artifact_generation"; revision: number; checklist: ChecklistItems; previousArtifact?: Artifact; previousEvals?: Evaluations }
          | { status: "judgment"; revision: number; artifact: Artifact; checklist: ChecklistItems }
          | { status: "traceability_validation"; artifact: Artifact; mapping: TraceMapping }
          | { status: "completed"; output: PhaseOutput }
          | { status: "escalated"; output: PhaseOutput; escalation: EscalationEvent }
          | { status: "halted"; escalation: EscalationEvent }
          | { status: "human_review_pending"; context: HumanReviewContext }
          | { status: "restructure_pending"; request: RestructureRequest }

        The transition function takes the current variant and a trigger,
        and returns a new variant. TypeScript's exhaustiveness checking
        ensures every state/trigger combination is handled.

    - pattern: "Event-sourced state transitions"
      description: |
        Every state transition is recorded as an event. The project
        state is the result of replaying all events from the beginning.
        In practice, the state is materialized (stored as a snapshot)
        after every transition for efficiency, but the event log
        (timeline in the dashboard) provides a complete audit trail.

        Events are: PhaseStarted, ChecklistExtracted, ChecklistValidated,
        ChecklistValidationFailed, ArtifactGenerated, JudgmentCompleted,
        TraceabilityValidated, PhaseCompleted, PhaseEscalated,
        PhaseHalted, OscillationDetected, RestructureTriggered,
        HumanReviewRequested, HumanInputReceived.

    - pattern: "Agent invocation as an async boundary"
      description: |
        Each agent invocation is an async call that may take seconds to
        minutes (LLM calls). The orchestrator awaits each invocation
        sequentially — no parallel agent invocations within a phase.

        The invocation boundary is where checkpointing occurs: before
        invoking an agent, the orchestrator checkpoints the current state.
        If the process dies during the agent call, recovery restarts
        from the last checkpoint and re-invokes the agent.

    - pattern: "Content hash computation at phase start"
      description: |
        When a phase starts, the orchestrator computes SHA-256 hashes
        of all input artifacts and compares them to declared content_hash
        values. This is a one-time cost at phase start, not per-agent-call.

        The hash is computed over the raw file bytes, not the parsed
        content. This ensures that whitespace changes and comment changes
        are detected.

    - pattern: "Restructure as a state machine reset"
      description: |
        Restructure does not require special control flow. It is
        implemented as:
          1. Record the restructure event.
          2. Reset the target phase and all intermediate phases to
             "not_started" (with artifact invalidation).
          3. Re-evaluate phase start conditions.
          4. The normal phase execution flow picks up from the earliest
             phase that is "not_started" with satisfied prerequisites.

        The loop guard (section 3.4, step 2) is checked before the reset.
        If the guard fires, the reset does not occur and the pipeline
        halts instead.

  # ---------------------------------------------------------------------------
  # 6.4 File Reference Summary
  # ---------------------------------------------------------------------------

  file_reference:
    - path: "docs/pipeline/project-state.yaml"
      read_by: ["orchestrator (on startup)", "dashboard generator", "human operator"]
      written_by: ["orchestrator (on every state transition)"]
      purpose: "Persistent pipeline state — single source of truth"

    - path: "docs/pipeline/dashboard.yaml"
      read_by: ["human operator", "external monitoring"]
      written_by: ["orchestrator (on every state transition)"]
      purpose: "Live project status view"

    - path: "docs/pipeline/reports/phase-{phase_id}-report.yaml"
      read_by: ["human operator", "pipeline completion report generator"]
      written_by: ["orchestrator (on phase completion)"]
      purpose: "Per-phase completion report"

    - path: "docs/pipeline/reports/pipeline-report.yaml"
      read_by: ["human operator"]
      written_by: ["orchestrator (on pipeline completion)"]
      purpose: "Final pipeline completion report"

    - path: "docs/pipeline/escalation-log.yaml"
      read_by: ["human operator", "restructure protocol"]
      written_by: ["orchestrator (on each escalation event)"]
      purpose: "Chronological escalation event log"

    - path: "docs/pipeline/project-state.{phase_id}.{timestamp}.yaml"
      read_by: ["human operator (for audit)"]
      written_by: ["orchestrator (on phase completion)"]
      purpose: "Immutable state snapshots at milestones"
```