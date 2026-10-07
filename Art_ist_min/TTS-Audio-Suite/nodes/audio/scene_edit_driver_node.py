"""
Scene Edit Driver Node
"""

import os
import sys

current_dir = os.path.dirname(__file__)
nodes_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(nodes_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.audio.scene_edit_driver import partition_scene_edit_instructions


class SceneEditDriverNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clips_dir": ("STRING", {"default": "", "multiline": False}),
                "enriched_json_path": ("STRING", {"default": "", "multiline": False}),
                "output_dir": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("step_clips_dir", "step_json_path", "voice_clips_dir", "voice_json_path", "route_info")
    FUNCTION = "edit_scene"
    CATEGORY = "TTS Audio Suite/🎵 Audio Processing"

    def edit_scene(self, clips_dir, enriched_json_path, output_dir):
        result = partition_scene_edit_instructions(
            enriched_json_path=enriched_json_path,
            output_dir=output_dir,
        )
        info = (
            f"Scene edit routing prepared:\n"
            f"  Clips dir: {clips_dir}\n"
            f"  Step edits: {result['step_count']}\n"
            f"  Voice edits: {result['voice_count']}\n"
            f"  Unsupported: {result['unsupported_count']}"
        )
        return clips_dir, result["step_json_path"], clips_dir, result["voice_json_path"], info
