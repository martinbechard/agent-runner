Read and follow:
- `docs/methodology/M-001-phase-processing-unit-schema.md`

Task:
Validate the generated PH-000 requirements inventory artifact for the Hello World example using a two-stage process:
1. run the deterministic mechanical pass
2. complete the remaining validation work yourself, including the higher-level review checks normally reserved for judgment

Inputs to read:
- `docs/requests/hello-world-python-app.md`
- `work/requirements-inventory.yaml`
- `work/requirements-inventory-traceability.yaml`
- `work/requirements-inventory-checklist.yaml`
- `work/requirements_inventory_mechanical_validate.py`

Required intermediate step:
- Run `python work/requirements_inventory_mechanical_validate.py`
- Read `work/requirements-inventory-mechanical-validation.yaml`

Output file to create:
- `work/requirements-inventory-validation.yaml`
- `work/requirements-inventory-validation-complement.yaml`

Requirements:
- Validate the generated artifact against the checklist, not the checklist itself.
- Use the mechanical report for deterministic checks such as exact strings, counts, ID formats, source_ref formats, one-to-one traceability, and artifact path correctness.
- Do not re-do deterministic checks manually unless the mechanical output appears incorrect.
- Start from the contents of `work/requirements-inventory-mechanical-validation.yaml`.
- Transform `work/requirements-inventory-mechanical-validation.yaml` into the final `validation_result` schema once at the start.
- Copy mechanical results forward unchanged for every checklist item already covered there, unless you detect a specific error in the mechanical report.
- Only add or modify checklist results for items that were left unchecked by the mechanical pass, or for a concrete mechanical-report error you can explain in `details`.
- Do not regenerate the whole validation result from scratch.
- Create `work/requirements-inventory-validation.yaml` by transforming the mechanical report into the final report shape once, then update that file in place.
- When doing that initial transform, drop mechanical-only wrapper fields such as `notes` and `unchecked_checklist_item_ids`. They do not belong in the final schema.
- If a note, correction, or semantic completion is needed, edit the existing `work/requirements-inventory-validation.yaml` file in place with a tool such as `sed`, `perl`, or another deterministic file-editing command.
- Do not rewrite already-present checklist results just to restate them in a new file body.
- Normal editing after the initial transform is allowed. The rule is about avoiding full-file regeneration, not about forbidding ordinary edits.
- The intended sequence is: create the file from the mechanical report once, then make only targeted in-place edits.
- Also write `work/requirements-inventory-validation-complement.yaml` containing only the non-mechanical additions and corrections beyond the mechanical pass.
- Complete the remaining non-mechanical review yourself.
- In addition to checklist conformance, perform the higher-level artifact review checks:
  - Check for silent omissions.
  - Check for invented content.
  - Check for compound items that are not truly atomic.
  - Check for lost nuance from the raw request.
  - Check for category mismatches between the request and the resulting inventory items.
- If one of those higher-level review checks reveals a problem already covered by a checklist item, record it in that checklist item's `details` and mark the item `fail`.
- If one of those higher-level review checks reveals a real artifact problem that does not map cleanly to any checklist item, record it in `uncovered_concerns`.
- For semantic checks such as `CL-RI-014`:
  - Paraphrase is allowed.
  - Splitting a compound request statement into multiple atomic inventory items is allowed.
  - Restating the request in clearer declarative form is allowed.
  - Fail only when the inventory introduces new substance: a capability, constraint, assumption, or success condition that is not grounded in the request.
- Use binary checklist result statuses only: `pass` or `fail`.
- `artifact_locations` may cite locations in either `work/requirements-inventory.yaml` or `work/requirements-inventory-traceability.yaml`.
- Keep `uncovered_concerns` empty unless you find a real artifact problem that does not map cleanly to any checklist item.
- Do not use `uncovered_concerns` to restate checklist failures.
- Return valid YAML with exactly one top-level key: `validation_result`.
- Use this structure:

```yaml
validation_result:
  overall_status: "pass"
  checklist_results:
    - checklist_item_id: "CL-RI-001"
      status: "pass"
      details: ""
      artifact_locations: []
  failed_item_ids: []
  uncovered_concerns: []
```

- If any checklist item fails, set `overall_status` to `fail` and include the failed item IDs in `failed_item_ids`.
- If all checklist items pass but `uncovered_concerns` is non-empty, set `overall_status` to `fail`.
- Use this complement structure:

```yaml
complement:
  manually_completed_items:
    - checklist_item_id: "CL-RI-014"
      status: "pass"
      details: ""
      artifact_locations: []
  corrected_mechanical_items:
    - checklist_item_id: "CL-RI-010"
      reason: ""
      updated_artifact_locations: []
  uncovered_concerns: []
```

- `manually_completed_items` is for checklist items left unchecked by the mechanical pass.
- `corrected_mechanical_items` is for specific fixes to mechanically generated results.
- Record in `complement.uncovered_concerns` only the higher-level review concerns you added beyond the mechanical pass.
- Do not copy already-correct mechanical results into the complement file.
- Do not rewrite the checklist.
- Do not generate or modify the inventory artifact.
- Output only valid YAML.
- The file content must be valid YAML. A short completion note in chat is allowed, but do not print non-YAML content into the output file.
- Keep chat output compact:
  - Do not echo or restate the full mechanical validation report.
  - Do not narrate routine steps such as reading files, running the mechanical script, or validating YAML parse success.
  - Ask questions only if truly blocked.
  - If not blocked, give at most a short completion note stating: output files written, overall status, and only the checklist items or uncovered concerns recorded in the complement file.
- Do not use any methodology file other than the schema reference above.
