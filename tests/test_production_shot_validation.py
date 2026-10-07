from __future__ import annotations

from dataclasses import replace

import pytest

from story_builder.services.minimax_h3_graph_compiler import (
    AudioReference, GraphPlanError, ImageReference, ReferencePlan, VideoReference,
)
from story_builder.services.production_shot_validation import validate_and_compile_shot


def _plan(*, videos=(), audios=()):
    prompt = "<Picture 1> defines Maya. <Video 1> is the preceding cut; continue from its final moment. "
    if videos:
        prompt += "<Audio 1> is the synchronized soundtrack of Video 1 for impact timing. "
    if audios:
        prompt += "<Audio 2> is Maya's voice reference for Subject 1 (S1). Maya (S1) speaks clearly."
    return ReferencePlan(schema_version=1, project_id="project-1", run_id="run-1", shot_id="shot-1",
        prompt=prompt, duration_seconds=5.0, images=(ImageReference("image-1", "character_master", "Maya identity"),),
        videos=tuple(videos), standalone_audios=tuple(audios))


def _resolved_metadata():
    return {
        "image-1": {"media_type": "image", "filename": "maya.png", "sha256": "a" * 64},
        "video-1": {"media_type": "video", "filename": "previous.mp4", "sha256": "b" * 64,
                    "duration_seconds": 20.0, "has_audio": True},
        "voice-1": {"media_type": "audio", "filename": "voice.wav", "sha256": "c" * 64,
                    "duration_seconds": 6.0, "has_audio": False},
    }


def _record(asset_id, kind):
    roles = {"image": ["character_master", "world_master"],
             "video": ["previous_cut_tail", "action_reference_video"],
             "audio": ["voice_excerpt"]}[kind]
    metadata = {}
    if kind == "audio":
        metadata = {"approval_status": "accepted", "run_id": "run-1", "character_id": "char-1",
                    "source_voice_asset_id": "master-1", "source_sha256": "e" * 64}
    return {"asset_id": asset_id, "project_id": "project-1", "kind": kind, "roles": roles, "metadata": metadata}


_BINDINGS = [{"run_id": "run-1", "speaker_id": "S1", "character_id": "char-1", "voice_asset_id": "master-1",
              "voice_asset_hash": "e" * 64, "source_project_id": "project-1"}]


def test_validation_compiles_exact_tags_intervals_and_hash_without_exposing_paths():
    plan = _plan(videos=[VideoReference("video-1", "previous_cut_tail", "continue prior motion",
        include_paired_soundtrack=True, audio_intent="impact rhythm")],
        audios=[AudioReference("voice-1", "voice_excerpt", "Maya timbre", "S1")])
    metadata = _resolved_metadata()
    result = validate_and_compile_shot(plan, get_asset=lambda asset_id: _record(asset_id, metadata[asset_id]["media_type"]),
        inspect_asset=lambda row: metadata[row["asset_id"]], voice_bindings=_BINDINGS)
    assert result["valid"] is True
    assert result["width"] == 1344 and result["height"] == 768
    assert result["reference_map"]["pictures"][0]["tag"] == "<Picture 1>"
    assert result["reference_map"]["videos"][0]["interval"] == [0.0, 15.0]
    assert result["reference_map"]["audios"][0]["tag"] == "<Audio 1>"
    assert result["reference_map"]["audios"][1]["tag"] == "<Audio 2>"
    assert result["reference_map"]["speaker_audio_tags"] == {"S1": "<Audio 2>"}
    assert len(result["validation_hash"]) == 64
    serialized = str(result)
    assert "maya.png" not in serialized and "comfy_filename" not in serialized


def test_compiler_resolves_reference_map_before_final_prompt_tags_exist():
    metadata = _resolved_metadata()
    plan = replace(_plan(videos=[VideoReference("video-1", "previous_cut_tail", "continue prior motion",
        include_paired_soundtrack=True, audio_intent="carry room tone")],
        audios=[AudioReference("voice-1", "voice_excerpt", "Maya timbre", "S1")]),
        prompt="Maya pauses, then turns toward the doorway.")
    result = validate_and_compile_shot(plan,
        get_asset=lambda asset_id: _record(asset_id, metadata[asset_id]["media_type"]),
        inspect_asset=lambda row: metadata[row["asset_id"]], voice_bindings=_BINDINGS,
        reference_map_only=True)
    assert result["reference_map_only"] is True
    assert result["prompt_tags_validated"] is False
    assert [row["tag"] for row in result["reference_map"]["pictures"]] == ["<Picture 1>"]
    assert [row["tag"] for row in result["reference_map"]["videos"]] == ["<Video 1>"]
    assert [row["tag"] for row in result["reference_map"]["audios"]] == ["<Audio 1>", "<Audio 2>"]
    assert result["reference_map"]["audios"][0]["paired_video_tag"] == "<Video 1>"
    assert result["reference_map"]["speaker_audio_tags"] == {"S1": "<Audio 2>"}
    assert result["plan"]["prompt"] == "Maya pauses, then turns toward the doorway."
    with pytest.raises(GraphPlanError) as final_validation:
        validate_and_compile_shot(plan,
            get_asset=lambda asset_id: _record(asset_id, metadata[asset_id]["media_type"]),
            inspect_asset=lambda row: metadata[row["asset_id"]], voice_bindings=_BINDINGS)
    assert final_validation.value.code == "prompt_reference_tags_mismatch"


def test_zero_reference_shot_compiles_separate_t2v_contract():
    plan = ReferencePlan(schema_version=1, project_id="project-1", run_id="run-1", shot_id="shot-1",
        prompt="A lantern glows in rain.", duration_seconds=5.0, images=(), videos=(), standalone_audios=())
    result = validate_and_compile_shot(plan, get_asset=lambda _asset: pytest.fail("T2V must not resolve references"),
        inspect_asset=lambda _record: pytest.fail("T2V must not inspect references"))
    assert result["workflow_id"] == "minimax_h3_t2v_local_v1"
    assert result["reference_map"] == {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}}
    assert result["asset_fingerprints"] == {}
    assert len(result["validation_hash"]) == 64


def test_t2v_duration_respects_the_installed_workflow_limit():
    plan = ReferencePlan(schema_version=1, project_id="project-1", run_id="run-1", shot_id="shot-1",
        prompt="A lantern glows in rain.", duration_seconds=10.1, images=(), videos=(), standalone_audios=())
    with pytest.raises(GraphPlanError) as invalid:
        validate_and_compile_shot(plan, get_asset=lambda _asset: pytest.fail("T2V must not resolve references"),
            inspect_asset=lambda _record: pytest.fail("T2V must not inspect references"))
    assert invalid.value.code == "invalid_duration"


def test_saved_reference_order_compiles_deterministically_and_changes_the_resolved_map():
    first = ImageReference("image-1", "character_master", "Maya identity")
    second = ImageReference("image-2", "world_master", "Observatory layout")
    metadata = {**_resolved_metadata(),
        "image-2": {"media_type": "image", "filename": "observatory.png", "sha256": "d" * 64}}
    base = _plan()
    ordered = replace(base, images=(first, second),
        prompt="<Picture 1> is Maya. <Picture 2> is the observatory.")
    reordered = replace(ordered, images=(second, first),
        prompt="<Picture 1> is the observatory. <Picture 2> is Maya.")
    get_asset = lambda asset_id: _record(asset_id, "image")
    inspect = lambda row: metadata[row["asset_id"]]

    one = validate_and_compile_shot(ordered, get_asset=get_asset, inspect_asset=inspect)
    repeated = validate_and_compile_shot(ordered, get_asset=get_asset, inspect_asset=inspect)
    swapped = validate_and_compile_shot(reordered, get_asset=get_asset, inspect_asset=inspect)
    assert one["validation_hash"] == repeated["validation_hash"]
    assert one["reference_map"] == repeated["reference_map"]
    assert one["reference_map"]["pictures"][0]["asset_id"] == "image-1"
    assert swapped["reference_map"]["pictures"][0]["asset_id"] == "image-2"
    assert swapped["validation_hash"] != one["validation_hash"]


def test_video_duration_must_fit_source_and_combined_budget():
    metadata = _resolved_metadata()
    refs = [VideoReference("video-a", "action_reference_video", "first action", 0, 8),
            VideoReference("video-b", "action_reference_video", "second action", 10, 17)]
    records = {**metadata, "video-a": {**metadata["video-1"], "filename": "a.mp4"},
               "video-b": {**metadata["video-1"], "filename": "b.mp4"}}
    plan = replace(_plan(videos=refs), prompt="<Picture 1> identity. <Video 1> action. <Video 2> action.")
    result = validate_and_compile_shot(plan,
            get_asset=lambda asset_id: _record(asset_id, records[asset_id]["media_type"]),
        inspect_asset=lambda row: records[row["asset_id"]])
    assert result["video_reference_seconds"] == 15

    over_budget = replace(plan, videos=(refs[0], replace(refs[1], start_sec=7, end_sec=15)))
    with pytest.raises(GraphPlanError) as too_long:
        validate_and_compile_shot(over_budget,
            get_asset=lambda asset_id: _record(asset_id, "image" if asset_id == "image-1" else "video"),
            inspect_asset=lambda row: records[row["asset_id"]])
    assert too_long.value.code == "video_reference_total_too_long"
    beyond_source = replace(plan, videos=(replace(refs[0], end_sec=21), refs[1]))
    with pytest.raises(GraphPlanError) as invalid:
        validate_and_compile_shot(beyond_source,
            get_asset=lambda asset_id: _record(asset_id, "image" if asset_id == "image-1" else "video"),
            inspect_asset=lambda row: records[row["asset_id"]])
    assert invalid.value.code == "invalid_video_interval"


def test_standalone_audio_duration_and_prompt_tags_are_enforced():
    metadata = _resolved_metadata()
    plan = replace(_plan(audios=[AudioReference("voice-1", "voice_excerpt", "voice", "S1")]),
                   prompt="<Picture 1> defines Maya. <Audio 1> is Maya voice for Subject 1 (S1). Maya (S1) speaks.")
    with pytest.raises(GraphPlanError) as overlong:
        validate_and_compile_shot(plan,
            get_asset=lambda asset_id: _record(asset_id, "audio" if asset_id == "voice-1" else "image"),
            inspect_asset=lambda row: {**metadata[row["asset_id"]], **({"duration_seconds": 19.0} if row["asset_id"] == "voice-1" else {})},
            voice_bindings=_BINDINGS)
    assert overlong.value.code == "audio_reference_duration_invalid"
    bad_tags = replace(plan, prompt="<Picture 1> only.")
    with pytest.raises(GraphPlanError) as unbound:
        validate_and_compile_shot(bad_tags,
            get_asset=lambda asset_id: _record(asset_id, "audio" if asset_id == "voice-1" else "image"),
            inspect_asset=lambda row: metadata[row["asset_id"]], voice_bindings=_BINDINGS)
    assert unbound.value.code == "prompt_reference_tags_mismatch"


def test_cross_project_records_and_unverified_assets_are_refused():
    plan = _plan()
    metadata = _resolved_metadata()
    with pytest.raises(GraphPlanError) as owner:
        validate_and_compile_shot(plan, get_asset=lambda asset_id: {**_record(asset_id, "image"), "project_id": "other-project"},
            inspect_asset=lambda row: metadata[row["asset_id"]])
    assert owner.value.code == "asset_project_mismatch"
    with pytest.raises(GraphPlanError) as digest:
        validate_and_compile_shot(plan, get_asset=lambda asset_id: _record(asset_id, "image"),
            inspect_asset=lambda _row: {"media_type": "image", "filename": "maya.png", "sha256": "not-a-hash"})
    assert digest.value.code == "asset_hash_missing"


def test_registry_role_and_saved_voice_binding_are_required_for_audio_references():
    metadata = _resolved_metadata()
    plan = replace(_plan(audios=[AudioReference("voice-1", "voice_excerpt", "Maya timbre", "S1")]),
        prompt="<Picture 1> defines Maya. <Audio 1> is Maya's voice reference for Subject 1 (S1). Maya (S1) speaks clearly.")
    inspect = lambda row: metadata[row["asset_id"]]

    forged_role = _record("voice-1", "audio")
    forged_role["roles"] = ["project_audio"]
    with pytest.raises(GraphPlanError) as role_error:
        validate_and_compile_shot(plan,
            get_asset=lambda asset_id: forged_role if asset_id == "voice-1" else _record(asset_id, "image"),
            inspect_asset=inspect, voice_bindings=_BINDINGS)
    assert role_error.value.code == "asset_role_mismatch"

    mismatched_run = _record("voice-1", "audio")
    mismatched_run["metadata"]["run_id"] = "another-run"
    with pytest.raises(GraphPlanError) as run_error:
        validate_and_compile_shot(plan,
            get_asset=lambda asset_id: mismatched_run if asset_id == "voice-1" else _record(asset_id, "image"),
            inspect_asset=inspect, voice_bindings=_BINDINGS)
    assert run_error.value.code == "voice_reference_binding_mismatch"

    with pytest.raises(GraphPlanError) as binding_error:
        validate_and_compile_shot(plan,
            get_asset=lambda asset_id: _record(asset_id, "audio" if asset_id == "voice-1" else "image"),
            inspect_asset=inspect, voice_bindings=[])
    assert binding_error.value.code == "voice_reference_binding_mismatch"
