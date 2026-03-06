from __future__ import annotations

import sys
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
    "ec2": "amazonec2",
    "ecs": "amazonecs",
    "github-pages": "githubpages",
    # AI tools
    "claude-code": "anthropic",
    "claude-desktop": "anthropic",
    "google-ai": "googlegemini",
    "gemini-3": "googlegemini",
    "mcp": "anthropic",
    "fastmcp": "anthropic",
    # Databases (extras)
    "aiosqlite": "sqlite",
    # Observability
    "honeycomb": "honeycomb",
    # VS Code ecosystem
    "oauth": "openid",
    # Process management
    "pm2": "pm2",
    # Code quality
    "sonarcloud": "sonarcloud",
    # API specs
    "open-api": "openapiinitiative",
    # Web standards
    "web-components": "webcomponentsdotorg",
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
    # Agentic / AI workflow
    "agentic-development": "robot",
    "code-execution": "terminal-2",
    "function-calling": "api-app",
    "structured-output": "list-tree",
    # Developer tools
    "developer-tools": "tools",
    "extension": "puzzle",
    "extensions": "puzzle",
    "marketplace": "building-store",
    "hooks": "webhook",
    # Cloud / IAM
    "iam": "shield-lock",
    "elasticache": "database",
    # Shell / system
    "shell": "terminal-2",
    # API / protocols
    "rest-api": "api-app",
    "websocket": "plug-connected",
    # Web frameworks
    "fast": "bolt",
    # Databases
    "valkey": "database",
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

def _slug_to_title(slug: str) -> str:
    """Convert a kebab-case slug to Title Case.  Keeps non-ASCII chars as-is."""
    return slug.replace("-", " ").title()


# ---------------------------------------------------------------------------
# Cover image — PIL/Pillow generation
# ---------------------------------------------------------------------------

# Tag → (gradient_start_rgb, gradient_end_rgb, accent_rgb)
TAG_COLOR_SCHEMES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]] = {
    # Cloud / AWS
    "aws": ((255, 153, 0), (204, 102, 0), (255, 210, 140)),
    "ecs": ((255, 153, 0), (204, 102, 0), (255, 210, 140)),
    "ec2": ((255, 153, 0), (204, 102, 0), (255, 210, 140)),
    "elasticache": ((255, 153, 0), (204, 102, 0), (255, 210, 140)),
    "iam": ((255, 153, 0), (204, 102, 0), (255, 210, 140)),
    "gcp": ((66, 133, 244), (52, 168, 83), (200, 230, 255)),
    "azure": ((0, 120, 212), (0, 78, 152), (140, 200, 255)),
    "cloud": ((30, 136, 229), (13, 71, 161), (144, 202, 249)),
    # AI / ML
    "ai": ((16, 185, 129), (5, 130, 90), (167, 243, 208)),
    "openai": ((16, 163, 127), (0, 110, 80), (180, 255, 220)),
    "claude": ((204, 119, 34), (160, 82, 16), (255, 210, 160)),
    "anthropic": ((204, 119, 34), (160, 82, 16), (255, 210, 160)),
    "claude-code": ((204, 119, 34), (160, 82, 16), (255, 210, 160)),
    "gemini": ((66, 133, 244), (25, 95, 200), (180, 210, 255)),
    "gemini-3": ((66, 133, 244), (25, 95, 200), (180, 210, 255)),
    "google-ai": ((66, 133, 244), (25, 95, 200), (180, 210, 255)),
    "machine-learning": ((16, 185, 129), (5, 130, 90), (167, 243, 208)),
    "llm": ((16, 185, 129), (5, 130, 90), (167, 243, 208)),
    # Python
    "python": ((55, 118, 171), (47, 85, 130), (200, 230, 255)),
    "fastapi": ((0, 150, 136), (0, 105, 92), (178, 223, 219)),
    "django": ((9, 46, 32), (44, 120, 44), (167, 243, 208)),
    # JavaScript / Frontend
    "javascript": ((50, 50, 50), (30, 30, 30), (247, 223, 30)),
    "typescript": ((49, 120, 198), (0, 78, 152), (144, 202, 249)),
    "react": ((30, 30, 30), (50, 50, 60), (97, 218, 251)),
    "vue": ((65, 184, 131), (52, 73, 94), (200, 240, 210)),
    "nextjs": ((30, 30, 30), (60, 60, 60), (200, 200, 200)),
    # DevOps / Infra
    "docker": ((13, 183, 237), (0, 120, 180), (179, 229, 252)),
    "kubernetes": ((50, 108, 229), (30, 70, 160), (159, 188, 249)),
    "k8s": ((50, 108, 229), (30, 70, 160), (159, 188, 249)),
    "terraform": ((98, 75, 178), (67, 51, 122), (200, 180, 245)),
    "devops": ((96, 125, 139), (55, 71, 79), (176, 190, 197)),
    # Databases
    "postgresql": ((51, 103, 145), (25, 67, 100), (144, 202, 249)),
    "redis": ((220, 56, 45), (160, 30, 20), (255, 170, 160)),
    "valkey": ((220, 56, 45), (160, 30, 20), (255, 170, 160)),
    "mongodb": ((77, 170, 37), (50, 120, 20), (200, 240, 180)),
    # Tools / Git / IDE
    "git": ((240, 80, 51), (180, 50, 30), (255, 180, 160)),
    "github": ((36, 41, 47), (60, 65, 72), (200, 200, 210)),
    "vscode": ((0, 122, 204), (0, 80, 160), (144, 202, 249)),
    "extensions": ((0, 122, 204), (0, 80, 160), (144, 202, 249)),
    # Hugo
    "hugo": ((255, 79, 100), (200, 50, 70), (255, 180, 190)),
    # MCP / Protocols
    "mcp": ((124, 58, 237), (91, 33, 182), (196, 181, 253)),
    "fastmcp": ((124, 58, 237), (91, 33, 182), (196, 181, 253)),
    # Trading / Finance
    "trading": ((34, 139, 34), (20, 100, 20), (144, 238, 144)),
    "kis-api": ((34, 139, 34), (20, 100, 20), (144, 238, 144)),
    # Shell / Automation
    "shell": ((50, 50, 50), (30, 30, 30), (180, 255, 180)),
    "automation": ((50, 50, 50), (30, 30, 30), (180, 255, 180)),
    "hooks": ((50, 50, 50), (30, 30, 30), (180, 255, 180)),
    # Web Components
    "web-components": ((255, 100, 0), (200, 60, 0), (255, 200, 150)),
    "fast": ((255, 100, 0), (200, 60, 0), (255, 200, 150)),
    # Structured output / API
    "function-calling": ((66, 133, 244), (25, 95, 200), (180, 210, 255)),
    "structured-output": ((66, 133, 244), (25, 95, 200), (180, 210, 255)),
    "api": ((100, 100, 120), (60, 60, 80), (180, 180, 210)),
}

_DEFAULT_PALETTE: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]] = (
    (99, 102, 106), (55, 58, 64), (180, 185, 190)
)

_COVER_WIDTH = 1200
_COVER_HEIGHT = 630


def _pick_palette(
    tags: list[str],
) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    """Select a color palette based on the first matching tag."""
    for tag in tags:
        key = tag.lower()
        if key in TAG_COLOR_SCHEMES:
            return TAG_COLOR_SCHEMES[key]
    return _DEFAULT_PALETTE


def _draw_gradient(
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    width: int,
    height: int,
) -> "Image.Image":
    """Create a diagonal gradient image."""
    from PIL import Image

    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            t = x / width * 0.6 + y / height * 0.4
            r = int(start[0] + (end[0] - start[0]) * t)
            g = int(start[1] + (end[1] - start[1]) * t)
            b = int(start[2] + (end[2] - start[2]) * t)
            pixels[x, y] = (r, g, b)  # type: ignore[index]
    return img


def _load_font(size: int, config: Config | None = None):  # noqa: ANN201
    """Load a Korean-compatible font. Falls back gracefully."""
    from PIL import ImageFont

    # Check config override first
    if config and config.images.cover_font_path:
        try:
            return ImageFont.truetype(config.images.cover_font_path, size)
        except (OSError, IOError):
            pass

    # System font candidates (macOS → Linux)
    candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:  # noqa: ANN001
    """Break text into lines that fit within max_width pixels."""
    # For CJK text, wrap character-by-character when no spaces
    has_spaces = " " in text
    if has_spaces:
        words = text.split()
    else:
        words = list(text)  # character-level for pure CJK

    lines: list[str] = []
    current = ""
    for word in words:
        sep = " " if has_spaces and current else ""
        test = f"{current}{sep}{word}"
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    # Limit to 3 lines, trim last line with ellipsis if needed
    if len(lines) > 3:
        lines = lines[:3]
        last = lines[-1]
        while len(last) > 1:
            candidate = last + "..."
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= max_width:
                lines[-1] = candidate
                break
            last = last[:-1]
        else:
            lines[-1] = "..."
    return lines or [text[:50]]


def _darken_color(color: tuple[int, int, int], factor: float = 0.3) -> tuple[int, int, int]:
    """Darken a color by a factor (0.0 = black, 1.0 = original)."""
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def _draw_grid_overlay(
    img: "Image.Image",
    color: tuple[int, int, int],
    spacing: int = 60,
    line_width: int = 1,
) -> None:
    """Draw a subtle grid pattern on the image."""
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    w, h = img.size
    for x in range(0, w, spacing):
        draw.line([(x, 0), (x, h)], fill=color, width=line_width)
    for y in range(0, h, spacing):
        draw.line([(0, y), (w, y)], fill=color, width=line_width)


def _draw_grid_layout(  # noqa: ANN001
    draw,
    title: str,
    subtitle: str,
    meta_line: str,
    accent: tuple[int, int, int],
    width: int,
    height: int,
    config: "Config | None" = None,
) -> None:
    """Draw the grid-style layout: accent line + left-aligned title + subtitle + date."""
    left_pad = 40

    title_font = _load_font(size=52, config=config)
    subtitle_font = _load_font(size=26, config=config)
    meta_font = _load_font(size=18, config=config)

    max_text_width = width - left_pad - 80
    lines = _wrap_text(draw, title, title_font, max_text_width)

    line_height = 64
    y = int(height * 0.32)

    # Accent line
    draw.line([(left_pad, y), (left_pad + 150, y)], fill=accent, width=4)
    y += 14

    # Title lines (left-aligned, white, with subtle shadow)
    for line in lines:
        draw.text((left_pad + 2, y + 2), line, fill=(0, 0, 0), font=title_font)
        draw.text((left_pad, y), line, fill=(255, 255, 255), font=title_font)
        y += line_height

    y += 4

    # Subtitle
    if subtitle:
        draw.text((left_pad, y), subtitle, fill=(200, 200, 210), font=subtitle_font)
        y += 38

    # Date | Category
    if meta_line:
        draw.text((left_pad, y), meta_line, fill=(160, 160, 170), font=meta_font)


def _draw_title(draw, title: str, font, width: int, height: int) -> None:  # noqa: ANN001
    """Draw wrapped title text, centered vertically in the upper portion (legacy)."""
    max_text_width = width - 140  # 70px padding each side
    lines = _wrap_text(draw, title, font, max_text_width)

    line_height = getattr(font, "size", 40) + 14
    total_h = len(lines) * line_height
    y_start = (int(height * 0.5) - total_h) // 2 + 30

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (width - tw) // 2
        y = y_start + i * line_height
        # Shadow
        draw.text((x + 2, y + 2), line, fill=(0, 0, 0), font=font)
        # Main text
        draw.text((x, y), line, fill=(255, 255, 255), font=font)


def _draw_tag_pills(draw, tags: list[str], font, accent: tuple[int, int, int], width: int, height: int) -> None:  # noqa: ANN001
    """Draw tag labels as rounded pill shapes at the bottom of the image."""
    if not tags:
        return

    display_tags = tags[:5]
    pill_h = 32
    pad_x = 16
    gap = 10
    max_pills_w = width - 40  # 20px margin each side
    y = height - 60

    pill_widths = []
    for tag in display_tags:
        bbox = draw.textbbox((0, 0), tag, font=font)
        pill_widths.append((bbox[2] - bbox[0]) + pad_x * 2)

    # Drop trailing tags until they fit within the image width
    while len(display_tags) > 1:
        total_w = sum(pill_widths) + gap * (len(display_tags) - 1)
        if total_w <= max_pills_w:
            break
        display_tags = display_tags[:-1]
        pill_widths = pill_widths[:-1]

    total_w = sum(pill_widths) + gap * (len(display_tags) - 1)
    x = (width - total_w) // 2

    # Text color based on accent brightness
    brightness = (accent[0] * 299 + accent[1] * 587 + accent[2] * 114) / 1000
    text_color = (30, 30, 30) if brightness > 128 else (255, 255, 255)

    for i, tag in enumerate(display_tags):
        pw = pill_widths[i]
        draw.rounded_rectangle(
            [x, y, x + pw, y + pill_h],
            radius=pill_h // 2,
            fill=accent,
        )
        bbox = draw.textbbox((0, 0), tag, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = x + (pw - tw) // 2
        ty = y + (pill_h - th) // 2 - 2
        draw.text((tx, ty), tag, fill=text_color, font=font)
        x += pw + gap


def generate_cover_image(
    title: str,
    tags: list[str],
    post_slug: str,
    config: Config,
) -> ImageResult:
    """Generate a gradient cover image with title and tag labels using PIL.

    Skips if the cover image already exists on disk (safe for --update).
    """
    repo = config.blog.repo_path_resolved
    rel_url = f"/images/posts/{post_slug}/cover.jpg"
    dest = repo / "static" / "images" / "posts" / post_slug / "cover.jpg"

    if dest.exists():
        return ImageResult(path=dest, relative_url=rel_url, success=True)

    try:
        from PIL import ImageDraw

        grad_start, grad_end, accent = _pick_palette(tags)

        # Dark grid-style background
        dark_start = _darken_color(grad_start, 0.28)
        dark_end = _darken_color(grad_end, 0.28)
        img = _draw_gradient(dark_start, dark_end, _COVER_WIDTH, _COVER_HEIGHT)

        # Grid overlay — slightly lighter than background
        grid_color = _darken_color(grad_start, 0.38)
        _draw_grid_overlay(img, grid_color, spacing=60, line_width=1)

        draw = ImageDraw.Draw(img)

        # Split title on " — " for display title + subtitle
        if " — " in title:
            display_title, subtitle = title.split(" — ", 1)
        elif " - " in title:
            display_title, subtitle = title.split(" - ", 1)
        else:
            display_title = title
            subtitle = " + ".join(t.replace("-", " ").title() for t in tags[:3])

        # Extract date from slug
        date_str = post_slug[:10] if len(post_slug) >= 10 else ""
        meta_line = f"{date_str}  |  Tech Log" if date_str else ""

        _draw_grid_layout(
            draw, display_title, subtitle, meta_line,
            accent, _COVER_WIDTH, _COVER_HEIGHT, config,
        )

        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(dest), "JPEG", quality=90)

        return ImageResult(path=dest, relative_url=rel_url, success=True)

    except Exception as e:
        return ImageResult(
            path=None, relative_url="", success=False,
            error=f"Cover image generation failed: {e}",
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


def _generate_taxonomy_card(
    slug: str, kind: str, config: Config,
) -> Path:
    """Generate a grid-style JPG card image for a taxonomy entry."""
    from PIL import ImageDraw as _ImageDraw

    prefix = f"{kind}-"
    repo = config.blog.repo_path_resolved
    dest = repo / "static" / "images" / "taxonomy" / f"{prefix}{slug}.jpg"

    if dest.exists():
        return dest

    if kind == "cat":
        palette = TAG_COLOR_SCHEMES.get(slug, _DEFAULT_PALETTE)
    else:
        palette = TAG_COLOR_SCHEMES.get(slug, _DEFAULT_PALETTE)

    grad_start, grad_end, accent = palette
    dark_start = _darken_color(grad_start, 0.28)
    dark_end = _darken_color(grad_end, 0.28)
    img = _draw_gradient(dark_start, dark_end, _COVER_WIDTH, _COVER_HEIGHT)

    grid_color = _darken_color(grad_start, 0.38)
    _draw_grid_overlay(img, grid_color, spacing=60, line_width=1)

    draw = _ImageDraw.Draw(img)
    title = _slug_to_title(slug) if slug.isascii() else slug
    label = "Category" if kind == "cat" else "Tag"

    _draw_grid_layout(
        draw, title, "", label,
        accent, _COVER_WIDTH, _COVER_HEIGHT, config,
    )

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dest), "JPEG", quality=90)
    return dest


def _ensure_taxonomy_icon(
    slug: str, kind: str, config: Config,
) -> TaxonomyResult:
    """Ensure a taxonomy entry (tag or category) has an SVG icon, JPG card, and _index.md.

    Args:
        slug: Kebab-case slug (e.g., "python", "tech-log").
        kind: Either "tag" or "cat".
        config: Application config.
    """
    prefix = f"{kind}-"
    content_subdir = "tags" if kind == "tag" else "categories"

    repo = config.blog.repo_path_resolved
    svg_path = repo / "static" / "images" / "taxonomy" / f"{prefix}{slug}.svg"
    jpg_path = repo / "static" / "images" / "taxonomy" / f"{prefix}{slug}.jpg"
    index_dir = repo / "content" / content_subdir / slug
    index_path = index_dir / "_index.md"

    svg_exists = svg_path.exists()
    jpg_exists = jpg_path.exists()
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

    # Generate JPG card image for section cards
    if not jpg_exists:
        try:
            _generate_taxonomy_card(slug, kind, config)
        except Exception:
            pass  # JPG is optional; SVG still works as fallback

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
    title: str,
    tags: list[str],
    categories: list[str],
    config: Config,
) -> ImageAssets:
    """Top-level: generate cover image + ensure all taxonomy icons.

    Called during the publish step after tags/categories are finalized.
    """
    assets = ImageAssets()

    # Cover image
    if config.images.cover_enabled and title:
        assets.cover = generate_cover_image(title, tags, post_slug, config)
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
