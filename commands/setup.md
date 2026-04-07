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
| `uv` installed | Show version | Stop. Tell user: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `git` installed | Show version | Stop. Tell user to install git |
| `hugo` installed + extended | Show version, confirm `+extended` | Will install in Phase 3A Step 2 |
| `gh` authenticated | Note username | Note: repo creation will be manual |

**Platform note:** This plugin targets macOS. Chrome history path and `brew install` are macOS-specific.

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
2. **"What's your primary language? (en/ko, default: en)"**
3. **"Multi-language support? (y/n, default: n)"** — If yes, ask: **"Which languages? (comma-separated, e.g., en,ko)"**. This creates `content/{lang}/posts/` directories for each language, adds a `languages:` block to `hugo.yaml`, and sets `language_content_dirs` in log-blog's config.
4. **"What's your GitHub username?"** — This determines the repo name: `{username}.github.io`

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
```

**If multi-language was selected** — create a directory for each language:
```bash
mkdir -p content/en/posts content/ko/posts
# Add more languages as needed (e.g., content/ja/posts)
```

**If single-language** — use the flat structure:
```bash
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

Write `hugo.yaml` with these values (substitute `{blog_title}`, `{language}`, `{username}`, `{timezone}`, `{current_year}`).

**If single-language:**

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

**If multi-language** — add a `languages:` block. The `menu` entries must go inside each language (Hugo does not merge top-level `menu:` with per-language menus). Each language gets its own `contentDir`, menu labels, and `hasCJKLanguage` flag.

Example for en + ko (adapt language names, menu labels, and URL prefixes for other combinations):

```yaml
baseURL: "https://{username}.github.io/"
title: "{blog_title}"
theme: stack
paginate: 10
languageCode: {primary_language}
defaultContentLanguage: {primary_language}
timezone: "{timezone}"

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

languages:
  en:
    languageName: English
    weight: 1
    contentDir: content/en
    menu:
      main:
        - identifier: posts
          name: Posts
          url: /posts/
          weight: 10
          params:
            icon: archives
        - identifier: categories
          name: Categories
          url: /categories/
          weight: 20
          params:
            icon: categories
        - identifier: tags
          name: Tags
          url: /tags/
          weight: 30
          params:
            icon: tag
      social: []
  ko:
    languageName: 한국어
    weight: 2
    contentDir: content/ko
    hasCJKLanguage: true
    menu:
      main:
        - identifier: posts
          name: 포스트
          url: /ko/posts/
          weight: 10
          params:
            icon: archives
        - identifier: categories
          name: 카테고리
          url: /ko/categories/
          weight: 20
          params:
            icon: categories
        - identifier: tags
          name: 태그
          url: /ko/tags/
          weight: 30
          params:
            icon: tag
      social: []

markup:
  goldmark:
    renderer:
      unsafe: true
  highlight:
    noClasses: false
```

**Key multi-language rules:**
- The default language (e.g., `en`) serves pages at the root (`/posts/`). Non-default languages get a prefix (`/ko/posts/`).
- Each language's `contentDir` maps to its content directory (e.g., `content/en`, `content/ko`).
- Menu URLs must include the language prefix for non-default languages.
- `hasCJKLanguage: true` should be set on CJK language entries (ko, ja, zh), not globally.
- There is no top-level `menu:` when using `languages:` — all menus go inside each language block.

### Step 4.5: Create initial content

**If single-language:**

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

**If multi-language** — create `_index.md` and hello-world post in each language directory. Use localized titles and content:

For each language directory (e.g., `content/en/posts/`, `content/ko/posts/`):

```bash
# English
mkdir -p "{BLOG_DIR}/content/en/posts"
```
Write `content/en/posts/_index.md`:
```markdown
---
title: "Posts"
---
```
Write `content/en/posts/hello-world.md`:
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

```bash
# Korean
mkdir -p "{BLOG_DIR}/content/ko/posts"
```
Write `content/ko/posts/_index.md`:
```markdown
---
title: "포스트"
---
```
Write `content/ko/posts/hello-world.md`:
```markdown
---
title: "안녕하세요"
description: "새 블로그의 첫 포스트입니다"
date: {today}
tags: ["blog"]
categories: ["general"]
---

블로그에 오신 것을 환영합니다! 이 사이트는 [logblog](https://github.com/ice-ice-bear/log-blog)로 구축되었습니다.
```

**Important:** Both language versions use the **same filename** (`hello-world.md`). Hugo matches translations by filename — the language switcher only appears when both `content/en/posts/hello-world.md` and `content/ko/posts/hello-world.md` exist.

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

### Step 2.5: Detect multi-language structure

Check if the blog uses Hugo's i18n content directories:
```bash
ls -d "{path}/content/ko/posts" "{path}/content/en/posts" 2>/dev/null
```

If language-specific directories exist (e.g., `content/ko/posts/`, `content/en/posts/`):

1. **Verify Hugo config has a `languages:` block** — read the Hugo config file and check for a `languages:` section:
   ```bash
   grep -c "^languages:" "{path}/hugo.yaml" "{path}/hugo.toml" "{path}/config.toml" 2>/dev/null
   ```
   
   If the directories exist but `languages:` is **missing from Hugo config**, warn the user:
   > "Your blog has language directories (`content/en/`, `content/ko/`) but Hugo's config is missing the `languages:` block. Without it, Hugo ignores the language-specific directories and the language switcher won't work."
   > "Want me to add the `languages:` block to your Hugo config? (y/n)"
   
   If yes, read the existing Hugo config and add the `languages:` block following the multi-language template from Phase 3A Step 4. Preserve all existing settings — only add the `languages:` section and remove the top-level `menu:` (which moves into each language block).

2. **Set `language_content_dirs`** in log-blog config:
   ```yaml
   language_content_dirs:
     ko: "content/ko/posts"
     en: "content/en/posts"
   ```

3. **Set `default_language`** based on `defaultContentLanguage` from Hugo config (default: `"en"`)

4. The `publish` command routes each post to the correct language directory via `--language`

If no language directories found:
- Set `language_content_dirs: {}` — single-language mode, posts go to `content_dir` only

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

### Step 2.5: Firecrawl API key (optional)

Ask the user:
> "Do you want to enable deep docs fetching? This uses Firecrawl to crawl documentation sub-pages for richer blog posts. It's optional — you can add it later."
> "If yes, get a free API key at https://firecrawl.dev and paste it here. Press Enter to skip."

If the user provides a key, store it for the config.yaml template.
If skipped, leave `firecrawl.api_key` empty in the generated config.

### Step 3: Write config.yaml

Write `config.yaml` in the log-blog project root with all values filled in:

```yaml
chrome:
  # Option A — filter by Google account email (recommended):
  google_accounts: ["{selected_accounts}"]
  # Option B — filter by folder name:
  # profiles: ["Default", "Profile 1"]
  history_db_base: "~/Library/Application Support/Google/Chrome"

time_range_hours: 24

blog:
  repo_path: "{repo_path}"
  repo_url: "{repo_url}"
  content_dir: "{detected_or_default}"
  language_content_dirs: {detected_language_content_dirs}  # e.g. {ko: "content/ko/posts", en: "content/en/posts"}
  default_language: "{default_language}"  # e.g. "en"
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

# Firecrawl deep docs fetching (optional).
# Deep-crawl documentation sites for guide-style blog posts.
# Get an API key at https://firecrawl.dev
firecrawl:
  api_key: "{firecrawl_api_key_if_provided}"
  max_pages: 10
```

Key substitutions:
- `chrome.google_accounts` — from Step 1 selection
- `blog.repo_path` — from Phase 3A (BLOG_DIR) or Phase 3B (user input)
- `blog.repo_url` — from Phase 3A (gh output) or Phase 3B (git remote get-url)
- `blog.content_dir` — from Phase 3B detection or default "content/posts"
- `blog.language_content_dirs` — from Phase 3A (if multi-language) or Phase 3B Step 2.5, e.g. `{ko: "content/ko/posts", en: "content/en/posts"}`
- `blog.default_language` — from Hugo `defaultContentLanguage` or user input (default: `"en"`)
- `blog.language` — from Phase 3A user input or Phase 3B detection
- `accounts.github.profile` — from Step 2
- `firecrawl.api_key` — from Step 2.5 (empty if skipped)
- `images.cover_enabled`, `images.taxonomy_enabled` — both true
- `sessions.claude_dir` — "~/.claude/projects"

Include commented-out options for `chrome.profiles`, `bitbucket`, and `ai_chats` so users can enable them later.

### Step 4: Install dependencies

```bash
cd "$(pwd)"
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
