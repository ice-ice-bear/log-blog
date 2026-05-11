# logblog

A Claude Code plugin that turns your Chrome browsing history into polished tech blog posts on your Hugo site.

## Overview

logblog reads your Chrome browsing history, classifies URLs by content type (YouTube, GitHub, docs, web pages), fetches enriched content from each source, and uses Claude AI to write and publish a deep-dive blog post to your Hugo blog — all from a single slash command.

## Skills

### `/logblog:post`

Creates a tech blog post from your recent browsing history.

**What it does:**

1. Extracts Chrome browsing history and Claude Code sessions
2. Classifies each URL by type (YouTube, GitHub repo/PR/issue, docs, web page, AI chats)
3. Shows you the classified list and asks for approval
4. Fetches enriched content — transcripts for YouTube, structured data for GitHub, full text for web pages, deep-crawled docs via Firecrawl
5. Writes a deep-dive technical blog post in English, then translates to Korean (bilingual workflow)
6. Generates a cover image and publishes both versions to your Hugo blog repo

**Usage:**

```
/logblog:post
```

**Features:**

- Automatic URL classification via regex dispatch table
- YouTube transcript extraction (Korean → English → any language fallback)
- GitHub and Bitbucket repo/PR/issue enrichment via `gh` CLI and REST API
- AI chat fetching from ChatGPT, Claude, Gemini, and Perplexity via Chrome CDP
- Deep docs crawling via Firecrawl — fetches sub-pages for guide-style coverage
- Dev log mode — turns Claude Code sessions into narrative development posts
- Bilingual publishing — writes in English, translates to Korean, publishes both
- Concurrent page fetching with Playwright
- Separate posts per topic (not combined daily logs)
- Cover image generation with PIL gradients
- Hugo frontmatter with tags, categories, and cover image

### `/logblog:kakao-post`

Creates tech blog posts from URLs people have shared in **a user-selected subset** of KakaoTalk open chats. The chat is the data source — never the subject of the post.

**What it does:**

1. Lists open chats with unread messages (uses [`kakao-chat`](https://github.com/ice-ice-bear/kakaotalk-chat-analyzer) CLI)
2. You pick which chats to mine (1-5 typical, never bulk-publish all)
3. Extracts the unread URLs and filters them by source tier (GitHub repos, arxiv, vendor blogs, etc.)
4. Shows you ~20 candidates and lets you pick 5-15 to write up, with optional groupings (e.g., bundle 5 same-day vendor announcements into one digest post)
5. Multi-agent dispatch for batch writing — one agent per post in parallel
6. Writes Korean+English posts with inline links throughout, mermaid diagrams, and a categorized References section
7. Publishes to your Hugo blog the same way `/logblog:post` does

**Strict source-hiding rule:** Published posts never mention KakaoTalk, 카카오톡, 채팅방, 오픈채팅, open chat, or chat threads. The blog reads as if you encountered each announcement directly. The skill includes pre- and post-publish self-check greps to enforce this.

**Usage:**

```
/logblog:kakao-post
```

**Prerequisites:**

- Run `/logblog:kakao-setup` once on a new machine to install kakaocli, derive the `KAKAOCLI_KEY`, and install the wrapper
- `config.yaml` already configured (run `/logblog:setup` if not)

### `/logblog:kakao-setup`

One-shot installer for everything `/logblog:kakao-post` depends on. macOS only.

**What it does:**

1. Diagnoses environment — Homebrew, full Xcode (not just Command Line Tools), KakaoTalk app, Full Disk Access
2. Installs kakaocli via `brew install silver-flight-group/tap/kakaocli`
3. Clones the [kakaotalk-chat-analyzer](https://github.com/ice-ice-bear/kakaotalk-chat-analyzer) wrapper and adds a `kakao-chat()` shell function so the wrapper is on PATH
4. Derives the `KAKAOCLI_KEY` (SQLCipher decryption key) — tries `kakaocli auth` first, falls back to a SHA-512 brute-force of the User ID when auto-auth times out (handles User IDs above ~22M)
5. Persists the key to your `~/.zshrc` (or `~/.bashrc`)
6. Runs three smoke tests end-to-end (`kakaocli chats` → `kakao-chat unread`)

**Usage:**

```
/logblog:kakao-setup
```

Run this once per machine. After it succeeds, `/logblog:kakao-post` works without further setup.

### `/logblog:setup`

Sets up a GitHub Pages blog with Hugo and the Stack theme from scratch.

**What it does:**

1. Installs Hugo and initializes a new site (or connects to an existing one)
2. Configures the Stack theme with your preferences
3. Sets up GitHub Pages deployment via GitHub Actions
4. Creates `config.yaml` to link log-blog to your blog repo
5. Verifies the full pipeline works end-to-end

**Usage:**

```
/logblog:setup
```

**Features:**

- Zero-to-published blog in one command
- Hugo Stack theme configuration
- GitHub Actions deployment setup
- Multi-account SSH configuration guidance
- Automatic `config.yaml` generation

## Installation

In Claude Code, open the plugin menu and add the marketplace, then install:

```
/plugin  →  Marketplaces  →  Add  →  ice-ice-bear/log-blog
/plugin  →  Discover  →  logblog  →  Install for you (user scope)
```

After installation, run `/reload-plugins` to activate. Verify with:

```
/logblog:post    # Create a blog post from browsing history
/logblog:setup   # Set up a new Hugo blog
```

To update after new releases:

```
/plugin  →  Installed  →  logblog  →  Update now
```

### Python Dependencies

```bash
# Requires Python 3.12+ and uv
uv sync
uv run playwright install chromium
```

### Configuration

Copy and edit the config file:

```bash
cp config.example.yaml config.yaml
```

```yaml
chrome:
  google_accounts: ["you@gmail.com"]
  history_db_base: "~/Library/Application Support/Google/Chrome"

time_range_hours: 24

blog:
  repo_path: "~/path/to/your-blog-repo"
  repo_url: "https://github.com/you/your-blog.git"
  content_dir: "content/posts"
  language_content_dirs:
    ko: "content/ko/posts"
    en: "content/en/posts"
  default_language: "en"
  language: "auto"  # "auto", "ko", "en"

playwright:
  headless: true
  timeout_ms: 15000
  max_concurrent: 5
  cdp_port: 9222

# Optional: deep docs crawling via Firecrawl
firecrawl:
  api_key: "${FIRECRAWL_API_KEY}"
  max_pages: 10
```

## CLI Usage

logblog also provides a standalone CLI for use outside Claude Code:

```bash
# Extract browsing history
uv run log-blog extract              # Pretty table of last 24h
uv run log-blog extract --hours 48   # Override time range
uv run log-blog extract --json       # JSON output

# Fetch page content
uv run log-blog fetch https://example.com --json
uv run log-blog fetch --deep https://docs.example.com/guide --json  # Deep-crawl docs via Firecrawl

# Dev log from Claude Code sessions
uv run log-blog sessions --list      # List recent coding projects
uv run log-blog sessions --project my-app --all --json  # Detailed session data

# Publish a markdown post
uv run log-blog publish post.md --push
uv run log-blog publish post.md --language ko  # Publish to Korean content dir

# Launch Chrome with CDP for authenticated AI chat fetching
uv run log-blog chrome-cdp

# Import AI chat exports (offline)
uv run log-blog import-ai ~/Downloads/conversations.json --json
```

## Requirements

| Requirement | Purpose |
|---|---|
| Python 3.12+ | Runtime |
| [uv](https://docs.astral.sh/uv/) | Package manager |
| Chromium (via Playwright) | Fetching web page content |
| [`gh` CLI](https://cli.github.com/) (authenticated) | Fetching GitHub repo/PR/issue data |
| Hugo blog repo | Publish destination |
| [Firecrawl API key](https://firecrawl.dev) (optional) | Deep docs crawling |

## Troubleshooting

**Issue:** `gh` commands fail with authentication errors
**Solution:** Run `gh auth login` to authenticate the GitHub CLI

**Issue:** Playwright times out on certain pages
**Solution:** Increase `playwright.timeout_ms` in `config.yaml` or reduce `max_concurrent`

**Issue:** Chrome history database is locked
**Solution:** Close Chrome before running `extract`, or use a different profile

**Issue:** Blog push fails with permission denied
**Solution:** Verify SSH keys are configured for the correct GitHub account. See the [multi-account SSH setup guide](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys) if using multiple accounts

## Tips

- Run `/logblog:post` at the end of a work session to capture what you learned
- Review the classified URL list carefully — remove irrelevant entries before fetching
- Use `--hours 48` in the CLI to capture a weekend session
- Each topic gets its own post with a unique filename to avoid overwriting

## Author

**ice-ice-bear**

## Version

0.3.0

## License

MIT
