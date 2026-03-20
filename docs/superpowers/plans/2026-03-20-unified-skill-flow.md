# Unified Skill Flow & Last-Run Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify browser history and dev log extraction into a single skill entry point, add last-run tracking so the tool automatically uses the correct time window.

**Architecture:** Three changes: (1) new `run_state.py` module for last-run persistence, (2) `--since-last-run` flag on `extract` and `sessions` CLI commands, (3) SKILL.md rewrite to merge Steps 1-3 with Dev Log Mode entry.

**Tech Stack:** Python 3.12, argparse, JSON state file, SKILL.md (markdown)

**Spec:** `docs/superpowers/specs/2026-03-20-unified-skill-flow-design.md`

---

### Task 1: Create `run_state.py` Module

**Files:**
- Create: `src/log_blog/run_state.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create `run_state.py` with load/save/hours helpers**

```python
"""Track last-run timestamp for --since-last-run flag."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATE_FILENAME = ".log-blog-state.json"


def _state_path(project_root: Path | None = None) -> Path:
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / STATE_FILENAME


def load_last_run(project_root: Path | None = None) -> str | None:
    """Return ISO 8601 timestamp of last run, or None if never run."""
    path = _state_path(project_root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data.get("last_run")
    except (json.JSONDecodeError, OSError):
        return None


def save_last_run(project_root: Path | None = None) -> None:
    """Write current UTC timestamp as last_run."""
    path = _state_path(project_root)
    data = {"last_run": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(data, indent=2) + "\n")


def hours_since_last_run(project_root: Path | None = None) -> int | None:
    """Return hours since last run, rounded up. None if never run."""
    last = load_last_run(project_root)
    if not last:
        return None
    try:
        last_dt = datetime.fromisoformat(last)
        delta = datetime.now(timezone.utc) - last_dt
        return max(1, int(delta.total_seconds() / 3600) + 1)
    except ValueError:
        return None
```

- [ ] **Step 2: Add `.log-blog-state.json` to `.gitignore`**

Append to `.gitignore`:
```
.log-blog-state.json
```

- [ ] **Step 3: Commit**

```bash
git add src/log_blog/run_state.py .gitignore
git commit -m "feat: add run_state module for last-run timestamp tracking"
```

---

### Task 2: Add `--since-last-run` to `extract` Command

**Files:**
- Modify: `src/log_blog/cli.py:88-92` (cmd_extract)
- Modify: `src/log_blog/cli.py:551-557` (argparse for extract)

- [ ] **Step 1: Add `--since-last-run` argument to extract parser**

In `main()`, after line 553 (`p_extract.add_argument("--hours", ...)`), add:

```python
p_extract.add_argument("--since-last-run", action="store_true",
                       help="Use time since last run instead of fixed hours")
```

- [ ] **Step 2: Update `cmd_extract` to handle `--since-last-run`**

Replace lines 88-92 of `cmd_extract`:

```python
def cmd_extract(args: argparse.Namespace) -> None:
    """Extract and display browsing history."""
    config = load_config(args.config)
    if args.hours:
        config.time_range_hours = args.hours
```

With:

```python
def cmd_extract(args: argparse.Namespace) -> None:
    """Extract and display browsing history."""
    from .run_state import hours_since_last_run, save_last_run

    config = load_config(args.config)
    if args.hours:
        config.time_range_hours = args.hours
    elif args.since_last_run:
        h = hours_since_last_run()
        if h is not None:
            config.time_range_hours = h
```

- [ ] **Step 3: Save state after successful extract**

At the end of `cmd_extract`, just before the function returns (after all output is printed), add:

```python
    save_last_run()
```

This should go after the last `print`/`console.print` statement in the function, before the implicit return.

- [ ] **Step 4: Verify manually**

```bash
# First run (no state file) — should use default 24h
uv run log-blog extract --since-last-run --json 2>/dev/null | python3 -c "import json,sys; print(len(json.load(sys.stdin)), 'entries')"

# Check state file was created
cat .log-blog-state.json

# Second run — should use narrow window
uv run log-blog extract --since-last-run --json 2>/dev/null | python3 -c "import json,sys; print(len(json.load(sys.stdin)), 'entries')"
```

- [ ] **Step 5: Commit**

```bash
git add src/log_blog/cli.py
git commit -m "feat: add --since-last-run flag to extract command"
```

---

### Task 3: Add `--since-last-run` to `sessions` Command

**Files:**
- Modify: `src/log_blog/cli.py:407-413` (cmd_sessions)
- Modify: `src/log_blog/cli.py:590-597` (argparse for sessions)

- [ ] **Step 1: Add `--since-last-run` argument to sessions parser**

In `main()`, after line 591 (`p_sessions.add_argument("--hours", ...)`), add:

```python
p_sessions.add_argument("--since-last-run", action="store_true",
                        help="Use time since last run instead of fixed hours")
```

- [ ] **Step 2: Update `cmd_sessions` to handle `--since-last-run`**

Replace line 413:

```python
    hours = args.hours or config.time_range_hours
```

With:

```python
    if args.hours:
        hours = args.hours
    elif args.since_last_run:
        from .run_state import hours_since_last_run
        h = hours_since_last_run()
        hours = h if h is not None else config.time_range_hours
    else:
        hours = config.time_range_hours
```

Note: `sessions` does NOT call `save_last_run()` — only `extract` saves state, since both commands run in the same skill invocation and we want a single timestamp.

- [ ] **Step 3: Verify manually**

```bash
# Should use the state file from extract's last run
uv run log-blog sessions --list --since-last-run
```

- [ ] **Step 4: Commit**

```bash
git add src/log_blog/cli.py
git commit -m "feat: add --since-last-run flag to sessions command"
```

---

### Task 4: Update SKILL.md — Unified Steps 1-3

**Files:**
- Modify: `.claude/skills/log-blog-skill/SKILL.md`

- [ ] **Step 1: Replace Step 1 with unified parallel extraction**

Find the current Step 1 section:
```
## Step 1: Extract History
```

Replace with:

```markdown
## Step 1: Extract History & Sessions

Run both commands simultaneously:

```bash
uv run log-blog extract --json --since-last-run
```

```bash
uv run log-blog sessions --list --since-last-run
```

Adjust `--hours N` if the user specifies a different range. The `--since-last-run` flag automatically calculates the time window from the last run. On first run, it falls back to the default 24 hours.

The `extract` command outputs a JSON array of `{url, title, visit_count, last_visit_time, url_type}`.
The `sessions --list` command shows a table of projects with session counts, commit counts, and duration.
```

- [ ] **Step 2: Update Step 2 to include session-based classification**

Find the current Step 2 section and append at the end, before Step 2.5:

```markdown
### Session-Based Projects

For each project from `sessions --list` output, determine its dev log status:

1. Check scan results (from Step 2.5) for existing series: posts where `series` field matches the project name
2. If series exists:
   - `next_num = highest series_num + 1`
   - Note `prev_last_commit` and `prev_date` for commit filtering in Step 4
3. If no series exists: `series_num = 1` (new series)
4. Projects with zero sessions or only trivial activity can be skipped
```

- [ ] **Step 3: Update Step 3 to show integrated presentation**

Find the current Step 3 section. After the existing browser-based presentation format, add a dev log section:

```markdown
**코드 기반 dev log 후보:**
- **project-a** (N sessions, M commits, Xh Ym) — Type — **#K** (continues from #K-1, N new commits)
- **project-b** (N sessions, M commits, Xh Ym) — Type — **new series #1**
- **project-c** — **already up to date** (0 new commits since #K)

Also state your post action recommendations for both browser-based and dev log posts together.

Ask: *"Want to add/remove any entries, or change the post action before I proceed?"*

**Wait for explicit approval before proceeding.**

After approval:
- Browser-based items proceed to Step 4 (fetch content)
- Dev log items proceed to Dev Log Mode Step 3 (get detailed session data with `sessions --project <name> --all --json`)
- Both types can be written in parallel
```

- [ ] **Step 4: Update Dev Log Mode Step 3 with explicit JSON handling**

Find the Dev Log Mode Step 3 section ("Get Detailed Data"). Add this note after the `sessions --project` command:

```markdown
**JSON structure note:** The `sessions --project` output is a JSON list. Use the first element:

```
data = json.load(output)
project = data[0] if isinstance(data, list) else data
commits = project["git_commits"]
```

Each commit has these fields: `sha`, `message`, `timestamp` (ISO 8601), `files`, `insertions`, `deletions`.

**Commit filtering:** Use the `timestamp` field (not `date`) for time-based filtering:
- Series continuation: find the commit where `sha.startswith(prev_last_commit)`, include only commits after that index
- Date fallback: `c["timestamp"] >= "{prev_date}T00:00:00+09:00"` (KST)
```

- [ ] **Step 5: Update Dev Log Mode entry point**

Find the Dev Log Mode section header. Replace the trigger description:

```markdown
## Dev Log Mode

When the user explicitly asks to "make a dev log" or "write a dev log from sessions", use this mode for the detailed writing steps. In the unified flow (above), dev log projects are already identified in Step 1 and presented in Step 3. This section covers Steps 3-5: fetching detailed data, writing, and publishing.

**If invoked standalone** (user asks only for dev logs, not the full pipeline): Run Step 1 of the main flow with `sessions --list --since-last-run` only (skip `extract`), then proceed to Step 2 presentation showing only dev log candidates.
```

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/log-blog-skill/SKILL.md
git commit -m "feat: unify browser history and dev log flows in SKILL.md

- Step 1 runs extract + sessions --list in parallel with --since-last-run
- Step 3 presents both browser and code-based post candidates
- Dev Log Mode Step 3 documents JSON list handling and timestamp field
- Dev Log Mode entry point updated for standalone invocation"
```

---

### Task 5: Final Verification

**Files:** None (manual testing only)

- [ ] **Step 1: Verify `--since-last-run` on first run**

```bash
rm -f .log-blog-state.json
uv run log-blog extract --since-last-run --json 2>/dev/null | python3 -c "import json,sys; print(len(json.load(sys.stdin)), 'entries')"
cat .log-blog-state.json
```

Expected: Falls back to 24h, state file created.

- [ ] **Step 2: Verify `--since-last-run` on second run**

```bash
uv run log-blog sessions --list --since-last-run
```

Expected: Uses time window from state file (very narrow, minutes since step 1).

- [ ] **Step 3: Verify `--hours` overrides `--since-last-run`**

```bash
uv run log-blog extract --hours 48 --since-last-run --json 2>/dev/null | python3 -c "import json,sys; print(len(json.load(sys.stdin)), 'entries')"
```

Expected: Uses 48h window (--hours takes precedence).

- [ ] **Step 4: Verify sessions JSON structure handling**

```bash
uv run log-blog sessions --project trading-agent --all --json 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
project = data[0] if isinstance(data, list) else data
commits = project['git_commits']
print(f'Type: {type(data)}, Commits: {len(commits)}, First timestamp: {commits[0][\"timestamp\"] if commits else \"none\"}')
"
```

Expected: `Type: <class 'list'>, Commits: N, First timestamp: 2026-03-...`

- [ ] **Step 5: Read through SKILL.md and verify unified flow is coherent**

Read `.claude/skills/log-blog-skill/SKILL.md` and verify:
- Step 1 mentions both `extract` and `sessions --list`
- Step 3 has both browser-based and dev log sections
- Dev Log Mode Step 3 has JSON list handling note
- Dev Log Mode entry point references unified flow
