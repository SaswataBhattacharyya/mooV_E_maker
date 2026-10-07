import asyncio
import hashlib
from pathlib import Path

import pytest
from fastapi import HTTPException

from story_builder.api import main as api
from story_builder.services import production_story_revisions


def _setup(tmp_path: Path, monkeypatch):
    store = api.ProjectStore(tmp_path / "projects")
    project = store.create_project(title="Refine", story_input="A traveler crosses a quiet bridge.", automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", store)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    project_id = project["id"]
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="refine-test", control_mode="manual")))
    revision = {"revision_id": "shot_plans-0123456789ab", "project_id": project_id,
        "run_id": run["run_id"], "stage": "shot_plans", "review_status": "accepted",
        "source_story_hash": run["config"]["source_story_hash"], "items": [{"unit_id": "shot-01",
            "content": {"prompt": "A traveler walks over a quiet bridge.", "asset_intents": [],
                "reference_map": {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}}}}]}
    production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id, run["run_id"], "shot_plans", revision)
    return project_id, run, revision


def test_refine_is_persisted_non_mutating_then_accepts_as_new_revision(tmp_path, monkeypatch):
    project_id, run, revision = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "refine_h3_prompt", lambda **kwargs: {
        "proposal_id": "refine-aaaaaaaaaaaa", "base_input_hash": "frozen", "shot_plan_revision": revision["revision_id"],
        "proposed_prompt": "A traveler crosses the quiet bridge at dawn.", "change_summary": ["Added dawn lighting."],
        "diff": "-old\n+new", "warnings": [], "lint": {"ok": True, "errors": [], "warnings": []},
        "assets_unchanged": True, "applied": False})
    proposal = api.propose_production_v2_refine(project_id, run["run_id"],
        api.ProductionV2RefineRequest(shot_plan_revision_id=revision["revision_id"], shot_id="shot-01", instruction="Make it dawn."))["proposal"]
    original = production_story_revisions.load_stage_revision(api.OUTPUT_ROOT, project_id, run["run_id"], "shot_plans", revision["revision_id"])
    assert proposal["applied"] is False
    assert original["items"][0]["content"]["prompt"] == "A traveler walks over a quiet bridge."
    accepted = api.accept_production_v2_refine(project_id, run["run_id"], proposal["proposal_id"],
        api.ProductionV2RefineAcceptRequest(shot_plan_revision_id=revision["revision_id"],
            expected_prompt_hash=hashlib.sha256(original["items"][0]["content"]["prompt"].encode()).hexdigest()))
    new_revision = accepted["revision"]
    assert accepted["accepted"] is True
    assert new_revision["revision_id"] != revision["revision_id"]
    assert new_revision["parent_revision_id"] == revision["revision_id"]
    assert new_revision["items"][0]["content"]["prompt"] == proposal["proposed_prompt"]
    assert original["items"][0]["content"]["prompt"] == "A traveler walks over a quiet bridge."
    with pytest.raises(HTTPException) as repeated:
        api.accept_production_v2_refine(project_id, run["run_id"], proposal["proposal_id"],
            api.ProductionV2RefineAcceptRequest(shot_plan_revision_id=revision["revision_id"],
                expected_prompt_hash=hashlib.sha256(original["items"][0]["content"]["prompt"].encode()).hexdigest()))
    assert repeated.value.status_code == 409


def test_refine_accept_rejects_stale_prompt_hash(tmp_path, monkeypatch):
    project_id, run, revision = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "refine_h3_prompt", lambda **kwargs: {
        "proposal_id": "refine-bbbbbbbbbbbb", "base_input_hash": "frozen", "shot_plan_revision": revision["revision_id"],
        "proposed_prompt": "A traveler crosses at dawn.", "change_summary": [], "diff": "",
        "warnings": [], "lint": {"ok": True, "errors": [], "warnings": []}, "assets_unchanged": True, "applied": False})
    proposal = api.propose_production_v2_refine(project_id, run["run_id"],
        api.ProductionV2RefineRequest(shot_plan_revision_id=revision["revision_id"], shot_id="shot-01", instruction="Dawn."))["proposal"]
    with pytest.raises(HTTPException) as stale:
        api.accept_production_v2_refine(project_id, run["run_id"], proposal["proposal_id"],
            api.ProductionV2RefineAcceptRequest(shot_plan_revision_id=revision["revision_id"], expected_prompt_hash="0" * 64))
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "refine_prompt_stale"


def test_refine_rejects_proposal_when_newer_accepted_shot_plan_exists(tmp_path, monkeypatch):
    project_id, run, revision = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "refine_h3_prompt", lambda **_kwargs: {
        "proposal_id": "refine-cccccccccccc", "base_input_hash": "frozen", "shot_plan_revision": revision["revision_id"],
        "proposed_prompt": "A traveler crosses at dawn.", "change_summary": [], "diff": "",
        "warnings": [], "lint": {"ok": True, "errors": [], "warnings": []}, "assets_unchanged": True, "applied": False})
    proposal = api.propose_production_v2_refine(project_id, run["run_id"],
        api.ProductionV2RefineRequest(shot_plan_revision_id=revision["revision_id"], shot_id="shot-01", instruction="Dawn."))["proposal"]
    newer = {**revision, "revision_id": "shot_plans-dddddddddddd", "parent_revision_id": revision["revision_id"],
        "accepted_at": "2099-01-01T00:00:00+00:00"}
    production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id, run["run_id"], "shot_plans", newer)
    with pytest.raises(HTTPException) as stale:
        api.accept_production_v2_refine(project_id, run["run_id"], proposal["proposal_id"],
            api.ProductionV2RefineAcceptRequest(shot_plan_revision_id=revision["revision_id"], expected_prompt_hash=proposal["base_prompt_hash"]))
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "shot_plan_stale"
