# Logblog Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert log-blog into a Claude Code plugin with `/logblog:setup` (blog environment setup) and `/logblog:post` (existing post creation workflow).

**Architecture:** Skill-only plugin — no Python code changes. Create `.claude-plugin/plugin.json` manifest, write `skills/setup/SKILL.md` from the design spec, and migrate existing skill to `skills/post/SKILL.md`. The CLI remains the execution layer.

**Tech Stack:** Claude Code plugin system, SKILL.md markdown files, existing log-blog Python CLI

**Spec:** `docs/superpowers/specs/2026-03-23-logblog-plugin-design.md`

---

## File Structure

```
log-blog/
├── .claude-plugin/
│   └── plugin.json                  # CREATE — plugin manifest
├── skills/
│   ├── setup/
│   │   └── SKILL.md                 # CREATE — /logblog:setup skill
│   └── post/
│       └── SKILL.md                 # CREATE — /logblog:post (migrated from .claude/skills/)
├── .claude/skills/log-blog-skill/
│   └── SKILL.md                     # KEEP — legacy, remove after verification
└── (everything else unchanged)
```

---

### Task 1: Create plugin manifest

**Files:**
- Create: `.claude-plugin/plugin.json`

- [ ] **Step 1: Create directory and manifest file**

```json
{
  "name": "logblog",
  "version": "0.1.0",
  "description": "Turn your daily browsing, coding sessions, and commits into tech blog posts on GitHub Pages",
  "author": "lsr"
}
```

- [ ] **Step 2: Verify the file is valid JSON**

Run: `python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "feat: add logblog Claude Code plugin manifest"
```

---

### Task 2: Create /logblog:setup skill

**Files:**
- Create: `skills/setup/SKILL.md`

This is the largest task — the full setup skill from the design spec. The skill is a guided conversation script that Claude follows step-by-step.

- [ ] **Step 1: Create the setup SKILL.md**

Write the file `skills/setup/SKILL.md` with the full content below:

````markdown
---
name: setup
description: Set up a GitHub Pages blog with Hugo and Stack theme end-to-end. Use when user wants to create a new blog or connect an existing Hugo blog to log-blog.
---

# Logblog Setup: GitHub Pages Blog from Zero

You are setting up a Hugo blog with the Stack theme on GitHub Pages, then configuring log-blog to publish to it.

**Project root**: The directory where you are running Claude Code (the log-blog repo).

---

## Phase 1: Environment Diagnosis

Run all checks and report a status table before proceeding:

```bash
uv --version
git --version
hugo version
gh auth status
```

Check results:

| Check | Pass | Fail action |
|---|---|---|
| `uv` installed | Show version | Stop. Tell user: `curl -LsSf https://astral.sh/uv/install.sh | sh` |
| `git` installed | Show version | Stop. Tell user to install git |
| `hugo` installed + extended | Show version, confirm `+extended` | Will install in Phase 3A Step 2 |
| `gh` authenticated | Note username | Note: repo creation will be manual |

Then check if log-blog is already configured:

```bash
test -f config.yaml && echo "EXISTS" || echo "MISSING"
```

If `config.yaml` exists, read `blog.repo_path` from it and check if it points to a valid Hugo site:
```bash
cat config.yaml | grep repo_path
```

If already configured with a valid blog:
> "Blog is already configured at {path}. Run `/logblog:post` to create a post."
> "Want to reconfigure? (y/n)"

If user says no, stop here.

---

## Phase 2: Branch Decision

Ask the user:
> "Do you have an existing Hugo blog, or should I create one from scratch?"
> 1. **Create new blog** — I'll set up Hugo, Stack theme, and GitHub Pages
> 2. **Connect existing blog** — I'll configure log-blog to use your existing Hugo blog

**Wait for user choice.**

- Choice 1 → Phase 3A (Creation Mode)
- Choice 2 → Phase 3B (Connection Mode)

---

## Phase 3A: Creation Mode

### Step 1: User Input

Ask these questions one at a time:

1. **"What should your blog be called?"** (e.g., "My Tech Blog")
2. **"What language? (en/ko, default: en)"**
3. **"What's your GitHub username?"** — This determines the repo name: `{username}.github.io`

### Step 2: Install Hugo (if not found in Phase 1)

Check if Homebrew is available:
```bash
brew --version
```

If brew is missing:
> "Hugo requires Homebrew on macOS. Install it from https://brew.sh then re-run `/logblog:setup`."
> Stop here.

If brew is available:
```bash
brew install hugo
hugo version
```

Homebrew installs the extended edition by default. If the version string does NOT contain `+extended` (older Hugo versions showed this), that's OK — Homebrew Hugo is always extended since v0.93+. Just verify Hugo is installed and proceed.

### Step 3: Create Hugo site + Stack theme

Determine where to create the site. Default: same parent directory as the log-blog repo.

```bash
# Get the parent directory of the log-blog project
BLOG_DIR="$(dirname "$(pwd)")/{username}.github.io"
```

Ask user:
> "I'll create the blog at `{BLOG_DIR}`. Is that OK, or provide a different path?"

**Important:** Store the final absolute path. Use it in ALL subsequent commands — do not rely on `cd` persisting between bash calls.

Then:
```bash
hugo new site "{BLOG_DIR}"
cd "{BLOG_DIR}"
git init
git submodule add https://github.com/CaiJimmy/hugo-theme-stack themes/stack
mkdir -p content/posts
```

### Step 4: Generate hugo.yaml

Delete the default `hugo.toml` that `hugo new site` creates, then write `hugo.yaml`:

```bash
rm -f "{BLOG_DIR}/hugo.toml"
```

Detect system timezone:
```bash
readlink /etc/localtime | sed 's|.*/zoneinfo/||'
```

Write `hugo.yaml` with these values (substitute `{blog_title}`, `{language}`, `{username}`, `{timezone}`, `{current_year}`):

```yaml
baseURL: "https://{username}.github.io/"
title: "{blog_title}"
theme: stack
paginate: 10
languageCode: {language}
defaultContentLanguage: {language}
timezone: "{timezone}"
hasCJKLanguage: true

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

markup:
  goldmark:
    renderer:
      unsafe: true
  highlight:
    noClasses: false
```

If language is `en`, set `hasCJKLanguage: false`.

### Step 4.5: Create initial content

Write `content/posts/_index.md`:
```markdown
---
title: "Posts"
---
```

Write `content/posts/hello-world.md` (use today's date):
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

### Step 5: GitHub Actions workflow

```bash
mkdir -p "{BLOG_DIR}/.github/workflows"
```

Write `.github/workflows/hugo.yaml` (substitute `{timezone}`):

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
          TZ: "{timezone}"
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

### Step 6: Initial commit + GitHub repo

Commit everything:
```bash
cd "{BLOG_DIR}"
git add .
git commit -m "Initial Hugo site setup with Stack theme"
```

Check if `gh` is authenticated (from Phase 1 results):

**If authenticated:**
```bash
gh repo create {username}.github.io --public --source=. --push
```

Wait 5 seconds, then enable GitHub Pages:
```bash
gh api repos/{username}/{username}.github.io/pages -X POST -f build_type=workflow
```

If the Pages API call fails:
- **409 Conflict** → Pages is already enabled, not an error — proceed
- **Other error** → Tell user: "Repo created and pushed. Enable GitHub Pages manually: Settings → Pages → Source: GitHub Actions"

**If not authenticated:**
> "Create a GitHub repo named `{username}.github.io` (public), then paste the repo URL here."

After user provides URL:
```bash
cd "{BLOG_DIR}"
git remote add origin {url}
git branch -M main
git push -u origin main
```

Then tell user:
> "Code pushed. Now enable GitHub Pages: go to repo Settings → Pages → Source → select 'GitHub Actions'."

---

## Phase 3B: Connection Mode

### Step 1: Get repo path

Ask:
> "Enter the local path to your Hugo blog repo (e.g., ~/Documents/github/my-blog):"

### Step 2: Validate

Check for Hugo config:
```bash
ls "{path}/hugo.yaml" "{path}/hugo.toml" "{path}/config.toml" 2>/dev/null
```

If none found:
> "This doesn't look like a Hugo project — no hugo.yaml, hugo.toml, or config.toml found. Check the path."

If found, read it to detect:
- **theme** — `theme:` field
- **content_dir** — `mainSections` in params, or default `"content/posts"`
- **language** — `defaultContentLanguage` field

### Step 3: Extract remote URL

```bash
git -C "{path}" remote get-url origin
```

Store the result as `{repo_url}`.

---

## Phase 4: Generate config.yaml

This runs after Phase 3A or 3B.

### Step 1: Chrome profile detection

```bash
uv run log-blog profiles --json
```

The output is a JSON array of `{folder, name, email, active}` objects.

Display them as a numbered list:
> "Detected Chrome profiles:"
> 1. work@company.com (Profile 1)
> 2. personal@gmail.com (Default)
> 3. side@gmail.com (Profile 3)
>
> "Which accounts should log-blog read history from? (comma-separated, e.g., 1,2):"

**Wait for user selection.** Multiple selections supported.

### Step 2: Detect gh username

```bash
gh api user --jq '.login' 2>/dev/null || echo ""
```

### Step 3: Write config.yaml

Write `config.yaml` in the log-blog project root with all values filled in.

Use the template from the design spec (`docs/superpowers/specs/2026-03-23-logblog-plugin-design.md`, Phase 4 Step 2). Key substitutions:

- `chrome.google_accounts` — from Step 1 selection
- `blog.repo_path` — from Phase 3A (`{BLOG_DIR}`) or Phase 3B (user input)
- `blog.repo_url` — from Phase 3A (`gh` output) or Phase 3B (`git remote get-url`)
- `blog.content_dir` — from Phase 3B detection or default `"content/posts"`
- `blog.language` — from Phase 3A user input or Phase 3B detection
- `accounts.github.profile` — from Step 2
- `images.cover_enabled`, `images.taxonomy_enabled` — both `true`
- `sessions.claude_dir` — `"~/.claude/projects"`

Include ALL sections from the spec template (chrome, blog, playwright, accounts, images, sessions). Include commented-out options for `chrome.profiles`, `bitbucket`, and `ai_chats` so users can enable them later.

### Step 4: Install dependencies

```bash
cd "$(pwd)"  # ensure we're in log-blog project root
uv sync
uv run playwright install chromium
```

---

## Phase 5: Verification

Run a smoke test:
```bash
uv run log-blog extract --json --hours 1
```

Report results:

```
✓ config.yaml created
✓ Blog repo connected ({repo_path})
✓ Chrome history accessible ({N} entries detected)
✓ Dependencies installed

Setup complete! Run /logblog:post to create your first blog post.
```

If extract returns an empty array, that's OK — tell the user:
> "Chrome history is accessible but no entries found in the last hour. This is normal if you haven't browsed recently. Try `/logblog:post` — it uses a 24-hour window by default."

If extract fails, report the error and suggest a fix based on the error message.
````

- [ ] **Step 2: Verify SKILL.md frontmatter is valid**

Run: `head -4 skills/setup/SKILL.md`
Expected:
```
---
name: setup
description: Set up a GitHub Pages blog with Hugo and Stack theme end-to-end. Use when user wants to create a new blog or connect an existing Hugo blog to log-blog.
---
```

- [ ] **Step 3: Commit**

```bash
git add skills/setup/SKILL.md
git commit -m "feat: add /logblog:setup skill for end-to-end blog setup"
```

---

### Task 3: Migrate /logblog:post skill

**Files:**
- Create: `skills/post/SKILL.md` (copy from `.claude/skills/log-blog-skill/SKILL.md`)

- [ ] **Step 1: Copy the existing skill**

```bash
mkdir -p skills/post
cp .claude/skills/log-blog-skill/SKILL.md skills/post/SKILL.md
```

- [ ] **Step 2: Update the frontmatter name**

Change only the first 4 lines of `skills/post/SKILL.md`:

From:
```yaml
---
name: log-blog
description: Read Chrome browsing history, classify tech content, generate and publish a tech blog post to your Hugo blog. Use when user wants to create a tech blog post from their browsing history.
---
```

To:
```yaml
---
name: post
description: Read Chrome browsing history, classify tech content, generate and publish a tech blog post to your Hugo blog. Use when user wants to create a tech blog post from their browsing history.
---
```

**Do NOT change anything else in the file.** The body content remains identical.

- [ ] **Step 3: Verify the file is complete**

Run: `wc -l skills/post/SKILL.md .claude/skills/log-blog-skill/SKILL.md`
Expected: Both files should have the same line count.

- [ ] **Step 4: Commit**

```bash
git add skills/post/SKILL.md
git commit -m "feat: migrate /log-blog skill to /logblog:post in plugin structure"
```

---

### Task 4: Verify plugin structure

**Files:** None created — verification only.

- [ ] **Step 1: Verify all plugin files exist**

Run: `ls -la .claude-plugin/plugin.json skills/setup/SKILL.md skills/post/SKILL.md`
Expected: All three files exist

- [ ] **Step 2: Verify plugin.json is valid**

Run: `python3 -c "import json; d=json.load(open('.claude-plugin/plugin.json')); assert d['name']=='logblog'; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify skill frontmatter names match plugin convention**

Run: `head -3 skills/setup/SKILL.md skills/post/SKILL.md`
Expected:
- setup skill: `name: setup`
- post skill: `name: post`

- [ ] **Step 4: Test plugin locally**

Tell the user:
> "Plugin files are ready. To test locally, reload Claude Code (`/reload-plugins` or restart).
> Then try `/logblog:setup` and `/logblog:post` to verify they appear as available skills."

- [ ] **Step 5: Document legacy skill status**

The old skill at `.claude/skills/log-blog-skill/SKILL.md` still works. Keep it during the transition period. Once the plugin versions are confirmed working, remove it:

```bash
# Only run after confirming /logblog:post works:
# rm -rf .claude/skills/log-blog-skill/
```

---

## Execution Order

All tasks are sequential:

```
Task 1 (manifest) → Task 2 (setup skill) → Task 3 (post skill) → Task 4 (verify)
```

Task 1 is trivial (1 file). Task 2 is the bulk of the work. Task 3 is a copy + 1-line edit. Task 4 is verification only.
