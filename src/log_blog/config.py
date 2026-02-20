from __future__ import annotations

import dataclasses
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Type, TypeVar

import yaml

_ENV_RE = re.compile(r"\$\{([^}]+)\}")

_T = TypeVar("_T")


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR_NAME} patterns with the corresponding environment variable value."""
    return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)


def _filter_fields(cls: Type[_T], data: dict) -> dict:
    """Return only the keys in `data` that are valid fields for the dataclass `cls`.

    Unknown keys are silently dropped, avoiding TypeError on unexpected YAML entries.
    """
    known = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
    return {k: v for k, v in data.items() if k in known}


@dataclass
class ChromeConfig:
    profiles: list[str] = field(default_factory=lambda: ["Default"])
    history_db_base: str = "~/Library/Application Support/Google/Chrome"
    google_accounts: list[str] = field(default_factory=list)
    # If google_accounts is set, it overrides profiles — history is read only
    # from Chrome profiles whose signed-in Google account email matches.
    # Run 'uv run log-blog profiles' to see all profiles and their emails.

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
class GitHubAccountConfig:
    profile: str = ""  # gh CLI username; used with: gh auth switch --user {profile}


@dataclass
class BitbucketAccountConfig:
    username: str = ""
    token: str = ""  # Bitbucket App Password; supports ${ENV_VAR} syntax


@dataclass
class AiChatServiceConfig:
    auth_profile: str = ""  # Google account email whose Chrome cookies are used.
    enabled: bool = True    # Set to false to skip this service entirely.


@dataclass
class AiChatConfig:
    perplexity: AiChatServiceConfig = field(default_factory=AiChatServiceConfig)
    chatgpt: AiChatServiceConfig = field(default_factory=AiChatServiceConfig)
    claude: AiChatServiceConfig = field(default_factory=AiChatServiceConfig)


@dataclass
class AccountsConfig:
    github: GitHubAccountConfig = field(default_factory=GitHubAccountConfig)
    bitbucket: BitbucketAccountConfig = field(default_factory=BitbucketAccountConfig)
    ai_chats: AiChatConfig = field(default_factory=AiChatConfig)


@dataclass
class Config:
    chrome: ChromeConfig = field(default_factory=ChromeConfig)
    time_range_hours: int = 24
    blog: BlogConfig = field(default_factory=BlogConfig)
    playwright: PlaywrightConfig = field(default_factory=PlaywrightConfig)
    accounts: AccountsConfig = field(default_factory=AccountsConfig)


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

    accounts_raw = data.get("accounts", {}) or {}
    github_data = dict(accounts_raw.get("github", {}) or {})
    bitbucket_data = dict(accounts_raw.get("bitbucket", {}) or {})
    ai_chats_raw = accounts_raw.get("ai_chats", {}) or {}

    # Resolve ${ENV_VAR} references in all credential string fields
    for field in ("token",):
        if field in bitbucket_data:
            bitbucket_data[field] = _resolve_env_vars(str(bitbucket_data[field]))
    for field in ("profile",):
        if field in github_data:
            github_data[field] = _resolve_env_vars(str(github_data[field]))

    def _ai_service(key: str) -> AiChatServiceConfig:
        svc = _filter_fields(AiChatServiceConfig, dict(ai_chats_raw.get(key, {}) or {}))
        if "auth_profile" in svc:
            svc["auth_profile"] = _resolve_env_vars(str(svc["auth_profile"]))
        return AiChatServiceConfig(**svc)

    return Config(
        chrome=ChromeConfig(**_filter_fields(ChromeConfig, chrome_data)),
        time_range_hours=data.get("time_range_hours", 24),
        blog=BlogConfig(**_filter_fields(BlogConfig, blog_data)),
        playwright=PlaywrightConfig(**_filter_fields(PlaywrightConfig, pw_data)),
        accounts=AccountsConfig(
            github=GitHubAccountConfig(**_filter_fields(GitHubAccountConfig, github_data)),
            bitbucket=BitbucketAccountConfig(**_filter_fields(BitbucketAccountConfig, bitbucket_data)),
            ai_chats=AiChatConfig(
                perplexity=_ai_service("perplexity"),
                chatgpt=_ai_service("chatgpt"),
                claude=_ai_service("claude"),
            ),
        ),
    )
