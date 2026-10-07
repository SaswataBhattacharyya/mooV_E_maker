"""Embedded subtitle extraction with provenance-preserving parsing."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


def extract_embedded(video: Path, output_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "unavailable", "source": "embedded", "segments": [], "text": ""}
    try:
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "s", "-show_entries", "stream=index:stream_tags=language", "-of", "json", str(video)], check=True, text=True, capture_output=True)
        import json
        streams = json.loads(probe.stdout).get("streams", [])
        if not streams:
            result["reason"] = "no embedded subtitle stream"
            return result
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "embedded.vtt"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-map", "0:s:0", "-c:s", "webvtt", str(path)], check=True, text=True, capture_output=True)
        segments: list[dict[str, Any]] = []
        raw = path.read_text(encoding="utf-8", errors="replace")
        for block in re.split(r"\n\s*\n", raw):
            match = re.search(r"(\d\d:\d\d:\d\d[.,]\d{3})\s+-->\s+(\d\d:\d\d:\d\d[.,]\d{3}).*\n(.+)", block, re.S)
            if not match:
                continue
            def seconds(value: str) -> float:
                h, m, s = value.replace(',', '.').split(':')
                return float(h) * 3600 + float(m) * 60 + float(s)
            text = re.sub(r"<[^>]+>", "", match.group(3)).replace("\n", " ").strip()
            if text:
                segments.append({"start_time_sec": round(seconds(match.group(1)), 3), "end_time_sec": round(seconds(match.group(2)), 3), "text": text})
        result.update({"status": "completed" if segments else "unavailable", "path": str(path), "segments": segments, "text": " ".join(item["text"] for item in segments)})
        if not segments:
            result["reason"] = "subtitle stream contained no parseable cues"
    except Exception as exc:
        result["reason"] = str(exc)
    return result
