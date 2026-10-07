"""
Scene Splitter Node
"""

import os
import sys
from typing import Any

current_dir = os.path.dirname(__file__)
nodes_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(nodes_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.audio.processing import AudioProcessingUtils
from utils.audio.scene_splitter import split_scene_audio


class SceneSplitterNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_file": ("STRING", {"default": "", "multiline": False}),
                "edit_instructions_path": ("STRING", {"default": "", "multiline": False}),
                "output_dir": ("STRING", {"default": "", "multiline": False}),
            },
            "optional": {
                "audio": ("AUDIO", {}),
                "transcript_path": ("STRING", {"default": "", "multiline": False}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("output_dir", "enriched_json_path", "scene_manifest_path", "split_info")
    FUNCTION = "split_scene"
    CATEGORY = "TTS Audio Suite/🎵 Audio Processing"

    def split_scene(self, audio_file, edit_instructions_path, output_dir, audio=None, transcript_path=""):
        if audio is not None:
            normalized = AudioProcessingUtils.normalize_audio_input(audio, "audio")
            temp_audio_path = AudioProcessingUtils.save_audio_to_temp_file(
                normalized["waveform"], normalized["sample_rate"], suffix=".wav"
            )
            audio_file = temp_audio_path

        result = split_scene_audio(
            audio_path=audio_file,
            instruction_path=edit_instructions_path,
            output_dir=output_dir,
            transcript_path=transcript_path or None,
        )

        info = (
            f"Scene split complete:\n"
            f"  Output dir: {result['output_dir']}\n"
            f"  Clips: {result['clip_count']}\n"
            f"  Edited targets: {result['edited_target_count']}\n"
            f"  Duration: {result['duration']:.3f}s"
        )
        return (
            result["output_dir"],
            result["enriched_json_path"],
            result["scene_manifest_path"],
            info,
        )
