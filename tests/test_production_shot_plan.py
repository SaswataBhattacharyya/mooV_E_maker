from __future__ import annotations

import uuid

import pytest

from story_builder.services import production_story_revisions
from story_builder.services.production_shot_plan import (
    ShotPlanError, canonical_content_hash, edit_shot, read_shot,
)


def _revision(output, project, run):
    content = {"prompt": "Maya enters the room.", "duration_seconds": 6,
        "characters": ["char-maya"], "asset_intents": [{"role": "character_master", "intent": "face identity only"}],
        "reference_map": {"pictures": [{"asset_id": "pa-0123456789abcdef", "tag": "<Picture 1>"}],
                          "videos": [], "audios": [], "speaker_audio_tags": {}}}
    revision = {"schema_version": 1, "revision_id": "shot_plans-012345abcdef", "project_id": project,
        "run_id": run, "stage": "shot_plans", "source_story_hash": "a" * 64,
        "review_status": "accepted", "accepted_at": "2026-10-02T00:00:00+00:00",
        "items": [{"unit_id": "scene-1-cut-1", "source_chunk_ids": ["chunk-1"], "content": content}]}
    production_story_revisions.write_stage_revision(output, project, run, "shot_plans", revision)
    return revision


def test_shot_get_and_edit_create_pending_revision_preserving_ids_and_references(tmp_path):
    output, project, run = tmp_path / "output", "film", str(uuid.uuid4())
    original = _revision(output, project, run)
    original_hash = canonical_content_hash(original["items"][0]["content"])
    loaded = read_shot(output, project, run, "scene-1-cut-1")
    assert loaded["revision_id"] == original["revision_id"]
    result = edit_shot(output, project, run, expected_revision_id=original["revision_id"],
        expected_content_hash=original_hash, shot_id="scene-1-cut-1",
        content={"prompt": "Maya enters slowly, watching the doorway."}, control_mode="manual")
    revised = result["revision"]
    assert revised["review_status"] == "pending_review"
    assert revised["parent_revision_id"] == original["revision_id"]
    assert result["shot"]["unit_id"] == "scene-1-cut-1"
    assert result["shot"]["source_chunk_ids"] == ["chunk-1"]
    assert result["shot"]["content"]["reference_map"] == original["items"][0]["content"]["reference_map"]
    assert result["shot"]["content"]["prompt"].startswith("Maya enters slowly")
    assert read_shot(output, project, run, "scene-1-cut-1")["revision_id"] == original["revision_id"]
    assert read_shot(output, project, run, "scene-1-cut-1", revised["revision_id"])["review_status"] == "pending_review"


@pytest.mark.parametrize("bad_patch,code", [
    ({"reference_map": {"pictures": []}}, "reference_wiring_is_immutable_here"),
    ({"duration_seconds": 30}, "shot_duration_invalid"),
    ({"asset_intents": [{"role": "invalid", "intent": "x"}]}, "shot_asset_intents_invalid"),
])
def test_shot_edit_rejects_unsafe_wiring_or_invalid_fields(tmp_path, bad_patch, code):
    output, project, run = tmp_path / "output", "film", str(uuid.uuid4())
    original = _revision(output, project, run)
    with pytest.raises(ShotPlanError) as error:
        edit_shot(output, project, run, expected_revision_id=original["revision_id"],
            expected_content_hash=canonical_content_hash(original["items"][0]["content"]),
            shot_id="scene-1-cut-1", content=bad_patch, control_mode="manual")
    assert error.value.code == code


def test_shot_edit_refuses_stale_content_and_full_mode(tmp_path):
    output, project, run = tmp_path / "output", "film", str(uuid.uuid4())
    original = _revision(output, project, run)
    with pytest.raises(ShotPlanError) as stale:
        edit_shot(output, project, run, expected_revision_id=original["revision_id"],
            expected_content_hash="0" * 64, shot_id="scene-1-cut-1",
            content={"prompt": "changed"}, control_mode="manual")
    assert stale.value.code == "shot_content_stale"
    with pytest.raises(ShotPlanError) as full:
        edit_shot(output, project, run, expected_revision_id=original["revision_id"],
            expected_content_hash=canonical_content_hash(original["items"][0]["content"]),
            shot_id="scene-1-cut-1", content={"prompt": "changed"}, control_mode="fully_automated")
    assert full.value.code == "director_review_required"
    with pytest.raises(ShotPlanError) as delegated_semi:
        edit_shot(output, project, run, expected_revision_id=original["revision_id"],
            expected_content_hash=canonical_content_hash(original["items"][0]["content"]),
            shot_id="scene-1-cut-1", content={"prompt": "changed"}, control_mode="semi",
            semi_gates={"story_review": False})
    assert delegated_semi.value.code == "director_review_required"
