"""Parse Claude Code CLI session transcripts (JSONL) into structured data."""

from __future__ import annotations

import json
import logging
import os
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
_MIN_SESSION_MESSAGES = 3
_MIN_SESSION_MINUTES = 2

_WORKTREE_SEPARATOR = "--claude-worktrees-"

# --- Tool classification ---
_INCLUDE_TOOLS = {"Edit", "Write", "Bash"}
_SUMMARY_TOOLS = {"WebFetch", "WebSearch", "Agent"}
_EXCLUDE_TOOLS = {
    "Read", "Grep", "Glob", "TodoWrite", "Skill", "ToolSearch",
    "NotebookEdit", "EnterPlanMode", "ExitPlanMode",
    "EnterWorktree", "ExitWorktree", "LSP",
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskStop", "TaskOutput",
    "AskUserQuestion", "CronCreate", "CronDelete", "CronList",
}


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


# ---------------------------------------------------------------------------
# Project auto-discovery
# ---------------------------------------------------------------------------


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

    if not dirname.startswith("-"):
        return None

    # Replace leading dash with /
    raw = "/" + dirname[1:]
    segments = raw.split("-")

    result_parts: list[str] = []
    i = 0
    while i < len(segments):
        # Try joining segments[i:j] greedily — longest match first
        matched = False
        for j in range(len(segments), i, -1):
            candidate = "-".join(segments[i:j])
            test_path = "/".join(result_parts + [candidate])
            if not test_path:
                continue
            if os.path.exists(test_path):
                result_parts.append(candidate)
                i = j
                matched = True
                break

        if not matched:
            # No match — append single segment and move on
            result_parts.append(segments[i])
            i += 1

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
    """Find all Claude Code projects with recent sessions."""
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

        # Derive project name from the last path component
        if repo_path:
            name = repo_path.name
        else:
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
        p.session_files.sort(key=lambda f: f.stat().st_mtime)
        result.append(p)

    result.sort(key=lambda p: len(p.session_files), reverse=True)
    return result


# ---------------------------------------------------------------------------
# JSONL session parsing
# ---------------------------------------------------------------------------


def _extract_user_text(content) -> str | None:
    """Extract plain text from a user message content field."""
    if isinstance(content, str):
        text = content.strip()
        if text.startswith(("<command-", "<task-notification", "<local-command")):
            return None
        if len(text) < 5:
            return None
        return text

    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block["text"].strip()
                if not t.startswith(("<command-", "<task-notification", "<local-command")) and len(t) >= 5:
                    texts.append(t)
        return "\n".join(texts) if texts else None

    return None


def _process_tool_use(block: dict) -> ConversationEntry | None:
    """Process a tool_use content block, returning a ConversationEntry or None."""
    name = block.get("name", "")
    inp = block.get("input", {})

    # MCP tools — skip
    if name.startswith("mcp__"):
        return None

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
            type="code_change", timestamp="", text=diff_text,
            file=file_path, action="edit",
        )

    if name == "Write":
        file_path = inp.get("file_path", "")
        content = inp.get("content", "")
        if len(content) > _MAX_CODE_CHANGE_CHARS:
            content = content[:_MAX_CODE_CHANGE_CHARS] + "\n[... truncated]"
        return ConversationEntry(
            type="code_change", timestamp="", text=content,
            file=file_path, action="write",
        )

    if name == "Bash":
        cmd = inp.get("command", "")
        return ConversationEntry(type="command", timestamp="", text="", command=cmd)

    if name in ("WebFetch", "WebSearch"):
        url = inp.get("url", "") or inp.get("query", "")
        return ConversationEntry(type="research", timestamp="", text="", url=url)

    if name == "Agent":
        prompt = inp.get("prompt", "")[:500]
        return ConversationEntry(type="agent_summary", timestamp="", text=prompt)

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


def parse_session(
    jsonl_path: Path,
    project_name: str = "",
    repo_path: str = "",
    repo_type: str = "local",
) -> SessionData | None:
    """Parse a single JSONL session file into structured data."""
    entries: list[ConversationEntry] = []
    timestamps: list[str] = []
    files_changed: set[str] = set()
    pending_bash: dict[str, ConversationEntry] = {}

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

                    if isinstance(content, list):
                        _process_tool_results(content, pending_bash)

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

    # Add non-error Bash commands (kept as "command" type)
    for entry in pending_bash.values():
        entries.append(entry)

    entries.sort(key=lambda e: e.timestamp)

    # Apply entry limit — prioritize user_request, error, code_change
    if len(entries) > _MAX_ENTRIES_PER_SESSION:
        priority = {
            "user_request": 0, "error": 1, "code_change": 2, "command": 3,
            "research": 4, "agent_summary": 5, "assistant_response": 6,
        }
        entries.sort(key=lambda e: (priority.get(e.type, 9), e.timestamp))
        entries = entries[:_MAX_ENTRIES_PER_SESSION]
        entries.sort(key=lambda e: e.timestamp)

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

    return SessionData(
        session_id=jsonl_path.stem,
        project_name=project_name,
        repo_path=repo_path,
        repo_type=repo_type,
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        duration_minutes=duration,
        conversation=entries,
        files_changed=sorted(files_changed),
    )


# ---------------------------------------------------------------------------
# Git log integration
# ---------------------------------------------------------------------------


def extract_git_commits(
    repo_path: Path,
    start_time: datetime,
    end_time: datetime,
) -> list[CommitInfo]:
    """Get git commits within a time window."""
    if not (repo_path / ".git").is_dir():
        return []

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

    import re

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

                if i + 1 < len(lines):
                    stat_line = lines[i + 1].strip()
                    if "insertion" in stat_line or "deletion" in stat_line:
                        ins_match = re.search(r"(\d+) insertion", stat_line)
                        del_match = re.search(r"(\d+) deletion", stat_line)
                        if ins_match:
                            insertions = int(ins_match.group(1))
                        if del_match:
                            deletions = int(del_match.group(1))
                        i += 1

                # Get files for this commit
                try:
                    files_result = subprocess.run(
                        ["git", "-C", str(repo_path), "diff-tree",
                         "--no-commit-id", "--name-only", "-r", sha],
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


# ---------------------------------------------------------------------------
# Project summary builder
# ---------------------------------------------------------------------------


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

        if not include_short:
            if session.duration_minutes < _MIN_SESSION_MINUTES and len(session.conversation) < _MIN_SESSION_MESSAGES:
                continue

        sessions.append(session)
        all_files.update(session.files_changed)

        try:
            s_start = datetime.fromisoformat(session.start_time.replace("Z", "+00:00"))
            s_end = datetime.fromisoformat(session.end_time.replace("Z", "+00:00"))
            if earliest is None or s_start < earliest:
                earliest = s_start
            if latest is None or s_end > latest:
                latest = s_end
        except Exception:
            pass

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
