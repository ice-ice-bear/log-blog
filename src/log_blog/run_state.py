"""Track last-run timestamp for --since-last-run flag."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATE_FILENAME = ".log-blog-state.json"


def _state_path(project_root: Path | None = None) -> Path:
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / STATE_FILENAME


def load_last_run(project_root: Path | None = None) -> str | None:
    """Return ISO 8601 timestamp of last run, or None if never run."""
    path = _state_path(project_root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data.get("last_run")
    except (json.JSONDecodeError, OSError):
        return None


def save_last_run(project_root: Path | None = None) -> None:
    """Write current UTC timestamp as last_run."""
    path = _state_path(project_root)
    data = {"last_run": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(data, indent=2) + "\n")


def hours_since_last_run(project_root: Path | None = None) -> int | None:
    """Return hours since last run, rounded up. None if never run."""
    last = load_last_run(project_root)
    if not last:
        return None
    try:
        last_dt = datetime.fromisoformat(last)
        delta = datetime.now(timezone.utc) - last_dt
        return max(1, int(delta.total_seconds() / 3600) + 1)
    except ValueError:
        return None
