from __future__ import annotations

from pathlib import Path

import pytest

from story_builder.services import production_take_runtime as runtime
from story_builder.services.minimax_h3_graph_compiler import ImageReference, ReferencePlan, plan_to_dict
from story_builder.services.minimax_h3_media import StagedAsset


def _fixture_validation():
    plan = ReferencePlan(schema_version=1, project_id="p1", run_id="r1", shot_id="s1",
        prompt="<Picture 1> establishes the character.", duration_seconds=5,
        images=(ImageReference("pa-0123456789abcdef", "character_master", "identity"),))
    return plan


def test_take_preparer_revalidates_frozen_hash_then_stages_and_compiles(tmp_path: Path, monkeypatch):
    plan = _fixture_validation()
    calls = []

    def stage(source, **kwargs):
        calls.append((source, kwargs))
        return StagedAsset(kwargs["asset_id"], "image", "staged-image.png", "a" * 64,
            "b" * 64, None, 1024, 1024, kwargs["owner_id"])

    monkeypatch.setattr(runtime.minimax_h3_media, "stage_image_reference", stage)
    monkeypatch.setattr(runtime.minimax_h3_media, "cleanup_owned_media", lambda *a, **k: {"removed": []})
    validation = {"valid": True, "validation_hash": "c" * 64, "plan": plan_to_dict(plan),
        "workflow_readiness": {"available": True}}
    preparer = runtime.make_take_preparer(validate=lambda _take, request: validation,
        resolve_source=lambda project, asset: Path("/safe") / project / asset,
        comfy_input_dir=tmp_path / "comfy-input", owner_root=tmp_path / "owned")
    prepared = preparer({"project_id": "p1", "run_id": "r1", "shot_id": "s1", "take_id": "t1",
        "attempt": 1, "input_snapshot": {"validation_request": {"prompt": plan.prompt},
            "validation_hash": "c" * 64}})

    assert calls[0][0] == Path("/safe/p1/pa-0123456789abcdef")
    assert calls[0][1]["owner_id"] == "t1_a1"
    assert prepared.graph
    assert any(node.get("class_type") == "LoadImage" for node in prepared.graph.values())
    prepared.cleanup()


def test_take_preparer_refuses_stale_validation_before_staging(tmp_path: Path, monkeypatch):
    called = []
    monkeypatch.setattr(runtime.minimax_h3_media, "stage_image_reference", lambda *a, **k: called.append(True))
    preparer = runtime.make_take_preparer(validate=lambda _take, _: {"valid": True, "validation_hash": "new"},
        resolve_source=lambda *_: Path("/never"), comfy_input_dir=tmp_path / "input", owner_root=tmp_path / "owned")
    with pytest.raises(ValueError, match="shot_validation_stale"):
        preparer({"project_id": "p1", "take_id": "t1", "attempt": 1,
            "input_snapshot": {"validation_request": {}, "validation_hash": "old"}})
    assert called == []


def test_take_preparer_compiles_zero_reference_take_as_t2v_without_staging(tmp_path: Path, monkeypatch):
    plan = _fixture_validation()
    plan = ReferencePlan(schema_version=1, project_id="p1", run_id="r1", shot_id="s1",
        prompt="A lantern glows in rain.", duration_seconds=5)
    calls = []
    monkeypatch.setattr(runtime.minimax_h3_media, "stage_image_reference", lambda *a, **k: calls.append("image"))
    monkeypatch.setattr(runtime.minimax_h3_media, "cleanup_owned_media", lambda *a, **k: {"removed": []})
    from story_builder.services.minimax_h3_graph_compiler import plan_to_dict
    from story_builder.services.minimax_h3_t2v import T2V_WORKFLOW_ID
    validation = {"valid": True, "validation_hash": "d" * 64, "plan": plan_to_dict(plan),
        "workflow_id": T2V_WORKFLOW_ID, "workflow_readiness": {"available": True}}
    prepared = runtime.make_take_preparer(validate=lambda *_: validation,
        resolve_source=lambda *_: Path("/never"), comfy_input_dir=tmp_path / "in",
        owner_root=tmp_path / "owned")({"project_id": "p1", "run_id": "r1", "shot_id": "s1",
        "take_id": "t2v1", "attempt": 1, "input_snapshot": {"validation_request": {},
        "validation_hash": "d" * 64}})
    assert calls == []
    kinds = {node.get("class_type") for node in prepared.graph.values()}
    assert "MiniMaxH3ImageToVideo" in kinds
    assert "SaveVideo" in kinds
    prepared.cleanup()


def test_t2v_compiler_rejects_reference_assets():
    from story_builder.services.minimax_h3_t2v import compile_t2v_graph
    with pytest.raises(ValueError, match="accepts no reference assets"):
        compile_t2v_graph(_fixture_validation())


def test_output_collector_indexes_only_safe_project_outputs_and_requires_video(tmp_path: Path, monkeypatch):
    copied_path = Path("generated.mp4")

    def download(_history, *, destination_dir: Path, comfy_url: str):
        destination_dir.mkdir(parents=True, exist_ok=True)
        (destination_dir / copied_path).write_bytes(b"media")
        return [{"kind": "video", "relative_path": str(copied_path), "filename": str(copied_path)}]

    from story_builder.services import production_assets
    monkeypatch.setattr(production_assets, "_probe_media", lambda *args: {"duration_seconds": 1})
    collector = runtime.make_output_collector(output_root=tmp_path / "output",
        storage_projects_root=tmp_path / "projects", comfy_url="http://comfy", download_outputs=download)
    result = collector({"project_id": "p1", "run_id": "r1", "shot_id": "s1", "take_id": "t1", "attempt": 1}, {"outputs": {}})
    assert result[0]["asset_id"].startswith("pa-")
    assert (tmp_path / "output" / "p1" / result[0]["relative_path"]).is_file()
    assert result[0]["approval_status"] == "candidate"
    roles = production_assets.get_asset_record(tmp_path / "projects", "p1", result[0]["asset_id"])["roles"]
    assert roles == ["project_video", "previous_cut_tail"]
    with pytest.raises(ValueError, match="output_missing_video"):
        runtime.make_output_collector(output_root=tmp_path / "output2", storage_projects_root=tmp_path / "projects",
            comfy_url="http://comfy", download_outputs=lambda *_a, **_k: [])(
                {"project_id": "p1", "run_id": "r1", "shot_id": "s1", "take_id": "t2"}, {"outputs": {}})
