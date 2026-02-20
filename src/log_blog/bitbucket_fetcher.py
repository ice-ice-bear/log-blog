"""Bitbucket content fetcher using the REST API v2 (stdlib urllib, no extra deps)."""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from typing import Any

from .url_classifier import BitbucketUrl, parse_bitbucket_url

logger = logging.getLogger(__name__)

_API_BASE = "https://api.bitbucket.org/2.0"
_TIMEOUT = 15


def fetch_bitbucket_content(
    url: str, username: str, token: str
) -> dict[str, Any] | None:
    """Fetch Bitbucket repo or PR metadata via REST API v2.

    Works without credentials for public repos/PRs; private content requires
    a Bitbucket App Password (username + token).

    Returns a structured dict, or None if the URL can't be parsed or the
    API request fails.
    """
    parsed = parse_bitbucket_url(url)
    if parsed is None:
        return None

    auth = _make_auth_header(username, token)

    try:
        if parsed.pr_number is not None:
            return _fetch_pr(parsed, auth)
        return _fetch_repo(parsed, auth)
    except Exception as e:
        logger.warning("Bitbucket fetch failed for %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_auth_header(username: str, token: str) -> dict[str, str]:
    """Build a Basic-auth Authorization header if both fields are present."""
    if username and token:
        creds = base64.b64encode(f"{username}:{token}".encode()).decode()
        return {"Authorization": f"Basic {creds}"}
    return {}


def _api_get(path: str, auth: dict[str, str], raw: bool = False) -> Any:
    """GET {_API_BASE}{path}, returning parsed JSON or raw text.

    Returns None on HTTP errors or network failures.
    """
    req = urllib.request.Request(
        f"{_API_BASE}{path}",
        headers={**auth, **({} if raw else {"Accept": "application/json"})},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read()
            return body.decode("utf-8", errors="replace") if raw else json.loads(body)
    except urllib.error.HTTPError as e:
        logger.warning("Bitbucket API %s → HTTP %s", path, e.code)
        return None
    except Exception as e:
        logger.warning("Bitbucket API %s failed: %s", path, e)
        return None


def _fetch_readme(workspace: str, slug: str, auth: dict[str, str]) -> str:
    """Try common README filenames via the /src/HEAD/ endpoint."""
    for name in ("README.md", "readme.md", "README.rst", "README.txt", "README"):
        content = _api_get(f"/repositories/{workspace}/{slug}/src/HEAD/{name}", auth, raw=True)
        if content:
            return content[:8000]
    return ""


def _fetch_repo(parsed: BitbucketUrl, auth: dict[str, str]) -> dict[str, Any] | None:
    ws, slug = parsed.workspace, parsed.repo_slug
    data = _api_get(f"/repositories/{ws}/{slug}", auth)
    if data is None:
        return None

    readme = _fetch_readme(ws, slug, auth)

    return {
        "type": "repo",
        "workspace": ws,
        "repo_slug": slug,
        "full_name": data.get("full_name", f"{ws}/{slug}"),
        "description": data.get("description", ""),
        "language": data.get("language", ""),
        "is_private": data.get("is_private", False),
        "size": data.get("size", 0),
        "readme": readme,
    }


def _fetch_pr(parsed: BitbucketUrl, auth: dict[str, str]) -> dict[str, Any] | None:
    ws, slug, pr_num = parsed.workspace, parsed.repo_slug, parsed.pr_number
    data = _api_get(f"/repositories/{ws}/{slug}/pullrequests/{pr_num}", auth)
    if data is None:
        return None

    diff_data = _api_get(
        f"/repositories/{ws}/{slug}/pullrequests/{pr_num}/diffstat", auth
    )

    return {
        "type": "pr",
        "workspace": ws,
        "repo_slug": slug,
        "pr_number": pr_num,
        "title": data.get("title", ""),
        "state": data.get("state", ""),
        "description": (data.get("description") or "")[:3000],
        "source_branch": (data.get("source") or {}).get("branch", {}).get("name", ""),
        "destination_branch": (data.get("destination") or {}).get("branch", {}).get("name", ""),
        "author": (data.get("author") or {}).get("display_name", ""),
        "diff_stats": diff_data,
    }
