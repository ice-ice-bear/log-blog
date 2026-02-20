from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from playwright.async_api import async_playwright

from .config import Config
from .url_classifier import UrlType, classify_url

logger = logging.getLogger(__name__)

_MAX_WEB_CONTENT = 15000


@dataclass
class PageContent:
    url: str
    title: str
    text_content: str
    success: bool
    error: str | None = None
    url_type: str = "web_page"
    metadata: dict | None = None


async def _fetch_one(page, url: str, timeout_ms: int) -> PageContent:
    """Fetch a single page's content via Playwright."""
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if response and response.status >= 400:
            return PageContent(
                url=url, title="", text_content="",
                success=False, error=f"HTTP {response.status}",
            )

        title = await page.title()

        # Extract main text content — prefer article/main, fall back to body
        # Also extract headings hierarchy and code blocks
        text_content = await page.evaluate("""
            () => {
                const selectors = ['article', 'main', '[role="main"]', '.post-content', '.entry-content'];
                let root = null;
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 100) {
                        root = el;
                        break;
                    }
                }
                if (!root) root = document.body;
                if (!root) return '';

                let parts = [];

                // Extract headings hierarchy
                const headings = root.querySelectorAll('h1, h2, h3, h4');
                if (headings.length > 0) {
                    parts.push('[HEADINGS]');
                    headings.forEach(h => {
                        const level = h.tagName.toLowerCase();
                        parts.push(level + ': ' + h.innerText.trim());
                    });
                    parts.push('[/HEADINGS]');
                    parts.push('');
                }

                // Main text
                parts.push(root.innerText.trim());

                // Extract code blocks
                const codeBlocks = root.querySelectorAll('pre code, pre');
                if (codeBlocks.length > 0) {
                    parts.push('');
                    parts.push('[CODE_BLOCKS]');
                    let count = 0;
                    codeBlocks.forEach(cb => {
                        if (count >= 5) return;
                        const text = cb.innerText.trim();
                        if (text.length > 20 && text.length < 2000) {
                            parts.push('```');
                            parts.push(text);
                            parts.push('```');
                            count++;
                        }
                    });
                    parts.push('[/CODE_BLOCKS]');
                }

                return parts.join('\\n');
            }
        """)

        if len(text_content) > _MAX_WEB_CONTENT:
            text_content = text_content[:_MAX_WEB_CONTENT] + "\n\n[Content truncated...]"

        return PageContent(url=url, title=title, text_content=text_content, success=True)

    except Exception as e:
        return PageContent(url=url, title="", text_content="", success=False, error=str(e))


def _fetch_youtube(url: str) -> PageContent:
    """Fetch YouTube content via transcript API."""
    from .youtube_fetcher import fetch_youtube_transcript

    result = fetch_youtube_transcript(url)
    if result:
        title = f"YouTube: {result['video_id']}"
        return PageContent(
            url=url,
            title=title,
            text_content=result["transcript_text"],
            success=True,
            url_type=UrlType.YOUTUBE.value,
            metadata=result,
        )
    # Transcript unavailable — return None to trigger Playwright fallback
    return None


_AI_CHAT_SERVICE_MAP = {
    UrlType.AI_CHAT_PERPLEXITY: "perplexity",
    UrlType.AI_CHAT_CHATGPT: "chatgpt",
    UrlType.AI_CHAT_CLAUDE: "claude",
}


async def _fetch_ai_chat_online(
    url: str,
    url_type: UrlType,
    config: Config,
    profiles: list[dict] | None = None,
) -> PageContent | None:
    """Fetch an AI chat URL using Chrome cookies for authentication.

    Looks up the per-service config from accounts.ai_chats.{service}:
    - enabled=false  → returns PageContent(success=False), no Playwright fallback
    - auth_profile="" → returns None, falls through to unauthenticated Playwright
    - auth_profile set → resolves email to Chrome folder, extracts cookies, injects

    The `profiles` argument is the pre-resolved list from list_chrome_profiles()
    (pass it in to avoid re-reading the Chrome Local State file per URL).

    Return values for the caller:
    - None           → fall back to Playwright
    - success=False  → skip entirely (disabled), no fallback
    - success=True   → content fetched successfully
    """
    service_name = _AI_CHAT_SERVICE_MAP.get(url_type)
    if not service_name:
        return None

    service_cfg = getattr(config.accounts.ai_chats, service_name)

    # Disabled — skip this service entirely, don't even fall back to Playwright
    if not service_cfg.enabled:
        logger.info("AI chat service '%s' is disabled in config; skipping", service_name)
        return PageContent(
            url=url, title="", text_content="",
            success=False, error=f"{service_name} disabled in accounts.ai_chats",
            url_type=url_type.value,
        )

    if not service_cfg.auth_profile:
        return None  # No auth configured → fall through to unauthenticated Playwright

    from .cookie_extractor import get_chrome_cookies_for_url
    from .ai_chat_fetcher import fetch_ai_chat
    from urllib.parse import urlparse

    # Use pre-resolved profiles list to avoid re-reading Local State per URL
    if profiles is None:
        from .history_reader import list_chrome_profiles
        profiles = list_chrome_profiles(config)

    # Resolve email → Chrome profile folder
    auth_folder = next(
        (p["folder"] for p in profiles
         if p["email"].lower() == service_cfg.auth_profile.lower()),
        None,
    )
    if not auth_folder:
        logger.warning(
            "accounts.ai_chats.%s.auth_profile '%s' not found in Chrome profiles",
            service_name, service_cfg.auth_profile,
        )
        return None

    profile_path = config.chrome.history_db_base_path / auth_folder
    domain = urlparse(url).netloc
    cookies = get_chrome_cookies_for_url(profile_path, domain)

    result = await fetch_ai_chat(url, cookies, config.playwright.timeout_ms, url_type.value)
    if not result:
        return None

    return PageContent(
        url=url,
        title=result["title"],
        text_content=result["content"],
        success=True,
        url_type=url_type.value,
        metadata={
            "service": result["service"],
            "source": "online",
            "auth_used": result["auth_used"],
            "account": service_cfg.auth_profile,
        },
    )


def _fetch_bitbucket(url: str, url_type: UrlType, config: Config) -> PageContent | None:
    """Fetch Bitbucket content via REST API v2, with optional Basic auth."""
    from .bitbucket_fetcher import fetch_bitbucket_content

    result = fetch_bitbucket_content(
        url,
        username=config.accounts.bitbucket.username,
        token=config.accounts.bitbucket.token,
    )
    if result is None:
        return None

    text_parts: list[str] = []

    if result["type"] == "repo":
        title = result.get("full_name", url)
        if result.get("description"):
            text_parts.append(f"Description: {result['description']}")
        if result.get("language"):
            text_parts.append(f"Language: {result['language']}")
        if result.get("is_private"):
            text_parts.append("Visibility: Private")
        if result.get("readme"):
            text_parts.append(f"\n--- README ---\n{result['readme']}")

    elif result["type"] == "pr":
        title = f"PR #{result['pr_number']}: {result['title']}"
        text_parts.append(f"State: {result['state']}")
        text_parts.append(f"Author: {result['author']}")
        text_parts.append(
            f"Branch: {result['source_branch']} → {result['destination_branch']}"
        )
        if result.get("description"):
            text_parts.append(f"\nDescription:\n{result['description']}")

    else:
        return None

    return PageContent(
        url=url,
        title=title,
        text_content="\n".join(text_parts)[:_MAX_WEB_CONTENT],
        success=True,
        url_type=url_type.value,
        metadata=result,
    )


def _fetch_github(url: str, url_type: UrlType) -> PageContent:
    """Fetch GitHub content via gh CLI."""
    from .github_fetcher import fetch_github_content

    result = fetch_github_content(url, url_type)
    if result:
        # Build a text representation for the LLM
        text_parts = []
        if result["type"] == "repo":
            text_parts.append(f"Repository: {result['owner']}/{result['repo']}")
            if result.get("description"):
                text_parts.append(f"Description: {result['description']}")
            text_parts.append(f"Stars: {result['stars']} | Forks: {result['forks']}")
            if result.get("primary_language"):
                text_parts.append(f"Primary Language: {result['primary_language']}")
            if result.get("topics"):
                text_parts.append(f"Topics: {', '.join(result['topics'])}")
            if result.get("languages"):
                langs = ", ".join(f"{k}: {v}" for k, v in result["languages"].items())
                text_parts.append(f"Languages: {langs}")
            if result.get("recent_commits"):
                text_parts.append("\nRecent Commits:")
                for c in result["recent_commits"]:
                    text_parts.append(f"  {c['sha']} {c['message']}")
            if result.get("readme"):
                text_parts.append(f"\n--- README ---\n{result['readme']}")

        elif result["type"] == "pr":
            text_parts.append(f"PR #{result['number']}: {result['title']}")
            text_parts.append(f"State: {result['state']}")
            text_parts.append(f"Changes: +{result['additions']} -{result['deletions']} ({result['changed_files']} files)")
            if result.get("body"):
                text_parts.append(f"\n{result['body']}")
            if result.get("comments"):
                text_parts.append("\nComments:")
                for c in result["comments"]:
                    text_parts.append(f"  @{c['author']}: {c['body']}")

        elif result["type"] == "issue":
            text_parts.append(f"Issue #{result['number']}: {result['title']}")
            text_parts.append(f"State: {result['state']}")
            if result.get("labels"):
                text_parts.append(f"Labels: {', '.join(result['labels'])}")
            if result.get("body"):
                text_parts.append(f"\n{result['body']}")
            if result.get("comments"):
                text_parts.append("\nComments:")
                for c in result["comments"]:
                    text_parts.append(f"  @{c['author']}: {c['body']}")

        title = result.get("title") or f"{result['owner']}/{result['repo']}"
        return PageContent(
            url=url,
            title=title,
            text_content="\n".join(text_parts),
            success=True,
            url_type=url_type.value,
            metadata=result,
        )

    return None


_AI_CHAT_TYPES = (UrlType.AI_CHAT_PERPLEXITY, UrlType.AI_CHAT_CHATGPT, UrlType.AI_CHAT_CLAUDE)
_GITHUB_TYPES = (UrlType.GITHUB_REPO, UrlType.GITHUB_PR, UrlType.GITHUB_ISSUE)


async def _fetch_batch(urls: list[str], config: Config) -> list[PageContent]:
    """Fetch multiple pages, dispatching by URL type."""
    results: list[PageContent] = []
    playwright_urls: list[tuple[int, str]] = []  # (index, url)

    # Switch GitHub account once before the batch if a profile is configured;
    # remember the previous user so we can restore it afterward.
    _previous_gh_user: str | None = None
    if config.accounts.github.profile:
        has_github = any(classify_url(u) in _GITHUB_TYPES for u in urls)
        if has_github:
            from .github_fetcher import switch_github_profile, get_current_gh_user
            _previous_gh_user = get_current_gh_user()
            switch_github_profile(config.accounts.github.profile)

    # Pre-resolve Chrome profiles once for AI chat cookie extraction
    _chrome_profiles: list[dict] | None = None
    if any(classify_url(u) in _AI_CHAT_TYPES for u in urls):
        from .history_reader import list_chrome_profiles
        _chrome_profiles = list_chrome_profiles(config)

    try:
        # Classify and dispatch non-Playwright fetches first
        for i, url in enumerate(urls):
            url_type = classify_url(url)

            if url_type == UrlType.YOUTUBE:
                content = _fetch_youtube(url)
                if content:
                    results.append(content)
                    continue
                # Fallback to Playwright
                playwright_urls.append((i, url))

            elif url_type in _GITHUB_TYPES:
                content = _fetch_github(url, url_type)
                if content:
                    results.append(content)
                    continue
                # Fallback to Playwright
                playwright_urls.append((i, url))

            elif url_type in (UrlType.BITBUCKET_REPO, UrlType.BITBUCKET_PR):
                content = _fetch_bitbucket(url, url_type, config)
                if content:
                    results.append(content)
                    continue
                # Fallback to Playwright
                playwright_urls.append((i, url))

            elif url_type in _AI_CHAT_TYPES:
                content = await _fetch_ai_chat_online(url, url_type, config, profiles=_chrome_profiles)
                if content is None:
                    # No auth configured → fall back to Playwright
                    playwright_urls.append((i, url))
                elif content.success:
                    results.append(content)
                # else: service disabled → skip entirely, no Playwright fallback

            else:
                # GITHUB_OTHER, BITBUCKET other, DOCS_PAGE, WEB_PAGE → Playwright
                playwright_urls.append((i, url))

    finally:
        # Restore previous gh CLI profile if we switched it
        if _previous_gh_user and config.accounts.github.profile != _previous_gh_user:
            from .github_fetcher import switch_github_profile
            switch_github_profile(_previous_gh_user)

    # Fetch remaining URLs via Playwright
    if playwright_urls:
        pw_urls = [u for _, u in playwright_urls]
        pw_results = await _fetch_with_playwright(pw_urls, config)

        for (_, url), page_content in zip(playwright_urls, pw_results):
            url_type = classify_url(url)
            page_content.url_type = url_type.value
            results.append(page_content)

    # Sort results to match original URL order
    url_order = {url: i for i, url in enumerate(urls)}
    results.sort(key=lambda r: url_order.get(r.url, 999))

    return results


async def _fetch_with_playwright(urls: list[str], config: Config) -> list[PageContent]:
    """Fetch pages concurrently using Playwright."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=config.playwright.headless)
        semaphore = asyncio.Semaphore(config.playwright.max_concurrent)

        async def fetch_with_semaphore(url: str) -> PageContent:
            async with semaphore:
                context = await browser.new_context()
                page = await context.new_page()
                try:
                    return await _fetch_one(page, url, config.playwright.timeout_ms)
                finally:
                    await context.close()

        tasks = [fetch_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks)
        await browser.close()

    return list(results)


def fetch_pages(urls: list[str], config: Config) -> list[PageContent]:
    """Fetch page content for a list of URLs. Synchronous wrapper."""
    return asyncio.run(_fetch_batch(urls, config))
