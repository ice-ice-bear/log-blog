"""Extract and decrypt Chrome cookies from a local profile for Playwright injection.

macOS only: Chrome encrypts cookie values with AES-128-CBC using a key stored in
the system Keychain under 'Chrome Safe Storage'. This module reads the raw SQLite
cookie database, decrypts the values, and returns cookies in a format that
Playwright's context.add_cookies() accepts.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_CHROME_EPOCH_OFFSET = 11_644_473_600  # seconds between 1601-01-01 and 1970-01-01


def get_chrome_cookies_for_url(profile_path: Path, domain: str) -> list[dict]:
    """Return decrypted Chrome cookies for a domain, ready for Playwright injection.

    Args:
        profile_path: Path to the Chrome profile directory (e.g. ~/...Chrome/Default).
        domain:       The host to filter cookies for (e.g. "perplexity.ai").

    Returns:
        List of Playwright-compatible cookie dicts. Empty list on any failure.
    """
    if sys.platform != "darwin":
        logger.warning("Cookie extraction is only supported on macOS; skipping auth cookies")
        return []

    cookies_db = profile_path / "Cookies"
    if not cookies_db.exists():
        logger.warning("Cookies DB not found at %s", cookies_db)
        return []

    aes_key = _derive_aes_key()
    if aes_key is None:
        logger.warning("Could not get Chrome Safe Storage key from Keychain; falling back to no auth")
        return []

    return _read_cookies(cookies_db, domain, aes_key)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_keychain_password() -> bytes | None:
    """Retrieve Chrome's master password from macOS Keychain via security CLI."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password",
             "-a", "Chrome", "-s", "Chrome Safe Storage", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().encode("utf-8")
    except Exception as e:
        logger.warning("Keychain lookup failed: %s", e)
    return None


def _derive_aes_key(password: bytes | None = None) -> bytes | None:
    """Derive a 16-byte AES key from Chrome's Keychain password using PBKDF2-SHA1."""
    import hashlib
    if password is None:
        password = _get_keychain_password()
    if password is None:
        return None
    return hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1003, dklen=16)


def _decrypt_value(encrypted: bytes, key: bytes) -> str:
    """Decrypt a single AES-128-CBC encrypted cookie value (v10 Chrome format)."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    # Chrome v80+ prefixes with b'v10', strip it
    if encrypted[:3] == b"v10":
        encrypted = encrypted[3:]

    if not encrypted:
        return ""

    iv = b" " * 16  # Chrome uses 16 space characters as the IV
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted) + decryptor.finalize()

    # Remove PKCS7 padding
    pad_len = decrypted[-1]
    if pad_len > 16:
        return ""
    return decrypted[:-pad_len].decode("utf-8", errors="replace")


def _chrome_expiry_to_unix(expiry: int) -> float:
    """Convert Chrome cookie expiry (microseconds since 1601) to Unix timestamp."""
    if expiry == 0:
        return 0.0
    return expiry / 1_000_000 - _CHROME_EPOCH_OFFSET


def _read_cookies(cookies_db: Path, domain: str, aes_key: bytes) -> list[dict]:
    """Read and decrypt matching cookies from the Chrome Cookies SQLite database."""
    # Copy DB to temp file to avoid lock issues (Chrome may be running)
    tmp = tempfile.mktemp(suffix=".db")
    try:
        shutil.copy2(cookies_db, tmp)
        conn = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        cursor = conn.execute(
            """
            SELECT host_key, name, encrypted_value, path, expires_utc, is_secure, is_httponly
            FROM cookies
            WHERE host_key LIKE ?
            """,
            (f"%{domain}",),
        )

        results: list[dict] = []
        for host_key, name, encrypted_value, path, expires_utc, is_secure, is_httponly in cursor:
            try:
                value = _decrypt_value(encrypted_value, aes_key) if encrypted_value else ""
            except Exception:
                value = ""

            if not value:
                continue

            cookie: dict = {
                "name": name,
                "value": value,
                "domain": host_key,
                "path": path or "/",
                "secure": bool(is_secure),
                "httpOnly": bool(is_httponly),
            }
            expiry = _chrome_expiry_to_unix(expires_utc)
            if expiry > 0:
                cookie["expires"] = expiry

            results.append(cookie)

        conn.close()
        logger.info("Extracted %d cookies for %s", len(results), domain)
        return results

    except Exception as e:
        logger.warning("Cookie extraction failed: %s", e)
        return []
    finally:
        Path(tmp).unlink(missing_ok=True)
