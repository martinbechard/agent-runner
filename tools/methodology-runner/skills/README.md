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
| 1 | structured-design | Inline prompt directives for architecture and solution-design generation. |
| 2 | structured-review | Inline prompt directives for structured review and checklist-driven judging. |

## Local Authoring Material

The root `tools/methodology-runner/skills/` tree still contains methodology
authoring/reference material such as:

- `judge-creation`
- `traceability-discipline`
- `authoring-prelude.txt`
- `AUTHORING-CONTEXT.md`

These are not currently auto-discovered by the installed runtime.

## Structure

```
tools/methodology-runner/skills/
  README.md
  AUTHORING-CONTEXT.md
  authoring-prelude.txt
  judge-creation/SKILL.md
  traceability-discipline/SKILL.md

tools/methodology-runner/skills/
  structured-design/SKILL.md
  structured-review/SKILL.md
  structured-review/references/generic-structured-document-checklist.md
```

## License

See repository root.
