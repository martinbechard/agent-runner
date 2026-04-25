"""Allow python -m backlog_runner to invoke the CLI."""

from __future__ import annotations

from backlog_runner.cli import main

raise SystemExit(main())
