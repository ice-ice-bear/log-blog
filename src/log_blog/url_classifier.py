"""Regex-based URL type detection for content fetching dispatch."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class UrlType(str, Enum):
    YOUTUBE = "youtube"
    GITHUB_REPO = "github_repo"
    GITHUB_PR = "github_pr"
    GITHUB_ISSUE = "github_issue"
    GITHUB_OTHER = "github_other"
    BITBUCKET_REPO = "bitbucket_repo"
    BITBUCKET_PR = "bitbucket_pr"
    DOCS_PAGE = "docs_page"
    WEB_PAGE = "web_page"


@dataclass
class GitHubUrl:
    owner: str
    repo: str
    number: int | None = None


# YouTube patterns
_YT_WATCH = re.compile(r"(?:www\.)?youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})")
_YT_SHORT = re.compile(r"youtu\.be/([a-zA-Z0-9_-]{11})")
_YT_EMBED = re.compile(r"(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})")

# GitHub patterns
_GH_PR = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")
_GH_ISSUE = re.compile(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)")
_GH_REPO = re.compile(r"github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")
_GH_OTHER = re.compile(r"github\.com/([^/]+)/([^/]+)")

# Bitbucket patterns
_BB_PR = re.compile(r"bitbucket\.org/([^/]+)/([^/]+)/pull-requests/(\d+)")
_BB_REPO = re.compile(r"bitbucket\.org/([^/]+)/([^/]+?)/?$")

# Docs patterns
_DOCS = re.compile(
    r"(?:docs\.|developer\.|devdocs\.|readthedocs\.)"
    r"|\.readthedocs\.io"
    r"|docs\.rs"
    r"|pkg\.go\.dev"
    r"|pypi\.org"
)


def classify_url(url: str) -> UrlType:
    """Classify a URL into a content type for fetch dispatch."""
    # YouTube
    if _YT_WATCH.search(url) or _YT_SHORT.search(url) or _YT_EMBED.search(url):
        return UrlType.YOUTUBE

    # GitHub
    if "github.com" in url:
        if _GH_PR.search(url):
            return UrlType.GITHUB_PR
        if _GH_ISSUE.search(url):
            return UrlType.GITHUB_ISSUE
        if _GH_REPO.search(url):
            return UrlType.GITHUB_REPO
        if _GH_OTHER.search(url):
            return UrlType.GITHUB_OTHER
        return UrlType.WEB_PAGE

    # Bitbucket
    if "bitbucket.org" in url:
        if _BB_PR.search(url):
            return UrlType.BITBUCKET_PR
        if _BB_REPO.search(url):
            return UrlType.BITBUCKET_REPO
        return UrlType.WEB_PAGE

    # Docs
    if _DOCS.search(url):
        return UrlType.DOCS_PAGE

    return UrlType.WEB_PAGE


def parse_youtube_id(url: str) -> str | None:
    """Extract a YouTube video ID from a URL."""
    for pattern in (_YT_WATCH, _YT_SHORT, _YT_EMBED):
        m = pattern.search(url)
        if m:
            return m.group(1)
    return None


def parse_github_url(url: str) -> GitHubUrl | None:
    """Extract owner/repo/number from a GitHub URL."""
    for pattern in (_GH_PR, _GH_ISSUE):
        m = pattern.search(url)
        if m:
            return GitHubUrl(owner=m.group(1), repo=m.group(2), number=int(m.group(3)))

    m = _GH_REPO.search(url)
    if m:
        return GitHubUrl(owner=m.group(1), repo=m.group(2))

    m = _GH_OTHER.search(url)
    if m:
        return GitHubUrl(owner=m.group(1), repo=m.group(2))

    return None
