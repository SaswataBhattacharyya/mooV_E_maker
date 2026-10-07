"""Run-scoped, atomic storage for non-mutating H3 Refine proposals."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from story_builder.services.production_story_revisions import revision_root


def _root(output_root: Path, project_id: str, run_id: str) -> Path:
    return revision_root(output_root, project_id, run_id) / "refine_proposals"


def write_proposal(output_root: Path, project_id: str, run_id: str,
                   proposal: dict[str, Any]) -> Path:
    proposal_id = str(proposal.get("proposal_id", ""))
    if not re.fullmatch(r"refine-[a-f0-9]{12}", proposal_id):
        raise ValueError("Refine proposal has an invalid ID.")
    directory = _root(output_root, project_id, run_id)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{proposal_id}.json"
    descriptor, temp_name = tempfile.mkstemp(prefix=".refine-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(proposal, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, destination)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return destination


def load_proposal(output_root: Path, project_id: str, run_id: str,
                  proposal_id: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"refine-[a-f0-9]{12}", proposal_id):
        return None
    path = _root(output_root, project_id, run_id) / f"{proposal_id}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(value, dict) or value.get("proposal_id") != proposal_id:
        raise ValueError("Stored Refine proposal has invalid identity or shape.")
    return value
