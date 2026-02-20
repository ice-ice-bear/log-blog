"""YouTube transcript fetcher using youtube-transcript-api."""

from __future__ import annotations

import logging

from .url_classifier import parse_youtube_id

logger = logging.getLogger(__name__)

_MAX_TRANSCRIPT_CHARS = 15000


def fetch_youtube_transcript(url: str) -> dict | None:
    """Fetch YouTube transcript and metadata.

    Returns a dict with keys: video_id, title, transcript_text, language
    or None if transcript is unavailable.
    """
    video_id = parse_youtube_id(url)
    if not video_id:
        return None

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        logger.warning("youtube-transcript-api not installed, skipping transcript fetch")
        return None

    try:
        transcript_entries = _get_transcript(video_id)
    except Exception as e:
        logger.warning("Failed to fetch transcript for %s: %s", video_id, e)
        return None

    if not transcript_entries:
        return None

    # Build full text from transcript entries
    text_parts = [entry.text for entry in transcript_entries]
    full_text = " ".join(text_parts)

    if len(full_text) > _MAX_TRANSCRIPT_CHARS:
        full_text = full_text[:_MAX_TRANSCRIPT_CHARS] + "\n\n[Transcript truncated...]"

    # Detect language from the transcript metadata
    language = getattr(transcript_entries[0], "language", None) if transcript_entries else None

    return {
        "video_id": video_id,
        "transcript_text": full_text,
        "language": language,
    }


def _get_transcript(video_id: str):
    """Try fetching transcript in preferred language order: ko > en > any."""
    from youtube_transcript_api import YouTubeTranscriptApi

    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

    # Try Korean first
    try:
        return transcript_list.find_transcript(["ko"]).fetch()
    except Exception:
        pass

    # Try English
    try:
        return transcript_list.find_transcript(["en"]).fetch()
    except Exception:
        pass

    # Try any generated/manual transcript
    try:
        for transcript in transcript_list:
            return transcript.fetch()
    except Exception:
        pass

    return None
