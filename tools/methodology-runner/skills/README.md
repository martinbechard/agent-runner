# methodology-runner skills

Authoring and reference material for methodology-runner skills.

This directory is the bundled runtime location for methodology-runner skill
content that is injected directly into phase prompts.

The files in this directory remain useful as methodology-owned authoring
context, shared discipline references, and historical skill-pack material.

## Spec

[Skill-Driven Methodology Runner Design](../../docs/superpowers/specs/2026-04-09-skill-driven-methodology-runner-design.md)

## Runtime Packaging

The active phase prompts resolve these files directly from
`tools/methodology-runner/skills/`. This avoids any runtime dependency on a
sibling checkout such as `agent-assets`.

## Quick start

From the repo root:

```bash
methodology-runner run \
  tests/fixtures/tiny-requirements.md \
  --workspace /tmp/test-release-smoke
```

This exercises the packaged prompt/runtime path through the checked-in
`methodology_runner` package.

## Bundled Runtime Skill Resources

| # | Skill ID | Role |
|---|----------|------|
| 1 | ar-structured-design | Agent-runner directives for architecture and solution-design generation. |
| 2 | ar-review-structured-artifact | Agent-runner directives for evidence-backed structured review and judging. |
| 3 | ar-traceability-discipline | Agent-runner directives for schema-respecting source coverage and justification. |

## Local Authoring Material

The root `tools/methodology-runner/skills/` tree still contains methodology
authoring/reference material such as:

- `judge-creation`
- `generator-creator`
- `ar-traceability-discipline`
- `authoring-prelude.txt`
- `AUTHORING-CONTEXT.md`

These are not currently auto-discovered by the installed runtime.

## Structure

```
tools/methodology-runner/skills/
  README.md
  AUTHORING-CONTEXT.md
  authoring-prelude.txt
  generator-creator/SKILL.md
  judge-creation/SKILL.md
  ar-traceability-discipline/SKILL.md

tools/methodology-runner/skills/
  ar-structured-design/SKILL.md
  ar-review-structured-artifact/SKILL.md
  ar-review-structured-artifact/references/review-checklist-structured.md
```

## Source Alignment

- `ar-structured-design` and `ar-review-structured-artifact` are adapted from
  the corresponding `dev-methodology` source skills. The prefix makes their
  runner-specific output and verdict boundaries distinct from user-scope
  skills with portable semantics.
- `generator-creator` and `judge-creation` are synchronized from their current
  user-scope authoring skills.
- `ar-traceability-discipline` is methodology-runner-owned because it must obey
  the runner's phase-specific schemas and deterministic validators.
- Runtime prompt modules include bundled copies through the `skills/` path
  mapping. They do not load these resources from a user-scope skill directory.

## License

See repository root.
