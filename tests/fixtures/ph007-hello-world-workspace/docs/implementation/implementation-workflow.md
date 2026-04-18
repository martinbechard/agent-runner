### Module
implementation-workflow

## Prompt 1: Create CLI Output Test And Runtime

### Generation Prompt

Use TDD for the CLI runtime.

Write or tighten a failing pytest that checks running `app.py` prints
`Hello, world!` to standard output. Then implement the smallest Python
runtime needed to make that test pass. Run `pytest -q` before finishing.

Files this prompt may create or update:
- `tests/test_app.py`
- `app.py`

### Validation Prompt

Review whether the CLI runtime slice followed TDD and whether the observed
project state now supports the tested `Hello, world!` behavior.

## Prompt 2: Add README Run Instructions

### Generation Prompt

Add the minimal README content needed for a human to run the application from
the command line and understand the expected output. Keep the README short and
aligned with the actual runtime behavior. Re-run `pytest -q` before finishing.

Files this prompt may create or update:
- `README.md`

### Validation Prompt

Review whether the README accurately reflects how to run the CLI runtime and
whether it stays aligned with the tested runtime behavior.

## Prompt 3: Final Verification

### Generation Prompt

Perform final verification of the assembled implementation.

Run the relevant tests and a direct CLI invocation. Confirm the implementation
still satisfies the required behavior and note any remaining gaps before
finishing.

### Validation Prompt

Review whether final verification was actually performed and whether the
implementation is ready for Phase 7 final verification reporting.
