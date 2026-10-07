"""Regressions for defects identified in the second Sol implementation audit."""
import asyncio
import copy

import pytest

from story_builder.api import main as api
from story_builder.services.director_contract import DirectorContractError, generate_resolved_shot_prompt
from story_builder.services.production_text_controller import build_shot_reference_catalog
from story_builder.services.production_ledger import ProductionLedger
from story_builder.services.production_reconciliation import reconcile_comfyui_takes


def _run(tmp_path, monkeypatch, mode="manual"):
    projects = api.ProjectStore(tmp_path / "projects")
    project = projects.create_project(title="Review fixture", story_input="Mira reaches the station.", automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", projects)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project["id"], api.ProductionV2RunRequest(
        idempotency_key="review-fixture", control_mode=mode)))
    return project["id"], run


def _canon(project_id, run, suffix="0123456789ab"):
    return {"schema_version": 1, "revision_id": f"story-canon-{suffix}", "stage": "story_detail",
        "project_id": project_id, "run_id": run["run_id"], "source_hash": run["config"]["source_story_hash"],
        "review_status": "accepted", "expanded_story": "Mira reaches the station.",
        "chunks": [{"chunk_id": "story_chunk_0001", "expanded_text": "Mira reaches the station."}]}


def _settle(store, project_id, run_id, stage, key, request, result=None, error=None):
    task = store.enqueue(project_id=project_id, run_id=run_id, stage=stage,
                         idempotency_key=key, request=request)
    store.claim(task_id=task["task_id"], owner_token=key)
    if error is not None:
        return store.fail(task_id=task["task_id"], owner_token=key, error=error)
    return store.complete(task_id=task["task_id"], owner_token=key, result=result)


def test_new_story_revision_does_not_reuse_old_outline_or_retry_old_text(tmp_path, monkeypatch):
    project_id, run = _run(tmp_path, monkeypatch, "fully_automated")
    store = api._production_stage_task_store()
    old, new = _canon(project_id, run), _canon(project_id, run, "abcdef123456")
    for canon in (old, new):
        api.production_story_revisions.write_revision(api.OUTPUT_ROOT, project_id, run["run_id"], canon)
    _settle(store, project_id, run["run_id"], "story_detail", "old-story", {}, {"revision_id": old["revision_id"]})
    _settle(store, project_id, run["run_id"], "controller:scene_outline", "old-outline",
        {"source_revision_id": old["revision_id"]}, {"units": [{"unit_id": "old-scene"}]})
    _settle(store, project_id, run["run_id"], "text:scenes", "old-scenes",
        {"source_revision_id": old["revision_id"], "units": []}, error={"retryable": True})
    _settle(store, project_id, run["run_id"], "story_detail", "new-story", {}, {"revision_id": new["revision_id"]})
    api._advance_production_text_controller(project_id, run["run_id"])
    queued = store.queued()
    assert [(row["stage"], row["request"]["source_revision_id"]) for row in queued] == [
        ("controller:scene_outline", new["revision_id"])]
    api._advance_production_text_controller(project_id, run["run_id"])
    assert len(store.queued()) == 1


@pytest.mark.parametrize("mutation", ["forged_map", "copied_id", "repair_invalid", "repair_map",
    "missing_arrays", "unsupported_role", "blank_intent"])
def test_generated_shot_contract_is_enforced_before_and_after_review(tmp_path, monkeypatch, mutation):
    mode = "fully_automated" if mutation.startswith("repair") else "manual"
    project_id, run = _run(tmp_path, monkeypatch, mode)
    canon = _canon(project_id, run)
    api.production_story_revisions.write_revision(api.OUTPUT_ROOT, project_id, run["run_id"], canon)
    content = {"prompt": "Mira reaches the station.", "duration_seconds": 5, "dialogue": [], "asset_intents": []}
    def mutate(row):
        if mutation in {"forged_map", "repair_map"}:
            row.update(prompt="Use <Picture 99>.", reference_map={"pictures": [{"tag": "<Picture 99>"}],
                "videos": [], "audios": [], "speaker_audio_tags": {}})
        elif mutation == "copied_id":
            row["asset_intents"] = [{"asset_id": "pa-invented", "role": "character_master", "intent": "identity"}]
        elif mutation == "missing_arrays":
            row.pop("dialogue")
            row.pop("asset_intents")
        elif mutation == "unsupported_role":
            row["asset_intents"] = [{"role": "made_up", "intent": "identity"}]
        elif mutation == "blank_intent":
            row["asset_intents"] = [{"role": "character_master", "intent": ""}]
        else:
            row.update(prompt="", duration_seconds=200)
    if not mutation.startswith("repair"):
        mutate(content)
    monkeypatch.setattr(api, "generate_chunked_units", lambda **_: {"complete": True,
        "expected_unit_ids": ["shot-1"], "completed_unit_ids": ["shot-1"],
        "items": [{"unit_id": "shot-1", "content": copy.deepcopy(content)}]})
    def review(**kwargs):
        items = copy.deepcopy(kwargs["revision"]["items"])
        mutate(items[0]["content"])
        return {"items": items, "accepted": True, "review_id": "fake-review", "decision": "approve",
            "corpus_version": "h3_prompt_rules_v1", "repair_attempts": 1}
    monkeypatch.setattr(api, "review_text_stage_revision", review)
    with pytest.raises(api.HTTPException) as error:
        api.generate_production_v2_text_stage(project_id, run["run_id"], "shot_plans",
            api.ProductionV2TextStageRequest(source_revision_id=canon["revision_id"],
                units=[{"unit_id": "shot-1", "source_chunk_ids": ["story_chunk_0001"]}]))
    assert error.value.status_code == 422
    assert api.production_story_revisions.list_stage_revisions(api.OUTPUT_ROOT, project_id, run["run_id"], "shot_plans") == []


def test_catalog_rejects_unapproved_generated_master_without_candidate_role():
    catalog = build_shot_reference_catalog(units=[{"unit_id": "shot-1", "character_ids": ["char-1"]}],
        voice_bindings=[], run_id="run-1", assets=[{"asset_id": "pa-1", "kind": "image",
        "source": "project_output", "roles": ["character_master"], "metadata": {"character_id": "char-1"}}])
    assert catalog[0]["images"] == []


def _resolved_kwargs():
    return dict(prompt_seed="Mira speaks.", shot_facts={"duration_seconds": 5},
        dialogue_lines=[{"speaker_id": "S1", "text": "We should go.", "language": "English"}],
        asset_intents=[], reference_map={"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}})


def test_resolved_prompt_cannot_accept_changed_dialogue_even_if_provider_approves():
    def provider(**kwargs):
        if "shot-prompt writer" in kwargs["prompt"]:
            return {"prompt": "Mira (S1): <d>[English] Stay here.</d>"}
        return {"decision": "approve", "confidence": 0.95, "issues": [], "repair_instruction": ""}
    result = generate_resolved_shot_prompt(**_resolved_kwargs(), generator=provider)
    assert result["accepted"] is False
    assert any(row["code"] == "dialogue_contract_mismatch" for row in result["lint"]["errors"])


@pytest.mark.parametrize("reference_map", [{}, {"pictures": [None], "videos": [], "audios": [], "speaker_audio_tags": {}},
    {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {"S1": "<Audio 99>"}}])
def test_resolved_prompt_rejects_malformed_compiler_map_before_provider(reference_map):
    kwargs = _resolved_kwargs()
    kwargs["reference_map"] = reference_map
    with pytest.raises(DirectorContractError):
        generate_resolved_shot_prompt(**kwargs, generator=lambda **_: pytest.fail("invalid map reached provider"))


def test_readonly_reconciler_preserves_confirmed_user_cancellation(tmp_path):
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="film", idempotency_key="run", config={})
    ledger.queue_take(project_id="film", run_id=run["run_id"], shot_id="shot", take_id="take",
                      idempotency_key="take", input_snapshot={})
    ledger.transition_take(project_id="film", take_id="take", status="submitting")
    take = ledger.reserve_prompt_id(project_id="film", take_id="take")
    ledger.transition_take(project_id="film", take_id="take", status="cancel_requested")
    def get_json(url, **_):
        if url.endswith("/queue"):
            return {"queue_running": [], "queue_pending": []}
        return {take["prompt_id"]: {"status": {"status_str": "error", "messages": [
            ["execution_interrupted", {"prompt_id": take["prompt_id"]}]]}}}
    report = reconcile_comfyui_takes(ledger, comfy_url="http://comfy.test", get_json=get_json)
    assert report["updated"][0]["status"] == "cancelled"


def _compiled_prompt():
    from story_builder.services.minimax_h3_graph_compiler import (
        AudioReference, ImageReference, VideoReference, ReferencePlan, ResolvedAsset, compile_r2v_graph)
    prompt = ("<Picture 1> defines Mira. <Video 1> is the preceding cut. <Audio 1> supplies its impacts. "
              "<Audio 2> is Mira's voice reference (S1). Mira (S1): <d>[English] We should go.</d>")
    plan = ReferencePlan(schema_version=1, project_id="film", run_id="run", shot_id="shot", prompt=prompt,
        duration_seconds=5, images=(ImageReference("image", "character_identity", "Mira's appearance"),),
        videos=(VideoReference("video", "continuity", "prior cut", include_paired_soundtrack=True,
                               audio_intent="impacts only"),),
        standalone_audios=(AudioReference("voice", "voice_timbre", "Mira's timbre", "S1"),))
    compiled = compile_r2v_graph(plan, {
        "image": ResolvedAsset("image", "image", "image.png", "a" * 64),
        "video": ResolvedAsset("video", "video", "video.mp4", "b" * 64, 0, 5, True),
        "voice": ResolvedAsset("voice", "audio", "voice.wav", "c" * 64)})
    return prompt, compiled.reference_map.as_dict()


def test_resolved_prompt_uses_real_compiler_tags_and_frozen_context():
    prompt, compiled_map = _compiled_prompt()
    original = copy.deepcopy(compiled_map)
    kwargs = _resolved_kwargs()
    kwargs["reference_map"] = compiled_map
    calls = []
    def provider(**call):
        calls.append(call)
        if "shot-prompt writer" in call["prompt"]:
            # A caller's mutable map must not change the snapshot used for lint/review.
            compiled_map["pictures"][0]["asset_id"] = "changed-after-call"
            return {"prompt": prompt}
        return {"decision": "approve", "confidence": 0.95, "issues": [], "repair_instruction": ""}
    result = generate_resolved_shot_prompt(**kwargs, generator=provider, provider="codex")
    assert result["accepted"] and not result["repair_attempted"]
    assert result["reference_map"] == original
    assert len(calls) == 2 and all(row["provider"] == "codex" for row in calls)
    assert "<Audio 2>" in calls[1]["prompt"] and '"asset_id":"image"' in calls[1]["prompt"]
    assert len(result["input_hash"]) == len(result["prompt_hash"]) == 64


def test_resolved_prompt_performs_one_targeted_semantic_repair_and_review():
    calls = []
    def provider(**call):
        calls.append(call["prompt"])
        if "shot-prompt writer" in call["prompt"]:
            return {"prompt": "Mira (S1): <d>[English] We should go.</d>"}
        if len(calls) == 2:
            return {"decision": "repair", "confidence": 0.9, "issues": ["Camera is vague."],
                    "repair_instruction": "State a medium close-up."}
        return {"decision": "approve", "confidence": 0.9, "issues": [], "repair_instruction": ""}
    result = generate_resolved_shot_prompt(**_resolved_kwargs(), generator=provider)
    assert result["accepted"] and result["repair_attempted"]
    assert len(calls) == 4 and "Camera is vague." in calls[2]
    assert [row["accepted"] for row in result["review_history"]] == [False, True]


@pytest.mark.parametrize("bad_confidence", [True, float("nan"), float("inf"), -1, 2])
def test_resolved_prompt_rejects_invalid_review_confidence(bad_confidence):
    def provider(**call):
        if "shot-prompt writer" in call["prompt"]:
            return {"prompt": "Mira (S1): <d>[English] We should go.</d>"}
        return {"decision": "approve", "confidence": bad_confidence, "issues": [], "repair_instruction": ""}
    with pytest.raises(DirectorContractError, match="strict JSON"):
        generate_resolved_shot_prompt(**_resolved_kwargs(), generator=provider)


def test_resolved_prompt_nonempty_review_issues_prevent_acceptance():
    def provider(**call):
        if "shot-prompt writer" in call["prompt"]:
            return {"prompt": "Mira (S1): <d>[English] We should go.</d>"}
        return {"decision": "approve", "confidence": 0.9, "issues": ["Missing accepted action."], "repair_instruction": ""}
    result = generate_resolved_shot_prompt(**_resolved_kwargs(), generator=provider)
    assert not result["accepted"] and len(result["review_history"]) == 2


@pytest.mark.parametrize("duration", [True, "5", float("nan"), float("inf"), 200])
def test_resolved_prompt_rejects_invalid_duration_before_provider(duration):
    kwargs = _resolved_kwargs()
    kwargs["shot_facts"] = {"duration_seconds": duration}
    with pytest.raises(DirectorContractError):
        generate_resolved_shot_prompt(**kwargs, generator=lambda **_: pytest.fail("invalid duration reached provider"))


def test_resolved_prompt_rejects_stale_run_corpus_before_provider():
    with pytest.raises(DirectorContractError, match="saved run snapshot"):
        generate_resolved_shot_prompt(**_resolved_kwargs(), expected_corpus_hash="changed",
            generator=lambda **_: pytest.fail("stale corpus reached provider"))


@pytest.mark.parametrize("candidate", [
    "Mira (S2): <d>[English] We should go.</d>",
    "Mira (S1): <d>[Hindi] We should go.</d>",
    "Mira (S1): <d>[English] We should go.</d> Mira (S1): <d>[English] Extra line.</d>",
    "Mira (S1): <d>[English] We should go.</d> <d>Malformed</d>"])
def test_resolved_prompt_rejects_changed_speaker_language_or_extra_dialogue(candidate):
    result = generate_resolved_shot_prompt(**_resolved_kwargs(), generator=lambda **_: {"prompt": candidate})
    assert not result["accepted"] and result["repair_attempted"]


@pytest.mark.parametrize("stage", ["story", "text"])
@pytest.mark.parametrize("bad_field", [{"confidence": True}, {"decision": []}])
def test_existing_director_reviews_reject_malformed_schema(stage, bad_field):
    from story_builder.services.director_contract import review_story_revision, review_text_stage_revision
    response = {"decision": "approve", "confidence": 0.9, "issues": [], "repair_instruction": "", **bad_field}
    if stage == "story":
        call = review_story_revision
        revision = {"chunks": [{"chunk_id": "chunk-1", "expanded_text": "Mira leaves."}]}
    else:
        call = review_text_stage_revision
        revision = {"stage": "scenes", "complete": True, "expected_unit_ids": ["scene-1"],
            "completed_unit_ids": ["scene-1"], "items": [{"unit_id": "scene-1", "content": {"summary": "Mira leaves."}}]}
    with pytest.raises(DirectorContractError):
        call(revision=revision, generator=lambda **_: response)


@pytest.mark.parametrize("wrong_prefix", [False, True])
def test_resolved_prompt_maps_canonical_uuid_to_h3_speaker_label(wrong_prefix):
    speaker = "2c35b097-3a51-4fbc-8584-744bb1b221ff"
    kwargs = _resolved_kwargs()
    kwargs["dialogue_lines"][0]["speaker_id"] = speaker
    calls = []
    def provider(**call):
        calls.append(call["prompt"])
        assert f'"speaker_labels":{{"{speaker}":"S1"}}' in call["prompt"]
        if "shot-prompt writer" in call["prompt"]:
            label = speaker if wrong_prefix else "S1"
            return {"prompt": f"Mira is (S1), bound to {speaker}. Mira ({label}): <d>[English] We should go.</d>"}
        return {"decision": "approve", "confidence": 0.95, "issues": [], "repair_instruction": ""}
    result = generate_resolved_shot_prompt(**kwargs, generator=provider)
    assert result["speaker_labels"] == {speaker: "S1"}
    assert result["accepted"] is (not wrong_prefix)
    if wrong_prefix:
        assert all("shot-prompt writer" in call for call in calls)
    else:
        assert "authoritative canonical-ID-to-local-S-label mapping" in calls[1]


def test_resolved_prompt_keeps_two_speakers_and_repeated_lines_bound():
    kwargs = _resolved_kwargs()
    kwargs["dialogue_lines"] = [
        {"speaker_id": "char-mira", "text": "Go."},
        {"speaker_id": "char-arun", "text": "Yes."},
        {"speaker_id": "char-mira", "text": "Now."}]
    def provider(**call):
        if "shot-prompt writer" in call["prompt"]:
            return {"prompt": "Mira (S1): <d>[English] Go.</d> Arun (S2): <d>[English] Yes.</d> Mira (S1): <d>[English] Now.</d>"}
        return {"decision": "approve", "confidence": 0.95, "issues": [], "repair_instruction": ""}
    result = generate_resolved_shot_prompt(**kwargs, generator=provider)
    assert result["accepted"]
    assert result["speaker_labels"] == {"char-mira": "S1", "char-arun": "S2"}



def test_reference_route_requires_wrapper_character_and_world_identities():
    from story_builder.services.production_route_assets import enforce_route_assets, RouteAssetError
    shot = {"unit_id": "cut-1", "character_ids": ["char-mira", "char-arun"],
        "world_id": "world-stairs", "content": {"asset_intents": [], "dialogue": []}}
    content = api._bound_shot_content(shot)
    assert "characters" not in shot["content"]
    with pytest.raises(RouteAssetError) as error:
        enforce_route_assets(route="reference_built", shot_content=content, selected_images=[],
            get_asset=lambda _: pytest.fail("empty selection must not resolve media"))
    assert error.value.details["missing_roles"] == {"character_master": 2, "world_master": 1}
    assets = {
        "mira": {"kind": "image", "source": "project_output", "roles": ["character_master"],
            "metadata": {"approval_status": "accepted", "character_id": "char-mira"}},
        "arun": {"kind": "image", "source": "project_output", "roles": ["character_master"],
            "metadata": {"approval_status": "accepted", "character_id": "char-arun"}},
        "stairs": {"kind": "image", "source": "project_output", "roles": ["world_master"],
            "metadata": {"approval_status": "accepted", "world_id": "world-stairs"}}}
    result = enforce_route_assets(route="reference_built", shot_content=content,
        selected_images=[{"asset_id": key, "role": value["roles"][0]} for key,value in assets.items()],
        get_asset=assets.__getitem__)
    assert result["satisfied"] and result["selected_roles"] == result["required_roles"]


@pytest.mark.parametrize("content", [{"characters": ["someone-else"]}, {"world_id": "other-world"}])
def test_bound_shot_identity_conflicts_are_held(content):
    with pytest.raises(api.HTTPException) as error:
        api._bound_shot_content({"character_ids": ["char-mira"], "world_id": "world-stairs", "content": content})

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "shot_identity_conflict"


def test_persisted_reference_shot_cannot_skip_masters_from_wrapper_fields(tmp_path, monkeypatch):
    project_id, _ = _run(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="reference-wrapper", control_mode="manual", making_route="reference_built")))
    revision = {"schema_version": 1, "revision_id": "shot_plans-eeeeeeeeeeee", "stage": "shot_plans",
        "review_status": "accepted", "items": [{"unit_id": "cut-01", "character_ids": ["char-mira"],
        "world_id": "world-stairs", "content": {"prompt": "Mira stands in the stairwell.", "asset_intents": []}}]}
    api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id, run["run_id"], "shot_plans", revision)
    reopened = ProductionLedger(api.STORAGE_ROOT / "production" / "v2_ledger.sqlite3")
    assert reopened.get_run(project_id=project_id, run_id=run["run_id"])["config"]["making_route"] == "reference_built"
    monkeypatch.setattr(api, "validate_and_compile_shot", lambda *_a, **_k: pytest.fail("missing masters reached compiler"))
    with pytest.raises(api.HTTPException) as error:
        api.validate_production_v2_shot(project_id, run["run_id"], "cut-01",
            api.ProductionV2ShotValidateRequest(shot_plan_revision_id=revision["revision_id"], prompt="Mira stands."))
    assert error.value.status_code == 422
    assert error.value.detail["code"] == "required_master_assets_missing"
    assert error.value.detail["details"]["missing_roles"] == {"character_master": 1, "world_master": 1}
    assert reopened.get_run(project_id=project_id, run_id=run["run_id"])["takes"] == []



def test_resolved_local_speaker_label_preserves_real_compiler_voice_uuid():
    from story_builder.services.minimax_h3_graph_compiler import (
        AudioReference, ReferencePlan, ResolvedAsset, compile_r2v_graph)
    speaker = "2c35b097-3a51-4fbc-8584-744bb1b221ff"
    prompt = f"<Audio 1> is Mira's voice reference ({speaker}). Mira (S1): <d>[English] We should go.</d>"
    plan = ReferencePlan(schema_version=1, project_id="film", run_id="run", shot_id="shot", prompt=prompt,
        duration_seconds=5, standalone_audios=(AudioReference("voice", "voice_timbre", "Mira's voice", speaker),))
    compiled = compile_r2v_graph(plan, {"voice": ResolvedAsset("voice", "audio", "voice.wav", "a" * 64)})
    kwargs = _resolved_kwargs()
    kwargs["dialogue_lines"][0]["speaker_id"] = speaker
    kwargs["reference_map"] = compiled.reference_map.as_dict()
    def provider(**call):
        if "shot-prompt writer" in call["prompt"]:
            return {"prompt": prompt}
        return {"decision": "approve", "confidence": 0.95, "issues": [], "repair_instruction": ""}
    result = generate_resolved_shot_prompt(**kwargs, generator=provider)
    assert result["accepted"]
    assert result["speaker_labels"] == {speaker: "S1"}
    assert result["reference_map"]["speaker_audio_tags"] == {speaker: "<Audio 1>"}


def test_accepted_legacy_scene_alias_is_read_only_and_shot_scoped():
    content = {"title": "Station", "shots": [
        {"shot_id": "shot-2", "beat": "Maya asks.", "emotion": "Urgent"},
        {"shot_id": "shot-3", "beat": "Arjun answers."}]}
    original = copy.deepcopy(content)
    context = api._dialogue_context_for_shot(content, {"unit_id": "shot-2"})
    assert context["shot"] == {"beat": "Maya asks.", "emotion": "Urgent"}
    assert content == original
    # The new-output boundary is deliberately stricter than legacy reads.
    units = [{"unit_id": "scene-1", "shot_units": [{"unit_id": "shot-2"}, {"unit_id": "shot-3"}]}]
    with pytest.raises(api.HTTPException):
        api._validate_generated_scene_items([{ "unit_id": "scene-1", "content": content}], units)


@pytest.mark.parametrize("beats", [
    [{"unit_id": "shot-2", "shot_id": "shot-3", "beat": "Wrong identity"}],
    [{"unit_id": "shot-2", "beat": "One"}, {"shot_id": "shot-2", "beat": "Two"}],
    [{"beat": "No identity"}], [{"shot_id": "shot-2", "beat": ""}],
    [{"shot_id": "shot-3", "beat": "Wrong shot"}],
])
def test_legacy_scene_alias_rejects_ambiguous_missing_and_unrelated_beats(beats):
    with pytest.raises(ValueError):
        api._dialogue_context_for_shot({"shots": beats}, {"unit_id": "shot-2"})


def _legacy_dialogue_binding_fixture():
    scenes = [{"unit_id": "scene-1", "character_ids": ["Mira"],
        "shot_units": [{"unit_id": "shot-1"}, {"unit_id": "shot-2"}],
        "content": {"shots": [{"unit_id": "shot-1", "beat": "Mira asks."},
            {"unit_id": "shot-2", "beat": "A pause."}]}}]
    revision = {"items": [{"unit_id": "dialogue-1", "scene_id": "scene-1", "content": {"beats": [
        {"beat": "A pause.", "dialogue": []},
        {"beat": "Mira asks.", "dialogue": [{"speaker_id": "Mira", "text": "Ready?"}]}]}}]}
    return scenes, revision


def test_accepted_legacy_dialogue_binds_exact_beats_without_position_or_mutation():
    scenes, revision = _legacy_dialogue_binding_fixture()
    original = copy.deepcopy((scenes, revision))
    bound = api._attach_accepted_dialogue_to_shots(scenes, revision)
    assert bound[0]["approved_dialogue_lines"] == [{"speaker_id": "Mira", "text": "Ready?"}]
    assert bound[1]["approved_dialogue_lines"] == []
    assert (scenes, revision) == original


@pytest.mark.parametrize("damage", ["changed_beat", "duplicate_beat", "missing_beat", "foreign_speaker", "wrong_scene"])
def test_accepted_legacy_dialogue_rejects_ambiguous_bindings(damage):
    scenes, revision = _legacy_dialogue_binding_fixture()
    item = revision["items"][0]; beats = item["content"]["beats"]
    if damage == "changed_beat": beats[0]["beat"] = "Different pause."
    elif damage == "duplicate_beat": beats.append(copy.deepcopy(beats[0]))
    elif damage == "missing_beat": beats.pop()
    elif damage == "foreign_speaker": beats[1]["dialogue"][0]["speaker_id"] = "Foreign"
    elif damage == "wrong_scene": item["scene_id"] = "scene-2"
    with pytest.raises(ValueError):
        api._attach_accepted_dialogue_to_shots(scenes, revision)
