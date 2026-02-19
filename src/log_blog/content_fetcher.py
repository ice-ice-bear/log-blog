from __future__ import annotations

import asyncio
from dataclasses import dataclass

from playwright.async_api import async_playwright

from .config import Config


@dataclass
class PageContent:
    url: str
    title: str
    text_content: str
    success: bool
    error: str | None = None


async def _fetch_one(page, url: str, timeout_ms: int) -> PageContent:
    """Fetch a single page's content."""
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if response and response.status >= 400:
            return PageContent(
                url=url, title="", text_content="",
                success=False, error=f"HTTP {response.status}",
            )

        title = await page.title()

        # Extract main text content — prefer article/main, fall back to body
        text_content = await page.evaluate("""
            () => {
                const selectors = ['article', 'main', '[role="main"]', '.post-content', '.entry-content'];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 100) {
                        return el.innerText.trim();
                    }
                }
                return document.body ? document.body.innerText.trim() : '';
            }
        """)

        # Truncate very long content
        if len(text_content) > 10000:
            text_content = text_content[:10000] + "\n\n[Content truncated...]"

        return PageContent(url=url, title=title, text_content=text_content, success=True)

    except Exception as e:
        return PageContent(url=url, title="", text_content="", success=False, error=str(e))


async def _fetch_batch(urls: list[str], config: Config) -> list[PageContent]:
    """Fetch multiple pages concurrently using Playwright."""
    results: list[PageContent] = []

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
