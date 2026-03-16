from log_blog.url_classifier import classify_url, UrlType


class TestAiLandingNoise:
    """AI service landing/oauth/settings pages should be classified as AI_LANDING."""

    def test_claude_landing(self):
        assert classify_url("https://claude.ai/") == UrlType.AI_LANDING

    def test_claude_oauth(self):
        assert classify_url("https://claude.ai/oauth/authorize?client_id=abc") == UrlType.AI_LANDING

    def test_claude_chrome_extension(self):
        assert classify_url("https://claude.ai/chrome/installed") == UrlType.AI_LANDING

    def test_claude_chrome(self):
        assert classify_url("https://claude.ai/chrome") == UrlType.AI_LANDING

    def test_claude_code_landing(self):
        assert classify_url("https://claude.ai/code") == UrlType.AI_LANDING

    def test_claude_code_onboarding(self):
        assert classify_url("https://claude.ai/code/onboarding") == UrlType.AI_LANDING

    def test_claude_code_family(self):
        assert classify_url("https://claude.ai/code/family") == UrlType.AI_LANDING

    def test_claude_code_session(self):
        assert classify_url("https://claude.ai/code/session_01B7q7jFgiLCaFcY4Pw6Amay") == UrlType.AI_LANDING

    def test_claude_project(self):
        assert classify_url("https://claude.ai/project/abc-def-123") == UrlType.AI_LANDING

    def test_chatgpt_landing(self):
        assert classify_url("https://chatgpt.com/") == UrlType.AI_LANDING

    def test_chatgpt_landing_bare(self):
        assert classify_url("https://chatgpt.com") == UrlType.AI_LANDING

    def test_chatgpt_auth(self):
        assert classify_url("https://chatgpt.com/auth/login") == UrlType.AI_LANDING

    def test_chatgpt_backend_api(self):
        assert classify_url("https://chatgpt.com/backend-api/conversation") == UrlType.AI_LANDING

    def test_chatgpt_gpts_landing(self):
        assert classify_url("https://chatgpt.com/gpts") == UrlType.AI_LANDING

    def test_gemini_landing_no_id(self):
        assert classify_url("https://gemini.google.com/app?is_sa=1") == UrlType.AI_LANDING

    def test_gemini_root(self):
        assert classify_url("https://gemini.google.com/?hl=ko") == UrlType.AI_LANDING

    def test_gemini_download(self):
        assert classify_url("https://gemini.google.com/app/download/mobile?is_sa=1") == UrlType.AI_LANDING

    def test_gemini_extensions(self):
        assert classify_url("https://gemini.google.com/app/extensions") == UrlType.AI_LANDING

    def test_gemini_settings(self):
        assert classify_url("https://gemini.google.com/app/settings") == UrlType.AI_LANDING

    def test_perplexity_landing(self):
        assert classify_url("https://perplexity.ai/") == UrlType.AI_LANDING


class TestAiChatConversationsStillMatch:
    """Existing conversation patterns must still work after noise filter is added."""

    def test_chatgpt_conversation(self):
        assert classify_url("https://chatgpt.com/c/69b77094-9800-8320-ac7f-a1fdddde92c6") == UrlType.AI_CHAT_CHATGPT

    def test_chatgpt_share(self):
        assert classify_url("https://chatgpt.com/share/abc-123") == UrlType.AI_CHAT_CHATGPT

    def test_chatgpt_gpt(self):
        assert classify_url("https://chatgpt.com/g/g-abc123") == UrlType.AI_CHAT_CHATGPT

    def test_claude_chat(self):
        assert classify_url("https://claude.ai/chat/abc-def-123-456") == UrlType.AI_CHAT_CLAUDE

    def test_gemini_conversation(self):
        assert classify_url("https://gemini.google.com/app/b316486a7f8fd8b7?is_sa=1") == UrlType.AI_CHAT_GEMINI

    def test_gemini_conversation_with_tracking(self):
        url = "https://gemini.google.com/app/accbf1620c63c6f5?is_sa=1&is_sa=1&android-min-version=301356232&gclid=CjwK"
        assert classify_url(url) == UrlType.AI_CHAT_GEMINI

    def test_perplexity_search(self):
        assert classify_url("https://perplexity.ai/search/some-query-abc123") == UrlType.AI_CHAT_PERPLEXITY

    def test_perplexity_page(self):
        assert classify_url("https://perplexity.ai/page/abc123") == UrlType.AI_CHAT_PERPLEXITY


class TestGeminiShareLinks:
    """Gemini share links should classify as AI_CHAT_GEMINI."""

    def test_gemini_share(self):
        assert classify_url("https://gemini.google.com/share/95c7453b12a1") == UrlType.AI_CHAT_GEMINI

    def test_gemini_share_with_query(self):
        assert classify_url("https://gemini.google.com/share/abc123?hl=ko") == UrlType.AI_CHAT_GEMINI


class TestNonAiUrlsUnchanged:
    """Non-AI URLs should still classify as before."""

    def test_github_repo(self):
        assert classify_url("https://github.com/owner/repo") == UrlType.GITHUB_REPO

    def test_youtube(self):
        assert classify_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == UrlType.YOUTUBE

    def test_web_page(self):
        assert classify_url("https://example.com/article") == UrlType.WEB_PAGE
