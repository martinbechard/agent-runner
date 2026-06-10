# Revised Methodology Flow Plan

**GOAL: REVISED-METHODOLOGY-FLOW** Separate unit TDD, support artifacts, simulations, and integration.
- **SYNOPSIS:** Revise the methodology so code units are developed through generated TDD prompt files, non-code artifacts are produced through separate artifact workflows, and integration grows incrementally using existing units plus simulations for missing units.
- **BECAUSE:** A single PH-006 implementation workflow is too coarse for complex systems and lets generators blur test creation, implementation, documentation, support scripts, and integration evidence.

**PHASE: PH-002 Architecture**
- **SYNOPSIS:** Identify conceptual system components and interactions.
- **PRODUCES:** `docs/architecture/architecture-design.yaml`
- **RULE:** Architecture remains conceptual: components, responsibilities, interaction examples, runtime boundaries, and simulation targets.
- **RULE:** Architecture does not enumerate every source, test, or documentation file.
- **BECAUSE:** Architecture should explain system shape, not implementation packaging.

**PHASE: PH-003 Solution Design**
- **SYNOPSIS:** Define implementation units, files, functionality per unit, UI surfaces, processing examples, and non-code artifacts.
- **PRODUCES:** `docs/design/solution-design.yaml`
- **CONTAINS:** `implementation_units`, `unit_functionalities`, `implementation_files`, `non_code_artifacts`, `integration_scenarios`, and `ui_surfaces`.
- **RULE:** Each code unit must list its owned files, public functions, classes, endpoints, dependencies, and functional behaviors.
- **RULE:** Each processing function must include input and output examples.
- **RULE:** Each UI surface must include an HTML mockup.
- **BECAUSE:** Later phases need explicit units and behaviors to generate repeatable TDD scaffolding.

**PHASE: PH-004 Interface Contracts**
- **SYNOPSIS:** Define language, API, and service interfaces between units.
- **PRODUCES:** `docs/design/interface-contracts.yaml`
- **RULE:** Any unit consumed by another unit before implementation must have an explicit interface.
- **BECAUSE:** Simulations and integration tests need compile-time or contract-level boundaries.

**PHASE: PH-005 Simulations**
- **SYNOPSIS:** Create simulations only for system components or units that are needed by other units before their real implementation exists.
- **PRODUCES:** `docs/simulations/simulation-definitions.yaml`
- **RULE:** Simulations implement explicit interfaces and document usage.
- **RULE:** Do not simulate test suites, README files, or support docs.
- **BECAUSE:** Simulations support partial integration, not artificial test pass/fail behavior.

**PHASE: PH-006A Functional Test Planning**
- **SYNOPSIS:** Produce structured functional test contracts for code units.
- **PRODUCES:** `docs/implementation/functional-test-contracts.yaml`
- **CONTAINS:** One `FTST-*` item per functional behavior.
- **FIELDS:** `id`, `unit_ref`, `component_ref`, `feature_refs`, `acceptance_criteria_refs`, `test_file`, `test_command`, `implementation_files`, `inputs`, `expected_outputs`, `valid_red_failures`, and `green_success_criteria`.
- **RULE:** Functional tests are for code behavior only.
- **BECAUSE:** TDD prompt generation should be driven by structured behavior contracts, not improvised by one broad implementation prompt.

**PHASE: PH-006B Support Artifact Planning**
- **SYNOPSIS:** Produce a separate plan for non-code artifacts.
- **PRODUCES:** `docs/implementation/support-artifact-plan.yaml`
- **CONTAINS:** README, docs, `.gitignore`, scripts, config, runbooks, packaging files, and other support artifacts.
- **RULE:** Each artifact gets an artifact-appropriate verification mode: content check, executable support check, schema check, lint check, or manual review note.
- **BECAUSE:** Non-code artifacts are important but should not be forced into TDD.

**PHASE: PH-006C Unit TDD Workflow Generation**
- **SYNOPSIS:** Generate one prompt-runner workflow per implementation unit.
- **PRODUCES:** `docs/implementation/units/{unit_id}-tdd-workflow.md`
- **PROMPT SHAPE PER FUNCTIONAL TEST:**
  - Red prompt: create or tighten only the test file, run the exact command, require an allowed failure.
  - Green prompt: edit implementation files only, rerun the exact command, require a pass.
  - Optional refactor prompt: keep tests green before and after.
- **RULE:** The red prompt must not edit implementation files.
- **RULE:** The green prompt must not rewrite the test unless the red prompt itself was invalid.
- **BECAUSE:** This enforces real TDD sequencing.

**PHASE: PH-006D Support Artifact Workflow Generation**
- **SYNOPSIS:** Generate prompt-runner workflows for non-code artifacts.
- **PRODUCES:** `docs/implementation/support/support-artifacts-workflow.md`
- **PROMPT TYPES:** README content check, `.gitignore` required-pattern check, verification script executable check, and config/schema check.
- **BECAUSE:** Support artifacts need focused verification, not behavior TDD.

**PHASE: PH-006E Incremental Integration Planning**
- **SYNOPSIS:** Define open-ended integration scenarios across implemented units, existing units, and simulations.
- **PRODUCES:** `docs/implementation/integration-plan.yaml`
- **CONTAINS:** `INT-*` scenarios with units under test, real dependencies, simulated dependencies, commands, expected behavior, and retirement rules for simulations.
- **RULE:** Integration tests can be broader and less mechanically red/green than unit TDD.
- **BECAUSE:** Integration is about proving collaboration boundaries, not only isolated behavior.

**PHASE: PH-006F Execution**
- **SYNOPSIS:** Execute generated workflows in dependency order.
- **ORDER:** Unit TDD workflows for dependency units, unit TDD workflows for consumers, consumer workflows using simulations where dependencies are not built, support artifact workflow, integration workflow, and final verification.
- **PRODUCES:** `docs/implementation/implementation-run-report.yaml`
- **BECAUSE:** The run report should show which unit tests passed, which simulations were used, which integrations passed, and which simulations remain.

## Example: Hello World

**PH-003 Units**
- `UNIT-001`: Hello World CLI.
- Files: `src/hello_world.py`.
- Functionality: emit `Hello, world!` and exit 0.

**PH-006A Functional Tests**
- `FTST-001`: command `pytest tests/test_hello_world.py`, execution `python3 src/hello_world.py`, expected stdout `Hello, world!`, exit 0.

**PH-006B Support Artifacts**
- `README.md`: setup, run, and test instructions.
- `verification/run_verification.sh`: runs `pytest tests/test_hello_world.py`.
- `.gitignore`: Python caches and local environments.

**Generated Prompt Files**
- `docs/implementation/units/UNIT-001-tdd-workflow.md`
  - Prompt 1: create failing CLI output test only.
  - Prompt 2: implement CLI to pass test.
- `docs/implementation/support/support-artifacts-workflow.md`
  - Prompt 1: README steady-state content check.
  - Prompt 2: verification script executable check.
  - Prompt 3: `.gitignore` pattern check.
- `docs/implementation/integration-workflow.md`
  - Prompt 1: run CLI and verification script as final integration.

## Example: Methodology Runner Report Web App

**PH-002 Components**
- `CMP-001`: Report Web Frontend.
- `CMP-002`: Report Server API.
- `CMP-003`: Methodology Run Report Parser.
- `CMP-004`: Report Data Store or file-backed report source.

**PH-003 Units**
- `UNIT-001`: Report parser library.
  - Files: `server/report_parser.py` or equivalent.
  - Functions: parse run timeline, summarize phases, extract variants and drilldowns.
- `UNIT-002`: Report API server.
  - Files: `server/app.py`, `server/routes/reports.py`.
  - Endpoints: list runs, get run summary, get phase drilldown.
- `UNIT-003`: Frontend report dashboard.
  - Files: `web/src/App.tsx`, `web/src/report-dashboard.tsx`.
  - UI: report list, phase summary, drilldown panel, variant details.
- `UNIT-004`: Frontend API client.
  - Files: `web/src/api/reports.ts`.
  - Functions: fetch reports and fetch report detail.

**PH-005 Simulations**
- Parser fake for API server tests if the parser is not yet implemented.
- API mock for frontend tests if the server is not yet implemented.
- File-source fake for parser/server integration.

**PH-006A Functional Tests**
- `FTST-001`: parser converts raw methodology-runner execution files into a report summary.
- `FTST-002`: parser exposes drilldown records for phases, prompts, and variants.
- `FTST-003`: API returns report list JSON.
- `FTST-004`: API returns report detail JSON using the parser interface.
- `FTST-005`: frontend renders a run list from mocked API data.
- `FTST-006`: frontend drilldown interaction shows prompt and variant detail.

**Generated Unit Prompt Files**
- `docs/implementation/units/UNIT-001-parser-tdd-workflow.md`
- `docs/implementation/units/UNIT-002-api-server-tdd-workflow.md`
- `docs/implementation/units/UNIT-003-frontend-dashboard-tdd-workflow.md`
- `docs/implementation/units/UNIT-004-frontend-api-client-tdd-workflow.md`

**Generated Integration Prompt Files**
- `docs/implementation/integration/INT-001-parser-server-workflow.md`
  - Uses real parser plus server API.
- `docs/implementation/integration/INT-002-frontend-api-mock-workflow.md`
  - Uses frontend plus API simulation.
- `docs/implementation/integration/INT-003-frontend-server-end-to-end-workflow.md`
  - Uses real frontend and real server.
- `docs/implementation/integration/INT-004-report-drilldown-workflow.md`
  - Verifies drilldown and variants from a real report fixture.

**Support Artifact Prompt File**
- `docs/implementation/support/support-artifacts-workflow.md`
  - README setup/run/test instructions.
  - `.gitignore`.
  - Dev server scripts.
  - Sample report fixture documentation.
  - Operation notes for report source location.

## Key Rule

**RULE: PH-006 Workflow Factory**
- **SYNOPSIS:** PH-006 should no longer be one implementation workflow.
- **REPLACEMENT:** PH-006 becomes a workflow factory plus executor that produces functional test contracts, a support artifact plan, unit TDD workflows, a support artifact workflow, integration workflows, and a final verification report.
- **BECAUSE:** This gives the methodology deterministic red/green unit development while still supporting larger systems with partial integration and simulations.
