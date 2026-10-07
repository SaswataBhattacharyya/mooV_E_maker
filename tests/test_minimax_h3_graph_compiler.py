from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from story_builder.services.minimax_h3_graph_compiler import (
    AudioReference,
    GraphPlanError,
    ImageReference,
    ReferencePlan,
    ResolvedAsset,
    VideoReference,
    compile_r2v_graph,
    lint_prompt_tags,
    load_base_graph,
    resolve_reference_assets,
    validate_comfy_capabilities,
    validate_reference_plan,
)


SHA = hashlib.sha256(b"test asset").hexdigest()


def _asset(asset_id: str, media_type: str, suffix: str = ".png", *, interval=None, has_audio: bool = False) -> ResolvedAsset:
    start, end = interval if interval else (None, None)
    return ResolvedAsset(asset_id, media_type, f"staged-{asset_id}{suffix}", SHA, start, end, has_audio)


def _plan(**changes) -> ReferencePlan:
    values = dict(
        schema_version=1,
        project_id="project-1",
        run_id="run-1",
        shot_id="shot-1",
        prompt="Use <Picture 1> as Maya's identity reference.",
        duration_seconds=5.0,
        images=(ImageReference("image-1", "character_identity", "Use Maya's appearance."),),
    )
    values.update(changes)
    return ReferencePlan(**values)


def test_compile_one_image_uses_a_copy_and_keeps_template_unchanged():
    base = load_base_graph()
    original = json.dumps(base, sort_keys=True)
    compiled = compile_r2v_graph(_plan(), {"image-1": _asset("image-1", "image")}, base_graph=base)

    h3 = compiled.graph["136"]
    assert h3["inputs"]["ref_images.ref_image_0"]
    loader_id = h3["inputs"]["ref_images.ref_image_0"][0]
    assert compiled.graph[loader_id] == {"class_type": "LoadImage", "inputs": {"image": "staged-image-1.png"}}
    assert [n["class_type"] for n in compiled.graph.values()].count("LoadImage") == 1
    assert compiled.width == 1344 and compiled.height == 768
    assert compiled.frame_count == 124
    assert compiled.reference_map.pictures[0]["tag"] == "<Picture 1>"
    assert compiled.graph["92"]["inputs"]["filename_prefix"] == "story_builder/run-1/shot-1"
    assert json.dumps(base, sort_keys=True) == original


def test_video_and_its_paired_audio_share_the_same_loader():
    plan = _plan(
        prompt="Use <Picture 1> for identity and <Video 1> for action; <Audio 1> supplies the synced action sounds.",
        videos=(VideoReference("video-1", "action", "Transfer the movement.", include_paired_soundtrack=True, audio_intent="Use impacts only."),),
    )
    compiled = compile_r2v_graph(plan, {
        "image-1": _asset("image-1", "image"),
        "video-1": _asset("video-1", "video", ".mp4", interval=(0.0, 5.0), has_audio=True),
    })

    h3_inputs = compiled.graph["136"]["inputs"]
    image_link = h3_inputs["ref_videos.ref_video_0"]
    audio_link = h3_inputs["ref_video_audios.ref_video_audio_0"]
    assert image_link[0] == audio_link[0]
    assert image_link[1] == 0
    assert audio_link[1] == 2
    assert compiled.graph[image_link[0]]["class_type"] == "VHS_LoadVideo"
    assert compiled.graph[image_link[0]]["inputs"]["force_rate"] == 24
    assert compiled.reference_map.audios[0]["tag"] == "<Audio 1>"
    assert compiled.reference_map.videos[0]["tag"] == "<Video 1>"


def test_audio_tag_order_accounts_for_paired_soundtracks_before_standalone_audio():
    plan = _plan(
        prompt="<Picture 1> is identity. <Audio 1> is the clip soundtrack. <Video 1> provides motion. <Audio 2> is Maya's voice (S1).",
        videos=(VideoReference("video-1", "continuity", "Same-scene continuity.", include_paired_soundtrack=True, audio_intent="Use timing."),),
        standalone_audios=(AudioReference("voice-1", "voice_timbre", "Maya's voice.", "S1"),),
    )
    compiled = compile_r2v_graph(plan, {
        "image-1": _asset("image-1", "image"),
        "video-1": _asset("video-1", "video", ".mp4", interval=(0.0, 5.0), has_audio=True),
        "voice-1": _asset("voice-1", "audio", ".wav"),
    })
    assert [item["tag"] for item in compiled.reference_map.audios] == ["<Audio 1>", "<Audio 2>"]
    assert compiled.reference_map.speaker_audio_tags == {"S1": "<Audio 2>"}


def test_two_character_dialogue_maps_each_voice_reference_to_stable_speaker_tags():
    prompt = ("<Picture 1> defines both characters. <Audio 1> is Maya's voice-timbre reference for speaker (S1). "
              'Maya (S1) says "We should go." <Audio 2> is Leena\'s voice-timbre reference for speaker (S2). '
              'Leena (S2) replies "I am ready."')
    plan = _plan(prompt=prompt, standalone_audios=(
        AudioReference("maya-voice", "voice_excerpt", "Voice timbre only; do not repeat source words.", "S1"),
        AudioReference("leena-voice", "voice_excerpt", "Voice timbre only; do not repeat source words.", "S2"),
    ))
    compiled = compile_r2v_graph(plan, {
        "image-1": _asset("image-1", "image"),
        "maya-voice": _asset("maya-voice", "audio", ".wav"),
        "leena-voice": _asset("leena-voice", "audio", ".wav"),
    })
    assert compiled.reference_map.speaker_audio_tags == {"S1": "<Audio 1>", "S2": "<Audio 2>"}
    assert [item["role"] for item in compiled.reference_map.audios] == ["voice_excerpt", "voice_excerpt"]
    assert [item["speaker_id"] for item in compiled.reference_map.audios] == ["S1", "S2"]
    assert len([node for node in compiled.graph.values() if node.get("class_type") == "LoadAudio"]) == 2
    assert compiled.graph["136"]["inputs"]["ref_audios.ref_audio_0"]
    assert compiled.graph["136"]["inputs"]["ref_audios.ref_audio_1"]


def test_maximum_reference_counts_compile_with_sequential_tags():
    images = tuple(ImageReference(f"image-{i}", "reference", f"Picture {i}.") for i in range(9))
    videos = tuple(VideoReference(f"video-{i}", "action", f"Video {i}.", include_paired_soundtrack=True, audio_intent=f"Audio {i} timing.") for i in range(3))
    audios = tuple(AudioReference(f"audio-{i}", "voice", f"Voice {i}.", f"S{i + 1}") for i in range(3))
    all_tags = [*(f"<Picture {i}>" for i in range(1, 10)), *(f"<Video {i}>" for i in range(1, 4)), *(f"<Audio {i}>" for i in range(1, 7))]
    plan = _plan(prompt="Every selected reference is declared: " + " ".join(all_tags) + ". <Audio 4> provides the timbre for speaker (S1). <Audio 5> provides the timbre for speaker (S2). <Audio 6> provides the timbre for speaker (S3).", images=images, videos=videos, standalone_audios=audios)
    asset_index = {f"image-{i}": _asset(f"image-{i}", "image") for i in range(9)}
    asset_index.update({f"video-{i}": _asset(f"video-{i}", "video", ".mp4", interval=(0.0, 5.0), has_audio=True) for i in range(3)})
    asset_index.update({f"audio-{i}": _asset(f"audio-{i}", "audio", ".wav") for i in range(3)})

    result = compile_r2v_graph(plan, asset_index)

    assert len(result.reference_map.pictures) == 9
    assert len(result.reference_map.videos) == 3
    assert len(result.reference_map.audios) == 6
    assert result.reference_map.speaker_audio_tags == {"S1": "<Audio 4>", "S2": "<Audio 5>", "S3": "<Audio 6>"}
    assert len([node for node in result.graph.values() if node.get("class_type") == "VHS_LoadVideo"]) == 3
    assert len([node for node in result.graph.values() if node.get("class_type") == "LoadAudio"]) == 3


@pytest.mark.parametrize("field,value", [
    ("images", tuple(ImageReference(f"i{x}", "r", "intent") for x in range(10))),
    ("videos", tuple(VideoReference(f"v{x}", "r", "intent") for x in range(4))),
    ("standalone_audios", tuple(AudioReference(f"a{x}", "r", "intent") for x in range(4))),
])
def test_reference_count_limits_are_enforced(field, value):
    with pytest.raises(GraphPlanError, match="Reference counts exceed"):
        validate_reference_plan(_plan(**{field: value}))


def test_zero_reference_plan_is_routed_out_of_r2v():
    plan = _plan(prompt="A person waits in the rain.", images=())
    with pytest.raises(GraphPlanError) as error:
        compile_r2v_graph(plan, {})
    assert error.value.code == "zero_reference_route"
    assert "T2V" in str(error.value)


def test_path_like_or_unhashed_resolved_asset_is_rejected():
    plan = _plan()
    with pytest.raises(GraphPlanError) as error:
        resolve_reference_assets(plan, {"image-1": ResolvedAsset("image-1", "image", "../secret.png", SHA)})
    assert error.value.code == "unsafe_staged_filename"

    with pytest.raises(GraphPlanError) as error:
        resolve_reference_assets(plan, {"image-1": ResolvedAsset("image-1", "image", "image.png", "not-a-hash")})
    assert error.value.code == "invalid_asset_hash"


def test_video_interval_must_be_staged_exactly_before_compile():
    plan = _plan(
        prompt="<Picture 1> is identity and <Video 1> gives movement.",
        videos=(VideoReference("video-1", "action", "Transfer movement.", 2.0, 5.0),),
    )
    with pytest.raises(GraphPlanError) as error:
        compile_r2v_graph(plan, {"image-1": _asset("image-1", "image"), "video-1": _asset("video-1", "video", ".mp4")})
    assert error.value.code == "asset_interval_not_staged"

    result = compile_r2v_graph(plan, {
        "image-1": _asset("image-1", "image"),
        "video-1": _asset("video-1", "video", ".mp4", interval=(2.0, 5.0)),
    })
    assert result.reference_map.videos[0]["interval"] == [2.0, 5.0]

    whole_source = _plan(
        prompt="<Picture 1> is identity and <Video 1> provides motion.",
        videos=(VideoReference("video-1", "action", "Use the short source."),),
    )
    result = compile_r2v_graph(whole_source, {
        "image-1": _asset("image-1", "image"),
        "video-1": _asset("video-1", "video", ".mp4", interval=(0.0, 3.0)),
    })
    assert result.reference_map.videos[0]["interval"] == [0.0, 3.0]


@pytest.mark.parametrize("prompt,code", [
    ("<Picture 1> and <Video 1>.", "prompt_reference_tags_mismatch"),
    ("<Picture 1> and <Picture 2>.", "prompt_reference_tags_mismatch"),
])
def test_prompt_tags_must_match_selected_references(prompt, code):
    plan = _plan(prompt=prompt)
    with pytest.raises(GraphPlanError) as error:
        compile_r2v_graph(plan, {"image-1": _asset("image-1", "image")})
    assert error.value.code == code


def test_speaker_voice_must_be_named_in_prompt():
    plan = _plan(
        prompt="<Picture 1> is Maya. <Audio 1> is a voice reference.",
        standalone_audios=(AudioReference("voice-1", "voice", "Maya timbre", "S1"),),
    )
    with pytest.raises(GraphPlanError) as error:
        compile_r2v_graph(plan, {"image-1": _asset("image-1", "image"), "voice-1": _asset("voice-1", "audio", ".wav")})
    assert error.value.code == "speaker_reference_unbound"


def test_invalid_interval_duration_resolution_and_aspect_ratio_fail_early():
    cases = [
        (_plan(duration_seconds=4.9), "invalid_duration"),
        (_plan(duration_seconds=15.1), "invalid_duration"),
        (_plan(resolution_preset=0.7), "unsupported_resolution_preset"),
        (_plan(aspect_ratio="9:16"), "unsupported_aspect_ratio"),
        (_plan(videos=(VideoReference("video-1", "action", "intent", 0, 16),)), "video_interval_too_long"),
    ]
    for plan, expected in cases:
        with pytest.raises(GraphPlanError) as error:
            validate_reference_plan(plan)
        assert error.value.code == expected


def test_live_capability_preflight_reports_missing_nodes_and_accepts_schema_fixture():
    with pytest.raises(GraphPlanError) as error:
        validate_comfy_capabilities({})
    assert error.value.code == "comfy_nodes_missing"

    fixture = {
        name: {"input": {"required": {}, "optional": {}}}
        for name in ("LoadImage", "LoadAudio", "VHS_LoadVideo", "CreateVideo", "SaveVideo", "MiniMaxH3ReferenceToVideo")
    }
    fixture["MiniMaxH3ReferenceToVideo"]["input"]["required"] = {key: [] for key in ("clip", "vae", "audio_vae", "prompt", "width", "height", "length", "ref_image_size")}
    fixture["MiniMaxH3ReferenceToVideo"]["input"]["optional"] = {key: [] for key in ("ref_images", "ref_videos", "ref_video_audios", "ref_audios")}
    fixture["VHS_LoadVideo"]["input"]["required"] = {key: [] for key in ("video", "force_rate", "custom_width", "custom_height", "frame_load_cap", "skip_first_frames", "select_every_nth")}
    assert validate_comfy_capabilities(fixture)["status"] == "ready"


def test_h3_17k_plus_5_alignment_is_deterministic():
    base = load_base_graph()
    for seconds, frames in ((5.0, 124), (10.0, 243), (15.0, 362)):
        plan = _plan(duration_seconds=seconds)
        result = compile_r2v_graph(plan, {"image-1": _asset("image-1", "image")}, base_graph=base)
        assert result.frame_count == frames
        assert (frames - 5) % 17 == 0
