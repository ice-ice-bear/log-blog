from unittest.mock import MagicMock, patch

import pytest

from log_blog.firecrawl_fetcher import _filter_by_path_prefix, fetch_docs_deep
from log_blog.config import Config, FirecrawlConfig


def test_filter_by_path_prefix_basic():
    """Should keep URLs under the same path prefix."""
    base_url = "https://docs.example.com/guides/getting-started"
    links = [
        "https://docs.example.com/guides/getting-started",
        "https://docs.example.com/guides/configuration",
        "https://docs.example.com/guides/deployment",
        "https://docs.example.com/api/reference",
        "https://other-site.com/guides/foo",
    ]
    result = _filter_by_path_prefix(base_url, links)
    assert result == [
        "https://docs.example.com/guides/getting-started",
        "https://docs.example.com/guides/configuration",
        "https://docs.example.com/guides/deployment",
    ]


def test_filter_by_path_prefix_root():
    """When base URL has no path segments beyond domain, keep all same-domain URLs."""
    base_url = "https://docs.example.com/"
    links = [
        "https://docs.example.com/guides/foo",
        "https://docs.example.com/api/bar",
        "https://other.com/page",
    ]
    result = _filter_by_path_prefix(base_url, links)
    assert result == [
        "https://docs.example.com/guides/foo",
        "https://docs.example.com/api/bar",
    ]


def test_filter_by_path_prefix_respects_limit():
    """Should respect max_pages limit."""
    base_url = "https://docs.example.com/guides/intro"
    links = [f"https://docs.example.com/guides/page{i}" for i in range(20)]
    result = _filter_by_path_prefix(base_url, links, max_pages=5)
    assert len(result) == 5


@patch("log_blog.firecrawl_fetcher.Firecrawl")
def test_fetch_docs_deep_success(mock_firecrawl_cls):
    """Should map, filter, batch_scrape, and combine results."""
    mock_client = MagicMock()
    mock_firecrawl_cls.return_value = mock_client

    # map returns links
    mock_client.map.return_value = {
        "links": [
            "https://docs.example.com/guides/intro",
            "https://docs.example.com/guides/setup",
            "https://docs.example.com/api/ref",
        ]
    }

    # batch_scrape returns page data
    mock_client.batch_scrape.return_value = {
        "data": [
            {"markdown": "# Intro\nIntro content", "metadata": {"title": "Intro"}},
            {"markdown": "# Setup\nSetup content", "metadata": {"title": "Setup"}},
        ]
    }

    config = Config(firecrawl=FirecrawlConfig(api_key="fc-test", max_pages=10))
    result = fetch_docs_deep("https://docs.example.com/guides/intro", config)

    assert result.success is True
    assert result.url_type == "docs_page"
    assert "Intro content" in result.text_content
    assert "Setup content" in result.text_content
    assert result.metadata["source"] == "firecrawl"
    assert result.metadata["pages_crawled"] == 2


@patch("log_blog.firecrawl_fetcher.Firecrawl")
def test_fetch_docs_deep_no_api_key(mock_firecrawl_cls):
    """Should return None when no API key is configured."""
    config = Config(firecrawl=FirecrawlConfig(api_key="", max_pages=10))
    result = fetch_docs_deep("https://docs.example.com/guides/intro", config)

    assert result is None
    mock_firecrawl_cls.assert_not_called()


@patch("log_blog.firecrawl_fetcher.Firecrawl")
def test_fetch_docs_deep_api_error(mock_firecrawl_cls):
    """Should return None on API errors so caller can fall back."""
    mock_client = MagicMock()
    mock_firecrawl_cls.return_value = mock_client
    mock_client.map.side_effect = Exception("API quota exceeded")

    config = Config(firecrawl=FirecrawlConfig(api_key="fc-test", max_pages=10))
    result = fetch_docs_deep("https://docs.example.com/guides/intro", config)

    assert result is None
