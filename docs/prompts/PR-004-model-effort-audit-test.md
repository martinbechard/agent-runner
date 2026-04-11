# PR-004 — Model & effort level comparison for audit

Cross-model and cross-effort test of the two-pass checklist audit
(Variant B from PR-003). Tests whether cheaper/faster models and
lower effort levels can handle extraction and judgment without
quality loss.

**How to run:**

```
prompt-runner run docs/prompts/PR-004-model-effort-audit-test.md \
  --project-dir /tmp/test-ph001-workspace-3 \
  --variant-sequential
```

The workspace must already contain completed PH-000 output
(requirements-inventory.yaml + raw-requirements.md).

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

## Prompt 2: Two-pass checklist audit [VARIANTS]

### Variant B-opus-high: Opus default (baseline)

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

### Variant B-sonnet-high: Sonnet default [MODEL:claude-sonnet-4-6]

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

### Variant B-haiku-high: Haiku default [MODEL:claude-haiku-4-5-20251001]

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

### Variant B-opus-medium: Opus medium effort [EFFORT:medium]

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

### Variant B-opus-low: Opus low effort [EFFORT:low]

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

### Variant B-sonnet-medium: Sonnet medium effort [MODEL:claude-sonnet-4-6] [EFFORT:medium]

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

