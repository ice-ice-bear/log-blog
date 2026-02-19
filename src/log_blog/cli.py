from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.table import Table

from .config import load_config
from .content_fetcher import fetch_pages
from .history_reader import read_history
from .post_generator import generate_post, post_filename
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

    for result in results:
        if result.success:
            console.print(f"\n[green]--- {result.title} ---[/green]")
            console.print(f"URL: {result.url}")
            # Print first 500 chars of content
            preview = result.text_content[:500]
            console.print(preview)
            if len(result.text_content) > 500:
                console.print(f"[dim]... ({len(result.text_content)} chars total)[/dim]")
        else:
            console.print(f"\n[red]FAILED: {result.url}[/red]")
            console.print(f"  Error: {result.error}")

    if args.json:
        data = [
            {
                "url": r.url,
                "title": r.title,
                "text_content": r.text_content,
                "success": r.success,
                "error": r.error,
            }
            for r in results
        ]
        print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_generate(args: argparse.Namespace) -> None:
    """Run the full pipeline: extract -> fetch -> generate -> publish."""
    config = load_config(args.config)
    if args.hours:
        config.time_range_hours = args.hours

    # Step 1: Extract history
    console.print("[blue]Step 1: Extracting browsing history...[/blue]")
    entries = read_history(config)
    if not entries:
        console.print("[yellow]No history entries found. Exiting.[/yellow]")
        return

    console.print(f"Found {len(entries)} entries")

    # Step 2: Output for Claude to classify (when used via skill)
    # In standalone mode, use all entries
    entry_dicts = [{"url": e.url, "title": e.title} for e in entries]

    # Step 3: Fetch content
    urls = [e.url for e in entries[:20]]  # Limit to top 20
    console.print(f"\n[blue]Step 2: Fetching content from {len(urls)} pages...[/blue]")
    contents = fetch_pages(urls, config)
    successful = [c for c in contents if c.success]
    console.print(f"Successfully fetched {len(successful)}/{len(urls)} pages")

    # Step 4: Generate post
    console.print("\n[blue]Step 3: Generating post...[/blue]")
    language = config.blog.language if config.blog.language != "auto" else "en"
    post_content = generate_post(
        entries=entry_dicts[:20],
        contents=contents,
        tags=["browsing-log"],
        language=language,
    )

    filename = post_filename()
    console.print(f"Generated post: {filename}")

    # Step 5: Publish
    if args.publish:
        console.print("\n[blue]Step 4: Publishing...[/blue]")
        pull_latest(config)
        post_path = publish_post(post_content, filename, config, push=args.push)
        console.print(f"[green]Published to {post_path}[/green]")
    else:
        # Just print the post
        console.print("\n[yellow]--- Generated Post (use --publish to save) ---[/yellow]\n")
        print(post_content)


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

    # generate
    p_gen = subparsers.add_parser("generate", help="Full pipeline: extract -> generate -> publish")
    p_gen.add_argument("--hours", type=int, help="Override time range (hours)")
    p_gen.add_argument("--publish", action="store_true", help="Save and commit the post")
    p_gen.add_argument("--push", action="store_true", help="Push after committing")
    p_gen.set_defaults(func=cmd_generate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
