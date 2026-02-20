"""Parse AI chat export files from ChatGPT, Claude, and Gemini.

Each service exports conversations in a different format:
  - ChatGPT: conversations.json (tree-structured mapping of nodes)
  - Claude:  conversations.json (simple array of chat_messages)
  - Gemini:  HTML files from Google Takeout

All parsers return a list of dicts matching the PageContent JSON schema so the
skill can treat them identically to fetched web pages.

source: "offline" — content from a local export file, not fetched from the web.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_MSG = 1500   # chars per individual message before truncation
_MAX_CONV = 10000  # chars per conversation total


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_ai_export(path: str | Path, days: int | None = None) -> list[dict]:
    """Auto-detect and parse an AI chat export file or directory.

    Args:
        path: Path to a file (conversations.json, *.html) or directory.
        days: If set, only include conversations updated within this many days.

    Returns:
        List of PageContent-compatible dicts with source="offline".
    """
    p = Path(path).expanduser()

    if p.is_dir():
        return _parse_directory(p, days)

    if not p.exists():
        logger.error("Export file not found: %s", p)
        return []

    service = _detect_service(p)
    if service == "chatgpt":
        return _parse_chatgpt(p, days)
    elif service == "claude":
        return _parse_claude(p, days)
    elif service == "gemini":
        return _parse_gemini_html(p, days)
    else:
        logger.warning("Could not detect AI export format for %s", p)
        return []


def _detect_service(path: Path) -> str:
    """Guess which AI service exported this file by inspecting its content."""
    if path.suffix == ".html":
        return "gemini"
    if path.suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                first = data[0]
                if "mapping" in first:
                    return "chatgpt"
                if "chat_messages" in first:
                    return "claude"
        except Exception:
            pass
    return "unknown"


def _parse_directory(directory: Path, days: int | None) -> list[dict]:
    """Parse all recognizable export files in a directory."""
    results = []
    for html_file in directory.rglob("*.html"):
        results.extend(_parse_gemini_html(html_file, days))
    for json_file in directory.rglob("conversations.json"):
        service = _detect_service(json_file)
        if service == "chatgpt":
            results.extend(_parse_chatgpt(json_file, days))
        elif service == "claude":
            results.extend(_parse_claude(json_file, days))
    return results


def _cutoff_timestamp(days: int | None) -> float:
    """Unix timestamp for `days` ago, or 0 if no filter."""
    import time
    if days is None:
        return 0.0
    return time.time() - (days * 86400)


# ---------------------------------------------------------------------------
# ChatGPT parser
# ---------------------------------------------------------------------------

def _parse_chatgpt(path: Path, days: int | None) -> list[dict]:
    """Parse a ChatGPT conversations.json export."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to parse ChatGPT export %s: %s", path, e)
        return []

    cutoff = _cutoff_timestamp(days)
    results = []

    for conv in data:
        update_time = conv.get("update_time") or conv.get("create_time") or 0
        if update_time < cutoff:
            continue

        title = conv.get("title", "Untitled conversation")
        mapping = conv.get("mapping", {})
        messages = _walk_chatgpt_tree(mapping)
        if not messages:
            continue

        text = _format_messages(messages)
        conv_id = conv.get("id", "")
        results.append(_make_page_content(
            url=f"export://chatgpt/{conv_id}",
            title=f"[ChatGPT] {title}",
            text_content=text,
            service="chatgpt",
            conversation_id=conv_id,
            created_at=str(conv.get("create_time", "")),
        ))

    return results


def _walk_chatgpt_tree(mapping: dict) -> list[dict]:
    """Walk the ChatGPT conversation tree following the main thread."""
    # Find root node (no parent or parent is None)
    root_id = None
    for node_id, node in mapping.items():
        if node.get("parent") is None:
            root_id = node_id
            break

    if root_id is None:
        return []

    messages = []
    current_id = root_id

    while current_id:
        node = mapping.get(current_id)
        if node is None:
            break

        msg = node.get("message")
        if msg:
            role = (msg.get("author") or {}).get("role", "")
            content = msg.get("content") or {}
            if role in ("user", "assistant") and content.get("content_type") == "text":
                parts = content.get("parts") or []
                text = "".join(str(p) for p in parts if isinstance(p, str)).strip()
                if text:
                    messages.append({"role": role, "text": text[:_MAX_MSG]})

        # Follow the last child (= accepted/final response in case of regenerations)
        children = node.get("children") or []
        current_id = children[-1] if children else None

    return messages


# ---------------------------------------------------------------------------
# Claude parser
# ---------------------------------------------------------------------------

def _parse_claude(path: Path, days: int | None) -> list[dict]:
    """Parse a Claude conversations.json export."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to parse Claude export %s: %s", path, e)
        return []

    import time
    cutoff = _cutoff_timestamp(days)
    results = []

    for conv in data:
        updated_at = conv.get("updated_at") or conv.get("created_at") or ""
        if updated_at and cutoff > 0:
            try:
                from datetime import datetime, timezone
                ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).timestamp()
                if ts < cutoff:
                    continue
            except Exception:
                pass

        title = conv.get("name") or "Untitled conversation"
        conv_id = conv.get("uuid", "")
        messages = []

        for msg in conv.get("chat_messages") or []:
            role = msg.get("sender", "")
            text = (msg.get("text") or "").strip()
            if role in ("human", "assistant") and text:
                label = "user" if role == "human" else "assistant"
                messages.append({"role": label, "text": text[:_MAX_MSG]})

        if not messages:
            continue

        results.append(_make_page_content(
            url=f"export://claude/{conv_id}",
            title=f"[Claude] {title}",
            text_content=_format_messages(messages),
            service="claude",
            conversation_id=conv_id,
            created_at=conv.get("created_at", ""),
        ))

    return results


# ---------------------------------------------------------------------------
# Gemini HTML parser (Google Takeout)
# ---------------------------------------------------------------------------

def _parse_gemini_html(path: Path, days: int | None) -> list[dict]:
    """Parse a Gemini conversation HTML file from Google Takeout."""
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.error("Failed to read Gemini export %s: %s", path, e)
        return []

    # Extract plain text — strip script/style blocks first, then all remaining tags
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()

    if not text or len(text) < 100:
        return []

    # Use filename stem as title (Takeout files are named by conversation)
    title = path.stem.replace("-", " ").replace("_", " ").title()

    return [_make_page_content(
        url=f"export://gemini/{path.stem}",
        title=f"[Gemini] {title}",
        text_content=text[:_MAX_CONV],
        service="gemini",
        conversation_id=path.stem,
        created_at="",
    )]


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _format_messages(messages: list[dict]) -> str:
    """Format a list of {role, text} dicts into a readable transcript."""
    parts = []
    for msg in messages:
        label = "[USER]" if msg["role"] == "user" else "[ASSISTANT]"
        parts.append(f"{label}\n{msg['text']}")
    return "\n\n".join(parts)[:_MAX_CONV]


def _make_page_content(
    url: str,
    title: str,
    text_content: str,
    service: str,
    conversation_id: str,
    created_at: str,
) -> dict:
    """Return a dict matching the PageContent JSON schema."""
    return {
        "url": url,
        "title": title,
        "text_content": text_content,
        "success": True,
        "error": None,
        "url_type": "ai_chat_export",
        "metadata": {
            "service": service,
            "source": "offline",
            "conversation_id": conversation_id,
            "created_at": created_at,
        },
    }
