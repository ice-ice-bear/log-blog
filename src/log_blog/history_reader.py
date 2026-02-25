from __future__ import annotations

import json
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
    fd = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    fd.close()
    tmp = Path(fd.name)
    shutil.copy2(db_path, tmp)
    return tmp


def list_chrome_profiles(config: Config) -> list[dict]:
    """Return all Chrome profiles with their associated Google account info.

    Reads the 'Local State' file Chrome keeps next to its profile directories.
    Each entry includes: folder, name, email, in_config (whether it's in
    config.chrome.profiles or matched by config.chrome.google_accounts).
    """
    local_state_path = config.chrome.history_db_base_path / "Local State"
    if not local_state_path.exists():
        return []

    try:
        state = json.loads(local_state_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    info_cache: dict = state.get("profile", {}).get("info_cache", {})
    active_folders = _resolve_active_profiles(config, info_cache)

    profiles = []
    for folder, info in sorted(info_cache.items()):
        profiles.append({
            "folder": folder,
            "name": info.get("name", folder),
            "email": info.get("user_name", ""),
            "active": folder in active_folders,
        })
    return profiles


def _resolve_active_profiles(config: Config, info_cache: dict) -> list[str]:
    """Resolve which Chrome profile folders to use.

    If config.chrome.google_accounts is set, returns only folders whose
    signed-in email matches. Otherwise returns config.chrome.profiles.
    """
    if not config.chrome.google_accounts:
        return config.chrome.profiles

    target = {e.lower() for e in config.chrome.google_accounts}
    matched = [
        folder for folder, info in info_cache.items()
        if info.get("user_name", "").lower() in target
    ]
    return matched if matched else config.chrome.profiles


def read_history(config: Config) -> list[HistoryEntry]:
    """Read Chrome browsing history for the configured time range."""
    cutoff_unix = time.time() - (config.time_range_hours * 3600)
    cutoff_chrome = int((cutoff_unix + _CHROME_EPOCH_OFFSET) * _CHROME_MICRO)

    entries: dict[str, HistoryEntry] = {}

    # Respect google_accounts filter if set; otherwise fall back to profiles list
    local_state_path = config.chrome.history_db_base_path / "Local State"
    if config.chrome.google_accounts and local_state_path.exists():
        try:
            state = json.loads(local_state_path.read_text(encoding="utf-8"))
            info_cache = state.get("profile", {}).get("info_cache", {})
            profiles = _resolve_active_profiles(config, info_cache)
        except Exception:
            profiles = config.chrome.profiles
    else:
        profiles = config.chrome.profiles

    for profile in profiles:
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
