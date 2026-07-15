# Agent Claim Coordination Enhancement Set

**Status:** Proposed

**Type:** Holding

## Summary

Provide the owner of the shared `agent-claim` skill with a portable set of six
enhancements that reduce speculative broad claims, distinguish worktree-local
commits from shared integration, and add a repository-global claim event
journal with two-day hot retention, durable archival, and contention reports.

This document is a handoff package. It is intentionally held outside the
dispatchable `agent-runner` feature backlog because the implementation belongs
to the repository that owns `skills/agent-claim/scripts/claim.py`.

## Context

The current claim command keeps only active state in the Git common directory's
`agent-claims.json`. It supports `status`, `acquire`, `heartbeat`, and `release`.
File ancestry and identical resources define overlap. A conflicting request
returns `WAIT`; a non-overlapping second writer requires or receives an
isolated worktree.

Analysis of `agent-runner` claim activity on July 14 and 15, 2026 found two
different contention patterns:

- Some July 14 claims used directory scopes, four or more requested paths, or
  the task-long `git:commit` resource.
- By July 15 most scopes were two exact files, but nearly every report task
  requested the same implementation and test files. Explicit waits included
  approximately 15 minutes 45 seconds and 3 minutes 58 seconds.
- Future file scope was often unknown at task start, encouraging agents either
  to overclaim or to release and reacquire after discovering another path.
- Historical analysis required reconstructing claim commands and results from
  task rollout logs because the live registry removes released claims.
- Rollout logs contain full task transcripts and can replay prior history in a
  resumed or forked task. They are therefore too broad and task-oriented to be
  the authoritative claim history.

The canonical implementation currently lives at:

- `skills/agent-claim/scripts/claim.py`
- `skills/agent-claim/SKILL.md`
- `scripts/test_agent_claim.py`

## Requirements

- Preserve the current registry as the authoritative live coordination state.
- Preserve existing command names, structured outcomes, and exit codes unless
  a separately documented compatibility migration is provided.
- Keep all repository-global state under the Git common directory so linked
  worktrees observe the same claims and journal.
- Keep journal records coordination-specific. Do not copy prompts, model
  responses, tool output, reasoning, or arbitrary transcript content.
- Avoid free-form task content in durable journal events by default; stable
  identifiers, relative scopes, modes, outcomes, and conflict data are enough
  for contention analysis.
- Keep claim operations safe when journaling or journal maintenance fails.
- Add concurrency, worktree, scope-change, journaling, and archival tests to
  the focused claim test suite.
- Update the shared skill instructions and any generated or published skill
  surfaces together with the implementation.

## Enhancement 1: Atomic Claim Scope Extension

### Problem

Agents cannot always know every touched file or exclusive resource before
investigation begins. The current command has no supported way to add a newly
discovered path to an existing claim. Agents compensate by claiming likely
directories up front or by releasing and reacquiring, both of which increase
contention or create an ownership gap.

### Proposed Behavior

Add an atomic command such as:

```text
claim.py --repo . extend \
  --claim-id <claim-id> \
  --file <new-path> \
  --resource <new-resource>
```

While holding the existing registry lock, the command should:

- Locate the existing claim and reject unknown claim IDs.
- Normalize and deduplicate requested additions.
- Check only the new scope against every other active claim.
- Exclude the claim being extended from its own overlap check.
- Add all requested files and resources as one atomic operation when none
  conflict.
- Return `WAIT` without changing the claim when any requested addition
  conflicts.
- Return the conflicting claim IDs and the exact overlapping path or resource
  pairs in structured output.
- Treat repeated requests for already-owned scope as idempotent success.
- Record the extension in the claim event journal when Enhancement 4 exists.

Scope contraction should be a separate future operation because relinquishing
a path while that path still has uncommitted changes can expose unsafe work.

### Acceptance Criteria

- An existing claim can add multiple files and resources atomically.
- A conflicting addition leaves the original claim byte-for-byte unchanged.
- Two simultaneous extensions cannot both acquire the same new path.
- Extending one isolated-worktree claim does not change its worktree, branch,
  baseline commit, or original claim timestamp.
- The response distinguishes additions from scope the claim already owned.

## Enhancement 2: Explicit Broad-Scope Guardrails

### Problem

The current ancestry algorithm intentionally treats a path as overlapping all
descendants, but `--file` does not distinguish one exact file from an entire
directory tree. Repository root, wildcard, and directory scopes can therefore
be requested without an explicit acknowledgement of their contention impact.

### Proposed Behavior

Introduce explicit broad-scope syntax instead of relying on the vague phrase
"bulk operation":

- Keep `--file <path>` for exact intended files.
- Add `--tree <path>` for an intended directory subtree.
- Add `--all-files` for the complete repository.
- Require `--scope-reason <bounded-text>` whenever `--tree` or `--all-files`
  is used.
- Reject `--file .`, `--file **`, and an existing directory passed through
  `--file`, with a message directing the caller to the explicit broad form.
- Define a compatibility period for older callers that used directory values
  with `--file`; warnings should precede hard rejection if compatibility is
  required.
- Include scope kind and the bounded reason in the claim registry and journal.
- Keep the reason short and local; it must not contain prompts or sensitive
  company information.

Enable this guardrail only after atomic scope extension is available, so an
agent can begin with narrow evidence and safely add scope as it learns more.

### Acceptance Criteria

- Exact files, directory trees, and repository-wide ownership are represented
  unambiguously.
- A broad scope cannot be acquired without an explicit reason.
- Existing overlap behavior remains correct for tree and all-files scopes.
- Structured rejection output identifies the offending scope and the required
  replacement syntax.
- Tests cover root, wildcard, existing directory, nonexistent future file,
  nested tree, and compatibility-mode behavior.

## Enhancement 3: Worktree-Aware Git Resource Semantics

### Problem

`git:commit` is documented as a common exclusive resource. A task that holds it
for its full lifetime can block unrelated work even though linked worktrees
have independent indexes, checked-out branches, and commits. The genuinely
shared operation is integration into the same target branch, not committing on
separate branches.

### Proposed Behavior

- Remove task-long `git:commit` from the recommended shared-resource examples.
- State explicitly that an isolated writer may commit to its unique branch
  without a repository-global commit resource.
- Reserve a target-specific resource for integration, for example
  `merge:integration:<target-branch>`.
- Acquire the integration resource only for the merge, cherry-pick, rebase, or
  equivalent update of the shared target branch, then release it promptly.
- Continue using dedicated resources for genuinely shared hooks, generators,
  databases, ports, or output locations when those operations cross worktree
  boundaries.
- Return the claim mode and target worktree clearly enough for agents to select
  the correct commit and integration behavior.

### Acceptance Criteria

- Two non-overlapping isolated claims can commit concurrently on unique
  branches without requesting a shared `git:commit` resource.
- Two attempts to integrate into the same target branch cannot proceed under
  the same target-specific integration resource.
- Integrations into different target branches do not conflict unless another
  declared shared resource overlaps.
- The skill documentation no longer implies that every Git commit is a global
  repository operation.
- Tests exercise primary, isolated, and target-integration cases.

## Enhancement 4: Repository-Global Claim Event Journal

### Problem

`agent-claims.json` contains only live claims. Once a claim is released, the
repository loses the acquisition, wait, heartbeat, recovery, and release
history. Rollout logs happen to contain some claim commands, but they are
per-task transcripts rather than a complete repository coordination ledger.

### Proposed Behavior

Write one append-only JSON Lines event for every claim command outcome under
the Git common directory:

```text
agent-claim-events/hot/YYYY-MM-DD.jsonl
```

Each event should use a versioned schema containing only coordination data:

- `schema_version`
- `event_id`
- UTC `timestamp`
- `action` and `outcome`
- `claim_id`, `root_task_id`, and optional `parent_claim_id`
- bounded agent identifier
- claim mode
- normalized relative file, tree, and resource scopes
- conflicting claim IDs and exact overlap details for `WAIT`
- branch or worktree identifier without unnecessary absolute user paths
- baseline and resulting commit IDs when relevant
- journal warning metadata when event persistence fails

Record at least acquire success and rejection, `WAIT`, isolate-required,
recovery-required, recovery acquisition, extension success and rejection,
heartbeat, release rejection, and release success.

The live registry must remain the coordination authority. Journal writing is
audit and diagnostics support: a journal failure must be visible in structured
output but must not corrupt or weaken registry locking. The implementation must
document and test its chosen crash-consistency behavior.

### Acceptance Criteria

- Claims created from any linked worktree append to the same daily journal.
- Concurrent events remain complete, individually parseable JSON lines.
- Event order is deterministic within the existing registry lock.
- The journal contains no prompt, response, reasoning, or arbitrary tool-result
  content.
- A released claim can be reconstructed as a lifecycle from journal events.
- Forked or resumed rollout history cannot duplicate journal events because
  the command assigns each real event a unique ID at execution time.
- A simulated journal-write failure returns an explicit warning and preserves
  claim safety.

## Enhancement 5: Two-Day Hot Journal and Durable Archival

### Problem

An indefinitely growing hot event file becomes expensive to inspect and risks
turning routine status checks into another source of contention. Recent events
are useful for active diagnosis, while older events should remain available as
durable, compact history.

### Proposed Behavior

Add an idempotent maintenance command such as:

```text
claim.py --repo . maintain-journal --hot-days 2
```

The default policy should:

- Keep today and the preceding calendar day as uncompressed daily JSONL files
  under `agent-claim-events/hot/`.
- Process complete UTC days older than the two-day hot window.
- Produce an immutable compressed raw archive such as
  `agent-claim-events/archive/YYYY/MM/YYYY-MM-DD.jsonl.gz`.
- Produce a small daily journal summary such as
  `agent-claim-events/journal/YYYY/MM/YYYY-MM-DD.json` or `.md`.
- Include counts by action and outcome, claim durations, wait episodes, wait
  duration when correlatable, top conflicting paths and resources, recovery
  events, and incomplete lifecycles in the daily summary.
- Validate the compressed archive before removing the corresponding hot file.
- Use temporary files plus atomic rename so interruption cannot leave a
  half-written archive presented as complete.
- Be safe and idempotent when rerun after partial completion.
- Never archive the current UTC day's file.
- Retain compressed archives indefinitely by default. Any deletion policy must
  be a separate explicit configuration, not an implied consequence of the
  two-day hot window.
- Avoid running compression inside the critical path of claim acquisition.
  Maintenance may be explicit, scheduled, or opportunistic at most once per
  day through a bounded background-safe mechanism.

The daily journal summary is the human- and metrics-friendly history. The
compressed JSONL remains the forensic source when deeper analysis is needed.

### Acceptance Criteria

- With a two-day hot window, only the current and previous UTC daily JSONL
  files remain uncompressed after maintenance.
- Every older complete day has a validated compressed archive and summary.
- Raw event count and event IDs before and after compression reconcile exactly.
- Rerunning maintenance produces no duplicate archive, summary, or event.
- Simulated interruption before validation leaves the original hot file
  untouched.
- Active claim operations remain available while old journals are processed;
  maintenance locking is narrow and documented.
- Archive retention is lossless by default and deletion requires separate
  explicit policy.

## Enhancement 6: Native Contention Diagnostics

### Problem

Without a claim-specific reporting surface, operators must search rollout
transcripts and manually correlate timestamps, claim IDs, requested paths, and
releases. This obscures whether contention comes from broad trees, hot exact
files, long claim duration, or shared resources.

### Proposed Behavior

Add a read-only report command backed by the event journal, for example:

```text
claim.py --repo . report --since 2d
```

Support structured JSON by default and an optional concise human-readable
format. Report:

- successful acquisitions by primary, isolated, and recovery mode
- `WAIT`, isolate-required, recovery-required, and release-rejected counts
- wait episodes and durations where a later successful event can be correlated
- median, percentile, and maximum claim duration
- top overlapping exact files, directory trees, and resources
- broad-scope frequency and reasons
- claims with missing release or stale heartbeat evidence
- integration-resource utilization
- journal coverage gaps or write warnings

The report must use only claim events and the live registry. It must not parse
Codex, Junie, Claude, or other harness transcripts.

### Acceptance Criteria

- The report reproduces known synthetic contention scenarios from focused
  tests.
- Exact-file hotspots are distinguishable from directory-tree and resource
  contention.
- Repeated polling by one blocked claim can be grouped into one wait episode
  while retaining the raw attempt count.
- Open claims are combined with journal history without being double-counted.
- JSON output has a versioned schema suitable for repository reporting tools.
- The command remains read-only and does not modify the registry or journal.

## Acceptance Criteria

- The receiving owner can split each numbered enhancement into an independent
  backlog item without needing the originating conversation.
- Dependencies and recommended order are explicit.
- The proposal distinguishes live registry state, the claim event journal,
  daily journal summaries, compressed archives, and external rollout logs.
- The two-day policy preserves older history rather than deleting it.
- The proposal does not prescribe changes to `agent-runner` report code or its
  project-only modularization backlog item.

## Dependencies

External intake by the owner of the shared `agent-claim` skill. Within the set,
the recommended implementation order is:

1. Atomic claim scope extension.
2. Repository-global claim event journal.
3. Two-day hot journal and durable archival.
4. Native contention diagnostics.
5. Explicit broad-scope guardrails.
6. Worktree-aware Git resource semantics.

Broad-scope rejection should not become mandatory before scope extension is
available. Archival and diagnostics depend on the event journal schema.

## Verification

- Run `python3 -m unittest scripts.test_agent_claim` in the canonical skill
  repository after every implementation stage.
- Add subprocess concurrency tests for acquisition, extension, journal append,
  and target-branch integration resources.
- Add linked-worktree tests proving every worktree resolves the same registry
  and event journal.
- Add deterministic-clock fixtures for daily rollover, the two-day boundary,
  daylight-saving independence, and incomplete current-day behavior.
- Add archive fault-injection tests covering interrupted write, failed
  validation, rerun, and exact event reconciliation.
- Add schema fixtures for journal events, daily summaries, and report output.
- Run the skill documentation generation and publication checks required by
  the canonical repository.
- Run `git diff --check` before delivery.

## Notes

- The two-day window means two UTC calendar files remain hot: today and
  yesterday. It does not mean "48 hours since each event," which would split
  daily files during archival.
- Absolute worktree paths may expose usernames or machine layout. Prefer mode,
  branch, and a repository-relative or opaque worktree identifier in durable
  journal records.
- Heartbeats can be noisy. The raw journal may record them while daily summaries
  collapse them to first, last, and count per claim.
- If journal durability is later promoted from diagnostic to coordination
  authority, that is a separate design requiring explicit transaction and
  recovery semantics.
