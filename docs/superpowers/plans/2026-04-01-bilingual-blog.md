# Bilingual Blog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable English/Korean bilingual blog with language switcher, and update logblog post skill to auto-translate and publish both languages.

**Architecture:** Hugo `languages` config enables the Stack theme's built-in language switcher. Posts go to `content/{lang}/posts/` with matching filenames for Hugo translation linking. The logblog skill generates Korean original → English rewrite → sequential publish with `--language` flag.

**Tech Stack:** Hugo (Stack theme), Python (logblog CLI), YAML config

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `~/Documents/github/ice-ice-bear.github.io/hugo.yaml` | Modify | Hugo multilingual config, menus per language |
| `~/Documents/github/ice-ice-bear.github.io/content/en/posts/_index.md` | Verify exists | English posts index |
| `skills/post/SKILL.md` | Modify | Add Step 5.5 translation, update Step 6/7 for bilingual publish |

---

### Task 1: Update Hugo config for bilingual support

**Files:**
- Modify: `~/Documents/github/ice-ice-bear.github.io/hugo.yaml`

- [ ] **Step 1: Change `defaultContentLanguage` and add `languages` section**

Replace lines 5-8 in `hugo.yaml`:

```yaml
# Old:
languageCode: ko
defaultContentLanguage: ko
timezone: "Asia/Seoul"
hasCJKLanguage: true
```

With:

```yaml
languageCode: en
defaultContentLanguage: en
timezone: "Asia/Seoul"

languages:
  en:
    languageName: English
    weight: 1
  ko:
    languageName: 한국어
    weight: 2
    hasCJKLanguage: true
```

- [ ] **Step 2: Move menu under `languages` and remove top-level `menu`**

Replace the entire `menu:` block (lines 60-99) with language-specific menus inside the `languages:` section added in Step 1. The full `languages:` block becomes:

```yaml
languages:
  en:
    languageName: English
    weight: 1
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
        - identifier: search
          name: Search
          url: /search/
          weight: 40
          params:
            icon: search
      social:
        - identifier: github
          name: GitHub
          url: "https://github.com/ice-ice-bear"
          weight: 10
          params:
            icon: brand-github
        - identifier: email
          name: Email
          url: "mailto:3balbi7@gmail.com"
          weight: 20
          params:
            icon: mail
  ko:
    languageName: 한국어
    weight: 2
    hasCJKLanguage: true
    menu:
      main:
        - identifier: posts
          name: 포스트
          url: /posts/
          weight: 10
          params:
            icon: archives
        - identifier: categories
          name: 카테고리
          url: /categories/
          weight: 20
          params:
            icon: categories
        - identifier: tags
          name: 태그
          url: /tags/
          weight: 30
          params:
            icon: tag
        - identifier: search
          name: 검색
          url: /search/
          weight: 40
          params:
            icon: search
      social:
        - identifier: github
          name: GitHub
          url: "https://github.com/ice-ice-bear"
          weight: 10
          params:
            icon: brand-github
        - identifier: email
          name: Email
          url: "mailto:3balbi7@gmail.com"
          weight: 20
          params:
            icon: mail
```

Delete the old top-level `menu:` block (the entire section from `menu:` through the last social entry).

- [ ] **Step 3: Verify `content/en/posts/_index.md` exists**

Check if the file exists. If not, create it:

```bash
ls ~/Documents/github/ice-ice-bear.github.io/content/en/posts/_index.md 2>/dev/null || echo "MISSING"
```

If missing, create:

```markdown
---
title: "Posts"
---
```

- [ ] **Step 4: Verify Hugo builds successfully**

```bash
cd ~/Documents/github/ice-ice-bear.github.io && hugo --gc --minify 2>&1 | tail -5
```

Expected: Build succeeds, shows page counts for both `en` and `ko`.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/github/ice-ice-bear.github.io
git add hugo.yaml content/en/posts/_index.md
git commit -m "feat: enable bilingual blog (en/ko) with language switcher"
```

---

### Task 2: Update logblog post skill with translation step

**Files:**
- Modify: `skills/post/SKILL.md`

- [ ] **Step 1: Add Step 5.5 — Translation between Step 5 and Step 6**

After the line `## Step 6: User Reviews the Post` (line 377), insert a new section **before** it. The new section goes between Step 5's closing `---` (line 375) and Step 6:

```markdown
## Step 5.5: Translate the Post (You — Claude — Do This)

After writing the original post (typically Korean), generate an English translation by **rewriting for an English-speaking audience** — not literal translation.

### Translation Guidelines

- **Rewrite, don't translate** — restructure sentences for natural English flow
- **Technical terms** follow English conventions (e.g., 분산 추적 → distributed tracing, 공급망 공격 → supply chain attack)
- **Translate**: `title`, `description` in frontmatter, all body text, Mermaid diagram labels, section headers
- **Keep unchanged**: `tags`, `categories`, `date`, `image`, `series`, `series_num`, `last_commit`, code blocks, URLs, CLI commands
- **Mermaid safety rules still apply** in the English version — `&lt;br/&gt;`, quoted `/` labels, `description` frontmatter, `<!--more-->`

Save both versions as separate temp files:
```bash
cat > /tmp/log-blog-post-ko.md << 'POSTEOF'
(Korean original)
POSTEOF

cat > /tmp/log-blog-post-en.md << 'POSTEOF'
(English rewrite)
POSTEOF
```

If the original post was written in English, generate a Korean translation instead using the same guidelines in reverse.
```

- [ ] **Step 2: Update Step 6 to show both versions**

Replace the current Step 6 content:

```markdown
## Step 6: User Reviews the Post

Show both the Korean and English versions to the user. Ask:

*"Here are the Korean and English versions. Want me to change anything before publishing?"*

Apply any edits the user requests to either version. Repeat until they approve both.
```

- [ ] **Step 3: Update Step 7 publish commands for bilingual**

Replace the Step 7 publish section to use sequential bilingual publish:

```markdown
## Step 7: Publish

Once the user approves both versions, publish sequentially — Korean first (generates cover image), then English (reuses the same image):

**Korean version** (generates cover image + taxonomy icons):
```bash
uv run log-blog publish /tmp/log-blog-post-ko.md --filename "SLUG.md" --cover-title "Korean Title" --tags "tag1,tag2" --language ko
```

**English version** (skips image generation — already created above):
```bash
uv run log-blog publish /tmp/log-blog-post-en.md --filename "SLUG.md" --cover-title "English Title" --tags "tag1,tag2" --language en --no-images
```

**Important:** Both versions MUST use the same `--filename` so Hugo links them as translations. The language switcher will appear automatically on the published post.

**For `update`** — add `--update` flag to both commands:
```bash
uv run log-blog publish /tmp/log-blog-post-ko.md --filename EXISTING.md --update --tags "tag1,tag2" --language ko
uv run log-blog publish /tmp/log-blog-post-en.md --filename EXISTING.md --update --tags "tag1,tag2" --language en --no-images
```
```

Update the Dev Log Mode Step 5 publish similarly:

```bash
uv run log-blog publish /tmp/log-blog-post-ko.md --filename "YYYY-MM-DD-{slug}.md" --cover-title "Title" --tags "tag1,tag2" --language ko
uv run log-blog publish /tmp/log-blog-post-en.md --filename "YYYY-MM-DD-{slug}.md" --cover-title "English Title" --tags "tag1,tag2" --language en --no-images
```

- [ ] **Step 4: Commit**

```bash
git add skills/post/SKILL.md
git commit -m "feat: add bilingual translation step to post skill"
```

---

### Task 3: Verify end-to-end with a test post

- [ ] **Step 1: Create a minimal test post in Korean**

```bash
cat > /tmp/test-bilingual-ko.md << 'POSTEOF'
---
title: "이중 언어 테스트"
description: 이중 언어 블로그 테스트 포스트
date: 2026-04-01
categories: ["tech-log"]
tags: ["test"]
toc: true
math: false
---

## 개요

이중 언어 블로그 테스트입니다.

<!--more-->

## 테스트 내용

이 포스트는 한국어와 영어 양쪽에 발행되는지 확인합니다.
POSTEOF
```

- [ ] **Step 2: Create English version**

```bash
cat > /tmp/test-bilingual-en.md << 'POSTEOF'
---
title: "Bilingual Test"
description: Test post for bilingual blog setup
date: 2026-04-01
categories: ["tech-log"]
tags: ["test"]
toc: true
math: false
---

## Overview

This is a bilingual blog test post.

<!--more-->

## Test Content

This post verifies that content is published to both Korean and English directories.
POSTEOF
```

- [ ] **Step 3: Publish Korean version**

```bash
uv run log-blog publish /tmp/test-bilingual-ko.md --filename "test-bilingual.md" --language ko --no-images
```

Expected: `Wrote post to .../content/ko/posts/test-bilingual.md`

- [ ] **Step 4: Publish English version**

```bash
uv run log-blog publish /tmp/test-bilingual-en.md --filename "test-bilingual.md" --language en --no-images
```

Expected: `Wrote post to .../content/en/posts/test-bilingual.md`

- [ ] **Step 5: Verify both files exist**

```bash
ls ~/Documents/github/ice-ice-bear.github.io/content/ko/posts/test-bilingual.md
ls ~/Documents/github/ice-ice-bear.github.io/content/en/posts/test-bilingual.md
```

Both should exist.

- [ ] **Step 6: Verify Hugo builds with both languages**

```bash
cd ~/Documents/github/ice-ice-bear.github.io && hugo --gc --minify 2>&1 | tail -5
```

Expected: Build succeeds with page counts for en and ko.

- [ ] **Step 7: Clean up test files**

```bash
cd ~/Documents/github/ice-ice-bear.github.io
git reset HEAD~2 --mixed
rm -f content/ko/posts/test-bilingual.md content/en/posts/test-bilingual.md
```
