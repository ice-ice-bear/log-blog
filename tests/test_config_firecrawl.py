import tempfile
from pathlib import Path

from log_blog.config import load_config


def test_firecrawl_config_defaults():
    """FirecrawlConfig should have sensible defaults when not in YAML."""
    config = load_config(Path("/nonexistent/path"))
    assert config.firecrawl.api_key == ""
    assert config.firecrawl.max_pages == 10


def test_firecrawl_config_from_yaml():
    """FirecrawlConfig should load from YAML."""
    yaml_content = """
firecrawl:
  api_key: "fc-test-key"
  max_pages: 20
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = load_config(Path(f.name))

    assert config.firecrawl.api_key == "fc-test-key"
    assert config.firecrawl.max_pages == 20


def test_firecrawl_config_env_var(monkeypatch):
    """FirecrawlConfig should resolve ${ENV_VAR} in api_key."""
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-from-env")
    yaml_content = """
firecrawl:
  api_key: "${FIRECRAWL_API_KEY}"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = load_config(Path(f.name))

    assert config.firecrawl.api_key == "fc-from-env"
