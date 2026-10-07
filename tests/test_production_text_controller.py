import asyncio
import hashlib
import io
import json

import pytest
from PIL import Image

from story_builder.api import main as api
from story_builder.services.production_ledger import ProductionLedger
from story_builder.services.production_stage_tasks import ProductionStageTaskStore
from story_builder.services.production_text_controller import (
    SceneOutlineError,
    ShotReferenceResolutionError,
    build_shot_reference_catalog,
    plan_scene_outline,
    reconcile_outline_identities,
    resolve_shot_reference_catalog,
)


def test_accepted_dialogue_is_bound_to_the_matching_shot_in_scene_order():
    scenes = [{"unit_id": "scene-1", "shot_units": [
        {"unit_id": "shot-1", "shot_index": 1}, {"unit_id": "shot-2", "shot_index": 2}]}]
    dialogue = {"items": [
        {"unit_id": "shot-1", "scene_id": "scene-1", "content": {
            "dialogue": [{"speaker_id": "char-maya", "text": "The storm is coming."}]}},
        {"unit_id": "shot-2", "scene_id": "scene-1", "content": {"dialogue": []}}]}

    result = api._attach_accepted_dialogue_to_shots(scenes, dialogue)

    assert [row["approved_dialogue_lines"] for row in result] == [
        [{"speaker_id": "char-maya", "text": "The storm is coming."}], []]
    with pytest.raises(ValueError, match="missing the shot-scoped dialogue array"):
        api._attach_accepted_dialogue_to_shots(scenes, {"items": [
            {"unit_id": "shot-1", "scene_id": "scene-1", "content": {"beats": [{"dialogue": []}]}},
            {"unit_id": "shot-2", "scene_id": "scene-1", "content": {"dialogue": []}}]})


@pytest.mark.parametrize(("dialogue", "message"), [
    ([{"unit_id": "shot-1", "scene_id": "scene-1", "content": {"dialogue": []}},
      {"unit_id": "shot-2", "scene_id": "scene-2", "content": {"dialogue": []}}], "wrong scene"),
    ([{"unit_id": "shot-1", "scene_id": "scene-1", "content": {"dialogue": []}},
      {"unit_id": "shot-2", "scene_id": "scene-1", "content": {"dialogue": []}},
      {"unit_id": "unplanned-shot", "scene_id": "scene-1", "content": {"dialogue": []}}], "unplanned shot"),
    ([{"unit_id": "shot-1", "scene_id": "scene-1", "content": {"dialogue": []}}], "missing planned shot links"),
])
def test_accepted_dialogue_must_map_exactly_to_same_scene_shot_ids(dialogue, message):
    scenes = [{"unit_id": "scene-1", "shot_units": [
        {"unit_id": "shot-1"}, {"unit_id": "shot-2"}]}]

    with pytest.raises(ValueError, match=message):
        api._attach_accepted_dialogue_to_shots(scenes, {"items": dialogue})


def test_controller_progresses_one_accepted_shot_at_a_time_and_resets_at_scene_boundary():
    shots = [{"unit_id": "cut-1", "scene_id": "scene-a"},
        {"unit_id": "cut-2", "scene_id": "scene-a"},
        {"unit_id": "cut-3", "scene_id": "scene-b"}]
    revision_id = "shot_plans-current"
    def take(shot_id, take_id, status, revision=revision_id):
        return {"shot_id": shot_id, "take_id": take_id, "status": status,
            "input_snapshot": {"shot_plan_revision_id": revision}}
    assert api._next_controller_shot(shots, [], shot_plan_revision_id=revision_id) == (shots[0], None)
    first_accepted = [take("cut-1", "take-1", "accepted")]
    assert api._next_controller_shot(shots, first_accepted, shot_plan_revision_id=revision_id) == (shots[1], "take-1")
    both_accepted = first_accepted + [take("cut-2", "take-2", "accepted")]
    assert api._next_controller_shot(shots, both_accepted, shot_plan_revision_id=revision_id) == (shots[2], None)
    assert api._next_controller_shot(shots, [take("cut-1", "take-1", "accepted"),
        take("cut-2", "take-2", "running")], shot_plan_revision_id=revision_id) is None
    assert api._next_controller_shot(shots, [take("cut-1", "take-1", "accepted"),
        take("cut-1", "retake", "accepted")], shot_plan_revision_id=revision_id) is None
    assert api._next_controller_shot(shots, [take("unknown-shot", "foreign", "accepted")],
        shot_plan_revision_id=revision_id) is None
    assert api._next_controller_shot(shots, [take("cut-1", "old-take", "accepted", "shot_plans-old")],
        shot_plan_revision_id=revision_id) is None


def test_accepted_visual_master_design_uses_exact_ids_and_rejects_conflicts():
    revision = {"stage": "visual_briefs", "review_status": "accepted", "revision_id": "visual-rev",
        "items": [{"unit_id": "visual-1", "content": {"continuity": {
            "visible_characters_and_animal": [{"id": "character-1", "identity": "Mira",
                "proposed_design_choice": "Red coat"}],
            "location": {"id": "world-1", "identifier": "North station"}}}}]}
    exact = api._accepted_visual_master_design("character-1", "character_master", revision)
    assert exact["design"] == "Red coat"
    assert exact["provenance"]["entity_id"] == "character-1"
    assert exact["provenance"]["field"].endswith("proposed_design_choice")
    assert api._accepted_visual_master_design("character-2", "character_master", revision) is None
    assert api._accepted_visual_master_design("world-1", "world_master", revision)["design"] == "North station"

    conflicting = {**revision, "items": revision["items"] + [{"unit_id": "visual-2", "content": {
        "continuity": {"visible_characters_and_animal": [{"id": "character-1", "identity": "Mira",
            "proposed_design_choice": "Blue coat"}]}}}]}
    with pytest.raises(ValueError, match="conflicting designs"):
        api._accepted_visual_master_design("character-1", "character_master", conflicting)


def test_controller_records_one_hold_for_legacy_scene_beats_without_stable_shot_ids(tmp_path, monkeypatch):
    projects = api.ProjectStore(tmp_path / "projects")
    project = projects.create_project(title="Legacy scene fixture", story_input="Mira reaches the stairwell.",
                                      automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", projects)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project["id"], api.ProductionV2RunRequest(
        idempotency_key="legacy-scene-run", control_mode="fully_automated")))
    canon = {**_canon(), "project_id": project["id"], "run_id": run["run_id"],
        "source_hash": run["config"]["source_story_hash"], "review_status": "accepted"}
    api.production_story_revisions.write_revision(api.OUTPUT_ROOT, project["id"], run["run_id"], canon)
    store = api._production_stage_task_store()

    story = store.enqueue(project_id=project["id"], run_id=run["run_id"], stage="story_detail",
        idempotency_key="accepted-story", request={})
    store.claim(task_id=story["task_id"], owner_token="story-worker")
    store.complete(task_id=story["task_id"], owner_token="story-worker",
        result={"revision_id": canon["revision_id"], "revision_stage": "story_detail"})
    shot_units = [{"unit_id": "shot-1", "shot_outline": {"action": "Mira reaches the stairwell."}}]
    outline = store.enqueue(project_id=project["id"], run_id=run["run_id"], stage="controller:scene_outline",
        idempotency_key="accepted-outline", request={"source_revision_id": canon["revision_id"]})
    store.claim(task_id=outline["task_id"], owner_token="outline-worker")
    store.complete(task_id=outline["task_id"], owner_token="outline-worker",
        result={"units": [{"unit_id": "scene-1", "shot_units": shot_units}]})
    scene_revision = {"revision_id": "scenes-abcdef123456", "project_id": project["id"], "run_id": run["run_id"],
        "stage": "scenes", "source_revision_id": canon["revision_id"], "source_story_hash": canon["source_hash"],
        "review_status": "accepted", "items": [{"unit_id": "scene-1", "shot_units": shot_units,
            "content": {"shots": [{"beat": "Mira reaches the stairwell."}]}}]}
    api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project["id"], run["run_id"],
        "scenes", scene_revision)
    scenes = store.enqueue(project_id=project["id"], run_id=run["run_id"], stage="text:scenes",
        idempotency_key="legacy-scenes", request={"source_revision_id": canon["revision_id"]})
    store.claim(task_id=scenes["task_id"], owner_token="scenes-worker")
    store.complete(task_id=scenes["task_id"], owner_token="scenes-worker",
        result={"revision_id": scene_revision["revision_id"], "revision_stage": "text:scenes"})

    api._advance_production_text_controller(project["id"], run["run_id"])
    api._advance_production_text_controller(project["id"], run["run_id"])

    persisted = api._production_v2_ledger().get_run(project_id=project["id"], run_id=run["run_id"])
    holds = [event for event in persisted["events"]
        if event["event_type"] == "controller_scene_shot_binding_blocked"]
    assert len(holds) == 1
    assert holds[0]["payload"]["scene_revision_id"] == "scenes-abcdef123456"
    assert not [task for task in store.list_run(project_id=project["id"], run_id=run["run_id"])
        if task["stage"] in {"text:dialogue", "text:visual_briefs", "text:shot_plans"}]
    # Run-detail responses expose only the latest 500 events. Idempotency
    # must survive an older hold leaving that window and ledger reopen.
    ledger = api._production_v2_ledger()
    for index in range(501):
        ledger.record_run_event(project_id=project["id"], run_id=run["run_id"],
            event_type="later_activity", payload={"index": index})
    api._advance_production_text_controller(project["id"], run["run_id"])
    with ledger._connect() as db:
        count = db.execute("SELECT COUNT(*) FROM production_events WHERE project_id=? AND run_id=? "
            "AND event_type='controller_scene_shot_binding_blocked'",
            (project["id"], run["run_id"])).fetchone()[0]
    assert count == 1


@pytest.mark.parametrize("retake_count", [1, 2])
def test_controller_advances_after_durable_retake_decision_and_accepted_replacement(tmp_path, retake_count):
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="film", idempotency_key="run", config={"control_mode": "fully_automated"})
    revision = "shot_plans-current"
    shots = [{"unit_id": "cut-1", "scene_id": "scene-a"},
        {"unit_id": "cut-2", "scene_id": "scene-a"}]

    def render_to_review(take_id, lineage=None):
        take = ledger.queue_take(project_id="film", run_id=run["run_id"], shot_id="cut-1",
            take_id=take_id, idempotency_key=take_id,
            input_snapshot={"shot_plan_revision_id": revision, **(lineage or {})})
        ledger.transition_take(project_id="film", take_id=take_id, status="submitting")
        prompt = ledger.reserve_prompt_id(project_id="film", take_id=take_id)["prompt_id"]
        ledger.bind_prompt_id(project_id="film", take_id=take_id, prompt_id=prompt)
        ledger.transition_take(project_id="film", take_id=take_id, status="collecting")
        return ledger.transition_take(project_id="film", take_id=take_id, status="needs_review")

    replacement = render_to_review("cut-1-attempt-1")
    for index in range(retake_count):
        original = replacement
        decision = {"action": "retake", "reason": f"continuity {index}"}
        next_id = f"cut-1-attempt-{index + 2}"
        ledger.record_director_video_review(take=original, decision=decision)
        ledger.resolve_director_video_review(job_id=original["job_id"], status="retake_queued",
            retake_take_id=next_id)
        replacement = render_to_review(next_id, {
            "director_retake_of_take_id": original["take_id"],
            "director_retake_root_take_id": "cut-1-attempt-1",
            "director_retake_decision_hash": hashlib.sha256(
                json.dumps(decision, sort_keys=True).encode()).hexdigest()[:16]})
    ledger.record_director_video_review(take=replacement, decision={"action": "accept"})
    ledger.accept_take(project_id="film", run_id=run["run_id"], take_id=replacement["take_id"])
    ledger.resolve_director_video_review(job_id=replacement["job_id"], status="accepted")

    reopened = ProductionLedger(ledger.path).get_run(project_id="film", run_id=run["run_id"])
    assert api._next_controller_shot(shots, reopened["takes"],
        shot_plan_revision_id=revision) == (shots[1], replacement["take_id"])


def test_controller_rejects_unresolved_or_conflicting_retake_history():
    shots = [{"unit_id": "cut-1", "scene_id": "scene-a"},
        {"unit_id": "cut-2", "scene_id": "scene-a"}]
    revision = "shot_plans-current"
    def take(take_id, status, review=None):
        return {"take_id": take_id, "shot_id": "cut-1", "status": status,
            "input_snapshot": {"shot_plan_revision_id": revision}, "director_review": review}
    accepted = take("winner", "accepted", {"resolution_status": "accepted"})
    unresolved = take("old", "needs_review", None)
    assert api._next_controller_shot(shots, [accepted, unresolved],
        shot_plan_revision_id=revision) is None
    conflicting = take("other-winner", "accepted", {"resolution_status": "accepted"})
    assert api._next_controller_shot(shots, [accepted, conflicting],
        shot_plan_revision_id=revision) is None


@pytest.mark.parametrize("mutation", ["source", "root", "decision", "active_source"])
def test_controller_retake_winner_requires_reciprocal_frozen_lineage(mutation):
    decision = {"action": "retake", "reason": "framing"}
    source = {"take_id": "original", "status": "needs_review", "director_review": {
        "resolution_status": "retake_queued", "retake_take_id": "winner", "decision": decision},
        "input_snapshot": {}}
    snapshot = {"director_retake_of_take_id": "original", "director_retake_root_take_id": "original",
        "director_retake_decision_hash": hashlib.sha256(json.dumps(decision, sort_keys=True).encode()).hexdigest()[:16]}
    if mutation == "active_source":
        source["status"] = "running"
    else:
        key = {"source": "director_retake_of_take_id", "root": "director_retake_root_take_id",
            "decision": "director_retake_decision_hash"}[mutation]
        snapshot[key] = "unrelated"
    winner = {"take_id": "winner", "status": "accepted", "input_snapshot": snapshot,
        "director_review": {"resolution_status": "accepted", "decision": {"action": "accept"}}}
    assert api._settled_controller_winner([source, winner]) is None


def _canon():
    return {"revision_id": "story-canon-0123456789ab", "expanded_story": "Mira arrives at the apartment. Arjun warns her. They leave together for the station.",
        "story_goal": "Reach the station", "continuity_rules": [], "chunks": [
            {"chunk_id": "story_chunk_0001", "continuity_summary": "Mira arrives.",
             "expanded_text": "Mira arrives at the apartment."},
            {"chunk_id": "story_chunk_0002", "continuity_summary": "Arjun warns her.",
             "expanded_text": "Arjun warns Mira."},
            {"chunk_id": "story_chunk_0003", "continuity_summary": "They leave together.",
             "expanded_text": "They leave together for the station."}]}


def test_explicit_controller_recovery_enqueues_one_bounded_retry(tmp_path, monkeypatch):
    projects = api.ProjectStore(tmp_path / "projects")
    project = projects.create_project(title="Recovery fixture", story_input="Mira and Arjun leave together.",
                                      automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", projects)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project["id"], api.ProductionV2RunRequest(
        idempotency_key="recovery-controller-run", control_mode="fully_automated")))
    canon = {**_canon(), "project_id": project["id"], "run_id": run["run_id"],
        "source_hash": run["config"]["source_story_hash"], "review_status": "accepted"}
    api.production_story_revisions.write_revision(api.OUTPUT_ROOT, project["id"], run["run_id"], canon)
    store = api._production_stage_task_store()
    story = store.enqueue(project_id=project["id"], run_id=run["run_id"], stage="story_detail",
        idempotency_key="accepted-story", request={})
    store.claim(task_id=story["task_id"], owner_token="story-worker")
    store.complete(task_id=story["task_id"], owner_token="story-worker",
        result={"revision_id": canon["revision_id"], "revision_stage": "story_detail"})
    outline = store.enqueue(project_id=project["id"], run_id=run["run_id"], stage="controller:scene_outline",
        idempotency_key="controller-outline", request={"source_revision_id": canon["revision_id"]})
    store.claim(task_id=outline["task_id"], owner_token="expired-outline-worker", lease_seconds=60)
    with store._connect() as db:
        db.execute("UPDATE production_stage_tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE task_id=?",
                   (outline["task_id"],))
    assert store.get(project_id=project["id"], run_id=run["run_id"],
                     task_id=outline["task_id"])["status"] == "recovery_required"

    resolved = asyncio.run(api.resolve_production_v2_stage_task(project["id"], run["run_id"],
        outline["task_id"], api.ProductionV2StageTaskRecoveryRequest(confirm_no_durable_result=True)))
    assert resolved["status"] == "failed"
    assert resolved["error"]["retryable"] is True
    attempts = [row for row in store.list_run(project_id=project["id"], run_id=run["run_id"])
                if row["stage"] == "controller:scene_outline"]
    assert len(attempts) == 2
    retry = next(row for row in attempts if row["task_id"] != outline["task_id"])
    assert retry["status"] == "queued"
    assert retry["idempotency_key"] == "controller-outline:retry:1"
    assert retry["request"] == outline["request"]

    # Replaying controller advancement must not create a second retry.
    api._advance_production_text_controller(project["id"], run["run_id"])
    attempts_after_replay = [row for row in store.list_run(project_id=project["id"], run_id=run["run_id"])
                            if row["stage"] == "controller:scene_outline"]
    assert [row["task_id"] for row in attempts_after_replay] == [row["task_id"] for row in attempts]


@pytest.mark.parametrize("corrected", [True, False])
def test_outline_identity_error_reaches_bounded_corrective_attempt_without_orphan_canon(tmp_path, monkeypatch, corrected):
    from story_builder.services.production_world_state import read_project_canon

    projects = api.ProjectStore(tmp_path / "projects")
    project = projects.create_project(title="Outline evidence", story_input="Mira waits in the station.",
        automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", projects)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project["id"], api.ProductionV2RunRequest(
        idempotency_key="outline-evidence", control_mode="fully_automated")))
    text = "Mira waits in the station."
    canon = {**_canon(), "project_id": project["id"], "run_id": run["run_id"],
        "source_hash": run["config"]["source_story_hash"], "review_status": "accepted", "expanded_story": text,
        "chunks": [{"chunk_id": "story_chunk_0001", "expanded_text": text}]}
    api.production_story_revisions.write_revision(api.OUTPUT_ROOT, project["id"], run["run_id"], canon)
    store = api._production_stage_task_store()
    task = store.enqueue(project_id=project["id"], run_id=run["run_id"], stage="controller:scene_outline",
        idempotency_key="outline-task", request={"source_revision_id": canon["revision_id"]})
    prompts = []

    def provider(**kwargs):
        prompts.append(kwargs["prompt"])
        # A rejected candidate must not leave new identities behind.
        assert read_project_canon(projects.root_dir, project["id"])["revision"] == 0
        location = "the station" if corrected and len(prompts) == 2 else "the tunnel"
        return {"scenes": [{"title": "Waiting", "summary": "Mira waits.", "location": location,
            "time": "Now", "characters": ["Mira"], "dramatic_turn": "She waits.",
            "source_chunk_ids": ["story_chunk_0001"],
            "shots": [{"purpose": "Establish", "action": "Mira waits."}]}]}

    # Real planner and atomic canon reconciliation; only inference is substituted.
    monkeypatch.setattr("story_builder.services.production_text_controller.generate_json", provider)
    monkeypatch.setattr(api, "_prepare_director_voice_bindings", lambda *_args: {
        "status": "not_required", "bound_count": 0, "pending_count": 0})
    monkeypatch.setattr(api, "_advance_production_text_controller", lambda *_args: None)
    api._execute_production_story_stage_task(task["task_id"])
    saved = store.get(project_id=project["id"], run_id=run["run_id"], task_id=task["task_id"])
    assert len(prompts) == 2
    assert "the tunnel' is not evidenced as a place" in prompts[1]
    assert saved["status"] == ("completed" if corrected else "failed")
    persisted = read_project_canon(projects.root_dir, project["id"])
    assert persisted["revision"] == (1 if corrected else 0)
    if corrected:
        assert [world["display_name"] for world in persisted["worlds"]] == ["the station"]


def test_shot_reference_catalog_is_project_run_and_identity_scoped():
    run_id = "run-1"
    mira, arjun, apartment = "char-mira", "char-arjun", "world-apartment"
    assets = [
        {"asset_id": "mira-master", "kind": "image", "roles": ["character_master"],
         "filename": "mira.png", "sha256": "a", "metadata": {"character_id": mira}},
        {"asset_id": "world-master", "kind": "image", "roles": ["world_master"],
         "filename": "apartment.png", "sha256": "b", "metadata": {"world_id": apartment}},
        {"asset_id": "arjun-master", "kind": "image", "roles": ["character_master"],
         "filename": "arjun.png", "sha256": "c", "metadata": {"character_id": arjun}},
        {"asset_id": "unaccepted-candidate", "kind": "image",
         "roles": ["image_candidate", "character_master"], "filename": "candidate.png",
         "metadata": {"character_id": mira, "production_image_job": {"accepted": False}}},
        {"asset_id": "voice-mira", "kind": "audio", "roles": ["voice_excerpt"],
         "filename": "mira-ref.wav", "sha256": "d",
         "metadata": {"run_id": run_id, "character_id": mira, "source_voice_asset_id": "voice-master-mira"}},
        {"asset_id": "voice-other-run", "kind": "audio", "roles": ["voice_excerpt"],
         "filename": "old-ref.wav", "metadata": {"run_id": "run-2", "character_id": mira,
             "source_voice_asset_id": "voice-master-mira"}},
        {"asset_id": "action-video", "kind": "video", "roles": ["action_reference_video"],
         "filename": "storm.mp4", "sha256": "e", "metadata": {}},
        {"asset_id": "music-bed", "kind": "audio", "roles": ["music_candidate"],
         "filename": "music.wav", "metadata": {}},
        {"asset_id": "legacy-malformed", "kind": "image", "roles": None,
         "filename": "broken.png", "metadata": {}},
    ]
    bindings = [None, {"run_id": run_id, "character_id": mira, "voice_asset_id": "voice-master-mira",
        "speaker_id": "S1"}, {"run_id": "run-2", "character_id": arjun,
        "voice_asset_id": "voice-master-arjun", "speaker_id": "S1"}]

    catalog = build_shot_reference_catalog(units=[{"unit_id": "shot-1", "scene_id": "scene-1",
        "character_ids": [mira, arjun], "world_id": apartment}], assets=assets,
        voice_bindings=bindings, run_id=run_id)

    assert catalog == [{"shot_id": "shot-1", "scene_id": "scene-1",
        "character_ids": [mira, arjun], "world_id": apartment,
        "images": [
            {"asset_id": "arjun-master", "filename": "arjun.png", "sha256": "c",
             "role": "character_master", "entity_id": arjun},
            {"asset_id": "mira-master", "filename": "mira.png", "sha256": "a",
             "role": "character_master", "entity_id": mira},
            {"asset_id": "world-master", "filename": "apartment.png", "sha256": "b",
             "role": "world_master", "entity_id": apartment}],
        "videos": [{"asset_id": "action-video", "filename": "storm.mp4", "sha256": "e",
                    "role": "action_reference_video"}],
        "voice_references": [{"asset_id": "voice-mira", "filename": "mira-ref.wav", "sha256": "d",
            "role": "voice_excerpt", "entity_id": mira, "speaker_id": "S1"}],
        "scope": "approved project assets and this run's bound voice excerpts"}]


def test_shot_catalog_resolution_preserves_exact_intents_and_bound_speaker():
    intents = [
        {"role": "character_master", "intent": "Preserve Mira's face and costume."},
        {"role": "voice_excerpt", "intent": "Use Mira's bound voice timbre."},
    ]
    catalog = [{"shot_id": "shot-1", "scene_id": "scene-1", "character_ids": ["mira"],
        "world_id": "world-1", "images": [{"asset_id": "master-mira", "role": "character_master", "entity_id": "mira"}],
        "videos": [], "voice_references": [{"asset_id": "voice-mira", "role": "voice_excerpt",
            "entity_id": "mira", "speaker_id": "S1"}]}]
    seen = {}

    def choose(*, request):
        seen.update(request)
        return {"images": [{"asset_id": "master-mira", "role": "character_master", "intent": intents[0]["intent"]}],
            "videos": [], "standalone_audios": [{"asset_id": "voice-mira", "role": "voice_excerpt",
                "intent": intents[1]["intent"], "speaker_id": "S1"}]}

    result = resolve_shot_reference_catalog(shot_id="shot-1", asset_intents=intents,
        catalog=catalog, selector=choose)
    assert result["images"][0]["asset_id"] == "master-mira"
    assert result["standalone_audios"][0]["speaker_id"] == "S1"
    assert seen["approved_catalog"]["images"] == catalog[0]["images"]


@pytest.mark.parametrize("mutation", ["forged_id", "wrong_intent", "wrong_speaker", "missing_choice"])
def test_shot_catalog_resolution_rejects_untrusted_or_incomplete_selection(mutation):
    intents = [{"role": "voice_excerpt", "intent": "Use the bound voice."}]
    catalog = [{"shot_id": "shot-1", "images": [], "videos": [], "voice_references": [
        {"asset_id": "voice-1", "role": "voice_excerpt", "entity_id": "char-1", "speaker_id": "S1"}]}]
    choice = {"images": [], "videos": [], "standalone_audios": [{"asset_id": "voice-1",
        "role": "voice_excerpt", "intent": intents[0]["intent"], "speaker_id": "S1"}]}
    if mutation == "forged_id": choice["standalone_audios"][0]["asset_id"] = "foreign"
    if mutation == "wrong_intent": choice["standalone_audios"][0]["intent"] = "invented intent"
    if mutation == "wrong_speaker": choice["standalone_audios"][0]["speaker_id"] = "S2"
    if mutation == "missing_choice": choice["standalone_audios"] = []
    with pytest.raises(ShotReferenceResolutionError):
        resolve_shot_reference_catalog(shot_id="shot-1", asset_intents=intents,
            catalog=catalog, selector=lambda **_: choice)


def test_scene_outline_uses_narrative_units_not_one_scene_per_source_chunk():
    captured = {}
    def planner(**kwargs):
        captured.update(kwargs)
        return {"scenes": [
            {"title": "The arrival", "summary": "Mira arrives and finds Arjun waiting.",
             "location": "Apartment", "time": "Evening", "characters": ["Mira", "Arjun"],
             "dramatic_turn": "Arjun reveals the storm warning.",
             "source_chunk_ids": ["story_chunk_0001", "story_chunk_0002"],
             "shots": [{"purpose": "Establish the room", "action": "Mira enters."},
                       {"purpose": "Reveal concern", "action": "Arjun shows the warning."}]},
            {"title": "The departure", "summary": "They decide to leave for safety.",
             "location": "Station", "time": "Moments later", "characters": ["Mira", "Arjun"],
             "dramatic_turn": "They leave together.", "source_chunk_ids": ["story_chunk_0003"],
             "shots": [{"purpose": "Resolve the decision", "action": "They step into the hall."}]}]}

    units = plan_scene_outline(canon=_canon(), provider="codex", generator=planner)
    assert "explicit locative" in captured["prompt"]
    assert 'return "the lighthouse", not "beside the lighthouse"' in captured["prompt"]
    assert "lighthouse keeper Arun" in captured["prompt"]
    assert 'a cabinet located in a cafe does' in captured["prompt"]
    assert 'not itself the scene location' in captured["prompt"]
    assert 'only exact person names explicitly present' in captured["prompt"]
    assert 'Do not put role descriptions, occupations, pronouns' in captured["prompt"]
    assert "Group consecutive beats into one scene" in captured["prompt"]
    assert "Do not assign the same dramatic event to multiple scenes" in captured["prompt"]
    assert [row["unit_id"] for row in units] == ["scene-001", "scene-002"]
    assert units[0]["source_chunk_ids"] == ["story_chunk_0001", "story_chunk_0002"]
    assert [shot["unit_id"] for shot in units[0]["shot_units"]] == ["shot-001-01", "shot-001-02"]


def test_scene_outline_rejects_uncovered_source_chunks():
    def planner(**_kwargs):
        return {"scenes": [{"title": "Only", "summary": "A scene.", "location": "Here",
            "time": "Now", "characters": ["Mira"], "dramatic_turn": "She leaves.",
            "source_chunk_ids": ["story_chunk_0001"],
            "shots": [{"purpose": "Start", "action": "Mira enters."}]}]}
    with pytest.raises(SceneOutlineError, match="does not cover all"):
        plan_scene_outline(canon=_canon(), provider="codex", generator=planner)


def test_outline_identity_reconciliation_is_stable_evidenced_and_idempotent(tmp_path):
    from story_builder.services.production_world_state import (
        create_anonymous_character, read_project_canon, save_project_canon,
    )

    existing = create_anonymous_character("Mira")
    save_project_canon(tmp_path, "film", expected_revision=0,
        characters=[existing], worlds=[], source_story_revision="story-canon-0123456789ab", actor="user")
    units = [{"unit_id": "scene-001", "source_chunk_ids": ["story_chunk_0001"],
        "scene_outline": {"characters": ["Mira", "Arjun"], "location": "Station"},
        "shot_units": [{"unit_id": "shot-001-01"}]}]
    first = reconcile_outline_identities(tmp_path, "film", story_revision_id="story-canon-0123456789ab",
        expanded_story="Mira and Arjun arrive at the Station.", source_chunks=_canon()["chunks"], units=units)
    after_first = read_project_canon(tmp_path, "film")
    mira_id = existing["character_id"]
    arjun = next(row for row in after_first["characters"] if row["display_name"] == "Arjun")
    station = next(row for row in after_first["worlds"] if row["display_name"] == "Station")
    assert first["characters"]["mira"] == mira_id
    assert first["characters"]["arjun"] == arjun["character_id"]
    assert first["worlds"]["station"] == station["world_id"]
    assert units[0]["character_ids"] == [mira_id, arjun["character_id"]]
    assert units[0]["shot_units"][0]["world_id"] == station["world_id"]
    assert arjun["evidence"] == [{"kind": "accepted_story_character_name",
        "source_story_revision": "story-canon-0123456789ab", "scene_id": "scene-001",
        "scene_context_chunk_ids": ["story_chunk_0001"],
        "matched_chunk_ids": ["story_chunk_0002"], "matched_text": "Arjun"}]

    second = reconcile_outline_identities(tmp_path, "film", story_revision_id="story-canon-0123456789ab",
        expanded_story="Mira and Arjun arrive at the Station.", source_chunks=_canon()["chunks"], units=units)
    after_second = read_project_canon(tmp_path, "film")
    assert second["reused"] is True
    assert after_second["revision"] == after_first["revision"]
    assert {row["display_name"]: row["character_id"] for row in after_second["characters"]} == {
        "Mira": mira_id, "Arjun": arjun["character_id"]}

    invalid_units = [{"unit_id": "scene-002", "source_chunk_ids": ["story_chunk_0002"],
        "scene_outline": {"characters": ["Mira"], "location": "Station"}, "shot_units": []}]
    with pytest.raises(SceneOutlineError, match="not evidenced"):
        reconcile_outline_identities(tmp_path, "film", story_revision_id="story-canon-0123456789ab",
            expanded_story="Miranda and Arjun arrive at the Station.", source_chunks=_canon()["chunks"], units=invalid_units)
    assert read_project_canon(tmp_path, "film")["revision"] == after_second["revision"]



def test_outline_location_rejects_character_occupation_even_when_text_contains_it(tmp_path):
    from story_builder.services.production_text_controller import _is_evidenced_location

    story = "Mira waits for lighthouse keeper Arun in her empty cafe."
    assert _is_evidenced_location("her empty cafe", story)
    assert _is_evidenced_location("Arun's cafe", "Mira waits at Arun's cafe.", character_names=["Arun"])
    assert not _is_evidenced_location("lighthouse keeper Arun", story, character_names=["Arun"])
    units = [{"unit_id": "scene-001", "source_chunk_ids": ["story_chunk_0001"],
        "scene_outline": {"characters": ["Mira", "Arun"], "location": "lighthouse keeper Arun"},
        "shot_units": [{"unit_id": "shot-001-01"}]}]
    with pytest.raises(SceneOutlineError, match="lighthouse keeper Arun.*not evidenced as a place"):
        reconcile_outline_identities(tmp_path, "film", story_revision_id="story-canon-0123456789ab",
            expanded_story=story, source_chunks=[{"chunk_id": "story_chunk_0001", "expanded_text": story}], units=units)
    assert not (tmp_path / "film" / "production_v2_canon.json").exists()


def test_outline_location_does_not_accept_location_prefix_of_person_role():
    from story_builder.services.production_text_controller import _is_evidenced_location

    story = "Mira asks for the station manager before leaving for the station at dusk."
    assert not _is_evidenced_location("Station", "Mira asks for the station manager.")
    assert _is_evidenced_location("station", story)


def test_outline_location_accepts_place_noun_after_beside():
    from story_builder.services.production_text_controller import _is_evidenced_location

    story = "At dawn, Mira finds a brass key beside the lighthouse."
    assert _is_evidenced_location("the lighthouse", story)
    assert not _is_evidenced_location("beside the lighthouse", story)


def test_outline_location_accepts_place_after_to():
    from story_builder.services.production_text_controller import _is_evidenced_location

    assert _is_evidenced_location("the seaside cafe", "Mira returns to the seaside cafe before sunset.")


def test_outline_identity_reconciliation_rejects_ambiguous_existing_alias(tmp_path):
    from story_builder.services.production_world_state import (
        create_anonymous_character, read_project_canon, save_project_canon,
    )

    first = create_anonymous_character("Mira")
    first["aliases"] = ["M"]
    second = create_anonymous_character("Maya")
    second["aliases"] = ["M"]
    before = save_project_canon(tmp_path, "film", expected_revision=0,
        characters=[first, second], worlds=[], source_story_revision="story-canon-0123456789ab", actor="user")
    units = [{"unit_id": "scene-001", "source_chunk_ids": ["story_chunk_0001"],
        "scene_outline": {"characters": ["M"], "location": "Station"}, "shot_units": []}]

    with pytest.raises(SceneOutlineError, match="multiple active canon identities"):
        reconcile_outline_identities(tmp_path, "film", story_revision_id="story-canon-0123456789ab",
            expanded_story="M meets someone at Station.", source_chunks=_canon()["chunks"], units=units)
    assert read_project_canon(tmp_path, "film")["revision"] == before["revision"]


@pytest.mark.parametrize(("control_mode", "semi_gates", "making_route", "invalid_identity", "invalid_later_design", "compile_failure_late", "enqueue_failure_late"), [
    ("fully_automated", {}, "direct_h3", False, False, False, False),
    ("semi", {"story_review": False, "shot_workflow_render_approval": False}, "direct_h3", False, False, False, False),
    ("fully_automated", {}, "reference_built", False, False, False, False),
    ("semi", {"story_review": False, "image_candidate_selection": False,
        "shot_workflow_render_approval": False}, "reference_built", False, False, False, False),
    ("fully_automated", {}, "reference_built", True, False, False, False),
    ("fully_automated", {}, "reference_built", False, True, False, False),
    ("fully_automated", {}, "reference_built", False, False, True, False),
    ("fully_automated", {}, "reference_built", False, False, False, True),
])
def test_full_controller_advances_durable_text_stages_and_stops_before_render(tmp_path, monkeypatch,
        control_mode, semi_gates, making_route, invalid_identity, invalid_later_design, compile_failure_late,
        enqueue_failure_late):
    projects = api.ProjectStore(tmp_path / "projects")
    project = projects.create_project(title="Automated story", story_input="Mira and Arjun reach the station.",
                                      automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", projects)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project["id"], api.ProductionV2RunRequest(
        idempotency_key="controller-run", control_mode=control_mode, semi_gates=semi_gates,
        making_route=making_route, image_workflow_id="z_image_turbo" if making_route == "reference_built" else None)))
    store = api._production_stage_task_store()
    canon = {**_canon(), "project_id": project["id"], "run_id": run["run_id"],
        "source_hash": run["config"]["source_story_hash"], "review_status": "accepted"}
    api.production_story_revisions.write_revision(api.OUTPUT_ROOT, project["id"], run["run_id"], canon)
    story_task = store.enqueue(project_id=project["id"], run_id=run["run_id"], stage="story_detail",
        idempotency_key="story-controller", request={})
    store.claim(task_id=story_task["task_id"], owner_token="test-story")
    store.complete(task_id=story_task["task_id"], owner_token="test-story",
        result={"revision_id": canon["revision_id"], "revision_stage": "story_detail"})

    planned_units = [{"unit_id": "scene-001", "source_chunk_ids": ["story_chunk_0001", "story_chunk_0002"],
        "scene_outline": {"title": "Station", "summary": "They arrive.", "location": "station",
            "time": "Now", "characters": ["Mira", "Arjun"], "dramatic_turn": "They arrive."},
        "shot_units": [{"unit_id": "shot-001-01", "scene_id": "scene-001", "source_chunk_ids": ["story_chunk_0001"],
                        "shot_outline": {"purpose": "Establish", "action": "They arrive."}}]}]
    outline_calls = []
    def fake_outline(**kwargs):
        outline_calls.append(kwargs)
        if len(outline_calls) == 1:
            raise SceneOutlineError("first outline missed source coverage")
        return planned_units
    monkeypatch.setattr(api, "plan_scene_outline", fake_outline)

    failed_scene_once = {"value": False}
    failed_shot_plan_once = {"value": False}
    def fake_text_stage(project_id, run_id, stage, payload):
        if stage == "scenes" and not failed_scene_once["value"]:
            failed_scene_once["value"] = True
            raise api.HTTPException(status_code=502, detail={"code": "temporary_provider_error",
                "message": "temporary provider outage", "retryable": True})
        if stage == "shot_plans" and not failed_shot_plan_once["value"]:
            failed_shot_plan_once["value"] = True
            raise api.HTTPException(status_code=422, detail={"code": "shot_plan_output_invalid",
                "message": "generated fields need correction", "unit_id": "shot-001-01",
                "invalid_fields": ["duration_seconds"], "retryable": True})
        items = []
        for unit in payload.units:
            content = ({"dialogue": []}
                if stage == "dialogue" else {"summary": f"{stage} for {unit['unit_id']}"})
            if stage == "scenes":
                content["shots"] = [{"unit_id": shot["unit_id"], "beat": shot["shot_outline"]["action"],
                    "emotion": "Focused", "dialogue_delivery": "Natural"}
                    for shot in unit.get("shot_units", [])]
            if stage == "shot_plans":
                content.update(prompt="Mira and Arjun enter the station.", duration_seconds=5,
                    dialogue=[], asset_intents=[])
                if invalid_identity:
                    unit["character_ids"] = ["inactive-character-id"]
            if stage == "visual_briefs" and making_route == "reference_built":
                project_canon = api.read_project_canon(api.PROJECT_STORE.root_dir, project_id)
                # Keep sparse but nonempty user canon so the queued prompt must
                # preserve it alongside the accepted visual proposal.
                character_rows = []
                for character in project_canon["characters"]:
                    character = dict(character)
                    if character.get("display_name") == "Mira":
                        character["appearance"] = "Canon: short dark hair and a small cheek scar."
                    elif character.get("display_name") == "Arjun":
                        character["appearance"] = "Canon: rectangular glasses."
                    character_rows.append(character)
                world_rows = [dict(world, description=("" if invalid_later_design
                    else "Canon: the station is an active transit hub."))
                    if world.get("display_name", "").casefold() == "station" else dict(world)
                    for world in project_canon["worlds"]]
                api.save_project_canon(api.PROJECT_STORE.root_dir, project_id,
                    expected_revision=project_canon["revision"], characters=character_rows,
                    worlds=world_rows, source_story_revision=canon["revision_id"], actor="test")
                canon_characters = {row["character_id"]: row["display_name"]
                    for row in character_rows if row.get("status") == "active"}
                character_designs = []
                for character_id in unit.get("character_ids", []):
                    name = canon_characters.get(character_id)
                    design = {"Mira": "Mira's approved design: rust-red rain jacket with a pale collar.",
                        "Arjun": "Arjun's approved design: muted green jacket with a high collar."}.get(name)
                    if design:
                        character_designs.append({"id": character_id, "identity": name,
                            "proposed_design_choice": design})
                content["continuity"] = {
                    "visible_characters_and_animal": character_designs,
                    "location": {"id": ("unmatched-world" if invalid_later_design else unit.get("world_id")),
                        "identifier": "Station concourse with a long central platform and blue departure boards."}}
            items.append({**unit, "content": content})
        revision = {"schema_version": 1, "revision_id": f"{stage}-{len(items):012x}",
            "project_id": project_id, "run_id": run_id, "stage": stage,
            "source_revision_id": payload.source_revision_id,
            "source_story_hash": canon["source_hash"], "stage_task_id": payload.stage_task_id,
            "stage_task_request_hash": payload.stage_task_request_hash,
            "review_status": "accepted", "items": items}
        api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id, run_id, stage, revision)
        return {"revision": revision}

    monkeypatch.setattr(api, "generate_production_v2_text_stage", fake_text_stage)
    if making_route == "reference_built":
        monkeypatch.setattr(api, "image_workflow_catalog", lambda: {"workflows": [{
            "workflow_id": "z_image_turbo", "available": True, "disabled_reason": None}]})
        compile_calls = []
        def compile_image_candidate(*, workflow_id, prompt, seed, output_prefix, **_kwargs):
            compile_calls.append(prompt)
            if compile_failure_late and len(compile_calls) % 3 == 0:
                raise ValueError("synthetic late image graph compilation failure")
            return {"workflow_id": workflow_id, "workflow_version": "test-v1", "prompt": prompt,
                "settings": {"width": 512, "height": 512},
                "candidates": [{"seed": seed, "graph": {"1": {"class_type": "KSampler", "inputs": {"seed": seed}}}}]}
        monkeypatch.setattr(api, "compile_image_candidates", compile_image_candidate)
    api._advance_production_text_controller(project["id"], run["run_id"])
    assert any(row["stage"] == "controller:scene_outline" and row["status"] == "queued" for row in store.list_run(project_id=project["id"], run_id=run["run_id"]))

    # Model a backend restart between durable controller stages. A fresh store
    # object over the same SQLite file must discover and reuse the queued task,
    # rather than enqueueing a duplicate outline request.
    restarted_store = ProductionStageTaskStore(tmp_path / "storage" / "production" / "v2_ledger.sqlite3")
    monkeypatch.setattr(api, "_production_stage_task_store", lambda: restarted_store)
    api._advance_production_text_controller(project["id"], run["run_id"])
    restarted_outline_tasks = [row for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"])
                               if row["stage"] == "controller:scene_outline"]
    assert len(restarted_outline_tasks) == 1
    assert restarted_outline_tasks[0]["status"] == "queued"

    for _ in range(8):
        api._advance_production_text_controller(project["id"], run["run_id"])
        queued = restarted_store.queued()
        assert queued, "controller should durably queue its next text stage"
        if enqueue_failure_late and queued[0]["stage"] == "text:shot_plans":
            image_store = api.ProductionImageJobStore(tmp_path / "storage" / "production" / "v2_ledger.sqlite3")
            with image_store._connect() as db:
                db.execute("""CREATE TRIGGER IF NOT EXISTS fail_late_master_insert
                    BEFORE INSERT ON production_image_jobs
                    WHEN NEW.asset_role='world_master'
                    BEGIN SELECT RAISE(ABORT, 'synthetic late image queue failure'); END""")
        api._execute_production_story_stage_task(queued[0]["task_id"])
        tasks = restarted_store.list_run(project_id=project["id"], run_id=run["run_id"])
        if any(row["stage"] == "text:shot_plans" and row["status"] == "completed" for row in tasks):
            break
    else:
        raise AssertionError("controller did not finish the text stage sequence")

    if making_route == "reference_built":
        image_store = api.ProductionImageJobStore(tmp_path / "storage" / "production" / "v2_ledger.sqlite3")
        api._advance_production_text_controller(project["id"], run["run_id"])
        with image_store._connect() as db:
            rows = db.execute("SELECT job_id, idempotency_key, asset_role, settings_json, graph_json, status, prompt "
                "FROM production_image_jobs WHERE project_id=? AND run_id=? ORDER BY idempotency_key",
                (project["id"], run["run_id"])).fetchall()
        if invalid_identity or invalid_later_design or compile_failure_late or enqueue_failure_late:
            assert rows == []
            run_record = api._production_v2_ledger().get_run(project_id=project["id"], run_id=run["run_id"])
            blocked_event = next(event for event in run_record["events"]
                if event["event_type"] == "controller_image_masters_blocked")
            assert blocked_event["payload"]["code"] == "automatic_master_generation_unavailable"
            if invalid_identity:
                assert "inactive or missing character" in blocked_event["payload"]["message"]
            if invalid_later_design:
                assert "No canonical or accepted visual design" in blocked_event["payload"]["message"]
            if compile_failure_late:
                assert "synthetic late image graph compilation failure" in blocked_event["payload"]["message"]
            if enqueue_failure_late:
                assert "synthetic late image queue failure" in blocked_event["payload"]["message"]
            assert not any(row["stage"] == "controller:resolved_shot_prompt"
                for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"]))
            assert run_record["takes"] == []
            return
        assert len(rows) == 3
        assert {row["status"] for row in rows} == {"queued"}
        assert {row["asset_role"] for row in rows} == {"character_master", "world_master"}
        assert len({row["idempotency_key"] for row in rows}) == 3
        world_job = next(row for row in rows if row["asset_role"] == "world_master")
        assert "environment reference of station" in world_job["prompt"]
        assert "spatial layout" in world_job["prompt"]
        assert "full visible face" not in world_job["prompt"]
        identities = [json.loads(row["settings_json"])["review_identity"] for row in rows]
        assert {identity["display_name"] for identity in identities} == {"Mira", "Arjun", "station"}
        assert all(identity["entity_id"] and identity["kind"] in {"character", "world"}
            for identity in identities)
        identity_by_name = {identity["display_name"]: identity for identity in identities}
        mira_identity = identity_by_name["Mira"]
        arjun_identity = identity_by_name["Arjun"]
        world_identity = identity_by_name["station"]
        mira_job = next(row for row in rows if json.loads(row["settings_json"])["review_identity"]["entity_id"]
            == mira_identity["entity_id"])
        arjun_job = next(row for row in rows if json.loads(row["settings_json"])["review_identity"]["entity_id"]
            == arjun_identity["entity_id"])
        assert "Mira's approved design: rust-red rain jacket with a pale collar." in mira_job["prompt"]
        assert "Arjun's approved design" not in mira_job["prompt"]
        assert "Arjun's approved design: muted green jacket with a high collar." in arjun_job["prompt"]
        assert "Mira's approved design" not in arjun_job["prompt"]
        assert "Canon: short dark hair and a small cheek scar." in mira_job["prompt"]
        assert "Canon: rectangular glasses." in arjun_job["prompt"]
        world_prompt = world_job["prompt"]
        assert "Station concourse with a long central platform and blue departure boards." in world_prompt
        assert "Canon: the station is an active transit hub." in world_prompt
        for character_job in (row for row in rows if row["asset_role"] == "character_master"):
            assert "framed from head to toe" in character_job["prompt"]
            assert "entire head, body and feet inside the frame" in character_job["prompt"]
            assert "reference portrait" not in character_job["prompt"]
            assert "without adding other people" in character_job["prompt"]
        assert "Preserve this canonical appearance: ." not in " ".join(row["prompt"] for row in rows)
        assert mira_identity["approved_visual_design"] == "Mira's approved design: rust-red rain jacket with a pale collar."
        assert mira_identity["visual_design_provenance"]["revision_id"] == "visual_briefs-000000000001"
        assert mira_identity["visual_design_provenance"]["entity_id"] == mira_identity["entity_id"]
        # Provenance belongs in the ledger/reviewer record, never in pixels.
        for row in rows:
            assert "visual_briefs-000000000001" not in row["prompt"]
            assert json.loads(row["settings_json"])["review_identity"]["entity_id"] not in row["prompt"]
        assert world_identity["approved_visual_design"] == (
            "Station concourse with a long central platform and blue departure boards.")
        original_builder = api._build_controller_master_prompt
        def upgraded_builder(*args, **kwargs):
            guide = original_builder(*args, **kwargs)
            return {**guide, "prompt": guide["prompt"] + " Updated producer framing."}
        monkeypatch.setattr(api, "_build_controller_master_prompt", upgraded_builder)
        api._advance_production_text_controller(project["id"], run["run_id"])
        with image_store._connect() as db:
            preserved = db.execute("SELECT job_id,prompt,graph_json,settings_json FROM production_image_jobs WHERE project_id=? AND run_id=? ORDER BY job_id",
                (project["id"], run["run_id"])).fetchall()
            before = sorted(rows, key=lambda row: row["job_id"])
            assert [tuple(row) for row in preserved] == [tuple(row[key] for key in ("job_id", "prompt", "graph_json", "settings_json")) for row in before]
            replay_count = db.execute("SELECT count(*) FROM production_image_jobs WHERE project_id=? AND run_id=?",
                (project["id"], run["run_id"])).fetchone()[0]
        assert replay_count == len(rows)
        run_record = api._production_v2_ledger().get_run(project_id=project["id"], run_id=run["run_id"])
        queued_event = next(event for event in run_record["events"]
            if event["event_type"] == "controller_image_masters_queued")
        assert len(queued_event["payload"]["pending"]) == 3
        assert not any(event["event_type"] == "controller_image_masters_blocked" for event in run_record["events"])
        assert not any(row["stage"] == "controller:resolved_shot_prompt"
            for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"]))
        assert run_record["takes"] == []
        # Simulate each queued image worker returning a completed candidate and
        # the Director accepting it. This exercises the real asset registry and
        # controller callback boundary without contacting ComfyUI or a provider.
        image_bytes = io.BytesIO()
        Image.new("RGB", (32, 32), (40, 80, 120)).save(image_bytes, format="PNG")
        accepted_masters = []
        for row in rows:
            settings = json.loads(row["settings_json"])
            identity = settings["review_identity"]
            relative_path = f"production/image_jobs/{row['job_id']}/candidate.png"
            output_path = api.OUTPUT_ROOT / project["id"] / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes.getvalue())
            candidate = api.register_production_asset_output(
                api.PROJECT_STORE.root_dir, api.OUTPUT_ROOT, project["id"],
                relative_path=relative_path, role="image_candidate",
                metadata={"production_image_job": {"job_id": row["job_id"],
                    "run_id": run["run_id"], "status": "completed",
                    "intended_role": row["asset_role"], "accepted": False}})
            accepted_masters.append(api.accept_production_image_candidate(
                api.PROJECT_STORE.root_dir, project["id"], candidate["asset_id"],
                role=row["asset_role"], actor="director", entity_id=identity["entity_id"]))
        # The worker's Director-accept callback advances the saved run. Master
        # assets must now be present in the immutable prompt-preparation catalog.
        api._advance_production_text_controller(project["id"], run["run_id"])
        resumed_tasks = [row for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"])
            if row["stage"] == "controller:resolved_shot_prompt"]
        assert len(resumed_tasks) == 1
        assert resumed_tasks[0]["status"] == "queued"
        images = resumed_tasks[0]["request"]["approved_reference_catalog"][0]["images"]
        assert {image["entity_id"] for image in images} == {identity["entity_id"]
            for identity in identities}
        assert {image["asset_id"] for image in images} == {asset["asset_id"]
            for asset in accepted_masters}
        api._advance_production_text_controller(project["id"], run["run_id"])
        replayed = [row for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"])
            if row["stage"] == "controller:resolved_shot_prompt"]
        assert len(replayed) == 1 and replayed[0]["task_id"] == resumed_tasks[0]["task_id"]
        assert len(api._production_v2_ledger().get_run(
            project_id=project["id"], run_id=run["run_id"])["takes"]) == 0
        return

    stages = [row["stage"] for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"])]
    assert set(stages) == {"story_detail", "controller:scene_outline", "text:scenes", "text:dialogue",
                           "text:visual_briefs", "text:shot_plans", "controller:resolved_shot_prompt"}
    prompt_task = next(row for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"])
        if row["stage"] == "controller:resolved_shot_prompt")
    shot_plan_attempts = [row for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"])
        if row["stage"] == "text:shot_plans"]
    assert len(shot_plan_attempts) == 2
    failed_shot_plan = next(row for row in shot_plan_attempts if row["status"] == "failed")
    shot_plan_task = next(row for row in shot_plan_attempts if row["status"] == "completed")
    assert failed_shot_plan["error"]["invalid_fields"] == ["duration_seconds"]
    assert shot_plan_task["idempotency_key"] == failed_shot_plan["idempotency_key"] + ":retry:1"
    assert shot_plan_task["request"] == failed_shot_plan["request"]
    assert shot_plan_task["request"]["max_chars_per_batch"] == 16_000
    for text_task in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"]):
        if text_task["stage"].startswith("text:"):
            assert text_task["request"]["max_chars_per_batch"] == 16_000
    assert prompt_task["status"] == "queued"
    assert prompt_task["request"]["shot_id"] == "shot-001-01"
    assert prompt_task["request"]["shot_plan_revision_id"] == "shot_plans-000000000001"
    assert prompt_task["request"]["resolve_catalog"] is True
    assert restarted_store.queued() == [prompt_task]
    api._advance_production_text_controller(project["id"], run["run_id"])
    prompt_tasks_after_replay = [row for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"])
        if row["stage"] == "controller:resolved_shot_prompt"]
    assert len(prompt_tasks_after_replay) == 1
    assert prompt_tasks_after_replay[0]["task_id"] == prompt_task["task_id"]
    assert api._production_v2_ledger().get_run(project_id=project["id"], run_id=run["run_id"])["takes"] == []
    run_status = asyncio.run(api.get_production_v2_run(project["id"], run["run_id"]))
    public_prompt_task = next(row for row in run_status["stage_tasks"]
        if row["task_id"] == prompt_task["task_id"])
    assert public_prompt_task["shot_id"] == "shot-001-01"
    assert public_prompt_task["shot_plan_revision_id"] == "shot_plans-000000000001"
    assert "request" not in public_prompt_task
    assert "approved_reference_catalog" not in public_prompt_task
    assert not any(row["stage"].startswith("render") for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"]))
    # A completed, accepted automatic prompt may create exactly one durable
    # take. The human POST stays behind 409; controller progress reuses the
    # same key after a restart and never calls the ComfyUI worker directly.
    prompt_owner = "accepted-prompt-test"
    restarted_store.claim(task_id=prompt_task["task_id"], owner_token=prompt_owner)
    resolved_prompt = "Mira and Arjun enter the station, prepared for H3."
    resolved_request = dict(prompt_task["request"]["validation_request"])
    assert resolved_request["prompt"] != resolved_prompt
    reference_map = {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}}
    prepared_result = {"accepted": True, "prompt": resolved_prompt,
        "prompt_hash": hashlib.sha256(resolved_prompt.encode("utf-8")).hexdigest(),
        "resolved_validation_request": resolved_request, "reference_map": reference_map,
        "asset_fingerprints": {}}
    restarted_store.complete(task_id=prompt_task["task_id"], owner_token=prompt_owner,
        result=prepared_result)
    monkeypatch.setattr(api, "validate_production_v2_shot", lambda *_args, **_kwargs: {
        "validation_hash": "v" * 64, "reference_map": reference_map, "asset_fingerprints": {},
        "workflow_id": "minimax_h3_t2v_local_v1", "workflow_version": "test",
        "workflow_readiness": {"available": True}})
    take_request = api.ProductionV2TakeQueueRequest(idempotency_key="human-must-not-dispatch",
        validation_request=api.ProductionV2ShotValidateRequest(**{**resolved_request, "prompt": resolved_prompt}),
        prompt_preparation_task_id=prompt_task["task_id"])
    with pytest.raises(api.HTTPException) as gated:
        api.queue_production_v2_take(project["id"], run["run_id"], "shot-001-01", take_request)
    assert gated.value.status_code == 409
    assert gated.value.detail["code"] == "automatic_render_controller_unavailable"
    api._advance_production_text_controller(project["id"], run["run_id"])
    queued_takes = api._production_v2_ledger().get_run(project_id=project["id"], run_id=run["run_id"])["takes"]
    assert len(queued_takes) == 1
    assert queued_takes[0]["status"] == "queued"
    assert queued_takes[0]["input_snapshot"]["validation_request"]["prompt"] == resolved_prompt
    assert queued_takes[0]["input_snapshot"]["prompt_preparation_task_id"] == prompt_task["task_id"]
    restarted_again = ProductionStageTaskStore(tmp_path / "storage" / "production" / "v2_ledger.sqlite3")
    restarted_ledger = api.ProductionLedger(tmp_path / "storage" / "production" / "v2_ledger.sqlite3")
    monkeypatch.setattr(api, "_production_stage_task_store", lambda: restarted_again)
    monkeypatch.setattr(api, "_production_v2_ledger", lambda: restarted_ledger)
    api._advance_production_text_controller(project["id"], run["run_id"])
    replayed_takes = restarted_ledger.get_run(project_id=project["id"], run_id=run["run_id"])["takes"]
    assert len(replayed_takes) == 1
    assert replayed_takes[0]["take_id"] == queued_takes[0]["take_id"]
    assert len(outline_calls) == 2
    assert "first outline missed source coverage" in outline_calls[1]["retry_note"]
    scene_attempts = [row for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"])
                      if row["stage"] == "text:scenes"]
    assert len(scene_attempts) == 2
    assert {row["status"] for row in scene_attempts} == {"failed", "completed"}
    assert len({row["idempotency_key"] for row in scene_attempts}) == 2
    project_canon = api.read_project_canon(projects.root_dir, project["id"])
    character_ids = {row["display_name"]: row["character_id"] for row in project_canon["characters"]}
    assert set(character_ids) == {"Mira", "Arjun"}
    world = next(row for row in project_canon["worlds"] if row["display_name"] == "station")
    assert all(row["source_story_revision"] == canon["revision_id"]
        for identity in [*project_canon["characters"], world] for row in identity["evidence"])
    for stage in ("scenes", "dialogue", "visual_briefs", "shot_plans"):
        task = next(row for row in restarted_store.list_run(project_id=project["id"], run_id=run["run_id"])
                    if row["stage"] == f"text:{stage}")
        unit = task["request"]["units"][0]
        assert unit["character_ids"] == [character_ids["Mira"], character_ids["Arjun"]]
        assert unit["world_id"] == world["world_id"]


def test_semi_human_story_gate_does_not_start_automatic_text_controller(tmp_path, monkeypatch):
    projects = api.ProjectStore(tmp_path / "projects")
    project = projects.create_project(title="Human reviewed", story_input="Mira reaches the station.", automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", projects)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project["id"], api.ProductionV2RunRequest(
        idempotency_key="semi-human-controller", control_mode="semi", semi_gates={"story_review": True})))
    canon = {**_canon(), "project_id": project["id"], "run_id": run["run_id"],
        "source_hash": run["config"]["source_story_hash"], "review_status": "accepted"}
    api.production_story_revisions.write_revision(api.OUTPUT_ROOT, project["id"], run["run_id"], canon)
    store = api._production_stage_task_store()
    task = store.enqueue(project_id=project["id"], run_id=run["run_id"], stage="story_detail",
        idempotency_key="semi-story", request={})
    store.claim(task_id=task["task_id"], owner_token="semi-story-worker")
    store.complete(task_id=task["task_id"], owner_token="semi-story-worker",
        result={"revision_id": canon["revision_id"], "revision_stage": "story_detail"})
    api._advance_production_text_controller(project["id"], run["run_id"])
    assert [row["stage"] for row in store.list_run(project_id=project["id"], run_id=run["run_id"])] == ["story_detail"]
