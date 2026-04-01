# Firecrawl Deep Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Firecrawl as an optional deep-crawl fetcher for documentation sites, controllable via `--deep` CLI flag.

**Architecture:** New `firecrawl_fetcher.py` module wraps the Firecrawl Python SDK. `content_fetcher.py` gains a `deep_urls` parameter to route specific DOCS_PAGE URLs through Firecrawl instead of Playwright. Config adds a `firecrawl` section with `api_key` and `max_pages`.

**Tech Stack:** Python 3.12, firecrawl-py SDK, asyncio

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/log_blog/firecrawl_fetcher.py` | Create | Firecrawl map + batch_scrape, path-prefix filtering |
| `src/log_blog/config.py` | Modify | Add `FirecrawlConfig` dataclass, wire into `Config` and `load_config` |
| `src/log_blog/content_fetcher.py` | Modify | Add `deep_urls` param to `fetch_pages`/`_fetch_batch`, route DOCS_PAGE+deep to firecrawl |
| `src/log_blog/cli.py` | Modify | Add `--deep` flag to `fetch` subcommand, pass to `fetch_pages` |
| `config.example.yaml` | Modify | Add `firecrawl` section |
| `pyproject.toml` | Modify | Add `firecrawl-py` dependency |
| `tests/test_firecrawl_fetcher.py` | Create | Unit tests for firecrawl_fetcher |
| `tests/test_content_fetcher_deep.py` | Create | Integration test for deep dispatch |
| `.claude/skills/log-blog-skill/SKILL.md` | Modify | Update Steps 3-5 for deep docs workflow |
| `skills/setup/SKILL.md` | Modify | Add Firecrawl API key prompt |

---

### Task 1: Add `firecrawl-py` Dependency

**Files:**
- Modify: `pyproject.toml:6-12`

- [ ] **Step 1: Add firecrawl-py to dependencies**

In `pyproject.toml`, add `firecrawl-py` to the dependencies list:

```toml
dependencies = [
    "firecrawl-py",
    "pillow",
    "playwright",
    "pyyaml",
    "rich",
    "youtube-transcript-api",
]
```

- [ ] **Step 2: Install the dependency**

Run:
```bash
uv sync
```

Expected: Successfully installs `firecrawl-py` and its dependencies.

- [ ] **Step 3: Verify import works**

Run:
```bash
uv run python -c "from firecrawl import Firecrawl; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add firecrawl-py dependency for deep docs fetching"
```

---

### Task 2: Add `FirecrawlConfig` to Config

**Files:**
- Modify: `src/log_blog/config.py:126-134` (Config dataclass)
- Modify: `src/log_blog/config.py:146-202` (load_config function)
- Test: `tests/test_config_firecrawl.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_firecrawl.py`:

```python
import tempfile
from pathlib import Path

from log_blog.config import load_config


def test_firecrawl_config_defaults():
    """FirecrawlConfig should have sensible defaults when not in YAML."""
    config = load_config(Path("/nonexistent/path"))
    assert config.firecrawl.api_key == ""
    assert config.firecrawl.max_pages == 10


def test_firecrawl_config_from_yaml():
    """FirecrawlConfig should load from YAML."""
    yaml_content = """
firecrawl:
  api_key: "fc-test-key"
  max_pages: 20
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = load_config(Path(f.name))

    assert config.firecrawl.api_key == "fc-test-key"
    assert config.firecrawl.max_pages == 20


def test_firecrawl_config_env_var(monkeypatch):
    """FirecrawlConfig should resolve ${ENV_VAR} in api_key."""
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-from-env")
    yaml_content = """
firecrawl:
  api_key: "${FIRECRAWL_API_KEY}"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = load_config(Path(f.name))

    assert config.firecrawl.api_key == "fc-from-env"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_firecrawl.py -v`

Expected: FAIL — `Config` has no `firecrawl` attribute.

- [ ] **Step 3: Add FirecrawlConfig dataclass and wire it into Config**

In `src/log_blog/config.py`, add the dataclass after `SessionsConfig` (around line 124):

```python
@dataclass
class FirecrawlConfig:
    api_key: str = ""
    max_pages: int = 10
```

Add the field to `Config` (after `sessions`):

```python
@dataclass
class Config:
    chrome: ChromeConfig = field(default_factory=ChromeConfig)
    time_range_hours: int = 24
    blog: BlogConfig = field(default_factory=BlogConfig)
    playwright: PlaywrightConfig = field(default_factory=PlaywrightConfig)
    accounts: AccountsConfig = field(default_factory=AccountsConfig)
    images: ImagesConfig = field(default_factory=ImagesConfig)
    sessions: SessionsConfig = field(default_factory=SessionsConfig)
    firecrawl: FirecrawlConfig = field(default_factory=FirecrawlConfig)
```

In `load_config()`, parse the firecrawl section. Add after the `sessions` line in the return statement:

```python
    # Parse firecrawl config
    firecrawl_data = dict(data.get("firecrawl", {}) or {})
    if "api_key" in firecrawl_data:
        firecrawl_data["api_key"] = _resolve_env_vars(str(firecrawl_data["api_key"]))
```

And add to the `Config(...)` constructor call:

```python
        firecrawl=FirecrawlConfig(**_filter_fields(FirecrawlConfig, firecrawl_data)),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_firecrawl.py -v`

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/log_blog/config.py tests/test_config_firecrawl.py
git commit -m "feat: add FirecrawlConfig to config system"
```

---

### Task 3: Create `firecrawl_fetcher.py`

**Files:**
- Create: `src/log_blog/firecrawl_fetcher.py`
- Test: `tests/test_firecrawl_fetcher.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_firecrawl_fetcher.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_firecrawl_fetcher.py -v`

Expected: FAIL — `log_blog.firecrawl_fetcher` does not exist.

- [ ] **Step 3: Implement firecrawl_fetcher.py**

Create `src/log_blog/firecrawl_fetcher.py`:

```python
from __future__ import annotations

import logging
from urllib.parse import urlparse

from .config import Config

logger = logging.getLogger(__name__)


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
        from firecrawl import Firecrawl

        client = Firecrawl(api_key=config.firecrawl.api_key)

        # Step 1: Map — discover sub-links on the docs site
        map_result = client.map(url=url, limit=100)
        all_links = map_result.get("links", [])

        if not all_links:
            # No sub-links found — scrape just the original URL
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_firecrawl_fetcher.py -v`

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/log_blog/firecrawl_fetcher.py tests/test_firecrawl_fetcher.py
git commit -m "feat: add firecrawl_fetcher module for deep docs crawling"
```

---

### Task 4: Integrate Deep Docs into `content_fetcher.py`

**Files:**
- Modify: `src/log_blog/content_fetcher.py:322-327` (`_fetch_batch` signature)
- Modify: `src/log_blog/content_fetcher.py:348-367` (URL bucketing)
- Modify: `src/log_blog/content_fetcher.py:451-453` (`fetch_pages`)
- Test: `tests/test_content_fetcher_deep.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_content_fetcher_deep.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_content_fetcher_deep.py -v`

Expected: FAIL — `fetch_pages` doesn't accept `deep_urls` parameter.

- [ ] **Step 3: Modify content_fetcher.py**

Update the `fetch_pages` function signature to accept `deep_urls`:

```python
def fetch_pages(
    urls: list[str],
    config: Config,
    deep_urls: set[str] | None = None,
) -> list[PageContent]:
    """Fetch page content for a list of URLs. Synchronous wrapper."""
    return asyncio.run(_fetch_batch(urls, config, deep_urls=deep_urls))
```

Update `_fetch_batch` signature:

```python
async def _fetch_batch(
    urls: list[str],
    config: Config,
    deep_urls: set[str] | None = None,
) -> list[PageContent]:
```

In the URL bucketing loop inside `_fetch_batch`, add deep docs handling. Replace the `else` clause (the `pw_direct_urls.append(url)` fallback, around line 367) with:

```python
            else:
                # Check if this is a deep docs request
                if deep_urls and url in deep_urls and url_type == UrlType.DOCS_PAGE:
                    from .firecrawl_fetcher import fetch_docs_deep
                    fc_result = fetch_docs_deep(url, config)
                    if fc_result is not None:
                        results[url] = fc_result
                        continue
                pw_direct_urls.append(url)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_content_fetcher_deep.py -v`

Expected: All 2 tests PASS.

- [ ] **Step 5: Run existing tests to check for regressions**

Run: `uv run pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/log_blog/content_fetcher.py tests/test_content_fetcher_deep.py
git commit -m "feat: route deep DOCS_PAGE URLs to Firecrawl in content_fetcher"
```

---

### Task 5: Add `--deep` Flag to CLI

**Files:**
- Modify: `src/log_blog/cli.py:146-183` (`cmd_fetch`)
- Modify: `src/log_blog/cli.py:718-721` (fetch argument parser)

- [ ] **Step 1: Add the `--deep` argument to the fetch parser**

In `cli.py`, find the fetch subparser section (around line 718-721). Add the `--deep` flag:

```python
    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch page content from URLs")
    p_fetch.add_argument("urls", nargs="+", help="URLs to fetch")
    p_fetch.add_argument("--json", action="store_true", help="Output as JSON")
    p_fetch.add_argument("--deep", action="store_true",
                         help="Use Firecrawl to deep-crawl documentation sites (fetches sub-pages)")
    p_fetch.set_defaults(func=cmd_fetch)
```

- [ ] **Step 2: Pass `deep_urls` to `fetch_pages` in `cmd_fetch`**

In `cmd_fetch` (around line 146-153), update to pass deep_urls:

```python
def cmd_fetch(args: argparse.Namespace) -> None:
    """Fetch content from URLs."""
    config = load_config(args.config)
    urls = args.urls

    deep_urls = set(urls) if args.deep else None

    if not args.json:
        if deep_urls:
            console.print(f"[blue]Deep-fetching {len(urls)} page(s) via Firecrawl...[/blue]")
        else:
            console.print(f"[blue]Fetching {len(urls)} page(s)...[/blue]")
    results = fetch_pages(urls, config, deep_urls=deep_urls)
```

- [ ] **Step 3: Verify the CLI flag is registered**

Run:
```bash
uv run log-blog fetch --help
```

Expected: Output includes `--deep` flag with description.

- [ ] **Step 4: Commit**

```bash
git add src/log_blog/cli.py
git commit -m "feat: add --deep flag to fetch command for Firecrawl deep docs"
```

---

### Task 6: Update `config.example.yaml`

**Files:**
- Modify: `config.example.yaml`

- [ ] **Step 1: Add firecrawl section**

Add after the `sessions:` section at the end of `config.example.yaml`:

```yaml

# Firecrawl deep docs fetching (optional).
# When enabled, documentation URLs can be deep-crawled to fetch sub-pages
# for more comprehensive blog posts. Get an API key at https://firecrawl.dev
firecrawl:
  api_key: "${FIRECRAWL_API_KEY}"  # Leave empty or unset to disable deep docs
  max_pages: 10                     # Max pages to crawl per documentation URL
```

- [ ] **Step 2: Commit**

```bash
git add config.example.yaml
git commit -m "docs: add firecrawl config section to example config"
```

---

### Task 7: Update the Blog Post Skill

**Files:**
- Modify: `.claude/skills/log-blog-skill/SKILL.md`

- [ ] **Step 1: Update Step 3 (Present to User)**

In the skill file, find the Step 3 section. In the presentation format for **Docs/Web** entries, add a deep docs annotation. Replace the Docs/Web line in the grouped list format:

```markdown
**Docs/Web:**
3. [Title](url) `[shallow]` ← default
4. [Title](url) `[shallow]`

Ask: *"Any docs entries you want me to deep-fetch? Deep mode crawls related sub-pages via Firecrawl for guide-style coverage. Just give me the numbers (e.g., '3, 4') or 'none'."*
```

- [ ] **Step 2: Update Step 4 (Fetch Enriched Content)**

Add a section after the existing fetch command documentation:

```markdown
### Deep docs fetching

For URLs the user selected for deep fetching, use the `--deep` flag:

```bash
uv run log-blog fetch --json --deep "DOCS_URL1" "DOCS_URL2"
```

Run shallow and deep fetches as separate commands — `--deep` applies to all URLs in that invocation. Combine the results.

Deep-fetched docs return `metadata.source = "firecrawl"` and `metadata.pages_crawled` showing how many sub-pages were crawled. The `text_content` contains combined markdown from all crawled pages, separated by page headers.

If Firecrawl is not configured (no API key), the command falls back to single-page Playwright fetch automatically.
```

- [ ] **Step 3: Update Step 5 (Write the Blog Post)**

In the "Writing Guidelines by URL Type" section, add a new entry for deep-fetched docs:

```markdown
**Docs (deep-fetched via Firecrawl):**
- Synthesize all crawled pages into a cohesive guide section
- Structure as: Overview → Key Concepts → Code Examples → Gotchas/Tips
- Don't just summarize each page separately — weave them into a narrative
- Reference specific sub-pages when citing details
- Note the total pages crawled in the section intro (e.g., "Based on N pages from the official docs...")
```

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/log-blog-skill/SKILL.md
git commit -m "feat: update skill for deep docs workflow in Steps 3-5"
```

---

### Task 8: Update the Setup Skill

**Files:**
- Modify: `skills/setup/SKILL.md`

- [ ] **Step 1: Add Firecrawl API key step to Phase 4**

In `skills/setup/SKILL.md`, find Phase 4 (Generate config.yaml). Add a new step after Step 2 (Detect gh username):

```markdown
### Step 2.5: Firecrawl API key (optional)

Ask the user:
> "Do you want to enable deep docs fetching? This uses Firecrawl to crawl documentation sub-pages for richer blog posts. It's optional — you can add it later."
> "If yes, get a free API key at https://firecrawl.dev and paste it here. Press Enter to skip."

If the user provides a key, store it for the config.yaml template.
If skipped, leave `firecrawl.api_key` empty in the generated config.
```

- [ ] **Step 2: Add firecrawl section to the config.yaml template**

In Step 3 (Write config.yaml) of Phase 4, add the firecrawl section to the YAML template:

```yaml
# Firecrawl deep docs fetching (optional).
# Deep-crawl documentation sites for guide-style blog posts.
# Get an API key at https://firecrawl.dev
firecrawl:
  api_key: "{firecrawl_api_key_if_provided}"
  max_pages: 10
```

Add to the "Key substitutions" list:
```
- `firecrawl.api_key` — from Step 2.5 (empty if skipped)
```

- [ ] **Step 3: Commit**

```bash
git add skills/setup/SKILL.md
git commit -m "feat: add Firecrawl API key prompt to setup skill"
```

---

### Task 9: End-to-End Verification

- [ ] **Step 1: Run all tests**

Run:
```bash
uv run pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Verify CLI help**

Run:
```bash
uv run log-blog fetch --help
```

Expected: Shows `--deep` flag with description "Use Firecrawl to deep-crawl documentation sites (fetches sub-pages)".

- [ ] **Step 3: Test shallow fetch still works (no regression)**

Run:
```bash
uv run log-blog fetch --json "https://docs.python.org/3/library/asyncio.html"
```

Expected: Returns single-page content via Playwright, `url_type: "docs_page"`, no Firecrawl involvement.

- [ ] **Step 4: Test deep fetch with API key (if available)**

If the user has a Firecrawl API key configured:

```bash
uv run log-blog fetch --json --deep "https://docs.firecrawl.dev/introduction"
```

Expected: Returns combined markdown from multiple sub-pages, `metadata.source: "firecrawl"`, `metadata.pages_crawled > 1`.

- [ ] **Step 5: Test deep fetch without API key (graceful fallback)**

Temporarily unset the API key in config.yaml, then:

```bash
uv run log-blog fetch --json --deep "https://docs.python.org/3/library/asyncio.html"
```

Expected: Falls back to Playwright, returns single-page content.

- [ ] **Step 6: Commit any fixes**

If any fixes were needed, commit them:

```bash
git add -A
git commit -m "fix: address issues found during e2e verification"
```
