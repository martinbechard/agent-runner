# Session notes — skill-driven methodology-runner follow-up work

**Date:** 2026-04-09
**Status:** Working notes, not a formal spec. Captures the state at end of the
            skill-driven methodology-runner implementation session and the
            agreed next direction for the skill pack + interactive harness work.
**Related:**
- `docs/superpowers/specs/2026-04-09-skill-driven-methodology-runner-design.md` (original spec, implemented)
- `docs/superpowers/plans/2026-04-09-skill-driven-methodology-runner.md` (implementation plan, executed)

---

## 1. Current state of the skill-driven methodology-runner

The Python/docs implementation landed cleanly on 2026-04-09 via subagent-driven
execution of the 19-task plan.

- **Tests:** 373/373 passing (305 baseline + 68 new across 19 tasks)
- **Commits on main:** 23 (2 baseline + 19 feature + 2 minor fixes)
- **Phase 0 validation outcome:** `skill-tool` mode verified against real
  `claude --print`; `constants.SKILL_LOADING_MODE = "skill-tool"` is the confirmed default

**New Python modules:** `constants.py`, `skill_catalog.py`, `baseline_config.py`,
`artifact_summarizer.py`, `skill_selector.py`, `prelude.py`, `phase_0_validation.py`

**Modified:** `models.py`, `phases.py` (inserted PH-002 Architecture, renumbered
PH-002..PH-006 to PH-003..PH-007), `orchestrator.py`, `prompt_generator.py`,
`cli.py`, `cross_reference.py`, `prompt_runner/runner.py`, `prompt_runner/__main__.py`,
`pyproject.toml`, `M-002-phase-definitions.md`, `CD-002-methodology-runner.md`

**New data:** `docs/methodology/skills-baselines.yaml` (non-negotiable baseline
skills per phase)

## 2. What is NOT yet done (intentionally deferred)

Per spec section 14, three follow-up items are still open:

1. **18 v1 SKILL.md files** for the companion `methodology-runner-skills` plugin
   — the tech-agnostic core listed in spec section 11. This is knowledge-engineering
   work, not code, and it's the main bottleneck for exercising the full system.

2. **PyPI / Claude Code plugin library distribution** — blocked on the skill
   pack existing.

3. **3-4 stub SKILL.md files for CLI smoke-testing** — a minimal set just
   sufficient to satisfy catalog discovery and let `methodology-runner run`
   execute end-to-end against a tiny requirements file before the real skill
   pack is ready.

**Important:** do NOT assume the Python side is missing anything. Run
`pytest -q` first (should show 373 passing). The Python implementation is
complete.

## 3. Why subagent-driven-development is the wrong fit for skill authoring

The 19-task Python plan executed cleanly via subagents because each task had
verbatim code blocks — deterministic mechanical implementation.

Skill authoring is different. Each SKILL.md needs pattern identification,
example curation, framing for when the skill applies, and iteration. That's
knowledge-curation work requiring human-in-loop judgment, not deterministic
implementation. A subagent given "author the tdd SKILL.md" would produce
something plausible but not considered — we'd end up with 18 plausible but
shallow skills.

The right execution model is **interactive claude sessions** where the user
drives the authoring, using `superpowers:skill-creator` as the in-session
guide, with a harness that sequences the work across skills.

## 4. Proposed approach — extend prompt-runner with interactive mode

Martin proposed extending `prompt-runner` (rather than creating a new tool)
with two features:

1. **Per-prompt `interactive: true` marker** — e.g., `## Prompt 1: Author tdd skill [interactive]`.
   When set, skip the generate-judge-revise loop entirely. Instead spawn
   `claude "<mission>"` with inherited stdin/stdout/stderr, wait for the
   process to exit, then check that any declared target file was created
   (structural lint only, no LLM validation).

2. **Optional validator** — a prompt block with only ONE code fence means
   no judge runs and the verdict is implicitly `pass`. This makes interactive
   mode coherent (the human IS the validator in-session) and is also useful
   for batch mode when validation isn't needed.

**Why extend instead of create:** prompt-runner already owns "sequence of
tasks with workspace + git awareness" — 90% of the machinery is already
there. A new tool would duplicate that without adding capability, and would
dilute prompt-runner's purpose.

**Size:** ~100-150 lines of prompt-runner changes including tests. Localized
extension; does not change existing generate-judge-revise behavior when the
new flags are absent.

## 5. Load-bearing assumption to test FIRST

The whole interactive-harness approach hinges on one untested assumption:

> Can `claude "<mission>"` (no `-p` flag) spawn an interactive session with
> the mission as the initial message, hand stdin/stdout to the user, and
> exit cleanly back to the parent process so the harness can resume?

If yes, the harness is ~40 lines of Python and works as expected. If no,
the fix is isolated to "how do we spawn claude interactively" — investigate
and adjust the invocation. No downstream code should be written until the
assumption is verified.

**Test script** — save as `scripts/test-interactive-claude.sh` and run it:

```bash
#!/bin/bash
# Verify that claude can be spawned interactively with an initial mission
# and exit cleanly back to the parent shell so a harness can resume control.

set -e

MISSION="You are my pair programmer for a 2-minute test. Say hello, then wait \
for me to say 'ready'. When I say 'ready', tell me one interesting fact and \
then tell me to type /exit to finish the test. Do nothing else."

echo "=== About to spawn: claude \"\$MISSION\" ==="
echo "When you see the interactive session: say 'ready', then type /exit."
echo "Press Enter to begin..."
read -r

# Important: NO pipes or redirection — stdin/stdout/stderr inherit from this
# shell so the user sees a real TTY session.
claude "$MISSION"
EXIT_CODE=$?

echo ""
echo "=== claude exited with code $EXIT_CODE ==="
echo "If you saw a real interactive session and it returned here cleanly,"
echo "the harness approach works."
```

Three things to watch for:

1. Does `claude "<mission>"` with no other flags actually enter interactive
   mode with the mission as the first message? Not 100% certain — might
   require an explicit flag like `-i`, or might interpret the argument as
   a file path. Check `claude --help` first if unsure.
2. Does exiting return control to the shell cleanly?
3. Is stdin preserved after exit (no TTY raw-mode leftover)?

## 6. Integration agent — simulated downstream consumer for single-phase testing

Martin's idea: while developing a single phase (say PH-001), we want to
test it with real skills and real agents, but the downstream phases (PH-002
through PH-007) may not exist yet. Instead of running them for real, **insert
an "integration agent" that simulates downstream consumers**. It reads the
phase's output + all prior artifacts, pretends to be the next phase's
generator, and produces a holistic usability critique beyond what the
phase's own judge checks.

### Why this fills a gap

Current testing covers three layers:

1. Schema/format — does the YAML parse, do IDs match patterns
2. Per-phase judge — phase-specific quality criteria
3. Cross-reference verifier — formal link integrity between phases

None of these answer "is this output actually USABLE by downstream phases?"
A human reviewer reading a PH-001 output with fresh eyes catches ambiguities,
missing context, and contradictions that the phase-local judge misses.
The integration agent is that fresh-eyes reviewer, automated.

### The pattern is free once optional-validator lands

The integration agent is just a prompt-runner invocation with optional
validator (no judge step):

- Generator prompt = "simulate downstream consumers, read these artifacts, produce a usability critique as YAML"
- Validator = none (skipped via the optional-validator feature)

Per-phase critic prompt files:

```
docs/prompts/integration-agent-PH-001-feature-specification.md
docs/prompts/integration-agent-PH-002-architecture.md
...
```

Development cycle:

1. Build real skills + prompts for PH-001
2. Run `methodology-runner run <tiny-reqs.md> --phases PH-001-feature-specification` for real
3. Run `prompt-runner run docs/prompts/integration-agent-PH-001.md` against the same workspace — critique produced as workspace artifact
4. Read critique, iterate on PH-001's skills/prompts/judge, repeat
5. When PH-001 is solid, move to PH-002, repeat

### Suggested critique output format

```yaml
phase_evaluated: PH-001-feature-specification
integration_agent_run_at: 2026-04-10T...
findings:
  - severity: blocking | warning | info
    location: features.FT-003
    issue: |
      FT-003 assumes a browser client but doesn't say so — the
      architect will not know whether to propose a web or mobile
      stack, and may silently pick one based on other signals.
    recommendation: "Add a client-type assumption to FT-003, or
                     cite the source requirement that implies it."
  - ...
overall_usability: high | medium | low
summary: "Brief text summary — 2-3 sentences."
```

### Design questions (decide later)

- **Gate or informational?** My instinct: informational during early
  development; promote to hard gate later if the agent's verdicts become
  reliable enough. Start soft.
- **Who authors the integration agent prompts?** Each is 1-2 hours of
  careful authoring because the prompt has to describe what downstream
  phases actually need. They could themselves be authored via the
  interactive harness once it exists (nice recursion).
- **Does the integration agent need skills?** Start prompt-only; add
  skills if critiques turn out shallow.
- **Lifespan.** Scaffold for early development. Once real downstream
  phases exist, real pipeline runs are better signal. Could retire the
  agents or keep them as regression guards — decide later.

### Risk

Integration agents can become a crutch. You might stop running real
downstream phases even after they exist because the agent is faster.
Resist that — the agent is a development aid, not a replacement. Real
pipeline runs remain the source of truth. Treat the agent's output as a
hint worth investigating, not a verdict.

## 7. Clean LLM-driven session exit — three-tier CLI pattern

**Constraint (important, easy to forget):** this project uses the `claude`
CLI specifically because it runs against the user's Claude Pro/Max
subscription. The [Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/)
makes direct API calls with pay-per-token billing — that's a different
billing model and is off the table. Any solution must use the CLI, not
the SDK.

**Empirical finding (Martin tested 2026-04-09):** the `claude` CLI cannot
exit itself from within an interactive session. Only the human can exit
(via `/exit` or Ctrl-C), or a tool can call `kill` on the process (ugly
and loses any structured result). There is no clean in-session exit
mechanism for interactive mode.

Conclusion: there is no single "clean LLM-driven session exit" for all
cases. Instead, there are three distinct patterns depending on what kind
of work the agent is doing, and each has its own clean exit model.

### The three-tier landscape

| Use case | CLI invocation | Exit mechanism |
|---|---|---|
| **Interactive human-driven** (skill authoring) | `claude "<mission>"` | Human types `/exit` or Ctrl-C |
| **Single-turn autonomous agent** (integration critic) | `claude -p "<mission>"` | Process exits naturally after the response |
| **Multi-turn autonomous agent** (future use cases) | Harness loop of `claude -p --resume <session-id>` | Parent harness decides when to stop based on agent output |

### Key insight: `claude -p` is multi-tool within a single response

`claude -p` is NOT a single LLM call with no tool use. Within a single `-p`
invocation, the agent can Read files, run Bash, Write files, think, and
then emit final text — all inside ONE invocation that then exits cleanly.
It's only "single-turn" in the sense that there's no back-and-forth
conversation. The agent still does rich multi-step work before emitting
its final output.

For the integration agent use case, this is more than sufficient:

1. Agent Reads workspace artifacts
2. Agent analyzes
3. Agent emits YAML critique as final text
4. Process exits naturally
5. Parent reads stdout, parses YAML, done

No kill-tricks, no human intervention, no SDK. This is exactly what
prompt-runner already does for every generator and judge call — we're
just adding one more pattern ("critic with no validator") on top.

### Mapping to our actual use cases

- **Skill authoring (interactive)** → `claude "<mission>"`, user drives,
  user types `/exit`. The mission prompt should make this explicit:

  ```
  You are helping me author the tdd SKILL.md file. Use the
  superpowers:skill-creator skill. When we're both satisfied
  with the final file, tell me to type /exit to return control
  to the harness.
  ```

  Harness waits via `subprocess.wait()`. Clean.

- **Integration agent (autonomous, per-phase critic)** → `claude -p` via
  prompt-runner with optional validator (§6 pattern, unchanged). The
  critic reads artifacts, emits YAML, exits. Clean.

- **Future multi-turn autonomous agents** → if we ever need a harness
  that drives autonomous multi-turn reasoning (e.g., an agent that has
  to research, propose, revise, propose again, all without human
  involvement), the pattern is: parent harness loops, each iteration
  calls `claude -p --resume <session-id>` with updated context, parent
  decides when to stop based on agent output. Not needed right now but
  documenting for later.

### Why `kill` from a tool is not worth it

Martin flagged the "agent runs a Bash kill command on its own process"
fallback as not-great. Agreeing — skip it:

- Abrupt kill loses any structured result the agent was about to emit
- No clean return value back to the parent
- Parent has to reconstruct the result from files on disk, if any
- Its only use case is "autonomous multi-turn agent decides when to stop",
  which the `claude -p --resume` loop handles better — the parent decides
  when to stop based on the agent's output, not the agent itself

### Stop hooks are still the wrong layer

[Stop hooks](https://code.claude.com/docs/en/hooks) can BLOCK the model
from stopping (force continuation), not help it exit. They're designed
to enforce "are you really done?" gate-keeping. Wrong direction for our
problem.

`SessionEnd` hooks fire on termination for cleanup but can't influence
when termination happens — too late in the lifecycle.

### Sources (from web research, 2026-04-09)

Research was done assuming the Agent SDK was available; it isn't for this
project, so the SDK-specific recommendations don't apply. But the
CLI-related findings remain valid:

- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference) — confirms `-p` for print mode, `/exit` for interactive
- [Claude Code Hooks reference](https://code.claude.com/docs/en/hooks) — confirms Stop hooks block termination rather than enabling it
- [Work with sessions — Claude API Docs](https://platform.claude.com/docs/en/agent-sdk/sessions) — documents the `--resume <session-id>` pattern that the multi-turn autonomous case would use

## 8. Planned order of operations

Not yet started — Martin has more feedback incoming that may change the
shape of this.

1. **Run the test script** (5 min) — confirm interactive spawn + exit detection works.
2. **Write 3-4 stub SKILL.md files** (15-30 min) for CLI smoke-testing
   methodology-runner end-to-end before real skill pack exists.
3. **Extend prompt-runner** with interactive mode + optional validator, TDD as always.
4. **Author 18 SKILL.md files** via the new interactive harness, using
   `superpowers:skill-creator` as the in-session guide, one session per skill.

## 9. Why a mock claude stub is NOT needed for integration testing

We already have one. Task 17's `test_smoke_skill_driven.py` drives the entire
orchestrator through a phase with a scripted `ClaudeClient` and zero real
`claude` calls. That's the unit-level mock. For CLI-level testing against
the actual binary, we need stub SKILL.md files on disk — not a mock claude.

---

## 10. Skill discovery approach — cwd-based, no symlinks

**Decision date:** 2026-04-09
**Status:** Implemented and tested.

### Why symlinks were rejected

The original PR-002 scaffold prompt instructed Claude to create a symlink:

    ln -s /path/to/repo/plugins/methodology-runner-skills \
          ~/.claude/plugins/methodology-runner-skills

This was rejected because it requires per-machine setup (the hardcoded
absolute path breaks on any machine other than Martin's), is not a repo
artifact (can't be committed), and creates invisible state that's easy to
lose or misconfigure.

### The chosen approach: cwd-based discovery

`skill_catalog.build_catalog` now accepts an optional `cwd` parameter
(defaults to `Path.cwd()`). During catalog construction, it walks
`<cwd>/plugins/*/skills/**/SKILL.md` as an additional discovery source,
placed between project-local and user-global in the priority chain.

Priority order (highest first):

1. `<workspace>/.claude/skills/` — project-local overrides
2. `<cwd>/plugins/*/skills/` — cwd-plugin (dev repo skills)
3. `~/.claude/skills/` — user-global skills
4. `~/.claude/plugins/*/skills/` — user-installed plugins

### Dev workflow

1. Keep `plugins/methodology-runner-skills/` in the repo root.
2. Run `methodology-runner run` from the repo root.
3. Discovery walks `plugins/*/skills/` automatically — no symlinks,
   no env vars, no CLI flags.

The cwd-plugin slot is second-highest priority so dev versions in the
repo shadow any system-installed version of the same skill.

### Code change

One new `cwd: Path | None = None` parameter in
`src/cli/methodology_runner/skill_catalog.py::build_catalog`, plus a
~10-line loop that walks `cwd/plugins/*/skills/` when `cwd/plugins/`
exists. Six new tests in `tests/cli/methodology_runner/test_skill_catalog.py`
cover discovery, priority shadowing, and the default-to-cwd behavior.

---

## Open questions / things to revisit

- Does `claude "<mission>"` actually enter interactive mode? (Section 5 — untested)
- Where should the `methodology-runner-skills` plugin directory live during
  development? **Resolved:** under `./plugins/methodology-runner-skills/`
  in this repo — cwd-based discovery picks it up when running from the
  repo root (see §10).
- Should the interactive harness extension be in prompt-runner proper, or
  in a new subcommand `prompt-runner author` that reuses the library but
  has its own CLI surface? (Not decided — extend first, refactor later if needed)
- Which integration agents can run within a single `claude -p` call
  (prompt-runner + optional validator)? For agents that turn out to need
  genuine multi-turn reasoning, fall back to the `claude -p --resume
  <session-id>` harness loop pattern (see §7). Start with single-turn
  where possible; escalate only if needed.
- The session ended mid-feedback from Martin — he has more direction to
  give on this before work begins. These notes are a checkpoint, not a
  finalized plan.
