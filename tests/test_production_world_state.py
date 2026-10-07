from __future__ import annotations

import json
import uuid

import pytest

from story_builder.services.production_world_state import (
    WorldStateError, create_anonymous_character, create_world,
    read_project_canon, save_project_canon,
)


def test_world_and_character_bibles_are_project_scoped_revisioned_and_keep_ids(tmp_path):
    character = create_anonymous_character()
    world = create_world("Rainy apartment", "A compact apartment above a railway station.")
    first = save_project_canon(tmp_path / "projects", "film-1", expected_revision=0,
        characters=[character], worlds=[world], source_story_revision="story-canon-012345abcdef")
    assert first["revision"] == 1
    assert first["characters"][0]["display_name"].startswith("Character-")
    assert uuid.UUID(first["characters"][0]["character_id"])
    assert len(first["content_hash"]) == 64
    changed = {**character, "display_name": "Maya", "aliases": ["Character-K7M2"]}
    second = save_project_canon(tmp_path / "projects", "film-1", expected_revision=1,
        characters=[changed], worlds=[{**world, "visual_rules": "Green walls, one brass lamp."}], actor="director")
    assert second["characters"][0]["character_id"] == character["character_id"]
    assert second["characters"][0]["display_name"] == "Maya"
    assert read_project_canon(tmp_path / "projects", "film-1")["revision"] == 2
    assert read_project_canon(tmp_path / "projects", "film-2")["characters"] == []
    revisions = sorted((tmp_path / "projects" / "film-1" / "production" / "canon_revisions").glob("*.json"))
    assert len(revisions) == 2
    assert json.loads(revisions[0].read_text())["revision"] == 1


def test_canon_conflicts_cannot_remove_ids_or_duplicate_identity(tmp_path):
    root = tmp_path / "projects"
    char = create_anonymous_character()
    world = create_world("Station")
    save_project_canon(root, "film", expected_revision=0, characters=[char], worlds=[world])
    with pytest.raises(WorldStateError, match="changed") as stale:
        save_project_canon(root, "film", expected_revision=0, characters=[char], worlds=[world])
    assert stale.value.code == "canon_revision_conflict"
    with pytest.raises(WorldStateError) as remove:
        save_project_canon(root, "film", expected_revision=1, characters=[], worlds=[world])
    assert remove.value.code == "canon_identity_removal"
    duplicate = {**char, "display_name": "duplicate"}
    with pytest.raises(WorldStateError) as dup:
        save_project_canon(root, "film", expected_revision=1, characters=[char, duplicate], worlds=[world])
    assert dup.value.code == "canon_id_duplicate"


def test_canon_validates_evidence_and_project_ids(tmp_path):
    with pytest.raises(WorldStateError) as evidence:
        save_project_canon(tmp_path, "film", expected_revision=0,
            characters=[{**create_anonymous_character(), "evidence": ["unstructured"]}], worlds=[])
    assert evidence.value.code == "canon_evidence_invalid"
    with pytest.raises(WorldStateError) as path:
        read_project_canon(tmp_path, "../outside")
    assert path.value.code == "invalid_project_id"
