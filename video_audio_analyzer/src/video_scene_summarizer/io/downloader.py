from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


def _yt_dlp():
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("YouTube downloading requires yt-dlp; install the project requirements first") from exc
    return yt_dlp


def _download_options(output_dir: Path) -> dict[str, Any]:
    return {
        "format": (
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[height<=720]+bestaudio/"
            "best[height<=720]/best"
        ),
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        "noplaylist": True,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
        "quiet": True,
    }


def fetch_metadata(url: str) -> dict[str, Any]:
    yt_dlp = _yt_dlp()
    with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
        return ydl.extract_info(url, download=False)


def download_video(url: str, output_dir: Path) -> tuple[Path, dict[str, Any]]:
    yt_dlp = _yt_dlp()
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = fetch_metadata(url)
    expected_path = None
    with yt_dlp.YoutubeDL(_download_options(output_dir)) as ydl:
        info = ydl.extract_info(url, download=True)
        expected = ydl.prepare_filename(info)
        expected_path = Path(expected)
    if expected_path and not expected_path.exists():
        mp4_guess = expected_path.with_suffix(".mp4")
        if mp4_guess.exists():
            expected_path = mp4_guess
    if not expected_path or not expected_path.exists():
        raise FileNotFoundError(f"Downloaded file not found for {url}")
    LOGGER.info("Downloaded %s to %s", url, expected_path)
    return expected_path, metadata
