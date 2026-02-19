from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ChromeConfig:
    profiles: list[str] = field(default_factory=lambda: ["Default"])
    history_db_base: str = "~/Library/Application Support/Google/Chrome"

    @property
    def history_db_base_path(self) -> Path:
        return Path(self.history_db_base).expanduser()


@dataclass
class BlogConfig:
    repo_path: str = "~/Documents/github/ice-ice-bear.github.io"
    repo_url: str = "https://github.com/ice-ice-bear/ice-ice-bear.github.io.git"
    content_dir: str = "content/posts"
    language: str = "auto"

    @property
    def repo_path_resolved(self) -> Path:
        return Path(self.repo_path).expanduser()

    @property
    def content_path(self) -> Path:
        return self.repo_path_resolved / self.content_dir


@dataclass
class PlaywrightConfig:
    headless: bool = True
    timeout_ms: int = 15000
    max_concurrent: int = 5


@dataclass
class Config:
    chrome: ChromeConfig = field(default_factory=ChromeConfig)
    time_range_hours: int = 24
    blog: BlogConfig = field(default_factory=BlogConfig)
    playwright: PlaywrightConfig = field(default_factory=PlaywrightConfig)


def _find_config() -> Path | None:
    """Search for config.yaml in the project directory."""
    project_dir = Path(__file__).resolve().parent.parent.parent
    config_path = project_dir / "config.yaml"
    if config_path.exists():
        return config_path
    return None


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration from a YAML file. Falls back to defaults."""
    if path is None:
        found = _find_config()
        if found is None:
            return Config()
        path = found

    path = Path(path)
    if not path.exists():
        return Config()

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    chrome_data = data.get("chrome", {})
    blog_data = data.get("blog", {})
    pw_data = data.get("playwright", {})

    return Config(
        chrome=ChromeConfig(**chrome_data),
        time_range_hours=data.get("time_range_hours", 24),
        blog=BlogConfig(**blog_data),
        playwright=PlaywrightConfig(**pw_data),
    )
