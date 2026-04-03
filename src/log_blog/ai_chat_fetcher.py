"""Fetch AI chat conversations by connecting to the user's running Chrome via CDP.

Instead of decrypting cookies or copying profiles, we connect to Chrome's
DevTools Protocol endpoint. This gives Playwright access to the user's live
browser session — all cookies, localStorage, and auth state — with zero
Keychain interaction.

Requires Chrome to be running with: --remote-debugging-port=9222

source: "online" — content fetched live from the web with user's auth session.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SPA_WAIT_MS = 3000   # extra wait after page load for SPA hydration
_MAX_CONTENT = 12000  # chars — AI conversations can be very long
_DEFAULT_CDP_PORT = 9222
_NAV_RETRIES = 2      # retry count for CDP navigation race conditions


async def fetch_ai_chat(
    url: str,
    cdp_port: int | None,
    timeout_ms: int,
    url_type: str,
    auth_required: bool = False,
) -> dict | None:
    """Fetch an AI chat URL by connecting to the user's running Chrome via CDP.

    Args:
        url:        The conversation URL.
        cdp_port:   Chrome DevTools Protocol port (default 9222).
                    If None or connection fails, falls back to a plain headless browser.
        timeout_ms: Page navigation timeout in milliseconds.
        url_type:   One of "ai_chat_perplexity" / "ai_chat_chatgpt" / "ai_chat_claude" / "ai_chat_gemini".
        auth_required: If True, skip unauthenticated fallback when CDP is unavailable.

    Returns:
        Dict with title, content, service, auth_used, source="online", or None on failure.
    """
    from playwright.async_api import async_playwright

    service = url_type.replace("ai_chat_", "")
    port = cdp_port or _DEFAULT_CDP_PORT

    try:
        async with async_playwright() as p:
            # Try connecting to the user's running Chrome
            browser = None
            auth_used = False
            try:
                browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
                auth_used = True
                logger.info("Connected to Chrome via CDP on port %d", port)
            except Exception as e:
                logger.warning(
                    "Could not connect to Chrome CDP on port %d: %s. "
                    "Launch Chrome with --remote-debugging-port=%d for authenticated fetching.",
                    port, e, port,
                )
                if auth_required:
                    logger.info(
                        "auth_profile is configured — skipping unauthenticated fallback for %s",
                        url,
                    )
                    return None
                # Fallback: headless browser without auth (no auth_profile configured)
                browser = await p.chromium.launch(headless=True)

            context = browser.contexts[0] if auth_used and browser.contexts else await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            )

            page = await context.new_page()
            try:
                # CDP navigation can race with existing tabs — retry on interruption
                last_err = None
                for attempt in range(_NAV_RETRIES + 1):
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                        last_err = None
                        break
                    except Exception as nav_err:
                        last_err = nav_err
                        if attempt < _NAV_RETRIES and "interrupted" in str(nav_err).lower():
                            logger.debug("CDP navigation interrupted (attempt %d), retrying", attempt + 1)
                            await page.wait_for_timeout(500)
                        else:
                            raise
                if last_err:
                    raise last_err

                await page.wait_for_timeout(_SPA_WAIT_MS)

                title = await page.title()
                content = await _extract_content(page, service, url)

                return {
                    "title": title,
                    "content": content[:_MAX_CONTENT] if content else "",
                    "service": service,
                    "auth_used": auth_used,
                    "source": "online",
                }
            finally:
                await page.close()
                if not auth_used:
                    await browser.close()

    except Exception as e:
        logger.warning(
            "AI chat fetch failed for %s (%s): %s. "
            "Ensure Chrome is running with: uv run log-blog chrome-cdp",
            url, service, e,
        )
        return None


async def _extract_content(page, service: str, url: str = "") -> str:
    """Extract conversation text using service-specific selectors with fallbacks."""

    if service == "perplexity":
        return await _extract_perplexity(page)
    elif service == "chatgpt":
        return await _extract_chatgpt(page)
    elif service == "claude":
        return await _extract_claude(page)
    elif service == "gemini" and "/share/" in url:
        return await _extract_gemini_share(page)
    elif service == "gemini":
        return await _extract_gemini(page)

    return await _generic_extract(page)


async def _extract_perplexity(page) -> str:
    """Extract question + answer from a Perplexity search page."""
    return await page.evaluate("""
        () => {
            const parts = [];

            const q = document.querySelector('h1, [class*="query"], [class*="question"]');
            if (q) parts.push('[QUESTION]\\n' + q.innerText.trim());

            const answers = document.querySelectorAll(
                '[class*="prose"], [class*="markdown"], [class*="answer"]'
            );
            answers.forEach((el, i) => {
                const text = el.innerText.trim();
                if (text.length > 50) {
                    parts.push('[ANSWER ' + (i + 1) + ']\\n' + text);
                }
            });

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
            const messages = document.querySelectorAll('[data-message-author-role]');

            if (messages.length === 0) {
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

            const human = document.querySelectorAll(
                '[class*="human"], [data-testid*="human"], .font-human-message'
            );
            const assistant = document.querySelectorAll(
                '[class*="assistant"], [data-testid*="assistant"], .font-claude-message'
            );

            if (human.length > 0 || assistant.length > 0) {
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

            const main = document.querySelector('main') || document.body;
            return main.innerText.trim().slice(0, 8000);
        }
    """)


async def _extract_gemini(page) -> str:
    """Extract the conversation thread from a Gemini (gemini.google.com) chat page."""
    return await page.evaluate("""
        () => {
            const parts = [];

            const turns = document.querySelectorAll(
                '[class*="query-content"], [class*="response-content"], '
                + '[class*="user-query"], [class*="model-response"], '
                + 'message-content, .conversation-container > div'
            );

            if (turns.length > 0) {
                turns.forEach(el => {
                    const text = el.innerText.trim();
                    if (text.length < 10) return;
                    const classes = (el.className || '') + (el.getAttribute('data-content-type') || '');
                    const isUser = /user|query|human/i.test(classes);
                    const isModel = /model|response|assistant/i.test(classes);
                    const label = isUser ? '[USER]' : isModel ? '[ASSISTANT]' : '[MESSAGE]';
                    parts.push(label + '\\n' + text);
                });
                if (parts.length > 0) return parts.join('\\n\\n');
            }

            const main = document.querySelector('main, [role="main"]') || document.body;
            return main.innerText.trim().slice(0, 8000);
        }
    """)


async def _extract_gemini_share(page) -> str:
    """Extract content from a Gemini share page (gemini.google.com/share/{id}).

    Share pages have a different DOM structure than /app/ conversations.
    They are publicly accessible — no auth needed.
    """
    return await page.evaluate("""
        () => {
            const parts = [];

            // Share pages may use different containers than /app/ pages
            const turns = document.querySelectorAll(
                '[class*="query-content"], [class*="response-content"], '
                + '[class*="user-query"], [class*="model-response"], '
                + 'message-content, .conversation-container > div, '
                + '[class*="prompt"], [class*="response"]'
            );

            if (turns.length > 0) {
                turns.forEach(el => {
                    const text = el.innerText.trim();
                    if (text.length < 10) return;
                    const classes = (el.className || '') + (el.getAttribute('data-content-type') || '');
                    const isUser = /user|query|human|prompt/i.test(classes);
                    const isModel = /model|response|assistant/i.test(classes);
                    const label = isUser ? '[USER]' : isModel ? '[ASSISTANT]' : '[MESSAGE]';
                    parts.push(label + '\\n' + text);
                });
                if (parts.length > 0) return parts.join('\\n\\n');
            }

            // Fallback: grab main content
            const main = document.querySelector('main, [role="main"]') || document.body;
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
