from __future__ import annotations

from datetime import date

from .content_fetcher import PageContent


def generate_post(
    entries: list[dict],
    contents: list[PageContent],
    tags: list[str],
    language: str = "en",
    post_date: date | None = None,
    introduction: str = "",
    highlights: list[dict] | None = None,
    quick_links: list[dict] | None = None,
    insights: str = "",
    image: str = "",
) -> str:
    """Generate a Hugo-compatible markdown blog post.

    This generates a template when called from CLI. When used via the Claude Code
    skill, Claude generates the actual content (introduction, highlights, insights)
    and passes them in.

    Args:
        entries: List of {"url": str, "title": str} dicts for all included links.
        contents: Fetched page contents for enrichment.
        tags: List of tags for the post.
        language: "en" or "ko".
        post_date: Date for the post. Defaults to today.
        introduction: AI-generated introduction text.
        highlights: List of {"url", "title", "summary"} for top items.
        quick_links: List of {"url", "title", "description"} for remaining items.
        insights: AI-generated insights/reflection text.
        image: Hugo-relative URL for the cover image (e.g., "/images/posts/slug/cover.jpg").
    """
    if post_date is None:
        post_date = date.today()

    date_str = post_date.isoformat()
    tags_str = ", ".join(f'"{t}"' for t in tags)

    # Build frontmatter (image first to match existing blog convention)
    title = f"Tech Log: {date_str}" if language == "en" else f"기술 로그: {date_str}"
    lines = ["---"]
    if image:
        lines.append(f'image: "{image}"')
    lines.extend([
        f'title: "{title}"',
        f"date: {date_str}",
        'categories: ["tech-log"]',
        f"tags: [{tags_str}]",
        "toc: true",
        "math: false",
        "---",
        "",
    ])

    # Introduction
    if introduction:
        if language == "ko":
            lines.append("## 개요")
        else:
            lines.append("## Overview")
        lines.append("")
        lines.append(introduction)
        lines.append("")

    # Highlights
    if highlights:
        if language == "ko":
            lines.append("## 주요 하이라이트")
        else:
            lines.append("## Highlights")
        lines.append("")
        for item in highlights:
            lines.append(f"### [{item['title']}]({item['url']})")
            lines.append("")
            lines.append(item.get("summary", ""))
            lines.append("")

    # Quick Links
    if quick_links:
        if language == "ko":
            lines.append("## 빠른 링크")
        else:
            lines.append("## Quick Links")
        lines.append("")
        for item in quick_links:
            desc = item.get("description", "")
            lines.append(f"- [{item['title']}]({item['url']}) — {desc}")
        lines.append("")

    # Insights
    if insights:
        if language == "ko":
            lines.append("## 인사이트")
        else:
            lines.append("## Insights")
        lines.append("")
        lines.append(insights)
        lines.append("")

    # If no structured content was provided, generate a simple link list
    if not introduction and not highlights and not quick_links and not insights:
        if language == "ko":
            lines.append("## 링크")
        else:
            lines.append("## Links")
        lines.append("")
        content_map = {c.url: c for c in contents if c.success}
        for entry in entries:
            url = entry["url"]
            title = entry.get("title", url)
            content = content_map.get(url)
            if content and content.text_content:
                # Use first 200 chars as description
                desc = content.text_content[:200].replace("\n", " ").strip()
                lines.append(f"- [{title}]({url}) — {desc}...")
            else:
                lines.append(f"- [{title}]({url})")
        lines.append("")

    return "\n".join(lines)


def post_filename(post_date: date | None = None) -> str:
    """Generate the filename for a tech log post."""
    if post_date is None:
        post_date = date.today()
    return f"{post_date.isoformat()}-tech-log.md"
