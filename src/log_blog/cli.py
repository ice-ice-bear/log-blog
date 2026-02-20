from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .config import load_config
from .content_fetcher import fetch_pages
from .history_reader import read_history
from .post_generator import post_filename
from .publisher import publish_post, pull_latest

console = Console()


def cmd_extract(args: argparse.Namespace) -> None:
    """Extract and display browsing history."""
    config = load_config(args.config)
    if args.hours:
        config.time_range_hours = args.hours

    entries = read_history(config)

    if args.json:
        data = [
            {
                "url": e.url,
                "title": e.title,
                "visit_count": e.visit_count,
                "last_visit_time": e.last_visit_iso,
            }
            for e in entries
        ]
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if not entries:
        console.print("[yellow]No history entries found for the given time range.[/yellow]")
        return

    table = Table(title=f"Browsing History (last {config.time_range_hours}h)")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", max_width=60)
    table.add_column("URL", max_width=60, style="blue")
    table.add_column("Visits", justify="right", width=6)
    table.add_column("Last Visit", width=20)

    for i, entry in enumerate(entries, 1):
        table.add_row(
            str(i),
            entry.title[:60] if entry.title else "[dim]untitled[/dim]",
            entry.url[:60],
            str(entry.visit_count),
            entry.last_visit_iso[:19],
        )

    console.print(table)
    console.print(f"\n[green]Total: {len(entries)} entries[/green]")


def cmd_fetch(args: argparse.Namespace) -> None:
    """Fetch content from URLs."""
    config = load_config(args.config)
    urls = args.urls

    console.print(f"[blue]Fetching {len(urls)} page(s)...[/blue]")
    results = fetch_pages(urls, config)

    if args.json:
        data = [
            {
                "url": r.url,
                "title": r.title,
                "text_content": r.text_content,
                "success": r.success,
                "error": r.error,
                "url_type": r.url_type,
                "metadata": r.metadata,
            }
            for r in results
        ]
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    for result in results:
        if result.success:
            type_tag = f"[cyan][{result.url_type}][/cyan] " if result.url_type != "web_page" else ""
            console.print(f"\n{type_tag}[green]--- {result.title} ---[/green]")
            console.print(f"URL: {result.url}")
            preview = result.text_content[:500]
            console.print(preview)
            if len(result.text_content) > 500:
                console.print(f"[dim]... ({len(result.text_content)} chars total)[/dim]")
        else:
            console.print(f"\n[red]FAILED: {result.url}[/red]")
            console.print(f"  Error: {result.error}")


def cmd_publish(args: argparse.Namespace) -> None:
    """Publish a markdown file to the blog repo."""
    config = load_config(args.config)
    file_path = Path(args.file)

    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        sys.exit(1)

    content = file_path.read_text(encoding="utf-8")
    filename = args.filename or post_filename()

    console.print(f"[blue]Publishing {filename} to blog repo...[/blue]")
    pull_latest(config)
    post_path = publish_post(content, filename, config, push=args.push)
    console.print(f"[green]Published to {post_path}[/green]")

    if not args.push:
        console.print("[yellow]Post committed locally. Use --push to push to remote, or run 'git push' in the blog repo.[/yellow]")


def main() -> None:
    parser = argparse.ArgumentParser(prog="log-blog", description="Browser history to blog pipeline")
    parser.add_argument("--config", "-c", help="Path to config.yaml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # extract
    p_extract = subparsers.add_parser("extract", help="Extract browsing history")
    p_extract.add_argument("--hours", type=int, help="Override time range (hours)")
    p_extract.add_argument("--json", action="store_true", help="Output as JSON")
    p_extract.set_defaults(func=cmd_extract)

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch page content from URLs")
    p_fetch.add_argument("urls", nargs="+", help="URLs to fetch")
    p_fetch.add_argument("--json", action="store_true", help="Output as JSON")
    p_fetch.set_defaults(func=cmd_fetch)

    # publish
    p_pub = subparsers.add_parser("publish", help="Publish a markdown file to the blog repo")
    p_pub.add_argument("file", help="Path to the markdown file to publish")
    p_pub.add_argument("--filename", help="Override output filename (default: YYYY-MM-DD-tech-log.md)")
    p_pub.add_argument("--push", action="store_true", help="Push to remote after committing")
    p_pub.set_defaults(func=cmd_publish)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
