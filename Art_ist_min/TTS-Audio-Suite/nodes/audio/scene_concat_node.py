"""
Scene Concat Node
"""

import os
import sys

current_dir = os.path.dirname(__file__)
nodes_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(nodes_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.audio.scene_concat import concat_scene_audio


class SceneConcatNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clips_dir": ("STRING", {"default": "", "multiline": False}),
            },
            "optional": {
                "output_path": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "output_path", "concat_info")
    FUNCTION = "concat_scene"
    CATEGORY = "TTS Audio Suite/🎵 Audio Processing"

    def concat_scene(self, clips_dir, output_path=""):
        result = concat_scene_audio(folder_path=clips_dir, output_path=output_path or None)
        info = (
            f"Scene concat complete:\n"
            f"  Output path: {result['output_path']}\n"
            f"  Clips used: {result['clip_count']}\n"
            f"  Sample rate: {result['sample_rate']}"
        )
        return result["audio"], result["output_path"], info
