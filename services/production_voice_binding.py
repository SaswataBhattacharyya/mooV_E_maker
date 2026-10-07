"""Project-scoped voice selection and stable speaker binding (no cloning)."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import random
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from .production_authority import director_controls


class VoiceBindingError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


def _path(storage_root: Path, project_id: str) -> Path:
    if not project_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in project_id):
        raise VoiceBindingError("invalid_project_id", "Project identifier has an invalid format.")
    root = Path(storage_root).resolve()
    target = (root / project_id / "production" / "voice_bindings.json").resolve()
    if not target.is_relative_to(root):
        raise VoiceBindingError("unsafe_project_path", "Voice-binding path escapes the configured project root.")
    return target


def _load(path: Path, project_id: str) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "project_id": project_id, "revision": 0, "bindings": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VoiceBindingError("voice_bindings_corrupt", f"Voice binding store could not be read: {exc}") from exc
    if data.get("schema_version") != 1 or data.get("project_id") != project_id or not isinstance(data.get("bindings"), list):
        raise VoiceBindingError("voice_bindings_invalid", "Voice binding store has an unsupported schema.")
    return data


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".voice-bindings-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def eligible_voice_pool(assets: list[Mapping[str, Any]], *, min_seconds: float = 30.0) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for asset in assets:
        asset_id = str(asset.get("asset_id", ""))
        reason = None
        if asset.get("kind") != "audio":
            reason = "not_audio"
        elif "voice_master" not in asset.get("roles", []):
            reason = "not_voice_master"
        else:
            media = asset.get("media") if isinstance(asset.get("media"), dict) else {}
            duration = media.get("duration_seconds")
            if not isinstance(duration, (int, float)) or duration < min_seconds:
                reason = "voice_master_too_short_or_unprobed"
            elif asset.get("source", "").startswith("external_"):
                reason = "external_voice_not_eligible_for_automatic_binding"
        if reason is None and (asset.get("metadata") or {}).get("approval_status", "accepted") != "accepted":
            reason = "not_accepted"
        if reason:
            excluded.append({"asset_id": asset_id, "reason": reason})
        else:
            eligible.append({"asset_id": asset_id, "sha256": str(asset.get("sha256", "")),
                             "duration_seconds": float(asset["media"]["duration_seconds"]),
                             "roles": list(asset.get("roles", [])),
                             "approval_status": (asset.get("metadata") or {}).get("approval_status", "accepted")})
    return eligible, excluded


def bind_voice(storage_root: Path, project_id: str, *, run_id: str, character_id: str,
               control_mode: str, strategy: str, asset_id: str | None,
               assets: list[Mapping[str, Any]], get_asset: Callable[[str], Mapping[str, Any]],
               min_seconds: float = 30.0, semi_gates: Mapping[str, bool] | None = None) -> dict[str, Any]:
    try:
        canonical_run = str(uuid.UUID(run_id))
        canonical_character = str(uuid.UUID(character_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise VoiceBindingError("identity_invalid", "run_id and character_id must be UUIDs.") from exc
    if canonical_run != run_id.lower() or canonical_character != character_id.lower():
        raise VoiceBindingError("identity_invalid", "run_id and character_id must use canonical UUID form.")
    if strategy not in {"manual", "seeded_random"}:
        raise VoiceBindingError("voice_strategy_invalid", "Voice strategy must be manual or seeded_random.")
    automatic = director_controls({"control_mode": control_mode, "semi_gates": semi_gates or {}}, "voice_selection")
    if strategy == "seeded_random" and not automatic:
        raise VoiceBindingError("voice_strategy_forbidden", "Seeded random voice choice is reserved for Fully automated mode.")
    if strategy == "manual" and automatic:
        raise VoiceBindingError("voice_strategy_forbidden", "Fully automated mode must use the saved seeded-random voice policy.")
    eligible, excluded = eligible_voice_pool(assets, min_seconds=min_seconds)
    if not eligible:
        raise VoiceBindingError("eligible_voice_pool_empty", "No accepted project voice master meets the minimum duration.",
                                details={"minimum_seconds": min_seconds, "excluded": excluded})
    pool_hash = hashlib.sha256(json.dumps(eligible, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if strategy == "manual":
        selected = next((row for row in eligible if row["asset_id"] == asset_id), None)
        if selected is None:
            raise VoiceBindingError("voice_asset_ineligible", "Selected voice is not an accepted, eligible project voice master.",
                                    details={"asset_id": asset_id, "minimum_seconds": min_seconds})
        seed = None
        reason = "user_selected"
    else:
        seed = int(hashlib.sha256(f"{canonical_run}:{canonical_character}:{pool_hash}".encode()).hexdigest()[:16], 16)
        selected = random.Random(seed).choice(sorted(eligible, key=lambda row: row["asset_id"]))
        reason = "reproducible_random_from_project_pool"
    path = _path(storage_root, project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / ".voice-bindings.lock").open("a+b") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        try:
            data = _load(path, project_id)
            existing = next((row for row in data["bindings"] if row.get("run_id") == canonical_run
                             and row.get("character_id") == canonical_character), None)
            if existing:
                same_choice = (existing.get("strategy") == strategy
                    and existing.get("eligible_pool_hash") == pool_hash
                    and (strategy == "seeded_random" or existing.get("voice_asset_id") == selected["asset_id"]))
                if same_choice:
                    return {**existing, "reused": True}
                raise VoiceBindingError("voice_binding_exists", "This character already has a voice binding in this run; explicitly revise it instead of silently rerolling.")
            record = get_asset(selected["asset_id"])
            # Keep the binding as an ID only; no media bytes or absolute paths enter the store.
            speaker = f"S{1 + len({row.get('speaker_id') for row in data['bindings'] if row.get('run_id') == canonical_run})}"
            binding = {"binding_id": f"voice-binding-{uuid.uuid4().hex[:16]}", "run_id": canonical_run,
                "character_id": canonical_character, "speaker_id": speaker,
                "voice_asset_id": selected["asset_id"], "voice_asset_hash": selected["sha256"],
                "source_project_id": project_id, "strategy": strategy, "seed": seed,
                "eligible_pool_hash": pool_hash, "eligible_asset_ids": [row["asset_id"] for row in eligible],
                "excluded_assets": excluded, "decision_reason": reason,
                "h3_reference_excerpt_required": True, "master_duration_seconds": selected["duration_seconds"],
                "created_at": datetime.now(timezone.utc).isoformat(), "asset_verified": bool(record)}
            data["bindings"].append(binding)
            data["revision"] = int(data["revision"]) + 1
            _atomic_json(path, data)
            return {**binding, "reused": False}
        finally:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)


def list_voice_bindings(storage_root: Path, project_id: str, *, run_id: str | None = None) -> dict[str, Any]:
    path = _path(storage_root, project_id)
    data = _load(path, project_id)
    rows = data["bindings"]
    if run_id is not None:
        try:
            run_id = str(uuid.UUID(run_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise VoiceBindingError("identity_invalid", "run_id must be a UUID.") from exc
        rows = [row for row in rows if row.get("run_id") == run_id]
    return {"project_id": project_id, "revision": data["revision"], "bindings": rows}
