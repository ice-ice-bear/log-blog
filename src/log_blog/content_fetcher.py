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


def _fetch_youtube(url: str) -> PageContent | None:
    """Fetch YouTube content via transcript API + oEmbed metadata."""
    from .youtube_fetcher import fetch_youtube_transcript, _fetch_oembed
    from .url_classifier import parse_youtube_id

    result = fetch_youtube_transcript(url)
    if result:
        title = result.get("title") or f"YouTube: {result['video_id']}"
        return PageContent(
            url=url,
            title=title,
            text_content=result["transcript_text"],
            success=True,
            url_type=UrlType.YOUTUBE.value,
            metadata=result,
        )

    # Transcript unavailable — try oEmbed for at least title/author metadata
    video_id = parse_youtube_id(url)
    if video_id:
        oembed = _fetch_oembed(video_id)
        if oembed.get("title"):
            return PageContent(
                url=url,
                title=oembed["title"],
                text_content=f"[Transcript unavailable]\n\nVideo: {oembed['title']}\nAuthor: {oembed.get('author_name', 'Unknown')}",
                success=True,
                url_type=UrlType.YOUTUBE.value,
                metadata={"video_id": video_id, **oembed, "transcript_text": ""},
            )

    # No metadata available — fall back to Playwright
    return None


_AI_CHAT_SERVICE_MAP = {
    UrlType.AI_CHAT_PERPLEXITY: "perplexity",
    UrlType.AI_CHAT_CHATGPT: "chatgpt",
    UrlType.AI_CHAT_CLAUDE: "claude",
    UrlType.AI_CHAT_GEMINI: "gemini",
}


async def _fetch_ai_chat_online(
    url: str,
    url_type: UrlType,
    config: Config,
) -> PageContent | None:
    """Fetch an AI chat URL by connecting to Chrome via CDP.

    Looks up the per-service config from accounts.ai_chats.{service}:
    - enabled=false  → returns PageContent(success=False), no Playwright fallback
    - auth_profile="" → returns None, falls through to unauthenticated Playwright
    - auth_profile set → connects to Chrome via CDP for authenticated fetching

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

    from .ai_chat_fetcher import fetch_ai_chat

    result = await fetch_ai_chat(
        url, config.playwright.cdp_port, config.playwright.timeout_ms, url_type.value,
        auth_required=bool(service_cfg.auth_profile),
    )
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


def _fetch_github(url: str, url_type: UrlType) -> PageContent | None:
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


_AI_CHAT_TYPES = (UrlType.AI_CHAT_PERPLEXITY, UrlType.AI_CHAT_CHATGPT, UrlType.AI_CHAT_CLAUDE, UrlType.AI_CHAT_GEMINI)
_GITHUB_TYPES = (UrlType.GITHUB_REPO, UrlType.GITHUB_PR, UrlType.GITHUB_ISSUE)


async def _fetch_batch(
    urls: list[str],
    config: Config,
    deep_urls: set[str] | None = None,
) -> list[PageContent]:
    """Fetch multiple pages, dispatching by URL type.

    Sync fetchers (YouTube, GitHub, Bitbucket) run in parallel via asyncio.to_thread.
    AI chat fetchers (already async) run in parallel via asyncio.gather.
    Remaining URLs go through Playwright concurrently.
    """
    classified = [(url, classify_url(url)) for url in urls]

    # Switch GitHub account once before the batch if a profile is configured
    _previous_gh_user: str | None = None
    has_github = any(ut in _GITHUB_TYPES for _, ut in classified)
    if config.accounts.github.profile and has_github:
        from .github_fetcher import switch_github_profile, get_current_gh_user
        _previous_gh_user = get_current_gh_user()
        switch_github_profile(config.accounts.github.profile)

    results: dict[str, PageContent] = {}
    playwright_urls: list[str] = []

    try:
        # --- Bucket URLs by type ---
        youtube_urls: list[str] = []
        github_urls: list[tuple[str, UrlType]] = []
        bitbucket_urls: list[tuple[str, UrlType]] = []
        ai_chat_urls: list[tuple[str, UrlType]] = []
        pw_direct_urls: list[str] = []

        for url, url_type in classified:
            if url_type == UrlType.AI_LANDING:
                results[url] = PageContent(
                    url=url, title="", text_content="",
                    success=False, error="AI landing page, no content to fetch",
                    url_type=url_type.value,
                )
                continue
            if url_type == UrlType.YOUTUBE:
                youtube_urls.append(url)
            elif url_type in _GITHUB_TYPES:
                github_urls.append((url, url_type))
            elif url_type in (UrlType.BITBUCKET_REPO, UrlType.BITBUCKET_PR):
                bitbucket_urls.append((url, url_type))
            elif url_type in _AI_CHAT_TYPES:
                ai_chat_urls.append((url, url_type))
            else:
                # Check if this is a deep docs request
                if deep_urls and url in deep_urls and url_type == UrlType.DOCS_PAGE:
                    from .firecrawl_fetcher import fetch_docs_deep
                    fc_result = fetch_docs_deep(url, config)
                    if fc_result is not None:
                        results[url] = fc_result
                        continue
                pw_direct_urls.append(url)

        # --- Run sync fetchers in parallel via to_thread ---
        sync_tasks: list = []
        sync_task_urls: list[str] = []

        for url in youtube_urls:
            sync_tasks.append(asyncio.to_thread(_fetch_youtube, url))
            sync_task_urls.append(url)

        for url, ut in github_urls:
            sync_tasks.append(asyncio.to_thread(_fetch_github, url, ut))
            sync_task_urls.append(url)

        for url, ut in bitbucket_urls:
            sync_tasks.append(asyncio.to_thread(_fetch_bitbucket, url, ut, config))
            sync_task_urls.append(url)

        if sync_tasks:
            sync_results = await asyncio.gather(*sync_tasks, return_exceptions=True)
            for url, content in zip(sync_task_urls, sync_results):
                if isinstance(content, Exception):
                    logger.warning("Sync fetch failed for %s: %s", url, content)
                    playwright_urls.append(url)
                elif content is not None:
                    results[url] = content
                else:
                    playwright_urls.append(url)

        # --- Run AI chat fetches (already async) in parallel ---
        if ai_chat_urls:
            ai_tasks = [_fetch_ai_chat_online(url, ut, config) for url, ut in ai_chat_urls]
            ai_results = await asyncio.gather(*ai_tasks, return_exceptions=True)
            for (url, _ut), content in zip(ai_chat_urls, ai_results):
                if isinstance(content, Exception):
                    logger.warning("AI chat fetch failed for %s: %s", url, content)
                    playwright_urls.append(url)
                elif content is None:
                    playwright_urls.append(url)
                elif content.success:
                    results[url] = content
                # else: service disabled → skip entirely

        # --- Playwright for everything remaining ---
        playwright_urls.extend(pw_direct_urls)

        if playwright_urls:
            pw_results = await _fetch_with_playwright(playwright_urls, config)
            for url, page_content in zip(playwright_urls, pw_results):
                page_content.url_type = classify_url(url).value
                results[url] = page_content

    finally:
        if _previous_gh_user and config.accounts.github.profile != _previous_gh_user:
            from .github_fetcher import switch_github_profile
            switch_github_profile(_previous_gh_user)

    # Sort results to match original URL order
    url_order = {url: i for i, url in enumerate(urls)}
    return sorted(results.values(), key=lambda r: url_order.get(r.url, 999))


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


def fetch_pages(
    urls: list[str],
    config: Config,
    deep_urls: set[str] | None = None,
) -> list[PageContent]:
    """Fetch page content for a list of URLs. Synchronous wrapper."""
    return asyncio.run(_fetch_batch(urls, config, deep_urls=deep_urls))
