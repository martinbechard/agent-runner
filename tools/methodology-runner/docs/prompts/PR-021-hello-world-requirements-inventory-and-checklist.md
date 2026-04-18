### Module

requirements-inventory

## Prompt 1: Generate Or Revise Requirements Inventory And Checklist

### Required Files

{{request_path}}

### Checks Files

work/{{artifact_prefix}}.yaml
work/{{artifact_prefix}}-traceability.yaml
work/{{artifact_prefix}}-corrections.yaml

### Generation Prompt

Read and follow:
- `.methodology/docs/M-001-phase-processing-unit-schema.md`

Task:
Generate the requirements inventory and checklist.

Inputs to read:
- `{{request_path}}`
- If they exist, also read:
  - `work/{{artifact_prefix}}.yaml`
  - `work/{{artifact_prefix}}-traceability.yaml`
  - `work/{{artifact_prefix}}-corrections.yaml`

Output files to create:
- `work/{{artifact_prefix}}.yaml`
- `work/{{artifact_prefix}}-traceability.yaml`
- `work/{{artifact_prefix}}-checklist.yaml`

Requirements:
- If `work/{{artifact_prefix}}-corrections.yaml` exists and both artifact files already exist, do not regenerate the artifacts from scratch.
- In that case, treat this as a revision pass:
  - read the existing artifacts
  - read the correction items
  - apply the required corrections to the existing artifacts in place
  - preserve all unaffected content
- Corrections are subordinate to the raw request in `{{request_path}}`.
- If a correction item conflicts with the raw request, do not apply that correction.
- Do not let a correction override the grounding rules below.
- Valid corrections restore fidelity to the raw request or fix structural/traceability problems.
- Invalid corrections introduce new meaning or replace what the raw request actually says.
- If `work/{{artifact_prefix}}-corrections.yaml` exists with `status: "no_corrections_needed"`, stop immediately because there are no corrections to apply.
- In that case:
  - do not modify any artifact file
  - do not rewrite the checklist
  - do not create any new file
  - return a short chat message that the step failed because there were no corrections to apply
- If the artifact files do not already exist, generate them from scratch.
- In this step, do not read, run, or rely on any local validator, helper script, or other repository script.
- Produce a flat requirements inventory in valid YAML.
- Write `work/{{artifact_prefix}}.yaml` with exactly one top-level key: `inventory_items`.
- Each inventory item must use exactly these keys: `id`, `source_ref`, `source_sentence`, `requirement`.
- Preserve source meaning without adding interpretation.
- Split compound statements into atomic RI items.
- Include exact source grounding for each RI item.
- `source_sentence` must be the complete source sentence from which the RI item is translated.
- If multiple RI items are derived from the same source sentence, repeat that exact `source_sentence` value on each of them.
- Do not use a partial quote when the source is unstructured text.
- Use sequential `RI-*` IDs.
- Create a separate valid YAML traceability mapping file.
- Write `work/{{artifact_prefix}}-traceability.yaml` with exactly one top-level key: `traceability`.
- Each traceability entry must use exactly these keys: `ri_id`, `source_ref`, `artifact_element_ref`.
- In `work/{{artifact_prefix}}-traceability.yaml`, every `artifact_element_ref` must point to `work/{{artifact_prefix}}.yaml`, not to `docs/requirements/...`.
- In `work/{{artifact_prefix}}-traceability.yaml`, every `source_ref` must point to `{{request_path}}`.
- In `work/{{artifact_prefix}}-traceability.yaml`, every `ri_id` must match exactly one inventory item `id`.
- In `work/{{artifact_prefix}}-traceability.yaml`, every `artifact_element_ref` must use this form: `work/{{artifact_prefix}}.yaml#$.inventory_items[N]`.
- Do not add requirements not grounded in the source request.
- After the inventory and traceability artifacts exist in their final revised state for this pass, generate the checklist.
- Write `work/{{artifact_prefix}}-checklist.yaml` as valid YAML with exactly one top-level key: `checklist_items`.
- Each checklist item must use exactly these keys: `id`, `source_ref`, `criterion`, `verification_method`.
- Use `CL-RI-*` IDs.
- Ground every checklist item in `{{request_path}}`.
- Use the generated inventory and traceability files to define checks against the artifact that now exists.
- Each `criterion` must be a single YAML string value, not a nested object and not free-form prose around the YAML.
- Keep each criterion concrete, atomic, and directly judgeable.
- Allowed verification methods: `schema_inspection`, `behavioral_trace`, `content_match`, `coverage_query`, `manual_review`.
- Do not judge the artifact.
- Do not judge the checklist.
- Output only the artifact content, traceability content, and checklist content needed for the three target files.
- Do not use any methodology file other than the schema reference above.

Required checklist shape:

```yaml
checklist_items:
  - id: "CL-RI-001"
    source_ref: "{{request_path}}#L1-L3"
    criterion: "Concrete pass/fail statement."
    verification_method: "content_match"
```

Required inventory shape:

```yaml
inventory_items:
  - id: "RI-001"
    source_ref: "{{request_path}}#L3-L4"
    source_sentence: "Complete source sentence."
    requirement: "Concrete atomic requirement."
```

Required traceability shape:

```yaml
traceability:
  - ri_id: "RI-001"
    source_ref: "{{request_path}}#L3-L4"
    artifact_element_ref: "work/{{artifact_prefix}}.yaml#$.inventory_items[0]"
```

### Validation Prompt

Task:
Validate the generated requirements inventory artifacts

You must validate the artifact set and provide correction instructions if the artifact set is inadequate.

For this step, the validation scope includes both:

- `work/{{artifact_prefix}}.yaml`
- `work/{{artifact_prefix}}-traceability.yaml`

Treat those two files together as the artifact set being validated.

Strictly follow these instructions:

Inputs to read:

- `{{request_path}}`

Inputs to read if they exist:

- `work/{{artifact_prefix}}.yaml`
- `work/{{artifact_prefix}}-traceability.yaml`
- `work/{{artifact_prefix}}-checklist.yaml`

Process:

1. run the deterministic mechanical checks script (without reading it): `python work/requirements_inventory_mechanical_validate.py work {{request_path}} {{artifact_prefix}}`
2. Read only the pass/fail result from `work/{{artifact_prefix}}-mechanical-validation.yaml`

- If the script fails to run, or the report file is missing or unreadable, do not stop.
- In that case, treat `mechanical_pass` as `fail`, continue with semantic validation of the artifact set, and still write both required output files.

3. perform semantic review only; do not manually re-check anything the mechanical validator decides
4. write the corrections needed, or write `no_corrections_needed`
5. write the overall pass/fail result

Output files to create:

- `work/{{artifact_prefix}}-validation.yaml`
- `work/{{artifact_prefix}}-corrections.yaml`

Requirements:

- Follow these instructions strictly.
- Use `work/{{artifact_prefix}}-checklist.yaml` as the source of truth for what must be checked.
- Use this prompt only to define the validation process, output formats, and conflict-resolution rules.
- If this prompt and `work/{{artifact_prefix}}-checklist.yaml` appear to disagree about checklist content, treat the checklist as authoritative for checklist content and treat the prompt as authoritative for process and output structure.
- Validate the generated artifact set against the checklist.
- Validate both the inventory artifact and its traceability artifact as one artifact set for this step.
- Use the mechanical pass/fail output as authoritative for deterministic checks such as exact source_sentence matching, source coverage, ID formats, source_ref formats, one-to-one traceability, and artifact path correctness.
- Read the mechanical output only to determine whether the mechanically decidable checks passed or failed.
- If the mechanical output is present and readable, trust its pass/fail result for mechanically decidable checks.
- Perform only the remaining semantic and non-mechanical checks that are not already decided by the mechanical report.
- The semantic and non-mechanical checks are:
  - silent omissions
  - invented content
  - compound items that are not truly atomic
  - lost nuance from the raw request
  - category mismatches between the request and the resulting inventory items
- For semantic checks:
  - Paraphrase is allowed.
  - Splitting a compound request statement into multiple atomic inventory items is allowed.
  - Restating the request in clearer declarative form is allowed.
  - Fail only when the inventory introduces new substance: a capability, constraint, assumption, or success condition that is not grounded in the request.
  - Do not treat semantic deduplication as acceptable in this requirements inventory step.
  - If the raw request contains two distinct requirement-bearing statements, represent them as separate RI items even if they restate the same idea.
  - This includes Definition of Done statements that restate earlier requirements.
  - Traceability alone does not justify collapsing multiple source statements into one RI item.
- Do not rewrite the checklist.
- Do not generate or modify the inventory artifact in this step.
- Do not create any additional analysis files.
- Keep the workflow compact. The only outputs from this step are the validation file and the corrections file.

Validation output requirements:

- Write `work/{{artifact_prefix}}-validation.yaml` with exactly one top-level key: `validation_result`.
- Use this structure:

```yaml
validation_result:
  overall_status: "pass"
  mechanical_pass: "pass"
  semantic_pass: "pass"
  summary: ""
```

- `overall_status` must be `pass` or `fail`.
- `mechanical_pass` must be `pass` or `fail`.
- `mechanical_pass` means whether the mechanical step completed successfully and produced a usable report whose mechanically decidable results pass.
- `semantic_pass` must be `pass` or `fail`.
- `semantic_pass` means whether the remaining semantic and non-mechanical review passes.
- Set `overall_status` to `pass` only if both:
  - `mechanical_pass` is `pass`
  - `semantic_pass` is `pass`
- Otherwise set `overall_status` to `fail`.
- If the mechanical script fails to run, or no usable mechanical report is available, set `mechanical_pass` to `fail`.
- If the mechanical report shows any failed mechanically decidable check, set `mechanical_pass` to `fail`.
- Set `semantic_pass` from the semantic and non-mechanical review only.
- Set `overall_status` to `fail` if any required correction is needed in either:
  - `work/{{artifact_prefix}}.yaml`
  - `work/{{artifact_prefix}}-traceability.yaml`
- `summary` must be short and direct.
- Do not include validator-defect analysis in this file.

Corrections output requirements:

- Write `work/{{artifact_prefix}}-corrections.yaml` with exactly one top-level key: `corrections`.
- Use this structure when corrections are needed:

```yaml
corrections:
  status: "corrections_needed"
  items:
    - id: "COR-001"
      target_file: "work/{{artifact_prefix}}.yaml"
      target_ref: "$.inventory_items[0]"
      problem: ""
      required_change: ""
      reason: ""
```

- Use this structure when no corrections are needed:

```yaml
corrections:
  status: "no_corrections_needed"
  items: []
```

- `status` must be either `corrections_needed` or `no_corrections_needed`.
- This file is only for required changes to the artifact set being validated.
- Every correction item must be concrete enough that a later pass can update the artifact directly.
- Prefer corrections that point to an existing artifact location:
  - `work/{{artifact_prefix}}.yaml`
  - `work/{{artifact_prefix}}-traceability.yaml`
- `target_ref` should be a precise YAML path when possible.
- If no exact YAML path exists yet, use the closest stable insertion point or a short precise locator string. Do not invent a nonexistent YAML path.
- `problem` must describe what is wrong.
- `required_change` must describe exactly what to change.
- `reason` must explain why the change is required, preferably citing the relevant checklist item or semantic review concern.
- If the artifact set passes, write `no_corrections_needed` and do not invent improvement suggestions.

Output discipline:

- Output only valid YAML into the two output files.
- A short completion note in chat is allowed.
- Do not echo the full mechanical report.
- Do not narrate routine steps.
- If not blocked, give at most a short completion note stating:
  - output files written
  - overall status
  - whether corrections are needed
