"""Project-owned dialogue reconstruction maps, parts, and immutable takes."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ReconstructionError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root(project_dir: Path) -> Path:
    path = project_dir / "audio" / "reconstruct"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path(project_dir: Path) -> Path:
    return _root(project_dir) / "session.json"


def _read(project_dir: Path) -> dict[str, Any]:
    path = _state_path(project_dir)
    if not path.exists():
        return {"version": 1, "characters": [], "parts": [], "takes": [], "updated_at": _now()}
    return json.loads(path.read_text(encoding="utf-8"))


def _write(project_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    state["updated_at"] = _now()
    path = _state_path(project_dir)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return state


def session(project_dir: Path) -> dict[str, Any]:
    return _read(project_dir)


def calibrate(project_dir: Path, character_name: str, sentence: str, settings: dict[str, Any]) -> dict[str, Any]:
    name = character_name.strip()
    if not name:
        raise ReconstructionError("Character name is required")
    if not sentence.strip():
        raise ReconstructionError("Calibration sentence is required")
    state = _read(project_dir)
    row = next((item for item in state["characters"] if item["name"].casefold() == name.casefold()), None)
    if row is None:
        row = {"character_id": f"recon-char-{uuid.uuid4().hex[:10]}", "name": name}
        state["characters"].append(row)
    row.update({"calibration_sentence": sentence.strip(), "voice_settings": settings, "status": "calibrated", "updated_at": _now()})
    return _write(project_dir, state)


def add_part(project_dir: Path, part_id: str, character_name: str, sequence: int, expected_text: str) -> dict[str, Any]:
    if not part_id.strip() or sequence < 1 or not expected_text.strip():
        raise ReconstructionError("part_id, positive sequence, and expected_text are required")
    state = _read(project_dir)
    if not any(item["name"].casefold() == character_name.strip().casefold() and item.get("status") == "calibrated" for item in state["characters"]):
        raise ReconstructionError("Calibrate the character before recording dialogue")
    existing = next((item for item in state["parts"] if item["part_id"] == part_id), None)
    if existing is None:
        existing = {"part_id": part_id, "character_name": character_name.strip(), "sequence": sequence, "expected_text": expected_text.strip(), "accepted_take_id": None}
        state["parts"].append(existing)
    else:
        existing.update(character_name=character_name.strip(), sequence=sequence, expected_text=expected_text.strip())
    _write(project_dir, state)
    return existing


def add_take(project_dir: Path, part_id: str, filename: str, content: bytes, transcript: str = "") -> dict[str, Any]:
    if not content:
        raise ReconstructionError("Recording is empty")
    state = _read(project_dir)
    part = next((item for item in state["parts"] if item["part_id"] == part_id), None)
    if part is None:
        raise ReconstructionError("Unknown reconstruction part")
    count = sum(1 for item in state["takes"] if item["part_id"] == part_id) + 1
    safe_stem = f"{part['character_name']}_{part['sequence']}".replace(" ", "_")
    take_id = f"{part_id}_take_{count:03d}"
    directory = _root(project_dir) / "takes"
    directory.mkdir(parents=True, exist_ok=True)
    raw_path = directory / f"{safe_stem}_take_{count:03d}{Path(filename or 'recording.wav').suffix.lower() or '.wav'}"
    raw_path.write_bytes(content)
    row = {"take_id": take_id, "part_id": part_id, "sequence": part["sequence"], "character_name": part["character_name"], "raw_path": str(raw_path.relative_to(project_dir)), "transcript": transcript, "status": "raw", "created_at": _now()}
    state["takes"].append(row)
    _write(project_dir, state)
    return row


def accept_take(project_dir: Path, part_id: str, take_id: str) -> dict[str, Any]:
    state = _read(project_dir)
    part = next((item for item in state["parts"] if item["part_id"] == part_id), None)
    take = next((item for item in state["takes"] if item["take_id"] == take_id and item["part_id"] == part_id), None)
    if part is None or take is None:
        raise ReconstructionError("Part or take not found")
    source = project_dir / take["raw_path"]
    accepted_dir = _root(project_dir) / "accepted"
    accepted_dir.mkdir(parents=True, exist_ok=True)
    accepted = accepted_dir / f"{take['character_name'].replace(' ', '_')}_{take['sequence']}{source.suffix}"
    shutil.copy2(source, accepted)
    take["status"] = "accepted"
    part["accepted_take_id"] = take_id
    part["accepted_path"] = str(accepted.relative_to(project_dir))
    _write(project_dir, state)
    return {"part": part, "take": take, "session": state}
