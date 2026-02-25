from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config

# ---------------------------------------------------------------------------
# Brand/technology tags → Simple Icons slug
# CDN: https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg
# ---------------------------------------------------------------------------
SIMPLE_ICONS_MAP: dict[str, str] = {
    # Languages
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "rust": "rust",
    "go": "go",
    "java": "openjdk",
    "kotlin": "kotlin",
    "swift": "swift",
    "c": "c",
    "cpp": "cplusplus",
    "c++": "cplusplus",
    "csharp": "csharp",
    "ruby": "ruby",
    "php": "php",
    "dart": "dart",
    "lua": "lua",
    "r": "r",
    "scala": "scala",
    "elixir": "elixir",
    "haskell": "haskell",
    "zig": "zig",
    # Frontend
    "react": "react",
    "vue": "vuedotjs",
    "angular": "angular",
    "svelte": "svelte",
    "nextjs": "nextdotjs",
    "nuxt": "nuxtdotjs",
    "tailwindcss": "tailwindcss",
    "tailwind": "tailwindcss",
    "css": "css3",
    "html": "html5",
    "sass": "sass",
    "webpack": "webpack",
    "vite": "vite",
    # Backend / Frameworks
    "node": "nodedotjs",
    "nodejs": "nodedotjs",
    "fastapi": "fastapi",
    "flask": "flask",
    "django": "django",
    "express": "express",
    "spring": "spring",
    "rails": "rubyonrails",
    "laravel": "laravel",
    "nestjs": "nestjs",
    # DevOps / Infra
    "docker": "docker",
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    "terraform": "terraform",
    "ansible": "ansible",
    "nginx": "nginx",
    "apache": "apache",
    "jenkins": "jenkins",
    "github-actions": "githubactions",
    "gitlab": "gitlab",
    "circleci": "circleci",
    # Cloud
    "aws": "amazonwebservices",
    "gcp": "googlecloud",
    "azure": "microsoftazure",
    "vercel": "vercel",
    "netlify": "netlify",
    "cloudflare": "cloudflare",
    "heroku": "heroku",
    "supabase": "supabase",
    "firebase": "firebase",
    # Databases
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "mysql": "mysql",
    "mongodb": "mongodb",
    "redis": "redis",
    "sqlite": "sqlite",
    "elasticsearch": "elasticsearch",
    # AI / ML
    "openai": "openai",
    "gemini": "googlegemini",
    "claude": "anthropic",
    "anthropic": "anthropic",
    "tensorflow": "tensorflow",
    "pytorch": "pytorch",
    "huggingface": "huggingface",
    "langchain": "langchain",
    # Tools
    "git": "git",
    "github": "github",
    "bitbucket": "bitbucket",
    "playwright": "playwright",
    "selenium": "selenium",
    "hugo": "hugo",
    "jekyll": "jekyll",
    "gatsby": "gatsby",
    "astro": "astro",
    "grafana": "grafana",
    "prometheus": "prometheus",
    "linux": "linux",
    "ubuntu": "ubuntu",
    "macos": "macos",
    "vim": "vim",
    "neovim": "neovim",
    "vscode": "visualstudiocode",
    "figma": "figma",
    "npm": "npm",
    "yarn": "yarn",
    "pnpm": "pnpm",
    "homebrew": "homebrew",
    # Data / Analytics
    "pandas": "pandas",
    "jupyter": "jupyter",
    "apache-spark": "apachespark",
    "airflow": "apacheairflow",
    "kafka": "apachekafka",
    "dbt": "dbt",
    # APIs / Protocols
    "graphql": "graphql",
    "grpc": "grpc",
    "swagger": "swagger",
    "postman": "postman",
    # Messaging / Communication
    "slack": "slack",
    "discord": "discord",
    # Browsers
    "chrome": "googlechrome",
    # Cloud services
    "aws-ec2": "amazonec2",
    "github-pages": "githubpages",
    # AI tools
    "claude-code": "anthropic",
    "google-ai": "googlegemini",
    "mcp": "anthropic",
    # Databases (extras)
    "aiosqlite": "sqlite",
    # Observability
    "honeycomb": "honeycomb",
    # VS Code ecosystem
    "oauth": "openid",
    # Process management
    "pm2": "pm2",
}

# ---------------------------------------------------------------------------
# Generic concept tags → Tabler Icons name (outline style)
# CDN: https://cdn.jsdelivr.net/npm/@tabler/icons@latest/icons/outline/{name}.svg
# ---------------------------------------------------------------------------
TABLER_ICONS_MAP: dict[str, str] = {
    "blog": "pencil",
    "machine-learning": "cpu",
    "ml": "cpu",
    "ai": "sparkles",
    "deep-learning": "brain",
    "group-study": "users-group",
    "job-interview": "briefcase",
    "coding": "code",
    "tech-log": "notebook",
    "api": "api-app",
    "database": "database",
    "security": "shield-lock",
    "devops": "server",
    "tutorial": "book",
    "documentation": "file-text",
    "docs": "file-text",
    "testing": "test-pipe",
    "performance": "chart-line",
    "architecture": "building",
    "microservices": "topology-star-3",
    "open-source": "brand-open-source",
    "web": "world",
    "mobile": "device-mobile",
    "cli": "terminal-2",
    "automation": "robot",
    "data": "chart-bar",
    "cloud": "cloud",
    "container": "box",
    "monitoring": "activity",
    "logging": "list-details",
    "cicd": "refresh",
    "ci-cd": "refresh",
    "deployment": "rocket",
    "agile": "layout-kanban",
    "refactoring": "tool",
    "debugging": "bug",
    "configuration": "settings",
    "networking": "network",
    "authentication": "lock",
    "authorization": "key",
    "encryption": "lock-access",
    "llm": "message-chatbot",
    "chatbot": "message-chatbot",
    "prompt": "message-dots",
    "rag": "database-search",
    "embedding": "vector",
    "fine-tuning": "adjustments",
    "token": "coins",
    "cost": "currency-dollar",
    "image-generation": "photo-ai",
    "mermaid": "chart-dots-3",
    "diagram": "chart-dots-3",
    # Blog / content
    "blog-automation": "robot",
    "static-site-generator": "world-code",
    "hugo-themes": "palette",
    "hugo-theme-stack": "stack-2",
    # AI workflow
    "ai-coding": "code-dots",
    "vibe-coding": "sparkles",
    "archon": "topology-ring-3",
    # Hugo specific
    "papermod": "file-text",
    # VS Code extension dev
    "vscode-extension": "puzzle",
    "uri-handler": "link",
    "code-server": "code",
    "remote-tunnels": "route",
    # Bug / reliability
    "bug": "bug",
    "thinking": "brain",
    "production": "server-check",
    # Observability
    "observability": "eye",
    "slo": "target",
    "apm": "activity-heartbeat",
    "distributed-tracing": "vector-triangle",
    # Process management
    "process-management": "cpu",
    "ecosystem": "sitemap",
}

# Fallback SVG for tags that don't match any map — a simple tag outline
FALLBACK_TAG_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round">'
    '<path d="M7.859 6h-2.834a2.025 2.025 0 0 0 -2.025 2.025v2.834c0 .537 .213 1.052 '
    '.593 1.432l6.116 6.116a2.025 2.025 0 0 0 2.864 0l2.834 -2.834a2.025 2.025 0 0 0 '
    '0 -2.864l-6.116 -6.116a2.025 2.025 0 0 0 -1.432 -.593z" />'
    '<path d="M10 9v.01" />'
    '</svg>'
)

_UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"
_SIMPLE_ICONS_CDN = "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg"
_TABLER_ICONS_CDN = "https://cdn.jsdelivr.net/npm/@tabler/icons@latest/icons/outline/{name}.svg"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ImageResult:
    path: Path | None
    relative_url: str
    success: bool
    error: str | None = None


@dataclass
class TaxonomyResult:
    tag_slug: str
    svg_path: Path | None = None
    index_path: Path | None = None
    already_existed: bool = False
    success: bool = True
    error: str | None = None


@dataclass
class ImageAssets:
    cover: ImageResult | None = None
    tag_results: list[TaxonomyResult] = field(default_factory=list)
    category_results: list[TaxonomyResult] = field(default_factory=list)

    @property
    def all_new_paths(self) -> list[Path]:
        """Return all newly created file paths for git add."""
        paths: list[Path] = []
        if self.cover and self.cover.success and self.cover.path:
            paths.append(self.cover.path)
        for r in self.tag_results + self.category_results:
            if not r.already_existed and r.success:
                if r.svg_path:
                    paths.append(r.svg_path)
                if r.index_path:
                    paths.append(r.index_path)
        return paths


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path, *, headers: dict[str, str] | None = None) -> None:
    """Download a URL to a local file path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=15) as resp:
        dest.write_bytes(resp.read())


def _slug_to_title(slug: str) -> str:
    """Convert a kebab-case slug to Title Case.  Keeps non-ASCII chars as-is."""
    return slug.replace("-", " ").title()


# ---------------------------------------------------------------------------
# Cover image
# ---------------------------------------------------------------------------

def fetch_cover_image(query: str, post_slug: str, config: Config) -> ImageResult:
    """Download a cover image for a blog post from Unsplash.

    Skips if the cover image already exists on disk (safe for --update).
    """
    repo = config.blog.repo_path_resolved
    rel_url = f"/images/posts/{post_slug}/cover.jpg"
    dest = repo / "static" / "images" / "posts" / post_slug / "cover.jpg"

    if dest.exists():
        return ImageResult(path=dest, relative_url=rel_url, success=True)

    api_key = config.images.unsplash_api_key
    if not api_key:
        return ImageResult(
            path=None,
            relative_url="",
            success=False,
            error="No Unsplash API key configured (images.unsplash_api_key)",
        )

    try:
        params = urllib.parse.urlencode({
            "query": query,
            "orientation": "landscape",
            "per_page": "1",
        })
        url = f"{_UNSPLASH_SEARCH_URL}?{params}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Client-ID {api_key}",
            "Accept-Version": "v1",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        results = data.get("results", [])
        if not results:
            return ImageResult(
                path=None, relative_url="", success=False,
                error=f"No Unsplash results for query: {query}",
            )

        image_url = results[0]["urls"]["regular"]
        _download(image_url, dest)
        return ImageResult(path=dest, relative_url=rel_url, success=True)

    except Exception as e:
        return ImageResult(
            path=None, relative_url="", success=False,
            error=f"Unsplash download failed: {e}",
        )


# ---------------------------------------------------------------------------
# Taxonomy icons
# ---------------------------------------------------------------------------

def _download_icon_svg(tag_slug: str) -> str | None:
    """Try to download an SVG for the given tag from Simple Icons or Tabler Icons.

    Returns the SVG content as a string, or None if all sources failed.
    """
    # Try Simple Icons first (brand/tech)
    si_slug = SIMPLE_ICONS_MAP.get(tag_slug)
    if si_slug:
        url = _SIMPLE_ICONS_CDN.format(slug=si_slug)
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8")
        except Exception:
            pass  # Fall through to Tabler

    # Try Tabler Icons (generic concepts)
    tabler_name = TABLER_ICONS_MAP.get(tag_slug)
    if tabler_name:
        url = _TABLER_ICONS_CDN.format(name=tabler_name)
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8")
        except Exception:
            pass  # Fall through to fallback

    return None


def _ensure_taxonomy_icon(
    slug: str, kind: str, config: Config,
) -> TaxonomyResult:
    """Ensure a taxonomy entry (tag or category) has an SVG icon and _index.md.

    Args:
        slug: Kebab-case slug (e.g., "python", "tech-log").
        kind: Either "tag" or "cat".
        config: Application config.
    """
    prefix = f"{kind}-"
    content_subdir = "tags" if kind == "tag" else "categories"

    repo = config.blog.repo_path_resolved
    svg_path = repo / "static" / "images" / "taxonomy" / f"{prefix}{slug}.svg"
    index_dir = repo / "content" / content_subdir / slug
    index_path = index_dir / "_index.md"

    svg_exists = svg_path.exists()
    index_exists = index_path.exists()

    if svg_exists and index_exists:
        return TaxonomyResult(tag_slug=slug, already_existed=True)

    result = TaxonomyResult(tag_slug=slug)

    if not svg_exists:
        svg_content = _download_icon_svg(slug)
        if svg_content is None:
            svg_content = FALLBACK_TAG_SVG
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.write_text(svg_content, encoding="utf-8")
        result.svg_path = svg_path

    if not index_exists:
        title = _slug_to_title(slug)
        index_content = f'---\ntitle: "{title}"\nimage: "/images/taxonomy/{prefix}{slug}.svg"\n---\n'
        index_dir.mkdir(parents=True, exist_ok=True)
        index_path.write_text(index_content, encoding="utf-8")
        result.index_path = index_path

    return result


def ensure_tag_icon(tag_slug: str, config: Config) -> TaxonomyResult:
    """Ensure a tag has an SVG icon and _index.md in the blog repo."""
    return _ensure_taxonomy_icon(tag_slug, "tag", config)


def ensure_category_icon(category_slug: str, config: Config) -> TaxonomyResult:
    """Ensure a category has an SVG icon and _index.md in the blog repo."""
    return _ensure_taxonomy_icon(category_slug, "cat", config)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def prepare_images(
    post_slug: str,
    tags: list[str],
    categories: list[str],
    cover_query: str,
    config: Config,
) -> ImageAssets:
    """Top-level: download cover image + ensure all taxonomy icons.

    Called during the publish step after tags/categories are finalized.
    """
    assets = ImageAssets()

    # Cover image
    if config.images.cover_enabled and cover_query:
        assets.cover = fetch_cover_image(cover_query, post_slug, config)
        if assets.cover.success:
            print(f"Cover image ready: {assets.cover.relative_url}", file=sys.stderr)
        elif assets.cover.error:
            print(f"Cover image skipped: {assets.cover.error}", file=sys.stderr)

    # Tag icons
    if config.images.taxonomy_enabled:
        for tag in tags:
            try:
                result = ensure_tag_icon(tag, config)
                assets.tag_results.append(result)
                if result.already_existed:
                    pass  # silent
                elif result.success:
                    print(f"Tag icon ready: tag-{tag}.svg", file=sys.stderr)
            except Exception as e:
                assets.tag_results.append(
                    TaxonomyResult(tag_slug=tag, success=False, error=str(e))
                )

    # Category icons
    if config.images.taxonomy_enabled:
        for cat in categories:
            try:
                result = ensure_category_icon(cat, config)
                assets.category_results.append(result)
                if result.already_existed:
                    pass
                elif result.success:
                    print(f"Category icon ready: cat-{cat}.svg", file=sys.stderr)
            except Exception as e:
                assets.category_results.append(
                    TaxonomyResult(tag_slug=cat, success=False, error=str(e))
                )

    return assets
