#!/usr/bin/env python3
"""
Iteratively edit scene clips using Step Audio EditX.
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.audio.scene_edit_driver import edit_scene_clips


def _prompt_if_missing(value: str, prompt: str) -> str:
    return value if value else input(f"{prompt}: ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Edit split scene clips with Step Audio EditX")
    parser.add_argument("--clips-dir", help="Folder containing split clips")
    parser.add_argument("--instructions", "--json", dest="instructions", help="Enriched edit JSON path")
    parser.add_argument("--output-dir", help="Output folder for edited clips")
    parser.add_argument("--comfyui-root", help="ComfyUI root path containing folder_paths.py")
    parser.add_argument("--voice-engine", choices=["chatterbox"], default="chatterbox", help="Voice conversion engine for edit_type=voice")
    parser.add_argument("--keep-originals", action="store_true", help="Do not delete original clips after editing")
    args = parser.parse_args()

    clips_dir = _prompt_if_missing(args.clips_dir, "Clips folder path")
    instructions = _prompt_if_missing(args.instructions, "Enriched edit JSON path")
    output_dir = _prompt_if_missing(args.output_dir, "Output folder path")

    result = edit_scene_clips(
        clips_dir=clips_dir,
        enriched_json_path=instructions,
        output_dir=output_dir,
        delete_originals=not args.keep_originals,
        voice_tts_engine_data=None if args.voice_engine == "chatterbox" else None,
        comfyui_root=args.comfyui_root,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
