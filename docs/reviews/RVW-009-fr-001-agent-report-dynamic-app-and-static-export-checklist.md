<!--
Copyright (c) 2026 Martin.Bechard@DevConsult.ca
Artifact-ID: 9c526981-22eb-498f-a44e-7bccd9245773
Created-UTC: 2026-08-12T12:58:27Z
Creating-Agent: Dev Artifact Reviewer
Runtime: Codex
Dispatched-Model: gpt-5.6-sol
Reasoning-Effort: low
Task-ID: /root/review_functional_spec
Artifact-ID-Evidence: runtime-supplied
Created-UTC-Evidence: runtime-supplied
Creating-Agent-Evidence: runtime-supplied
Runtime-Evidence: runtime-supplied
Dispatched-Model-Evidence: runtime-supplied
Reasoning-Effort-Evidence: runtime-supplied
Task-ID-Evidence: runtime-supplied
-->

# FR-001 Functional Specification Review Checklist

## Review Scope

- Target artifact: `docs/requirements/functional/FR-001-agent-report-dynamic-app-and-static-export.md`
- Parent architecture input: `docs/architecture/ARC-001-agent-report-dynamic-app-and-static-export.md`
- Subsystem design input: `docs/design/high-level/HLD-003-agent-report-dynamic-app-and-static-export.md`
- Current-behavior inputs: `tools/report/README.md`, `tools/report/src/agent_report/mcp_server.py`, `tools/report/src/agent_report/mcp_report.py`, `tools/report/src/agent_report/cli.py`, and `tools/report/scripts/run-timeline.py`
- Test-evidence inputs: the test paths named in FR-001 under Related Tests and Verification
- Reviewed FR-001 SHA-256: `705d645aa9ff63d5b7f98cbdd46cc7bd013dab60e22c483b9e801e12004b5723`
- Reviewed ARC-001 SHA-256: `d85df60a9eb2ab29dc0509e2d8e6c5ae275be1432a47e61ecec3f297e42d28b0`
- Reviewed HLD-003 SHA-256: `aaa7bcda252ca620dcab33b7c273496c20ab757be52d1b7a411e9f18f7954908`
- Generic checklist: `review-checklist-structured.md`
- Artifact checklist: `review-checklist-functional-spec.md`
- Shared verifier: `verify-documentation-page`
- Terminology snapshot: `terminology.md` was absent from the configured provider snapshot at catalog revision `d801aa1fb7ddcc330a5e3173372ea6af4a3d08ec58074478e85aa5603e926658`.
- Link-verifier dispatch: `verify_markdown_links` rejected `/Users/martinbechard/dev/agent-runner` as outside its configured workspace roots. The verifier assessment preserves this as a non-blocking capability gap and does not use a fallback to bypass the structured rejection.

The review identified these contract elements before assessment: local operator, MCP client, CLI caller, Tauri host, report worker, Rust discovery engine, and static report reader; eight actor workflows; desktop, CLI, MCP, worker-message, and static-file surfaces; report and operation states; and ten verification blocks.

## Findings And Corrections

### High impact

None.

### Medium impact

None.

### Low impact

None.

### Verified Corrections

#### F-001: Required workflow diagrams added

- Checklist item: FS-30
- Target locations: `Workflows > Workflow 6: Use The CLI`, `Workflows > Workflow 8: Read A Static Report`, and `Workflow Diagram`
- Correction evidence: `Workflow Diagram > CLI Workflow` now uses a Mermaid sequence diagram for validation, argument failure, service execution, success, and handled operation failure. `Workflow Diagram > Static Report Reading Workflow` now uses a Mermaid flowchart for entry selection, relative navigation, omitted-evidence decisions, and dynamic-application recovery.
- Verification: PASS. The diagrams cover the ordered steps and branches in Workflow 6 and Workflow 8 with appropriate diagram types.
- Authority: `review-checklist-functional-spec.md` requires a diagram for every workflow with two or more ordered actor actions. The `review-functional-spec` skill treats a qualifying workflow left only in prose as a response-adequacy finding.
- Residual impact: None.

#### F-002: CLI operation examples and mapping added

- Checklist items: FS-28, FS-41, and FS-43
- Target locations: `Entry Points > Operation Inventory` and `Interface Examples > CLI Success And Failure`
- Correction evidence: `CLI Operation-To-Example Map` maps all documented CLI modes to the preceding example or Examples A through F. The examples cover thread and rollout-path Codex reports, Codex and Junie catalogs, native Junie, methodology, prompt-runner, comparison, and sealed Codex reproduction. They include representative outputs, diagnostics, and exit statuses. Example E gives a concrete shared-failure rationale for methodology, prompt-runner, and comparison adapters.
- Verification: PASS. Every operation has mapped evidence, and distinct inputs, outputs, validation, and handled-failure behavior remain visible.
- Authority: `review-checklist-functional-spec.md` requires proportionate examples for documented CLI behavior and requires each operation to be mapped when one example covers multiple operations.
- Residual impact: None.

#### F-003: Architecture and subsystem-design authority separated

- Checklist items: GS-10, GS-12, GS-17, GS-23, FS-09, FS-24, FS-34, FS-35, and FS-38
- Target locations: `Authoritative Sources`, `Related Code`, `Related Wiki Pages`, `Entry Points > Operation Inventory`, `Scope`, and `Documentation Acceptance`
- Correction evidence: FR-001 now assigns system architecture, system-wide constraints, runtime roots, authority boundaries, and compatibility policy to ARC-001. It separately assigns subsystem component ownership, exact operation allocation, contracts, and implementation order to HLD-003. Intended module paths are attributed to HLD-003 rather than to architecture.
- Verification: PASS. ARC-001 defines the system frame and ARC-01 through ARC-16. HLD-003 accepts those parent constraints and owns the subsystem component and operation inventory. FR-001 retains actor-visible precedence without absorbing either design scope.
- Authority: The accepted ARC-001 and HLD-003 authority statements, plus `review-checklist-structured.md` scope-separation questions.
- Residual impact: None.

## Integrated Verdict

**FUNCTIONAL SPECIFICATION REVIEW: PASS.**

FR-001 is coherent and source-aware. It correctly separates its actor-visible authority from ARC-001 system architecture and HLD-003 subsystem design. MCP remains first-class, independently runnable without Tauri, and preserves the current `generate_report`, `query_time_range`, and `get_event_details` operations. Current CLI and static backends also remain supported. The authority-chain correction, workflow diagrams, and complete CLI operation-to-example mapping resolve F-001 through F-003. Documentation acceptance passes.

**IMPLEMENTATION READINESS: BLOCKED.** This matches FR-001, ARC-001, and HLD-003. The four product decisions and lower-level protocol, cache, export, and UI designs remain prerequisites.

**TERMINOLOGY REVIEW: PASS.** The configured terminology snapshot returned the valid ABSENT outcome. No governed preferred terms were available to apply.

## Completed Generic Structured-Artifact Checklist

### Skill Workflow

#### GS-01

- Status: PASS
- Question: Does the review identify the target artifact path before scoring checklist items?
- Evidence type: exact quotation
- Evidence source: this review, Review Scope
- Evidence: “Target artifact: `docs/requirements/functional/FR-001-agent-report-dynamic-app-and-static-export.md`”
- Assessment: The target is explicit before the checklist.
- Correction: None.
- Authority: `review-checklist-structured.md`, Skill Workflow Questions.
- Impact: No unresolved impact.

#### GS-02

- Status: PASS
- Question: Does the review identify the input artifact paths or directives before scoring checklist items?
- Evidence type: summary
- Evidence source: this review, Review Scope
- Evidence: The review names ARC-001, HLD-003, current-behavior files, test evidence, both checklists, and the shared verifier.
- Assessment: Material inputs are explicit before scoring.
- Correction: None.
- Authority: `review-checklist-structured.md`, Skill Workflow Questions.
- Impact: No unresolved impact.

#### GS-03

- Status: PASS
- Question: Does the review name review-checklist-structured.md as the generic base checklist?
- Evidence type: exact quotation
- Evidence source: this review, Review Scope
- Evidence: “Generic checklist: `review-checklist-structured.md`”
- Assessment: The generic checklist is named.
- Correction: None.
- Authority: `review-checklist-structured.md`, Skill Workflow Questions.
- Impact: No unresolved impact.

#### GS-04

- Status: N/A
- Question: Does the completed review checklist save next to the target using target-name.review-checklist-structured.md?
- Evidence type: not applicable
- Evidence source: dispatch directive
- Evidence: The dispatch explicitly approves and requires `docs/reviews/RVW-009-fr-001-agent-report-dynamic-app-and-static-export-checklist.md` as the only review evidence file.
- Assessment: The request-specific approved location overrides the generic default naming and placement rule.
- Correction: None.
- Authority: User-approved dispatch scope takes precedence over the generic skill default.
- Impact: No unresolved impact; the review remains in the repository's approved review location.

#### GS-05

- Status: PASS
- Question: Does the checklist exist before findings are written?
- Evidence type: assessment
- Evidence source: review execution record
- Evidence: The generic, functional, and shared-verifier assessments were completed before the findings were derived and recorded.
- Assessment: Findings derive from completed checklist failures.
- Correction: None.
- Authority: `review-checklist-structured.md`, Skill Workflow Questions.
- Impact: No unresolved impact.

#### GS-06

- Status: PASS
- Question: Are findings derived from failed or questionable checklist items rather than independent opinion?
- Evidence type: summary
- Evidence source: this review, Findings And Corrections
- Evidence: The retained correction records cite FS-30 for F-001 and FS-28, FS-41, and FS-43 for F-002.
- Assessment: Each original finding traces to checklist items that now pass after correction.
- Correction: None.
- Authority: `review-checklist-structured.md`, Skill Workflow Questions.
- Impact: No unresolved impact.

#### GS-07

- Status: PASS
- Question: Do findings cite checklist item IDs and target locations?
- Evidence type: summary
- Evidence source: this review, Findings And Corrections
- Evidence: Each finding names its checklist IDs and target section locations.
- Assessment: Finding traceability is complete.
- Correction: None.
- Authority: `review-checklist-structured.md`, Skill Workflow Questions.
- Impact: No unresolved impact.

#### GS-08

- Status: PASS
- Question: Does every finding state a correction, authority, and impact?
- Evidence type: summary
- Evidence source: this review, Findings And Corrections
- Evidence: F-001 and F-002 each retain correction evidence, verification, authority, and residual impact.
- Assessment: The review preserves an actionable and auditable correction record.
- Correction: None.
- Authority: `review-checklist-structured.md`, Skill Workflow Questions.
- Impact: No unresolved impact.

#### GS-09

- Status: PASS
- Question: Is severity based on practical impact instead of writing preference?
- Evidence type: assessment
- Evidence source: this review, Findings And Corrections
- Evidence: Both findings are medium because they force downstream workflow or test authors to reconstruct observable contracts; no wording preference determines severity.
- Assessment: Severity reflects downstream ambiguity.
- Correction: None.
- Authority: `review-checklist-structured.md`, Skill Workflow Questions.
- Impact: No unresolved impact.

### Input Coverage

#### GS-10

- Status: PASS
- Question: Are all material input directives traced to target locations or marked as not applied?
- Evidence type: summary
- Evidence source: FR-001, ARC-001, and HLD-003
- Evidence: FR-001 traces the accepted decision packet, ARC-001, HLD-003, current code and tests, README, and metrics design through Authoritative Sources, Related Code, Related Tests, Open Questions, and Verification.
- Assessment: The material input boundaries are traceable.
- Correction: None.
- Authority: `review-checklist-structured.md`, Input Coverage Questions.
- Impact: No unresolved impact.

#### GS-11

- Status: PASS
- Question: Are missing directive applications marked as failures or open questions instead of ignored?
- Evidence type: summary
- Evidence source: FR-001, Open Questions and Implementation Readiness
- Evidence: Four unresolved product decisions are named with recommendations, impact, and owners. Lower-level design prerequisites are named as blockers.
- Assessment: Missing decisions are visible rather than silently assumed.
- Correction: None.
- Authority: `review-checklist-structured.md`, Input Coverage Questions.
- Impact: No unresolved impact.

#### GS-12

- Status: PASS
- Question: Does the target avoid contradicting stated input directives?
- Evidence type: assessment
- Evidence source: FR-001, ARC-001, HLD-003, current MCP source, and README
- Evidence: FR-001, ARC-001, and HLD-003 retain current MCP operations, require MCP to run without Tauri, preserve current static adapters, keep Rust as Codex discovery authority, and separate implemented from intended behavior. Current source registers the three retained MCP tools.
- Assessment: No material contradiction was found.
- Correction: None.
- Authority: `review-checklist-structured.md`, Input Coverage Questions.
- Impact: No unresolved impact.

#### GS-13

- Status: PASS
- Question: Are unsupported requirements or claims flagged with exact evidence gaps rather than plausible paraphrases labeled as quotations?
- Evidence type: summary
- Evidence source: FR-001, Related Tests, Open Questions, Operation Inventory, and Verification
- Evidence: Intended operations and planned tests are labeled intended or planned. Unidentified test files are stated as “Not yet identified.”
- Assessment: Future behavior is not misrepresented as implemented evidence.
- Correction: None.
- Authority: `review-checklist-structured.md`, Input Coverage Questions.
- Impact: No unresolved impact.

### Internal Logic

#### GS-14

- Status: PASS
- Question: Are concepts introduced before they are used?
- Evidence type: assessment
- Evidence source: FR-001
- Evidence: Current Understanding establishes the product frame; Actors and Entry Points precede detailed workflows; Concepts defines project-specific scope and snapshot terms before later rules and verification.
- Assessment: The dependency order supplies sufficient context.
- Correction: None.
- Authority: `review-checklist-structured.md`, Internal Logic Questions.
- Impact: No unresolved impact.

#### GS-15

- Status: PASS
- Question: Does the document follow a logical dependency order?
- Evidence type: summary
- Evidence source: FR-001 section order
- Evidence: Sources and evidence precede workflow context; actor and entry-point contracts precede workflows; examples and diagrams precede rules, edge cases, acceptance, readiness, and verification.
- Assessment: The order supports progressive understanding.
- Correction: None.
- Authority: `review-checklist-structured.md`, Internal Logic Questions.
- Impact: No unresolved impact.

#### GS-16

- Status: PASS
- Question: Does the document avoid material contradictions?
- Evidence type: assessment
- Evidence source: FR-001 internal reconciliation, ARC-001, and HLD-003
- Evidence: Root-only defaults, independent child and collaborator scope, explicit refresh, export modes, MCP independence, compatibility behavior, acceptance, and readiness are consistent across FR-001, ARC-001, and HLD-003.
- Assessment: No material internal contradiction was found.
- Correction: None.
- Authority: `review-checklist-structured.md`, Internal Logic Questions.
- Impact: No unresolved impact.

#### GS-17

- Status: PASS
- Question: Are requirements distinguished from solution choices?
- Evidence type: summary
- Evidence source: FR-001, Authoritative Sources, Operation Inventory, Open Questions, and Scope
- Evidence: Actor-visible behavior is stated in FR-001. System-wide architecture belongs to ARC-001. Subsystem ownership and exact operation allocation belong to HLD-003. Component internals remain with later component designs. Proposed defaults and unresolved choices are labeled.
- Assessment: Requirements and technical choices remain distinguishable.
- Correction: None.
- Authority: `review-checklist-structured.md`, Internal Logic Questions.
- Impact: No unresolved impact.

#### GS-18

- Status: PASS
- Question: Are goals distinguished from features where relevant?
- Evidence type: summary
- Evidence source: FR-001, Current Understanding, Parent Workflow, Actors, Scope, and Workflows
- Evidence: The operator's outcome is stated separately from the included features and detailed workflows.
- Assessment: Goal and feature inventories are not conflated.
- Correction: None.
- Authority: `review-checklist-structured.md`, Internal Logic Questions.
- Impact: No unresolved impact.

### Structured Design Scope

#### GS-19

- Status: N/A
- Question: When the target is a component or prompt-chain design, does it explain the workflow rather than only the final artifact contract?
- Evidence type: not applicable
- Evidence source: target artifact classification
- Evidence: FR-001 is a functional specification, not a component or prompt-chain design.
- Assessment: The mode-specific question does not apply.
- Correction: None.
- Authority: `review-checklist-structured.md`, Structured Design Scope Questions.
- Impact: No unresolved impact.

#### GS-20

- Status: N/A
- Question: Are skills treated as compact operational artifacts rather than the place where the whole component workflow is explained?
- Evidence type: not applicable
- Evidence source: target artifact classification
- Evidence: FR-001 does not define an Agent Skill.
- Assessment: The question does not apply.
- Correction: None.
- Authority: `review-checklist-structured.md`, Structured Design Scope Questions.
- Impact: No unresolved impact.

#### GS-21

- Status: N/A
- Question: When the target is an architecture document, does it stay focused on system shape, boundaries, interactions, responsibilities, and major boundary-shaping technology choices?
- Evidence type: not applicable
- Evidence source: target artifact classification
- Evidence: FR-001 is not the architecture artifact; ARC-001 is the parent architecture input, and HLD-003 is the subsystem design input.
- Assessment: The architecture-specific scoring question does not apply to FR-001.
- Correction: None.
- Authority: `review-checklist-structured.md`, Structured Design Scope Questions.
- Impact: No unresolved impact.

#### GS-22

- Status: N/A
- Question: When the target is a component design document, does it explain the chosen component or workflow without silently redesigning system boundaries?
- Evidence type: not applicable
- Evidence source: target artifact classification
- Evidence: FR-001 is not a component design.
- Assessment: The question does not apply.
- Correction: None.
- Authority: `review-checklist-structured.md`, Structured Design Scope Questions.
- Impact: No unresolved impact.

#### GS-23

- Status: PASS
- Question: Does the target avoid mixing architecture and component design concerns so heavily that decision scope becomes unclear?
- Evidence type: assessment
- Evidence source: FR-001, ARC-001, and HLD-003
- Evidence: FR-001 assigns system-wide constraints and authority boundaries to ARC-001. It labels `application_service.py`, `event_cache.py`, `report_worker.py`, and `static_export.py` as intended paths established by HLD-003. It leaves classes, functions, DTO fields, table names, migration statements, cursor encoding, and UI-test internals to lower-level design.
- Assessment: Technical detail supports observable behavior without obscuring decision ownership.
- Correction: None.
- Authority: `review-checklist-structured.md`, Structured Design Scope Questions.
- Impact: No unresolved impact.

### Writing And Section Model

#### GS-24

- Status: PASS
- Question: For every prose sentence, table-row claim, and complete list-item claim, does it add information or an action that the document requires?
- Evidence type: assessment
- Evidence source: complete sentence and claim sweep of FR-001
- Evidence: The sweep found no decorative or redundant sentence that materially fails the Needed check. Repeated MCP and compatibility statements establish requirements across source, actor, operation, rule, acceptance, and verification contexts.
- Assessment: Claims contribute contract, evidence, context, or verification information.
- Correction: None.
- Authority: `review-checklist-structured.md`, Writing And Section Model Questions, Needed check.
- Impact: No unresolved impact.

#### GS-25

- Status: PASS
- Question: For every prose sentence, table-row claim, and complete list-item claim, does it use familiar words and explain every necessary technical term?
- Evidence type: assessment
- Evidence source: complete sentence and claim sweep of FR-001
- Evidence: Project-specific terms such as root task, collaborator, scope, preflight, snapshot, normalized event cache, and export modes are defined. Exact protocol and product identifiers remain appropriately literal.
- Assessment: No material Clear-check failure was found.
- Correction: None.
- Authority: `review-checklist-structured.md`, Writing And Section Model Questions, Clear check.
- Impact: No unresolved impact.

#### GS-26

- Status: PASS
- Question: For every prose sentence, table-row claim, and complete list-item claim, when it uses “the” before a common noun, has an earlier sentence introduced that specific instance?
- Evidence type: assessment
- Evidence source: complete sentence and claim sweep of FR-001
- Evidence: Definite references resolve to named actors, operations, sections, artifacts, files, snapshots, workers, services, or immediately preceding workflow objects.
- Assessment: No material Definite-reference failure was found.
- Correction: None.
- Authority: `review-checklist-structured.md`, Writing And Section Model Questions, Definite reference check.
- Impact: No unresolved impact.

#### GS-27

- Status: PASS
- Question: Does the document use plain English, short sentences, and simple words?
- Evidence type: assessment
- Evidence source: FR-001 prose review
- Evidence: Most requirements use short active sentences. Longer technical sentences preserve enumerations or exact boundary detail and remain understandable.
- Assessment: The prose is proportionate to the specification's technical scope.
- Correction: None.
- Authority: `review-checklist-structured.md` and `ste-technical-writing`.
- Impact: No unresolved impact.

#### GS-28

- Status: PASS
- Question: Are jargon, buzzwords, and abstract phrasing avoided unless clearly needed?
- Evidence type: assessment
- Evidence source: FR-001 prose review
- Evidence: Technical terms name concrete product concepts, formats, protocols, states, or operations. No material buzzword pattern was found.
- Assessment: Specialized language is necessary and defined or self-identifying.
- Correction: None.
- Authority: `review-checklist-structured.md` and `ste-technical-writing`.
- Impact: No unresolved impact.

#### GS-29

- Status: PASS
- Question: Are technical terms defined once when first introduced?
- Evidence type: summary
- Evidence source: FR-001, Current Understanding and Concepts
- Evidence: The opening introduces Agent Report and bounded snapshots. Concepts supplies stable definitions for actor-visible project terms used by detailed rules.
- Assessment: Necessary terms receive a usable definition.
- Correction: None.
- Authority: `review-checklist-structured.md` and `ste-technical-writing`.
- Impact: No unresolved impact.

#### GS-30

- Status: PASS
- Question: Are vague words such as robust, seamless, optimize, leverage, and enhance removed or made specific?
- Evidence type: assessment
- Evidence source: lexical and prose review of FR-001
- Evidence: No material use of the listed vague words was found. Terms such as bounded, coherent, current, planned, and atomic have explicit behavioral meaning.
- Assessment: Requirements are specific.
- Correction: None.
- Authority: `review-checklist-structured.md` and `ste-technical-writing`.
- Impact: No unresolved impact.

#### GS-31

- Status: PASS
- Question: Does the document stay concrete and actionable?
- Evidence type: summary
- Evidence source: FR-001
- Evidence: The specification names actors, selectors, limits, states, errors, recovery actions, outputs, decisions, owners, interface examples, workflow diagrams, and verification assertions.
- Assessment: Downstream work can derive concrete contracts without an unresolved review finding.
- Correction: None.
- Authority: `review-checklist-structured.md`, Writing And Section Model Questions.
- Impact: No unresolved impact.

#### GS-32

- Status: PASS
- Question: When relevant, does the document include finality, technical directives, constraints, definition of good, and test cases?
- Evidence type: summary
- Evidence source: FR-001, Scope, States And Rules, Documentation Acceptance, Implementation Readiness, and Verification
- Evidence: The artifact states acceptance, readiness, constraints, observable rules, and ten testable verification blocks.
- Assessment: Required finality and verification content is present.
- Correction: None.
- Authority: `review-checklist-structured.md`, Writing And Section Model Questions.
- Impact: No unresolved impact.

#### GS-33

- Status: N/A
- Question: When the target is a component design document, are finality, technical directives, and definition of good kept distinct?
- Evidence type: not applicable
- Evidence source: target artifact classification
- Evidence: FR-001 is not a component design.
- Assessment: The mode-specific question does not apply.
- Correction: None.
- Authority: `review-checklist-structured.md`, Writing And Section Model Questions.
- Impact: No unresolved impact.

#### GS-34

- Status: N/A
- Question: When the target is an architecture document, are system shape, boundaries and interactions, constraints, and definition of good kept distinct?
- Evidence type: not applicable
- Evidence source: target artifact classification
- Evidence: FR-001 is not an architecture document.
- Assessment: The mode-specific question does not apply.
- Correction: None.
- Authority: `review-checklist-structured.md`, Writing And Section Model Questions.
- Impact: No unresolved impact.

### Markdown And YAML

#### GS-35

- Status: N/A
- Question: When both markdown and YAML exist, does markdown remain the authority unless the user asked for YAML as primary?
- Evidence type: not applicable
- Evidence source: FR-001 format
- Evidence: The artifact contains Markdown and no companion YAML contract.
- Assessment: The comparison does not apply.
- Correction: None.
- Authority: `review-checklist-structured.md`, Markdown And YAML Questions.
- Impact: No unresolved impact.

#### GS-36

- Status: N/A
- Question: Does the YAML preserve the markdown document's real section structure?
- Evidence type: not applicable
- Evidence source: FR-001 format
- Evidence: No YAML artifact is in review scope.
- Assessment: The question does not apply.
- Correction: None.
- Authority: `review-checklist-structured.md`, Markdown And YAML Questions.
- Impact: No unresolved impact.

#### GS-37

- Status: N/A
- Question: Do grouped items remain grouped rather than flattened into unrelated entries?
- Evidence type: not applicable
- Evidence source: FR-001 format
- Evidence: This checklist question concerns Markdown-to-YAML projection; no YAML projection exists.
- Assessment: The question does not apply.
- Correction: None.
- Authority: `review-checklist-structured.md`, Markdown And YAML Questions.
- Impact: No unresolved impact.

#### GS-38

- Status: N/A
- Question: Are stable IDs preserved in YAML entries?
- Evidence type: not applicable
- Evidence source: FR-001 format
- Evidence: No YAML entries are in scope.
- Assessment: The question does not apply.
- Correction: None.
- Authority: `review-checklist-structured.md`, Markdown And YAML Questions.
- Impact: No unresolved impact.

#### GS-39

- Status: N/A
- Question: Does the YAML avoid generic type fields unless the task explicitly called for that style?
- Evidence type: not applicable
- Evidence source: FR-001 format
- Evidence: No YAML artifact is in scope.
- Assessment: The question does not apply.
- Correction: None.
- Authority: `review-checklist-structured.md`, Markdown And YAML Questions.
- Impact: No unresolved impact.

## Completed Functional-Specification Checklist

### Skill Workflow

#### FS-01

- Status: PASS
- Question: Does the review identify the actor, workflow, surfaces, states, and verification claims before assessment?
- Evidence type: summary
- Evidence source: this review, Review Scope
- Evidence: The review names the seven actors, eight workflows, five surface groups, report and operation states, and ten verification blocks before scoring.
- Assessment: Required contract elements were inventoried first.

#### FS-02

- Status: PASS
- Question: Does the completed review checklist name this checklist as review-checklist-functional-spec.md?
- Evidence type: exact quotation
- Evidence source: this review, Review Scope
- Evidence: “Artifact checklist: `review-checklist-functional-spec.md`”
- Assessment: The artifact checklist is named.

#### FS-03

- Status: N/A
- Question: Does the completed review checklist save next to the artifact using artifact-name.review-checklist-functional-spec.md?
- Evidence type: not applicable
- Evidence source: dispatch directive
- Evidence: The dispatch explicitly requires this approved `docs/reviews/RVW-009-...-checklist.md` path as the only review evidence file.
- Assessment: The request-specific approved review location overrides the skill's default adjacent filename.

#### FS-04

- Status: PASS
- Question: Does the review use verify-documentation-page with the artifact, source evidence, and completed review checklist?
- Evidence type: summary
- Evidence source: this review, Shared Page Verifier Assessment
- Evidence: The shared assessment checks page contract, source authority, links, diagrams, steady-state structure, and consistency against the completed checklist.
- Assessment: Shared verification is integrated.

#### FS-05

- Status: PASS
- Question: Does the final assessment derive findings or pass status from the completed review checklist rather than memory?
- Evidence type: summary
- Evidence source: this review, Findings And Corrections
- Evidence: The resolved findings cite GS-10, GS-12, GS-17, GS-23, FS-09, FS-24, FS-28, FS-30, FS-34, FS-35, FS-38, FS-41, and FS-43. Their current PASS status derives from the reviewed source hashes; memory supplied only historical context and was not used as acceptance evidence.
- Assessment: The final verdict derives from current source and checklist evidence.

#### FS-06

- Status: PASS
- Question: Does the output lead with findings ordered by severity when problems exist?
- Evidence type: summary
- Evidence source: this review, Findings And Corrections
- Evidence: Findings appear before the verdict and checklists, grouped as high, medium, and low impact.
- Assessment: The required output order is satisfied.

### Shared Contract

#### FS-07

- Status: PASS
- Question: Does the artifact start with Current Understanding, Authoritative Sources, Related Code, Related Tests, Related Backlog Items, Related Wiki Pages, Open Questions, and Maintenance Notes?
- Evidence type: summary
- Evidence source: FR-001, opening section sequence
- Evidence: All eight required sections occur before Parent Workflow.
- Assessment: The shared opening contract is complete.

#### FS-08

- Status: PASS
- Question: Does Current Understanding describe the behavior as it should be understood now?
- Evidence type: exact quotation
- Evidence source: FR-001, Current Understanding
- Evidence: “The product is partially implemented. The current CLI, MCP server, desktop run index, static report views, telemetry, and export formats remain supported.”
- Assessment: The section states current and intended behavior without presenting the whole design as implemented.

#### FS-09

- Status: PASS
- Question: Do Authoritative Sources distinguish implemented behavior from intended behavior?
- Evidence type: exact quotation
- Evidence source: FR-001, Authoritative Sources
- Evidence: “Current code and tests govern claims about implemented behavior.”
- Assessment: Source precedence separates implementation evidence from intended functional and design authority.

#### FS-10

- Status: PASS
- Question: Do Related Code and Related Tests identify evidence or say Not yet identified after a real search?
- Evidence type: summary
- Evidence source: FR-001, Related Code and Related Tests
- Evidence: Both sections contain repository-relative trees. Planned dynamic tests are explicitly “not yet identified as files.” Current source and test files exist in the repository.
- Assessment: Evidence and gaps are explicit.

#### FS-11

- Status: PASS
- Question: Do Open Questions capture behavior, ownership, or acceptance conflicts that cannot be resolved from sources?
- Evidence type: summary
- Evidence source: FR-001, Open Questions
- Evidence: Four questions state a recommendation, impact, and decision owner. MCP retention is explicitly excluded from open status.
- Assessment: Unresolved product choices are bounded and owned.

#### FS-12

- Status: PASS
- Question: When evaluating Documentation Acceptance and Implementation Readiness, do you skip any leading retained explanatory note or notes, then require the first authored decisions to begin with ACCEPTED or BLOCKED and READY or BLOCKED, respectively, before any later explanatory prose, while Documentation Acceptance judges source evidence, accepted design prerequisites, and current reverse-engineering pass requirements without requiring intentionally absent later wiki pages?
- Evidence type: exact quotation
- Evidence source: FR-001, Documentation Acceptance and Implementation Readiness
- Evidence: “**ACCEPTED.** This specification reconciles current source evidence with the accepted Dev Architect decision packet.” and “**BLOCKED.** Product implementation must wait for user review and acceptance of the four decisions in Open Questions.”
- Assessment: Both first authored decisions use an allowed leading token and state the correct basis.

#### FS-13

- Status: PASS
- Question: Is documentation acceptance separate from implementation readiness, allowing accurate documentation of known defects, unimplemented behavior, open design decisions, and current limitations while Implementation Readiness is BLOCKED for affected downstream work?
- Evidence type: summary
- Evidence source: FR-001, Documentation Acceptance, Implementation Readiness, Operation Inventory, and Verification
- Evidence: The document accepts its source reconciliation while separately blocking implementation. Intended and planned items remain labeled.
- Assessment: The two judgments are separate and meaningful.

### Artifact-Specific Contract

#### FS-14

- Status: PASS
- Question: Does User Or Actor Goal name the actor and the outcome they need?
- Evidence type: summary
- Evidence source: FR-001, Current Understanding, Parent Workflow, and Actors
- Evidence: The local operator needs to find recorded runs, inspect execution evidence, understand large coordination runs, and export a privacy-bounded report. Other actors have explicit goals and permissions.
- Assessment: Although the section title is Actors rather than User Or Actor Goal, the required actor-goal contract is explicit.

#### FS-15

- Status: PASS
- Question: Does the specification prevent chaos in architecture and design by giving downstream authors one coherent actor-visible contract for actors, operations, entry points, inputs, permissions, validation, states, ordering, visible results, errors, recovery, persistence outcomes, and acceptance scenarios?
- Evidence type: summary
- Evidence source: FR-001, Actors through Verification
- Evidence: The artifact defines actors, an operation inventory, eight workflows, interface examples, states and rules, edge cases, acceptance status, and ten scenarios with steps and assertions. Its authority chain distinguishes FR-001 actor-visible behavior, ARC-001 system architecture, and HLD-003 subsystem design.
- Assessment: The current contract is coherent and complete for documentation acceptance.

#### FS-16

- Status: PASS
- Question: Are details not established by authoritative inputs classified as justified functional propositions or open questions rather than presented as accepted requirements?
- Evidence type: summary
- Evidence source: FR-001, Current Understanding, Open Questions, Operation Inventory, Export Rules, and Verification
- Evidence: Behavior is labeled Implemented, worktree, Intended, Planned, or proposed. Four unresolved decisions remain open with recommendations and owners.
- Assessment: The artifact does not silently promote unknown implementation behavior.

#### FS-17

- Status: PASS
- Question: Does each justified functional proposition explain its supporting constraints or reasoning, why it is necessary to complete the workflow or unblock downstream design, and the role that owns or may revise it?
- Evidence type: summary
- Evidence source: FR-001, Open Questions
- Evidence: Each recommendation has an impact and decision owner. Current Understanding and Scope provide the compatibility, scale, and trust constraints that support intended behavior.
- Assessment: Propositions are sufficiently justified and owned.

#### FS-18

- Status: PASS
- Question: Before leaving a resolvable actor-visible detail open, does the specification make a reasonable effort to propose practical behavior?
- Evidence type: summary
- Evidence source: FR-001, Open Questions
- Evidence: Every open question includes a concrete recommendation, including migration timing, a 5 GiB cache proposal, Codex-first dynamic scope, and transport-neutral future adaptation.
- Assessment: The specification proposes behavior before deferring authority.

#### FS-19

- Status: PASS
- Question: Are exact actor-visible contracts free of `...`, Unicode ellipsis, wildcards, `TBD`, catch-all wording, unnamed variants, and omitted intermediate states?
- Evidence type: assessment
- Evidence source: lexical and workflow review of FR-001
- Evidence: No `TBD`, ellipsis marker, wildcard placeholder, or unnamed workflow variant was found in actor-visible contracts.
- Assessment: Exact contracts avoid shorthand omissions.

#### FS-20

- Status: PASS
- Question: Do Parent Workflow And Entry Points identify where the workflow starts and how users reach it?
- Evidence type: exact quotation
- Evidence source: FR-001, Entry Points
- Evidence: “The Tauri dynamic workspace is the intended primary entry point for Codex analysis. CLI and MCP remain first-class entry points. Static files remain the portable reading entry point.”
- Assessment: Parent context and entry paths are explicit.

#### FS-21

- Status: PASS
- Question: Does Route Or Surface List cover relevant routes, screens, commands, APIs, notifications, or external surfaces?
- Evidence type: summary
- Evidence source: FR-001, Operation Inventory
- Evidence: The inventory covers desktop catalog and workspace actions, CLI modes and adapters, retained and intended MCP operations, worker messages, title lookup, source links, report windows, and diagnostics.
- Assessment: Relevant surfaces are inventoried.

#### FS-22

- Status: PASS
- Question: When Related Code or another placement section names three or more repository paths that share a prefix, or paths spanning two or more folders, does it present their placement in one or more fenced text trees with complete repository-relative root and package segments?
- Evidence type: summary
- Evidence source: FR-001, Related Code and Related Tests
- Evidence: Desktop, report runtime, Rust discovery, and test paths are presented in fenced repository-relative text trees.
- Assessment: Path placement is clear and complete.

#### FS-23

- Status: PASS
- Question: When a path tree would become large or separate workflow surfaces need different metadata, is it split into named component or ownership subsections with one small fenced text tree and adjacent metadata in each, without multiline table cells, simulated HTML breaks, repeated common-prefix lists, or one row per full path?
- Evidence type: summary
- Evidence source: FR-001, Related Code
- Evidence: Separate Desktop And Native Host, Report Runtime CLI And MCP, and Native Discovery subsections contain bounded trees with adjacent ownership prose.
- Assessment: Trees are split by coherent ownership and avoid prohibited formatting.

#### FS-24

- Status: PASS
- Question: Does a primary and supporting operation inventory cover every route, API, command, event, job, notification, and supporting reference-data lookup directly invoked by the workflow, with actor and authentication source; authorization, ownership, tenancy, and data filtering; selector, request, paging, and sort; response projection, disclosure, status, and error; state or side effects; and verification?
- Evidence type: summary
- Evidence source: FR-001, Operation Inventory, States And Rules, and Interface Examples
- Evidence: The inventory covers known desktop, CLI, MCP, worker-message, lookup, navigation, and diagnostic operations. Actor authority is established globally and per row. Selectors, limits, results, side effects, verification, tenancy exclusions, data filtering, disclosure, status, and error behavior are supplied by the inventory plus the adjacent global rules.
- Assessment: The operation inventory is complete, and FS-28, FS-41, and FS-43 confirm complete mapped interface evidence.

#### FS-25

- Status: PASS
- Question: Do Scope And Non-Goals distinguish included behavior from excluded or deferred behavior?
- Evidence type: summary
- Evidence source: FR-001, Scope
- Evidence: Included behavior is listed separately from remote hosting, multi-user access, source editing, network ingestion, watching, module internals, and future non-Codex dynamic adapters.
- Assessment: Scope boundaries are explicit.

#### FS-26

- Status: PASS
- Question: Do Concepts define terms the actor must understand without drifting into module design?
- Evidence type: summary
- Evidence source: FR-001, Concepts
- Evidence: Concepts defines actor-visible scope, snapshot, cache, evidence, and export terms. It does not prescribe module names or internal class structure.
- Assessment: The definitions support the workflow at the right level.

#### FS-27

- Status: PASS
- Question: Are Workflow Steps written from the actor's point of view and do they cover main, alternate, empty, error, and recovery paths?
- Evidence type: summary
- Evidence source: FR-001, Workflows and Edge Cases
- Evidence: Workflows start with operator, caller, client, or reader actions. Alternate scope, empty search, validation, cancellation, failure, conflict, omission, and recovery behavior are included.
- Assessment: Actor-visible paths are comprehensive.

#### FS-28

- Status: PASS
- Question: Does Interface Examples classify every documented interface as UI, API, event or message, CLI, or another non-interactive surface and select proportionate examples from the documented interface type and behavior?
- Evidence type: summary
- Evidence source: FR-001, Interface Examples and Operation Inventory
- Evidence: The section classifies and illustrates UI, CLI, MCP, worker message, and static-directory surfaces. The CLI operation map and Examples A through F cover every documented CLI mode with proportionate success and failure evidence.
- Assessment: Interface types and representative examples are complete.

#### FS-29

- Status: PASS
- Question: When UI behavior depends on spatial placement, ordering, grouping, relative prominence, two or more view states that must be compared, an overlay or simultaneous region, responsive or conditional layout, or direct manipulation such as drag, drop, drawing, or spatial selection, does it provide a proportionate mockup, wireframe, or interaction diagram and identify its layout, state-transition, or interaction contract role?
- Evidence type: summary
- Evidence source: FR-001, UI Layout Contract and Workflow Diagram
- Evidence: The UI wireframe defines grouping, relative prominence, simultaneous preflight and workspace regions, the preflight-to-workspace transition, and narrow-window navigation behavior. The static-directory tree defines exported spatial grouping. Heatmap and sequence rules preserve direct-manipulation semantics.
- Assessment: Spatial and interaction-dependent UI behavior has proportionate visual evidence. CLI and static-reading workflow diagrams now complete the adjacent workflow evidence.

#### FS-30

- Status: PASS
- Question: Does every workflow with two or more ordered actor actions, or any branch, permission gate, alternate path, recovery path, state transition, or external handoff, include an appropriate Mermaid sequence, state, or flow diagram instead of leaving the complete workflow only in prose, a numbered list, or a table?
- Evidence type: summary
- Evidence source: FR-001, Workflows and Workflow Diagram
- Evidence: Eight Mermaid blocks cover worker messaging, discovery and snapshot, dynamic inspection, refresh and recovery, export, MCP, CLI use, and static report reading. The CLI sequence covers validation and terminal branches. The static-reading flowchart covers entry selection, navigation, omission, and recovery.
- Assessment: Every qualifying workflow has a proportionate Mermaid diagram.

#### FS-31

- Status: PASS
- Question: Does each workflow diagram use a sequence diagram for ordered actor-system exchanges, a state diagram for named states and transitions, or a flowchart for branches, decisions, or recovery paths, while treating verification-step lists as test procedures rather than workflow-diagram triggers?
- Evidence type: summary
- Evidence source: FR-001, Worker Message And Producer-Consumer Sequence and Workflow Diagram
- Evidence: Worker and MCP exchanges use sequence diagrams, refresh uses a state diagram, and discovery, inspection, and export branches use flowcharts. Verification steps are outside workflow diagrams.
- Assessment: Existing diagrams use appropriate forms.

#### FS-32

- Status: PASS
- Question: Do States, Rules, Permissions, And Edge Cases identify status values, permission gates, validation rules, limits, and failure behavior?
- Evidence type: summary
- Evidence source: FR-001, Actors, States And Rules, and Edge Cases
- Evidence: The specification defines twelve report states, authority constraints, scope gates, page and bucket limits, path and privacy rules, structured errors, and recovery outcomes.
- Assessment: State and rule coverage is strong.

#### FS-33

- Status: PASS
- Question: Do Verification blocks name test type, test files, scenario, steps, assertions, and current status?
- Evidence type: summary
- Evidence source: FR-001, Verification Blocks FR-01 through FR-10
- Evidence: Each block contains Type, Test files, Status, Scenario, Steps, and Assertions. Planned files are explicitly unidentified.
- Assessment: Verification-block structure is complete.

#### FS-34

- Status: PASS
- Question: Do Related Documents link architecture, high-level design, module design, tests, and wiki pages that support the workflow?
- Evidence type: summary
- Evidence source: FR-001, Authoritative Sources, Related Tests, Related Backlog Items, Related Wiki Pages, and Open Questions
- Evidence: FR-001 links ARC-001, HLD-003, CD-001, README, pricing data, source, tests, and backlog. It explicitly says that no project wiki page or later module design is yet identified.
- Assessment: Existing related evidence is linked and intentional absences are disclosed.

#### FS-35

- Status: PASS
- Question: Does technical implementation detail stay in related technical documents unless users need it to understand behavior?
- Evidence type: assessment
- Evidence source: FR-001, ARC-001, and HLD-003
- Evidence: FR-001 uses protocol, cache, publication, and intended module-path details only where they make ownership, latency, privacy, cancellation, offline use, or recovery observable. ARC-001 owns system-wide boundaries. The four intended module paths are explicitly established by HLD-003. Lower-level classes, functions, DTO fields, table names, migration statements, cursor encoding, and UI-test internals remain deferred.
- Assessment: Included technical detail supports actor-visible behavior and preserves the architecture-to-HLD authority boundary.

#### FS-36

- Status: PASS
- Question: When named scenarios are used, do they cover every material actor, entry point, state, permission, main path, alternate path, and recovery path?
- Evidence type: summary
- Evidence source: FR-001, Verification
- Evidence: FR-01 through FR-10 cover catalog, scope, views, refresh, cancellation, exports, CLI, MCP, privacy, cache, interaction, accessibility, and recovery.
- Assessment: Scenario coverage is comprehensive, with future work correctly planned.

#### FS-37

- Status: PASS
- Question: Are scenario prose, workflow diagrams, state tables, and machine-readable contracts consistent with each other?
- Evidence type: assessment
- Evidence source: FR-001, Workflows, Interface Examples, Workflow Diagram, States And Rules, Edge Cases, and Verification
- Evidence: Snapshot IDs, revisions, root-only scope, pagination, refresh, cancellation, export, and structured error semantics agree across representations.
- Assessment: No contradiction or residual diagram gap was found.

#### FS-38

- Status: PASS
- Question: Does the artifact name the project-owned approval or acceptance authority when one exists, without inventing a universal gate?
- Evidence type: summary
- Evidence source: FR-001, Authoritative Sources, Open Questions, and Implementation Readiness
- Evidence: FR-001 governs actor-visible behavior, ARC-001 governs the system-wide frame, and HLD-003 governs subsystem ownership and operation allocation. Product owner and Product owner with Dev Architect review own the four remaining decisions. User review and acceptance block implementation.
- Assessment: Authority is specific and scoped.

## Additional Interface-Example Checks

#### FS-39

- Status: N/A
- Question: Does each documented API behavior provide one coherent example containing the method, path, query parameters, headers, authentication, and request body together with the response status, headers, and body, plus representative validation, authentication, and conflict cases?
- Evidence type: not applicable
- Evidence source: FR-001, Scope and Interface Examples
- Evidence: FR-001 defines no HTTP API. MCP is explicitly a stdio tool surface, and the architecture excludes a local HTTP server.
- Assessment: HTTP method, path, header, and response-header requirements do not apply.

#### FS-40

- Status: PASS
- Question: Does each documented event or message behavior provide a representative payload and a producer-consumer sequence that makes direction, ordering, acknowledgement, and failure behavior observable when applicable?
- Evidence type: summary
- Evidence source: FR-001, Worker Message And Producer-Consumer Sequence
- Evidence: JSON Lines request, progress, result, and cancel payloads accompany a Mermaid producer-consumer sequence with completion, acknowledgement, and forced-termination branches.
- Assessment: Worker message behavior has proportionate evidence.

#### FS-41

- Status: PASS
- Question: Does each documented CLI behavior provide a representative invocation, output, and failure, including relevant arguments, options, exit status, and diagnostic output?
- Evidence type: summary
- Evidence source: FR-001, CLI Success And Failure and Operation Inventory
- Evidence: The initial and A-through-F examples include invocations, outputs, diagnostics, and exit statuses for Codex thread and path selection, Codex and Junie catalogs, native Junie, methodology, prompt-runner, comparison, and sealed Codex reproduction.
- Assessment: Every documented CLI behavior has representative success and failure evidence.

#### FS-42

- Status: N/A
- Question: Is a concrete no-example rationale used only when no required interface example applies, with the interface and behavior, why an additional example would add no contract information, and the exact prose, table, or verification block that already makes observable behavior unambiguous?
- Evidence type: not applicable
- Evidence source: FR-001, Interface Examples
- Evidence: The artifact does not claim a general no-example rationale. It supplies mapped examples for all documented interfaces and uses a concrete shared-failure explanation for three CLI adapters whose distinct inputs are preserved.
- Assessment: No unsupported no-example rationale requires validation.

#### FS-43

- Status: PASS
- Question: When one example covers multiple operations, does the specification map every operation to it while preserving distinct inputs, outcomes, and failures?
- Evidence type: summary
- Evidence source: FR-001, CLI Success And Failure and Operation Inventory
- Evidence: `CLI Operation-To-Example Map` maps all nine documented CLI operation families to the preceding evidence or Examples A through F. Example E preserves the distinct inputs and states why the three adapters share one failure contract.
- Assessment: The mapping is complete and preserves material distinctions.

## Shared Page Verifier Assessment

### Page Contract

- Status: PASS
- Evidence: FR-001 has a single H1, logical H2 and H3 hierarchy, the required shared opening sections, actor-visible sections, acceptance and readiness decisions, and verification blocks. No unresolved `TODO`, `TBD`, placeholder ellipsis, or malformed fence was found.
- Assessment: The maintained Markdown page has a coherent page contract.

### Source Authority And Cross-Document Consistency

- Status: PASS
- Evidence: FR-001 distinguishes accepted intended behavior from current source and test evidence. ARC-001 owns the system frame, requires independently runnable CLI and MCP entry points, and preserves current MCP tools. HLD-003 owns the subsystem components and exact operation allocation while keeping MCP process-local and independent of Tauri. Current `mcp_server.py` registers `generate_report`, `query_time_range`, and `get_event_details` over FastMCP stdio. The README documents those same tools and current static backends.
- Assessment: The authority hierarchy and principal source claims are consistent. Intended behavior is labeled, and MCP remains first-class, independent, and current-operation compatible.

### Links And Paths

- Status: QUESTION
- Evidence: The configured `verify_markdown_links` operation rejected `/Users/martinbechard/dev/agent-runner` as outside its workspace roots. The review did not use a fallback after this structured authorization rejection. FR-001, ARC-001, HLD-003, and the source files used for substantive review were readable, and the fenced Related Code and Related Tests trees remain repository-relative.
- Assessment: No malformed path tree was found, but a fresh exhaustive local-link result is unavailable. This is a verifier-capability gap, not evidence of a broken target link.

### Diagrams

- Status: PASS
- Evidence: Eight Mermaid blocks are present and use appropriate flowchart, state, and sequence forms. The added CLI sequence and static-reading flowchart cover the formerly missing qualifying workflows.
- Assessment: Diagram coverage is complete, useful, editable, and consistent with the workflow prose.

### Steady-State And STE Review

- Status: PASS
- Evidence: The artifact is framed around current understanding rather than change history. It separates implemented, worktree, intended, and planned behavior. Enumerations are exposed through tables and lists. Technical terms are defined, and no semantic or material clarity defect was found.
- Assessment: The prose follows applicable Simplified Technical English principles without changing source meaning. This is not a claim of formal ASD-STE100 compliance.

### Verifier Verdict

**VERIFY DOCUMENTATION PAGE: PASS WITH A NON-BLOCKING VERIFICATION GAP.** Source authority, section structure, diagram coverage, interface evidence, steady-state framing, and cross-document consistency pass. Exhaustive local-link validation is inconclusive because the configured verifier rejected the repository root before checking links.
