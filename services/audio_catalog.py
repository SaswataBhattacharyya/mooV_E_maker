"""Read-only audio capability, voice, and model discovery for the Audio Studio."""

from __future__ import annotations

import os
import platform
import re
import tempfile
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_COMFYUI_ROOT = Path("/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI")
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}
MODEL_EXTENSIONS = {".pth", ".pt", ".safetensors", ".ckpt", ".bin"}
VOICE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")


def comfyui_root() -> Path:
    return Path(os.environ.get("COMFYUI_ROOT", str(DEFAULT_COMFYUI_ROOT))).expanduser().resolve()


def tts_suite_root() -> Path:
    configured = os.environ.get("TTS_AUDIO_SUITE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return comfyui_root() / "custom_nodes" / "TTS-Audio-Suite"


def _relative_or_name(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _reference_transcript(audio_path: Path) -> Path | None:
    preferred = audio_path.with_name(f"{audio_path.stem}.reference.txt")
    fallback = audio_path.with_suffix(".txt")
    if preferred.is_file() and preferred.read_text(encoding="utf-8", errors="replace").strip():
        return preferred
    if fallback.is_file() and fallback.read_text(encoding="utf-8", errors="replace").strip():
        return fallback
    return None


def voice_roots() -> list[tuple[str, Path, bool]]:
    root = comfyui_root()
    return [
        ("user", root / "models" / "voices", True),
        ("tts-user", root / "models" / "TTS" / "voices", True),
        ("bundled", tts_suite_root() / "voices_examples", False),
    ]


def user_voice_root() -> Path:
    return comfyui_root() / "models" / "voices"


def install_reference_voice(*, name: str, filename: str, audio: bytes, transcript: str) -> dict[str, Any]:
    clean_name = name.strip()
    if not VOICE_NAME_RE.fullmatch(clean_name):
        raise ValueError("Voice name must be 1-80 characters using letters, numbers, spaces, dot, underscore, or hyphen")
    suffix = Path(filename).suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        raise ValueError(f"Unsupported reference audio type: {suffix or 'missing extension'}")
    exact_text = transcript.strip()
    if not exact_text:
        raise ValueError("An exact non-empty transcript is required")
    if not audio:
        raise ValueError("Reference audio is empty")

    root = user_voice_root()
    root.mkdir(parents=True, exist_ok=True)
    audio_target = root / f"{clean_name}{suffix}"
    transcript_target = root / f"{clean_name}.reference.txt"
    if audio_target.exists() or transcript_target.exists():
        raise FileExistsError(f"A reference voice named '{clean_name}' already exists")

    with tempfile.NamedTemporaryFile(dir=root, prefix=".voice-", suffix=suffix, delete=False) as staged_audio:
        staged_audio.write(audio)
        staged_audio_path = Path(staged_audio.name)
    with tempfile.NamedTemporaryFile(dir=root, prefix=".voice-", suffix=".txt", mode="w", encoding="utf-8", delete=False) as staged_text:
        staged_text.write(exact_text + "\n")
        staged_text_path = Path(staged_text.name)
    try:
        os.replace(staged_audio_path, audio_target)
        os.replace(staged_text_path, transcript_target)
    except Exception:
        staged_audio_path.unlink(missing_ok=True)
        staged_text_path.unlink(missing_ok=True)
        audio_target.unlink(missing_ok=True)
        transcript_target.unlink(missing_ok=True)
        raise
    return {
        "name": clean_name,
        "audio_path": str(audio_target),
        "transcript_path": str(transcript_target),
        "refresh_required": True,
        "restart_required": False,
    }


def comfy_voice_key(voice: dict[str, Any]) -> str:
    relative = str(voice["relative_path"]).replace("\\", "/").strip("/")
    if voice["source"] == "bundled":
        return f"voices_examples/{relative}"
    if voice["source"] == "tts-user":
        return f"TTS/voices/{relative}"
    return relative


def refresh_live_voice_catalog(*, comfy_url: str, expected_voice_id: str | None = None) -> dict[str, Any]:
    """Trigger the suite's INPUT_TYPES refresh and compare its live dropdown."""
    try:
        with urllib.request.urlopen(f"{comfy_url.rstrip('/')}/object_info/CharacterVoicesNode", timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not refresh live voice discovery at {comfy_url}") from exc
    node = payload.get("CharacterVoicesNode") or {}
    spec = node.get("input", {}).get("required", {}).get("voice_name", [])
    live_values = spec[0] if spec and isinstance(spec[0], list) else []
    catalog = discover_voices()
    live_set = {str(value) for value in live_values}
    discovered_ids = [voice["id"] for voice in catalog if voice.get("discoverable") and comfy_voice_key(voice) in live_set]
    expected = next((voice for voice in catalog if voice["id"] == expected_voice_id), None) if expected_voice_id else None
    expected_key = comfy_voice_key(expected) if expected else None
    expected_discovered = expected_key in live_set if expected_key else None
    return {
        "refreshed": True,
        "live_count": len([value for value in live_values if value != "none"]),
        "catalog_count": len([voice for voice in catalog if voice.get("discoverable")]),
        "live_values": live_values,
        "discovered_voice_ids": discovered_ids,
        "expected_voice_id": expected_voice_id,
        "expected_voice_key": expected_key,
        "expected_discovered": expected_discovered,
        "restart_required": expected_discovered is False,
    }


def discover_voices() -> list[dict[str, Any]]:
    voices: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for source, root, writable in voice_roots():
        if not root.is_dir():
            continue
        for audio_path in sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS):
            resolved = audio_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            transcript = _reference_transcript(audio_path)
            voices.append(
                {
                    "id": f"{source}:{_relative_or_name(audio_path, root)}",
                    "name": audio_path.stem,
                    "source": source,
                    "relative_path": _relative_or_name(audio_path, root),
                    "audio_path": str(audio_path),
                    "transcript_path": str(transcript) if transcript else None,
                    "has_transcript": transcript is not None,
                    "discoverable": transcript is not None,
                    "user_managed": writable,
                }
            )
    return voices


def discover_models() -> list[dict[str, Any]]:
    models_root = comfyui_root() / "models" / "TTS"
    if not models_root.is_dir():
        return []
    models: list[dict[str, Any]] = []
    for family in sorted(path for path in models_root.iterdir() if path.is_dir() and path.name != "voices"):
        candidates = sorted(path for path in family.iterdir() if path.is_dir())
        if not candidates:
            candidates = [family]
        for candidate in candidates:
            artifacts = [
                path for path in candidate.rglob("*") if path.is_file() and path.suffix.lower() in MODEL_EXTENSIONS
            ]
            if not artifacts and candidate != family:
                # Some Hugging Face model directories use non-checkpoint assets; keep the
                # directory visible if it contains any files at all.
                artifacts = [path for path in candidate.rglob("*") if path.is_file()]
            if not artifacts:
                continue
            supported_f5 = family.name == "F5-TTS" and candidate.name in {"F5TTS_v1_Base", "F5TTS_Base", "E2TTS_Base"}
            models.append(
                {
                    "id": _relative_or_name(candidate, models_root),
                    "family": family.name,
                    "name": candidate.name,
                    "path": str(candidate),
                    "artifact_count": len(artifacts),
                    "finetune_status": "local-preparation" if supported_f5 else "unverified",
                    "aarch64_status": "preflight-required" if supported_f5 else "unverified",
                    "one_shot_reference": family.name in {"F5-TTS", "ChatterBox", "CosyVoice", "IndexTTS"},
                }
            )
    return models


def audio_blocks() -> list[dict[str, Any]]:
    return [
        {"id": "voice_library", "label": "Voice Library", "phase": 1, "status": "available", "executor": "backend"},
        {"id": "character_map", "label": "Character Map", "phase": 1, "status": "available", "executor": "backend"},
        {"id": "tts_multichar_timed", "label": "Timed Multi-Character TTS", "phase": 2, "status": "available", "executor": "comfyui"},
        {"id": "voice_discovery_live", "label": "Live Voice Discovery", "phase": 3, "status": "available", "executor": "backend"},
        {"id": "finetune", "label": "F5 Dataset Preparation", "phase": 4, "status": "available", "executor": "training"},
        {"id": "split", "label": "Split Audio", "phase": 5, "status": "available", "executor": "python"},
        {"id": "stitch", "label": "Stitch Audio", "phase": 5, "status": "available", "executor": "python"},
        {"id": "voice_repair", "label": "Voice Repair", "phase": 6, "status": "available", "executor": "comfyui"},
        {"id": "voice_changer", "label": "Voice Changer", "phase": 7, "status": "available", "executor": "comfyui"},
        {"id": "rvc_voice_pitch", "label": "RVC Voice/Pitch", "phase": 7, "status": "available", "executor": "comfyui"},
        {"id": "emotion", "label": "Emotion Change", "phase": 8, "status": "available", "executor": "comfyui"},
        {"id": "style", "label": "Style Change", "phase": 8, "status": "available", "executor": "comfyui"},
        {"id": "export", "label": "Pipeline and Export", "phase": 9, "status": "planned", "executor": "backend"},
    ]


def system_architecture() -> dict[str, Any]:
    return {
        "machine": platform.machine(),
        "platform": platform.platform(),
        "is_aarch64": platform.machine().lower() in {"aarch64", "arm64"},
    }
