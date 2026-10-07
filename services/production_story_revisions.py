"""Atomic, run-scoped story canon revisions for production V2."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any


def revision_root(output_root: Path, project_id: str, run_id: str) -> Path:
    """Resolve a validated project/run path beneath the generated-output root."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", project_id):
        raise ValueError("Invalid project identifier for story revision storage.")
    try:
        canonical_run_id = str(uuid.UUID(run_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Invalid UUID run identifier for story revision storage.") from exc
    if canonical_run_id != run_id.lower():
        raise ValueError("Run identifier must use canonical UUID form.")
    root = output_root.resolve()
    target = (root / project_id / "production_v2" / "runs" / canonical_run_id / "story" / "revisions").resolve()
    if not target.is_relative_to(root):
        raise ValueError("Story revision path escapes the project output root.")
    return target


def write_revision(output_root: Path, project_id: str, run_id: str,
                   revision: dict[str, Any]) -> Path:
    if not isinstance(revision, dict) or not revision.get("revision_id"):
        raise ValueError("A revision object with revision_id is required.")
    if not re.fullmatch(r"story-canon-[a-f0-9]{12}", str(revision["revision_id"])):
        raise ValueError("Story revision ID has an invalid format.")
    directory = revision_root(output_root, project_id, run_id)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{revision['revision_id']}.json"
    encoded = json.dumps(revision, ensure_ascii=False, indent=2).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".story-revision-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return destination


def load_revision(output_root: Path, project_id: str, run_id: str,
                  revision_id: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"story-canon-[a-f0-9]{12}", revision_id):
        return None
    path = revision_root(output_root, project_id, run_id) / f"{revision_id}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(value, dict) or value.get("revision_id") != revision_id:
        raise ValueError("Stored story revision has invalid identity or shape.")
    return value


def list_revisions(output_root: Path, project_id: str, run_id: str) -> list[dict[str, Any]]:
    directory = revision_root(output_root, project_id, run_id)
    if not directory.is_dir():
        return []
    revisions: list[dict[str, Any]] = []
    for path in sorted(directory.glob("story-canon-*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("revision_id") == path.stem:
            revisions.append(value)
    return revisions


def write_stage_revision(output_root: Path, project_id: str, run_id: str,
                         stage: str, revision: dict[str, Any]) -> Path:
    if stage not in {"scenes", "dialogue", "visual_briefs", "shot_plans"}:
        raise ValueError("Unsupported production text stage.")
    revision_id = str(revision.get("revision_id") or "")
    if not re.fullmatch(rf"{re.escape(stage)}-[a-f0-9]{{12}}", revision_id):
        raise ValueError("Stage revision ID does not match its stage.")
    directory = revision_root(output_root, project_id, run_id) / stage
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{revision_id}.json"
    encoded = json.dumps(revision, ensure_ascii=False, indent=2).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{stage}-revision-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return destination


def load_stage_revision(output_root: Path, project_id: str, run_id: str,
                        stage: str, revision_id: str) -> dict[str, Any] | None:
    if stage not in {"scenes", "dialogue", "visual_briefs", "shot_plans"}:
        raise ValueError("Unsupported production text stage.")
    if not re.fullmatch(rf"{re.escape(stage)}-[a-f0-9]{{12}}", revision_id):
        return None
    path = revision_root(output_root, project_id, run_id) / stage / f"{revision_id}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(value, dict) or value.get("revision_id") != revision_id:
        raise ValueError("Stored production stage revision has invalid identity or shape.")
    return value


def list_stage_revisions(output_root: Path, project_id: str, run_id: str,
                         stage: str) -> list[dict[str, Any]]:
    if stage not in {"scenes", "dialogue", "visual_briefs", "shot_plans"}:
        raise ValueError("Unsupported production text stage.")
    directory = revision_root(output_root, project_id, run_id) / stage
    if not directory.is_dir():
        return []
    revisions: list[dict[str, Any]] = []
    for path in sorted(directory.glob(f"{stage}-*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if (isinstance(value, dict) and value.get("revision_id") == path.stem
                and re.fullmatch(rf"{re.escape(stage)}-[a-f0-9]{{12}}", path.stem)):
            revisions.append(value)
    return revisions
