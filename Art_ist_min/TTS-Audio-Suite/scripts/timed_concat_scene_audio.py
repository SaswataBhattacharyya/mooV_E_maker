#!/usr/bin/env python3
"""
Concatenate scene clips using an explicit JSON manifest with per-clip gaps.
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.audio.timed_scene_concat import concat_scene_audio_by_manifest


def _prompt_if_missing(value: str, prompt: str) -> str:
    return value if value else input(f"{prompt}: ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Concatenate scene clips using a manifest with scheduled silence gaps")
    parser.add_argument("--clips-dir", help="Folder containing audio clips referenced by the manifest")
    parser.add_argument("--manifest", help="JSON manifest defining file order and gap_after_seconds values")
    parser.add_argument("--output", "--output-path", dest="output", help="Optional output file path")
    args = parser.parse_args()

    clips_dir = _prompt_if_missing(args.clips_dir, "Clips folder path")
    manifest = _prompt_if_missing(args.manifest, "Manifest JSON path")
    result = concat_scene_audio_by_manifest(folder_path=clips_dir, manifest_path=manifest, output_path=args.output)

    serializable = dict(result)
    serializable.pop("audio", None)
    print(json.dumps(serializable, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
