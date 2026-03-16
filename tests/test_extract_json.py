import json
from unittest.mock import patch

from log_blog.history_reader import HistoryEntry
from log_blog.url_classifier import UrlType


class TestExtractJsonUrlType:
    """extract --json should include url_type field."""

    def test_url_type_included(self):
        """When extract outputs JSON, each entry should have a url_type field."""
        from log_blog.cli import cmd_extract
        import argparse
        import io
        from contextlib import redirect_stdout

        entries = [
            HistoryEntry(url="https://chatgpt.com/c/abc-123", title="Chat", visit_count=1, last_visit_time=1700000000.0),
            HistoryEntry(url="https://gemini.google.com/app/abc123", title="Gemini", visit_count=1, last_visit_time=1700000000.0),
            HistoryEntry(url="https://claude.ai/", title="Claude", visit_count=1, last_visit_time=1700000000.0),
            HistoryEntry(url="https://example.com", title="Example", visit_count=1, last_visit_time=1700000000.0),
        ]

        args = argparse.Namespace(config=None, hours=24, json=True, include_noise=False)

        f = io.StringIO()
        with patch("log_blog.cli.read_history", return_value=entries), redirect_stdout(f):
            cmd_extract(args)

        data = json.loads(f.getvalue())

        # AI_LANDING (claude.ai/) should be excluded by default
        urls = [e["url"] for e in data]
        assert "https://claude.ai/" not in urls

        # Remaining entries should have url_type
        types = {e["url"]: e["url_type"] for e in data}
        assert types["https://chatgpt.com/c/abc-123"] == "ai_chat_chatgpt"
        assert types["https://gemini.google.com/app/abc123"] == "ai_chat_gemini"
        assert types["https://example.com"] == "web_page"

    def test_include_noise_flag(self):
        """--include-noise should include AI_LANDING entries."""
        from log_blog.cli import cmd_extract
        import argparse
        import io
        from contextlib import redirect_stdout

        entries = [
            HistoryEntry(url="https://claude.ai/", title="Claude", visit_count=1, last_visit_time=1700000000.0),
        ]

        args = argparse.Namespace(config=None, hours=24, json=True, include_noise=True)

        f = io.StringIO()
        with patch("log_blog.cli.read_history", return_value=entries), redirect_stdout(f):
            cmd_extract(args)

        data = json.loads(f.getvalue())
        assert len(data) == 1
        assert data[0]["url_type"] == "ai_landing"
