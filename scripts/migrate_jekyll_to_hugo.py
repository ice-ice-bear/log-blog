#!/usr/bin/env python3
"""Migrate Jekyll posts from ice-ice-bear.github.io to Hugo format."""

import re
import sys
from pathlib import Path

import yaml


JEKYLL_REPO = Path.home() / "Documents/github/ice-ice-bear.github.io"
HUGO_CONTENT_DIR = JEKYLL_REPO / "content/posts"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def convert_frontmatter(fm: dict) -> dict:
    """Convert Jekyll frontmatter to Hugo format."""
    new_fm = {}

    # Title
    if "title" in fm:
        new_fm["title"] = fm["title"]

    # Date — extracted from filename, but keep if present
    if "date" in fm:
        new_fm["date"] = fm["date"]

    # Categories: string -> list
    if "categories" in fm:
        cats = fm["categories"]
        if isinstance(cats, str):
            new_fm["categories"] = [cats]
        else:
            new_fm["categories"] = list(cats)

    # Tags: 'tag' -> 'tags' (Hugo convention)
    tags = fm.get("tags") or fm.get("tag")
    if tags:
        if isinstance(tags, str):
            new_fm["tags"] = [tags]
        else:
            new_fm["tags"] = list(tags)

    # Math: use_math -> math
    if fm.get("use_math"):
        new_fm["math"] = True

    # ToC
    if fm.get("toc"):
        new_fm["toc"] = True

    # Skip: layout, typora-root-url (not needed in Hugo)

    return new_fm


def fix_image_paths(content: str) -> str:
    """Fix image paths for Hugo.

    Jekyll: ![alt](/images/...) or ![alt](../images/...)
    Hugo:   ![alt](/images/...) (absolute paths work since images go in static/)
    """
    # Fix relative paths like ../images/ to /images/
    content = re.sub(
        r"!\[([^\]]*)\]\(\.\./images/",
        r"![\1](/images/",
        content,
    )
    return content


def migrate_post(jekyll_path: Path) -> tuple[str, str]:
    """Migrate a single Jekyll post to Hugo format.

    Returns (filename, content) tuple.
    """
    raw = jekyll_path.read_text(encoding="utf-8")

    # Extract frontmatter
    match = FRONTMATTER_RE.match(raw)
    if not match:
        print(f"  WARNING: No frontmatter found in {jekyll_path.name}, skipping")
        return None, None

    fm_text = match.group(1)
    body = raw[match.end():]

    # Parse Jekyll frontmatter
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        print(f"  WARNING: Failed to parse frontmatter in {jekyll_path.name}: {e}")
        return None, None

    # Extract date from filename (YYYY-MM-DD-title.md)
    filename = jekyll_path.name
    date_match = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)\.md", filename)
    if date_match:
        date_str = date_match.group(1)
        slug = date_match.group(2)
    else:
        print(f"  WARNING: Cannot extract date from {filename}, skipping")
        return None, None

    # Convert frontmatter
    hugo_fm = convert_frontmatter(fm)
    if "date" not in hugo_fm:
        hugo_fm["date"] = date_str

    # Fix body content
    body = fix_image_paths(body)

    # Build Hugo post
    hugo_fm_text = yaml.dump(hugo_fm, allow_unicode=True, default_flow_style=False).strip()
    hugo_content = f"---\n{hugo_fm_text}\n---\n{body}"

    # Sanitize filename — replace brackets and special chars
    safe_slug = slug.replace("[", "").replace("]", "")
    output_filename = f"{date_str}-{safe_slug}.md"

    return output_filename, hugo_content


def main():
    posts_dir = JEKYLL_REPO / "_posts"
    if not posts_dir.exists():
        print(f"ERROR: Jekyll posts directory not found: {posts_dir}")
        sys.exit(1)

    HUGO_CONTENT_DIR.mkdir(parents=True, exist_ok=True)

    jekyll_posts = sorted(posts_dir.glob("*.md"))
    print(f"Found {len(jekyll_posts)} Jekyll posts")

    migrated = 0
    for post_path in jekyll_posts:
        print(f"Migrating: {post_path.name}")
        output_filename, content = migrate_post(post_path)
        if output_filename is None:
            continue

        output_path = HUGO_CONTENT_DIR / output_filename
        output_path.write_text(content, encoding="utf-8")
        print(f"  -> {output_filename}")
        migrated += 1

    print(f"\nMigrated {migrated}/{len(jekyll_posts)} posts to {HUGO_CONTENT_DIR}")


if __name__ == "__main__":
    main()
