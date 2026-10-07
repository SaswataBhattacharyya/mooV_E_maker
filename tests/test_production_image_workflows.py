from __future__ import annotations

import json
from pathlib import Path

import pytest

from story_builder.services.production_image_workflows import (
    ImageWorkflowError,
    SPECS,
    compile_image_candidates,
    generation_policy,
    image_output_provenance,
    image_workflow_catalog,
)


def test_candidate_policy_is_four_user_choices_or_one_director_choice():
    assert generation_policy("manual")["initial_candidates"] == 4
    assert generation_policy("semi")["selection_authority"] == "user"
    full = generation_policy("fully_automated", full_retake_budget=3)
    assert full == {"initial_candidates": 1, "full_retake_budget": 3, "selection_authority": "director"}
    with pytest.raises(ImageWorkflowError, match="retake budget"):
        generation_policy("fully_automated", full_retake_budget=5)


def test_qwen_2512_and_zimage_compile_four_deterministic_independent_graphs():
    for workflow_id, prompt_node, sampler_node, latent_node, save_node in (
        ("qwen_image_2512", "227", "230", "232", "60"),
        ("z_image_turbo", "45", "44", "41", "76"),
    ):
        compiled = compile_image_candidates(workflow_id=workflow_id, prompt="Rain on an empty stage.",
            control_mode="manual", seed=41, output_prefix="run-01/character")
        assert compiled["initial_candidate_count"] == 4
        assert [row["seed"] for row in compiled["candidates"]] == [41, 42, 43, 44]
        for index, row in enumerate(compiled["candidates"], 1):
            graph = row["graph"]
            assert graph[prompt_node]["inputs"]["text"] == "Rain on an empty stage."
            assert graph[sampler_node]["inputs"]["seed"] == 40 + index
            assert graph[latent_node]["inputs"]["batch_size"] == 1
            assert graph[save_node]["inputs"]["filename_prefix"] == f"run-01/character/candidate-{index}"
    full = compile_image_candidates(workflow_id="qwen_image_2512", prompt="One approved image.",
        control_mode="fully_automated", seed=9, output_prefix="story/char-a", full_retake_budget=2)
    assert full["initial_candidate_count"] == 1
    assert full["full_retake_budget"] == 2


def test_qwen_edit_2511_compiles_optional_reference_slots_without_paths():
    source = Path("workflows/api/qwen_edit_2511_api.json")
    assert source.is_file()
    original = json.loads(source.read_text())
    for node_id in ("147", "148"):
        assert original[node_id]["class_type"] == "FluxKontextMultiReferenceLatentMethod"
        assert original[node_id]["inputs"]["reference_latents_method"] == "index_timestep_zero"
        assert "method" not in original[node_id]["inputs"]
    assert original["37"]["inputs"]["unet_name"] == "qwen_image_edit_2511_bf16.safetensors"
    assert original["89"]["inputs"]["lora_name"].startswith("Qwen-Image-Edit-2511")
    assert original["3"]["inputs"]["positive"] == ["148", 0]
    assert original["3"]["inputs"]["negative"] == ["147", 0]
    one = compile_image_candidates(workflow_id="qwen_image_edit_2511", prompt="Change the coat to green.",
        control_mode="semi", seed=100, output_prefix="edit/shot-1", source_images=["source.png"])
    graph = one["candidates"][0]["graph"]
    assert len(one["candidates"]) == 4
    assert graph["78"]["inputs"]["image"] == "source.png"
    assert "120" not in graph and "121" not in graph
    assert "image2" not in graph["111"]["inputs"] and "image3" not in graph["111"]["inputs"]
    three = compile_image_candidates(workflow_id="qwen_image_edit_2511", prompt="Make a storyboard.",
        control_mode="fully_automated", seed=8, output_prefix="edit/shot-2",
        source_images=["input.png", "world.png", "character.png"])
    assert three["candidates"][0]["graph"]["121"]["inputs"]["image"] == "character.png"
    assert "image3" in three["candidates"][0]["graph"]["111"]["inputs"]
    assert ".." not in json.dumps(three["candidates"][0]["graph"])


def test_existing_qwen_edit_2509_graph_remains_distinct_and_unchanged():
    legacy = json.loads(Path("workflows/api/qwen_edit_api.json").read_text())
    new_2511 = json.loads(Path("workflows/api/qwen_edit_2511_api.json").read_text())
    assert legacy["37"]["inputs"]["unet_name"] == "qwen_image_edit_2509_fp8_e4m3fn.safetensors"
    assert legacy["89"]["inputs"]["lora_name"] == "Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors"
    assert new_2511["37"]["inputs"]["unet_name"] == "qwen_image_edit_2511_bf16.safetensors"
    assert new_2511["89"]["inputs"]["lora_name"] == "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"
    assert legacy != new_2511


@pytest.mark.parametrize("kwargs", [
    {"workflow_id": "unknown", "prompt": "x", "control_mode": "manual", "seed": 1, "output_prefix": "x"},
    {"workflow_id": "qwen_image_edit_2511", "prompt": "x", "control_mode": "manual", "seed": 1, "output_prefix": "x"},
    {"workflow_id": "qwen_image_2512", "prompt": "x", "control_mode": "manual", "seed": 1, "output_prefix": "../x"},
    {"workflow_id": "qwen_image_2512", "prompt": "x", "control_mode": "manual", "seed": 1, "output_prefix": "x", "width": 255},
    {"workflow_id": "z_image_turbo", "prompt": "x", "control_mode": "manual", "seed": 1, "output_prefix": "x", "steps": 30},
])
def test_invalid_image_graph_requests_fail_before_submission(kwargs):
    with pytest.raises(ImageWorkflowError):
        compile_image_candidates(**kwargs)


def test_readiness_fails_closed_until_exact_workflow_smoke_and_live_nodes_exist(tmp_path: Path):
    model_root = tmp_path / "comfy" / "models"
    for spec in SPECS.values():
        for folder, filename in spec["models"].values():
            path = model_root / folder / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
    all_nodes = {node: {} for spec in SPECS.values() for node in spec["required_nodes"]}
    blocked = image_workflow_catalog(comfy_root=tmp_path / "comfy", object_info=all_nodes,
                                     workflow_root=Path("workflows/api"), smoke_root=tmp_path / "smokes")
    assert all(item["available"] is False for item in blocked["workflows"])
    assert all("smoke" in item["disabled_reason"] for item in blocked["workflows"])

    smoke_root = tmp_path / "smokes"
    smoke_root.mkdir()
    for workflow_id, spec in SPECS.items():
        (smoke_root / f"{workflow_id}.json").write_text(json.dumps({
            "workflow_id": workflow_id, "workflow_version": spec["version"], "status": "passed",
            "output_probe": {"kind": "image", "width": 64, "height": 64}, "unloaded_after_run": True}))
    ready = image_workflow_catalog(comfy_root=tmp_path / "comfy", object_info=all_nodes,
                                   workflow_root=Path("workflows/api"), smoke_root=smoke_root)
    assert all(item["available"] is True for item in ready["workflows"])
    missing_node_info = dict(all_nodes)
    missing_node_info.pop("FluxKontextMultiReferenceLatentMethod")
    missing = image_workflow_catalog(comfy_root=tmp_path / "comfy", object_info=missing_node_info,
                                     workflow_root=Path("workflows/api"), smoke_root=smoke_root)
    edit = next(item for item in missing["workflows"] if item["workflow_id"] == "qwen_image_edit_2511")
    assert edit["available"] is False and "FluxKontextMultiReferenceLatentMethod" in edit["disabled_reason"]


def test_catalog_reports_installed_files_but_does_not_claim_live_readiness_when_comfy_is_offline(tmp_path: Path):
    root = Path("/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI")
    catalog = image_workflow_catalog(comfy_root=root, workflow_root=Path("workflows/api"),
        smoke_root=tmp_path / "none", comfy_url="http://127.0.0.1:1")
    qwen = next(item for item in catalog["workflows"] if item["workflow_id"] == "qwen_image_2512")
    edit = next(item for item in catalog["workflows"] if item["workflow_id"] == "qwen_image_edit_2511")
    assert qwen["models"]["diffusion_model"]["present"] is True
    assert edit["models"]["lightning_lora"]["present"] is True
    assert all(item["available"] is False and item["comfyui_online"] is False for item in catalog["workflows"])


def test_output_provenance_freezes_workflow_prompt_seed_settings_and_candidate():
    record = image_output_provenance(project_id="p1", run_id="run1", asset_role="character_master",
        workflow_id="qwen_image_2512", prompt="A character sheet", seed=123,
        settings={"width": 1664, "height": 928, "steps": 50, "cfg": 4.0}, candidate_index=2)
    assert record["workflow_version"] == "1"
    assert record["seed"] == 123 and record["candidate_index"] == 2
    assert record["accepted"] is False
