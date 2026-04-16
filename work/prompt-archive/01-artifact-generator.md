Task:
Generate the PH-000 requirements inventory for the Hello World example.

Inputs to read:
- `docs/requests/hello-world-python-app.md`
- Read `work/requirements-inventory.yaml`, `work/requirements-inventory-traceability.yaml`, and `work/requirements-inventory-corrections.yaml` only if all three exist and this is clearly a revision pass.

Output files to create:
- `work/requirements-inventory.yaml`
- `work/requirements-inventory-traceability.yaml`

Requirements:
- Follow these instructions strictly.
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
- If `work/requirements-inventory-corrections.yaml` exists with `status: "no_corrections_needed"`, leave the existing artifacts unchanged.
- If the artifact files do not already exist, generate them from scratch.
- Do not read or use other local scripts, validators, or reference files during this step.
- Produce a flat requirements inventory in valid YAML.
- Preserve source meaning without adding interpretation.
- Split compound statements into atomic RI items.
- Include source grounding and verbatim support for each RI item.
- Use sequential `RI-*` IDs.
- Create a separate valid YAML traceability mapping file.
- In `work/requirements-inventory-traceability.yaml`, every
  `artifact_element_ref` must point to `work/requirements-inventory.yaml`,
  not to `docs/requirements/...`.
- In `work/requirements-inventory-traceability.yaml`, every
  `input_source_ref` must point to the real raw input file
  `docs/requests/hello-world-python-app.md`.
- Do not add requirements not grounded in the source request.
- Do not judge the artifact.
- Output only the artifact content and traceability content needed for the two target files.
