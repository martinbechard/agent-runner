Read and follow:
- `docs/methodology/M-001-phase-processing-unit-schema.md`

Task:
Produce the PH-000 checklist extraction output for the Hello World example.

Inputs to read:
- `docs/requests/hello-world-python-app.md`
- `work/requirements-inventory.yaml`
- `work/requirements-inventory-traceability.yaml`

Output file to create:
- `work/requirements-inventory-checklist.yaml`

Requirements:
- Write valid YAML with exactly one top-level key: `checklist_items`.
- Each checklist item must use exactly these keys: `id`, `source_ref`, `criterion`, `verification_method`.
- Use `CL-RI-*` IDs.
- Ground every checklist item in `docs/requests/hello-world-python-app.md`.
- Use the generated inventory and traceability files to define checks against the artifact that now exists.
- Each `criterion` must be a single YAML string value, not a nested object and not free-form prose around the YAML.
- Keep each criterion concrete, atomic, and directly judgeable.
- Allowed verification methods: `schema_inspection`, `behavioral_trace`, `content_match`, `coverage_query`, `manual_review`.
- Do not generate the inventory artifact.
- Do not judge the checklist.
- Output only YAML.
- Do not use any methodology file other than the schema reference above.

Required shape:

```yaml
checklist_items:
  - id: "CL-RI-001"
    source_ref: "docs/requests/hello-world-python-app.md#L1-L3"
    criterion: "Concrete pass/fail statement."
    verification_method: "content_match"
```
