# AI Chat Extraction Improvement — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix AI chat URL classification so that conversation URLs are properly identified and noise URLs are filtered out, and add Gemini share link support.

**Architecture:** Add a noise-filter layer before conversation-pattern matching in `classify_url()`, expand the Gemini regex to include share links, add `url_type` to `extract --json` output, and handle `AI_LANDING` in the fetch pipeline.

**Tech Stack:** Python 3.12, pytest (new dependency), regex, Playwright (existing)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/log_blog/url_classifier.py` | Modify | Add `AI_LANDING` type, noise patterns, Gemini share regex |
| `src/log_blog/cli.py` | Modify | Add `url_type` to extract JSON, add `--include-noise` flag |
| `src/log_blog/content_fetcher.py` | Modify | Early-return for `AI_LANDING` URLs |
| `src/log_blog/ai_chat_fetcher.py` | Modify | Add `_extract_gemini_share()` |
| `.claude/skills/log-blog-skill/SKILL.md` | Modify | Update Steps 2 and 3 |
| `tests/test_url_classifier.py` | Create | Unit tests for classification |
| `tests/test_extract_json.py` | Create | Tests for extract JSON output |
| `pyproject.toml` | Modify | Add pytest dev dependency |

## Chunk 1: Test Infrastructure + URL Classifier

### Task 1: Add pytest dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pytest to pyproject.toml**

Add `[project.optional-dependencies]` section:

```toml
[project.optional-dependencies]
dev = ["pytest"]
```

- [ ] **Step 2: Install dev dependencies**

Run: `uv sync --extra dev`
Expected: pytest installed successfully

- [ ] **Step 3: Create tests directory**

Run: `mkdir -p tests`

- [ ] **Step 4: Verify pytest runs**

Run: `uv run pytest --version`
Expected: prints pytest version

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pytest dev dependency"
```

---

### Task 2: Add AI_LANDING type and noise patterns to url_classifier.py

**Files:**
- Create: `tests/test_url_classifier.py`
- Modify: `src/log_blog/url_classifier.py`

- [ ] **Step 1: Write failing tests for noise URL classification**

```python
# tests/test_url_classifier.py
from log_blog.url_classifier import classify_url, UrlType


class TestAiLandingNoise:
    """AI service landing/oauth/settings pages should be classified as AI_LANDING."""

    def test_claude_landing(self):
        assert classify_url("https://claude.ai/") == UrlType.AI_LANDING

    def test_claude_oauth(self):
        assert classify_url("https://claude.ai/oauth/authorize?client_id=abc") == UrlType.AI_LANDING

    def test_claude_chrome_extension(self):
        assert classify_url("https://claude.ai/chrome/installed") == UrlType.AI_LANDING

    def test_claude_chrome(self):
        assert classify_url("https://claude.ai/chrome") == UrlType.AI_LANDING

    def test_claude_code_landing(self):
        assert classify_url("https://claude.ai/code") == UrlType.AI_LANDING

    def test_claude_code_onboarding(self):
        assert classify_url("https://claude.ai/code/onboarding") == UrlType.AI_LANDING

    def test_claude_code_family(self):
        assert classify_url("https://claude.ai/code/family") == UrlType.AI_LANDING

    def test_claude_code_session(self):
        # Claude Code sessions are terminal-based — Chrome only stores the /code landing
        assert classify_url("https://claude.ai/code/session_01B7q7jFgiLCaFcY4Pw6Amay") == UrlType.AI_LANDING

    def test_claude_project(self):
        # Project pages are dashboards, not conversations
        assert classify_url("https://claude.ai/project/abc-def-123") == UrlType.AI_LANDING

    def test_chatgpt_landing(self):
        assert classify_url("https://chatgpt.com/") == UrlType.AI_LANDING

    def test_chatgpt_landing_bare(self):
        assert classify_url("https://chatgpt.com") == UrlType.AI_LANDING

    def test_chatgpt_auth(self):
        assert classify_url("https://chatgpt.com/auth/login") == UrlType.AI_LANDING

    def test_chatgpt_backend_api(self):
        assert classify_url("https://chatgpt.com/backend-api/conversation") == UrlType.AI_LANDING

    def test_chatgpt_gpts_landing(self):
        assert classify_url("https://chatgpt.com/gpts") == UrlType.AI_LANDING

    def test_gemini_landing_no_id(self):
        assert classify_url("https://gemini.google.com/app?is_sa=1") == UrlType.AI_LANDING

    def test_gemini_root(self):
        assert classify_url("https://gemini.google.com/?hl=ko") == UrlType.AI_LANDING

    def test_gemini_download(self):
        assert classify_url("https://gemini.google.com/app/download/mobile?is_sa=1") == UrlType.AI_LANDING

    def test_gemini_extensions(self):
        assert classify_url("https://gemini.google.com/app/extensions") == UrlType.AI_LANDING

    def test_gemini_settings(self):
        assert classify_url("https://gemini.google.com/app/settings") == UrlType.AI_LANDING

    def test_perplexity_landing(self):
        assert classify_url("https://perplexity.ai/") == UrlType.AI_LANDING


class TestAiChatConversationsStillMatch:
    """Existing conversation patterns must still work after noise filter is added."""

    def test_chatgpt_conversation(self):
        assert classify_url("https://chatgpt.com/c/69b77094-9800-8320-ac7f-a1fdddde92c6") == UrlType.AI_CHAT_CHATGPT

    def test_chatgpt_share(self):
        assert classify_url("https://chatgpt.com/share/abc-123") == UrlType.AI_CHAT_CHATGPT

    def test_chatgpt_gpt(self):
        assert classify_url("https://chatgpt.com/g/g-abc123") == UrlType.AI_CHAT_CHATGPT

    def test_claude_chat(self):
        assert classify_url("https://claude.ai/chat/abc-def-123-456") == UrlType.AI_CHAT_CLAUDE

    def test_gemini_conversation(self):
        assert classify_url("https://gemini.google.com/app/b316486a7f8fd8b7?is_sa=1") == UrlType.AI_CHAT_GEMINI

    def test_gemini_conversation_with_tracking(self):
        url = "https://gemini.google.com/app/accbf1620c63c6f5?is_sa=1&is_sa=1&android-min-version=301356232&gclid=CjwK"
        assert classify_url(url) == UrlType.AI_CHAT_GEMINI

    def test_perplexity_search(self):
        assert classify_url("https://perplexity.ai/search/some-query-abc123") == UrlType.AI_CHAT_PERPLEXITY

    def test_perplexity_page(self):
        assert classify_url("https://perplexity.ai/page/abc123") == UrlType.AI_CHAT_PERPLEXITY


class TestGeminiShareLinks:
    """Gemini share links should classify as AI_CHAT_GEMINI."""

    def test_gemini_share(self):
        assert classify_url("https://gemini.google.com/share/95c7453b12a1") == UrlType.AI_CHAT_GEMINI

    def test_gemini_share_with_query(self):
        assert classify_url("https://gemini.google.com/share/abc123?hl=ko") == UrlType.AI_CHAT_GEMINI


class TestNonAiUrlsUnchanged:
    """Non-AI URLs should still classify as before."""

    def test_github_repo(self):
        assert classify_url("https://github.com/owner/repo") == UrlType.GITHUB_REPO

    def test_youtube(self):
        assert classify_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == UrlType.YOUTUBE

    def test_web_page(self):
        assert classify_url("https://example.com/article") == UrlType.WEB_PAGE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_url_classifier.py -v`
Expected: `TestAiLandingNoise` and `TestGeminiShareLinks` tests FAIL; `TestAiChatConversationsStillMatch` and `TestNonAiUrlsUnchanged` PASS

- [ ] **Step 3: Add AI_LANDING to UrlType enum**

In `src/log_blog/url_classifier.py`, add after line 26 (`WEB_PAGE`):

```python
    AI_LANDING = "ai_landing"
```

- [ ] **Step 4: Add noise patterns and Gemini share regex**

In `src/log_blog/url_classifier.py`, add after the `_AI_CHAT_DOMAINS` line (line 79):

```python
# Noise patterns — landing pages, auth flows, settings, etc.
# Checked BEFORE conversation patterns to prevent wasted Playwright fetches.
_AI_NOISE_PATTERNS = [
    re.compile(r"claude\.ai/(?:oauth|chrome|code|project)(?:/|[?#]|$)"),
    re.compile(r"claude\.ai/?(?:[?#]|$)"),
    re.compile(r"chatgpt\.com/(?:auth|backend-api|gpts)?/?(?:[?#]|$)"),
    re.compile(r"gemini\.google\.com/(?:app(?:/(?:download|extensions|settings))?)?/?(?:[?#]|$)"),
    re.compile(r"gemini\.google\.com/?(?:[?#]|$)"),
    re.compile(r"perplexity\.ai/?(?:[?#]|$)"),
]
```

Update the `_GEMINI` regex (line 74-76) to also match share links:

```python
_GEMINI = re.compile(
    r"gemini\.google\.com/app/[a-zA-Z0-9]+"    # gemini.google.com/app/{conversation-id}
    r"|gemini\.google\.com/share/[a-zA-Z0-9]+" # gemini.google.com/share/{id}
)
```

- [ ] **Step 5: Restructure classify_url() to check noise first**

Replace the AI chat section of `classify_url()` (lines 109-125) with:

```python
    # AI noise filter — check before conversation patterns
    for domain in _AI_CHAT_DOMAINS:
        if domain in url:
            if any(p.search(url) for p in _AI_NOISE_PATTERNS):
                return UrlType.AI_LANDING
            break

    # AI chat services — must match per-conversation URLs
    if "perplexity.ai" in url:
        if _PERPLEXITY.search(url):
            return UrlType.AI_CHAT_PERPLEXITY
        _warn_unmatched_ai(url, "perplexity")
    if "chatgpt.com" in url or "chat.openai.com" in url:
        if _CHATGPT.search(url):
            return UrlType.AI_CHAT_CHATGPT
        _warn_unmatched_ai(url, "chatgpt")
    if "claude.ai" in url:
        if _CLAUDE.search(url):
            return UrlType.AI_CHAT_CLAUDE
        _warn_unmatched_ai(url, "claude")
    if "gemini.google.com" in url:
        if _GEMINI.search(url):
            return UrlType.AI_CHAT_GEMINI
        _warn_unmatched_ai(url, "gemini")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_url_classifier.py -v`
Expected: ALL tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/log_blog/url_classifier.py tests/test_url_classifier.py
git commit -m "feat: add AI_LANDING noise filter and Gemini share link support"
```

## Chunk 2: Extract Command + Content Fetcher

### Task 3: Add url_type to extract --json output

**Files:**
- Modify: `src/log_blog/cli.py:88-130`
- Create: `tests/test_extract_json.py`

- [ ] **Step 1: Write failing test for url_type in extract JSON**

```python
# tests/test_extract_json.py
import json
from unittest.mock import patch

from log_blog.history_reader import HistoryEntry
from log_blog.url_classifier import UrlType


class TestExtractJsonUrlType:
    """extract --json should include url_type field."""

    def test_url_type_included(self):
        """When extract outputs JSON, each entry should have a url_type field."""
        from log_blog.cli import cmd_extract
        import argparse
        import io
        from contextlib import redirect_stdout

        entries = [
            HistoryEntry(url="https://chatgpt.com/c/abc-123", title="Chat", visit_count=1, last_visit_time=1700000000.0),
            HistoryEntry(url="https://gemini.google.com/app/abc123", title="Gemini", visit_count=1, last_visit_time=1700000000.0),
            HistoryEntry(url="https://claude.ai/", title="Claude", visit_count=1, last_visit_time=1700000000.0),
            HistoryEntry(url="https://example.com", title="Example", visit_count=1, last_visit_time=1700000000.0),
        ]

        args = argparse.Namespace(config=None, hours=24, json=True, include_noise=False)

        f = io.StringIO()
        with patch("log_blog.cli.read_history", return_value=entries), redirect_stdout(f):
            cmd_extract(args)

        data = json.loads(f.getvalue())

        # AI_LANDING (claude.ai/) should be excluded by default
        urls = [e["url"] for e in data]
        assert "https://claude.ai/" not in urls

        # Remaining entries should have url_type
        types = {e["url"]: e["url_type"] for e in data}
        assert types["https://chatgpt.com/c/abc-123"] == "ai_chat_chatgpt"
        assert types["https://gemini.google.com/app/abc123"] == "ai_chat_gemini"
        assert types["https://example.com"] == "web_page"

    def test_include_noise_flag(self):
        """--include-noise should include AI_LANDING entries."""
        from log_blog.cli import cmd_extract
        import argparse
        import io
        from contextlib import redirect_stdout

        entries = [
            HistoryEntry(url="https://claude.ai/", title="Claude", visit_count=1, last_visit_time=1700000000.0),
        ]

        args = argparse.Namespace(config=None, hours=24, json=True, include_noise=True)

        f = io.StringIO()
        with patch("log_blog.cli.read_history", return_value=entries), redirect_stdout(f):
            cmd_extract(args)

        data = json.loads(f.getvalue())
        assert len(data) == 1
        assert data[0]["url_type"] == "ai_landing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_extract_json.py -v`
Expected: FAIL — `url_type` not in output, `include_noise` attribute missing

- [ ] **Step 3: Modify cmd_extract to include url_type and filter noise**

In `src/log_blog/cli.py`, modify the `cmd_extract` function. Add import at top of the JSON block:

```python
from .url_classifier import classify_url, UrlType
```

Replace the JSON output block (lines 96-107) with:

```python
    if args.json:
        from .url_classifier import classify_url, UrlType

        data = []
        for e in entries:
            url_type = classify_url(e.url)
            if url_type == UrlType.AI_LANDING and not args.include_noise:
                continue
            data.append({
                "url": e.url,
                "title": e.title,
                "visit_count": e.visit_count,
                "last_visit_time": e.last_visit_iso,
                "url_type": url_type.value,
            })
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
```

- [ ] **Step 4: Add --include-noise argument to the extract parser**

Find where the extract subparser adds arguments (search for `add_argument` calls near `--json` for extract) and add:

```python
extract_parser.add_argument("--include-noise", action="store_true", default=False,
                            help="Include AI landing/noise URLs in output")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_extract_json.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/log_blog/cli.py tests/test_extract_json.py
git commit -m "feat: add url_type to extract --json and filter AI_LANDING noise"
```

---

### Task 4: Handle AI_LANDING in content_fetcher.py

**Files:**
- Modify: `src/log_blog/content_fetcher.py:334-344`

- [ ] **Step 1: Add early-return for AI_LANDING in _fetch_batch bucketing**

In `src/log_blog/content_fetcher.py`, in the `_fetch_batch` function's bucketing loop (line 334), add a check before the existing type checks:

```python
        for url, url_type in classified:
            if url_type == UrlType.AI_LANDING:
                results[url] = PageContent(
                    url=url, title="", text_content="",
                    success=False, error="AI landing page, no content to fetch",
                    url_type=url_type.value,
                )
                continue
            if url_type == UrlType.YOUTUBE:
                youtube_urls.append(url)
            # ... rest unchanged
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/log_blog/content_fetcher.py
git commit -m "feat: skip AI_LANDING URLs in content fetcher"
```

## Chunk 3: Gemini Share Extractor + Skill Update

### Task 5: Add Gemini share link extraction

**Files:**
- Modify: `src/log_blog/ai_chat_fetcher.py:106-118`

- [ ] **Step 1: Add _extract_gemini_share to ai_chat_fetcher.py**

Add after the `_extract_gemini` function (after line 248):

```python
async def _extract_gemini_share(page) -> str:
    """Extract content from a Gemini share page (gemini.google.com/share/{id}).

    Share pages have a different DOM structure than /app/ conversations.
    They are publicly accessible — no auth needed.
    """
    return await page.evaluate("""
        () => {
            const parts = [];

            // Share pages may use different containers than /app/ pages
            const turns = document.querySelectorAll(
                '[class*="query-content"], [class*="response-content"], '
                + '[class*="user-query"], [class*="model-response"], '
                + 'message-content, .conversation-container > div, '
                + '[class*="prompt"], [class*="response"]'
            );

            if (turns.length > 0) {
                turns.forEach(el => {
                    const text = el.innerText.trim();
                    if (text.length < 10) return;
                    const classes = (el.className || '') + (el.getAttribute('data-content-type') || '');
                    const isUser = /user|query|human|prompt/i.test(classes);
                    const isModel = /model|response|assistant/i.test(classes);
                    const label = isUser ? '[USER]' : isModel ? '[ASSISTANT]' : '[MESSAGE]';
                    parts.push(label + '\\n' + text);
                });
                if (parts.length > 0) return parts.join('\\n\\n');
            }

            // Fallback: grab main content
            const main = document.querySelector('main, [role="main"]') || document.body;
            return main.innerText.trim().slice(0, 8000);
        }
    """)
```

- [ ] **Step 2: Route share links to the new extractor**

In `_extract_content` (line 106), add a check for Gemini share URLs. Modify the function to accept the URL as a parameter:

Update the function signature at line 106:

```python
async def _extract_content(page, service: str, url: str = "") -> str:
```

Add before the `if service == "gemini"` check (line 115):

```python
    elif service == "gemini" and "/share/" in url:
        return await _extract_gemini_share(page)
```

And update the call site at line 87:

```python
                content = await _extract_content(page, service, url)
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/log_blog/ai_chat_fetcher.py
git commit -m "feat: add Gemini share link content extraction"
```

---

### Task 6: Update the skill

**Files:**
- Modify: `.claude/skills/log-blog-skill/SKILL.md`

- [ ] **Step 1: Update Step 2 in SKILL.md**

Replace the Step 2 section to note that `url_type` is now in the extract output:

```markdown
## Step 2: Classify and Group (You — Claude — Do This)

Read the JSON output. Each entry now includes a `url_type` field from the classifier.

**Use `url_type` for grouping** — don't reclassify manually:
- `youtube` → YouTube
- `github_repo`, `github_pr`, `github_issue` → GitHub
- `ai_chat_perplexity`, `ai_chat_chatgpt`, `ai_chat_claude`, `ai_chat_gemini` → AI Chats
- `docs_page`, `web_page` → Docs/Web
- `ai_landing` entries are already filtered out by default

**Filter out non-tech** entries (social media, shopping, banking, etc.) based on URL and title.
```

- [ ] **Step 2: Update Step 3 to mention Claude export path**

Add to the Step 3 section, after the post action recommendation:

```markdown
If the user frequently uses Claude.ai web chat or Claude Code, suggest:
> "To include Claude conversations, export your data from claude.ai → Settings → Export, then run `uv run log-blog import-ai ~/path/to/claude-export.json`."
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/log-blog-skill/SKILL.md
git commit -m "docs: update skill to use url_type from extract output"
```

---

### Task 7: End-to-end manual verification

- [ ] **Step 1: Run extract and verify AI noise is filtered**

Run: `uv run log-blog extract --json --hours 720 | python3 -c "import json,sys; d=json.load(sys.stdin); ai=[e for e in d if 'ai_' in e.get('url_type','')]; print(f'Total: {len(d)}, AI chat: {len([e for e in ai if e[\"url_type\"]!=\"ai_landing\"])}, AI landing: {len([e for e in ai if e[\"url_type\"]==\"ai_landing\"])}')"`

Expected: AI landing count should be 0 (filtered by default). AI chat count should show matched conversations.

- [ ] **Step 2: Verify --include-noise shows landing pages**

Run: `uv run log-blog extract --json --hours 720 --include-noise | python3 -c "import json,sys; d=json.load(sys.stdin); landing=[e for e in d if e.get('url_type')=='ai_landing']; print(f'AI landing pages: {len(landing)}'); [print(f'  {e[\"title\"][:40]:40s} {e[\"url\"][:60]}') for e in landing[:5]]"`

Expected: Should show landing page entries.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit (if any fixes were needed)**

Only if adjustments were made during verification.
