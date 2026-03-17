# Session Dev Log Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `sessions` CLI command that parses Claude Code session transcripts (JSONL) and combines them with git log data to produce structured JSON for dev log blog posts.

**Architecture:** New `session_parser.py` module handles JSONL parsing + project auto-discovery + git log extraction. CLI command `sessions` in `cli.py` exposes it. Config gets a `SessionsConfig` dataclass. The skill gets a "Dev Log Mode" section.

**Tech Stack:** Python, dataclasses, subprocess (for git), pathlib, json

**Spec:** `docs/superpowers/specs/2026-03-17-session-devlog-design.md`

---

## Chunk 1: Core Data Structures and Config

### Task 1: Add SessionsConfig to config.py

**Files:**
- Modify: `src/log_blog/config.py:101-182`
- Modify: `config.example.yaml`

- [ ] **Step 1: Add SessionsConfig dataclass**

Add after `ImagesConfig` (line 106), before `Config`:

```python
@dataclass
class SessionsConfig:
    claude_dir: str = "~/.claude/projects"

    @property
    def claude_dir_path(self) -> Path:
        return Path(self.claude_dir).expanduser()
```

- [ ] **Step 2: Add sessions field to Config**

Add to the `Config` dataclass fields (after `images`):

```python
    sessions: SessionsConfig = field(default_factory=SessionsConfig)
```

- [ ] **Step 3: Wire up in load_config()**

Add after `images_data` parsing (around line 145):

```python
    sessions_data = data.get("sessions", {}) or {}
```

And add to the `Config(...)` constructor at the end:

```python
        sessions=SessionsConfig(**_filter_fields(SessionsConfig, sessions_data)),
```

- [ ] **Step 4: Add sessions section to config.example.yaml**

Append at end of file:

```yaml

# Claude Code session parsing for dev log blog posts.
# Sessions are auto-discovered from ~/.claude/projects/ by default.
sessions:
  claude_dir: "~/.claude/projects"  # Where Claude Code stores session transcripts
  # projects:                       # Optional overrides for auto-discovery (parsed manually)
  #   custom-name:
  #     session_dir: "~/.claude/projects/-Users-lsr-some-weird-path"
  #     repo_path: "~/Documents/actual/repo/path"
```

- [ ] **Step 5: Verify config loads without errors**

Run: `uv run python -c "from log_blog.config import load_config; c = load_config(); print(c.sessions.claude_dir)"`
Expected: `~/.claude/projects`

- [ ] **Step 6: Commit**

```bash
git add src/log_blog/config.py config.example.yaml
git commit -m "feat: add SessionsConfig for Claude Code session parsing"
```

---

### Task 2: Create session_parser.py with data structures

**Files:**
- Create: `src/log_blog/session_parser.py`

- [ ] **Step 1: Create the module with all dataclasses**

```python
"""Parse Claude Code CLI session transcripts (JSONL) into structured data."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Truncation limits ---
_MAX_ASSISTANT_CHARS = 1500
_MAX_CODE_CHANGE_CHARS = 2000
_MAX_ERROR_CHARS = 1000
_MAX_ENTRIES_PER_SESSION = 100
_MAX_OUTPUT_BYTES = 100_000  # 100KB total per project JSON
_MIN_SESSION_MESSAGES = 3
_MIN_SESSION_MINUTES = 2


@dataclass
class ConversationEntry:
    type: str          # "user_request" | "assistant_response" | "code_change" | "error" | "command" | "research" | "agent_summary"
    timestamp: str     # ISO 8601
    text: str
    file: str | None = None
    action: str | None = None   # "edit" | "write" for code_change
    command: str | None = None  # For error and command entries
    url: str | None = None      # For research entries


@dataclass
class CommitInfo:
    sha: str
    message: str
    timestamp: str
    files: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0


@dataclass
class SessionData:
    session_id: str
    project_name: str
    repo_path: str
    repo_type: str           # "github" | "bitbucket" | "local"
    start_time: str
    end_time: str
    duration_minutes: int
    conversation: list[ConversationEntry] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)


@dataclass
class ProjectInfo:
    """Discovered project with its session directory and mapped repo path."""
    name: str
    session_dir: Path
    repo_path: Path | None
    repo_type: str  # "github" | "bitbucket" | "local"
    session_files: list[Path] = field(default_factory=list)


@dataclass
class ProjectSummary:
    project_name: str
    repo_path: str
    repo_type: str
    session_count: int
    total_duration_minutes: int
    sessions: list[SessionData] = field(default_factory=list)
    git_commits: list[CommitInfo] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `uv run python -c "from log_blog.session_parser import ConversationEntry, SessionData, ProjectSummary; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/log_blog/session_parser.py
git commit -m "feat: add session_parser data structures"
```

---

## Chunk 2: Project Auto-Discovery

### Task 3: Implement project auto-discovery

**Files:**
- Modify: `src/log_blog/session_parser.py`

- [ ] **Step 1: Add the path reverse-mapping function**

```python
_WORKTREE_SEPARATOR = "--claude-worktrees-"


def _reverse_map_path(dirname: str) -> Path | None:
    """Reverse-map a Claude Code project directory name to a filesystem path.

    Claude Code encodes paths by replacing '/' with '-':
      -Users-lsr-Documents-github-trading-agent → /Users/lsr/Documents/github/trading-agent

    The challenge: directory names themselves can contain hyphens.
    We use greedy filesystem matching: try the longest possible directory name first,
    then progressively split on hyphens until we find a real path.
    """
    # Strip worktree suffix
    if _WORKTREE_SEPARATOR in dirname:
        dirname = dirname.split(_WORKTREE_SEPARATOR)[0]

    # Replace leading dash with /
    if not dirname.startswith("-"):
        return None
    raw = "/" + dirname[1:]

    # Split into segments by dash
    segments = raw.split("-")
    # segments[0] is "" (from leading /), segments[1] is first dir component

    # Greedy reconstruction: try joining remaining segments as directory names
    result_parts: list[str] = []
    i = 0
    while i < len(segments):
        # Try joining segments[i:] greedily — longest match first
        best_end = i
        for j in range(len(segments), i, -1):
            candidate = "-".join(segments[i:j])
            test_path = "/".join(result_parts + [candidate])
            if not test_path:
                continue
            if os.path.exists(test_path) or os.path.exists(test_path + "/"):
                best_end = j
                result_parts.append(candidate)
                break
        else:
            # No match found — append remaining as single segment
            result_parts.append(segments[i])
            best_end = i + 1

        i = best_end

    path = Path("/".join(result_parts))
    return path if path.exists() else None


def _detect_repo_type(repo_path: Path) -> str:
    """Detect whether a git repo is github, bitbucket, or local."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        url = result.stdout.strip()
        if "github.com" in url or "github-blog" in url:
            return "github"
        if "bitbucket.org" in url:
            return "bitbucket"
    except Exception:
        pass
    return "local"


def discover_projects(
    hours: int,
    claude_dir: Path,
    include_short: bool = False,
    min_sessions: int = 2,
) -> list[ProjectInfo]:
    """Find all Claude Code projects with recent sessions.

    Scans claude_dir for project directories containing .jsonl files
    modified within the last `hours` hours. Maps each to a git repo path.
    """
    if not claude_dir.exists():
        logger.warning("Claude projects directory not found: %s", claude_dir)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    projects: dict[str, ProjectInfo] = {}

    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue
        dirname = project_dir.name

        # Skip the bare "-" directory (global settings)
        if dirname == "-":
            continue

        # Find recent JSONL files
        recent_files: list[Path] = []
        for jsonl_file in project_dir.glob("*.jsonl"):
            mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=timezone.utc)
            if mtime >= cutoff:
                recent_files.append(jsonl_file)

        if not recent_files:
            continue

        # Reverse-map to filesystem path
        repo_path = _reverse_map_path(dirname)
        is_git = repo_path is not None and (repo_path / ".git").is_dir()

        # Derive project name from the last path component(s)
        if repo_path:
            name = repo_path.name
        else:
            # Fallback: use last segment of the encoded dirname
            name = dirname.rsplit("-", 1)[-1] if "-" in dirname else dirname

        repo_type = _detect_repo_type(repo_path) if is_git and repo_path else "local"

        # Merge with existing project (worktrees map to same repo)
        if name in projects:
            projects[name].session_files.extend(recent_files)
        else:
            projects[name] = ProjectInfo(
                name=name,
                session_dir=project_dir,
                repo_path=repo_path,
                repo_type=repo_type,
                session_files=recent_files,
            )

    # Filter by minimum session count
    result = []
    for p in projects.values():
        if len(p.session_files) < min_sessions and not include_short:
            continue
        # Sort files by modification time
        p.session_files.sort(key=lambda f: f.stat().st_mtime)
        result.append(p)

    # Sort projects by total session file count (most active first)
    result.sort(key=lambda p: len(p.session_files), reverse=True)
    return result
```

- [ ] **Step 2: Test auto-discovery against real data**

Run: `uv run python -c "
from log_blog.session_parser import discover_projects
from pathlib import Path
projects = discover_projects(24, Path.home() / '.claude/projects', min_sessions=1)
for p in projects:
    print(f'{p.name}: {len(p.session_files)} sessions, repo={p.repo_path}, type={p.repo_type}')
"`
Expected: Lists projects like `trading-agent: 22 sessions, repo=/Users/lsr/Documents/github/trading-agent, type=github`

- [ ] **Step 3: Commit**

```bash
git add src/log_blog/session_parser.py
git commit -m "feat: add project auto-discovery with greedy path matching"
```

---

## Chunk 3: JSONL Session Parsing

### Task 4: Implement JSONL parsing with smart extraction

**Files:**
- Modify: `src/log_blog/session_parser.py`

- [ ] **Step 1: Add the JSONL parsing functions**

```python
# --- Tool classification ---
_INCLUDE_TOOLS = {"Edit", "Write", "Bash"}
_SUMMARY_TOOLS = {"WebFetch", "WebSearch", "Agent"}
_EXCLUDE_TOOLS = {"Read", "Grep", "Glob", "TodoWrite", "Skill", "ToolSearch",
                   "NotebookEdit", "EnterPlanMode", "ExitPlanMode",
                   "EnterWorktree", "ExitWorktree", "LSP",
                   "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskStop", "TaskOutput",
                   "AskUserQuestion", "CronCreate", "CronDelete", "CronList"}


def _extract_user_text(content) -> str | None:
    """Extract plain text from a user message content field."""
    if isinstance(content, str):
        # Skip command messages and very short content
        text = content.strip()
        if text.startswith("<command-") or text.startswith("<task-notification"):
            return None
        if text.startswith("<local-command"):
            return None
        if len(text) < 5:
            return None
        return text
    # content is a list — look for plain text (not tool_result)
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    t = block["text"].strip()
                    if not t.startswith("<command-") and not t.startswith("<task-notification") and not t.startswith("<local-command") and len(t) >= 5:
                        texts.append(t)
        return "\n".join(texts) if texts else None
    return None


def _process_tool_use(block: dict) -> ConversationEntry | None:
    """Process a tool_use content block, returning a ConversationEntry or None."""
    name = block.get("name", "")
    inp = block.get("input", {})
    ts = ""  # Will be set by caller

    # MCP tools — skip
    if name.startswith("mcp__"):
        return None

    # Excluded tools
    if name in _EXCLUDE_TOOLS:
        return None

    if name == "Edit":
        file_path = inp.get("file_path", "")
        old = inp.get("old_string", "")
        new = inp.get("new_string", "")
        diff_text = f"-{old}\n+{new}" if old or new else ""
        if len(diff_text) > _MAX_CODE_CHANGE_CHARS:
            diff_text = diff_text[:_MAX_CODE_CHANGE_CHARS] + "\n[... truncated]"
        return ConversationEntry(
            type="code_change", timestamp=ts, text=diff_text,
            file=file_path, action="edit",
        )

    if name == "Write":
        file_path = inp.get("file_path", "")
        content = inp.get("content", "")
        if len(content) > _MAX_CODE_CHANGE_CHARS:
            content = content[:_MAX_CODE_CHANGE_CHARS] + "\n[... truncated]"
        return ConversationEntry(
            type="code_change", timestamp=ts, text=content,
            file=file_path, action="write",
        )

    if name == "Bash":
        cmd = inp.get("command", "")
        # We don't know if it's an error yet — mark as command, upgrade to error later
        return ConversationEntry(
            type="command", timestamp=ts, text="",
            command=cmd,
        )

    if name in ("WebFetch", "WebSearch"):
        url = inp.get("url", "") or inp.get("query", "")
        return ConversationEntry(
            type="research", timestamp=ts, text="",
            url=url,
        )

    if name == "Agent":
        prompt = inp.get("prompt", "")[:500]
        return ConversationEntry(
            type="agent_summary", timestamp=ts, text=prompt,
        )

    return None


def _process_tool_results(content: list, pending_bash: dict[str, ConversationEntry]) -> None:
    """Check tool_result blocks to upgrade Bash commands with errors."""
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue

        tool_id = block.get("tool_use_id", "")
        is_error = block.get("is_error", False)

        if tool_id in pending_bash:
            entry = pending_bash.pop(tool_id)
            if is_error:
                # Extract error text from result content
                result_content = block.get("content", "")
                if isinstance(result_content, list):
                    parts = [b.get("text", "") for b in result_content if isinstance(b, dict)]
                    result_content = "\n".join(parts)
                elif not isinstance(result_content, str):
                    result_content = str(result_content)
                if len(result_content) > _MAX_ERROR_CHARS:
                    result_content = result_content[:_MAX_ERROR_CHARS] + "\n[... truncated]"
                entry.type = "error"
                entry.text = result_content


def parse_session(jsonl_path: Path, project_name: str = "", repo_path: str = "", repo_type: str = "local") -> SessionData | None:
    """Parse a single JSONL session file into structured data.

    Returns None if the session is empty or cannot be parsed.
    """
    entries: list[ConversationEntry] = []
    timestamps: list[str] = []
    files_changed: set[str] = set()

    # Track pending Bash tool_use blocks waiting for their tool_result
    pending_bash: dict[str, ConversationEntry] = {}  # tool_use_id → entry

    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = obj.get("type")
                ts = obj.get("timestamp", "")
                if ts:
                    timestamps.append(ts)

                if msg_type == "user":
                    msg = obj.get("message", {})
                    content = msg.get("content")

                    # Check for tool_result blocks (to resolve pending Bash errors)
                    if isinstance(content, list):
                        _process_tool_results(content, pending_bash)

                    # Extract user text
                    text = _extract_user_text(content)
                    if text:
                        entries.append(ConversationEntry(
                            type="user_request", timestamp=ts, text=text,
                        ))

                elif msg_type == "assistant":
                    msg = obj.get("message", {})
                    content = msg.get("content", [])
                    if not isinstance(content, list):
                        continue

                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        block_type = block.get("type")

                        if block_type == "text":
                            text = block.get("text", "").strip()
                            if text and len(text) >= 10:
                                if len(text) > _MAX_ASSISTANT_CHARS:
                                    text = text[:_MAX_ASSISTANT_CHARS] + "\n[... truncated]"
                                entries.append(ConversationEntry(
                                    type="assistant_response", timestamp=ts, text=text,
                                ))

                        elif block_type == "tool_use":
                            entry = _process_tool_use(block)
                            if entry:
                                entry.timestamp = ts
                                if entry.type == "command":
                                    # Stash until we see the tool_result
                                    tool_id = block.get("id", "")
                                    pending_bash[tool_id] = entry
                                else:
                                    entries.append(entry)
                                    if entry.file:
                                        files_changed.add(entry.file)

    except Exception as e:
        logger.warning("Failed to parse session %s: %s", jsonl_path.name, e)
        return None

    if not entries:
        return None

    # Add non-error Bash commands that had results (as "command" type)
    # These were never upgraded to "error" so they stay as commands
    for entry in pending_bash.values():
        entries.append(entry)

    # Sort by timestamp
    entries.sort(key=lambda e: e.timestamp)

    # Apply entry limit — prioritize user_request, error, code_change
    if len(entries) > _MAX_ENTRIES_PER_SESSION:
        priority = {"user_request": 0, "error": 1, "code_change": 2, "command": 3,
                     "research": 4, "agent_summary": 5, "assistant_response": 6}
        entries.sort(key=lambda e: (priority.get(e.type, 9), e.timestamp))
        entries = entries[:_MAX_ENTRIES_PER_SESSION]
        entries.sort(key=lambda e: e.timestamp)  # Re-sort by time

    # Calculate duration
    if len(timestamps) >= 2:
        try:
            start = datetime.fromisoformat(min(timestamps).replace("Z", "+00:00"))
            end = datetime.fromisoformat(max(timestamps).replace("Z", "+00:00"))
            duration = int((end - start).total_seconds() / 60)
        except Exception:
            start = end = datetime.now(timezone.utc)
            duration = 0
    else:
        start = end = datetime.now(timezone.utc)
        duration = 0

    session_id = jsonl_path.stem  # UUID filename without .jsonl

    return SessionData(
        session_id=session_id,
        project_name=project_name,
        repo_path=repo_path,
        repo_type=repo_type,
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        duration_minutes=duration,
        conversation=entries,
        files_changed=sorted(files_changed),
    )
```

- [ ] **Step 2: Test parsing against a real session file**

Run: `uv run python -c "
from log_blog.session_parser import parse_session
from pathlib import Path
# Use the current session file
session = parse_session(
    Path.home() / '.claude/projects/-Users-lsr-Documents-github-log-blog/fc99c800-c60b-482a-a4b0-8c9cb9a35dad.jsonl',
    project_name='log-blog',
)
if session:
    print(f'Session: {session.session_id[:12]}...')
    print(f'Duration: {session.duration_minutes} min')
    print(f'Entries: {len(session.conversation)}')
    print(f'Files changed: {session.files_changed[:5]}')
    for e in session.conversation[:5]:
        print(f'  [{e.type}] {e.text[:80]}...')
else:
    print('Failed to parse')
"`
Expected: Parsed session with conversation entries showing user requests, code changes, errors

- [ ] **Step 3: Commit**

```bash
git add src/log_blog/session_parser.py
git commit -m "feat: add JSONL session parsing with smart extraction"
```

---

## Chunk 4: Git Log Integration and Project Summary

### Task 5: Add git log extraction and project summary builder

**Files:**
- Modify: `src/log_blog/session_parser.py`

- [ ] **Step 1: Add git log extraction**

```python
def extract_git_commits(repo_path: Path, start_time: datetime, end_time: datetime) -> list[CommitInfo]:
    """Get git commits within a time window.

    Uses git log with --after/--before to find commits, then extracts
    stat info (files changed, insertions, deletions) for each.
    """
    if not (repo_path / ".git").is_dir():
        return []

    # Add some buffer (commits may happen slightly before/after sessions)
    after = (start_time - timedelta(minutes=5)).isoformat()
    before = (end_time + timedelta(minutes=5)).isoformat()

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "log",
             f"--after={after}", f"--before={before}",
             "--format=%H|%s|%aI", "--shortstat"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
    except Exception as e:
        logger.warning("git log failed for %s: %s", repo_path, e)
        return []

    commits: list[CommitInfo] = []
    lines = result.stdout.strip().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        if "|" in line:
            parts = line.split("|", 2)
            if len(parts) == 3:
                sha, message, timestamp = parts
                insertions = deletions = 0

                # Next non-empty line might be stat
                if i + 1 < len(lines):
                    stat_line = lines[i + 1].strip()
                    if "insertion" in stat_line or "deletion" in stat_line:
                        # Parse "3 files changed, 45 insertions(+), 12 deletions(-)"
                        import re as _re
                        ins_match = _re.search(r"(\d+) insertion", stat_line)
                        del_match = _re.search(r"(\d+) deletion", stat_line)
                        if ins_match:
                            insertions = int(ins_match.group(1))
                        if del_match:
                            deletions = int(del_match.group(1))
                        i += 1  # Skip stat line

                # Get files for this commit
                try:
                    files_result = subprocess.run(
                        ["git", "-C", str(repo_path), "diff-tree", "--no-commit-id",
                         "--name-only", "-r", sha],
                        capture_output=True, text=True, timeout=5,
                    )
                    files = [f for f in files_result.stdout.strip().split("\n") if f]
                except Exception:
                    files = []

                commits.append(CommitInfo(
                    sha=sha[:8],
                    message=message.strip(),
                    timestamp=timestamp,
                    files=files,
                    insertions=insertions,
                    deletions=deletions,
                ))
        i += 1

    return commits
```

- [ ] **Step 2: Add the project summary builder**

```python
def build_project_summary(
    project: ProjectInfo,
    hours: int,
    include_short: bool = False,
) -> ProjectSummary:
    """Build a complete summary for one project: all sessions + git commits."""
    sessions: list[SessionData] = []
    all_files: set[str] = set()
    earliest = None
    latest = None

    repo_str = str(project.repo_path) if project.repo_path else ""

    for jsonl_file in project.session_files:
        session = parse_session(
            jsonl_file,
            project_name=project.name,
            repo_path=repo_str,
            repo_type=project.repo_type,
        )
        if session is None:
            continue

        # Filter short sessions
        if not include_short:
            if session.duration_minutes < _MIN_SESSION_MINUTES and len(session.conversation) < _MIN_SESSION_MESSAGES:
                continue

        sessions.append(session)
        all_files.update(session.files_changed)

        # Track time range
        try:
            s_start = datetime.fromisoformat(session.start_time.replace("Z", "+00:00"))
            s_end = datetime.fromisoformat(session.end_time.replace("Z", "+00:00"))
            if earliest is None or s_start < earliest:
                earliest = s_start
            if latest is None or s_end > latest:
                latest = s_end
        except Exception:
            pass

    # Get git commits across the full time range
    git_commits: list[CommitInfo] = []
    if project.repo_path and earliest and latest:
        git_commits = extract_git_commits(project.repo_path, earliest, latest)
        for c in git_commits:
            all_files.update(c.files)

    total_minutes = sum(s.duration_minutes for s in sessions)

    return ProjectSummary(
        project_name=project.name,
        repo_path=repo_str,
        repo_type=project.repo_type,
        session_count=len(sessions),
        total_duration_minutes=total_minutes,
        sessions=sessions,
        git_commits=git_commits,
        files_changed=sorted(all_files),
    )
```

- [ ] **Step 3: Test the full pipeline**

Run: `uv run python -c "
from log_blog.session_parser import discover_projects, build_project_summary
from pathlib import Path
projects = discover_projects(24, Path.home() / '.claude/projects', min_sessions=1)
if projects:
    p = projects[0]
    summary = build_project_summary(p, 24)
    print(f'{summary.project_name}: {summary.session_count} sessions, {len(summary.git_commits)} commits, {summary.total_duration_minutes} min')
    print(f'Files: {summary.files_changed[:5]}')
    if summary.git_commits:
        c = summary.git_commits[0]
        print(f'Latest commit: {c.sha} {c.message}')
"
`
Expected: Shows project with session count, commits, and file list

- [ ] **Step 4: Commit**

```bash
git add src/log_blog/session_parser.py
git commit -m "feat: add git log extraction and project summary builder"
```

---

## Chunk 5: CLI Command and Skill Update

### Task 6: Add `sessions` CLI command

**Files:**
- Modify: `src/log_blog/cli.py`

- [ ] **Step 1: Add the cmd_sessions function**

Add before `cmd_publish` function:

```python
def cmd_sessions(args: argparse.Namespace) -> None:
    """Extract Claude Code session data for dev log blog posts."""
    from dataclasses import asdict
    from .session_parser import discover_projects, build_project_summary

    config = load_config(args.config)
    hours = args.hours or config.time_range_hours
    claude_dir = config.sessions.claude_dir_path

    min_sessions = 1 if args.all else 2
    projects = discover_projects(
        hours, claude_dir,
        include_short=args.include_short,
        min_sessions=min_sessions,
    )

    if not projects:
        console.print("[yellow]No Claude Code sessions found in the given time range.[/yellow]")
        return

    # Filter to specific project if requested
    if args.project:
        projects = [p for p in projects if p.name == args.project]
        if not projects:
            console.print(f"[red]Project '{args.project}' not found.[/red]")
            return

    if args.list:
        # Quick overview mode
        if args.json:
            data = []
            for p in projects:
                summary = build_project_summary(p, hours, include_short=args.include_short)
                data.append({
                    "project_name": summary.project_name,
                    "repo_path": summary.repo_path,
                    "repo_type": summary.repo_type,
                    "session_count": summary.session_count,
                    "commit_count": len(summary.git_commits),
                    "total_duration_minutes": summary.total_duration_minutes,
                })
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            table = Table(title=f"Claude Code Sessions (last {hours}h)")
            table.add_column("Project", min_width=15)
            table.add_column("Sessions", justify="right", width=10)
            table.add_column("Commits", justify="right", width=10)
            table.add_column("Duration", justify="right", width=12)
            table.add_column("Type", width=10)

            for p in projects:
                summary = build_project_summary(p, hours, include_short=args.include_short)
                h, m = divmod(summary.total_duration_minutes, 60)
                duration = f"{h}h {m:02d}m" if h else f"{m}m"
                table.add_row(
                    summary.project_name,
                    str(summary.session_count),
                    str(len(summary.git_commits)),
                    duration,
                    summary.repo_type,
                )

            console.print(table)
        return

    # Full detail mode
    summaries = []
    for p in projects:
        summary = build_project_summary(p, hours, include_short=args.include_short)
        summaries.append(summary)

    if args.json:
        data = [asdict(s) for s in summaries]
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    # Rich table output for non-JSON
    for summary in summaries:
        console.print(f"\n[bold blue]{summary.project_name}[/bold blue] ({summary.repo_type})")
        console.print(f"  Sessions: {summary.session_count} | Commits: {len(summary.git_commits)} | Duration: {summary.total_duration_minutes}m")
        console.print(f"  Repo: {summary.repo_path}")

        if summary.git_commits:
            console.print("  [green]Commits:[/green]")
            for c in summary.git_commits[:10]:
                console.print(f"    {c.sha} {c.message} (+{c.insertions}/-{c.deletions})")

        if summary.files_changed:
            console.print(f"  [dim]Files changed: {', '.join(summary.files_changed[:10])}[/dim]")
```

- [ ] **Step 2: Register the subcommand in main()**

Add after the `chrome-cdp` parser block, before the `publish` parser:

```python
    # sessions
    p_sessions = subparsers.add_parser("sessions", help="Extract Claude Code session data for dev log blog posts")
    p_sessions.add_argument("--hours", type=int, help="Time window (default: from config, usually 24)")
    p_sessions.add_argument("--project", help="Filter to one project by name")
    p_sessions.add_argument("--all", action="store_true", help="Include projects with only 1 session")
    p_sessions.add_argument("--include-short", action="store_true", help="Include very short sessions (<2 min or <3 messages)")
    p_sessions.add_argument("--json", action="store_true", help="Output structured JSON")
    p_sessions.add_argument("--list", action="store_true", help="Quick overview: just project names and counts")
    p_sessions.set_defaults(func=cmd_sessions)
```

- [ ] **Step 3: Test the CLI command**

Run: `uv run log-blog sessions --list`
Expected: Table showing projects with session counts, commits, duration

Run: `uv run log-blog sessions --list --json`
Expected: JSON array with project summaries

- [ ] **Step 4: Test full detail mode**

Run: `uv run log-blog sessions --project log-blog --all`
Expected: Detailed view with commits and file changes for the log-blog project

- [ ] **Step 5: Commit**

```bash
git add src/log_blog/cli.py
git commit -m "feat: add sessions CLI command for dev log extraction"
```

---

### Task 7: Update the skill with Dev Log Mode

**Files:**
- Modify: `.claude/skills/log-blog-skill/skill.md`

- [ ] **Step 1: Add Dev Log Mode section to the skill**

Insert a new section after the existing "## Tips" section at the end of the skill file:

```markdown

---

## Dev Log Mode

When the user asks to "make a dev log", "write a dev log from sessions", "what did I work on today", or similar — use this mode instead of the Chrome history flow.

### Step 1: List Projects

```bash
uv run log-blog sessions --list
```

This shows all Claude Code projects with sessions from the last 24 hours.

### Step 2: Present to User

Show the user which projects they worked on:

> "Today you worked on N projects:
> - **trading-agent** (22 sessions, 12 commits, 8h 15m) — GitHub
> - **hybrid-search** (9 sessions, 5 commits, 3h 40m) — Bitbucket
> - **log-blog** (10 sessions, 3 commits, 2h 10m) — GitHub
>
> Which ones should get dev log posts?"

Wait for user approval.

### Step 3: Get Detailed Data

For each approved project:

```bash
uv run log-blog sessions --project <name> --json
```

This returns structured JSON with:
- **sessions**: conversation entries (user requests, code changes, errors, assistant responses)
- **git_commits**: actual commits with sha, message, files, insertions/deletions
- **files_changed**: all files touched across sessions

### Step 4: Write the Dev Log Post

Use the structured data to write a narrative dev log post. The post should be **problem → solution** oriented, not a topic overview.

**Template:**

```markdown
---
image: "/images/posts/YYYY-MM-DD-{slug}/cover.jpg"
title: "Series Title #N — Descriptive Subtitle"
description: Plain text summary for SEO
date: YYYY-MM-DD
categories: ["category"]
tags: ["tech1", "tech2"]
toc: true
math: false
---

## 개요
Brief summary of what was built/fixed today.
Link to previous post if this is a sequential series.

<!--more-->

---

## [Problem/Feature Name]

### 배경
Why this work was needed (from user_request entries in session data).

### 구현
What was done (from git commits + code_change entries).
Include actual code snippets from the diffs.

```python
# actual code from the session
```

### 문제 해결
Debugging narrative (from error entries):
"X를 시도 → Y 에러 → 원인: Z → 해결: ..."

---

## [Next Problem/Feature]
(Repeat the 배경/구현/문제 해결 pattern)

---

## 커밋 로그

| SHA | 메시지 | 변경 |
|-----|--------|------|
| abc1234 | feat: add bullish researcher | +120 -30 |

---

## 인사이트
Reflection connecting the day's work to broader patterns.
```

**Key rules for dev log posts:**
- Must include at least one Mermaid diagram (architecture change, before/after, or data flow)
- Follow all mermaid safety rules (description frontmatter, `<!--more-->`, `&lt;br/&gt;`, quote labels with `/`)
- Include actual error messages and the debugging journey
- Use code snippets from the actual session diffs
- Default language: Korean (same as tech-log posts)
- Use `--filename "YYYY-MM-DD-{project-slug}.md"` to avoid collisions

### Step 5: Publish

Same as the standard publish flow:

```bash
uv run log-blog publish /tmp/log-blog-post.md --filename "YYYY-MM-DD-{slug}.md" --cover-title "Post Title" --tags "tag1,tag2"
```

For sequential series (e.g., trading agent #4):
- Check existing posts with `uv run log-blog scan --json --limit 30`
- Find the latest post in the series and increment the number
- Link to the previous post in the 개요 section
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/log-blog-skill/skill.md
git commit -m "docs: add Dev Log Mode to log-blog skill"
```

---

### Task 8: End-to-end integration test

- [ ] **Step 1: Run the full pipeline manually**

```bash
# List projects
uv run log-blog sessions --list

# Get JSON for one project
uv run log-blog sessions --project log-blog --all --json > /tmp/sessions-test.json

# Verify the JSON is valid
python3 -c "import json; d = json.load(open('/tmp/sessions-test.json')); print(f'Projects: {len(d)}, Sessions: {d[0][\"session_count\"]}, Commits: {len(d[0][\"git_commits\"])}')"
```

Expected: Valid JSON with sessions and commits

- [ ] **Step 2: Verify session parsing quality**

```bash
# Check that conversation entries have meaningful content
python3 -c "
import json
d = json.load(open('/tmp/sessions-test.json'))
for s in d[0]['sessions'][:2]:
    print(f'Session {s[\"session_id\"][:8]}: {len(s[\"conversation\"])} entries, {s[\"duration_minutes\"]}m')
    for e in s['conversation'][:3]:
        print(f'  [{e[\"type\"]}] {e[\"text\"][:100]}')
    print()
"
```

Expected: Entries show user requests, code changes, errors with meaningful text

- [ ] **Step 3: Final commit with all changes**

If any fixes were needed during integration testing, commit them:

```bash
git add -A
git commit -m "fix: integration test adjustments for sessions command"
```
