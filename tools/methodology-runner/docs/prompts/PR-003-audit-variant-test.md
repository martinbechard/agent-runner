# PR-003 — Audit approach A/B test

A/B test comparing two audit approaches for the requirements inventory
phase (PH-000). Uses the prompt-runner [VARIANTS] fork mechanism.

**How to run:**

```
prompt-runner run docs/prompts/PR-003-audit-variant-test.md \
  --project-dir <workspace-with-completed-ph000>
```

The workspace must already contain:
- `docs/requirements/raw-requirements.md` (the source document)
- `docs/requirements/requirements-inventory.yaml` (from a completed PH-000 run)

Prompt 1 reads and validates both files exist. Prompt 2 forks into two
variants that each audit the inventory using a different approach.
After both variants complete, compare their results via
`tools/report/scripts/run-timeline.py` and the fork's `comparison.txt`.

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

## Prompt 2: Audit the requirements inventory [VARIANTS]

### Variant A: Long task list (current approach)

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

### Variant B: Two-pass checklist

```
You are a requirements auditor performing a structured two-pass audit.

PASS 1: EXTRACTION CHECKLIST (no inference, mechanical only)

Read both files:
  docs/requirements/raw-requirements.md
  docs/requirements/requirements-inventory.yaml

Walk the source document section by section, paragraph by paragraph.
For each requirement-bearing statement (shall, must, will, should, or
imperative verb), produce a checklist entry:

  extraction_checklist:
    - section: "Functional"
      statement_number: 1
      source_text: "exact text from source"
      matching_ri_ids: [RI-001, RI-002]  # or [] if no match
      match_status: covered | partial | missing
      verbatim_match: true | false  # does the RI's verbatim_quote match exactly?
      notes: ""  # only if partial — what's different

Include the "Context and motivation" section — scan for implicit
requirements and assumptions.

Rules:
- Do NOT infer whether a finding is important. Just record what you see.
- Do NOT fix anything. This is observation only.
- Every statement gets an entry, even if perfectly covered.
- "covered" means at least one RI-* item's verbatim_quote matches.
- "partial" means an RI-* item exists but the quote doesn't match exactly.
- "missing" means no RI-* item corresponds to this statement.

Also produce a reverse checklist — for each RI-* item, verify it maps
to a real source statement:

  reverse_checklist:
    - ri_id: RI-001
      source_statement: "exact text this traces to"
      source_found: true | false  # does the source actually contain this?
      category_matches_section: true | false

PASS 2: JUDGMENT CHECKLIST

Read your extraction checklist. For each entry that is NOT
"covered + verbatim_match=true + category_matches=true", produce
a finding:

  findings:
    - source: "extraction_checklist[3]" or "reverse_checklist[5]"
      severity: critical | major | minor
      finding_type: omission | fidelity | compound | category | invention
      description: "what's wrong, specifically"
      fix: "what to change in the inventory"

Severity rules:
  critical: match_status=missing (omission), source_found=false (invention),
            verbatim_match=false with meaning change (fidelity)
  major: compound not split, category wrong
  minor: verbatim_match=false but only whitespace/punctuation difference

Write the complete audit (both checklists + findings) as your response.
Do NOT modify the inventory file — this is audit only.
```

```
You are reviewing a two-pass audit of a requirements inventory.

Read the audit output. Check:

1. EXTRACTION CHECKLIST completeness:
   - Does it have an entry for every requirement-bearing statement
     in docs/requirements/raw-requirements.md?
   - Read the source document yourself and verify no statements were
     skipped in the checklist.

2. REVERSE CHECKLIST completeness:
   - Does it have an entry for every RI-* item in the inventory?

3. FINDINGS accuracy:
   - For each finding marked "critical", verify it's genuinely critical
     (not a false positive).
   - For any "missing" items, confirm they're actually missing by
     checking the inventory yourself.

4. FINDINGS completeness:
   - Are there extraction_checklist entries with match_status != covered
     that have NO corresponding finding? That's a gap in the judgment pass.

If the audit is thorough and accurate: VERDICT: pass
If the audit missed source statements or has false findings: VERDICT: revise

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
