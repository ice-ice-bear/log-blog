from unittest.mock import patch, MagicMock

from log_blog.config import Config, FirecrawlConfig
from log_blog.content_fetcher import PageContent, fetch_pages


@patch("log_blog.content_fetcher._fetch_with_playwright")
@patch("log_blog.firecrawl_fetcher.Firecrawl")
def test_fetch_pages_deep_routes_to_firecrawl(mock_fc_cls, mock_pw):
    """DOCS_PAGE URLs in deep_urls should go through Firecrawl, not Playwright."""
    mock_client = MagicMock()
    mock_fc_cls.return_value = mock_client
    mock_client.map.return_value = {
        "links": ["https://docs.example.com/guides/intro"]
    }
    mock_client.batch_scrape.return_value = {
        "data": [
            {"markdown": "# Guide\nContent here", "metadata": {"title": "Guide"}}
        ]
    }

    config = Config(firecrawl=FirecrawlConfig(api_key="fc-test", max_pages=10))
    urls = ["https://docs.example.com/guides/intro"]
    results = fetch_pages(urls, config, deep_urls=set(urls))

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].metadata["source"] == "firecrawl"
    # Playwright should NOT have been called for this URL
    mock_pw.assert_not_called()


@patch("log_blog.content_fetcher._fetch_with_playwright")
def test_fetch_pages_deep_fallback_to_playwright(mock_pw):
    """When Firecrawl has no API key, deep URLs should fall back to Playwright."""
    mock_pw.return_value = [
        PageContent(
            url="https://docs.example.com/guides/intro",
            title="Guide", text_content="content",
            success=True, url_type="docs_page",
        )
    ]

    config = Config(firecrawl=FirecrawlConfig(api_key="", max_pages=10))
    urls = ["https://docs.example.com/guides/intro"]
    results = fetch_pages(urls, config, deep_urls=set(urls))

    assert len(results) == 1
    assert results[0].success is True
    mock_pw.assert_called_once()
