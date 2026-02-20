"""GitHub content fetcher using the gh CLI."""

from __future__ import annotations

import base64
import json
import logging
import subprocess

from .url_classifier import GitHubUrl, UrlType, parse_github_url

logger = logging.getLogger(__name__)


def get_current_gh_user() -> str | None:
    """Return the currently active gh CLI username, or None on failure."""
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def switch_github_profile(profile: str) -> bool:
    """Switch the active gh CLI account to the specified profile.

    Returns True on success, False if the switch failed (fetch will still proceed
    with whatever account is currently active).
    """
    if not profile:
        return True
    logger.info("Switching gh profile to '%s'", profile)
    try:
        result = subprocess.run(
            ["gh", "auth", "switch", "--user", profile],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("gh auth switch --user %s failed: %s", profile, result.stderr[:200])
            return False
        return True
    except FileNotFoundError:
        logger.warning("gh CLI not found; cannot switch profile")
        return False
    except subprocess.TimeoutExpired:
        logger.warning("gh auth switch timed out")
        return False


def fetch_github_content(url: str, url_type: UrlType) -> dict | None:
    """Fetch GitHub content based on URL type.

    Returns a dict with structured metadata, or None on failure.
    """
    parsed = parse_github_url(url)
    if not parsed:
        return None

    try:
        if url_type == UrlType.GITHUB_REPO:
            return _fetch_repo(parsed)
        elif url_type == UrlType.GITHUB_PR:
            return _fetch_pr(parsed)
        elif url_type == UrlType.GITHUB_ISSUE:
            return _fetch_issue(parsed)
    except Exception as e:
        logger.warning("GitHub fetch failed for %s: %s", url, e)

    return None


def _run_gh(*args: str) -> str | None:
    """Run a gh CLI command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("gh %s failed: %s", " ".join(args[:3]), result.stderr[:200])
            return None
        return result.stdout
    except FileNotFoundError:
        logger.warning("gh CLI not found")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("gh command timed out")
        return None


def _fetch_repo(parsed: GitHubUrl) -> dict | None:
    """Fetch repository metadata, README, and recent commits."""
    repo_slug = f"{parsed.owner}/{parsed.repo}"

    # Repo metadata
    raw = _run_gh("api", f"repos/{repo_slug}", "--jq",
                  '{description, stargazers_count, forks_count, language, topics, html_url}')
    if not raw:
        return None
    meta = json.loads(raw)

    # README (base64-decoded, up to 8KB)
    readme_text = ""
    raw_readme = _run_gh("api", f"repos/{repo_slug}/readme", "--jq", ".content")
    if raw_readme:
        try:
            decoded = base64.b64decode(raw_readme.strip()).decode("utf-8", errors="replace")
            readme_text = decoded[:8000]
            if len(decoded) > 8000:
                readme_text += "\n\n[README truncated...]"
        except Exception:
            pass

    # Last 5 commits
    commits_raw = _run_gh("api", f"repos/{repo_slug}/commits?per_page=5", "--jq",
                          '[.[] | {sha: .sha[:7], message: .commit.message[:120]}]')
    commits = []
    if commits_raw:
        try:
            commits = json.loads(commits_raw)
        except json.JSONDecodeError:
            pass

    # Languages
    langs_raw = _run_gh("api", f"repos/{repo_slug}/languages")
    languages = {}
    if langs_raw:
        try:
            languages = json.loads(langs_raw)
        except json.JSONDecodeError:
            pass

    return {
        "type": "repo",
        "owner": parsed.owner,
        "repo": parsed.repo,
        "description": meta.get("description", ""),
        "stars": meta.get("stargazers_count", 0),
        "forks": meta.get("forks_count", 0),
        "primary_language": meta.get("language", ""),
        "topics": meta.get("topics", []),
        "languages": languages,
        "readme": readme_text,
        "recent_commits": commits,
    }


def _fetch_pr(parsed: GitHubUrl) -> dict | None:
    """Fetch pull request details."""
    if parsed.number is None:
        return None

    repo_slug = f"{parsed.owner}/{parsed.repo}"
    fields = "title,state,body,additions,deletions,changedFiles,comments,url"

    raw = _run_gh("pr", "view", str(parsed.number),
                  "--repo", repo_slug, "--json", fields)
    if not raw:
        return None

    data = json.loads(raw)

    # Truncate body
    body = (data.get("body") or "")[:3000]
    if len(data.get("body") or "") > 3000:
        body += "\n\n[Body truncated...]"

    # Extract comments (first 10, 300 chars each)
    comments = []
    for c in (data.get("comments") or [])[:10]:
        comment_body = (c.get("body") or "")[:300]
        comments.append({
            "author": c.get("author", {}).get("login", "unknown"),
            "body": comment_body,
        })

    return {
        "type": "pr",
        "owner": parsed.owner,
        "repo": parsed.repo,
        "number": parsed.number,
        "title": data.get("title", ""),
        "state": data.get("state", ""),
        "body": body,
        "additions": data.get("additions", 0),
        "deletions": data.get("deletions", 0),
        "changed_files": data.get("changedFiles", 0),
        "comments": comments,
    }


def _fetch_issue(parsed: GitHubUrl) -> dict | None:
    """Fetch issue details."""
    if parsed.number is None:
        return None

    repo_slug = f"{parsed.owner}/{parsed.repo}"
    fields = "title,state,body,labels,comments,url"

    raw = _run_gh("issue", "view", str(parsed.number),
                  "--repo", repo_slug, "--json", fields)
    if not raw:
        return None

    data = json.loads(raw)

    # Truncate body
    body = (data.get("body") or "")[:3000]
    if len(data.get("body") or "") > 3000:
        body += "\n\n[Body truncated...]"

    # Labels
    labels = [l.get("name", "") for l in (data.get("labels") or [])]

    # Comments (first 10, 300 chars each)
    comments = []
    for c in (data.get("comments") or [])[:10]:
        comment_body = (c.get("body") or "")[:300]
        comments.append({
            "author": c.get("author", {}).get("login", "unknown"),
            "body": comment_body,
        })

    return {
        "type": "issue",
        "owner": parsed.owner,
        "repo": parsed.repo,
        "number": parsed.number,
        "title": data.get("title", ""),
        "state": data.get("state", ""),
        "body": body,
        "labels": labels,
        "comments": comments,
    }
