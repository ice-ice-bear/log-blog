from __future__ import annotations

import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .config import Config

# Chrome stores timestamps as microseconds since 1601-01-01
_CHROME_EPOCH_OFFSET = 11644473600
_CHROME_MICRO = 1_000_000

# URL prefixes to filter out
_IGNORED_PREFIXES = (
    "chrome://",
    "chrome-extension://",
    "chrome-native://",
    "about:",
    "data:",
    "blob:",
    "javascript:",
    "file://",
    "devtools://",
    "edge://",
)


@dataclass
class HistoryEntry:
    url: str
    title: str
    visit_count: int
    last_visit_time: float  # Unix timestamp

    @property
    def last_visit_iso(self) -> str:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self.last_visit_time, tz=timezone.utc).isoformat()


def _chrome_time_to_unix(chrome_time: int) -> float:
    """Convert Chrome timestamp (microseconds since 1601-01-01) to Unix timestamp."""
    return chrome_time / _CHROME_MICRO - _CHROME_EPOCH_OFFSET


def _copy_history_db(db_path: Path) -> Path:
    """Copy the Chrome History DB to a temp file to avoid lock issues."""
    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy2(db_path, tmp)
    return Path(tmp)


def read_history(config: Config) -> list[HistoryEntry]:
    """Read Chrome browsing history for the configured time range."""
    cutoff_unix = time.time() - (config.time_range_hours * 3600)
    cutoff_chrome = int((cutoff_unix + _CHROME_EPOCH_OFFSET) * _CHROME_MICRO)

    entries: dict[str, HistoryEntry] = {}

    for profile in config.chrome.profiles:
        db_path = config.chrome.history_db_base_path / profile / "History"
        if not db_path.exists():
            continue

        tmp_db = _copy_history_db(db_path)
        try:
            conn = sqlite3.connect(f"file:{tmp_db}?mode=ro", uri=True)
            cursor = conn.execute(
                """
                SELECT url, title, visit_count, last_visit_time
                FROM urls
                WHERE last_visit_time > ?
                ORDER BY last_visit_time DESC
                """,
                (cutoff_chrome,),
            )

            for url, title, visit_count, last_visit_time in cursor:
                if any(url.startswith(prefix) for prefix in _IGNORED_PREFIXES):
                    continue
                if url not in entries:
                    entries[url] = HistoryEntry(
                        url=url,
                        title=title or "",
                        visit_count=visit_count,
                        last_visit_time=_chrome_time_to_unix(last_visit_time),
                    )

            conn.close()
        finally:
            tmp_db.unlink(missing_ok=True)

    # Sort by visit time descending
    return sorted(entries.values(), key=lambda e: e.last_visit_time, reverse=True)
