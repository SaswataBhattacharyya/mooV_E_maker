#!/usr/bin/env python3
"""
Concatenate numbered scene clips into a final scene audio file.
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.audio.scene_concat import concat_scene_audio


def _prompt_if_missing(value: str, prompt: str) -> str:
    return value if value else input(f"{prompt}: ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Concatenate numbered scene clips")
    parser.add_argument("--clips-dir", help="Folder containing numbered clips")
    parser.add_argument("--output", "--output-path", dest="output", help="Optional output file path")
    args = parser.parse_args()

    clips_dir = _prompt_if_missing(args.clips_dir, "Clips folder path")
    result = concat_scene_audio(folder_path=clips_dir, output_path=args.output)

    serializable = dict(result)
    serializable.pop("audio", None)
    print(json.dumps(serializable, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
