"""Validation for scanner-safe Hermes media requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class RequestError(ValueError):
    """Raised when a request is unsafe or incomplete."""


@dataclass(frozen=True)
class MediaRequest:
    workflow: str
    prompt: str
    negative_prompt: str = ""
    input_images: list[Path] = field(default_factory=list)
    input_videos: list[Path] = field(default_factory=list)
    input_audio: list[Path] = field(default_factory=list)
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    seed: int | None = None
    count: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaRequest":
        if not isinstance(data, dict):
            raise RequestError("Request must be a JSON object")
        workflow = str(data.get("workflow", "")).strip()
        prompt = str(data.get("prompt", "")).strip()
        if not workflow:
            raise RequestError("workflow is required")
        if not prompt:
            raise RequestError("prompt is required")
        count = int(data.get("count", 1))
        if count < 1 or count > 8:
            raise RequestError("count must be between 1 and 8")
        width = _optional_int(data, "width")
        height = _optional_int(data, "height")
        if width is not None and (width < 64 or width > 4096 or width % 8):
            raise RequestError("width must be 64..4096 and divisible by 8")
        if height is not None and (height < 64 or height > 4096 or height % 8):
            raise RequestError("height must be 64..4096 and divisible by 8")
        duration = float(data["duration"]) if data.get("duration") is not None else None
        if duration is not None and not 1 <= duration <= 30:
            raise RequestError("duration must be between 1 and 30 seconds")
        return cls(
            workflow=workflow,
            prompt=prompt,
            negative_prompt=str(data.get("negative_prompt", "")).strip(),
            input_images=_paths(data.get("input_images", []), "input_images"),
            input_videos=_paths(data.get("input_videos", []), "input_videos"),
            input_audio=_paths(data.get("input_audio", []), "input_audio"),
            width=width,
            height=height,
            duration=duration,
            seed=_optional_int(data, "seed"),
            count=count,
        )


def _optional_int(data: dict[str, Any], key: str) -> int | None:
    return int(data[key]) if data.get(key) is not None else None


def _paths(values: Any, key: str) -> list[Path]:
    if not isinstance(values, list):
        raise RequestError(f"{key} must be an array")
    paths = [Path(str(value)).expanduser().resolve() for value in values]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise RequestError(f"Missing {key}: {', '.join(missing)}")
    return paths
