# methodology-runner-skills

Baseline skill pack for the AI-driven development methodology. Provides
18 tech-agnostic skills covering all 8 phases of methodology-runner.

## Companion spec

[Skill-Driven Methodology Runner Design](../../docs/superpowers/specs/2026-04-09-skill-driven-methodology-runner-design.md)

## Discovery

methodology-runner discovers skills by walking
`<cwd>/plugins/*/skills/**/SKILL.md`. Run methodology-runner from the
repo root and these skills are picked up automatically.

## V1 skill list (18 tech-agnostic)

| # | Skill ID | Role |
|---|----------|------|
| 1 | tdd | Test-driven development discipline: red/green/refactor, failing tests first. |
| 2 | traceability-discipline | Universal traceability rules: every artifact traces to a prior-phase element. |
| 3 | requirements-extraction | PH-000 generator: extract requirements from documents fidelity-first. |
| 4 | requirements-quality-review | PH-000 judge: evaluate requirements for completeness and atomicity. |
| 5 | feature-specification | PH-001 generator: group requirements into features with acceptance criteria. |
| 6 | feature-quality-review | PH-001 judge: evaluate features for testability and completeness. |
| 7 | architecture-decomposition | PH-002 generator: split enhancement into components, choose boundaries. |
| 8 | tech-stack-catalog | PH-002 generator: high-level awareness of candidate technology stacks. |
| 9 | architecture-review | PH-002 judge: evaluate stack manifests for coherence and feasibility. |
| 10 | solution-design-patterns | PH-003 generator: tech-agnostic design discipline (SoC, interfaces, error handling). |
| 11 | solution-design-review | PH-003 judge: evaluate designs for modularity, testability, and clarity. |
| 12 | contract-first-design | PH-004 generator: write interface contracts before implementations. |
| 13 | contract-review | PH-004 judge: evaluate contracts for completeness and consistency. |
| 14 | simulation-framework | PH-005 generator: write simulations exercising contracts pre-implementation. |
| 15 | simulation-review | PH-005 judge: evaluate simulations for coverage and realism. |
| 16 | code-review-discipline | PH-006 judge: universal code review (readability, testability, no dead code). |
| 17 | cross-component-verification | PH-007 generator: verify components integrate correctly at contract boundaries. |
| 18 | verification-review | PH-007 judge: evaluate cross-component verification completeness. |

## Plugin structure

```
plugins/methodology-runner-skills/
  .claude-plugin/
    plugin.json
  README.md
  skills/
    tdd/SKILL.md
    traceability-discipline/SKILL.md
    ...
```

## License

See repository root.
