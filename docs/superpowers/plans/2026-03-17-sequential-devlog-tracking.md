# Sequential Dev Log Tracking Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `series`, `series_num`, and `last_commit` frontmatter fields to dev log posts so the skill can automatically detect series continuation and filter already-covered commits.

**Architecture:** Extend the `ExistingPost` dataclass and `_parse_post()` in `post_advisor.py` to read three new optional YAML frontmatter fields. Update the Dev Log Mode section of `SKILL.md` to use these fields for automatic series detection and commit filtering. No new CLI commands or flags needed.

**Tech Stack:** Python (dataclass + YAML parsing), Markdown (SKILL.md skill text)

**Spec:** `docs/superpowers/specs/2026-03-17-sequential-devlog-tracking-design.md`

---

### Task 1: Add series fields to ExistingPost dataclass

**Files:**
- Modify: `src/log_blog/post_advisor.py:12-20`

- [ ] **Step 1: Add 3 optional fields to ExistingPost**

```python
@dataclass
class ExistingPost:
    filename: str
    path: str  # absolute path as string
    title: str
    date: str  # YYYY-MM-DD
    tags: list[str]
    categories: list[str]
    content_preview: str  # first 300 chars of body text
    series: str | None = None  # project identifier for dev log series
    series_num: int | None = None  # 1-based sequence number
    last_commit: str | None = None  # short SHA of last covered commit
```

- [ ] **Step 2: Update _parse_post() to extract the new fields**

In `_parse_post()` (line 77-85), add the three fields to the `ExistingPost` constructor:

```python
    series_num_raw = fm.get("series_num")

    return ExistingPost(
        filename=path.name,
        path=str(path),
        title=str(fm.get("title", path.stem)),
        date=date_str,
        tags=list(fm.get("tags", []) or []),
        categories=list(fm.get("categories", []) or []),
        content_preview=body.strip()[:300],
        series=fm.get("series"),
        series_num=int(series_num_raw) if series_num_raw is not None else None,
        last_commit=fm.get("last_commit"),
    )
```

Note: `series_num` needs explicit `int()` cast because YAML may parse it as int already, but we want to be safe if it's a string.

- [ ] **Step 3: Verify scan output includes new fields**

Run:
```bash
uv run log-blog scan --json --limit 5 2>/dev/null | python3 -c "import json,sys; posts=json.load(sys.stdin); print(json.dumps(posts[0], indent=2))"
```

Expected: The JSON output includes `"series": null`, `"series_num": null`, `"last_commit": null` for existing posts that don't have these frontmatter fields.

- [ ] **Step 4: Commit**

```bash
git add src/log_blog/post_advisor.py
git commit -m "feat: add series, series_num, last_commit to ExistingPost for dev log tracking"
```

---

### Task 2: Update Dev Log Mode template in SKILL.md

**Files:**
- Modify: `.claude/skills/log-blog-skill/SKILL.md:440-450` (Dev Log post template)

- [ ] **Step 1: Add series frontmatter to the post template**

Replace the current template frontmatter block (lines ~440-450) with:

```markdown
**Template:**

\`\`\`markdown
---
image: "/images/posts/YYYY-MM-DD-{slug}/cover.jpg"
title: "Series Title #N — Descriptive Subtitle"
description: Plain text summary for SEO
date: YYYY-MM-DD
series: "project-name"
series_num: N
last_commit: "abc1234"
categories: ["category"]
tags: ["tech1", "tech2"]
toc: true
math: false
---
\`\`\`
```

- [ ] **Step 2: Update the commit log table template to remove SHA column**

Replace the commit log table in the template (line ~476-478):

Before:
```
| SHA | 메시지 | 변경 |
|-----|--------|------|
| abc1234 | feat: add feature | +120 -30 |
```

After:
```
| 메시지 | 변경 |
|--------|------|
| feat: add feature | +120 -30 |
```

This aligns with the user's feedback to never show commit IDs in blog posts.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/log-blog-skill/SKILL.md
git commit -m "feat: add series frontmatter fields to dev log post template"
```

---

### Task 3: Add series detection logic to SKILL.md Dev Log Mode

**Files:**
- Modify: `.claude/skills/log-blog-skill/SKILL.md:397-503` (Dev Log Mode section)

- [ ] **Step 1: Insert series detection step between Step 1 and Step 2**

After the existing "Step 1: List Projects" section and before "Step 2: Present to User", insert a new "Step 1.5: Detect Series Continuation" section:

```markdown
### Step 1.5: Detect Series Continuation

Run scan to find existing series posts:

\`\`\`bash
uv run log-blog scan --json --limit 30
\`\`\`

For each project from Step 1, check if a series already exists:

1. Filter scan results: posts where `series` field matches the project name
2. Sort matching posts by `series_num` DESC, take the highest
3. Record: `prev_series_num`, `prev_last_commit`, `prev_filename`, `prev_date`

**If previous series post found:**
- `next_num = prev_series_num + 1`
- When fetching session data in Step 3, filter commits:
  - Reverse `git_commits` to chronological order (sessions returns newest-first)
  - Find the commit where `sha.startswith(prev_last_commit)` (prefix match)
  - Include only commits AFTER that index
  - If `prev_last_commit` is not found (rebase/force push), fall back to date filtering:
    include commits with timestamp >= `prev_date + 1 day 00:00 KST`
  - If `prev_last_commit` is null but series exists, use the same date fallback
- If zero new commits after filtering → report "already up to date", skip this project
- Link to previous post: `[이전 글: #{prev_series_num}](/posts/{prev_filename without .md}/)`

**If no previous series post found:**
- `series_num = 1`
- Include all commits from sessions output
```

- [ ] **Step 2: Update Step 2 to show series info**

Update the "Present to User" section to include series continuation info:

```markdown
### Step 2: Present to User

Show which projects they worked on, with series status:

> "Today you worked on N projects:
> - **trading-agent** (22 sessions, 12 commits, 8h 15m) — GitHub — **#5** (continues from #4, 8 new commits)
> - **hybrid-search** (9 sessions, 5 commits, 3h 40m) — Bitbucket — **new series #1**
> - **log-blog** (4 sessions, 3 commits, 2h) — GitHub — **already up to date** (0 new commits since #2)
>
> Which ones should get dev log posts?"

Wait for user approval.
```

- [ ] **Step 3: Update Step 4 to set series frontmatter**

Add a note to the "Write the Dev Log Post" section:

```markdown
**Series frontmatter:** When writing the post, always set these fields:
- `series`: the project name (from `sessions --list`)
- `series_num`: the computed sequence number
- `last_commit`: the short SHA (first 7 chars) of the newest commit in the post's git_commits

For sequential posts (#2+), add a link to the previous post in the 개요 section:
> [이전 글: #{prev_num} — {prev_title}](/posts/{prev_filename_without_md}/)
```

- [ ] **Step 4: Update Step 5 publish note**

Replace the current sequential hint at the end of Dev Log Mode (line ~502):

Before:
```
For sequential series: check existing posts with `uv run log-blog scan --json --limit 30`, find the latest in the series, increment the number, and link to the previous post in 개요.
```

After:
```
Series tracking is automatic via frontmatter fields (`series`, `series_num`, `last_commit`). The skill detects continuation in Step 1.5 — no manual checking needed.
```

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/log-blog-skill/SKILL.md
git commit -m "feat: add automatic series detection logic to Dev Log Mode"
```

---

### Task 4: Backfill today's dev log posts with series frontmatter

**Files:**
- Modify: Blog repo posts (4 files published today)

- [ ] **Step 1: Get the latest commit SHAs for each project**

```bash
# trading-agent
git -C ~/Documents/github/trading-agent log -1 --format="%h" 2>/dev/null
# log-blog
git -C ~/Documents/github/log-blog log -1 --format="%h" 2>/dev/null
# megaupskill (find actual path)
# hybrid-image-search-demo (find actual path from bitbucket dir)
```

- [ ] **Step 2: Add series frontmatter to each post**

For each of the 4 posts published today, add `series`, `series_num`, and `last_commit` to the YAML frontmatter block (after the `date:` line). Example for trading-agent:

```yaml
series: "trading-agent"
series_num: 4
last_commit: "02fd47c"
```

Posts to update:
- `2026-03-17-trading-agent-dev4.md` → series: "trading-agent", series_num: 4
- `2026-03-17-log-blog-sessions.md` → series: "log-blog", series_num: 1
- `2026-03-17-megaupskill-i18n.md` → series: "megaupskill", series_num: 1
- `2026-03-17-hybrid-search-auth.md` → series: "hybrid-image-search-demo", series_num: 1

Note: `trading-agent` is #4 because previous posts #1-#3 exist in the series (though without series frontmatter — those are standalone and won't be detected, which is fine).

- [ ] **Step 3: Commit and push blog repo**

```bash
cd ~/Documents/github/ice-ice-bear.github.io
git add content/posts/2026-03-17-trading-agent-dev4.md content/posts/2026-03-17-log-blog-sessions.md content/posts/2026-03-17-megaupskill-i18n.md content/posts/2026-03-17-hybrid-search-auth.md
git commit -m "feat: add series tracking frontmatter to dev log posts"
git push
```

- [ ] **Step 4: Verify scan reads the new fields**

```bash
uv run log-blog scan --json --limit 5 2>/dev/null | python3 -c "
import json, sys
posts = json.load(sys.stdin)
for p in posts[:4]:
    print(f\"{p['filename']:50s} series={p.get('series'):25s} num={p.get('series_num')} last={p.get('last_commit')}\")"
```

Expected: The 4 updated posts show their series, series_num, and last_commit values.

- [ ] **Step 5: Commit log-blog changes (if any)**

```bash
git add -A && git commit -m "feat: add sequential dev log tracking (scan + skill)"
```
