import json
from pathlib import Path

import pytest

from story_builder.services import manual_director as director


def test_workflow_catalog_is_derived_from_available_api_graphs():
    catalog = {row["workflow_id"]: row for row in director.workflow_catalog()}
    assert catalog["minimax_text"]["available"] is True
    assert catalog["minimax_text"]["accepted_slots"] == []
    assert catalog["minimax_references"]["reference_limits"]["reference_images"]["max"] == 3
    assert catalog["wan_first_last"]["required_slots"] == ["first_frame", "last_frame"]
    assert "duration_seconds" in {field["key"] for field in catalog["wan_first_last"]["parameters"]}


def test_local_upload_is_idempotent_and_stays_in_repertoire(tmp_path, monkeypatch):
    monkeypatch.setattr(director, "REPERTOIRE_ROOT", tmp_path / "video_repertoire")
    a = director.upload_asset("frame.png", b"fake-png-bytes", "first_frame")
    b = director.upload_asset("renamed.png", b"fake-png-bytes", "first_frame")
    assert a["asset_id"] == b["asset_id"]
    assert a["relative_path"].startswith("manual/assets/")
    assert len(director.list_manual_assets()) == 1
    with pytest.raises(ValueError, match="not accepted"):
        director.upload_asset("sound.wav", b"audio", "first_frame")


def test_workflow_validation_rejects_missing_or_unsupported_references(tmp_path, monkeypatch):
    monkeypatch.setattr(director, "REPERTOIRE_ROOT", tmp_path / "video_repertoire")
    image = director.upload_asset("start.png", b"image", "first_frame")
    with pytest.raises(ValueError, match="requires a last frame"):
        director.validate_request({"workflow_id": "wan_first_last", "prompt": "A scene",
                                   "references": [{"slot": "first_frame", "asset_id": image["asset_id"]}]})
    with pytest.raises(ValueError, match="cannot use the first_frame"):
        director.validate_request({"workflow_id": "minimax_text", "prompt": "A scene",
                                   "references": [{"slot": "first_frame", "asset_id": image["asset_id"]}]})


def test_validation_rejects_unsafe_or_missing_repertoire_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(director, "REPERTOIRE_ROOT", tmp_path / "video_repertoire")
    with pytest.raises(ValueError, match="safe video-repertoire"):
        director.resolve_reference({"slot": "reference_images", "relative_path": "../../etc/passwd"})


def test_h3_and_wan_workflow_inputs_are_mapped_without_modifying_source_graph():
    source = director._load_workflow(director.WORKFLOW_ROOT / director.WORKFLOWS["wan_first_last"]["file"])
    graph = json.loads(json.dumps(source))
    refs = [(director.WORKFLOW_ROOT / "wan2_2_flf2v_api.json", {"slot": "first_frame", "media_type": "image"}),
            (director.WORKFLOW_ROOT / "wan2_2_flf2v_api.json", {"slot": "last_frame", "media_type": "image"})]
    director._apply_inputs(graph, "wan_first_last", {"prompt": "A woman runs through rain", "negative_prompt": "blur",
        "parameters": {"duration_seconds": 5.0, "width": 640, "height": 640, "steps": 20}}, refs,
        ["first.png", "last.png"], "manual-012345abcdef")
    assert graph["80"]["inputs"]["image"] == "first.png"
    assert graph["89"]["inputs"]["image"] == "last.png"
    assert graph["90"]["inputs"]["text"] == "A woman runs through rain"
    assert graph["78"]["inputs"]["text"] == "blur"
    assert graph["81"]["inputs"]["length"] == 81
    assert source["81"]["inputs"]["length"] == 81
    assert graph["86"]["inputs"]["frame_rate"] == 16
    assert graph["86"]["inputs"]["fps"] == 16


def test_wan_create_video_schema_compatibility_injects_required_fps():
    graph = {"1": {"class_type": "CreateVideo", "inputs": {"images": ["2", 0]}}}
    director._apply_inputs(graph, "wan_first_last", {"prompt": "motion", "negative_prompt": "", "parameters": {}},
        [], [], "manual-test")
    assert graph["1"]["inputs"]["fps"] == 16


def test_minimax_reference_graph_fills_every_required_image_node():
    graph = {str(index): {"class_type": "LoadImage", "inputs": {"image": f"stale-default-{index}.png"}}
        for index in (1, 2, 3)}
    refs = [(Path("one.png"), {"slot": "reference_images", "media_type": "image"}),
            (Path("two.png"), {"slot": "reference_images", "media_type": "image"})]
    director._apply_inputs(graph, "minimax_references", {"prompt": "move gently", "negative_prompt": "", "parameters": {}},
        refs, ["one.png", "two.png"], "manual-test")
    assert [graph[str(index)]["inputs"]["image"] for index in (1, 2, 3)] == ["one.png", "two.png", "two.png"]
