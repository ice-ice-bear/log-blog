# Claude Code Sessions → Dev Log Blog Posts

**Date**: 2026-03-17
**Status**: Approved

## Problem

The user runs 20-40+ Claude Code CLI sessions daily across multiple projects (GitHub + Bitbucket). These sessions contain rich development narratives — debugging journeys, architectural decisions, code changes — that are ideal for detailed dev log blog posts. Currently there is no way to extract and use this data in the log-blog pipeline.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Content source | Hybrid: git log + JSONL sessions | Git log = "what changed", JSONL = "why/how" (debugging narrative) |
| Granularity | One post per project per day | Matches existing preference for separate posts per topic |
| Trigger | CLI command (`sessions`) + updated skill | JSONL parsing too complex for ad-hoc Claude; skill orchestrates |
| JSONL extraction | Smart: user msgs, assistant text, errors, code diffs | Captures debugging journey; skips noise (reads, searches, hooks) |
| Project mapping | Auto-discovery from directory names, config overrides | Less maintenance than manual registry |
| Post style | Narrative dev log (problem → solution) | Different from tech-log topic overviews |

## Architecture

```
~/.claude/projects/{project}/*.jsonl  ──┐
                                        ├──→  `uv run log-blog sessions`  ──→  structured JSON
{project-repo}/.git/log                ──┘           (CLI command)              │
                                                                                ↓
                                                                    Claude (via skill)
                                                                         writes post
                                                                                ↓
                                                                    `uv run log-blog publish`
```

## Components

### 1. Project Auto-Discovery

The Claude Code project directory name encodes the filesystem path:
- `-Users-lsr-Documents-github-trading-agent` → `~/Documents/github/trading-agent`

**Algorithm**:
1. Scan `~/.claude/projects/` for directories containing `.jsonl` files modified within `--hours`
2. Reverse-map directory name to filesystem path (replace leading `-` with `/`, internal `-` with `/` where path segments match)
3. Verify the mapped path is a git repository
4. Detect repo type: check for `.git` remote URL containing `github.com` vs `bitbucket.org`

**Config override** (optional, in `config.yaml`):
```yaml
sessions:
  claude_dir: "~/.claude/projects"  # default
  projects:
    # Override auto-discovery for edge cases
    custom-name:
      session_dir: "~/.claude/projects/-Users-lsr-some-weird-path"
      repo_path: "~/Documents/actual/repo/path"
```

### 2. Session Parser (`session_parser.py`)

Reads JSONL files and applies smart extraction rules:

**Inclusion rules by message type:**

| Message type | Include? | Extract |
|---|---|---|
| User text messages | Yes | Full text (narrative spine) |
| Assistant text responses | Yes | Full text (decisions, explanations) |
| Assistant thinking blocks | No | Internal reasoning, too noisy |
| Edit/Write tool calls | Yes | File path + input (the diff/content) |
| Bash tool calls with errors | Yes | Command + stderr/error output |
| Bash tool calls (success) | Summary | Command only, not full output |
| Read/Grep/Glob tool calls | No | Exploration, not narrative |
| Progress/hook events | No | System noise |
| Agent sub-tasks | Summary | Delegation description + result summary |
| file-history-snapshot | No | System bookkeeping |
| queue-operation | No | System bookkeeping |

**Key functions:**

```python
def parse_session(jsonl_path: Path) -> SessionData:
    """Parse a single JSONL session file into structured data."""

def discover_projects(hours: int, claude_dir: Path) -> list[ProjectInfo]:
    """Find all projects with recent sessions, auto-map to git repos."""

def extract_git_commits(repo_path: Path, start_time: datetime, end_time: datetime) -> list[CommitInfo]:
    """Get git commits within the session's time window."""

def build_project_summary(project: ProjectInfo, hours: int) -> ProjectSummary:
    """Combine all sessions + git commits for one project."""
```

**Output schema — `SessionData`:**

```python
@dataclass
class ConversationEntry:
    type: str          # "user_request" | "assistant_response" | "code_change" | "error" | "agent_summary"
    timestamp: str     # ISO 8601
    text: str          # Message content or error text
    file: str | None   # For code_change entries
    action: str | None # "edit" | "write" | "delete" for code_change
    command: str | None # For error entries (the bash command that failed)

@dataclass
class CommitInfo:
    sha: str
    message: str
    timestamp: str
    files: list[str]
    insertions: int
    deletions: int

@dataclass
class SessionData:
    session_id: str
    project_name: str
    repo_path: str
    repo_type: str           # "github" | "bitbucket" | "local"
    start_time: str
    end_time: str
    duration_minutes: int
    conversation: list[ConversationEntry]
    files_changed: list[str]

@dataclass
class ProjectSummary:
    project_name: str
    repo_path: str
    repo_type: str
    session_count: int
    total_duration_minutes: int
    sessions: list[SessionData]
    git_commits: list[CommitInfo]
    files_changed: list[str]  # Deduplicated across all sessions
```

**JSON output** (for `--json` flag):

```json
{
  "project_name": "trading-agent",
  "repo_path": "~/Documents/github/trading-agent",
  "repo_type": "github",
  "session_count": 22,
  "total_duration_minutes": 480,
  "sessions": [
    {
      "session_id": "abc123...",
      "start_time": "2026-03-17T09:00:00Z",
      "end_time": "2026-03-17T09:45:00Z",
      "duration_minutes": 45,
      "conversation": [
        {"type": "user_request", "timestamp": "...", "text": "add Bullish researcher agent"},
        {"type": "code_change", "timestamp": "...", "file": "agents/bullish.py", "action": "write", "text": "class BullishResearcher:..."},
        {"type": "error", "timestamp": "...", "command": "python test_agents.py", "text": "ImportError: cannot import name 'BullishResearcher'"},
        {"type": "assistant_response", "timestamp": "...", "text": "The import path needs updating..."}
      ],
      "files_changed": ["agents/bullish.py", "agents/__init__.py"]
    }
  ],
  "git_commits": [
    {
      "sha": "abc123",
      "message": "feat: add bullish researcher agent",
      "timestamp": "2026-03-17T09:40:00Z",
      "files": ["agents/bullish.py", "agents/__init__.py"],
      "insertions": 120,
      "deletions": 5
    }
  ],
  "files_changed": ["agents/bullish.py", "agents/__init__.py", "..."]
}
```

### 3. CLI Command

Added to `cli.py`:

```
uv run log-blog sessions [OPTIONS]

Options:
  --hours N        Time window (default: 24)
  --project NAME   Filter to one project (by auto-discovered name)
  --all            Show all projects (default: only projects with 2+ sessions)
  --json           Output structured JSON (for skill pipeline)
  --list           Just list projects with session counts (no detail)
```

**Examples:**

```bash
# Quick overview: what did I work on today?
uv run log-blog sessions --list
# Output:
# trading-agent    22 sessions  12 commits  8h 15m
# hybrid-search     9 sessions   5 commits  3h 40m
# log-blog         10 sessions   3 commits  2h 10m

# Detailed extraction for blog post
uv run log-blog sessions --project trading-agent --json

# All projects, full detail
uv run log-blog sessions --all --json
```

### 4. Skill Integration

Add a "Dev Log Mode" section to `.claude/skills/log-blog-skill/skill.md`:

**Trigger**: User says "make a dev log", "write dev log from sessions", "what did I work on today" or similar.

**Flow**:

1. Run `uv run log-blog sessions --list` to show project overview
2. Present to user: "Today you worked on N projects. Which ones should get dev log posts?"
3. For each approved project, run `uv run log-blog sessions --project X --json`
4. Claude writes the post using the structured data
5. Standard publish flow with `--cover-title` and `--tags`

**Blog post template for dev logs:**

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
Brief: what was built/fixed today.
Link to previous post if sequential.

<!--more-->

---

## [Problem/Feature Name]

### 배경
Why this work was needed (from user_request messages).

### 구현
What was done (from git commits + code_change events).
Include actual code snippets from diffs.

### 문제 해결
Debugging narrative (from error events):
"X를 시도 → Y 에러 → 원인: Z → 해결: ..."

---

## [Next Problem/Feature]
...

---

## 커밋 로그

| SHA | 메시지 | 변경 |
|-----|--------|------|
| abc1234 | feat: add bullish researcher | +120 -30 |

---

## 인사이트
Reflection connecting the day's work to broader patterns.
```

**Key differences from tech-log posts:**
- Narrative-driven (problem → investigation → solution) not topic-driven
- Includes actual error messages and debugging steps
- Commit log table at the end
- Sequential numbering when part of an ongoing series
- Mermaid diagrams show architecture changes or before/after flows

### 5. Size Limits and Truncation

Sessions can be large. Limits to prevent context overflow:

- **Conversation entries**: Max 100 entries per session (prioritize user_request, error, code_change)
- **Code change text**: Max 2000 chars per entry (truncate with `[... truncated]`)
- **Error output**: Max 1000 chars per entry
- **Assistant responses**: Max 500 chars per entry (these are summaries, not the meat)
- **Total output per project**: If `--json` output exceeds 100KB, further truncate assistant_response entries

## Files to Create/Modify

| File | Action | Purpose |
|---|---|---|
| `src/log_blog/session_parser.py` | Create | JSONL parsing + smart extraction |
| `src/log_blog/cli.py` | Modify | Add `sessions` command |
| `src/log_blog/config.py` | Modify | Add `sessions` config section |
| `config.example.yaml` | Modify | Document sessions config |
| `.claude/skills/log-blog-skill/skill.md` | Modify | Add Dev Log Mode section |

## Edge Cases

- **Session spans midnight**: Use session start_time for date grouping
- **No git commits** (exploratory session): Still include conversation narrative, note "no commits"
- **Repo not found** (deleted or moved): Skip git log, warn in output
- **Very short sessions** (<2 minutes, <3 messages): Filter out by default, include with `--all`
- **Worktree sessions**: Directory name contains worktree suffix — strip it for repo mapping
