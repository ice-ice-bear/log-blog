# Sequential Dev Log Tracking via Frontmatter

**Date**: 2026-03-17
**Status**: Draft
**Author**: Claude + User

## Problem

When generating dev log posts from Claude Code sessions, there's no way to know which commits a previous post already covered. This causes two issues:

1. **Duplicate content**: Running the dev log skill on Wednesday includes commits already covered in Monday's post.
2. **Manual series management**: Sequential numbering (#1, #2, #3) requires manually inspecting existing posts and counting.

The current workflow relies entirely on the skill operator (Claude) to manually cross-reference `scan` output against `sessions` output, which is error-prone and doesn't persist state across conversations.

## Solution

Add three optional frontmatter fields to dev log posts and update the skill logic to use them for automatic continuation detection.

### New Frontmatter Fields

```yaml
---
title: "주식 트레이딩 에이전트 개발기 #4 — ..."
series: "trading-agent"       # matches project name from `sessions --list`
series_num: 4                 # explicit sequence number
last_commit: "02fd47c"        # last commit SHA covered by this post
# ... existing fields unchanged
---
```

| Field | Type | Description |
|-------|------|-------------|
| `series` | `string \| null` | Project identifier. Must match the project name from `sessions --list` output (e.g., `"trading-agent"`, `"log-blog"`, `"megaupskill"`). |
| `series_num` | `int \| null` | Explicit 1-based sequence number within the series. |
| `last_commit` | `string \| null` | Short SHA (7+ chars) of the last git commit covered by this post. Used to determine where the next post should start. |

All three fields are optional. Posts without them are treated as standalone (no series).

### `scan` Command Changes

The `ExistingPost` dataclass adds three new fields:

```python
@dataclass
class ExistingPost:
    filename: str
    path: str
    title: str
    date: str
    tags: list[str]
    categories: list[str]
    content_preview: str
    # New fields
    series: str | None = None
    series_num: int | None = None
    last_commit: str | None = None
```

The frontmatter parser in `scan` already reads YAML — it just needs to extract these additional keys. No new CLI flags needed. The `--json` output includes the new fields (null if absent).

### Skill Logic Update (SKILL.md Dev Log Mode)

Replace the current manual Step 2.5 with automated series detection for dev log posts:

#### Updated Dev Log Mode Step 2: Series Detection

```
1. Run `sessions --list` → get projects with commits in last 24h
2. Run `scan --json --limit 30` → get existing posts with series metadata
3. User selects which projects to cover
4. For each approved project:
   a. Filter scan results: posts where series == project_name
   b. Sort by series_num DESC, take the first (latest)

   IF latest post found:
     - next_num = latest.series_num + 1
     - last_covered = latest.last_commit
     - Run `sessions --project <name> --all --json`
     - From git_commits, filter: only commits AFTER last_covered
       (compare commit list order — commits are chronological,
        find the index of last_covered and take everything after it)
     - If zero new commits → report "already up to date", skip
     - Action: sequential (#next_num)
     - Link to previous post in 개요 section

   IF no previous post found:
     - series_num = 1
     - Include all commits from sessions output
     - Action: new series

5. When generating the post markdown:
   - Set frontmatter: series, series_num, last_commit = SHA of newest commit
   - Title: "{Series Title} #{series_num} — {Subtitle}"
```

#### Commit Filtering Logic

The skill compares the `last_commit` SHA from the previous post against the `git_commits` array from `sessions --project`:

```
git_commits from sessions: [oldest ... newest]
  commit_A (oldest)
  commit_B
  commit_C  ← last_commit from previous post
  commit_D  ← NEW (include)
  commit_E  ← NEW (include)
  commit_F  ← NEW (include, also set as last_commit for this post)
```

If `last_commit` SHA is not found in the commits list (e.g., after a rebase or force push), fall back to **time-based filtering**: include commits with timestamps after the previous post's `date` field.

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| First post in a series | `series_num: 1`, all commits included |
| No new commits since last post | Skip with message "already up to date" |
| `last_commit` SHA not in git history (rebase) | Fall back to date-based filtering |
| Multiple posts same project same day | `series_num` increments correctly (#4, #5) |
| Existing posts without series frontmatter | Treated as standalone, not part of any series |
| User wants to restart numbering | Manually set `series_num: 1` in new post |

### Backward Compatibility

- All new frontmatter fields are optional with `None` defaults
- `scan` returns `null` for missing fields — no breakage
- Existing posts continue to work as-is
- The skill only uses series logic when `series` frontmatter is present
- Browsing-history-based posts (non-dev-log) are unaffected

### What Changes Where

| Component | Change | Size |
|-----------|--------|------|
| `src/log_blog/cli.py` (scan parser) | Read `series`, `series_num`, `last_commit` from frontmatter | ~10 lines |
| `ExistingPost` dataclass | Add 3 optional fields | 3 lines |
| `SKILL.md` Dev Log Mode | Add series detection + commit filtering logic | ~40 lines of skill text |
| Post template in `SKILL.md` | Add `series`, `series_num`, `last_commit` to frontmatter template | 3 lines |

### Not In Scope

- No CLI flag like `--since-post` on the `sessions` command (keep CLI decoupled from blog)
- No automatic backfilling of existing posts (manual one-time task if desired)
- No series management UI or dedicated command
- No cross-repo series (each series maps to exactly one project)
