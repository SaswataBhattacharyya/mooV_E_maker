#!/usr/bin/env python3
"""
Convert audio files such as FLAC/WAV/M4A/OGG/AAC to MP3 using ffmpeg.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _prompt_if_missing(value: str, prompt: str) -> str:
    return value if value else input(f"{prompt}: ").strip()


def _ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg was not found on PATH")


def convert_audio_to_mp3(
    input_path: str,
    output_path: str | None = None,
    bitrate: str = "192k",
    overwrite: bool = False,
) -> dict[str, object]:
    _ensure_ffmpeg()

    source = Path(input_path)
    if not source.exists():
        raise FileNotFoundError(f"Input audio file not found: {input_path}")
    if not source.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")

    target = Path(output_path) if output_path else source.with_suffix(".mp3")
    if target.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y" if overwrite else "-n",
        "-i",
        str(source),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "Unknown ffmpeg failure"
        raise RuntimeError(f"ffmpeg conversion failed: {stderr}")

    return {
        "input_path": str(source.resolve()),
        "output_path": str(target.resolve()),
        "bitrate": bitrate,
        "overwrote": overwrite,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert an audio file to MP3 using ffmpeg")
    parser.add_argument("--input", "--audio", dest="input_path", help="Input audio file path")
    parser.add_argument("--output", dest="output_path", help="Optional output MP3 path")
    parser.add_argument("--bitrate", default="192k", help="Target MP3 bitrate (default: 192k)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output file")
    args = parser.parse_args()

    input_path = _prompt_if_missing(args.input_path, "Input audio file path")
    result = convert_audio_to_mp3(
        input_path=input_path,
        output_path=args.output_path,
        bitrate=args.bitrate,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
