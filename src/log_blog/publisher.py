from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Config


def ensure_repo(config: Config) -> Path:
    """Ensure the blog repo exists locally. Clone if missing."""
    repo_path = config.blog.repo_path_resolved
    if not repo_path.exists():
        print(f"Cloning blog repo to {repo_path}...")
        subprocess.run(
            ["git", "clone", config.blog.repo_url, str(repo_path)],
            check=True,
        )
    return repo_path


def pull_latest(config: Config) -> None:
    """Pull latest changes from the blog repo."""
    repo_path = ensure_repo(config)
    subprocess.run(["git", "pull"], cwd=repo_path, check=True)


def publish_post(content: str, filename: str, config: Config, push: bool = False) -> Path:
    """Write a post file to the blog repo, commit, and optionally push.

    Args:
        content: The markdown content of the post.
        filename: The filename (e.g., "2026-02-19-tech-log.md").
        config: Application config.
        push: Whether to git push after committing.

    Returns:
        Path to the written file.
    """
    repo_path = ensure_repo(config)
    content_dir = config.blog.content_path
    content_dir.mkdir(parents=True, exist_ok=True)

    post_path = content_dir / filename
    post_path.write_text(content, encoding="utf-8")
    print(f"Wrote post to {post_path}")

    # Git add and commit
    subprocess.run(["git", "add", str(post_path)], cwd=repo_path, check=True)

    commit_msg = f"Add tech log: {filename}"
    subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=repo_path,
        check=True,
    )
    print(f"Committed: {commit_msg}")

    if push:
        subprocess.run(["git", "push"], cwd=repo_path, check=True)
        print("Pushed to remote.")

    return post_path
