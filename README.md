# log-blog

A CLI tool that reads your Chrome browsing history and turns it into a tech blog post for your Hugo site.

## How it works

1. **Extract** — Reads Chrome's SQLite history database for the last N hours
2. **Fetch** — Uses Playwright to visit URLs and extract article content
3. **Publish** — Generates a Hugo-compatible markdown post and commits it to your blog repo

When used with the Claude Code skill (included in this repo), Claude AI classifies your browsing into tech topics, writes summaries, and publishes a polished blog post.

## Setup

```bash
# Requires Python 3.12+
uv sync
uv run playwright install chromium
```

Copy and edit the config:

```bash
cp config.example.yaml config.yaml
```

### Configuration

```yaml
chrome:
  profiles: ["Default"]
  history_db_base: "~/Library/Application Support/Google/Chrome"

time_range_hours: 24

blog:
  repo_path: "~/path/to/your-blog-repo"
  repo_url: "https://github.com/you/your-blog.git"
  content_dir: "content/posts"
  language: "auto"  # "auto", "ko", "en"

playwright:
  headless: true
  timeout_ms: 15000
  max_concurrent: 5
```

## Usage

### Extract browsing history

```bash
log-blog extract              # Pretty table of last 24h
log-blog extract --hours 48   # Override time range
log-blog extract --json       # JSON output
```

### Fetch page content

```bash
log-blog fetch https://example.com https://another.com
log-blog fetch --json https://example.com
```

### Publish a markdown post

```bash
log-blog publish post.md                  # Commit locally
log-blog publish post.md --push           # Commit and push
log-blog publish post.md --filename custom-name.md
```

## Project structure

```
src/log_blog/
  cli.py             # CLI entry point (extract, fetch, publish)
  config.py          # YAML config loader
  history_reader.py  # Chrome SQLite history reader
  content_fetcher.py # Playwright-based page content extractor
  post_generator.py  # Hugo markdown post generator
  publisher.py       # Git commit/push to blog repo
scripts/
  migrate_jekyll_to_hugo.py
```

## Claude Code skill

This repo ships a `/log-blog` skill for [Claude Code](https://claude.ai/code) in [`.claude/skills/log-blog-skill/`](.claude/skills/log-blog-skill/SKILL.md). When you open this project in Claude Code, the skill is automatically available — no global install needed.

### Usage

Type `/log-blog` in Claude Code to start the pipeline. Claude will:

1. Extract your Chrome history for the last 24 hours
2. Show you a classified list (tech vs. non-tech) and ask for approval
3. Fetch enriched content — transcripts for YouTube, structured data for GitHub repos/PRs/issues, full text for web pages
4. Write a deep-dive technical blog post in your preferred language
5. Publish it to your Hugo blog repo and optionally push to GitHub

### Skill lookup order

Claude Code checks the local `.claude/skills/` directory first. If you also have the skill installed globally (`~/.claude/skills/log-blog-skill/`), the local version takes precedence when you're inside this repo. Both can coexist.

### Required tools

| Tool | Why |
|---|---|
| `gh` CLI (authenticated) | Fetching GitHub repo/PR/issue content |
| Chromium (via Playwright) | Fetching generic web pages |
| `config.yaml` | Blog repo path, Chrome profile, language |

## License

MIT
