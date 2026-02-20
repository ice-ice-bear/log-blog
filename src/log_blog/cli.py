from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .ai_export_parser import parse_ai_export
from .config import load_config
from .content_fetcher import fetch_pages
from .history_reader import list_chrome_profiles, read_history
from .post_advisor import scan_existing_posts
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


def cmd_profiles(args: argparse.Namespace) -> None:
    """List all Chrome profiles with their associated Google accounts."""
    config = load_config(args.config)
    profiles = list_chrome_profiles(config)

    if not profiles:
        console.print("[yellow]No Chrome profiles found. Check chrome.history_db_base in config.yaml.[/yellow]")
        return

    if args.json:
        print(json.dumps(profiles, ensure_ascii=False, indent=2))
        return

    filter_note = ""
    if config.chrome.google_accounts:
        filter_note = f" (filtered by google_accounts: {', '.join(config.chrome.google_accounts)})"
    elif config.chrome.profiles:
        filter_note = f" (active profiles: {', '.join(config.chrome.profiles)})"

    table = Table(title=f"Chrome Profiles{filter_note}")
    table.add_column("Folder", width=12)
    table.add_column("Name", max_width=20)
    table.add_column("Google Account", max_width=40)
    table.add_column("Active", width=8, justify="center")

    for p in profiles:
        active_mark = "[green]✓[/green]" if p["active"] else ""
        table.add_row(p["folder"], p["name"], p["email"], active_mark)

    console.print(table)
    console.print("\n[dim]Set [bold]chrome.google_accounts[/bold] in config.yaml to filter by email, "
                  "or [bold]chrome.profiles[/bold] to filter by folder name.[/dim]")


def cmd_scan(args: argparse.Namespace) -> None:
    """Scan existing blog posts and display their metadata."""
    from dataclasses import asdict

    config = load_config(args.config)
    posts = scan_existing_posts(config, limit=args.limit)

    if args.json:
        print(json.dumps([asdict(p) for p in posts], ensure_ascii=False, indent=2))
        return

    if not posts:
        console.print("[yellow]No existing posts found.[/yellow]")
        return

    table = Table(title="Existing Blog Posts (newest first)")
    table.add_column("Date", width=12)
    table.add_column("Title", max_width=50)
    table.add_column("Tags", max_width=40)
    table.add_column("File", max_width=30, style="dim")

    for post in posts:
        table.add_row(
            post.date,
            post.title[:50],
            ", ".join(post.tags[:5]),
            post.filename,
        )

    console.print(table)
    console.print(f"\n[green]Total: {len(posts)} posts[/green]")


def cmd_import_ai(args: argparse.Namespace) -> None:
    """Parse an AI chat export file (ChatGPT/Claude/Gemini) and output as JSON."""
    results = parse_ai_export(args.path, days=args.days)

    if not results:
        console.print("[yellow]No conversations found in export file.[/yellow]")
        return

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    table = Table(title=f"AI Chat Export — {Path(args.path).name}")
    table.add_column("Service", width=12)
    table.add_column("Source", width=8)
    table.add_column("Title", max_width=55)
    table.add_column("Preview", max_width=40, style="dim")

    for item in results:
        meta = item.get("metadata") or {}
        preview = item["text_content"][:80].replace("\n", " ")
        table.add_row(
            meta.get("service", "?"),
            meta.get("source", "offline"),
            item["title"][:55],
            preview,
        )

    console.print(table)
    console.print(f"\n[green]{len(results)} conversation(s) found[/green]")
    console.print("[dim]Run with --json to get output compatible with the skill pipeline.[/dim]")


def cmd_publish(args: argparse.Namespace) -> None:
    """Publish a markdown file to the blog repo."""
    config = load_config(args.config)
    file_path = Path(args.file)

    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        sys.exit(1)

    content = file_path.read_text(encoding="utf-8")
    filename = args.filename or post_filename()

    action = "Updating" if args.update else "Publishing"
    console.print(f"[blue]{action} {filename} in blog repo...[/blue]")
    pull_latest(config)
    post_path = publish_post(content, filename, config, push=args.push, update=args.update)
    console.print(f"[green]{'Updated' if args.update else 'Published'} to {post_path}[/green]")

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

    # profiles
    p_profiles = subparsers.add_parser("profiles", help="List Chrome profiles and their Google accounts")
    p_profiles.add_argument("--json", action="store_true", help="Output as JSON")
    p_profiles.set_defaults(func=cmd_profiles)

    # scan
    p_scan = subparsers.add_parser("scan", help="Scan existing blog posts and show their metadata")
    p_scan.add_argument("--limit", type=int, default=30, help="Max number of posts to return (default: 30)")
    p_scan.add_argument("--json", action="store_true", help="Output as JSON")
    p_scan.set_defaults(func=cmd_scan)

    # import-ai
    p_import = subparsers.add_parser("import-ai", help="Parse AI chat export files (ChatGPT/Claude/Gemini)")
    p_import.add_argument("path", help="Path to export file or directory")
    p_import.add_argument("--days", type=int, default=None, help="Only include conversations from the last N days")
    p_import.add_argument("--json", action="store_true", help="Output as JSON (compatible with fetch output)")
    p_import.set_defaults(func=cmd_import_ai)

    # publish
    p_pub = subparsers.add_parser("publish", help="Publish a markdown file to the blog repo")
    p_pub.add_argument("file", help="Path to the markdown file to publish")
    p_pub.add_argument("--filename", help="Override output filename (default: YYYY-MM-DD-tech-log.md)")
    p_pub.add_argument("--push", action="store_true", help="Push to remote after committing")
    p_pub.add_argument("--update", action="store_true", help="Update an existing post (changes commit message)")
    p_pub.set_defaults(func=cmd_publish)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
