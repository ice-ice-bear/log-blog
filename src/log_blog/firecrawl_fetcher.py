from __future__ import annotations

import logging
from urllib.parse import urlparse

from .config import Config

logger = logging.getLogger(__name__)

try:
    from firecrawl import Firecrawl
except ImportError:
    Firecrawl = None  # type: ignore[assignment,misc]


def _filter_by_path_prefix(
    base_url: str,
    links: list[str],
    max_pages: int = 10,
) -> list[str]:
    """Keep only URLs sharing the same domain and path prefix as base_url."""
    parsed = urlparse(base_url)
    base_domain = parsed.netloc
    # Use parent directory as prefix (e.g., /guides/intro → /guides/)
    path_parts = parsed.path.rstrip("/").rsplit("/", 1)
    base_prefix = path_parts[0] + "/" if len(path_parts) > 1 else "/"

    filtered = []
    for link in links:
        p = urlparse(link)
        if p.netloc != base_domain:
            continue
        if p.path.startswith(base_prefix):
            filtered.append(link)
        if len(filtered) >= max_pages:
            break

    return filtered


def fetch_docs_deep(url: str, config: Config):
    """Fetch docs via Firecrawl: map sub-links, batch scrape, combine.

    Returns a PageContent on success, or None if Firecrawl is unavailable
    (no API key, API error) so the caller can fall back to Playwright.
    """
    from .content_fetcher import PageContent

    if not config.firecrawl.api_key:
        logger.info("Firecrawl API key not configured; skipping deep docs fetch")
        return None

    try:
        if Firecrawl is None:
            logger.warning("firecrawl package not installed; skipping deep docs fetch")
            return None

        client = Firecrawl(api_key=config.firecrawl.api_key)

        # Step 1: Map — discover sub-links on the docs site
        map_result = client.map(url=url, limit=100)
        all_links = map_result.get("links", [])

        if not all_links:
            all_links = [url]

        # Step 2: Filter to same path prefix
        filtered = _filter_by_path_prefix(
            url, all_links, max_pages=config.firecrawl.max_pages,
        )

        if not filtered:
            filtered = [url]

        logger.info(
            "Firecrawl: mapped %d links, filtered to %d under path prefix",
            len(all_links), len(filtered),
        )

        # Step 3: Batch scrape
        batch_result = client.batch_scrape(
            filtered,
            formats=["markdown"],
            poll_interval=2,
        )

        # Step 4: Combine markdown from all pages
        pages_data = batch_result.get("data", [])
        parts: list[str] = []
        sub_urls: list[str] = []

        for i, page in enumerate(pages_data):
            markdown = page.get("markdown", "")
            meta = page.get("metadata", {})
            page_title = meta.get("title", f"Page {i + 1}")
            page_url = meta.get("sourceURL", filtered[i] if i < len(filtered) else "")

            if markdown.strip():
                parts.append(f"--- {page_title} ({page_url}) ---")
                parts.append(markdown.strip())
                parts.append("")
                sub_urls.append(page_url)

        combined = "\n".join(parts)

        return PageContent(
            url=url,
            title=pages_data[0].get("metadata", {}).get("title", url) if pages_data else url,
            text_content=combined,
            success=True,
            url_type="docs_page",
            metadata={
                "source": "firecrawl",
                "pages_crawled": len(sub_urls),
                "sub_urls": sub_urls,
            },
        )

    except Exception as e:
        logger.warning("Firecrawl fetch failed for %s: %s", url, e)
        return None
