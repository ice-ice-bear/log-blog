"""YouTube transcript fetcher using youtube-transcript-api."""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error

from .url_classifier import parse_youtube_id

logger = logging.getLogger(__name__)

_MAX_TRANSCRIPT_CHARS = 15000
_OEMBED_URL = "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"


def _fetch_oembed(video_id: str) -> dict:
    """Fetch video title and author via YouTube oEmbed API (no extra deps)."""
    try:
        url = _OEMBED_URL.format(video_id=video_id)
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read())
        return {
            "title": data.get("title", ""),
            "author_name": data.get("author_name", ""),
            "author_url": data.get("author_url", ""),
            "thumbnail_url": data.get("thumbnail_url", ""),
        }
    except Exception as e:
        logger.debug("oEmbed fetch failed for %s: %s", video_id, e)
        return {}


def fetch_youtube_transcript(url: str) -> dict | None:
    """Fetch YouTube transcript and metadata.

    Returns a dict with keys: video_id, title, author_name, transcript_text,
    language, language_code, thumbnail_url — or None if transcript is unavailable.
    """
    video_id = parse_youtube_id(url)
    if not video_id:
        return None

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        logger.warning("youtube-transcript-api not installed, skipping transcript fetch")
        return None

    # Fetch video metadata via oEmbed (lightweight, no API key needed)
    oembed = _fetch_oembed(video_id)

    try:
        transcript = _get_transcript(video_id)
    except Exception as e:
        logger.warning("Failed to fetch transcript for %s: %s", video_id, e)
        return None

    if not transcript:
        return None

    # Build full text from transcript snippets
    text_parts = [snippet.text for snippet in transcript]
    full_text = " ".join(text_parts)

    if len(full_text) > _MAX_TRANSCRIPT_CHARS:
        full_text = full_text[:_MAX_TRANSCRIPT_CHARS] + "\n\n[Transcript truncated...]"

    return {
        "video_id": video_id,
        "title": oembed.get("title", ""),
        "author_name": oembed.get("author_name", ""),
        "author_url": oembed.get("author_url", ""),
        "thumbnail_url": oembed.get("thumbnail_url", ""),
        "transcript_text": full_text,
        "language": getattr(transcript, "language", None),
        "language_code": getattr(transcript, "language_code", None),
    }


def _get_transcript(video_id: str):
    """Try fetching transcript in preferred language order: ko > en > any.

    Uses youtube-transcript-api v1.x instance-based API.
    Returns a FetchedTranscript (iterable of FetchedTranscriptSnippet) or None.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()

    # Try direct fetch with language priority (ko > en)
    try:
        return api.fetch(video_id, languages=["ko", "en"])
    except Exception:
        pass

    # Fallback: list all transcripts and take the first available
    try:
        transcript_list = api.list(video_id)
        for transcript in transcript_list:
            try:
                return transcript.fetch()
            except Exception:
                continue
    except Exception:
        pass

    return None
