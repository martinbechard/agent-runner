# PR-005 — Extraction-only model shootoff

Tests whether cheaper models (Sonnet, Haiku) can handle the purely
mechanical extraction step (Pass 1 only) without hallucination. The
hypothesis is that hallucination in PR-004 happened because Pass 1
and Pass 2 were combined — the model confused "observe" with "judge."

This test runs Pass 1 (extraction checklist) ONLY, with no judgment
step. Each variant uses a different model. The judge for ALL variants
runs at default (Opus) to provide a consistent quality check.

**How to run:**

```
prompt-runner run docs/prompts/PR-005-extraction-only-model-shootoff.md \
  --project-dir /tmp/test-ph001-workspace-3 \
  --variant-sequential
```

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

## Prompt 2: Extraction-only audit [VARIANTS]

### Variant Opus: Opus extraction [MODEL:claude-opus-4-6]

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
- If the inventory has items RI-001 through RI-018, your reverse
  checklist has exactly 18 entries. Not 19. Not 20. Exactly what
  the file contains.
- Do NOT infer, judge, or fix anything. Pure observation only.
- "covered" = at least one RI item's verbatim_quote matches.
- "partial" = RI item exists but quote doesn't match exactly.
- "missing" = no RI item corresponds to this statement.

Write ONLY the extraction_checklist and reverse_checklist.
No findings. No judgment. No recommendations.
```

```
You are verifying a purely mechanical extraction audit.

Read both source files yourself:
  docs/requirements/raw-requirements.md
  docs/requirements/requirements-inventory.yaml

Check:

1. EXTRACTION CHECKLIST:
   - Does it have an entry for every requirement-bearing statement?
   - Are match_status values correct? Cross-check a sample.

2. REVERSE CHECKLIST:
   - Does it have EXACTLY one entry per RI-* item in the inventory?
   - Count the RI-* items in the inventory file. Count the entries
     in the reverse checklist. They must match.
   - Are ALL ri_id values real (exist in the inventory)?
   - Flag any ri_id that does NOT exist in the inventory as a
     CRITICAL hallucination.

3. NO JUDGMENT LEAKAGE:
   - The output must contain ONLY extraction_checklist and
     reverse_checklist. No findings, no severity, no recommendations.
   - If judgment content leaked in, that's a failure.

If counts match and no hallucinated IDs: VERDICT: pass
If any ri_id doesn't exist in inventory: VERDICT: revise
If extraction is incomplete: VERDICT: revise

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

### Variant Sonnet: Sonnet extraction [MODEL:claude-sonnet-4-6]

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
- If the inventory has items RI-001 through RI-018, your reverse
  checklist has exactly 18 entries. Not 19. Not 20. Exactly what
  the file contains.
- Do NOT infer, judge, or fix anything. Pure observation only.
- "covered" = at least one RI item's verbatim_quote matches.
- "partial" = RI item exists but quote doesn't match exactly.
- "missing" = no RI item corresponds to this statement.

Write ONLY the extraction_checklist and reverse_checklist.
No findings. No judgment. No recommendations.
```

```
You are verifying a purely mechanical extraction audit.

Read both source files yourself:
  docs/requirements/raw-requirements.md
  docs/requirements/requirements-inventory.yaml

Check:

1. EXTRACTION CHECKLIST:
   - Does it have an entry for every requirement-bearing statement?
   - Are match_status values correct? Cross-check a sample.

2. REVERSE CHECKLIST:
   - Does it have EXACTLY one entry per RI-* item in the inventory?
   - Count the RI-* items in the inventory file. Count the entries
     in the reverse checklist. They must match.
   - Are ALL ri_id values real (exist in the inventory)?
   - Flag any ri_id that does NOT exist in the inventory as a
     CRITICAL hallucination.

3. NO JUDGMENT LEAKAGE:
   - The output must contain ONLY extraction_checklist and
     reverse_checklist. No findings, no severity, no recommendations.
   - If judgment content leaked in, that's a failure.

If counts match and no hallucinated IDs: VERDICT: pass
If any ri_id doesn't exist in inventory: VERDICT: revise
If extraction is incomplete: VERDICT: revise

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

### Variant Haiku: Haiku extraction [MODEL:claude-haiku-4-5-20251001]

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
- If the inventory has items RI-001 through RI-018, your reverse
  checklist has exactly 18 entries. Not 19. Not 20. Exactly what
  the file contains.
- Do NOT infer, judge, or fix anything. Pure observation only.
- "covered" = at least one RI item's verbatim_quote matches.
- "partial" = RI item exists but quote doesn't match exactly.
- "missing" = no RI item corresponds to this statement.

Write ONLY the extraction_checklist and reverse_checklist.
No findings. No judgment. No recommendations.
```

```
You are verifying a purely mechanical extraction audit.

Read both source files yourself:
  docs/requirements/raw-requirements.md
  docs/requirements/requirements-inventory.yaml

Check:

1. EXTRACTION CHECKLIST:
   - Does it have an entry for every requirement-bearing statement?
   - Are match_status values correct? Cross-check a sample.

2. REVERSE CHECKLIST:
   - Does it have EXACTLY one entry per RI-* item in the inventory?
   - Count the RI-* items in the inventory file. Count the entries
     in the reverse checklist. They must match.
   - Are ALL ri_id values real (exist in the inventory)?
   - Flag any ri_id that does NOT exist in the inventory as a
     CRITICAL hallucination.

3. NO JUDGMENT LEAKAGE:
   - The output must contain ONLY extraction_checklist and
     reverse_checklist. No findings, no severity, no recommendations.
   - If judgment content leaked in, that's a failure.

If counts match and no hallucinated IDs: VERDICT: pass
If any ri_id doesn't exist in inventory: VERDICT: revise
If extraction is incomplete: VERDICT: revise

VERDICT: pass
VERDICT: revise
VERDICT: escalate
```

