"""Project-scoped, revisioned character and world canon for production V2.

This is text metadata only. Generated/imported media stays in the asset/output
stores and is referenced by stable IDs so the canon never creates duplicate
media copies.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WorldStateError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


def _root(storage_projects_root: Path, project_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", project_id):
        raise WorldStateError("invalid_project_id", "Project identifier has an invalid format.")
    root = Path(storage_projects_root).resolve()
    target = (root / project_id / "production").resolve()
    if not target.is_relative_to(root):
        raise WorldStateError("unsafe_project_path", "Project canon path escapes the configured root.")
    return target


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".production-canon-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _empty(project_id: str) -> dict[str, Any]:
    return {"schema_version": 1, "project_id": project_id, "revision": 0,
            "characters": [], "worlds": [], "updated_at": None, "content_hash": None}


def read_project_canon(storage_projects_root: Path, project_id: str) -> dict[str, Any]:
    path = _root(storage_projects_root, project_id) / "canon.json"
    if not path.exists():
        return _empty(project_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorldStateError("canon_corrupt", f"Project canon could not be read: {exc}") from exc
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or data.get("project_id") != project_id or not isinstance(data.get("characters"), list)
            or not isinstance(data.get("worlds"), list) or not isinstance(data.get("revision"), int)):
        raise WorldStateError("canon_invalid", "Project canon has an unsupported or invalid schema.")
    return data


def _validate_rows(rows: Any, *, kind: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or len(rows) > 500:
        raise WorldStateError("canon_rows_invalid", f"{kind} must be a list with at most 500 records.")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise WorldStateError("canon_record_invalid", f"Each {kind[:-1]} record must be an object.")
        identity_key = "character_id" if kind == "characters" else "world_id"
        try:
            identity = str(uuid.UUID(str(row.get(identity_key, ""))))
        except (ValueError, TypeError, AttributeError) as exc:
            raise WorldStateError("canon_id_invalid", f"{identity_key} must be a UUID.") from exc
        if identity in seen:
            raise WorldStateError("canon_id_duplicate", f"Duplicate {identity_key} in project canon.")
        seen.add(identity)
        label = str(row.get("display_name") or "").strip()
        if not label or len(label) > 120:
            raise WorldStateError("canon_name_invalid", f"{identity_key} requires a display name of 1–120 characters.")
        if any(existing.get("display_name", "").casefold() == label.casefold() for existing in result):
            raise WorldStateError("canon_name_duplicate", f"{kind} display names must be unique within a project.")
        description = str(row.get("description") or "").strip()
        if len(description) > 12000:
            raise WorldStateError("canon_description_too_long", f"{identity_key} description exceeds 12000 characters.")
        evidence = row.get("evidence", [])
        if not isinstance(evidence, list) or len(evidence) > 100 or any(not isinstance(x, dict) for x in evidence):
            raise WorldStateError("canon_evidence_invalid", "Evidence must be a list of at most 100 structured records.")
        safe_row = {identity_key: identity, "display_name": label, "description": description,
                    "evidence": evidence, "status": row.get("status", "active")}
        if safe_row["status"] not in {"active", "archived"}:
            raise WorldStateError("canon_status_invalid", "Canon status must be active or archived.")
        if kind == "characters":
            safe_row["aliases"] = _string_list(row.get("aliases", []), "aliases")
            safe_row["appearance"] = str(row.get("appearance") or "")[:12000]
            safe_row["voice_brief"] = str(row.get("voice_brief") or "")[:4000]
        else:
            safe_row["visual_rules"] = str(row.get("visual_rules") or "")[:12000]
            safe_row["locations"] = _string_list(row.get("locations", []), "locations")
        result.append(safe_row)
    return result


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 100:
        raise WorldStateError("canon_field_invalid", f"{label} must be a list with at most 100 items.")
    result = []
    for item in value:
        if not isinstance(item, str) or len(item) > 500:
            raise WorldStateError("canon_field_invalid", f"Each {label} item must be text up to 500 characters.")
        result.append(item.strip())
    return result


def save_project_canon(storage_projects_root: Path, project_id: str, *, expected_revision: int,
                       characters: Any, worlds: Any, source_story_revision: str | None = None,
                       actor: str = "user") -> dict[str, Any]:
    production_root = _root(storage_projects_root, project_id)
    production_root.mkdir(parents=True, exist_ok=True)
    with (production_root / ".canon.lock").open("a+b") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        try:
            return _save_project_canon_locked(storage_projects_root, project_id,
                expected_revision=expected_revision, characters=characters, worlds=worlds,
                source_story_revision=source_story_revision, actor=actor)
        finally:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)


def _save_project_canon_locked(storage_projects_root: Path, project_id: str, *, expected_revision: int,
                               characters: Any, worlds: Any, source_story_revision: str | None,
                               actor: str) -> dict[str, Any]:
    current = read_project_canon(storage_projects_root, project_id)
    if expected_revision != current["revision"]:
        raise WorldStateError("canon_revision_conflict", "Project canon changed; reload it before saving.")
    character_rows = _validate_rows(characters, kind="characters")
    world_rows = _validate_rows(worlds, kind="worlds")
    # Existing IDs are authoritative. Saving may rename or archive a record,
    # but may not silently erase one or replace its immutable identity.
    old_characters = {row["character_id"]: row for row in current["characters"]}
    old_worlds = {row["world_id"]: row for row in current["worlds"]}
    new_characters = {row["character_id"]: row for row in character_rows}
    new_worlds = {row["world_id"]: row for row in world_rows}
    if not set(old_characters).issubset(new_characters) or not set(old_worlds).issubset(new_worlds):
        raise WorldStateError("canon_identity_removal", "Existing character/world IDs cannot be removed; archive them instead.")
    stamp = datetime.now(timezone.utc).isoformat()
    next_revision = current["revision"] + 1
    body = {"schema_version": 1, "project_id": project_id, "revision": next_revision,
            "source_story_revision": source_story_revision,
            "characters": character_rows, "worlds": world_rows, "updated_at": stamp, "updated_by": actor}
    body["content_hash"] = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                                      separators=(",", ":")).encode()).hexdigest()
    production_root = _root(storage_projects_root, project_id)
    _atomic_json(production_root / "canon.json", body)
    revision_name = f"canon-r{next_revision:06d}-{body['content_hash'][:12]}.json"
    _atomic_json(production_root / "canon_revisions" / revision_name, body)
    return body


def create_anonymous_character(display_name: str | None = None) -> dict[str, Any]:
    identity = str(uuid.uuid4())
    return {"character_id": identity, "display_name": display_name or f"Character-{identity.replace('-', '')[:4].upper()}",
            "description": "", "appearance": "", "voice_brief": "", "aliases": [], "evidence": [], "status": "active"}


def create_world(display_name: str, description: str = "") -> dict[str, Any]:
    return {"world_id": str(uuid.uuid4()), "display_name": display_name, "description": description,
            "visual_rules": "", "locations": [], "evidence": [], "status": "active"}
