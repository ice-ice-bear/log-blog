# AI Chat Extraction Improvement — Design Spec

**Date**: 2026-03-16
**Status**: Approved
**Problem**: AI chat URLs from Chrome history aren't being properly classified or surfaced. Most fall through to `web_page` type, causing the skill to miss them entirely.

## Root Cause Analysis

Examined Chrome history across two profiles (Default, Profile 1) and found 96 AI-service URLs out of 3,575 total entries. Of those 96:

- **Claude**: Dominated by `claude.ai/code/*` (Claude Code sessions), `claude.ai/oauth/*`, `claude.ai/chrome/*` — none matched the `claude.ai/chat/{uuid}` pattern
- **ChatGPT**: Only 1 conversation URL (`chatgpt.com/c/...`), rest are landing pages
- **Gemini**: Many conversation URLs (`gemini.google.com/app/{id}`) match correctly, but `gemini.google.com/share/{id}` links are missed
- **Perplexity**: No URLs found in history

The classifier correctly identifies per-conversation URLs, but the user's actual browsing patterns don't match the expected patterns (Claude Code vs web UI, share links vs direct links).

## Design

### 1. URL Classifier Expansion (`url_classifier.py`)

#### New URL type

```python
class UrlType(str, Enum):
    # ... existing types ...
    AI_CHAT_CLAUDE_CODE = "ai_chat_claude_code"  # Not browser-scrapable
    AI_LANDING = "ai_landing"                     # Noise: landing/oauth/settings pages
```

#### New conversation patterns

| Pattern | Type |
|---------|------|
| `gemini.google.com/share/{id}` | `AI_CHAT_GEMINI` |
| `claude.ai/project/{uuid}` | `AI_CHAT_CLAUDE` |
| `claude.ai/code/session_{id}` | `AI_CHAT_CLAUDE_CODE` |

#### Noise filter patterns (checked before conversation patterns)

```python
_AI_NOISE_PATTERNS = [
    re.compile(r"claude\.ai/(?:oauth|chrome|code(?:/(?:onboarding|family))?)?(?:[?#]|$)"),
    re.compile(r"chatgpt\.com/?(?:[?#]|$)"),
    re.compile(r"gemini\.google\.com/(?:app)?(?:/download)?(?:[?#]|$)"),
    re.compile(r"gemini\.google\.com/?(?:[?#]|$)"),
    re.compile(r"perplexity\.ai/?(?:[?#]|$)"),
]
```

Noise patterns are checked first. If matched → `UrlType.AI_LANDING`. This prevents:
- Wasting Playwright fetch slots on login walls
- Cluttering extract output for the skill
- Warning log spam from `_warn_unmatched_ai()`

### 2. Extract Command Enhancement (`cli.py`)

Add `url_type` field to `--json` output by running each URL through `classify_url()`:

```json
{
  "url": "https://gemini.google.com/app/b316486a7f8fd8b7?is_sa=1",
  "title": "Google Gemini",
  "visit_count": 3,
  "last_visit_time": "2026-03-15T10:00:00+00:00",
  "url_type": "ai_chat_gemini"
}
```

Filtering behavior:
- `extract --json`: excludes `AI_LANDING` by default
- `extract --json --all`: includes everything

This makes the skill's Step 2 classification reliable — uses the same regex engine as the fetch pipeline.

### 3. AI Chat Fetcher Updates (`ai_chat_fetcher.py`)

#### Gemini share links

- `gemini.google.com/share/{id}` — publicly accessible, no CDP needed
- Add `_extract_gemini_share()` with share-page-specific DOM selectors
- Falls back to generic Playwright if DOM structure is unrecognized

#### Claude Code sessions

- **Not browser-scrapable** — Claude Code UI doesn't render conversation content in standard DOM
- Strategy: surface in extract output with `url_type: "ai_chat_claude_code"` so the skill can inform the user
- The skill shows: "Claude Code sessions detected — use `uv run log-blog import-ai` with your Claude export to include them"
- No fetch attempt is made for these URLs

### 4. Skill Update (`SKILL.md`)

#### Step 2 simplification

When extract output includes `url_type`, the skill groups by type directly instead of Claude manually classifying URLs.

#### Step 3 Claude Code note

For any `ai_chat_claude_code` entries, display:

> "Claude Code sessions detected — these require export data. Run `uv run log-blog import-ai ~/path/to/claude-export.json` to include them."

## Files to Modify

1. **`src/log_blog/url_classifier.py`** — Add `AI_CHAT_CLAUDE_CODE`, `AI_LANDING` types; add noise patterns; expand conversation patterns
2. **`src/log_blog/cli.py`** — Add `url_type` to `extract --json` output; add `--all` flag
3. **`src/log_blog/ai_chat_fetcher.py`** — Add `_extract_gemini_share()`; skip `AI_CHAT_CLAUDE_CODE`
4. **`src/log_blog/content_fetcher.py`** — Handle `AI_LANDING` (skip) and `AI_CHAT_CLAUDE_CODE` (skip with metadata)
5. **`.claude/skills/log-blog-skill/SKILL.md`** — Update Steps 2 and 3

## Out of Scope

- API-based conversation fetching (future work if scraping proves too brittle)
- Perplexity collections support (no URLs in current history to validate against)
- Configurable content length limits (current 12,000 char limit is sufficient)
