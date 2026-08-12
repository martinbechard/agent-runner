# Modularize the Report Tool for Concurrent Maintenance

## Synopsis

Decompose the report tool's monolithic implementation and regression test file
into cohesive, independently maintainable modules while preserving existing
report behavior, command-line compatibility, privacy safeguards, and output
formats.

## Rationale

The report implementation is concentrated in
`tools/report/scripts/run-timeline.py` (approximately 7,900 lines), while its
regression coverage is concentrated in
`tools/report/tests/test_run_timeline.py` (approximately 2,700 lines). The
repository claim mechanism coordinates ownership at file-path granularity, so
otherwise independent report changes repeatedly contend for these same two
files.

Claim-log analysis on July 14 and 15, 2026 found that 34 of 39 successful July
14 claims and 21 of 22 successful July 15 claims touched both hot files. The
observed contention included waits of approximately 15 minutes 45 seconds and
3 minutes 58 seconds between report tasks.

This is a project-only structural change. It must be implemented incrementally
and conservatively because the report tool handles multiple input formats,
privacy-sensitive disclosure rules, lifecycle reconstruction, pricing and
token calculations, and HTML, Markdown, JSON, and CSV output.

## Notes

### Possible Requirements

- Identify cohesive module boundaries from current responsibilities and call
  relationships before moving code.
- Preserve `tools/report/scripts/run-timeline.py` as the supported command-line
  entry point and preserve its existing CLI arguments and exit behavior.
- Extract implementation in small, reviewable stages rather than performing a
  single large rewrite.
- Split regression tests along the same responsibility boundaries so future
  changes do not routinely require ownership of one global test file.
- Add characterization coverage before extracting behavior that is not already
  protected by focused tests.
- Preserve secret redaction, bounded previews, encrypted-content handling, and
  all other privacy guarantees.
- Preserve supported Codex, Junie, prompt-runner, methodology-runner, live,
  sealed, and normalized-report workflows.
- Preserve JSON, turn CSV, work-unit CSV, Markdown, and HTML schemas and
  semantics unless an output change is separately approved and documented.
- Document the resulting module boundaries and the intended location of new
  tests in `tools/report/README.md`.
- Keep each extraction commit independently testable and suitable for rollback.

### Possible Acceptance Criteria

- The report entry point continues to support every command documented in
  `tools/report/README.md` without requiring callers to import a new module or
  invoke a new script.
- Report parsing, normalization, calculations, privacy filtering, and output
  rendering are divided into cohesive implementation modules with matching
  focused test modules.
- Representative changes in at least two independent report concerns can be
  implemented and tested using disjoint file claims.
- Existing fixtures produce behaviorally equivalent normalized JSON, CSV,
  Markdown, and HTML output. Any intentional byte-level difference is reviewed
  and recorded before acceptance.
- Privacy and encrypted-content regression tests pass without weakening or
  deleting assertions.
- No extraction stage leaves duplicate authorities, circular imports, or a
  compatibility shim that contains substantial business logic.
- The full report regression suite and the repository's applicable test suite
  pass after the final extraction.

### Dependencies

None. The implementer should nevertheless coordinate with active report-tool
claims before starting because this work necessarily touches the current hot
files during extraction.

### Possible Verification

- Run `pytest -q tools/report/tests/test_run_timeline.py` before the first
  extraction to establish a clean baseline.
- Add and run focused tests for each extracted module during every stage.
- Run the complete report test directory with `pytest -q tools/report/tests`.
- Exercise the documented Codex and Junie report commands against stable
  fixtures or sealed inputs and compare every generated companion format.
- Review generated HTML manually for layout and drill-down regressions.
- Verify that secret-redaction, bounded-preview, encrypted-message, lifecycle,
  pricing, and token-accounting tests remain present and passing.
- Run `git diff --check` before delivery.

### Additional Notes

- Exact module names and extraction order should follow a fresh dependency and
  execution-path analysis; they are intentionally not prescribed here.
- This item addresses project structure and file-level claim contention. It
  does not change the shared claim skill or introduce sub-file locking.
- Unknown future change scope remains expected. The goal is to provide enough
  cohesive boundaries that scope can be expanded to another leaf module when
  needed instead of defaulting to the entire report implementation and test
  corpus.

## Revisit Trigger

Revisit when report-tool changes are again blocked by overlapping file claims
or when maintainers deliberately schedule a modularization initiative.
