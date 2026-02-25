# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
uv sync
uv run playwright install chromium

# Run the CLI
uv run log-blog extract
uv run log-blog extract --hours 48 --json
uv run log-blog fetch https://example.com --json
uv run log-blog publish post.md --push

# Launch Chrome with CDP for authenticated AI chat fetching
uv run log-blog chrome-cdp

# Run with a specific config file
uv run log-blog --config /path/to/config.yaml extract
```

There are no tests yet. There is no linting configuration; use standard Python conventions.

## Architecture

**log-blog** is a Python CLI tool (entry point: `log_blog.cli:main`) that reads Chrome browsing history and publishes a Hugo-compatible markdown blog post. The intended primary usage is via the Claude Code skill at `.claude/`, where Claude AI acts as the intelligence layer to classify, summarize, and write the post.

### Data flow

```
Chrome SQLite DB → history_reader → list[HistoryEntry]
                                          ↓
                         url_classifier (classify each URL by type)
                                          ↓
                    ┌─────────────────────┼──────────────────────┐
               YouTube              GitHub repo/PR/issue      Web page / Docs
          youtube_fetcher         github_fetcher (gh CLI)    Playwright browser
          (transcript API)         structured dict             text_content
                    └─────────────────────┼──────────────────────┘
                                    list[PageContent]
                                          ↓
                                   post_generator → markdown string
                                          ↓
                                     publisher → git commit/push to blog repo
```

### Key modules

- **`url_classifier.py`** — Regex-based dispatch table. Classifies a URL into `UrlType` enum (YouTube, GitHub repo/PR/issue, Bitbucket, AI chats, docs page, web page). This determines which fetcher is used.
- **`content_fetcher.py`** — Orchestrates fetching. Calls specialized fetchers first; falls back to Playwright for all others. Uses `asyncio.Semaphore` for concurrency control. Returns `list[PageContent]`.
- **`PageContent`** dataclass — The universal return type from all fetchers: `url`, `title`, `text_content`, `success`, `error`, `url_type`, `metadata`.
- **`github_fetcher.py`** — Uses the `gh` CLI (must be authenticated). Fetches repo metadata + README, PR details, or issue details. Returns a structured dict, then `content_fetcher` converts it to `PageContent`.
- **`youtube_fetcher.py`** — Uses `youtube-transcript-api`. Tries Korean → English → any language. Falls back to Playwright if transcript unavailable.
- **`post_generator.py`** — Generates Hugo frontmatter + markdown. Accepts pre-written `introduction`, `highlights`, `quick_links`, `insights` from the Claude skill. Falls back to a plain link list if none are provided.
- **`publisher.py`** — Clones the blog repo if missing, pulls latest, writes the file, `git add` + `git commit`, optionally `git push`.
- **`config.py`** — Loads `config.yaml` from the project root. Falls back to hardcoded defaults. All path fields support `~` expansion.

### Configuration

Copy `config.example.yaml` → `config.yaml`. Key fields:
- `chrome.profiles` — list of Chrome profile folder names (e.g., `["Default", "Profile 1"]`)
- `blog.repo_path` — local path to the Hugo blog repo (cloned automatically if missing)
- `blog.language` — `"auto"`, `"ko"`, or `"en"`
- `playwright.max_concurrent` — controls how many browser pages run in parallel
- `playwright.cdp_port` — Chrome DevTools Protocol port for authenticated AI chat fetching (default: 9222)

### External dependencies

- **Playwright/Chromium** — headless browser for generic web pages; must be installed separately with `uv run playwright install chromium`
- **gh CLI** — must be installed and authenticated (`gh auth login`) for GitHub URL enrichment
- **youtube-transcript-api** — Python package, already in dependencies
