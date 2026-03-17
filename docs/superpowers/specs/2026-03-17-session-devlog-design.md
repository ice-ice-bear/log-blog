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

**Algorithm** (greedy filesystem matching):
1. Scan `~/.claude/projects/` for directories containing `.jsonl` files modified within `--hours`
2. Strip worktree suffix: split on `--claude-worktrees-` and take the first part
3. Reverse-map directory name to filesystem path:
   - Replace the leading `-` with `/` to get a raw path string (e.g., `/Users/lsr/Documents/github/trading-agent`)
   - Split on `-` to get candidate segments
   - Starting from index 0, greedily try joining segments with `/` and check if the path exists on disk
   - Use the longest matching prefix that resolves to a real directory
   - Example: `-Users-lsr-Documents-bitbucket-hybrid-image-search-demo` → try `/Users` ✓, `/Users/lsr` ✓, ..., `/Users/lsr/Documents/bitbucket/hybrid-image-search-demo` ✓ (stop, full match)
   - Example with hyphens: segments `hybrid`, `image`, `search`, `demo` → try `hybrid-image-search-demo/` first (as single directory name), then `hybrid-image-search/demo/`, etc.
4. Verify the mapped path is a git repository (`os.path.isdir(path / '.git')`)
5. Detect repo type: parse `.git/config` or run `git remote get-url origin` — check for `github.com` vs `bitbucket.org`

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

Reads JSONL files and applies smart extraction rules.

**JSONL message format** (from Claude Code CLI):

Each line is a JSON object with a top-level `type` field:
- `"user"` — user messages. `obj["message"]["content"]` is either a plain string (user text) or a list containing `tool_result` dicts (with `tool_use_id`, `content`, `is_error` fields).
- `"assistant"` — assistant messages. `obj["message"]["content"]` is a list of content blocks, each with `type` = `"thinking"`, `"text"`, or `"tool_use"`. Tool use blocks have `name` (e.g., `Bash`, `Edit`, `Write`, `Read`, `Grep`) and `input` dict.
- `"system"` — system prompts/context injection. Excluded.
- `"progress"` — hook events, agent progress, query updates. Excluded.
- `"file-history-snapshot"` — file backup bookkeeping. Excluded.
- `"queue-operation"` — internal queue management. Excluded.
- `"last-prompt"` — session end marker. Excluded.

Tool results appear as `tool_result` blocks inside the next `"user"` message, paired by `tool_use_id`. Error results have `is_error: true`.

The `session_id` is the JSONL filename (UUID). Note: a resumed session creates a new JSONL file but may reference the same `sessionId` in message fields. We treat each JSONL file as a separate session for simplicity.

**Inclusion rules by message/tool type:**

| Message type | Include? | Extract |
|---|---|---|
| User text messages | Yes | Full text (narrative spine) |
| Assistant text responses | Yes | Full text, max 1500 chars (decisions, explanations) |
| Assistant thinking blocks | No | Internal reasoning, too noisy |
| Edit/Write tool calls | Yes | File path + input (the diff/content) |
| Bash tool calls with errors | Yes | Command + stderr/error output |
| Bash tool calls (success) | Summary | Command only, not full output |
| Read/Grep/Glob tool calls | No | Exploration, not narrative |
| WebFetch/WebSearch tool calls | Summary | URL/query only (research context) |
| Agent tool calls | Summary | Delegation description + result summary |
| TodoWrite/Skill/ToolSearch | No | Internal bookkeeping |
| MCP tools (`mcp__*`) | No | External tool noise |
| Progress/hook/system events | No | System noise |
| file-history-snapshot | No | System bookkeeping |
| queue-operation/last-prompt | No | System bookkeeping |

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
    type: str          # "user_request" | "assistant_response" | "code_change" | "error" | "command" | "research" | "agent_summary"
    timestamp: str     # ISO 8601
    text: str          # Message content or error text
    file: str | None   # For code_change entries
    action: str | None # "edit" | "write" | "delete" for code_change
    command: str | None # For error and command entries (the bash command)
    url: str | None    # For research entries (WebFetch/WebSearch URL or query)

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
  --all            Show all projects including those with only 1 session (default: 2+ sessions)
  --include-short  Include very short sessions (<2 min or <3 messages), excluded by default
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
- **Assistant responses**: Max 1500 chars per entry (keep explanatory narrative)
- **Total output per project**: If `--json` output exceeds 100KB, further truncate assistant_response entries

### 6. Config Integration

Add to `config.py`:

```python
@dataclass
class SessionsConfig:
    claude_dir: str = "~/.claude/projects"
    # Manual project overrides stored as a raw dict since
    # nested dict[str, dataclass] doesn't fit _filter_fields pattern.
    # Parsed manually in session_parser.py.
```

Add to `Config` dataclass:
```python
sessions: SessionsConfig = field(default_factory=SessionsConfig)
```

Add to `config.example.yaml`:
```yaml
sessions:
  claude_dir: "~/.claude/projects"  # Where Claude Code stores session transcripts
  # projects:                       # Optional overrides for auto-discovery
  #   custom-name:
  #     session_dir: "~/.claude/projects/-Users-lsr-some-weird-path"
  #     repo_path: "~/Documents/actual/repo/path"
```

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
- **Very short sessions** (<2 minutes, <3 messages): Filter out by default, include with `--include-short`
- **Worktree sessions**: Directory name contains `--claude-worktrees-{name}` suffix — split on `--claude-worktrees-` and take the first part for repo mapping
- **Resumed sessions**: Multiple JSONL files may share the same in-message `sessionId` — each JSONL file is treated as a separate session (using filename UUID as `session_id`)
