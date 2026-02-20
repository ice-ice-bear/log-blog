from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from .config import Config


@dataclass
class ExistingPost:
    filename: str
    path: str  # absolute path as string
    title: str
    date: str  # YYYY-MM-DD
    tags: list[str]
    categories: list[str]
    content_preview: str  # first 300 chars of body text


def scan_existing_posts(config: Config, limit: int = 30) -> list[ExistingPost]:
    """Scan blog repo content dir for existing posts, returning newest first.

    Reads all .md files in the configured content directory, parses YAML
    frontmatter from each, and returns structured post metadata.
    """
    posts_dir = config.blog.content_path
    if not posts_dir.exists():
        return []

    md_files = sorted(
        posts_dir.glob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    posts: list[ExistingPost] = []
    for md_file in md_files[:limit]:
        try:
            post = _parse_post(md_file)
            if post is not None:
                posts.append(post)
        except Exception:
            continue

    return posts


def _parse_post(path: Path) -> ExistingPost | None:
    """Parse a Hugo markdown post, extracting YAML frontmatter and body preview."""
    text = path.read_text(encoding="utf-8")

    # Match --- frontmatter block ---
    match = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
    if not match:
        return None

    fm_str, body = match.group(1), match.group(2)

    try:
        fm = yaml.safe_load(fm_str)
    except yaml.YAMLError:
        return None

    if not isinstance(fm, dict):
        return None

    # Normalize date to YYYY-MM-DD string (yaml may parse it as date object)
    date_val = fm.get("date", "")
    if hasattr(date_val, "isoformat"):
        date_str = date_val.isoformat()[:10]
    else:
        date_str = str(date_val)[:10]

    return ExistingPost(
        filename=path.name,
        path=str(path),
        title=str(fm.get("title", path.stem)),
        date=date_str,
        tags=list(fm.get("tags", []) or []),
        categories=list(fm.get("categories", []) or []),
        content_preview=body.strip()[:300],
    )
