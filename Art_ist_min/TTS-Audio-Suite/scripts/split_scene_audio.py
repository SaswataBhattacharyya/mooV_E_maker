#!/usr/bin/env python3
"""
Split scene audio into numbered clips using edit timing instructions.
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.audio.scene_splitter import split_scene_audio


def _prompt_if_missing(value: str, prompt: str) -> str:
    return value if value else input(f"{prompt}: ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Split scene audio into numbered clips")
    parser.add_argument("--audio", "--audio-file", dest="audio", help="Input scene audio path")
    parser.add_argument("--instructions", "--edit-instructions", dest="instructions", help="JSON/text edit instructions path")
    parser.add_argument("--output-dir", help="Output folder path")
    parser.add_argument("--transcript", help="Optional full transcript text path")
    parser.add_argument(
        "--name-template",
        help=(
            "Optional clip naming template. Available fields: "
            "{scene_stem}, {index}, {pad_width}, {kind}, {start}, {end}. "
            "Example: '{scene_stem}_clip_{index:03d}.wav'"
        ),
    )
    args = parser.parse_args()

    audio = _prompt_if_missing(args.audio, "Input audio path")
    instructions = _prompt_if_missing(args.instructions, "Instruction JSON/text path")
    output_dir = _prompt_if_missing(args.output_dir, "Output folder path")

    result = split_scene_audio(
        audio_path=audio,
        instruction_path=instructions,
        output_dir=output_dir,
        transcript_path=args.transcript,
        clip_name_template=args.name_template,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
