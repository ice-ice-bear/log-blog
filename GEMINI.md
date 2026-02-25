# GEMINI.md - log-blog Project Context

## Project Overview
`log-blog` is a Python-based CLI tool designed to automate the creation of technical blog posts for Hugo-based websites by analyzing the user's Chrome browsing history. It bridges the gap between daily technical research/reading and content creation, using Playwright for web scraping and specialized fetchers for GitHub and YouTube.

### Main Technologies
- **Python 3.12+**: Core language.
- **uv**: Project and dependency management.
- **Playwright**: Headless browser automation for fetching web content.
- **SQLite**: Direct reading of Chrome's history database.
- **GitHub CLI (gh)**: Enriched data extraction for repositories, PRs, and issues.
- **youtube-transcript-api**: Automatic transcript extraction for YouTube videos.
- **Rich**: Enhanced terminal output and progress visualization.
- **Claude AI**: Integrated via a custom skill (`.claude/skills/log-blog-skill/`) to classify history and generate polished summaries.

## Building and Running

### Setup
1. **Install dependencies**:
   ```bash
   uv sync
   ```
2. **Install Playwright browser**:
   ```bash
   uv run playwright install chromium
   ```
3. **Configure**:
   ```bash
   cp config.example.yaml config.yaml
   # Edit config.yaml with your Chrome profile paths and blog repository location.
   ```

### Execution
- **Extract History**: `log-blog extract [--hours N] [--json]`
- **Fetch Content**: `log-blog fetch <URL1> <URL2> ...`
- **Publish Post**: `log-blog publish <FILE.md> [--push] [--filename NAME]`

## Project Architecture

- `src/log_blog/cli.py`: Command-line interface entry point.
- `src/log_blog/history_reader.py`: Logic for reading and filtering Chrome's SQLite history files (handles file locking by creating temporary copies).
- `src/log_blog/content_fetcher.py`: Master fetcher that dispatches URLs to specialized modules or Playwright.
- `src/log_blog/github_fetcher.py`: Uses `gh` CLI to get structured data for repos, PRs, and issues.
- `src/log_blog/youtube_fetcher.py`: Extracts transcripts for video content.
- `src/log_blog/url_classifier.py`: Determines the type of URL to choose the best fetching strategy.
- `src/log_blog/post_generator.py`: Generates Hugo-compatible Markdown files with appropriate frontmatter.
- `src/log_blog/publisher.py`: Automates the Git workflow (pull, commit, push) for the target blog repository.

## Development Conventions

- **Type Hinting**: Extensive use of Python type hints for clarity and safety.
- **Asyncio**: Used for concurrent page fetching in Playwright to improve performance.
- **CLI Design**: Follows a subcommand pattern (`extract`, `fetch`, `publish`).
- **Data Classes**: Used for structured data passing between modules (e.g., `HistoryEntry`, `PageContent`).
- **Claude Integration**: The project is optimized to work with Claude Code, providing a specialized skill that handles the AI reasoning layer (classification and summarization).

## Key Files
- `pyproject.toml`: Defines dependencies and the `log-blog` entry point.
- `config.example.yaml`: Template for user-specific configuration (Chrome paths, blog repo path).
- `.claude/skills/log-blog-skill/SKILL.md`: Documentation and implementation for the Claude Code skill.
- `scripts/migrate_jekyll_to_hugo.py`: A utility script for legacy content migration.
