"""
Scene edit driver utilities.

Provides:
- partitioning of scene edit JSON into Step vs voice routes
- standalone mixed edit execution
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torchaudio

from utils.compatibility.pytorch_patches import apply_pytorch_patches
from utils.audio.processing import AudioProcessingUtils
from utils.voice.discovery import get_available_voices, load_voice_reference, voice_discovery

apply_pytorch_patches(verbose=False)


def _resolve_comfyui_root(comfyui_root: Optional[str] = None) -> Optional[Path]:
    candidates = []
    if comfyui_root:
        candidates.append(Path(comfyui_root))
    env_root = os.environ.get("COMFYUI_ROOT")
    if env_root:
        candidates.append(Path(env_root))

    project_root = Path(__file__).resolve().parents[2]
    candidates.extend([
        project_root.parent / "ComfyUI",
        project_root.parent.parent / "ComfyUI",
        project_root.parent.parent.parent / "ComfyUI",
    ])

    for candidate in candidates:
        if (candidate / "folder_paths.py").exists():
            return candidate.resolve()
    return None


def _prepare_comfyui_imports(comfyui_root: Optional[str] = None) -> Path:
    resolved = _resolve_comfyui_root(comfyui_root)
    if not resolved:
        raise RuntimeError(
            "Could not locate ComfyUI root for Step Audio EditX standalone editing. "
            "Set COMFYUI_ROOT or pass a ComfyUI root path to the edit driver."
        )
    resolved_str = str(resolved)
    if resolved_str not in sys.path:
        sys.path.insert(0, resolved_str)
    return resolved


def _load_step_audio_editor_node(comfyui_root: Optional[str] = None):
    _prepare_comfyui_imports(comfyui_root)
    project_root = Path(__file__).resolve().parents[2]
    node_path = project_root / "nodes" / "step_audio_editx_special" / "step_audio_editx_audio_editor_node.py"
    spec = importlib.util.spec_from_file_location("scene_editx_editor_node", node_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.StepAudioEditXAudioEditorNode


def _load_voice_changer_node(comfyui_root: Optional[str] = None):
    _prepare_comfyui_imports(comfyui_root)
    project_root = Path(__file__).resolve().parents[2]
    node_path = project_root / "nodes" / "unified" / "voice_changer_node.py"
    spec = importlib.util.spec_from_file_location("scene_voice_changer_node", node_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.UnifiedVoiceChangerNode


def _save_comfy_audio(audio_dict: Dict[str, Any], output_path: str) -> None:
    waveform = audio_dict["waveform"]
    sample_rate = int(audio_dict["sample_rate"])
    if waveform.dim() == 3:
        waveform = waveform.squeeze(0)
    elif waveform.dim() == 1:
        waveform = waveform.unsqueeze(0)
    torchaudio.save(output_path, waveform.cpu(), sample_rate)


def _coerce_iterations(item: Dict[str, Any]) -> int:
    value = item.get("n_edit_iterations", item.get("iterations", 1))
    try:
        return max(1, min(5, int(value)))
    except Exception:
        return 1


STEP_EDIT_TYPES = {"emotion", "style", "speed", "paralinguistic", "denoise", "vad"}
VOICE_EDIT_TYPES = {"voice"}


def _default_voice_engine_data() -> Dict[str, Any]:
    return {
        "engine_type": "chatterbox",
        "config": {
            "device": "auto",
            "language": "English",
        },
        "adapter_class": "ChatterBoxAdapter",
    }


def _resolve_voice_reference_path(voice_value: str) -> Tuple[str, str]:
    voice_value = str(voice_value or "").strip()
    if not voice_value:
        raise ValueError("Voice edit item is missing the 'voice' field")

    candidate_paths = []
    as_path = Path(voice_value)
    if as_path.is_file():
        candidate_paths.append(as_path.resolve())

    project_root = Path(__file__).resolve().parents[2]
    candidate_paths.append((project_root / "voices_examples" / voice_value).resolve())

    for candidate in candidate_paths:
        if candidate.exists():
            return str(candidate), ""

    voice_info = voice_discovery.get_voice_info(voice_value)
    if voice_info and voice_info.get("audio_path"):
        return voice_info["audio_path"], voice_info.get("text_content", "") or ""

    basename = os.path.basename(voice_value).lower()
    for key in get_available_voices(force_refresh=True):
        if key == "none":
            continue
        if os.path.basename(key).lower() == basename:
            audio_path, reference_text = load_voice_reference(key)
            if audio_path:
                return audio_path, reference_text or ""

    raise FileNotFoundError(f"Could not resolve target voice reference '{voice_value}'")


def _partition_items(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    step_items: List[Dict[str, Any]] = []
    voice_items: List[Dict[str, Any]] = []
    unsupported_items: List[Dict[str, Any]] = []
    for item in items:
        edit_type = str(item.get("edit_type", "emotion")).strip().lower()
        if edit_type in STEP_EDIT_TYPES:
            step_items.append(item)
        elif edit_type in VOICE_EDIT_TYPES:
            voice_items.append(item)
        else:
            unsupported_items.append(item)
    return step_items, voice_items, unsupported_items


def partition_scene_edit_instructions(
    enriched_json_path: str,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    output_path = Path(output_dir or Path(enriched_json_path).resolve().parent)
    output_path.mkdir(parents=True, exist_ok=True)

    with open(enriched_json_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    if not isinstance(items, list):
        raise ValueError("Enriched edit JSON must be a list")

    step_items, voice_items, unsupported_items = _partition_items(items)

    stem = Path(enriched_json_path).stem
    step_json_path = output_path / f"{stem}_step.json"
    voice_json_path = output_path / f"{stem}_voice.json"
    unsupported_json_path = output_path / f"{stem}_unsupported.json"

    with open(step_json_path, "w", encoding="utf-8") as f:
        json.dump(step_items, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(voice_json_path, "w", encoding="utf-8") as f:
        json.dump(voice_items, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(unsupported_json_path, "w", encoding="utf-8") as f:
        json.dump(unsupported_items, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return {
        "step_json_path": str(step_json_path.resolve()),
        "voice_json_path": str(voice_json_path.resolve()),
        "unsupported_json_path": str(unsupported_json_path.resolve()),
        "step_count": len(step_items),
        "voice_count": len(voice_items),
        "unsupported_count": len(unsupported_items),
    }


def edit_scene_clips(
    clips_dir: str,
    enriched_json_path: str,
    output_dir: Optional[str] = None,
    delete_originals: bool = True,
    tts_engine_data: Optional[Dict[str, Any]] = None,
    voice_tts_engine_data: Optional[Dict[str, Any]] = None,
    comfyui_root: Optional[str] = None,
) -> Dict[str, Any]:
    clips_path = Path(clips_dir)
    output_path = Path(output_dir or clips_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    with open(enriched_json_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    if not isinstance(items, list):
        raise ValueError("Enriched edit JSON must be a list")

    StepAudioEditXAudioEditorNode = _load_step_audio_editor_node(comfyui_root=comfyui_root)
    editor = StepAudioEditXAudioEditorNode()
    UnifiedVoiceChangerNode = _load_voice_changer_node(comfyui_root=comfyui_root)
    voice_changer = UnifiedVoiceChangerNode()

    edited_files: List[str] = []
    failed_files: List[str] = []
    skipped_files: List[str] = []
    route_stats = {"step": 0, "voice": 0, "unsupported": 0}

    for item in items:
        file_name = item.get("file_name")
        text = str(item.get("text", "")).strip()
        edit_type = str(item.get("edit_type", "emotion")).strip().lower()
        if not file_name:
            failed_files.append("<missing-file-name>")
            continue
        source_path = clips_path / file_name
        if not source_path.exists():
            failed_files.append(file_name)
            continue

        waveform, sample_rate = AudioProcessingUtils.safe_load_audio(str(source_path))
        comfy_audio = AudioProcessingUtils.format_for_comfyui(waveform, sample_rate)

        if edit_type in STEP_EDIT_TYPES:
            emotion = str(item.get("emotion", "none"))
            style = str(item.get("style", "none"))
            speed = str(item.get("speed", "none"))
            n_edit_iterations = _coerce_iterations(item)

            edited_audio, _edit_info = editor.edit_audio(
                input_audio=comfy_audio,
                audio_text=text,
                edit_type=edit_type,
                emotion=emotion,
                style=style,
                speed=speed,
                n_edit_iterations=n_edit_iterations,
                tts_engine=tts_engine_data,
            )
            route_stats["step"] += 1
        elif edit_type in VOICE_EDIT_TYPES:
            voice_path, _reference_text = _resolve_voice_reference_path(str(item.get("voice", "")))
            target_waveform, target_sample_rate = AudioProcessingUtils.safe_load_audio(voice_path)
            target_audio = AudioProcessingUtils.format_for_comfyui(target_waveform, target_sample_rate)
            refinement_passes = max(1, int(item.get("refinement_passes", 1)))
            effective_voice_engine = voice_tts_engine_data or _default_voice_engine_data()

            edited_audio, _edit_info = voice_changer.convert_voice(
                TTS_engine=effective_voice_engine,
                source_audio=comfy_audio,
                narrator_target=target_audio,
                refinement_passes=refinement_passes,
                max_chunk_duration=int(item.get("max_chunk_duration", 30)),
                chunk_method=str(item.get("chunk_method", "smart")),
            )
            route_stats["voice"] += 1
        else:
            skipped_files.append(file_name)
            route_stats["unsupported"] += 1
            continue

        edited_name = f"edited_{file_name}"
        edited_path = output_path / edited_name
        _save_comfy_audio(edited_audio, str(edited_path))
        edited_files.append(edited_name)

        if delete_originals:
            try:
                source_path.unlink()
            except FileNotFoundError:
                pass

    return {
        "clips_dir": str(clips_path.resolve()),
        "output_dir": str(output_path.resolve()),
        "edited_files": edited_files,
        "edited_count": len(edited_files),
        "failed_files": failed_files,
        "failed_count": len(failed_files),
        "skipped_files": skipped_files,
        "skipped_count": len(skipped_files),
        "route_stats": route_stats,
        "delete_originals": delete_originals,
    }
