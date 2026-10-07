from __future__ import annotations

import json
import re
from dataclasses import is_dataclass, asdict
from pathlib import Path
from typing import Any


def sanitize_name(value: str) -> str:
    value = value.strip().replace(" ", "_")
    value = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    return re.sub(r"_+", "_", value).strip("._") or "video"


def seconds_to_hms(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def make_json_safe(payload: Any) -> Any:
    if isinstance(payload, Path):
        return str(payload)
    if is_dataclass(payload):
        return make_json_safe(asdict(payload))
    if isinstance(payload, dict):
        return {str(key): make_json_safe(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple, set)):
        return [make_json_safe(item) for item in payload]
    return payload


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(make_json_safe(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def dump_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
