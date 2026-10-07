"""Isolated Demucs source-separation adapter."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any


def separate(audio_path: Path, output_dir: Path, mode: str, auto_music_detected: bool,
             *, auto_voice_requested: bool = False) -> dict[str, Any]:
    """Separate vocals/accompaniment while retaining the original mix.

    Demucs does not classify arbitrary SFX. Its `vocals` and `no_vocals`
    (or `drums`/`bass`/`other`) stems are source-separation outputs, not
    semantic labels such as dialogue, music, thunder, or footsteps.
    """
    raw_mode = (mode or "AUTO").strip().lower().replace("_", "-")
    aliases = {"off": "OFF", "auto": "AUTO", "2": "2-STEM", "2-stem": "2-STEM",
               "4": "4-STEM", "4-stem": "4-STEM", "6": "6-STEM", "6-stem": "6-STEM"}
    mode = aliases.get(raw_mode, "AUTO")
    result: dict[str, Any] = {"status": "disabled" if mode == "OFF" else "unavailable", "backend": "demucs", "mode": mode, "outputs": []}
    if mode == "OFF":
        return result
    if mode == "AUTO" and not (auto_music_detected or auto_voice_requested):
        result.update({"status": "not_requested", "reason": "AUTO found no music or opted-in voice passage requiring stems"})
        return result
    if importlib.util.find_spec("demucs") is None:
        result["reason"] = "demucs runtime is not installed in the isolated worker"
        return result
    model = "htdemucs_6s" if mode == "6-STEM" else "htdemucs"
    output_dir.mkdir(parents=True, exist_ok=True)
    command = ["python", "-m", "demucs.separate", "-n", model, "-o", str(output_dir), str(audio_path)]
    # AUTO chooses the cheaper two-stem vocal/accompaniment split. Explicit
    # 4/6-stem modes produce their model-defined instrument stems.
    if mode in {"AUTO", "2-STEM"}:
        command.extend(["--two-stems", "vocals"])
    try:
        completed = subprocess.run(command, check=True, text=True, capture_output=True)
        files = sorted(str(path) for path in output_dir.rglob("*.wav"))
        result.update({"status": "completed", "model": model, "outputs": files,
                       "stem_semantics": "vocals_vs_accompaniment" if mode in {"AUTO", "2-STEM"} else "model_source_stems",
                       "stdout_tail": completed.stdout[-1000:]})
    except Exception as exc:
        result["reason"] = str(exc)
    return result
