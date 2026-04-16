# PH-000 Related Files

Temporary working list of the active files directly related to `PH-000-requirements-inventory`.

## Specs

- [CD-009-ph000-requirements-inventory-design.md](/Users/martinbechard/dev/agent-runner/docs/design/components/CD-009-ph000-requirements-inventory-design.md): component design authority for the PH-000 workflow and artifact contract.
- [M-002-phase-definitions.yaml](/Users/martinbechard/dev/agent-runner/docs/methodology/M-002-phase-definitions.yaml): methodology phase registry including `PH-000-requirements-inventory`.
- [M-003-agent-role-specifications.md](/Users/martinbechard/dev/agent-runner/docs/methodology/M-003-agent-role-specifications.md): generator, judge, and selector role specifications used by PH-000 runs.
- [M-006-orchestration.md](/Users/martinbechard/dev/agent-runner/docs/methodology/M-006-orchestration.md): orchestration rules for how PH-000 runs inside the methodology pipeline.
- [skills-baselines.yaml](/Users/martinbechard/dev/agent-runner/docs/methodology/skills-baselines.yaml): baseline PH-000 generator and judge skill assignments.

## Prompt Files

- [PR-025-ph000-requirements-inventory.md](/Users/martinbechard/dev/agent-runner/docs/prompts/PR-025-ph000-requirements-inventory.md): hand-authored PH-000 prompt-runner input spec.

## Skill Files

- [ph000-requirements-extraction/SKILL.md](/Users/martinbechard/dev/agent-runner/plugins/methodology-runner-skills/skills/ph000-requirements-extraction/SKILL.md): PH-000 generator extraction and decomposition discipline.
- [ph000-requirements-quality-review/SKILL.md](/Users/martinbechard/dev/agent-runner/plugins/methodology-runner-skills/skills/ph000-requirements-quality-review/SKILL.md): PH-000 judge semantic review discipline.
- [traceability-discipline/SKILL.md](/Users/martinbechard/dev/agent-runner/plugins/methodology-runner-skills/skills/traceability-discipline/SKILL.md): shared traceability and quote-fidelity discipline used by PH-000.

## Runtime / Implementation Files

- [phases.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phases.py): code-level PH-000 contract and output path.
- [orchestrator.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/orchestrator.py): phase execution flow that runs PH-000.
- [skill_selector.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/skill_selector.py): selects PH-000 skills and builds prelude inputs.
- [prompt_generator.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/prompt_generator.py): generates the PH-000 prompt-runner input file.
- [prelude.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/prelude.py): renders generator and judge skill preludes used by PH-000.
- [phase_0_validation.py](/Users/martinbechard/dev/agent-runner/src/cli/methodology_runner/phase_0_validation.py): PH-000 validation support code.
- [phase-0-deterministic-validation.py](/Users/martinbechard/dev/agent-runner/scripts/phase-0-deterministic-validation.py): deterministic validator for PH-000 output structure and fidelity checks.

## Test Files

- [test_baseline_config.py](/Users/martinbechard/dev/agent-runner/tests/cli/methodology_runner/test_baseline_config.py): PH-000 baseline skill config coverage.
- [test_models_skills.py](/Users/martinbechard/dev/agent-runner/tests/cli/methodology_runner/test_models_skills.py): PH-000 skill model parsing coverage.
- [test_cross_ref_retry_skills.py](/Users/martinbechard/dev/agent-runner/tests/cli/methodology_runner/test_cross_ref_retry_skills.py): PH-000 skill manifest retry-path coverage.
- [test_smoke_skill_driven.py](/Users/martinbechard/dev/agent-runner/tests/cli/methodology_runner/test_smoke_skill_driven.py): end-to-end PH-000 skill-driven smoke coverage.
- [test_orchestrator_skills.py](/Users/martinbechard/dev/agent-runner/tests/cli/methodology_runner/test_orchestrator_skills.py): PH-000 selector/prelude orchestration coverage.
- [test_prompt_generator.py](/Users/martinbechard/dev/agent-runner/tests/cli/methodology_runner/test_prompt_generator.py): PH-000 prompt generation and deterministic-template coverage.
- [test_prelude.py](/Users/martinbechard/dev/agent-runner/tests/cli/methodology_runner/test_prelude.py): PH-000 skill prelude rendering coverage.
