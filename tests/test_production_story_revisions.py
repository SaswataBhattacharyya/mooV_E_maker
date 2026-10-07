from __future__ import annotations

import json

import pytest

from story_builder.services.production_story_revisions import (
    list_revisions,
    load_revision,
    load_stage_revision,
    revision_root,
    write_revision,
    write_stage_revision,
)


def test_story_and_stage_revisions_are_atomic_project_run_scoped_json(tmp_path):
    root = tmp_path / "output"
    story = {"revision_id": "story-canon-0123456789ab", "review_status": "pending_review", "chunks": []}
    path = write_revision(root, "project-a", "8a9c4c53-02a1-4c11-9dfa-0902bab485d7", story)
    assert json.loads(path.read_text()) == story
    assert load_revision(root, "project-a", "8a9c4c53-02a1-4c11-9dfa-0902bab485d7", story["revision_id"]) == story
    assert [row["revision_id"] for row in list_revisions(root, "project-a", "8a9c4c53-02a1-4c11-9dfa-0902bab485d7")] == [story["revision_id"]]

    scenes = {"revision_id": "scenes-abcdef012345", "stage": "scenes", "items": []}
    scene_path = write_stage_revision(root, "project-a", "8a9c4c53-02a1-4c11-9dfa-0902bab485d7", "scenes", scenes)
    assert scene_path.is_relative_to(root)
    assert load_stage_revision(root, "project-a", "8a9c4c53-02a1-4c11-9dfa-0902bab485d7", "scenes", scenes["revision_id"]) == scenes


@pytest.mark.parametrize("project_id,run_id", [
    ("../outside", "run"),
    ("project", "../../outside"),
])
def test_revision_root_rejects_path_escape(tmp_path, project_id, run_id):
    with pytest.raises(ValueError, match="Invalid|escapes"):
        revision_root(tmp_path / "output", project_id, run_id)


def test_stage_revision_rejects_unsafe_stage_and_id(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        write_stage_revision(tmp_path, "p", "run", "../../project", {"revision_id": "bad"})
    with pytest.raises(ValueError, match="does not match"):
        write_stage_revision(tmp_path, "p", "run", "scenes", {"revision_id": "dialogue-abcd"})


def test_story_revision_id_cannot_escape_revision_directory(tmp_path):
    with pytest.raises(ValueError, match="invalid format"):
        write_revision(tmp_path, "project", "8a9c4c53-02a1-4c11-9dfa-0902bab485d7",
                       {"revision_id": "../../outside"})
    assert load_revision(tmp_path, "project", "8a9c4c53-02a1-4c11-9dfa-0902bab485d7", "../../outside") is None
