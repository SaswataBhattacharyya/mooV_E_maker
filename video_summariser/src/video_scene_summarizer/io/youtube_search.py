from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)


def _yt_dlp():
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("YouTube search requires yt-dlp; install the project requirements first") from exc
    return yt_dlp


def normalize_url(value: str) -> str:
    return value.strip()


def get_latest_video_url(channel_url: str) -> str:
    yt_dlp = _yt_dlp()
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "playlistend": 1,
        "noplaylist": False,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    entries = info.get("entries") or []
    if not entries:
        raise RuntimeError("No videos found for channel query.")
    latest = entries[0]
    if latest.get("webpage_url"):
        return normalize_url(latest["webpage_url"])
    if latest.get("id"):
        return f"https://www.youtube.com/watch?v={latest['id']}"
    raise RuntimeError("Could not extract latest video URL.")


def search_youtube_urls(query: str, max_results: int) -> list[dict[str, Any]]:
    yt_dlp = _yt_dlp()
    search_term = f"ytsearch{max_results}:{query}"
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "noplaylist": True,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_term, download=False)
    entries = info.get("entries") or []
    results: list[dict[str, Any]] = []
    for entry in entries:
        url = entry.get("webpage_url")
        if not url and entry.get("id"):
            url = f"https://www.youtube.com/watch?v={entry['id']}"
        if not url:
            continue
        results.append(
            {
                "url": normalize_url(url),
                "video_id": entry.get("id", ""),
                "title": entry.get("title", entry.get("id", "video")),
                "channel": entry.get("channel") or entry.get("uploader") or "",
            }
        )
    LOGGER.info("Collected %s candidate URLs for query %r", len(results), query)
    return results
