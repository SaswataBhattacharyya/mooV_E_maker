"""Versioned production-style prompt packs used by automation runs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STYLE_ROOT = ROOT / "prompts" / "styles"
REQUIRED_STAGES = ("story", "scene_direction", "image", "audio", "video", "review")


def _validate(payload: dict[str, Any], source: Path) -> dict[str, Any]:
    missing = [key for key in ("style_id", "name", "version", "stages") if key not in payload]
    if missing:
        raise ValueError(f"{source.name}: missing {', '.join(missing)}")
    stages = payload.get("stages")
    if not isinstance(stages, dict) or any(key not in stages or not str(stages[key]).strip() for key in REQUIRED_STAGES):
        raise ValueError(f"{source.name}: stages must include {', '.join(REQUIRED_STAGES)}")
    return payload


def list_styles() -> list[dict[str, Any]]:
    results = []
    for path in sorted(STYLE_ROOT.glob("*.json")):
        try:
            results.append(_validate(json.loads(path.read_text(encoding="utf-8")), path))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return results


def get_style(style_id: str) -> dict[str, Any]:
    match = next((item for item in list_styles() if item.get("style_id") == style_id), None)
    if match is None:
        raise KeyError(style_id)
    return match
