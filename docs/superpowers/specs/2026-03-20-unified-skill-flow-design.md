# Unified Skill Flow, Last-Run Tracking & Session Data Bug Fixes

**Date**: 2026-03-20
**Status**: Draft

## Problem Statement

Three issues were identified during the 2026-03-20 blog posting session:

1. **Dev log posts not surfaced in initial skill flow**: The log-blog skill has two independent modes — browser history (Steps 1-7) and Dev Log Mode — with no automatic detection or combined presentation. Users must explicitly ask for dev logs after the browser history flow completes.

2. **Session data processing clarity**: When processing `sessions --project X --all --json` output:
   - Output is always a JSON list `[{...}]` — SKILL.md should handle this explicitly
   - Commits use a `timestamp` field (ISO 8601) — SKILL.md should document the exact field name to prevent ambiguity

3. **Fixed 24h window is suboptimal**: Both `extract` and `sessions` default to `--hours 24`, but the user runs the skill daily. If a run is delayed or skipped, entries between 24h ago and the previous run are lost. A "since last run" mode would capture exactly the right window.

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
- Run `uv run log-blog scan --json --limit 30` once — use for both browser post action detection (existing Step 2.5) and dev log series detection
- For each project from `sessions --list`:
  - Check for existing series posts matching the project name in scan results
  - Determine new commit count using `timestamp` field filtering
  - Assign action: `new series`, `sequential (#N)`, or `already up to date`

### Change 3: Unified Step 3 — Integrated Presentation

Present all post candidates in a single list with two sections:

```
**브라우저 기반 포스트 후보:**

YouTube:
  1. [Title](url)
GitHub:
  2. [Title](url)
Docs/Web:
  3. [Title](url)
Filtered out:
  - [Title](url)

**코드 기반 dev log 후보:**
  - project-a (N new commits) — #M (continues from #M-1)
  - project-b (N commits) — new series #1
  - project-c — already up to date (0 new commits since #K)

Post action 추천: [per-item recommendations]

어떤 포스트를 올릴까요? 항목을 추가/제거하거나 변경하고 싶으면 말씀해주세요.
```

User approves once. Then:
- Browser-based items proceed to Step 4 (fetch)
- Dev log items proceed to `sessions --project X --all --json` for detailed data

Both can be written in parallel (Step 5 / Dev Log Step 4).

The unified Steps 1-3 fully replace both the old browser-only Steps 1-3 and the old Dev Log Mode Steps 1-2. The Dev Log Mode section remains for Steps 3-5 (detailed data fetching, writing, publishing) but is no longer the entry point.

### Change 4: SKILL.md — Explicit JSON and Field Handling

Add clear instructions in Dev Log Mode Step 3 for processing session data:

```
`sessions --project X --all --json` 출력은 항상 JSON list이다. 첫 번째 요소를 사용한다:

  data = json.load(output)
  project = data[0] if isinstance(data, list) else data
  commits = project["git_commits"]

커밋 필터링 시 `timestamp` 필드(ISO 8601)를 사용한다:
  - 시리즈 연속: prev_last_commit SHA prefix 매칭 후 이후 커밋만 포함
  - Date fallback: c["timestamp"] >= "{prev_date}T00:00:00+09:00" (KST)
```

No CLI code changes — the list output format is correct and consistent. The SKILL.md handles it explicitly.

### Change 5: Last-Run Tracking — `--since-last-run` Flag

Add a `--since-last-run` flag to both `extract` and `sessions` commands. When used, the tool reads the last run timestamp from a state file and uses it as the time window start.

**State file**: `.log-blog-state.json` in the project root (gitignored).

```json
{
  "last_run": "2026-03-20T09:30:00+09:00"
}
```

**CLI changes** (`src/log_blog/cli.py`):

```
uv run log-blog extract --since-last-run --json
uv run log-blog sessions --list --since-last-run
```

- `--since-last-run`: Calculate hours from `last_run` timestamp to now, pass as `time_range_hours`
- If state file missing or `last_run` is null, fall back to `config.time_range_hours` (24h default)
- `--hours N` takes precedence over `--since-last-run` if both specified

**State update**: After a successful `extract` or `sessions` call, write the current timestamp to the state file. This happens at command completion, so interrupted runs don't advance the cursor.

**New module** (`src/log_blog/run_state.py`):

```python
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

STATE_FILENAME = ".log-blog-state.json"

@dataclass
class RunState:
    last_run: str | None = None  # ISO 8601

def load_state(project_root: Path) -> RunState:
    path = project_root / STATE_FILENAME
    if not path.exists():
        return RunState()
    data = json.loads(path.read_text())
    return RunState(last_run=data.get("last_run"))

def save_state(project_root: Path) -> None:
    path = project_root / STATE_FILENAME
    data = {"last_run": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(data, indent=2))

def hours_since_last_run(project_root: Path) -> int | None:
    state = load_state(project_root)
    if not state.last_run:
        return None
    last = datetime.fromisoformat(state.last_run)
    delta = datetime.now(timezone.utc) - last
    return max(1, int(delta.total_seconds() / 3600) + 1)  # Round up, minimum 1h
```

**SKILL.md update**: Change Step 1 commands to use `--since-last-run`:

```
Step 1: Extract History & Sessions

Run both commands simultaneously:
  - uv run log-blog extract --json --since-last-run
  - uv run log-blog sessions --list --since-last-run
```

If the user specifies `--hours N` explicitly, respect that override.

**Gitignore**: Add `.log-blog-state.json` to `.gitignore`.

## Edge Cases

- **Zero browser history + active dev log sessions**: Unified Step 3 shows only the dev log section. Browser section says "기술 관련 항목 없음".
- **Active browser history + zero new commits**: Dev log section shows all projects as "already up to date". User can still choose browser-only posts.
- **Multiple projects with same name**: `sessions --list` uses repo path as disambiguator. Series matching uses the `series` frontmatter field which is project-name based.
- **First run (no state file)**: Falls back to `config.time_range_hours` (24h). State file created after first successful run.
- **Skipped day**: If last run was 48h ago, `--since-last-run` calculates ~49h window, capturing everything since the previous run.
- **Multiple runs same day**: Second run finds very few new entries (only since the first run). This is correct behavior.

## Files to Modify

| File | Change |
|------|--------|
| `.claude/skills/log-blog-skill/SKILL.md` | Unified Steps 1-3, explicit JSON/timestamp handling, `--since-last-run` in Step 1 |
| `src/log_blog/cli.py` | Add `--since-last-run` flag to `extract` and `sessions` commands, call `save_state()` on completion |
| `src/log_blog/run_state.py` | New module: `load_state()`, `save_state()`, `hours_since_last_run()` |
| `.gitignore` | Add `.log-blog-state.json` |

Note: Out-of-scope uncommitted changes in `content_fetcher.py` and `youtube_fetcher.py` are unrelated and should be committed separately.

## Backward Compatibility

- CLI `sessions` command output: unchanged (always list)
- `--since-last-run` is opt-in. Without it, `--hours N` and `config.time_range_hours` work exactly as before.
- SKILL.md: unified Steps 1-3 fully replace old browser-only Steps 1-3 and old Dev Log Mode Steps 1-2. Dev Log Mode Steps 3-5 (write/publish) remain as-is.

## Testing

Manual verification checklist:

1. Run `uv run log-blog extract --json --hours 24` — verify browser history output
2. Run `uv run log-blog sessions --list` — verify project list with session counts
3. Run `uv run log-blog sessions --project trading-agent --all --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(type(d), type(d[0]))"` — verify list containing dict
4. Run `uv run log-blog sessions --project trading-agent --all --json | python3 -c "import json,sys; d=json.load(sys.stdin)[0]; print(d['git_commits'][0]['timestamp'])"` — verify timestamp field exists
5. Invoke `/log-blog-skill` and verify both browser history and dev log candidates appear in the unified Step 3 presentation
6. Verify that projects with zero new commits show "already up to date"
7. Verify that series continuation correctly identifies previous post and increments series_num
8. Run `uv run log-blog extract --since-last-run --json` on first run (no state file) — verify falls back to 24h
9. Run again — verify `.log-blog-state.json` was created and second run uses narrower window
10. Delete `.log-blog-state.json`, run with `--hours 48 --since-last-run` — verify `--hours` takes precedence
