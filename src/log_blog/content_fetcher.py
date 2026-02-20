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


async def _fetch_batch(urls: list[str], config: Config) -> list[PageContent]:
    """Fetch multiple pages, dispatching by URL type."""
    results: list[PageContent] = []
    playwright_urls: list[tuple[int, str]] = []  # (index, url)

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

        elif url_type in (UrlType.GITHUB_REPO, UrlType.GITHUB_PR, UrlType.GITHUB_ISSUE):
            content = _fetch_github(url, url_type)
            if content:
                results.append(content)
                continue
            # Fallback to Playwright
            playwright_urls.append((i, url))

        else:
            # GITHUB_OTHER, BITBUCKET_*, DOCS_PAGE, WEB_PAGE → Playwright
            playwright_urls.append((i, url))

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
