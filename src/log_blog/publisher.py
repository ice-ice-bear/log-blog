from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import Config


def _run_git(*args: str, cwd: Path | None = None) -> None:
    """Run a git command, converting failures into user-friendly messages."""
    try:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        cmd_str = " ".join(["git", *args])
        print(f"Error running '{cmd_str}':", file=sys.stderr)
        if e.stderr:
            print(f"  {e.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: 'git' is not installed or not on PATH.", file=sys.stderr)
        sys.exit(1)


def ensure_repo(config: Config) -> Path:
    """Ensure the blog repo exists locally. Clone if missing."""
    if not config.blog.repo_path:
        print("Error: blog.repo_path is not configured. Set it in config.yaml.", file=sys.stderr)
        sys.exit(1)
    repo_path = config.blog.repo_path_resolved
    if not repo_path.exists():
        if not config.blog.repo_url:
            print(
                f"Error: blog repo not found at {repo_path} and blog.repo_url is not configured for cloning.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Cloning blog repo to {repo_path}...")
        _run_git("clone", config.blog.repo_url, str(repo_path))
    return repo_path


def pull_latest(config: Config) -> None:
    """Pull latest changes from the blog repo."""
    repo_path = ensure_repo(config)
    _run_git("pull", cwd=repo_path)


def publish_post(
    content: str,
    filename: str,
    config: Config,
    push: bool = False,
    update: bool = False,
    extra_paths: list[Path] | None = None,
) -> Path:
    """Write a post file to the blog repo, commit, and optionally push.

    Args:
        content: The markdown content of the post.
        filename: The filename (e.g., "2026-02-19-tech-log.md").
        config: Application config.
        push: Whether to git push after committing.
        update: Whether this is an update to an existing post (changes commit message).
        extra_paths: Additional files to git add (cover images, taxonomy icons, _index.md).

    Returns:
        Path to the written file.
    """
    repo_path = ensure_repo(config)
    content_dir = config.blog.content_path
    content_dir.mkdir(parents=True, exist_ok=True)

    post_path = content_dir / filename

    if update and not post_path.exists():
        print(
            f"Warning: --update specified but '{filename}' does not exist in the blog repo; "
            "creating a new file instead.",
            file=sys.stderr,
        )

    post_path.write_text(content, encoding="utf-8")
    print(f"Wrote post to {post_path}")

    # Git add post and any extra files (images, taxonomy icons)
    _run_git("add", str(post_path), cwd=repo_path)
    if extra_paths:
        for extra in extra_paths:
            _run_git("add", str(extra), cwd=repo_path)

    verb = "Update" if update else "Add"
    commit_msg = f"{verb} tech log: {filename}"
    _run_git("commit", "-m", commit_msg, cwd=repo_path)
    print(f"Committed: {commit_msg}")

    if push:
        _run_git("push", cwd=repo_path)
        print("Pushed to remote.")

    return post_path
