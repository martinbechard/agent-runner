### Module

verification-sweep

## Prompt 1: Produce Final Verification Report

### Required Files

docs/features/feature-specification.yaml
docs/requirements/requirements-inventory.yaml
docs/implementation/implementation-workflow.md
docs/implementation/implementation-run-report.yaml

### Deterministic Validation

python-module:methodology_runner.phase_7_validation
--feature-spec
docs/features/feature-specification.yaml
--requirements-inventory
docs/requirements/requirements-inventory.yaml
--implementation-workflow
docs/implementation/implementation-workflow.md
--implementation-run-report
docs/implementation/implementation-run-report.yaml
--verification-report
docs/verification/verification-report.yaml

### Generation Prompt

As a verification auditor, you must perform the final verification after the
child implementation workflow completed and write the result to
docs/verification/verification-report.yaml.

Context:
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>
<REQUIREMENTS_INVENTORY>
{{INCLUDE:docs/requirements/requirements-inventory.yaml}}
</REQUIREMENTS_INVENTORY>
<IMPLEMENTATION_WORKFLOW>
{{INCLUDE:docs/implementation/implementation-workflow.md}}
</IMPLEMENTATION_WORKFLOW>
<IMPLEMENTATION_RUN_REPORT>
{{INCLUDE:docs/implementation/implementation-run-report.yaml}}
</IMPLEMENTATION_RUN_REPORT>

Phase purpose:
- Confirm the child implementation workflow completed successfully.
- Verify the implemented workspace using real files and real verification
  commands, not hypothetical plans.
- Record per-requirement satisfaction with concrete evidence.
- Report any partial or unsatisfied requirements honestly.

Verification discipline:
- Use the implementation run report as the primary source for:
  - which files were changed
  - which test commands were already observed
  - whether the child run completed
- Inspect the changed files and rerun low-cost verification commands when
  needed to confirm real behavior.
- Do not fabricate evidence. Only claim a requirement is satisfied when the
  files and observed command behavior materially support that claim.
- If a requirement is only partially supported, mark it `partial` rather than
  forcing `satisfied`.
- Do not mark a requirement `satisfied` based only on subjective judgment,
  stylistic preference, or a vague sense that the implementation is "close
  enough".
- If a requirement contains qualitative language and the evidence only proves
  part of it, use `partial` or `unsatisfied` unless the evidence proves the
  underlying claim explicitly.
- If exact runtime output matters, preserve that exact observed output in the
  evidence notes rather than paraphrasing it.
- When an output is inherently runtime-volatile, such as a current date/time
  value or a test runner elapsed duration, record the semantically relevant
  behavior rather than binding requirement satisfaction to one exact literal
  unless the upstream approved artifacts explicitly require that literal.
- If you rerun a verification command in Phase 7 and the command output
  contains volatile values, do not claim that the rerun reproduces the exact
  transient literals seen in Phase 6. State the truthful current observation
  and summarize the stable behavior it proves.
- `verification_commands` and `requirement_results[*].evidence.commands` are
  for real workspace verification commands only. Do not include methodology-
  internal validator or self-check commands such as
  `python -m methodology_runner.phase_7_validation`.
- Downstream verification may use concrete implementation-aware checks, but do
  not mark behavior unsatisfied solely because of a more specific formatting
  preference unless the upstream approved artifacts require that detail or the
  missing detail changes the requirement's meaning. A compatible refinement is
  allowed; contradiction or unsupported exclusion is not.
- Verify delivered code quality where code files changed. Code should follow
  project-local best practices and include meaningful file-level, type-level,
  and function-level comments or docstrings for public surfaces and non-obvious
  behavior without adding comments that merely restate self-evident code.
- Verify delivered documentation quality where documentation files changed.
  Documentation should describe the steady-state software that exists now and
  should not rely on reader knowledge of an older or previous state unless the
  upstream request explicitly asks for migration notes, release notes, or
  historical change documentation.
- Verify README quality for application deliverables. A README for an
  application should include typical setup and operation entries such as
  prerequisites, installation or setup, configuration and environment
  variables when applicable, run or start commands, test or verification
  commands, and common operating notes.

Output schema to satisfy:
verification_commands:
  - command: "pytest -q"
    exit_code: 0
    purpose: "What this command verified"
    evidence: "Short observed result"
requirement_results:
  - inventory_ref: "RI-NNN"
    feature_refs: ["FT-NNN", "..."]
    status: "satisfied"
    evidence:
      files: ["relative/path", "..."]
      commands: ["command", "..."]
      notes: "Why this requirement is satisfied, partial, or unsatisfied"
coverage_summary:
  total_requirements: 0
  satisfied: 0
  partial: 0
  unsatisfied: 0
  satisfaction_percentage: 0.0

Acceptance requirements:
- The file must be valid YAML parseable by a standard YAML parser.
- The top-level keys must appear exactly in this order:
  verification_commands
  requirement_results
  coverage_summary
- Every RI-* from docs/requirements/requirements-inventory.yaml must appear in
  requirement_results.
- status must be one of:
  satisfied
  partial
  unsatisfied
- Every requirement_results entry must include:
  inventory_ref
  feature_refs
  status
  evidence
- evidence.files, evidence.commands, and evidence.notes must all be present.
- coverage_summary counts must match the actual requirement_results rows.
- When code, documentation, or README files are part of the delivered change,
  the report must not mark related requirements satisfied if those files fail
  the applicable delivery-quality expectations for comments, steady-state
  documentation, or application setup and operation guidance.
- Do not create any files other than docs/verification/verification-report.yaml.
- Write the full file contents to docs/verification/verification-report.yaml.

### Validation Prompt

Review the current final verification report against <FEATURE_SPECIFICATION>,
<REQUIREMENTS_INVENTORY>, <IMPLEMENTATION_WORKFLOW>, and
<IMPLEMENTATION_RUN_REPORT>.

Context:
<FEATURE_SPECIFICATION>
{{INCLUDE:docs/features/feature-specification.yaml}}
</FEATURE_SPECIFICATION>
<REQUIREMENTS_INVENTORY>
{{INCLUDE:docs/requirements/requirements-inventory.yaml}}
</REQUIREMENTS_INVENTORY>
<IMPLEMENTATION_WORKFLOW>
{{INCLUDE:docs/implementation/implementation-workflow.md}}
</IMPLEMENTATION_WORKFLOW>
<IMPLEMENTATION_RUN_REPORT>
{{INCLUDE:docs/implementation/implementation-run-report.yaml}}
</IMPLEMENTATION_RUN_REPORT>
<VERIFICATION_REPORT>
{{RUNTIME_INCLUDE:docs/verification/verification-report.yaml}}
</VERIFICATION_REPORT>

The deterministic validation result is already provided to you. Use it for
mechanical checks and do not re-run or duplicate those checks manually.

Your job is to decide whether the final verification report is truthful and
phase-ready.

Review method:
- Iterate through requirement_results in RI-* order.
- Then iterate through verification_commands in authored order.
- Then review coverage_summary against the actual requirement rows.
- Before flagging evidence or coverage as missing, check whether the same
  downstream-actionable verification meaning is already covered elsewhere in
  the report.
- Only flag it as missing if the allegedly missing content would change the
  truthfulness of the final verification outcome.

Focus your semantic review on these failure modes:

1. Phantom satisfaction:
   - Flag requirements marked satisfied without materially relevant file or
     command evidence.
2. Ignored child-run outcome:
   - Flag reports that treat a halted child workflow as successfully verified.
3. Thin evidence:
   - Flag rows whose evidence is too generic to justify the stated status.
4. Coverage overstatement:
   - Flag reports that force `satisfied` where the evidence supports only
     `partial` or `unsatisfied`.
5. Unsupported feature links:
   - Flag feature_refs that do not materially connect the requirement to the
     implementation evidence.
6. Subjective satisfaction:
   - Flag rows marked satisfied when the evidence is only qualitative,
     impressionistic, or inferred rather than directly supported by files or
     commands.
7. Evidence contradiction:
   - Flag rows whose evidence notes contradict the exact observed command
     outputs, test assertions, or implementation files.
8. Upstream semantic contradiction or unsupported exclusion:
   - Flag verification that either:
     - treats an upstream-required behavior as unsatisfied because of a
       downstream-only formatting/detail preference that the approved artifacts
       do not require
     - or broadens the claimed requirement so far that the report no longer
       verifies the actual approved behavior.
9. Volatile-literal overreach:
   - Flag reports that treat exact runtime-generated clock values, timestamp
     strings, or test-run durations as durable requirement evidence when the
     upstream artifacts do not require those exact literals.
10. Methodology self-validation leakage:
   - Flag reports that include methodology-internal validator/self-check
     commands in `verification_commands` or `requirement_results[*].evidence.commands`.
11. Delivery-quality omission:
   - Flag satisfied or partial implementation claims that ignore missing
     project-local code best practices, missing meaningful file-level,
     type-level, or function-level comments/docstrings in changed code,
     transitional documentation that depends on previous-state knowledge, or
     application README content that lacks setup and operation guidance.

Review instructions:
- Treat this phase as final verification of the real implemented workspace.
- Do not ask for speculative future tests if the current report can already
  state an honest partial or unsatisfied outcome.
- Do not request wording polish or alternate phrasing unless the current
  wording is misleading or materially consequential.
- If you find issues, cite exact RI-* / FT-* IDs and, when useful, the file
  paths or verification commands involved.
- When evaluating a `satisfied` row, ask explicitly:
  - does the cited evidence prove the requirement's actual meaning?
  - or is the row only inferring satisfaction from nearby implementation?
- For each material correction, include at least one corrective rule in this form:
  - RULE: the generator MUST / MUST NOT / SHOULD / SHOULD NOT make a specific change
    - BECAUSE: why that correction is necessary
- Use VERDICT: pass only if the report is truthful, complete, and materially
  supported by the implementation evidence.
- Use VERDICT: revise if the report can be corrected within this same file.
- Use VERDICT: escalate only if the child implementation run failed or the
  workspace does not contain enough real evidence to complete final
  verification.

End with exactly one of:
VERDICT: pass
VERDICT: revise
VERDICT: escalate
