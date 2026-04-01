# Firecrawl Deep Docs Integration

**Date:** 2026-04-01
**Status:** Approved

## Summary

Add Firecrawl as an optional fetcher for `DOCS_PAGE` URLs. When the skill presents classified URLs (Step 4), docs URLs get a "shallow/deep" choice. Deep mode uses Firecrawl to crawl sub-links under the same path prefix, returning up to N pages (default 10, configurable). The skill synthesizes crawled content into a guide-style section (overview, key concepts, examples, gotchas).

## Motivation

Currently, docs pages are fetched with Playwright — one page at a time. This produces shallow summaries. For guide-style blog posts, the AI needs broader context from related docs pages (sibling sections, sub-pages). Firecrawl's map + batch scrape fills this gap.

## Architecture

### New Module: `firecrawl_fetcher.py`

Location: `src/log_blog/firecrawl_fetcher.py`

Wraps the Firecrawl Python SDK (`firecrawl-py`). Exports:

```python
async def fetch_docs_deep(url: str, config: Config) -> PageContent
```

Internal flow:
1. `map(url)` — discover all links on the docs site
2. Filter to same path prefix as the input URL
3. Limit to `config.firecrawl.max_pages` (default 10)
4. `batch_scrape(filtered_urls, formats=["markdown"])` — fetch each as markdown
5. Combine all markdown into a single `text_content` with page separators
6. Return `PageContent` with:
   - `url_type = "docs_page"`
   - `metadata = {"source": "firecrawl", "pages_crawled": N, "sub_urls": [...]}`

### Integration: `content_fetcher.py`

New dispatch branch in `_fetch_batch()`:

- When `url_type == DOCS_PAGE` and `deep=True` for that URL:
  - Route to `firecrawl_fetcher.fetch_docs_deep()`
  - On failure (no API key, API error, 0 results): fall back to Playwright single-page fetch

The `deep` flag is passed per-URL via a new parameter to `fetch_pages()`.

### Config: `config.py` + `config.example.yaml`

New config section:

```yaml
firecrawl:
  api_key: "${FIRECRAWL_API_KEY}"   # required for deep docs
  max_pages: 10                      # max pages to crawl per URL
```

New dataclass:

```python
@dataclass
class FirecrawlConfig:
    api_key: str = ""
    max_pages: int = 10
```

Added as `Config.firecrawl: FirecrawlConfig`.

### CLI: `cli.py`

`fetch` command gains a `--deep` flag:

```bash
uv run log-blog fetch --json --deep "https://docs.example.com/guides/intro"
```

When `--deep` is set, all provided URLs are marked for deep Firecrawl fetch. URLs that are not `DOCS_PAGE` type ignore the flag and fetch normally.

### Skill: `.claude/skills/log-blog-skill/SKILL.md`

**Step 4 (present for approval):**
- Docs URLs are shown with a `[shallow/deep]` annotation
- Skill asks user which docs URLs to fetch deeply

**Step 5 (fetch):**
- Pass `--deep` flag for user-selected deep URLs
- Separate fetch calls if needed: one with `--deep` for deep URLs, one without for the rest

**Step 6 (write post):**
- Deep-fetched docs content is synthesized into a guide-style section:
  - Overview of the technology/feature
  - Key concepts extracted from multiple pages
  - Code examples (consolidated, not duplicated)
  - Gotchas and common mistakes

### Setup Skill: `/logblog:setup`

Add an optional step to the setup flow:
- Prompt user for Firecrawl API key
- Explain it's optional (only needed for deep docs fetching)
- If provided, write to `config.yaml` under `firecrawl.api_key`

## Data Flow

```
User selects "deep" for docs URL
        |
fetch --json --deep "https://docs.example.com/guides/intro"
        |
content_fetcher: url_type=DOCS_PAGE + deep=True
        |
firecrawl_fetcher.fetch_docs_deep(url, config)
        |
    1. map(url) -> discover sub-links
    2. filter: same path prefix only
    3. limit to config.firecrawl.max_pages
    4. batch_scrape(filtered_urls) -> markdown[]
    5. combine into single text_content
        |
PageContent(url_type="docs_page", metadata={source: "firecrawl", pages_crawled: N})
        |
Skill synthesizes into guide section
```

## Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| No API key configured | Skip Firecrawl, use Playwright, warn user |
| Firecrawl API error | Fall back to Playwright for that URL |
| `map()` returns 0 sub-links | Scrape just the original URL via Firecrawl |
| URL is not `DOCS_PAGE` type | Ignore `--deep` flag, fetch normally |

## Dependencies

- Add `firecrawl-py` to `pyproject.toml`

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/log_blog/firecrawl_fetcher.py` | Create — new fetcher module |
| `src/log_blog/content_fetcher.py` | Modify — add deep docs dispatch branch |
| `src/log_blog/config.py` | Modify — add `FirecrawlConfig` dataclass |
| `src/log_blog/cli.py` | Modify — add `--deep` flag to `fetch` command |
| `config.example.yaml` | Modify — add `firecrawl` section |
| `pyproject.toml` | Modify — add `firecrawl-py` dependency |
| `.claude/skills/log-blog-skill/SKILL.md` | Modify — update Steps 4, 5, 6 for deep docs |
| `.claude/skills/logblog-setup/SKILL.md` | Modify — add Firecrawl API key prompt |
