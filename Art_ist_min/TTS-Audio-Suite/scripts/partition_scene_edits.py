#!/usr/bin/env python3
"""
Partition enriched scene edit JSON into Step Audio EditX, voice-change,
and unsupported buckets without requiring ComfyUI imports.
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.audio.scene_edit_driver import partition_scene_edit_instructions


def _prompt_if_missing(value: str, prompt: str) -> str:
    return value if value else input(f"{prompt}: ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Partition enriched scene edit JSON by edit route")
    parser.add_argument("--instructions", "--json", dest="instructions", help="Enriched edit JSON path")
    parser.add_argument("--output-dir", help="Output folder path")
    args = parser.parse_args()

    instructions = _prompt_if_missing(args.instructions, "Enriched edit JSON path")
    output_dir = _prompt_if_missing(args.output_dir, "Output folder path")

    result = partition_scene_edit_instructions(
        enriched_json_path=instructions,
        output_dir=output_dir,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
