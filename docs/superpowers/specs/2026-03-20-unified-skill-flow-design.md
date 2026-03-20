# Unified Skill Flow & Session Data Bug Fixes

**Date**: 2026-03-20
**Status**: Draft

## Problem Statement

Two issues were identified during the 2026-03-20 blog posting session:

1. **Dev log posts not surfaced in initial skill flow**: The log-blog skill has two independent modes — browser history (Steps 1-7) and Dev Log Mode — with no automatic detection or combined presentation. Users must explicitly ask for dev logs after the browser history flow completes.

2. **Session data processing bugs**: When processing `sessions --project X --all --json` output, two bugs cause filtering failures:
   - Output is always a JSON list `[{...}]`, but filtering code assumes a bare dict `{...}`
   - Commits use a `timestamp` field (ISO 8601), but filtering code references a nonexistent `date` field

## Design

### Change 1: Unified Step 1 — Parallel Extraction

Modify SKILL.md Step 1 to run both extraction commands in parallel:

```
Step 1: Extract History & Sessions

Run both commands simultaneously:
  - uv run log-blog extract --json --hours 24
  - uv run log-blog sessions --list
```

This adds ~2-3 seconds (local file scan) with no API cost.

### Change 2: Unified Step 2 — Combined Classification

Merge browser history classification (current Step 2) with session-based project analysis (current Dev Log Mode Step 1.5) into a single step:

- Classify browser history entries by `url_type`
- For each project from `sessions --list`:
  - Run `uv run log-blog scan --json --limit 30` (once, shared)
  - Check for existing series posts matching each project
  - Determine new commit count using `timestamp` field filtering
  - Assign action: `new series`, `sequential (#N)`, or `already up to date`

### Change 3: Unified Step 3 — Integrated Presentation

Present all post candidates in a single numbered list with two sections:

```
📰 브라우저 기반 포스트 후보:
  YouTube:
    1. [Title](url)
  GitHub:
    2. [Title](url)
  Docs/Web:
    3. [Title](url)
  Filtered out:
    - [Title](url)

💻 코드 기반 dev log 후보:
  - project-a (N new commits) — #M (continues from #M-1)
  - project-b (N commits) — new series #1
  - project-c — ⏭ already up to date (0 new commits since #K)

Post action 추천: [per-item recommendations]

어떤 포스트를 올릴까요? 항목을 추가/제거하거나 변경하고 싶으면 말씀해주세요.
```

User approves once. Then:
- Browser-based items proceed to Step 4 (fetch)
- Dev log items proceed to `sessions --project X --all --json` for detailed data

Both can be written in parallel (Step 5 / Dev Log Step 4).

### Change 4: CLI Fix — Single Project Returns Dict

Modify `cmd_sessions()` in `cli.py` (lines 476-478):

**Before:**
```python
if args.json:
    data = [asdict(s) for s in summaries]
    print(json.dumps(data, ensure_ascii=False, indent=2))
```

**After:**
```python
if args.json:
    data = [asdict(s) for s in summaries]
    if args.project and len(data) == 1:
        print(json.dumps(data[0], ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
```

When `--project` is specified and yields exactly one result, output a bare dict instead of a single-element list.

### Change 5: SKILL.md Defensive JSON Handling

Add a note in Dev Log Mode Step 3 instructions:

```
sessions --project의 JSON 출력이 list인 경우 첫 번째 요소를 사용한다.
커밋 필터링 시 `timestamp` 필드(ISO 8601)를 사용한다.
예: c["timestamp"] >= "2026-03-18T00:00:00+09:00"
```

### Change 6: SKILL.md Commit Filtering Field Fix

Update all references in Dev Log Mode Step 1.5 from implicit `date` assumption to explicit `timestamp`:

- Filter commits by `c["timestamp"]` (ISO 8601 string, comparable as string for date prefix matching)
- Date fallback: `c["timestamp"] >= "{prev_date}T00:00:00+09:00"` (KST)

## Files to Modify

| File | Change |
|------|--------|
| `.claude/skills/log-blog-skill/SKILL.md` | Unified Steps 1-3, defensive JSON handling, timestamp field fix |
| `src/log_blog/cli.py` | Single-project dict output (lines 476-478) |

## Backward Compatibility

- `sessions --list` (no `--project`): output unchanged (list)
- `sessions --project X --all --json` with multiple results: output unchanged (list)
- `sessions --project X --all --json` with one result: **changed from `[{...}]` to `{...}`**
- SKILL.md defensive handling ensures both formats work regardless

## Testing

- Run `uv run log-blog sessions --project trading-agent --all --json` and verify output is a dict
- Run `uv run log-blog sessions --list --json` and verify output is still a list
- Invoke `/log-blog-skill` and verify both browser history and dev log candidates appear in Step 3
