# methodology-runner-skills

Baseline skill pack for the AI-driven development methodology.

All active methodology skills live here, covering the methodology phases with a tech-agnostic generator/judge baseline.

## Spec

[Skill-Driven Methodology Runner Design](../../docs/superpowers/specs/2026-04-09-skill-driven-methodology-runner-design.md)

## Discovery

methodology-runner discovers skills by walking
`<cwd>/tools/methodology-runner/skills/**/SKILL.md`. Run methodology-runner from the
repo root and these skills are picked up automatically.

## Quick start

From the repo root:

```bash
methodology-runner run \
  tests/fixtures/tiny-requirements.md \
  --workspace /tmp/test-release-smoke
```

This uses repo-local discovery from `./tools/methodology-runner/skills/`. No symlinks or extra install step are required while developing in this repo.

## Active skill list

| # | Skill ID | Role |
|---|----------|------|
| 1 | artifact-generator | Shared generator-prompt discipline for methodology artifacts. |
| 2 | judge-creation | Shared judge-prompt discipline for methodology artifacts. |
| 3 | traceability-discipline | Universal traceability rules: every artifact traces to a prior-phase element. |

## Structure

```
tools/methodology-runner/skills/
  README.md
  AUTHORING-CONTEXT.md
  authoring-prelude.txt
  artifact-generator/SKILL.md
  judge-creation/SKILL.md
  traceability-discipline/SKILL.md
  # phase-local rules now live in the prompt modules
```

## License

See repository root.
