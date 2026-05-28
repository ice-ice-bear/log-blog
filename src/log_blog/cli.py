from __future__ import annotations

import argparse
import json
import shutil
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


def _inject_frontmatter_field(content: str, key: str, value: str, *, overwrite: bool = False) -> str:
    """Insert or update a YAML field in existing frontmatter.

    When *overwrite* is True, replaces an existing value for *key*.
    Otherwise skips if the key is already present (legacy behaviour).
    """
    if not content.startswith("---"):
        return content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return content
    fm = parts[1]
    lines = fm.rstrip("\n").split("\n")

    # Check if key already exists
    existing_idx = None
    for i, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            existing_idx = i
            break

    if existing_idx is not None:
        if overwrite:
            lines[existing_idx] = f'{key}: "{value}"'
        else:
            return content
    else:
        # Insert after 'date:' line to keep image near the top
        insert_idx = len(lines)
        for i, line in enumerate(lines):
            if line.startswith("date:"):
                insert_idx = i + 1
                break
        lines.insert(insert_idx, f'{key}: "{value}"')

    return "---" + "\n".join(lines) + "\n---" + parts[2]


def _parse_frontmatter_tags(content: str) -> tuple[list[str], list[str]]:
    """Extract tags and categories from YAML frontmatter.

    Returns (tags, categories) lists. Handles both inline `[a, b]`
    and multi-line `- a` YAML list formats.
    """
    if not content.startswith("---"):
        return [], []
    parts = content.split("---", 2)
    if len(parts) < 3:
        return [], []
    fm_lines = parts[1].strip().splitlines()

    def _parse_list(lines: list[str], start: int) -> list[str]:
        """Parse a YAML list value starting at *start* index."""
        # Inline: tags: ["a", "b"] or tags: [a, b]
        value_part = lines[start].split(":", 1)[1].strip()
        if value_part.startswith("["):
            raw = value_part.strip("[]")
            return [v.strip().strip("\"'") for v in raw.split(",") if v.strip().strip("\"'")]
        # Multi-line:
        #   tags:
        #     - a
        #     - b
        items: list[str] = []
        for line in lines[start + 1:]:
            stripped = line.strip()
            if stripped.startswith("- "):
                items.append(stripped[2:].strip().strip("\"'"))
            elif stripped == "" or not line[0].isspace():
                break
        return items

    tags: list[str] = []
    categories: list[str] = []
    for i, line in enumerate(fm_lines):
        if line.startswith("tags:"):
            tags = _parse_list(fm_lines, i)
        elif line.startswith("categories:"):
            categories = _parse_list(fm_lines, i)
    return tags, categories


def cmd_extract(args: argparse.Namespace) -> None:
    """Extract and display browsing history."""
    from .run_state import hours_since_last_run, save_last_run

    config = load_config(args.config)
    if args.hours:
        config.time_range_hours = args.hours
    elif args.since_last_run:
        h = hours_since_last_run()
        if h is not None:
            config.time_range_hours = h

    entries = read_history(config)

    if args.json:
        from .url_classifier import classify_url, UrlType

        data = []
        for e in entries:
            url_type = classify_url(e.url)
            if url_type == UrlType.AI_LANDING and not args.include_noise:
                continue
            data.append({
                "url": e.url,
                "title": e.title,
                "visit_count": e.visit_count,
                "last_visit_time": e.last_visit_iso,
                "url_type": url_type.value,
            })
        print(json.dumps(data, ensure_ascii=False, indent=2))
        save_last_run()
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
    save_last_run()


def cmd_fetch(args: argparse.Namespace) -> None:
    """Fetch content from URLs."""
    config = load_config(args.config)
    urls = args.urls

    deep_urls = set(urls) if args.deep else None

    if not args.json:
        if deep_urls:
            console.print(f"[blue]Deep-fetching {len(urls)} page(s) via Firecrawl...[/blue]")
        else:
            console.print(f"[blue]Fetching {len(urls)} page(s)...[/blue]")
    results = fetch_pages(urls, config, deep_urls=deep_urls)

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


def _resolve_cdp_profile(config, chrome_data: Path) -> str | None:
    """Find the Chrome profile folder that matches the most-used auth_profile email.

    Reads Chrome's Local State to map Google account emails → profile folder names,
    then picks the profile whose email appears most often in ai_chats config.
    """
    # Collect all enabled auth_profile emails
    ai = config.accounts.ai_chats
    emails: list[str] = []
    for svc in (ai.perplexity, ai.chatgpt, ai.claude, ai.gemini):
        if svc.enabled and svc.auth_profile:
            emails.append(svc.auth_profile.lower())

    if not emails:
        return None

    # Find the most common email
    from collections import Counter
    target_email = Counter(emails).most_common(1)[0][0]

    # Map email → Chrome profile folder via Local State
    local_state_path = chrome_data / "Local State"
    if not local_state_path.exists():
        return None

    try:
        import json as _json
        state = _json.loads(local_state_path.read_text(encoding="utf-8"))
        info_cache = state.get("profile", {}).get("info_cache", {})
        for folder, info in info_cache.items():
            if info.get("user_name", "").lower() == target_email:
                return folder
    except Exception:
        pass

    return None


def _find_chrome_binary() -> str:
    """Find the Chrome binary path, preferring PATH lookup with macOS fallback."""
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    macos_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(macos_path).exists():
        return macos_path
    return "google-chrome"


def cmd_chrome_cdp(args: argparse.Namespace) -> None:
    """Launch Chrome with CDP remote debugging using a profile copy."""
    import subprocess
    import tempfile

    config = load_config(args.config)
    port = args.port or config.playwright.cdp_port
    chrome_data = Path(config.chrome.history_db_base).expanduser()

    # Resolve profile: CLI flag → auto-detect from ai_chats auth_profile → "Default"
    profile_dir = args.profile
    if not profile_dir:
        profile_dir = _resolve_cdp_profile(config, chrome_data)
    if not profile_dir:
        profile_dir = "Default"

    # Create a temp directory with essential profile files
    cdp_dir = Path(tempfile.mkdtemp(prefix="chrome-cdp-"))
    target_profile = cdp_dir / profile_dir
    target_profile.mkdir(parents=True, exist_ok=True)

    # Copy essential files for auth sessions
    source_profile = chrome_data / profile_dir
    essential_files = ["Cookies", "Login Data", "Preferences", "Secure Preferences", "Web Data"]
    for fname in essential_files:
        src = source_profile / fname
        if src.exists():
            shutil.copy2(src, target_profile / fname)

    # Also copy Network/Cookies if present
    net_cookies = source_profile / "Network" / "Cookies"
    if net_cookies.exists():
        (target_profile / "Network").mkdir(exist_ok=True)
        shutil.copy2(net_cookies, target_profile / "Network" / "Cookies")

    # Copy parent-level Local State
    local_state = chrome_data / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, cdp_dir / "Local State")

    console.print(f"[blue]Launching Chrome with CDP on port {port}...[/blue]")
    console.print(f"[dim]Profile: {profile_dir} → {cdp_dir}[/dim]")

    chrome_bin = _find_chrome_binary()
    proc = subprocess.Popen(
        [chrome_bin, f"--remote-debugging-port={port}",
         f"--user-data-dir={cdp_dir}", f"--profile-directory={profile_dir}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )

    # Wait briefly and check if CDP is listening
    import time
    time.sleep(5)
    if proc.poll() is not None:
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        console.print(f"[red]Chrome exited unexpectedly.[/red]\n{stderr}")
        sys.exit(1)

    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=5)
        data = json.loads(resp.read())
        console.print(f"[green]CDP ready — Chrome {data.get('Browser', '?')}[/green]")
        console.print(f"[dim]ws: {data.get('webSocketDebuggerUrl', '?')}[/dim]")
    except Exception:
        console.print("[yellow]Chrome launched but CDP endpoint not responding yet. It may need a few more seconds.[/yellow]")

    console.print(f"\n[green]Chrome is running with CDP on port {port}.[/green]")
    console.print("[dim]Run 'uv run log-blog fetch ...' in another terminal to fetch AI chat content.[/dim]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        console.print("\n[yellow]Chrome stopped.[/yellow]")
    finally:
        shutil.rmtree(cdp_dir, ignore_errors=True)


def _check_series_updates(config) -> list[dict]:
    """Check known series repos for new commits since last_commit.

    Cross-references scan results (existing blog posts with series + last_commit)
    against actual git repos to find projects with new commits, regardless of
    session time window.

    Returns list of dicts: {project_name, repo_path, repo_type, last_commit,
                            new_commit_count, series_num}
    """
    from .post_advisor import scan_existing_posts
    from .session_parser import extract_commits_since_sha, _detect_repo_type
    from pathlib import Path

    posts = scan_existing_posts(config, limit=50)

    # Group by series, keep highest series_num per series
    series_map: dict = {}
    for post in posts:
        if not post.series or not post.last_commit:
            continue
        existing = series_map.get(post.series)
        if existing is None or (post.series_num or 0) > (existing.series_num or 0):
            series_map[post.series] = post

    # Aliased series → real repo directory name (so we can find the repo on disk
    # when the published series name doesn't match the directory).
    reverse_aliases = config.sessions.reverse_series_aliases

    # Check each series repo for new commits
    updates = []
    for series_name, post in series_map.items():
        # Search order: real repo directory name (if aliased), then the series name itself
        search_names = []
        if series_name in reverse_aliases:
            search_names.append(reverse_aliases[series_name])
        search_names.append(series_name)

        # Find the repo path — check common locations with case-insensitive match
        repo_path = None
        for candidate_name in search_names:
            for base in [
                Path.home() / "Documents" / "github",
                Path.home() / "Documents" / "bitbucket",
            ]:
                if not base.is_dir():
                    continue
                # Exact match first
                candidate = base / candidate_name
                if candidate.is_dir() and (candidate / ".git").is_dir():
                    repo_path = candidate
                    break
                # Case-insensitive fallback
                try:
                    for child in base.iterdir():
                        if child.name.lower() == candidate_name.lower() and child.is_dir():
                            if (child / ".git").is_dir():
                                repo_path = child
                                break
                except PermissionError:
                    continue
                if repo_path:
                    break
            if repo_path:
                break

        if repo_path is None:
            continue

        new_commits = extract_commits_since_sha(repo_path, post.last_commit)
        if new_commits:
            repo_type = _detect_repo_type(repo_path)
            updates.append({
                "project_name": series_name,
                "repo_path": str(repo_path),
                "repo_type": repo_type,
                "last_commit": post.last_commit,
                "new_commit_count": len(new_commits),
                "series_num": (post.series_num or 0) + 1,
                "prev_filename": post.filename,
            })

    return updates


def cmd_sessions(args: argparse.Namespace) -> None:
    """Extract Claude Code session data for dev log blog posts."""
    from dataclasses import asdict
    from .session_parser import discover_projects, build_project_summary

    config = load_config(args.config)
    if args.hours:
        hours = args.hours
    elif args.since_last_run:
        from .run_state import hours_since_last_run
        h = hours_since_last_run()
        hours = h if h is not None else config.time_range_hours
    else:
        hours = config.time_range_hours
    claude_dir = config.sessions.claude_dir_path

    min_sessions = 1 if args.all else 2
    projects = discover_projects(
        hours, claude_dir,
        include_short=args.include_short,
        min_sessions=min_sessions,
        series_aliases=config.sessions.series_aliases,
    )

    # Also check series repos for new commits since last_commit
    series_updates = _check_series_updates(config)
    discovered_names = {p.name for p in projects}

    # Add series projects not already discovered via sessions
    from .session_parser import ProjectInfo
    from pathlib import Path
    for update in series_updates:
        if update["project_name"] not in discovered_names:
            repo_path = Path(update["repo_path"])
            projects.append(ProjectInfo(
                name=update["project_name"],
                session_dir=Path(""),  # no session dir
                repo_path=repo_path,
                repo_type=update["repo_type"],
                session_files=[],  # no sessions — commit-only detection
            ))

    if not projects:
        console.print("[yellow]No Claude Code sessions or series updates found.[/yellow]")
        return

    if args.project:
        projects = [p for p in projects if p.name == args.project]
        if not projects:
            console.print(f"[red]Project '{args.project}' not found.[/red]")
            return

    # Build a lookup for series updates
    series_update_map = {u["project_name"]: u for u in series_updates}

    if args.list:
        if args.json:
            data = []
            for p in projects:
                summary = build_project_summary(p, hours, include_short=args.include_short)
                entry = {
                    "project_name": summary.project_name,
                    "repo_path": summary.repo_path,
                    "repo_type": summary.repo_type,
                    "session_count": summary.session_count,
                    "commit_count": len(summary.git_commits),
                    "total_duration_minutes": summary.total_duration_minutes,
                }
                # Enrich with series info if available
                su = series_update_map.get(summary.project_name)
                if su:
                    entry["series_update"] = {
                        "last_commit": su["last_commit"],
                        "new_commit_count": su["new_commit_count"],
                        "next_series_num": su["series_num"],
                        "prev_filename": su["prev_filename"],
                    }
                data.append(entry)
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            table = Table(title=f"Claude Code Sessions & Series Updates")
            table.add_column("Project", min_width=15)
            table.add_column("Sessions", justify="right", width=10)
            table.add_column("Commits", justify="right", width=10)
            table.add_column("Duration", justify="right", width=12)
            table.add_column("Type", width=10)
            table.add_column("Series", width=20)

            for p in projects:
                summary = build_project_summary(p, hours, include_short=args.include_short)
                h, m = divmod(summary.total_duration_minutes, 60)
                duration = f"{h}h {m:02d}m" if h else f"{m}m"

                su = series_update_map.get(summary.project_name)
                if su:
                    series_info = f"#{su['series_num']} (+{su['new_commit_count']} commits)"
                else:
                    series_info = "new"

                # For commit-only projects (no sessions), show commit count from series
                commit_count = len(summary.git_commits)
                if commit_count == 0 and su:
                    commit_count = su["new_commit_count"]

                table.add_row(
                    summary.project_name,
                    str(summary.session_count),
                    str(commit_count),
                    duration,
                    summary.repo_type,
                    series_info,
                )

            console.print(table)
        return

    # Full detail mode
    summaries = []
    for p in projects:
        summary = build_project_summary(p, hours, include_short=args.include_short)

        # For series projects with no time-window commits, use SHA-based commits
        su = series_update_map.get(summary.project_name)
        if not summary.git_commits and su and p.repo_path:
            from .session_parser import extract_commits_since_sha
            summary.git_commits = extract_commits_since_sha(
                p.repo_path, su["last_commit"]
            )
            for c in summary.git_commits:
                summary.files_changed = sorted(
                    set(summary.files_changed) | set(c.files)
                )

        summaries.append(summary)

    if args.json:
        data = [asdict(s) for s in summaries]
        # Enrich with series info
        for i, summary in enumerate(summaries):
            su = series_update_map.get(summary.project_name)
            if su:
                data[i]["series_update"] = {
                    "last_commit": su["last_commit"],
                    "new_commit_count": su["new_commit_count"],
                    "next_series_num": su["series_num"],
                    "prev_filename": su["prev_filename"],
                }
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    for summary in summaries:
        console.print(f"\n[bold blue]{summary.project_name}[/bold blue] ({summary.repo_type})")
        console.print(f"  Sessions: {summary.session_count} | Commits: {len(summary.git_commits)} | Duration: {summary.total_duration_minutes}m")
        console.print(f"  Repo: {summary.repo_path}")

        if summary.git_commits:
            console.print("  [green]Commits:[/green]")
            for c in summary.git_commits[:10]:
                console.print(f"    {c.sha} {c.message} (+{c.insertions}/-{c.deletions})")

        if summary.files_changed:
            console.print(f"  [dim]Files changed: {', '.join(summary.files_changed[:10])}[/dim]")


def cmd_publish(args: argparse.Namespace) -> None:
    """Publish a markdown file to the blog repo."""
    from .image_handler import prepare_images

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

    # Prepare images (cover + taxonomy icons) unless --no-images
    extra_paths = None
    if not args.no_images:
        post_slug = filename.removesuffix(".md")
        # Parse tags/categories from frontmatter, merge with CLI --tags
        fm_tags, fm_categories = _parse_frontmatter_tags(content)
        cli_tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        tags = list(dict.fromkeys(fm_tags + cli_tags))  # dedupe, preserve order
        categories = fm_categories or ["tech-log"]
        cover_title = args.cover_title or ""

        if tags or categories or cover_title:
            console.print("[blue]Preparing images...[/blue]")
            assets = prepare_images(post_slug, cover_title, tags, categories, config, language=args.language)
            extra_paths = assets.all_new_paths
            if extra_paths:
                console.print(f"[green]{len(extra_paths)} image file(s) ready[/green]")

            # Inject or fix image frontmatter to match the generated cover path
            if assets.cover and assets.cover.success and assets.cover.relative_url:
                content = _inject_frontmatter_field(content, "image", assets.cover.relative_url, overwrite=True)

    post_path = publish_post(
        content, filename, config,
        push=args.push, update=args.update, extra_paths=extra_paths,
        language=args.language,
    )
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
    p_extract.add_argument("--since-last-run", action="store_true",
                           help="Use time since last run instead of fixed hours")
    p_extract.add_argument("--json", action="store_true", help="Output as JSON")
    p_extract.add_argument("--include-noise", action="store_true", default=False,
                           help="Include AI landing/noise URLs in output")
    p_extract.set_defaults(func=cmd_extract)

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch page content from URLs")
    p_fetch.add_argument("urls", nargs="+", help="URLs to fetch")
    p_fetch.add_argument("--json", action="store_true", help="Output as JSON")
    p_fetch.add_argument("--deep", action="store_true",
                         help="Use Firecrawl to deep-crawl documentation sites (fetches sub-pages)")
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

    # chrome-cdp
    p_cdp = subparsers.add_parser("chrome-cdp", help="Launch Chrome with CDP remote debugging for authenticated AI chat fetching")
    p_cdp.add_argument("--port", type=int, help="CDP port (default: from config, usually 9222)")
    p_cdp.add_argument("--profile", help="Chrome profile folder name (default: 'Default')")
    p_cdp.set_defaults(func=cmd_chrome_cdp)

    # sessions
    p_sessions = subparsers.add_parser("sessions", help="Extract Claude Code session data for dev log blog posts")
    p_sessions.add_argument("--hours", type=int, help="Time window (default: from config, usually 24)")
    p_sessions.add_argument("--since-last-run", action="store_true",
                            help="Use time since last run instead of fixed hours")
    p_sessions.add_argument("--project", help="Filter to one project by name")
    p_sessions.add_argument("--all", action="store_true", help="Include projects with only 1 session")
    p_sessions.add_argument("--include-short", action="store_true", help="Include very short sessions (<2 min or <3 messages)")
    p_sessions.add_argument("--json", action="store_true", help="Output structured JSON")
    p_sessions.add_argument("--list", action="store_true", help="Quick overview: just project names and counts")
    p_sessions.set_defaults(func=cmd_sessions)

    # publish
    p_pub = subparsers.add_parser("publish", help="Publish a markdown file to the blog repo")
    p_pub.add_argument("file", help="Path to the markdown file to publish")
    p_pub.add_argument("--filename", help="Override output filename (default: YYYY-MM-DD-tech-log.md)")
    p_pub.add_argument("--push", action="store_true", help="Push to remote after committing")
    p_pub.add_argument("--update", action="store_true", help="Update an existing post (changes commit message)")
    p_pub.add_argument("--cover-title", help="Post title for cover image generation (rendered on the image)")
    p_pub.add_argument("--tags", help="Comma-separated tags for taxonomy icon ensuring (e.g., 'python,fastapi')")
    p_pub.add_argument("--no-images", action="store_true", help="Skip cover image and taxonomy icon handling")
    p_pub.add_argument("--language", help="Post language (e.g., 'ko', 'en'). Routes to the matching language_content_dirs entry. Defaults to blog.default_language.")
    p_pub.set_defaults(func=cmd_publish)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
