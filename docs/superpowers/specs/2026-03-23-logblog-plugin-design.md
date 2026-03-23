# Logblog Plugin Design Spec

## Overview

Convert the log-blog project from a standalone Claude Code skill into a **Claude Code plugin** with two skills:

- **`/logblog:setup`** — End-to-end GitHub Pages blog setup (Hugo + Stack theme + GitHub Actions + config.yaml)
- **`/logblog:post`** — Collect activity from browsing history, git commits, and Claude Code sessions → write and publish a blog post

The plugin is skill-only (no MCP server). The existing Python CLI remains the execution layer — skills invoke it via Bash commands, same as today.

## Goals

1. Lower the barrier to entry: a user with no blog can go from zero to first post with `/logblog:setup` → `/logblog:post`
2. Make log-blog installable from any project directory via `/plugin install`
3. Keep the existing CLI and Python modules unchanged

## Non-Goals

- MCP server (deferred — not needed for plugin functionality)
- GitLab support (separate feature work)
- Multi-account SSH setup (out of scope)
- Theme selection (Stack only)

---

## Plugin Structure

```
log-blog/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── skills/
│   ├── setup/
│   │   └── SKILL.md             # /logblog:setup
│   └── post/
│       └── SKILL.md             # /logblog:post (migrated from .claude/skills/log-blog-skill/)
├── src/log_blog/                # Existing Python modules (unchanged)
├── pyproject.toml               # Existing (unchanged)
├── config.example.yaml          # Existing (unchanged)
└── ...
```

### plugin.json

```json
{
  "name": "logblog",
  "version": "0.1.0",
  "description": "Turn your daily browsing, coding sessions, and commits into tech blog posts on GitHub Pages",
  "author": "lsr"
}
```

---

## /logblog:setup — Design

### Phase 1: Environment Diagnosis

Run these checks and report results:

| Check | Command | Pass | Fail |
|---|---|---|---|
| uv installed | `uv --version` | Show version | "Install uv first: `curl -LsSf https://astral.sh/uv/install.sh \| sh`" — stop |
| Git installed | `git --version` | Show version | "Install git first" — stop |
| Hugo installed | `hugo version` | Show version, verify `+extended` | Proceed to install |
| Hugo extended | Parse version string | OK | `brew install hugo` |
| gh CLI auth | `gh auth status` | Note username(s) | Note: repo creation will be manual |
| Existing config.yaml | Check file existence in project root | → Connection mode (Phase 3B) | → Creation mode (Phase 3A) |

**Platform note:** This plugin targets macOS. Chrome history path (`~/Library/Application Support/Google/Chrome`) and `brew install` are macOS-specific.

If config.yaml already exists AND blog.repo_path points to a valid Hugo site:
> "Blog is already configured at {path}. Run /logblog:post to create a post."
> "Want to reconfigure? (y/n)"

### Phase 2: Branch Decision

```
config.yaml exists AND blog.repo_path valid?
  ├─ YES → "Already configured. Reconfigure?" → if yes, Phase 3B
  └─ NO  → "Do you have an existing Hugo blog?"
              ├─ YES → Phase 3B (connection mode)
              └─ NO  → Phase 3A (creation mode)
```

### Phase 3A: Creation Mode

#### Step 1: User Input

Ask these 3 questions:

1. **Blog title** — e.g., "My Tech Blog"
2. **Language** — en / ko (default: en)
3. **GitHub username** — for `{username}.github.io` repo name

#### Step 2: Install Hugo (if needed)

```bash
# macOS only (this project targets macOS based on Chrome history path)
brew install hugo
hugo version  # verify extended
```

If `brew` is not installed, show Homebrew install instructions and stop.

#### Step 3: Create Hugo site + Stack theme

```bash
hugo new site {username}.github.io
cd {username}.github.io
git init
git submodule add https://github.com/CaiJimmy/hugo-theme-stack themes/stack
mkdir -p content/posts
```

#### Step 4: Generate hugo.yaml

Based on current blog's hugo.yaml as a proven template. Includes Stack-required `menu` and `sidebar` config:

```yaml
baseURL: "https://{username}.github.io/"
title: "{blog_title}"
theme: stack
paginate: 10
languageCode: {language_code}     # "en" or "ko"
defaultContentLanguage: {language} # "en" or "ko"
timezone: "{timezone}"             # detect from system
hasCJKLanguage: true               # if ko

params:
  mainSections:
    - posts
  featuredImageField: image
  rssFullContent: true
  favicon: /images/profile.png
  footer:
    since: {current_year}
  dateFormat:
    published: "2006-01-02"
    lastUpdated: "2006-01-02 15:04"
  colorScheme:
    toggle: true
    default: auto
  sidebar:
    compact: false
    emoji: ""
    subtitle: ""
  article:
    math: true
    toc: true
    readingTime: true
    license:
      enabled: false
  widgets:
    homepage:
      - type: search
      - type: archives
      - type: tag-cloud

menu:
  main: []
  social: []

# Mermaid support
markup:
  goldmark:
    renderer:
      unsafe: true
  highlight:
    noClasses: false
```

#### Step 4.5: Create initial content

Create `content/posts/_index.md`:
```markdown
---
title: "Posts"
---
```

Create a welcome post so the deployed site isn't blank:
```markdown
---
title: "Hello World"
description: "First post on my new blog"
date: {today}
tags: ["blog"]
categories: ["general"]
---

Welcome to my blog! This site was set up with [logblog](https://github.com/ice-ice-bear/log-blog).
```

#### Step 5: GitHub Actions workflow

Create `.github/workflows/hugo.yaml`:

```yaml
name: Deploy Hugo site to Pages

on:
  push:
    branches: ["main"]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

defaults:
  run:
    shell: bash

jobs:
  build:
    runs-on: ubuntu-latest
    env:
      HUGO_VERSION: "0.147.1"
    steps:
      - name: Install Hugo CLI
        run: |
          wget -O ${{ runner.temp }}/hugo.deb https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_linux-amd64.deb \
          && sudo dpkg -i ${{ runner.temp }}/hugo.deb
      - name: Checkout
        uses: actions/checkout@v4
        with:
          submodules: recursive
          fetch-depth: 0
      - name: Setup Pages
        id: pages
        uses: actions/configure-pages@v5
      - name: Build with Hugo
        env:
          HUGO_CACHEDIR: ${{ runner.temp }}/hugo_cache
          HUGO_ENVIRONMENT: production
          TZ: "{timezone}"  # Same as hugo.yaml timezone, detected from system
        run: hugo --gc --minify --baseURL "${{ steps.pages.outputs.base_url }}/"
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: ./public

  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

#### Step 6: Initial commit + Create GitHub repo + push

First, commit all generated files:
```bash
git add .
git commit -m "Initial Hugo site setup with Stack theme"
```

Then create the remote repo:
```
gh auth status check
  ├─ Authenticated:
  │   gh repo create {username}.github.io --public --source=. --push
  │   # Wait a moment for GitHub to initialize, then enable Pages:
  │   gh api repos/{username}/{username}.github.io/pages \
  │       -X POST -f build_type=workflow
  │
  └─ Not authenticated:
      "Create a repo named '{username}.github.io' on GitHub, then paste the URL:"
      → git remote add origin {url}
      → git branch -M main
      → git push -u origin main
      → "Now enable GitHub Pages: Settings → Pages → Source: GitHub Actions"
```

### Phase 3B: Connection Mode

#### Step 1: Get repo path

```
"Enter the local path to your Hugo blog repo:"
→ User provides path (e.g., ~/Documents/github/my-blog)
```

#### Step 2: Validate

```
Check: {path}/hugo.yaml OR {path}/hugo.toml OR {path}/config.toml exists?
  (Note: Hugo's config file, NOT log-blog's config.yaml)
  ├─ YES → detect theme, content_dir, language from Hugo config
  │        content_dir: check Hugo config's mainSections or default "content/posts"
  └─ NO  → "This doesn't look like a Hugo project. Check the path."
```

#### Step 3: Extract remote URL

```bash
git -C {path} remote get-url origin
# → https://github.com/user/user.github.io.git
```

### Phase 4: Generate config.yaml

Common to both modes. Runs after Phase 3A or 3B.

#### Step 1: Chrome profile detection

```bash
uv run log-blog profiles --json
```

Display all profiles and ask user to select (multiple selection supported):

```
Detected Chrome profiles:
  1. work@company.com (Profile 1)
  2. personal@gmail.com (Default)
  3. side@gmail.com (Profile 3)

Which accounts should log-blog read history from? (e.g., 1,2):
```

#### Step 2: Generate config.yaml

```yaml
chrome:
  # Option A — filter by Google account email (recommended):
  google_accounts: ["{selected_account_1}", "{selected_account_2}"]
  # Option B — filter by folder name:
  # profiles: ["Default", "Profile 1"]
  history_db_base: "~/Library/Application Support/Google/Chrome"

time_range_hours: 24

blog:
  repo_path: "{repo_path}"
  repo_url: "{repo_url}"
  content_dir: "{detected_or_default}"  # e.g., "content/posts"
  language: "{language}"

playwright:
  headless: true
  timeout_ms: 15000
  max_concurrent: 5
  cdp_port: 9222

accounts:
  github:
    profile: "{gh_username_if_detected}"
  bitbucket:
    username: ""
    token: "${BITBUCKET_APP_PASSWORD}"
  ai_chats:
    perplexity:
      auth_profile: ""
      enabled: true
    chatgpt:
      auth_profile: ""
      enabled: true
    claude:
      auth_profile: ""
      enabled: true
    gemini:
      auth_profile: ""
      enabled: true

images:
  cover_enabled: true
  taxonomy_enabled: true

sessions:
  claude_dir: "~/.claude/projects"
```

#### Step 3: Install dependencies (if needed)

```bash
# Only if first time in the log-blog project directory
uv sync
uv run playwright install chromium
```

### Phase 5: Verification

Run a quick smoke test:

```bash
uv run log-blog extract --json --hours 1
```

Report results:

```
✓ config.yaml created
✓ Blog repo connected ({username}.github.io)
✓ Chrome history accessible ({N} entries detected)
✓ Dependencies installed

Setup complete! Run /logblog:post to create your first blog post.
```

If any step fails, report the specific error and suggest a fix.

---

## /logblog:post — Design

This is a direct migration of the existing `/log-blog` skill (`.claude/skills/log-blog-skill/SKILL.md`) with these changes:

1. **Rename**: `/log-blog` → `/logblog:post`
2. **Move**: `.claude/skills/log-blog-skill/SKILL.md` → `skills/post/SKILL.md`
3. **Content**: Identical to current SKILL.md — no functional changes
4. **Frontmatter**: Update `name` field to match plugin naming

All existing workflow steps (extract → classify → scan → present → fetch → write → publish) remain unchanged.

---

## Migration Plan

1. Create `.claude-plugin/plugin.json`
2. Create `skills/setup/SKILL.md` (new)
3. Copy `.claude/skills/log-blog-skill/SKILL.md` → `skills/post/SKILL.md` (update name field only)
4. Keep `.claude/skills/log-blog-skill/SKILL.md` during transition (remove after verification)
5. No Python code changes required

---

## Decisions Log

| Decision | Choice | Reason |
|---|---|---|
| Plugin type | Skill-only, no MCP | MCP adds complexity without clear benefit for current usage |
| Theme | Stack only | Cover images, mermaid rules, taxonomy icons are all Stack-specific |
| Deployment | GitHub Actions | Automatic, standard for GitHub Pages |
| Repo creation | gh CLI with manual fallback | gh already a dependency; fallback for unauthenticated users |
| SSH multi-account | Excluded | Too advanced, edge case |
| GitLab support | Excluded | Requires new fetcher — separate feature work |
| Language default | en first, then ko | User preference |
| Chrome profiles | Auto-detect + user selection | Multiple accounts supported |
| Existing blog | Auto-detect via config.yaml | Seamless for returning users |
