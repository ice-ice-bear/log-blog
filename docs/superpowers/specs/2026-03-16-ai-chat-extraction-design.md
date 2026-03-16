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
    AI_LANDING = "ai_landing"  # Noise: landing/oauth/settings pages
```

Note: `AI_CHAT_CLAUDE_CODE` is NOT added — Claude Code runs in terminal, not the browser. Chrome history contains only `claude.ai/code` (landing page) and `claude.ai/code/onboarding`, which are noise. There are no per-session URLs in Chrome history for Claude Code.

#### New conversation patterns

| Pattern | Type |
|---------|------|
| `gemini.google.com/share/{id}` | `AI_CHAT_GEMINI` |

Note: `claude.ai/project/{uuid}` is NOT classified as `AI_CHAT_CLAUDE` — project pages are organizational dashboards, not conversations. They are included in the noise filter instead.

#### Noise filter patterns (checked before conversation patterns)

A new noise check runs **before** the per-domain conversation matching blocks in `classify_url()`. This is a structural change: the current code has `if "claude.ai" in url: ...` blocks with inline `_warn_unmatched_ai()` calls. The new flow is:

1. Check `_AI_NOISE_PATTERNS` → return `AI_LANDING` immediately
2. Then check per-domain conversation patterns (existing flow)
3. `_warn_unmatched_ai()` only fires for URLs that pass the noise filter but fail the conversation pattern

```python
_AI_NOISE_PATTERNS = [
    re.compile(r"claude\.ai/(?:oauth|chrome|code|project)(?:/|[?#]|$)"),
    re.compile(r"claude\.ai/?(?:[?#]|$)"),
    re.compile(r"chatgpt\.com/(?:auth|backend-api|gpts)?/?(?:[?#]|$)"),
    re.compile(r"gemini\.google\.com/(?:app(?:/(?:download|extensions|settings))?)?/?(?:[?#]|$)"),
    re.compile(r"gemini\.google\.com/?(?:[?#]|$)"),
    re.compile(r"perplexity\.ai/?(?:[?#]|$)"),
]
```

Noise patterns are checked first. If matched → `UrlType.AI_LANDING`. This prevents:
- Wasting Playwright fetch slots on login walls
- Cluttering extract output for the skill
- Warning log spam from `_warn_unmatched_ai()`

The existing `_AI_CHAT_DOMAINS` tuple (line 79) remains unchanged — it is only used by `_warn_unmatched_ai()`, which now only fires for URLs that pass the noise filter.

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
- `extract --json --include-noise`: includes `AI_LANDING` entries too

This adds a lightweight dependency: `cmd_extract()` imports `classify_url` from `url_classifier`. Classification runs on every URL during extract (regex matching ~3,500 URLs is negligible).

This makes the skill's Step 2 classification reliable — uses the same regex engine as the fetch pipeline.

### 3. AI Chat Fetcher Updates (`ai_chat_fetcher.py`)

#### Gemini share links

- `gemini.google.com/share/{id}` — publicly accessible, no CDP needed
- Add `_extract_gemini_share()` with share-page-specific DOM selectors
- Falls back to generic Playwright if DOM structure is unrecognized

#### Claude Code sessions

Claude Code runs in terminal — Chrome history only contains `claude.ai/code` (landing page), not per-session URLs. These are classified as `AI_LANDING` noise and filtered out.

Users who want Claude conversation content in their blog posts should use the offline export path:
```bash
uv run log-blog import-ai ~/path/to/claude-export.json --json --days 7
```

### 4. Skill Update (`SKILL.md`)

#### Step 2 simplification

When extract output includes `url_type`, the skill groups by type directly instead of Claude manually classifying URLs.

#### Step 3 note on Claude conversations

Claude Code URLs are filtered as noise. If the user wants Claude conversation content, the skill should mention the offline export path:

> "To include Claude conversations, export your data from claude.ai → Settings → Export, then run `uv run log-blog import-ai ~/path/to/claude-export.json`."

## Files to Modify

1. **`src/log_blog/url_classifier.py`** — Add `AI_LANDING` type; add noise patterns checked before conversation matching; expand `_GEMINI` regex to also match `gemini.google.com/share/{id}`
2. **`src/log_blog/cli.py`** — Add `url_type` to `extract --json` output; add `--include-noise` flag
3. **`src/log_blog/ai_chat_fetcher.py`** — Add `_extract_gemini_share()` for share-page DOM extraction
4. **`src/log_blog/content_fetcher.py`** — Handle `AI_LANDING` (skip entirely, return `PageContent(success=False, error="AI landing page, no content to fetch")`). Add early-return check before the type-based dispatch buckets. Do NOT add `AI_LANDING` to `_AI_CHAT_TYPES` or `_AI_CHAT_SERVICE_MAP`.
5. **`.claude/skills/log-blog-skill/SKILL.md`** — Update Steps 2 and 3

## Out of Scope

- API-based conversation fetching (future work if scraping proves too brittle)
- Perplexity collections support (no URLs in current history to validate against)
- Configurable content length limits (current 12,000 char limit is sufficient)
