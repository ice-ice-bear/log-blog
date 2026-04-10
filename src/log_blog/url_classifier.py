"""Regex-based URL type detection for content fetching dispatch."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class UrlType(str, Enum):
    YOUTUBE = "youtube"
    GITHUB_REPO = "github_repo"
    GITHUB_PR = "github_pr"
    GITHUB_ISSUE = "github_issue"
    GITHUB_OTHER = "github_other"
    BITBUCKET_REPO = "bitbucket_repo"
    BITBUCKET_PR = "bitbucket_pr"
    AI_CHAT_PERPLEXITY = "ai_chat_perplexity"
    AI_CHAT_CHATGPT = "ai_chat_chatgpt"
    AI_CHAT_CLAUDE = "ai_chat_claude"
    AI_CHAT_GEMINI = "ai_chat_gemini"
    DOCS_PAGE = "docs_page"
    WEB_PAGE = "web_page"
    AI_LANDING = "ai_landing"


@dataclass
class GitHubUrl:
    owner: str
    repo: str
    number: int | None = None


@dataclass
class BitbucketUrl:
    workspace: str
    repo_slug: str
    pr_number: int | None = None


# YouTube patterns
_YT_WATCH = re.compile(r"(?:www\.)?youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})")
_YT_SHORT = re.compile(r"youtu\.be/([a-zA-Z0-9_-]{11})")
_YT_SHORTS = re.compile(r"(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})")
_YT_EMBED = re.compile(r"(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})")
# YouTube noise — homepages, channel pages, playlists (not individual videos)
_YT_NOISE = re.compile(r"(?:www\.)?youtube\.com/(?:@|channel/|playlist\?|feed/|$)")
_YT_HOMEPAGE = re.compile(r"(?:www\.)?youtube\.com/?(?:[?#]|$)")

# GitHub patterns
_GH_PR = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")
_GH_ISSUE = re.compile(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)")
_GH_REPO = re.compile(r"github\.com/([^/]+)/([^/]+?)(?:\.git)?/?(?:[?#]|$)")
_GH_OTHER = re.compile(r"github\.com/([^/]+)/([^/]+)")
# GitHub non-repo pages — user profiles, notifications, topics, explore, etc.
_GH_NON_REPO = re.compile(
    r"github\.com/(?:topics|explore|notifications|settings|orgs|marketplace"
    r"|sponsors|collections|trending|features|pricing|enterprise|readme)(?:/|[?#]|$)"
    r"|github\.com/[^/]+/?(?:[?#]|$)"  # user profile pages (single path segment)
)

# Bitbucket patterns
_BB_PR = re.compile(r"bitbucket\.org/([^/]+)/([^/]+)/pull-requests/(\d+)")
_BB_REPO = re.compile(r"bitbucket\.org/([^/]+)/([^/]+?)/?(?:[?#]|$)")

# AI chat patterns — per-conversation URLs only (not landing pages)
# Verified: 2026-02-25
_PERPLEXITY = re.compile(
    r"perplexity\.ai/search/[^?#/]+"      # perplexity.ai/search/{query-or-uuid}
    r"|perplexity\.ai/page/[^?#/]+"       # perplexity.ai/page/{id} (Perplexity Pages)
    r"|perplexity\.ai/computer/a/[^?#/]+" # perplexity.ai/computer/a/{slug} (Computer agent sessions)
)
# Verified: 2026-02-25 — ChatGPT migrated from chat.openai.com → chatgpt.com (2024)
_CHATGPT = re.compile(
    r"chatgpt\.com/(?:c|share|g)/[a-zA-Z0-9_-]+"   # chatgpt.com/c/{id}, /share/{id}, /g/{gpt-id}
    r"|chat\.openai\.com/(?:c|share)/[a-zA-Z0-9-]+" # legacy domain (redirects but still in history DBs)
)
# Verified: 2026-02-25
_CLAUDE = re.compile(
    r"claude\.ai/chat/[a-zA-Z0-9-]+"      # claude.ai/chat/{uuid}
)
# Verified: 2026-02-25
_GEMINI = re.compile(
    r"gemini\.google\.com/app/[a-zA-Z0-9]+"    # gemini.google.com/app/{conversation-id}
    r"|gemini\.google\.com/share/[a-zA-Z0-9]+" # gemini.google.com/share/{id}
)

# Known AI service domains for unmatched-URL warning (landing pages, settings, etc.)
_AI_CHAT_DOMAINS = ("perplexity.ai", "chatgpt.com", "chat.openai.com", "claude.ai", "gemini.google.com")

# Noise patterns — landing pages, auth flows, settings, etc.
# Checked BEFORE conversation patterns to prevent wasted Playwright fetches.
_AI_NOISE_PATTERNS = [
    re.compile(r"claude\.ai/(?:oauth|chrome|code|project|settings|new|download)(?:/|[?#]|$)"),
    re.compile(r"claude\.ai/?(?:[?#]|$)"),
    re.compile(r"chatgpt\.com/?(?:[?#]|$)"),
    re.compile(r"chatgpt\.com/(?:auth|backend-api|gpts)(?:/|[?#]|$)"),
    re.compile(r"gemini\.google\.com/app/(?:download|extensions|settings)(?:/|[?#]|$)"),
    re.compile(r"gemini\.google\.com/(?:app)?/?(?:[?#]|$)"),
    re.compile(r"perplexity\.ai/?(?:[?#]|$)"),
    re.compile(r"perplexity\.ai/search/new(?:[?#]|$)"),  # "new search" landing page
    re.compile(r"perplexity\.ai/computer/new(?:[?#]|$)"), # "new computer" landing page
    re.compile(r"perplexity\.ai/(?:pro|billing|max)(?:/|[?#]|$)"),  # billing/subscription pages
]

# Docs patterns
_DOCS = re.compile(
    r"(?:docs\.|developer\.|devdocs\.|readthedocs\.)"
    r"|\.readthedocs\.io"
    r"|docs\.rs"
    r"|pkg\.go\.dev"
    r"|pypi\.org"
    r"|code\.claude\.com/docs"
)

# General noise — search engines, auth, email, social media non-content pages
_GENERAL_NOISE = re.compile(
    r"google\.com/search\?"                # Google search results
    r"|google\.com/aclk\?"                 # Google ad clicks
    r"|accounts\.google\.com"              # Google auth flows
    r"|mail\.google\.com"                  # Gmail
    r"|signin\.aws\.amazon\.com"           # AWS auth
    r"|console\.aws\.amazon\.com/console/home"  # AWS console home (not specific service)
)


def classify_url(url: str) -> UrlType:
    """Classify a URL into a content type for fetch dispatch."""
    # General noise — filter early before any specific checks
    if _GENERAL_NOISE.search(url):
        return UrlType.AI_LANDING  # reuse AI_LANDING as generic "skip" type

    # YouTube — check noise first, then video patterns
    if "youtube.com" in url or "youtu.be" in url:
        if _YT_NOISE.search(url) or _YT_HOMEPAGE.search(url):
            return UrlType.AI_LANDING
        if _YT_WATCH.search(url) or _YT_SHORT.search(url) or _YT_SHORTS.search(url) or _YT_EMBED.search(url):
            return UrlType.YOUTUBE
        return UrlType.WEB_PAGE

    # GitHub — filter non-repo pages first
    if "github.com" in url:
        if _GH_NON_REPO.search(url):
            return UrlType.WEB_PAGE
        if _GH_PR.search(url):
            return UrlType.GITHUB_PR
        if _GH_ISSUE.search(url):
            return UrlType.GITHUB_ISSUE
        if _GH_REPO.search(url):
            return UrlType.GITHUB_REPO
        if _GH_OTHER.search(url):
            return UrlType.GITHUB_OTHER
        return UrlType.WEB_PAGE

    # AI noise filter — check before conversation patterns
    for domain in _AI_CHAT_DOMAINS:
        if domain in url:
            if any(p.search(url) for p in _AI_NOISE_PATTERNS):
                return UrlType.AI_LANDING
            break

    # AI chat services — must match per-conversation URLs
    if "perplexity.ai" in url:
        if _PERPLEXITY.search(url):
            return UrlType.AI_CHAT_PERPLEXITY
        _warn_unmatched_ai(url, "perplexity")
    if "chatgpt.com" in url or "chat.openai.com" in url:
        if _CHATGPT.search(url):
            return UrlType.AI_CHAT_CHATGPT
        _warn_unmatched_ai(url, "chatgpt")
    if "claude.ai" in url:
        if _CLAUDE.search(url):
            return UrlType.AI_CHAT_CLAUDE
        _warn_unmatched_ai(url, "claude")
    if "gemini.google.com" in url:
        if _GEMINI.search(url):
            return UrlType.AI_CHAT_GEMINI
        _warn_unmatched_ai(url, "gemini")

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
    for pattern in (_YT_WATCH, _YT_SHORT, _YT_SHORTS, _YT_EMBED):
        m = pattern.search(url)
        if m:
            return m.group(1)
    return None


def parse_bitbucket_url(url: str) -> BitbucketUrl | None:
    """Extract workspace/repo_slug/pr_number from a Bitbucket URL."""
    m = _BB_PR.search(url)
    if m:
        return BitbucketUrl(workspace=m.group(1), repo_slug=m.group(2), pr_number=int(m.group(3)))
    m = _BB_REPO.search(url)
    if m:
        return BitbucketUrl(workspace=m.group(1), repo_slug=m.group(2))
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


_warned_urls: set[str] = set()


def _warn_unmatched_ai(url: str, service: str) -> None:
    """Log a warning when an AI service domain is seen but the URL pattern didn't match.

    This catches landing pages, settings pages, and new URL patterns that haven't
    been added to the regex yet. Deduplicates to avoid log spam.
    """
    if url in _warned_urls:
        return
    _warned_urls.add(url)
    logger.warning(
        "AI chat URL from %s not matched by conversation pattern (classified as web_page): %s",
        service,
        url,
    )
