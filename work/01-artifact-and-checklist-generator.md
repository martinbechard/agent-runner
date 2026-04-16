Read and follow:
- `docs/methodology/M-001-phase-processing-unit-schema.md`

Task:
Generate the requirements inventory and checklist for the Hello World example.

Inputs to read:
- `docs/requests/hello-world-python-app.md`
- If they exist, also read:
  - `work/requirements-inventory.yaml`
  - `work/requirements-inventory-traceability.yaml`
  - `work/requirements-inventory-corrections.yaml`

Output files to create:
- `work/requirements-inventory.yaml`
- `work/requirements-inventory-traceability.yaml`
- `work/requirements-inventory-checklist.yaml`

Requirements:
- If `work/requirements-inventory-corrections.yaml` exists and both artifact files already exist, do not regenerate the artifacts from scratch.
- In that case, treat this as a revision pass:
  - read the existing artifacts
  - read the correction items
  - apply the required corrections to the existing artifacts in place
  - preserve all unaffected content
- Corrections are subordinate to the raw request in `docs/requests/hello-world-python-app.md`.
- If a correction item conflicts with the raw request, do not apply that correction.
- Do not let a correction override the grounding rules below.
- Valid corrections restore fidelity to the raw request or fix structural/traceability problems.
- Invalid corrections introduce new meaning or replace what the raw request actually says.
- If `work/requirements-inventory-corrections.yaml` exists with `status: "no_corrections_needed"`, stop immediately because there are no corrections to apply.
- In that case:
  - do not modify any artifact file
  - do not rewrite the checklist
  - do not create any new file
  - return a short chat message that the step failed because there were no corrections to apply
- If the artifact files do not already exist, generate them from scratch.
- In this step, do not read, run, or rely on any local validator, helper script, or other repository script.
- Produce a flat requirements inventory in valid YAML.
- Write `work/requirements-inventory.yaml` with exactly one top-level key: `inventory_items`.
- Each inventory item must use exactly these keys: `id`, `source_ref`, `source_sentence`, `requirement`.
- Preserve source meaning without adding interpretation.
- Split compound statements into atomic RI items.
- Include exact source grounding for each RI item.
- `source_sentence` must be the complete source sentence from which the RI item is translated.
- If multiple RI items are derived from the same source sentence, repeat that exact `source_sentence` value on each of them.
- Do not use a partial quote when the source is unstructured text.
- Use sequential `RI-*` IDs.
- Create a separate valid YAML traceability mapping file.
- Write `work/requirements-inventory-traceability.yaml` with exactly one top-level key: `traceability`.
- Each traceability entry must use exactly these keys: `ri_id`, `source_ref`, `artifact_element_ref`.
- In `work/requirements-inventory-traceability.yaml`, every `artifact_element_ref` must point to `work/requirements-inventory.yaml`, not to `docs/requirements/...`.
- In `work/requirements-inventory-traceability.yaml`, every `source_ref` must point to `docs/requests/hello-world-python-app.md`.
- In `work/requirements-inventory-traceability.yaml`, every `ri_id` must match exactly one inventory item `id`.
- In `work/requirements-inventory-traceability.yaml`, every `artifact_element_ref` must use this form: `work/requirements-inventory.yaml#$.inventory_items[N]`.
- Do not add requirements not grounded in the source request.
- After the inventory and traceability artifacts exist in their final revised state for this pass, generate the checklist.
- Write `work/requirements-inventory-checklist.yaml` as valid YAML with exactly one top-level key: `checklist_items`.
- Each checklist item must use exactly these keys: `id`, `source_ref`, `criterion`, `verification_method`.
- Use `CL-RI-*` IDs.
- Ground every checklist item in `docs/requests/hello-world-python-app.md`.
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
    source_ref: "docs/requests/hello-world-python-app.md#L1-L3"
    criterion: "Concrete pass/fail statement."
    verification_method: "content_match"
```

Required inventory shape:

```yaml
inventory_items:
  - id: "RI-001"
    source_ref: "docs/requests/hello-world-python-app.md#L3-L4"
    source_sentence: "Complete source sentence."
    requirement: "Concrete atomic requirement."
```

Required traceability shape:

```yaml
traceability:
  - ri_id: "RI-001"
    source_ref: "docs/requests/hello-world-python-app.md#L3-L4"
    artifact_element_ref: "work/requirements-inventory.yaml#$.inventory_items[0]"
```
