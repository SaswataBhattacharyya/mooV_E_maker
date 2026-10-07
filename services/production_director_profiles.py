"""Versioned Director behavior profiles, separate from narrative prompt styles."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "prompts" / "director_profiles" / "production_types_v1.json"
REQUIRED_KEYS = ("display_name", "purpose", "behavior", "review_priorities")


class DirectorProfileError(ValueError):
    """A production type has no valid, versioned Director behavior profile."""


def load_registry(path: Path | None = None) -> dict[str, Any]:
    source = Path(path or PROFILE_PATH)
    try:
        registry = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DirectorProfileError(f"Could not load Director profile registry: {exc}") from exc
    profiles = registry.get("profiles")
    if not registry.get("version") or not isinstance(profiles, dict) or not profiles:
        raise DirectorProfileError("Director profile registry requires a version and non-empty profiles object.")
    for profile_id, profile in profiles.items():
        missing = [key for key in REQUIRED_KEYS if key not in profile]
        if missing or any(not str(profile[key]).strip() for key in REQUIRED_KEYS[:2]):
            raise DirectorProfileError(f"Director profile {profile_id!r} is missing valid fields: {missing or 'empty required text'}.")
        for field in ("behavior", "review_priorities"):
            if not isinstance(profile[field], list) or not profile[field] or any(not isinstance(item, str) or not item.strip() for item in profile[field]):
                raise DirectorProfileError(f"Director profile {profile_id!r} field {field} must be a non-empty list of strings.")
    canonical = json.dumps(registry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**registry, "content_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def resolve_profile(production_type: str, *, path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(path)
    profile = registry["profiles"].get(production_type)
    if profile is None:
        raise DirectorProfileError(f"Unknown production type {production_type!r}; choose one of {', '.join(sorted(registry['profiles']))}.")
    return {"production_type": production_type, "profile_version": registry["version"],
            "registry_hash": registry["content_hash"], **profile}
