"""Fetch AI chat conversations using cookie-injected Playwright.

Each AI service (Perplexity, ChatGPT, Claude) renders conversations as a
single-page app. We inject the user's Chrome session cookies into a headless
browser to bypass authentication and Cloudflare, then extract the Q&A thread
with service-specific CSS selectors.

source: "online" — content fetched live from the web with user's auth session.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SPA_WAIT_MS = 3000   # extra wait after page load for SPA hydration
_MAX_CONTENT = 12000  # chars — AI conversations can be very long


async def fetch_ai_chat(
    url: str,
    cookies: list[dict],
    timeout_ms: int,
    url_type: str,
) -> dict | None:
    """Fetch an AI chat URL with injected cookies.

    Args:
        url:        The conversation URL.
        cookies:    Playwright-format cookie dicts from cookie_extractor.
        timeout_ms: Page navigation timeout in milliseconds.
        url_type:   One of "ai_chat_perplexity" / "ai_chat_chatgpt" / "ai_chat_claude".

    Returns:
        Dict with title, content, service, auth_used, source="online", or None on failure.
    """
    from playwright.async_api import async_playwright

    service = url_type.replace("ai_chat_", "")  # "perplexity" / "chatgpt" / "claude"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )
            if cookies:
                await context.add_cookies(cookies)

            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                # Extra wait for React/Next.js SPA to hydrate content
                await page.wait_for_timeout(_SPA_WAIT_MS)

                title = await page.title()
                content = await _extract_content(page, service)

                return {
                    "title": title,
                    "content": content[:_MAX_CONTENT] if content else "",
                    "service": service,
                    "auth_used": bool(cookies),
                    "source": "online",
                }
            finally:
                await context.close()
                await browser.close()

    except Exception as e:
        logger.warning("AI chat fetch failed for %s: %s", url, e)
        return None


async def _extract_content(page, service: str) -> str:
    """Extract conversation text using service-specific selectors with fallbacks."""

    if service == "perplexity":
        return await _extract_perplexity(page)
    elif service == "chatgpt":
        return await _extract_chatgpt(page)
    elif service == "claude":
        return await _extract_claude(page)

    # Unknown service — generic fallback
    return await _generic_extract(page)


async def _extract_perplexity(page) -> str:
    """Extract question + answer from a Perplexity search page."""
    return await page.evaluate("""
        () => {
            const parts = [];

            // Question is usually in h1 or a heading-level element
            const q = document.querySelector('h1, [class*="query"], [class*="question"]');
            if (q) parts.push('[QUESTION]\\n' + q.innerText.trim());

            // Answers are in prose/markdown containers
            const answers = document.querySelectorAll(
                '[class*="prose"], [class*="markdown"], [class*="answer"]'
            );
            answers.forEach((el, i) => {
                const text = el.innerText.trim();
                if (text.length > 50) {
                    parts.push('[ANSWER ' + (i + 1) + ']\\n' + text);
                }
            });

            // Sources list
            const sources = document.querySelectorAll('[class*="source"] a, [class*="citation"] a');
            if (sources.length > 0) {
                const sourceList = Array.from(sources)
                    .slice(0, 8)
                    .map(a => a.href + (a.innerText ? ' — ' + a.innerText.trim() : ''))
                    .filter(s => s.startsWith('http'));
                if (sourceList.length > 0) {
                    parts.push('[SOURCES]\\n' + sourceList.join('\\n'));
                }
            }

            return parts.join('\\n\\n') || document.body.innerText.slice(0, 8000);
        }
    """)


async def _extract_chatgpt(page) -> str:
    """Extract the Q&A thread from a ChatGPT conversation (private or share link)."""
    return await page.evaluate("""
        () => {
            const parts = [];
            // Each turn has data-message-author-role="user" or "assistant"
            const messages = document.querySelectorAll('[data-message-author-role]');

            if (messages.length === 0) {
                // Fallback: try article elements (share page layout)
                const articles = document.querySelectorAll('article');
                articles.forEach(a => {
                    const text = a.innerText.trim();
                    if (text.length > 10) parts.push(text);
                });
                return parts.join('\\n\\n') || document.body.innerText.slice(0, 8000);
            }

            messages.forEach(msg => {
                const role = msg.getAttribute('data-message-author-role');
                const label = role === 'user' ? '[USER]' : '[ASSISTANT]';
                // Content is inside .markdown or .whitespace-pre-wrap
                const content = msg.querySelector(
                    '.markdown, .whitespace-pre-wrap, [class*="prose"]'
                );
                const text = (content || msg).innerText.trim();
                if (text.length > 5) {
                    parts.push(label + '\\n' + text);
                }
            });

            return parts.join('\\n\\n');
        }
    """)


async def _extract_claude(page) -> str:
    """Extract the conversation thread from a Claude.ai chat page."""
    return await page.evaluate("""
        () => {
            const parts = [];

            // Human turns
            const human = document.querySelectorAll(
                '[class*="human"], [data-testid*="human"], .font-human-message'
            );
            // Assistant turns
            const assistant = document.querySelectorAll(
                '[class*="assistant"], [data-testid*="assistant"], .font-claude-message'
            );

            // If we found role-specific elements, interleave them
            if (human.length > 0 || assistant.length > 0) {
                // Collect all message elements with their vertical position
                const all = [];
                human.forEach(el => all.push({ role: 'USER', el, top: el.getBoundingClientRect().top }));
                assistant.forEach(el => all.push({ role: 'ASSISTANT', el, top: el.getBoundingClientRect().top }));
                all.sort((a, b) => a.top - b.top);
                all.forEach(({ role, el }) => {
                    const text = el.innerText.trim();
                    if (text.length > 5) parts.push('[' + role + ']\\n' + text);
                });
                return parts.join('\\n\\n');
            }

            // Fallback: grab main content
            const main = document.querySelector('main') || document.body;
            return main.innerText.trim().slice(0, 8000);
        }
    """)


async def _generic_extract(page) -> str:
    """Generic text extraction for unknown AI services."""
    return await page.evaluate("""
        () => {
            const main = document.querySelector('main, article, [role="main"]') || document.body;
            return main.innerText.trim().slice(0, 8000);
        }
    """)
