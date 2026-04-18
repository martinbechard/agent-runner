# PR-009 — Audit Variant A (flat)

Flat Codex-compatible version of PR-003 Variant A: the long task list
approach for auditing the PH-000 requirements inventory.

**How to run:**

```
prompt-runner run docs/prompts/PR-009-audit-variant-a-flat.md \
  --project-dir /tmp/test-ph001-workspace-3
```

The workspace must already contain:
- `docs/requirements/raw-requirements.md`
- `docs/requirements/requirements-inventory.yaml`

---

## Prompt 1: Validate workspace state

```
Read these two files and confirm they exist and are non-empty:

1. docs/requirements/raw-requirements.md
2. docs/requirements/requirements-inventory.yaml

If both exist and contain content, respond with:
"Workspace validated. Both files present."

If either is missing or empty, respond with:
"ERROR: <which file> is missing or empty."
```

```
Check the response. If it says "Workspace validated", pass.
If it mentions ERROR, revise.

VERDICT: pass
```

## Prompt 2: Audit the requirements inventory (Variant A)

```
You are a requirements engineer performing a coverage hardening pass
on an existing requirements inventory.

STEP 1: Read both files.

Use the Read tool to read:
  docs/requirements/raw-requirements.md
  docs/requirements/requirements-inventory.yaml

STEP 2: Paragraph-by-paragraph cross-check.

Go through the raw requirements document one paragraph at a time,
one sentence at a time. For EVERY sentence that contains shall,
must, will, should, or an imperative verb describing system
behaviour, verify there is a corresponding RI-* item in the
inventory whose verbatim_quote matches that sentence or clause.

Also check:
  - The "Context and motivation" section for implicit requirements
    or assumptions (e.g., "single binary", "zero configuration",
    "sensible defaults", "intentionally minimal").
  - List items within numbered requirements (e.g., the ignore
    patterns in item 10 are part of one constraint, not separate
    requirements, but verify they are fully captured in the quote).

STEP 3: Identify gaps.

List any statements from the source document that have no
corresponding RI-* item. These are gaps that must be filled.

STEP 4: Check for unsplit compounds.

Review each existing RI-* item. If a verbatim_quote contains
multiple independent clauses describing distinct system behaviours
joined by "and", "or", or semicolons, split them into separate
items. Assign new sequential RI-NNN IDs continuing from the
highest existing ID.

When splitting:
  - Each new item gets the relevant clause as its verbatim_quote
    (exact text from the source, not rewritten).
  - Preserve the original item's source_location.
  - Update tags and rationale appropriately.
  - The rationale should note "split from RI-NNN" in the because field.

STEP 5: Verify all verbatim_quote values.

For every RI-* item (existing and new), confirm the verbatim_quote
text appears character-for-character in the source document. If you
find any discrepancy (extra spaces, changed words, missing
punctuation), correct the quote to match the source exactly.

STEP 6: Verify category assignments.

Cross-check each item's category against its source section and
the language used:
  - Functional section + shall/must -> functional
  - Non-functional section + shall -> non_functional
  - Constraints section + shall skip/shall not -> constraint
  - Assumptions section -> assumption
  - Context section items -> typically assumption or constraint

Fix any mismatches.

STEP 7: Rebuild coverage_check.

Create a fresh coverage_check mapping. For each numbered
requirement in the source document, extract a short identifying
phrase and map it to all RI-* IDs that cover it. Include any
additional requirements found in the Context section. Add a status
line with accurate counts.

STEP 8: Rebuild coverage_verdict.

Recompute all counts:
  total_upstream_phrases: count of distinct source statements checked
  covered: count covered by at least one RI-* item
  orphaned: count with no coverage (must be 0 for PASS)
  out_of_scope: count of items in out_of_scope list
  open_assumptions: total count of ASM-* entries across all items
  verdict: PASS if orphaned is 0, FAIL otherwise

STEP 9: Write the updated file.

Use the Write tool to write the complete updated YAML to:
  docs/requirements/requirements-inventory.yaml

The file must be valid YAML. All RI-NNN IDs must be unique and
zero-padded to three digits.

IMPORTANT: Do not remove any correctly extracted items from the
previous version. Only add missing items, split compounds, fix
quotes, and update coverage sections.
```

```
You are a senior requirements auditor performing final verification.
Be thorough and strict.

Read both files:
  docs/requirements/raw-requirements.md
  docs/requirements/requirements-inventory.yaml

Check each of these in order:

1. YAML validity — all required fields present per item
2. Completeness — every source statement has a corresponding RI-* item
3. Fidelity — every verbatim_quote appears character-for-character in source
4. Atomicity — no unsplit compounds
5. Categories — correct per source section and language
6. Coverage check — accurate counts, all IDs valid
7. No invented requirements — every item traces to real source text

Severity:
  CRITICAL: omissions, inventions, fidelity errors, invalid YAML
  MAJOR: unsplit compounds, wrong categories, coverage errors
  MINOR: missing tags, weak rationale, style

Decision:
  Any CRITICAL -> VERDICT: revise
  Any MAJOR -> VERDICT: revise
  Only MINOR -> VERDICT: pass

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
