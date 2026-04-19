from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_app_prints_hello_world() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repo_root / "app.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "Hello, world!\n"
