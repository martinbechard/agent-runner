# report

`tools/report/` holds cross-tool reporting utilities for this repository.

Current contents:

- `scripts/run-timeline.py`
  - generates an HTML timeline report from a `prompt-runner` run directory or
    a `methodology-runner` workspace
- `tests/`
  - regression tests and fixtures for the report script

Run the timeline tool directly from the checkout:

```bash
python tools/report/scripts/run-timeline.py <path> [--output report.html]
```

Run its tests:

```bash
pytest -q tools/report/tests/test_run_timeline.py
```
