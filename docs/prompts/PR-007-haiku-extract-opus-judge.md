# PR-007 — Haiku extraction + Opus judgment (per-pair model override)

Tests the optimal split pipeline: Haiku for mechanical extraction,
Opus for judgment. Uses mid-variant [MODEL:] directives so each
prompt pair within the variant runs on a different model.

Based on findings from PR-004 through PR-006:
- Haiku extraction is reliable and cheap ($0.08 vs $0.55 Opus)
- Haiku/Sonnet judgment hallucinate (flag real items as missing)
- Opus judgment is reliable but the PR-006 variant applied Haiku
  to BOTH extraction and judgment because [MODEL:] was variant-wide

This test uses per-pair model switching:
1. Haiku extraction (no validator) — $0.08
2. [MODEL:claude-opus-4-6] switches to Opus
3. Opus judgment (with validator) — estimated $0.30

Expected total: ~$0.38 vs baseline ~$0.48 (21% savings)

**How to run:**

    prompt-runner run docs/prompts/PR-007-haiku-extract-opus-judge.md \
      --project-dir /tmp/test-ph001-workspace-3 \
      --variant-sequential

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

## Prompt 2: Audit pipeline [VARIANTS]

### Variant Baseline: Opus two-pass combined

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
      verbatim_match: true | false
      notes: ""

Include the "Context and motivation" section.

CRITICAL RULES:
- Read the ACTUAL inventory file. Do NOT guess or invent RI-* IDs.
- Do NOT infer, judge, or fix anything in Pass 1. Pure observation.

Also produce a reverse checklist — for each RI-* item in the
inventory, verify it maps to a real source statement:

  reverse_checklist:
    - ri_id: RI-001
      source_statement: "exact text this traces to"
      source_found: true | false
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

Read both source files yourself:
  docs/requirements/raw-requirements.md
  docs/requirements/requirements-inventory.yaml

Check:

1. EXTRACTION CHECKLIST completeness — every source statement covered?
2. REVERSE CHECKLIST completeness — one entry per RI-* item?
3. FINDINGS accuracy — are critical findings genuinely critical?
4. FINDINGS completeness — any uncovered entries with no finding?

If thorough and accurate: VERDICT: pass
If missed statements or false findings: VERDICT: revise

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

### Variant Optimized: Haiku extract then Opus judge [MODEL:claude-haiku-4-5-20251001]

```
You are a requirements auditor performing EXTRACTION ONLY.

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
      verbatim_match: true | false
      notes: ""

Include the "Context and motivation" section.

Also produce a reverse checklist — for each RI-* item in the
inventory, verify it maps to a real source statement:

  reverse_checklist:
    - ri_id: RI-001
      source_statement: "exact text this traces to"
      source_found: true | false
      category_matches_section: true | false

CRITICAL RULES:
- Read the ACTUAL inventory file. Do NOT guess or invent RI-* IDs.
- Every ri_id in reverse_checklist MUST exist in the inventory.
- Do NOT infer, judge, or fix anything. Pure observation only.

Write ONLY the extraction_checklist and reverse_checklist.
No findings. No judgment. No recommendations.
```

[MODEL:claude-opus-4-6]

```
You are a senior requirements auditor performing judgment on a
mechanical extraction checklist.

The extraction checklist was produced by a previous prompt and is
available in the prior-artifact context above. Read it carefully.

Also read BOTH source files yourself:
  docs/requirements/raw-requirements.md
  docs/requirements/requirements-inventory.yaml

STEP 1: VERIFY THE EXTRACTION

Check the extraction_checklist:
- Does it have an entry for every requirement-bearing statement?
- Are match_status values correct? Cross-check each against the
  actual inventory.

Check the reverse_checklist:
- Does it have EXACTLY one entry per RI-* item in the inventory?
- Are ALL ri_id values real (exist in the inventory)?
- Are source_found and category_matches_section correct?

STEP 2: PRODUCE FINDINGS

For each extraction entry that is NOT fully correct, produce:

  findings:
    - source: "extraction_checklist[N]" or "reverse_checklist[N]"
      severity: critical | major | minor
      finding_type: omission | fidelity | compound | category | invention
      description: "what's wrong, specifically"
      fix: "what to change in the inventory"

Also flag any ERRORS in the extraction itself (wrong statuses,
missing entries, hallucinated IDs).
```

```
Check the judgment output:
- Are findings specific and actionable?
- Does every non-covered extraction entry have a corresponding finding?
- Are severity levels appropriate?

If judgment is thorough: VERDICT: pass
If judgment missed issues or has errors: VERDICT: revise

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```
