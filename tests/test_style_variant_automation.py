import asyncio
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException

from story_builder.api import main as api


def _published_variant(tmp_path: Path, monkeypatch) -> str:
    store = api.ProjectStore(tmp_path / "projects")
    project = store.create_project(title="Style snapshot", story_input="A small story.", automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", store)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    rules = {stage: [f"Follow the published {stage} rule."]
             for stage in ("story", "scene_direction", "image", "audio", "video", "review")}
    draft = asyncio.run(api.create_production_v2_style_draft(api.NarrativeStyleDraftRequest(
        base_style_id="story_film", display_name="Quiet style", rules_by_stage=rules)))
    published = asyncio.run(api.publish_production_v2_style_draft(draft["variant_id"],
        api.NarrativeStylePublishRequest(expected_revision=draft["draft_revision"])))
    assert published["status"] == "published"
    return project["id"], published


def test_automation_run_freezes_published_variant_and_uses_its_stage_rules(tmp_path, monkeypatch):
    project_id, variant = _published_variant(tmp_path, monkeypatch)
    tasks = BackgroundTasks()
    run = asyncio.run(api.start_story_automation(project_id,
        api.AutomationStartRequest(style_id="story_film", detail_story=True,
            narrative_style_variant_id=variant["variant_id"]), tasks))
    assert run["narrative_style_variant_id"] == variant["variant_id"]
    assert run["narrative_style_variant_version"] == 1
    assert run["narrative_style_variant_hash"] == variant["content_hash"]
    assert "Follow the published story rule." in run["style_snapshot"]["stages"]["story"]
    assert tasks.tasks[0].args[2] == run["style_snapshot"]
    persisted = api.PROJECT_STORE.read_project(project_id)["automation_run"]
    assert persisted["narrative_style_variant_hash"] == variant["content_hash"]


def test_automation_rejects_variant_from_another_production_type(tmp_path, monkeypatch):
    project_id, variant = _published_variant(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as mismatch:
        asyncio.run(api.start_story_automation(project_id,
            api.AutomationStartRequest(style_id="news_report", narrative_style_variant_id=variant["variant_id"]),
            BackgroundTasks()))
    assert mismatch.value.status_code == 422
    assert mismatch.value.detail["code"] == "style_variant_base_mismatch"
