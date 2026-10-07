import asyncio
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
import httpx

from story_builder.api import main as api
from story_builder.services.chunked_generation import generate_story_canon


def test_dialogue_context_drops_verbose_visual_fields_without_losing_scene_facts() -> None:
    content = {
        "title": "At the cafe", "summary": "Mira shares the key with Arun.",
        "location": "the cafe", "time": "Before sunset", "characters": ["Mira", "Arun"],
        "dramatic_turn": "They discover the key opens the cabinet.",
        "shots": [{"beat": "Mira shows the key.", "emotion": "Curious", "dialogue_delivery": "Quietly",
                   "camera": "x" * 10000, "lighting": "x" * 10000, "blocking": "x" * 10000}],
    }

    compact = api._dialogue_context_for_scene(content)

    assert compact == {
        "title": "At the cafe", "summary": "Mira shares the key with Arun.",
        "location": "the cafe", "time": "Before sunset", "characters": ["Mira", "Arun"],
        "dramatic_turn": "They discover the key opens the cabinet.",
        "shots": [{"beat": "Mira shows the key.", "emotion": "Curious", "dialogue_delivery": "Quietly"}],
    }
    assert len(json.dumps(compact)) < 1000


def test_dialogue_context_contains_only_the_matching_shot_beat():
    content = {"title": "Warning", "location": "Stairwell", "characters": ["Mira", "Arjun"],
        "dramatic_turn": "They discover the water and mark the landing.",
        "shots": [
            {"unit_id": "shot-1", "beat": "Mira sees the floodwater.", "emotion": "Alert",
             "dialogue_delivery": "None", "camera": "wide", "dialogue": []},
            {"unit_id": "shot-2", "beat": "Mira warns Arjun.", "emotion": "Urgent",
             "dialogue_delivery": "Direct", "camera": "close", "dialogue": [{"text": "The water is rising."}]},
        ]}

    context = api._dialogue_context_for_shot(content, {"unit_id": "shot-2"})

    assert context == {"title": "Warning", "location": "Stairwell", "characters": ["Mira", "Arjun"],
        "shot": {"beat": "Mira warns Arjun.", "emotion": "Urgent", "dialogue_delivery": "Direct"}}
    assert "dramatic_turn" not in context
    assert "Mira sees the floodwater" not in json.dumps(context)
    assert "dialogue" not in context["shot"]


@pytest.mark.parametrize("shots", [[], [{"unit_id": "shot-2"}, {"unit_id": "shot-2"}]])
def test_dialogue_context_fails_closed_when_shot_beat_is_missing_or_duplicated(shots):
    with pytest.raises(ValueError, match="exactly one beat"):
        api._dialogue_context_for_shot({"shots": shots}, {"unit_id": "shot-2"})


def test_generated_dialogue_requires_per_shot_stable_speaker_ids():
    units = [{"unit_id": "shot-1", "character_ids": ["char-mira"]}]
    api._validate_generated_dialogue_items([{"unit_id": "shot-1", "content": {
        "dialogue": [{"speaker_id": "char-mira", "text": "The water is rising."}]}}], units)

    with pytest.raises(HTTPException) as malformed:
        api._validate_generated_dialogue_items([{"unit_id": "shot-1", "content": {
            "dialogue": [{"character": "Mira", "text": "The water is rising."}]}}], units)
    assert malformed.value.status_code == 422
    assert malformed.value.detail["code"] == "dialogue_output_invalid"
    assert malformed.value.detail["unit_id"] == "shot-1"
    assert "speaker_id" in malformed.value.detail["invalid_fields"]

    with pytest.raises(HTTPException) as extra_content:
        api._validate_generated_dialogue_items([{"unit_id": "shot-1", "content": {
            "dialogue": [{"speaker_id": "char-mira", "text": "The water is rising."}],
            "action": "Mira looks at the door."}}], units)
    assert extra_content.value.detail["code"] == "dialogue_output_invalid"
    assert extra_content.value.detail["invalid_fields"] == ["content.fields"]


def test_generated_scene_beats_must_match_planned_shot_ids_exactly():
    units = [{"unit_id": "scene-1", "shot_units": [
        {"unit_id": "shot-1"}, {"unit_id": "shot-2"}]}]
    api._validate_generated_scene_items([{"unit_id": "scene-1", "content": {"shots": [
        {"unit_id": "shot-1", "beat": "Mira reaches the landing."},
        {"unit_id": "shot-2", "beat": "Arjun points to the exit."}]}}], units)

    malformed = [
        [{"unit_id": "shot-1", "beat": "Mira reaches the landing."},
         {"beat": "Arjun points to the exit."}],  # missing stable link
        [{"unit_id": "shot-1", "beat": "Mira reaches the landing."},
         {"unit_id": "shot-1", "beat": "Arjun points to the exit."}],  # duplicate
        [{"unit_id": "shot-1", "beat": "Mira reaches the landing."},
         {"unit_id": "shot-extra", "beat": "Unsupported extra beat."}],  # missing + extra
        [{"unit_id": "shot-1", "beat": "Mira reaches the landing."},
         {"unit_id": "shot-2", "beat": "  "}],  # empty beat
    ]
    for beats in malformed:
        with pytest.raises(HTTPException) as invalid:
            api._validate_generated_scene_items([{"unit_id": "scene-1", "content": {"shots": beats}}], units)
        assert invalid.value.status_code == 422
        assert invalid.value.detail["code"] == "scene_output_invalid"
        assert invalid.value.detail["stage"] == "scenes"
        assert invalid.value.detail["retryable"] is True
        assert "shots.unit_id" in invalid.value.detail["invalid_fields"] or "shots.beat" in invalid.value.detail["invalid_fields"]


def test_visual_context_is_bounded_and_keeps_core_shot_direction() -> None:
    content = {
        "title": "At the lighthouse", "location": "the lighthouse", "time": "Sunset",
        "characters": ["Mira", "Arun"], "dramatic_turn": "They return the map to its keeper.",
        "summary": "x" * 10000,
        "shots": [{key: "x" * 1000 for key in ("beat", "emotion", "camera", "lighting", "blocking", "palette")}],
    }

    compact = api._visual_context_for_scene(content)

    assert compact["location"] == "the lighthouse"
    assert compact["characters"] == ["Mira", "Arun"]
    assert compact["shots"][0].keys() == {"beat", "emotion", "camera", "lighting"}
    assert all(len(value) <= 180 for value in compact["shots"][0].values())
    assert len(json.dumps(compact)) < 1500


def _temporary_project(tmp_path: Path, monkeypatch, story: str = "A director enters a silent theater.") -> str:
    store = api.ProjectStore(tmp_path / "projects")
    project = store.create_project(title="Ledger API", story_input=story, automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", store)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    return project["id"]


def test_create_and_get_v2_run_is_idempotent_and_does_not_touch_legacy_run(tmp_path: Path, monkeypatch) -> None:
    project_id = _temporary_project(tmp_path, monkeypatch)
    request = api.ProductionV2RunRequest(
        idempotency_key="browser-start-1", control_mode="semi", making_route="hybrid",
        semi_gates={"voice_selection": True}, narrative_style_id="story_film",
    )

    first = asyncio.run(api.create_production_v2_run(project_id, request))
    again = asyncio.run(api.create_production_v2_run(project_id, request))

    assert first["run_id"] == again["run_id"]
    assert first["status"] == "draft"
    assert first["config"]["control_mode"] == "semi"
    assert first["config"]["making_route"] == "hybrid"
    assert first["config"]["image_workflow_id"] is None
    assert first["config"]["provider"] in {"codex", "ollama"}
    assert first["config"]["source_story_hash"]
    assert first["config"]["h3_rules_version"] == "h3_prompt_rules_v1"
    assert len(first["config"]["h3_rules_hash"]) == 64
    assert first["config"]["director_profile"]["production_type"] == "story_film"
    assert first["config"]["director_profile"]["profile_version"] == "production_director_profiles_v1"
    assert len(first["config"]["director_profile"]["registry_hash"]) == 64
    assert first["config"]["workflow_capabilities"][0]["workflow_id"] == "minimax_h3_r2v_dynamic_v1"

    fetched = asyncio.run(api.get_production_v2_run(project_id, first["run_id"]))
    assert fetched["run_id"] == first["run_id"]
    assert fetched["events"][0]["event_type"] == "run_created"
    project = api.PROJECT_STORE.read_project(project_id)
    assert project.get("production_run") is None


def test_full_reference_built_run_requires_and_freezes_an_image_workflow(tmp_path: Path, monkeypatch) -> None:
    project_id = _temporary_project(tmp_path, monkeypatch)
    missing = api.ProductionV2RunRequest(idempotency_key="full-reference-missing",
        control_mode="fully_automated", making_route="reference_built")
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(api.create_production_v2_run(project_id, missing))
    assert rejected.value.status_code == 422
    assert rejected.value.detail["code"] == "image_workflow_required"

    selected = api.ProductionV2RunRequest(idempotency_key="full-reference-selected",
        control_mode="fully_automated", making_route="reference_built",
        image_workflow_id="z_image_turbo")
    created = asyncio.run(api.create_production_v2_run(project_id, selected))
    assert created["config"]["image_workflow_id"] == "z_image_turbo"


def test_semi_reference_built_requires_workflow_only_when_image_selection_is_delegated(
        tmp_path: Path, monkeypatch) -> None:
    project_id = _temporary_project(tmp_path, monkeypatch)
    delegated_without_workflow = api.ProductionV2RunRequest(idempotency_key="semi-reference-delegated-missing",
        control_mode="semi", making_route="reference_built",
        semi_gates={"image_candidate_selection": False})
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(api.create_production_v2_run(project_id, delegated_without_workflow))
    assert rejected.value.status_code == 422
    assert rejected.value.detail["code"] == "image_workflow_required"

    human_selected = api.ProductionV2RunRequest(idempotency_key="semi-reference-human-selection",
        control_mode="semi", making_route="reference_built",
        semi_gates={"image_candidate_selection": True})
    created = asyncio.run(api.create_production_v2_run(project_id, human_selected))
    assert created["config"]["image_workflow_id"] is None

    delegated_with_workflow = api.ProductionV2RunRequest(idempotency_key="semi-reference-delegated-ready",
        control_mode="semi", making_route="reference_built",
        semi_gates={"image_candidate_selection": False}, image_workflow_id="qwen_image_2512")
    delegated = asyncio.run(api.create_production_v2_run(project_id, delegated_with_workflow))
    assert delegated["config"]["image_workflow_id"] == "qwen_image_2512"


@pytest.mark.parametrize(("initial_status", "interrupt_result", "expected_action"), [
    ("running", (True, "Interrupted only the owned prompt."), "interrupt_requested"),
    ("recovery_required", (False, "Ownership changed; refusing global interrupt."), "reconcile_after_completion"),
])
def test_cancel_active_take_records_intent_and_uses_exact_prompt_guard(
        tmp_path: Path, monkeypatch, initial_status: str, interrupt_result: tuple[bool, str], expected_action: str):
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="cancel-run", control_mode="manual")))
    ledger = api._production_v2_ledger()
    ledger.queue_take(project_id=project_id, run_id=run["run_id"], shot_id="scene-1-cut-1", take_id="cancel-take",
        idempotency_key="cancel-job", input_snapshot={"graph_hash": "g1"})
    ledger.transition_take(project_id=project_id, take_id="cancel-take", status="submitting")
    prompt_id = ledger.reserve_prompt_id(project_id=project_id, take_id="cancel-take")["prompt_id"]
    ledger.bind_prompt_id(project_id=project_id, take_id="cancel-take", prompt_id=prompt_id)
    if initial_status == "running":
        ledger.reconcile_remote_state(project_id=project_id, take_id="cancel-take", observed="running")
    else:
        ledger.transition_take(project_id=project_id, take_id="cancel-take", status="recovery_required")

    class QueueResponse:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps({"queue_running": [[1, prompt_id]], "queue_pending": []}).encode()

    monkeypatch.setattr(api, "COMFYUI_URL", "http://comfy.test")
    monkeypatch.setattr(api, "urlopen", lambda *_args, **_kwargs: QueueResponse())
    guarded = []
    def guarded_interrupt(**kwargs):
        guarded.append(kwargs["prompt_id"])
        current = ledger.get_run(project_id=project_id, run_id=run["run_id"])["takes"][0]
        assert current["status"] == "cancel_requested"
        return interrupt_result
    monkeypatch.setattr(api, "interrupt_if_owned_prompt", guarded_interrupt)

    result = api.cancel_production_v2_take(project_id, run["run_id"], "cancel-take",
        api.ProductionV2CancelRequest(reason="operator stop"))

    assert result["take"]["status"] == "cancel_requested"
    assert result["comfy_action"] == expected_action
    assert guarded == [prompt_id]


def _recovery_take(tmp_path: Path, monkeypatch) -> tuple[str, str, str, Any]:
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="recovery-run", control_mode="manual")))
    ledger = api._production_v2_ledger()
    ledger.queue_take(project_id=project_id, run_id=run["run_id"], shot_id="scene-1-cut-1",
        take_id="recovery-take", idempotency_key="recovery-job", input_snapshot={"graph_hash": "g1"})
    ledger.transition_take(project_id=project_id, take_id="recovery-take", status="submitting")
    prompt_id = ledger.reserve_prompt_id(project_id=project_id, take_id="recovery-take")["prompt_id"]
    ledger.bind_prompt_id(project_id=project_id, take_id="recovery-take", prompt_id=prompt_id)
    ledger.transition_take(project_id=project_id, take_id="recovery-take", status="recovery_required")
    monkeypatch.setattr(api, "COMFYUI_URL", "http://comfy.test")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    return project_id, run["run_id"], prompt_id, ledger


def test_recovery_take_resolves_only_after_exact_prompt_is_absent_and_user_confirms_no_output(tmp_path, monkeypatch):
    project_id, run_id, prompt_id, ledger = _recovery_take(tmp_path, monkeypatch)

    class Response:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(self.body).encode()

    def urlopen(url, timeout=10):
        if url.endswith("/queue"):
            return Response({"queue_running": [], "queue_pending": []})
        assert url.endswith(f"/history/{prompt_id}")
        return Response({})
    monkeypatch.setattr(api, "urlopen", urlopen)

    result = api.reconcile_absent_production_v2_take(project_id, run_id, "recovery-take",
        api.ProductionV2ReconcileAbsentRequest(prompt_id=prompt_id, confirm_no_output=True))
    assert result["take"]["status"] == "failed"
    assert result["take"]["error"]["remote_queue_absent"] is True
    assert result["take"]["error"]["remote_history_absent"] is True
    retried = api.retry_production_v2_take(project_id, run_id, "recovery-take")
    assert retried["take"]["status"] == "queued"
    assert retried["take"]["attempt"] == 2
    assert ledger.get_run(project_id=project_id, run_id=run_id)["takes"][0]["prompt_id"] is None


@pytest.mark.parametrize("observation", ["queued", "history", "unavailable", "malformed"])
def test_recovery_take_stays_blocked_when_remote_absence_is_not_proven(tmp_path, monkeypatch, observation):
    project_id, run_id, prompt_id, ledger = _recovery_take(tmp_path, monkeypatch)

    class Response:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(self.body).encode()

    def urlopen(url, timeout=10):
        if observation == "unavailable": raise OSError("offline")
        if observation == "malformed": return Response({"queue_running": [], "queue_pending": None})
        if url.endswith("/queue"):
            queued = [[1, prompt_id]] if observation == "queued" else []
            return Response({"queue_running": queued, "queue_pending": []})
        return Response({prompt_id: {"outputs": {}}} if observation == "history" else {})
    monkeypatch.setattr(api, "urlopen", urlopen)

    with pytest.raises(HTTPException) as rejected:
        api.reconcile_absent_production_v2_take(project_id, run_id, "recovery-take",
            api.ProductionV2ReconcileAbsentRequest(prompt_id=prompt_id, confirm_no_output=True))
    assert rejected.value.status_code in {409, 503}
    assert ledger.get_run(project_id=project_id, run_id=run_id)["takes"][0]["status"] == "recovery_required"


def test_recovery_take_requires_exact_prompt_and_explicit_no_output_confirmation(tmp_path, monkeypatch):
    project_id, run_id, prompt_id, ledger = _recovery_take(tmp_path, monkeypatch)
    for payload in (
        api.ProductionV2ReconcileAbsentRequest(prompt_id="different-prompt", confirm_no_output=True),
        api.ProductionV2ReconcileAbsentRequest(prompt_id=prompt_id, confirm_no_output=False),
    ):
        with pytest.raises(HTTPException):
            api.reconcile_absent_production_v2_take(project_id, run_id, "recovery-take", payload)
    assert ledger.get_run(project_id=project_id, run_id=run_id)["takes"][0]["status"] == "recovery_required"


def test_recovery_take_refuses_registered_output_even_if_remote_prompt_is_absent(tmp_path, monkeypatch):
    project_id, run_id, prompt_id, ledger = _recovery_take(tmp_path, monkeypatch)
    ledger.transition_take(project_id=project_id, take_id="recovery-take", status="collecting")
    ledger.set_take_outputs(project_id=project_id, take_id="recovery-take",
        outputs=[{"kind": "video", "asset_id": "saved-output", "sha256": "a" * 64}])
    ledger.transition_take(project_id=project_id, take_id="recovery-take", status="recovery_required")

    with pytest.raises(HTTPException) as rejected:
        api.reconcile_absent_production_v2_take(project_id, run_id, "recovery-take",
            api.ProductionV2ReconcileAbsentRequest(prompt_id=prompt_id, confirm_no_output=True))
    assert rejected.value.status_code == 409
    assert ledger.get_run(project_id=project_id, run_id=run_id)["takes"][0]["status"] == "recovery_required"


def test_recovery_take_final_compare_and_set_preserves_worker_state_change(tmp_path, monkeypatch):
    project_id, run_id, prompt_id, ledger = _recovery_take(tmp_path, monkeypatch)

    class Response:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(self.body).encode()
    monkeypatch.setattr(api, "urlopen", lambda url, timeout=10:
        Response({"queue_running": [], "queue_pending": []}) if url.endswith("/queue") else Response({}))

    original = ledger.fail_recovery_if_absent
    monkeypatch.setattr(api, "_production_v2_ledger", lambda: ledger)
    def race(**kwargs):
        ledger.transition_take(project_id=project_id, take_id="recovery-take", status="running")
        return original(**kwargs)
    monkeypatch.setattr(ledger, "fail_recovery_if_absent", race)

    with pytest.raises(HTTPException) as rejected:
        api.reconcile_absent_production_v2_take(project_id, run_id, "recovery-take",
            api.ProductionV2ReconcileAbsentRequest(prompt_id=prompt_id, confirm_no_output=True))
    assert rejected.value.status_code == 409
    assert ledger.get_run(project_id=project_id, run_id=run_id)["takes"][0]["status"] == "running"


def test_run_api_rejects_missing_story_invalid_gates_and_pathlike_project_ids(tmp_path: Path, monkeypatch) -> None:
    project_id = _temporary_project(tmp_path, monkeypatch, story="   ")
    with pytest.raises(HTTPException) as missing_story:
        asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(idempotency_key="k")))
    assert missing_story.value.status_code == 422
    with pytest.raises(HTTPException) as bad_project:
        asyncio.run(api.create_production_v2_run("../outside", api.ProductionV2RunRequest(idempotency_key="k")))
    assert bad_project.value.status_code == 404

    project_id = _temporary_project(tmp_path / "valid", monkeypatch)
    bad_gates = api.ProductionV2RunRequest(idempotency_key="k", semi_gates={"unbounded_gate": True})
    with pytest.raises(HTTPException) as unknown_gate:
        asyncio.run(api.create_production_v2_run(project_id, bad_gates))
    assert unknown_gate.value.status_code == 422


def test_h3_prompt_rules_endpoint_returns_versioned_corpus():
    response = asyncio.run(api.production_v2_h3_prompt_rules())
    assert response["version"] == "h3_prompt_rules_v1"
    assert len(response["content_hash"]) == 64
    assert "reference_roles.md" in response["rules"]


def test_production_image_job_api_queues_project_scoped_idempotent_t2i_candidates(tmp_path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="image-run", control_mode="manual")))
    monkeypatch.setattr(api, "image_workflow_catalog", lambda: {"workflows": [{
        "workflow_id": "z_image_turbo", "available": True, "disabled_reason": None}]})
    request = api.ProductionImageJobRequest(idempotency_key="character-master-1",
        workflow_id="z_image_turbo", asset_role="character_master",
        prompt="A portrait of the lead character", seed=500)
    first = asyncio.run(api.queue_production_image_job(project_id, run["run_id"], request))
    again = asyncio.run(api.queue_production_image_job(project_id, run["run_id"], request))
    assert first["status"] == "queued" and len(first["jobs"]) == 4
    assert first["batch_id"] == again["batch_id"] and again["reused"] is True
    assert all(job["status"] == "queued" for job in first["jobs"])
    batch = asyncio.run(api.get_production_image_job_batch(project_id, first["batch_id"]))
    assert batch["jobs"][0]["workflow_id"] == "z_image_turbo"
    assert "graph" not in batch["jobs"][0]


def test_production_image_job_api_fails_closed_for_unavailable_workflow(tmp_path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="image-run", control_mode="semi")))
    monkeypatch.setattr(api, "image_workflow_catalog", lambda: {"workflows": [{
        "workflow_id": "z_image_turbo", "available": False, "disabled_reason": "GPU model files missing"}]})
    unavailable = api.ProductionImageJobRequest(idempotency_key="unavailable", workflow_id="z_image_turbo",
        asset_role="character_master", prompt="portrait", seed=1)
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(api.queue_production_image_job(project_id, run["run_id"], unavailable))
    assert rejected.value.status_code == 503
    assert rejected.value.detail["code"] == "image_workflow_unavailable"


def test_qwen_edit_api_stages_project_image_and_persists_worker_graph(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from story_builder.services import production_assets
    from story_builder.services.production_image_jobs import ProductionImageJobStore
    from PIL import Image

    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="edit-run", control_mode="manual")))
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    source_path = api.OUTPUT_ROOT / project_id / "source.png"
    source_path.parent.mkdir(parents=True)
    Image.new("RGB", (32, 32), (40, 90, 130)).save(source_path)
    monkeypatch.setattr(production_assets, "_probe_media", lambda *_args, **_kwargs: {"width": 32, "height": 32})
    asset = production_assets.register_output(api.PROJECT_STORE.root_dir, api.OUTPUT_ROOT, project_id,
        relative_path="source.png", role="project_image", metadata={"source": "fixture"})
    monkeypatch.setattr(api, "image_workflow_catalog", lambda: {"workflows": [{
        "workflow_id": "qwen_image_edit_2511", "available": True, "disabled_reason": None}]})
    staged = []
    def fake_stage(source, *, asset_id, owner_id, **_kwargs):
        source_bytes = Path(source).read_bytes()
        staged.append((asset_id, owner_id, source_bytes))
        return SimpleNamespace(filename=f"staged-{asset_id}.png", source_sha256=hashlib.sha256(source_bytes).hexdigest())
    monkeypatch.setattr(api, "stage_image_reference", fake_stage)
    request = api.ProductionImageJobRequest(idempotency_key="edit-image-1",
        workflow_id="qwen_image_edit_2511", asset_role="character_master", prompt="Change the coat to green",
        seed=502, source_asset_ids=[asset["asset_id"]])

    first = asyncio.run(api.queue_production_image_job(project_id, run["run_id"], request))
    again = asyncio.run(api.queue_production_image_job(project_id, run["run_id"], request))

    assert first["batch_id"] == again["batch_id"] and again["reused"] is True
    assert len(first["jobs"]) == 4
    assert "staging_owner_id" not in first["jobs"][0]["settings"]
    assert len(staged) == 2  # the second request re-resolves and idempotently reuses the owner file
    assert staged[0][0] == asset["asset_id"]
    store = ProductionImageJobStore(api.STORAGE_ROOT / "production" / "v2_ledger.sqlite3")
    private = store.next_queued()
    assert private["settings"]["source_asset_ids"] == [asset["asset_id"]]
    assert private["settings"]["source_provenance"] == [{"asset_id": asset["asset_id"], "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest()}]
    assert private["graph"]["78"]["inputs"]["image"] == f"staged-{asset['asset_id']}.png"
    assert private["settings"]["staging_owner_id"].startswith("image_")


def test_qwen_edit_api_rejects_unaccepted_candidate_source(tmp_path, monkeypatch):
    from story_builder.services import production_assets
    from PIL import Image
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="edit-source-run", control_mode="manual")))
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    source = api.OUTPUT_ROOT / project_id / "candidate.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (16, 16), (1, 2, 3)).save(source)
    monkeypatch.setattr(production_assets, "_probe_media", lambda *_args, **_kwargs: {"width": 16, "height": 16})
    candidate = production_assets.register_output(api.PROJECT_STORE.root_dir, api.OUTPUT_ROOT, project_id,
        relative_path="candidate.png", role="image_candidate", metadata={"production_image_job": {"accepted": False}})
    monkeypatch.setattr(api, "image_workflow_catalog", lambda: {"workflows": [{
        "workflow_id": "qwen_image_edit_2511", "available": True, "disabled_reason": None}]})
    monkeypatch.setattr(api, "stage_image_reference", lambda *_args, **_kwargs: pytest.fail("unaccepted sources must not be staged"))
    payload = api.ProductionImageJobRequest(idempotency_key="edit-unaccepted", workflow_id="qwen_image_edit_2511",
        asset_role="character_master", prompt="edit", seed=1, source_asset_ids=[candidate["asset_id"]])
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(api.queue_production_image_job(project_id, run["run_id"], payload))
    assert rejected.value.status_code == 409
    assert rejected.value.detail["code"] == "edit_source_candidate_unaccepted"
    missing = payload.model_copy(update={"idempotency_key": "edit-missing-source",
        "source_asset_ids": ["pa-0000000000000000"]})
    with pytest.raises(HTTPException) as not_found:
        asyncio.run(api.queue_production_image_job(project_id, run["run_id"], missing))
    assert not_found.value.status_code == 422
    assert not_found.value.detail["code"] == "asset_not_found"


def test_full_image_job_requires_active_identity_and_persists_bounded_director_policy(tmp_path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="full-image-run", control_mode="fully_automated")))
    character = asyncio.run(api.create_project_character_identity(project_id,
        api.ProductionCanonCharacterCreateRequest()))["character"]
    monkeypatch.setattr(api, "image_workflow_catalog", lambda: {"workflows": [{
        "workflow_id": "z_image_turbo", "available": True, "disabled_reason": None}]})
    payload = api.ProductionImageJobRequest(idempotency_key="full-image-candidate", workflow_id="z_image_turbo",
        asset_role="character_master", prompt="portrait", seed=7)
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(api.queue_production_image_job(project_id, run["run_id"], payload))
    assert rejected.value.status_code == 422
    assert rejected.value.detail["code"] == "image_identity_required"
    wrong_identity = payload.model_copy(update={"entity_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"})
    with pytest.raises(HTTPException) as wrong:
        asyncio.run(api.queue_production_image_job(project_id, run["run_id"], wrong_identity))
    assert wrong.value.status_code == 422
    assert wrong.value.detail["code"] == "image_identity_not_in_canon"
    queued = asyncio.run(api.queue_production_image_job(project_id, run["run_id"],
        payload.model_copy(update={"entity_id": character["character_id"]})))
    assert len(queued["jobs"]) == 1
    assert queued["generation_policy"] == {"initial_candidates": 1, "selection_authority": "director",
        "retake_supported": True, "full_retake_budget": 2}
    assert queued["jobs"][0]["settings"]["review_identity"]["entity_id"] == character["character_id"]
    assert queued["jobs"][0]["settings"]["director_review_required"] is True
    assert queued["jobs"][0]["settings"]["director_provider"] == run["config"]["provider"]
    polled = asyncio.run(api.get_production_image_job_batch(project_id, queued["batch_id"]))
    assert polled["generation_policy"]["selection_authority"] == "director"


def test_production_image_candidate_acceptance_is_run_scoped_and_additive(tmp_path, monkeypatch):
    from story_builder.services import production_assets
    from story_builder.services.production_image_jobs import ProductionImageJobStore

    project_id = _temporary_project(tmp_path, monkeypatch)
    manual_run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="candidate-manual-run", control_mode="manual")))
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(production_assets, "_probe_media", lambda *_args, **_kwargs: {"width": 512, "height": 512})
    store = ProductionImageJobStore(api.STORAGE_ROOT / "production" / "v2_ledger.sqlite3")
    batch = store.enqueue_batch(project_id=project_id, run_id=manual_run["run_id"], idempotency_key="candidate-job",
        workflow_id="z_image_turbo", workflow_version="1", asset_role="character_master", prompt="portrait",
        settings={"width": 512}, candidates=[{"seed": 19, "graph": {"save": {"class_type": "SaveImage", "inputs": {"filename_prefix": "p/b/candidate"}}}}])
    job = store.next_queued()
    store.reserve_prompt_id(job["job_id"])
    store.transition(job["job_id"], "running")
    relative = f"production/image_jobs/{job['job_id']}/candidate.png"
    output = api.OUTPUT_ROOT / project_id / relative
    output.parent.mkdir(parents=True)
    output.write_bytes(b"generated image test fixture")
    asset = production_assets.register_output(api.PROJECT_STORE.root_dir, api.OUTPUT_ROOT, project_id,
        relative_path=relative, role="image_candidate", metadata={"production_image_job": {
            "job_id": job["job_id"], "run_id": manual_run["run_id"], "status": "completed",
            "intended_role": "character_master", "accepted": False}})
    store.transition(job["job_id"], "completed", output_asset_id=asset["asset_id"])
    accepted = asyncio.run(api.accept_production_image_candidate_route(project_id, manual_run["run_id"],
        asset["asset_id"], api.ProductionImageCandidateAcceptRequest(role="character_master")))
    assert accepted["asset_id"] == asset["asset_id"]
    assert accepted["roles"] == ["image_candidate", "character_master"]
    assert accepted["metadata"]["production_image_job"]["accepted_by"] == "user"
    assert output.is_file()

    full_run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="candidate-full-run", control_mode="fully_automated")))
    with pytest.raises(HTTPException) as full_mode:
        asyncio.run(api.accept_production_image_candidate_route(project_id, full_run["run_id"],
            asset["asset_id"], api.ProductionImageCandidateAcceptRequest(role="character_master")))
    assert full_mode.value.status_code == 409
    assert full_mode.value.detail["code"] == "director_image_acceptance_unavailable"


def test_project_canon_routes_create_stable_character_and_world_bibles(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    first = asyncio.run(api.create_project_character_identity(project_id,
        api.ProductionCanonCharacterCreateRequest()))
    second = asyncio.run(api.create_project_character_identity(project_id,
        api.ProductionCanonCharacterCreateRequest()))
    assert first["character"]["character_id"] != second["character"]["character_id"]
    assert first["character"]["display_name"] != second["character"]["display_name"]
    assert first["character"]["display_name"].startswith("Character-")
    world = asyncio.run(api.create_project_world_identity(project_id,
        api.ProductionCanonWorldCreateRequest(display_name="Maya's apartment", description="North-facing window.")))
    canon = asyncio.run(api.get_project_production_canon(project_id))
    assert canon["revision"] == 3
    assert len(canon["characters"]) == 2 and canon["worlds"][0]["world_id"] == world["world"]["world_id"]
    edited = [{**row, "display_name": "Maya"} if row["character_id"] == first["character"]["character_id"] else row
              for row in canon["characters"]]
    saved = asyncio.run(api.put_project_production_canon(project_id, api.ProductionCanonSaveRequest(
        expected_revision=canon["revision"], characters=edited, worlds=canon["worlds"])))
    assert saved["characters"][0]["character_id"] == first["character"]["character_id"]


def test_project_canon_route_rejects_stale_edit_without_overwrite(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    created = asyncio.run(api.create_project_character_identity(project_id,
        api.ProductionCanonCharacterCreateRequest(display_name="Maya")))
    with pytest.raises(HTTPException) as stale:
        asyncio.run(api.put_project_production_canon(project_id, api.ProductionCanonSaveRequest(
            expected_revision=0, characters=[created["character"]], worlds=[])))
    assert stale.value.status_code == 409
    assert asyncio.run(api.get_project_production_canon(project_id))["revision"] == 1


def test_voice_binding_api_is_additive_project_scoped_and_manual_only_when_selected(tmp_path: Path, monkeypatch):
    from story_builder.services import production_assets

    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="voice-run", control_mode="manual")))
    character = asyncio.run(api.create_project_character_identity(project_id,
        api.ProductionCanonCharacterCreateRequest(display_name="Maya")))["character"]
    monkeypatch.setattr(production_assets, "_probe_media", lambda *_args, **_kwargs: {
        "duration_seconds": 35.0, "format": "wav", "streams": [{"codec_type": "audio", "codec_name": "pcm_s16le"}]})
    voice = production_assets.register_upload(api.PROJECT_STORE.root_dir, project_id,
        filename="voice.wav", content=b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 40,
        role="voice_master")
    payload = api.ProductionVoiceBindingRequest(character_id=character["character_id"],
        strategy="manual", voice_asset_id=voice["asset_id"])
    result = asyncio.run(api.create_production_voice_binding(project_id, run["run_id"], payload))
    assert result["voice_asset_id"] == voice["asset_id"] and result["speaker_id"] == "S1"
    stored = asyncio.run(api.get_production_voice_bindings(project_id, run["run_id"]))
    assert stored["bindings"][0]["binding_id"] == result["binding_id"]
    run_after = asyncio.run(api.get_production_v2_run(project_id, run["run_id"]))
    assert run_after["events"][-1]["event_type"] == "voice_binding_created"


def test_voice_binding_api_requires_existing_canon_identity(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="voice-run-missing-character", control_mode="manual")))
    with pytest.raises(HTTPException) as missing:
        asyncio.run(api.create_production_voice_binding(project_id, run["run_id"],
            api.ProductionVoiceBindingRequest(character_id="00000000-0000-4000-8000-000000000001",
                                              strategy="manual", voice_asset_id="pa-0000000000000000")))
    assert missing.value.status_code == 404


def test_director_outline_voice_preparation_persists_seeded_bindings_and_reuses_them(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace
    import uuid

    project_id = "director-voices"
    run_id = str(uuid.uuid4())
    character_id = str(uuid.uuid4())
    asset_id = "voice-master-local"
    assets = [{"asset_id": asset_id, "kind": "audio", "roles": ["voice_master"],
        "source": "upload", "sha256": "a" * 64, "media": {"duration_seconds": 35.0},
        "metadata": {"approval_status": "accepted"}}]
    monkeypatch.setattr(api, "PROJECT_STORE", SimpleNamespace(root_dir=tmp_path))
    monkeypatch.setattr(api, "read_project_canon", lambda *_args: {"characters": [
        {"character_id": character_id, "status": "active"}]})
    monkeypatch.setattr(api, "list_production_assets", lambda *_args, **_kwargs: {
        "assets": assets, "total": len(assets)})
    monkeypatch.setattr(api, "get_production_asset_record", lambda *_args: {"asset_id": asset_id})

    config = {"control_mode": "fully_automated", "semi_gates": {}}
    first = api._prepare_director_voice_bindings(project_id, run_id, config, [character_id])
    second = api._prepare_director_voice_bindings(project_id, run_id, config, [character_id])
    saved = api.list_production_voice_bindings(tmp_path, project_id, run_id=run_id)["bindings"]

    assert first == {"status": "complete", "bound_count": 1, "pending_count": 0}
    assert second == first
    assert len(saved) == 1
    assert saved[0]["strategy"] == "seeded_random"
    assert saved[0]["voice_asset_id"] == asset_id
    assert saved[0]["seed"] is not None


def test_director_outline_voice_preparation_reports_missing_pool_and_respects_semi_gate(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace
    import uuid

    project_id = "director-voices"
    run_id = str(uuid.uuid4())
    character_id = str(uuid.uuid4())
    monkeypatch.setattr(api, "PROJECT_STORE", SimpleNamespace(root_dir=tmp_path))
    monkeypatch.setattr(api, "read_project_canon", lambda *_args: {"characters": [
        {"character_id": character_id, "status": "active"}]})
    monkeypatch.setattr(api, "list_production_assets", lambda *_args, **_kwargs: {"assets": [], "total": 0})

    missing = api._prepare_director_voice_bindings(project_id, run_id,
        {"control_mode": "fully_automated"}, [character_id])
    manual_gate = api._prepare_director_voice_bindings(project_id, run_id,
        {"control_mode": "semi", "semi_gates": {"voice_selection": True}}, [character_id])

    assert missing == {"status": "needs_eligible_voice_assets", "bound_count": 0,
        "pending_count": 1, "minimum_voice_seconds": 30}
    assert manual_gate == {"status": "human_selection_required", "bound_count": 0, "pending_count": 0}


def test_shot_plan_get_and_put_api_use_optimistic_immutable_revisions(tmp_path: Path, monkeypatch):
    from story_builder.services.production_shot_plan import canonical_content_hash
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="shot-edit", control_mode="manual")))
    content = {"prompt": "Maya enters.", "duration_seconds": 6, "asset_intents": [],
        "reference_map": {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}}}
    revision = {"schema_version": 1, "revision_id": "shot_plans-abcdef012345", "project_id": project_id,
        "run_id": run["run_id"], "stage": "shot_plans", "source_story_hash": "a" * 64,
        "review_status": "accepted", "accepted_at": "2026-10-02T00:00:00+00:00",
        "items": [{"unit_id": "scene-1-cut-1", "source_chunk_ids": [], "content": content}]}
    api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id,
        run["run_id"], "shot_plans", revision)
    loaded = api.get_production_v2_shot(project_id, run["run_id"], "scene-1-cut-1")
    response = api.put_production_v2_shot(project_id, run["run_id"], "scene-1-cut-1",
        api.ProductionV2ShotEditRequest(expected_revision_id=revision["revision_id"],
            expected_content_hash=canonical_content_hash(content), content_patch={"prompt": "Maya enters cautiously."}))
    assert response["review_required"] is True
    assert response["revision"]["parent_revision_id"] == loaded["revision_id"]
    assert response["shot"]["content"]["reference_map"] == content["reference_map"]
    assert response["output_path"].startswith(f"{project_id}/production_v2/runs/")


def test_shot_plan_put_api_blocks_manual_edits_when_semi_delegates_story_review(tmp_path: Path, monkeypatch):
    from story_builder.services.production_shot_plan import canonical_content_hash
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="shot-edit-semi-delegated", control_mode="semi",
        semi_gates={"story_review": False})))
    content = {"prompt": "Maya enters.", "duration_seconds": 6, "asset_intents": [],
        "reference_map": {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}}}
    revision = {"schema_version": 1, "revision_id": "shot_plans-fedcba654321", "project_id": project_id,
        "run_id": run["run_id"], "stage": "shot_plans", "source_story_hash": "a" * 64,
        "review_status": "accepted", "accepted_at": "2026-10-02T00:00:00+00:00",
        "items": [{"unit_id": "scene-1-cut-1", "source_chunk_ids": [], "content": content}]}
    api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id,
        run["run_id"], "shot_plans", revision)
    with pytest.raises(HTTPException) as blocked:
        api.put_production_v2_shot(project_id, run["run_id"], "scene-1-cut-1",
            api.ProductionV2ShotEditRequest(expected_revision_id=revision["revision_id"],
                expected_content_hash=canonical_content_hash(content), content_patch={"prompt": "Maya enters cautiously."}))
    assert blocked.value.status_code == 409
    assert blocked.value.detail["code"] == "director_review_required"


def test_shot_composer_draft_is_durable_revision_checked_and_separate_from_accepted_plan(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="shot-draft", control_mode="manual")))
    revision = {"schema_version": 1, "revision_id": "shot_plans-aaaaaaaaaaaa", "project_id": project_id,
        "run_id": run["run_id"], "stage": "shot_plans", "source_story_hash": "a" * 64,
        "review_status": "accepted", "accepted_at": "2026-10-02T00:00:00+00:00",
        "items": [{"unit_id": "scene-1-cut-1", "source_chunk_ids": [],
                   "content": {"prompt": "Maya enters.", "duration_seconds": 5}}]}
    api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id,
        run["run_id"], "shot_plans", revision)
    initial = api.get_production_v2_shot_draft(project_id, run["run_id"], "scene-1-cut-1")
    assert initial == {"shot_id": "scene-1-cut-1", "revision": 0, "draft": None, "stale": False}
    request = api.ProductionV2ShotDraftRequest(
        expected_draft_revision=0, shot_plan_revision_id=revision["revision_id"],
        prompt="Maya enters through the rain.", duration_seconds=7, resolution_preset=0.98,
        steps=20, ref_image_size="max", seed=17,
        images=[{"asset_id": "pa-aaaaaaaaaaaaaaaa", "role": "character_master", "intent": "Keep Maya's identity."}],
        videos=[], standalone_audios=[])
    saved = api.save_production_v2_shot_draft(project_id, run["run_id"], "scene-1-cut-1", request)
    assert saved["revision"] == 1 and saved["draft"]["images"][0]["asset_id"] == "pa-aaaaaaaaaaaaaaaa"
    assert saved["stale"] is False
    ledger = api._production_v2_ledger()
    ledger.queue_take(project_id=project_id, run_id=run["run_id"], shot_id="scene-1-cut-1",
        take_id="queued-from-draft-r1", idempotency_key="queued-from-draft-r1",
        input_snapshot={"validation_request": saved["draft"],
            "shot_plan_revision_id": revision["revision_id"]})
    edited = api.save_production_v2_shot_draft(project_id, run["run_id"], "scene-1-cut-1",
        request.model_copy(update={"expected_draft_revision": 1, "prompt": "Changed after queue."}))
    assert edited["held_child_take_ids"] == ["queued-from-draft-r1"]
    take_state = {row["take_id"]: row for row in ledger.get_run(project_id=project_id,
        run_id=run["run_id"])["takes"]}
    assert take_state["queued-from-draft-r1"]["status"] == "waiting_for_user"
    assert ledger.claim_next_queued_take(lease_owner="draft-change-race-check") is None
    restored = api.get_production_v2_shot_draft(project_id, run["run_id"], "scene-1-cut-1")
    assert restored["draft"]["prompt"] == "Changed after queue."
    assert restored["draft"]["steps"] == 20
    run_after = asyncio.run(api.get_production_v2_run(project_id, run["run_id"]))
    assert any(event["event_type"] == "child_draft_changed_after_queue" for event in run_after["events"])
    with pytest.raises(HTTPException) as stale:
        api.save_production_v2_shot_draft(project_id, run["run_id"], "scene-1-cut-1",
            request.model_copy(update={"prompt": "Old tab overwrite"}))
    assert stale.value.status_code == 409
    assert api.get_production_v2_shot(project_id, run["run_id"], "scene-1-cut-1")["shot"]["content"]["prompt"] == "Maya enters."


def test_director_profile_catalog_is_additive_and_versioned():
    response = asyncio.run(api.production_v2_director_profiles())
    assert response["version"] == "production_director_profiles_v1"
    assert len(response["content_hash"]) == 64
    assert "news_report" in response["profiles"]
    assert response["profiles"]["news_report"]["review_priorities"]


def test_style_source_upload_is_additive_deduplicated_and_rejects_video(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")

    async def exercise_routes() -> None:
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post("/api/production/v2/style-sources",
                                      files={"file": ("guide.md", b"# Style\n\nUse sparse dialogue.", "text/markdown")})
            assert first.status_code == 201
            source = first.json()
            assert source["source_id"].startswith("style-source-")
            assert source["evidence_blocks"][0]["locator"] == "line:1-1"
            repeated = await client.post("/api/production/v2/style-sources",
                                         files={"file": ("same.md", b"# Style\n\nUse sparse dialogue.", "text/markdown")})
            assert repeated.status_code == 201
            assert repeated.json()["deduplicated"] is True
            listed = await client.get("/api/production/v2/style-sources")
            assert len(listed.json()["sources"]) == 1
            rejected = await client.post("/api/production/v2/style-sources",
                                         files={"file": ("clip.mp4", b"video", "video/mp4")})
            assert rejected.status_code == 422
            assert rejected.json()["detail"]["code"] == "unsupported_style_source"

    asyncio.run(exercise_routes())


def test_style_variant_api_publish_and_run_snapshot_are_revision_safe(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    rules = {stage: [f"Use restrained choices for {stage}."]
             for stage in ("story", "scene_direction", "image", "audio", "video", "review")}

    async def exercise_routes() -> None:
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            uploaded = await client.post("/api/production/v2/style-sources",
                files={"file": ("source.txt", b"Use pauses before reveals.\n", "text/plain")})
            assert uploaded.status_code == 201
            source_id = uploaded.json()["source_id"]
            draft_response = await client.post("/api/production/v2/styles/drafts", json={
                "base_style_id": "story_film", "display_name": "Quiet Suspense",
                "source_ids": [source_id], "rules_by_stage": rules,
                "evidence": [{"source_id": source_id, "locator": "line:1-1",
                    "quote": "Use pauses before reveals.", "statement": "Favor pauses before a reveal.",
                    "kind": "explicit", "confidence": 0.9}],
            })
            assert draft_response.status_code == 201
            draft = draft_response.json()
            variant_id = draft["variant_id"]
            draft_list = await client.get("/api/production/v2/styles/drafts")
            assert [row["variant_id"] for row in draft_list.json()["drafts"]] == [variant_id]
            stale = await client.put(f"/api/production/v2/styles/drafts/{variant_id}", json={
                "base_style_id": "story_film", "display_name": "Stale", "rules_by_stage": rules,
                "expected_revision": 0,
            })
            assert stale.status_code == 422
            published = await client.post(f"/api/production/v2/styles/drafts/{variant_id}/publish",
                                          json={"expected_revision": 1})
            assert published.status_code == 200
            versions = await client.get(f"/api/production/v2/styles/{variant_id}/versions")
            assert [row["version"] for row in versions.json()["versions"]] == [1]
            tree = await client.get("/api/production/v2/styles")
            story_base = next(row for row in tree.json()["production_types"] if row["production_type"] == "story_film")
            assert story_base["variants"][0]["variant_id"] == variant_id

            run = await client.post(f"/api/projects/{project_id}/production/v2/runs", json={
                "idempotency_key": "with-style-variant", "production_type": "story_film",
                "narrative_style_variant_id": variant_id,
            })
            assert run.status_code == 201
            snapshot = run.json()["config"]["narrative_style_variant"]
            assert snapshot["version"] == 1
            assert snapshot["content_hash"] == published.json()["content_hash"]

    asyncio.run(exercise_routes())


def test_published_variant_stage_rules_reach_the_generation_context(tmp_path: Path, monkeypatch):
    from story_builder.services import narrative_style_library

    project_id = _temporary_project(tmp_path, monkeypatch, story="Mira waits before opening the observatory door.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: {
        "review_id": "approved", "decision": "approve", "accepted": True,
        "reviews": [], "issues": [], "repair_instructions": [], "repaired_chunks": {}})
    rules = {stage: [f"Base {stage} guidance."] for stage in narrative_style_library.STAGES}
    rules["scene_direction"] = ["Hold a quiet beat before Mira opens the door."]
    draft = narrative_style_library.create_draft(tmp_path / "storage" / "production" / "style_library", {
        "base_style_id": "story_film", "display_name": "Measured reveal", "source_ids": [],
        "rules_by_stage": rules, "director_behavior_overrides": {"pacing": ["Pause before reveals."]},
        "evidence": [{"source_id": None, "locator": "user-authored", "quote": "",
            "statement": "User-authored: pause before reveals.", "kind": "user_authored", "confidence": 1.0}],
        "negative_constraints": ["Do not change story facts."], "example_brief": "Mira waits at a door."})
    narrative_style_library.publish_draft(tmp_path / "storage" / "production" / "style_library",
        draft["variant_id"], expected_revision=draft["draft_revision"])
    captured = {}
    def generate_units(**kwargs):
        captured.update(kwargs)
        return {"stage": kwargs["stage"], "items": [{"unit_id": row["unit_id"],
            "content": {"description": "Mira waits before opening the door."}} for row in kwargs["units"]],
            "expected_unit_ids": [row["unit_id"] for row in kwargs["units"]],
            "completed_unit_ids": [row["unit_id"] for row in kwargs["units"]], "complete": True}
    monkeypatch.setattr(api, "generate_chunked_units", generate_units)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="variant-behavior", production_type="story_film",
        narrative_style_variant_id=draft["variant_id"])))
    pending = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"],
        pending["revision"]["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=pending["revision"]["source_hash"])))
    api.generate_production_v2_text_stage(project_id, run["run_id"], "scenes",
        api.ProductionV2TextStageRequest(source_revision_id=pending["revision"]["revision_id"],
            units=[{"unit_id": "scene-001", "source_chunk_ids": ["story_chunk_0001"]}]))
    guidance = captured["context"]["narrative_style_guidance"]
    assert guidance["variant_id"] == draft["variant_id"]
    assert guidance["variant_version"] == 1
    assert guidance["style_stage"] == "scene_direction"
    assert guidance["base_rule"]
    assert guidance["variant_rules"] == ["Hold a quiet beat before Mira opens the door."]
    assert guidance["evidence"][0]["kind"] == "user_authored"


def test_style_analyze_route_uses_selected_provider_and_returns_draft_only(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api.reasoning_provider, "get_settings", lambda: {"provider": "codex"})
    seen = {}

    def analyze(root, *, base_style_id, source_ids, provider):
        seen.update({"root": root, "base_style_id": base_style_id,
                     "source_ids": source_ids, "provider": provider})
        return {"status": "draft_proposal", "persisted": False, "published": False}

    monkeypatch.setattr(api, "analyze_narrative_style_sources", analyze)

    async def exercise_route() -> None:
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/production/v2/styles/analyze", json={
                "base_style_id": "story_film", "source_ids": ["style-source-0123456789abcdef"]})
            assert response.status_code == 200
            assert response.json()["published"] is False

    asyncio.run(exercise_route())
    assert seen["provider"] == "codex"
    assert seen["base_style_id"] == "story_film"


def test_run_rejects_unknown_production_type(tmp_path: Path, monkeypatch) -> None:
    project_id = _temporary_project(tmp_path, monkeypatch)
    request = api.ProductionV2RunRequest(idempotency_key="unknown-type", production_type="unsupported")
    with pytest.raises(HTTPException) as invalid:
        asyncio.run(api.create_production_v2_run(project_id, request))
    assert invalid.value.status_code == 422
    assert invalid.value.detail["code"] == "invalid_production_type"


def test_v2_routes_are_registered_without_replacing_legacy_production_routes():
    routes = {(method, route.path) for route in api.app.routes
              for method in getattr(route, "methods", set())}
    assert ("POST", "/api/projects/{project_id}/production/v2/runs/{run_id}/story/detail") in routes
    assert ("POST", "/api/projects/{project_id}/production/v2/runs/{run_id}/text/{stage}") in routes
    assert ("POST", "/api/projects/{project_id}/production/start") in routes
    assert ("GET", "/api/projects/{project_id}/production/v2/assets") in routes
    assert ("POST", "/api/projects/{project_id}/production/v2/assets") in routes
    assert ("POST", "/api/projects/{project_id}/production/v2/assets/links") in routes
    assert ("GET", "/api/projects/{project_id}/production/v2/assets/{asset_id}/content") in routes
    assert ("GET", "/api/production/v2/image-workflows") in routes
    assert ("POST", "/api/projects/{project_id}/production/v2/runs/{run_id}/image-jobs") in routes
    assert ("GET", "/api/projects/{project_id}/production/v2/image-jobs/{batch_id}") in routes
    assert ("POST", "/api/projects/{project_id}/production/v2/runs/{run_id}/image-candidates/{asset_id}/accept") in routes
    assert ("POST", "/api/projects/{project_id}/production/v2/runs/{run_id}/shots/{shot_id}/validate") in routes


def test_image_workflow_preflight_route_is_additive_and_read_only(monkeypatch):
    expected = {"schema_version": 1, "workflows": [{"workflow_id": "qwen_image_2512", "available": False}]}
    monkeypatch.setattr(api, "image_workflow_catalog", lambda: expected)
    assert asyncio.run(api.production_v2_image_workflows()) == expected


def test_shot_validation_requires_accepted_revision_and_audits_gpu_free_preview(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "validate_and_compile_shot", lambda plan, **_kwargs: {
        "valid": True, "validation_hash": "a" * 64, "workflow_id": "minimax_h3_r2v_dynamic_v1",
        "reference_map": {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}},
        "asset_fingerprints": {}, "width": 1344, "height": 768, "frame_count": 125,
        "duration_seconds": 5.0, "graph_compiler_version": "1.0.0"})
    capability = api.dynamic_h3_capability()
    capability.update({"available": False, "disabled_reason": "No smoke"})
    monkeypatch.setattr(api, "dynamic_h3_capability", lambda: capability)
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="shot-validate", control_mode="manual")))
    request = api.ProductionV2ShotValidateRequest(shot_plan_revision_id="shot_plans-aaaaaaaaaaaa",
        prompt="The Director prepared this prompt.")
    with pytest.raises(HTTPException) as missing:
        api.validate_production_v2_shot(project_id, run["run_id"], "cut-01", request)
    assert missing.value.status_code == 409

    revision = {"schema_version": 1, "revision_id": "shot_plans-aaaaaaaaaaaa", "stage": "shot_plans",
        "review_status": "accepted", "items": [{"unit_id": "cut-01", "content": {
            "prompt": "The Director prepared this prompt.", "asset_intents": []}}]}
    api.production_story_revisions.write_stage_revision(tmp_path / "output", project_id, run["run_id"], "shot_plans", revision)
    result = api.validate_production_v2_shot(project_id, run["run_id"], "cut-01", request)
    assert result["valid"] is True
    assert result["workflow_readiness"]["available"] is False
    map_result = api.validate_production_v2_shot(project_id, run["run_id"], "cut-01",
        request.model_copy(update={"reference_map_only": True}))
    assert map_result["reference_map_ready"] is True
    assert map_result["prompt_tags_validated"] is False
    assert "workflow_readiness" not in map_result
    events = asyncio.run(api.get_production_v2_run(project_id, run["run_id"]))["events"]
    assert any(event["event_type"] == "shot_plan_validated" for event in events)
    assert any(event["event_type"] == "shot_reference_map_resolved" for event in events)


def test_shot_prompt_preparation_persists_run_pinned_request_and_worker_result(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="prompt-prep-run", control_mode="semi")))
    revision = {"schema_version": 1, "revision_id": "shot_plans-bbbbbbbbbbbb", "stage": "shot_plans",
        "review_status": "accepted", "created_at": "2026-10-05T00:00:00+00:00",
        "items": [{"unit_id": "cut-01", "scene_id": "scene-01", "content": {
            "prompt": "A performer crosses a quiet stage.", "duration_seconds": 5.0,
            "shot_intent": "Reveal the empty theater.", "dialogue": [], "asset_intents": []}}]}
    api.production_story_revisions.write_stage_revision(tmp_path / "output", project_id,
        run["run_id"], "shot_plans", revision)
    resolution = {"reference_map_ready": True, "prompt_tags_validated": False,
        "reference_resolution_hash": "r" * 64, "asset_fingerprints": {},
        "reference_map": {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}},
        "workflow_id": "minimax_h3_t2v_local_v1", "route_asset_policy": {"satisfied": True}}
    monkeypatch.setattr(api, "validate_production_v2_shot", lambda *_args, **_kwargs: resolution)
    generated_prompt = "A performer crosses the empty theater."
    generated = {"prompt": generated_prompt, "accepted": True,
        "lint": {"ok": True, "errors": [], "warnings": []}, "review": {"decision": "approve"},
        "review_history": [], "repair_attempted": False, "provider": run["config"]["provider"],
        "input_hash": "i" * 64, "prompt_hash": hashlib.sha256(generated_prompt.encode("utf-8")).hexdigest(),
        "corpus_version": run["config"]["h3_rules_version"], "corpus_hash": run["config"]["h3_rules_hash"],
        "reference_map": resolution["reference_map"]}
    generation_calls = []
    monkeypatch.setattr(api, "generate_resolved_shot_prompt", lambda **kwargs:
        (generation_calls.append(kwargs) or generated))
    validation_request = api.ProductionV2ShotValidateRequest(
        shot_plan_revision_id=revision["revision_id"], prompt="A performer crosses a quiet stage.")
    payload = api.ProductionV2ShotPromptPrepareRequest(idempotency_key="prompt-prep-cut-1",
        shot_plan_revision_id=revision["revision_id"], validation_request=validation_request)
    background = api.BackgroundTasks()
    queued = api.enqueue_production_v2_shot_prompt_preparation(project_id, run["run_id"], "cut-01",
        payload, background)
    assert queued["stage"] == "controller:resolved_shot_prompt"
    assert queued["status"] == "queued"
    assert len(background.tasks) == 1
    stored = api._production_stage_task_store().get(project_id=project_id, run_id=run["run_id"],
        task_id=queued["task_id"])
    assert stored["request"]["reference_map"] == resolution["reference_map"]
    assert stored["request"]["run_config_hash"]

    api._execute_production_story_stage_task(queued["task_id"])
    completed = api.get_production_v2_shot_prompt_preparation(project_id, run["run_id"], "cut-01",
        queued["task_id"])
    assert completed["status"] == "completed"
    assert completed["result"]["prompt"] == generated["prompt"]
    assert completed["result"]["resolved_validation_request"]["prompt"] == generated["prompt"]
    assert completed["result"]["accepted"] is True
    assert completed["result"]["reference_resolution_hash"] == "r" * 64

    # Simulate a backend restart by constructing a new store object over the
    # same SQLite file, then replay the identical preparation request. The
    # completed result must be reused without re-running provider work.
    restarted_store = api.ProductionStageTaskStore(api.STORAGE_ROOT / "production" / "v2_ledger.sqlite3")
    assert restarted_store.get(project_id=project_id, run_id=run["run_id"],
        task_id=queued["task_id"])["result"] == completed["result"]
    replay_background = api.BackgroundTasks()
    replayed_task = api.enqueue_production_v2_shot_prompt_preparation(project_id, run["run_id"], "cut-01",
        payload, replay_background)
    assert replayed_task["task_id"] == queued["task_id"]
    assert replayed_task["status"] == "completed"
    assert replay_background.tasks == []
    assert len(generation_calls) == 1

    final_validation = {**resolution, "valid": True, "validation_hash": "v" * 64,
        "workflow_version": 1, "workflow_readiness": {"available": True}}
    monkeypatch.setattr(api, "validate_production_v2_shot", lambda *_args, **_kwargs: final_validation)
    substituted = validation_request.model_copy(update={"prompt": "A different prompt."})
    with pytest.raises(HTTPException) as changed_prompt:
        api.queue_production_v2_take(project_id, run["run_id"], "cut-01",
            api.ProductionV2TakeQueueRequest(idempotency_key="prompt-substitution",
                validation_request=substituted, prompt_preparation_task_id=queued["task_id"]))
    assert changed_prompt.value.status_code == 409
    assert changed_prompt.value.detail["code"] == "shot_prompt_preparation_mismatch"

    newer_revision = {**revision, "revision_id": "shot_plans-cccccccccccc",
        "created_at": "2026-10-06T00:00:00+00:00"}
    api.production_story_revisions.write_stage_revision(tmp_path / "output", project_id,
        run["run_id"], "shot_plans", newer_revision)
    with pytest.raises(HTTPException) as stale_plan:
        api.queue_production_v2_take(project_id, run["run_id"], "cut-01",
            api.ProductionV2TakeQueueRequest(idempotency_key="stale-plan-take",
                validation_request=validation_request.model_copy(update={"prompt": generated_prompt}),
                prompt_preparation_task_id=queued["task_id"]))
    assert stale_plan.value.status_code == 409
    assert stale_plan.value.detail["code"] == "shot_prompt_preparation_mismatch"
    api.production_story_revisions.write_stage_revision(tmp_path / "output", project_id,
        run["run_id"], "shot_plans", {**newer_revision, "review_status": "pending_review"})

    original_read_project = api.PROJECT_STORE.read_project
    monkeypatch.setattr(api.PROJECT_STORE, "read_project", lambda project: {
        **original_read_project(project), "story_input": "A changed source story."})
    with pytest.raises(HTTPException) as changed_story:
        api.queue_production_v2_take(project_id, run["run_id"], "cut-01",
            api.ProductionV2TakeQueueRequest(idempotency_key="changed-source-take",
                validation_request=validation_request.model_copy(update={"prompt": generated_prompt}),
                prompt_preparation_task_id=queued["task_id"]))
    assert changed_story.value.status_code == 409
    assert changed_story.value.detail["code"] == "source_story_changed"
    monkeypatch.setattr(api.PROJECT_STORE, "read_project", original_read_project)

    dispatched = api.queue_production_v2_take(project_id, run["run_id"], "cut-01",
        api.ProductionV2TakeQueueRequest(idempotency_key="prepared-prompt-take",
            validation_request=validation_request.model_copy(update={"prompt": generated_prompt}),
            prompt_preparation_task_id=queued["task_id"]))
    assert dispatched["take"]["status"] == "queued"
    assert dispatched["take"]["input_snapshot"]["prompt_preparation_task_id"] == queued["task_id"]
    replayed_take = api.queue_production_v2_take(project_id, run["run_id"], "cut-01",
        api.ProductionV2TakeQueueRequest(idempotency_key="prepared-prompt-take",
            validation_request=validation_request.model_copy(update={"prompt": generated_prompt}),
            prompt_preparation_task_id=queued["task_id"]))
    assert replayed_take["take"]["job_id"] == dispatched["take"]["job_id"]
    assert replayed_take["take"]["take_id"] == dispatched["take"]["take_id"]
    assert len(api._production_v2_ledger().get_run(project_id=project_id, run_id=run["run_id"])["takes"]) == 1


def test_director_prompt_task_resolves_only_frozen_catalog_ids(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="catalog-resolve-run", control_mode="fully_automated")))
    revision = {"schema_version": 1, "revision_id": "shot_plans-cafe00000001", "stage": "shot_plans",
        "review_status": "accepted", "created_at": "2026-10-05T00:00:00+00:00",
        "items": [{"unit_id": "cut-01", "scene_id": "scene-01", "content": {
            "prompt": "Mira enters the station.", "duration_seconds": 5.0,
            "dialogue": [], "asset_intents": [{"role": "character_master", "intent": "Preserve Mira's approved identity."}]}}]}
    api.production_story_revisions.write_stage_revision(tmp_path / "output", project_id,
        run["run_id"], "shot_plans", revision)
    catalog = [{"shot_id": "cut-01", "scene_id": "scene-01", "character_ids": ["mira"],
        "world_id": None, "images": [{"asset_id": "master-mira", "role": "character_master", "entity_id": "mira"}],
        "videos": [], "voice_references": [], "scope": "approved project assets and this run's bound voice excerpts"}]
    monkeypatch.setattr(api, "_approved_catalog_for_shot", lambda *_args, **_kwargs: catalog)
    resolution_by_selection = {
        False: {"reference_resolution_hash": "e" * 64, "asset_fingerprints": {},
            "reference_map": {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}}},
        True: {"reference_resolution_hash": "f" * 64, "asset_fingerprints": {"master-mira": "a" * 64},
            "reference_map": {"pictures": [{"tag": "<Picture 1>", "asset_id": "master-mira",
                "role": "character_master", "intent": "Preserve Mira's approved identity."}],
                "videos": [], "audios": [], "speaker_audio_tags": {}}},
    }
    def validate(_project, _run, _shot, body):
        return {"reference_map_ready": True, **resolution_by_selection[bool(body.images)]}
    monkeypatch.setattr(api, "validate_production_v2_shot", validate)
    provider_calls = []
    def generate_json(**kwargs):
        provider_calls.append(kwargs)
        return {"images": [{"asset_id": "master-mira", "role": "character_master",
            "intent": "Preserve Mira's approved identity."}], "videos": [], "standalone_audios": []}
    monkeypatch.setattr(api.reasoning_provider, "generate_json", generate_json)
    generated_prompt = "Mira enters the station, preserving her identity with <Picture 1>."
    generated = {"prompt": generated_prompt, "accepted": True,
        "lint": {"ok": True, "errors": [], "warnings": []}, "review": {"decision": "approve"},
        "review_history": [], "repair_attempted": False, "provider": run["config"]["provider"],
        "input_hash": "i" * 64, "prompt_hash": hashlib.sha256(generated_prompt.encode()).hexdigest(),
        "corpus_version": run["config"]["h3_rules_version"], "corpus_hash": run["config"]["h3_rules_hash"],
        "reference_map": resolution_by_selection[True]["reference_map"]}
    monkeypatch.setattr(api, "generate_resolved_shot_prompt", lambda **_kwargs: generated)
    validation_request = api.ProductionV2ShotValidateRequest(
        shot_plan_revision_id=revision["revision_id"], prompt="Mira enters the station.")
    payload = api.ProductionV2ShotPromptPrepareRequest(idempotency_key="catalog-prompt-task",
        shot_plan_revision_id=revision["revision_id"], validation_request=validation_request,
        resolve_catalog=True)
    background = api.BackgroundTasks()
    queued = api.enqueue_production_v2_shot_prompt_preparation(project_id, run["run_id"], "cut-01",
        payload, background)
    stored = api._production_stage_task_store().get(project_id=project_id, run_id=run["run_id"],
        task_id=queued["task_id"])
    assert stored["request"]["approved_reference_catalog"] == catalog
    api._execute_production_story_stage_task(queued["task_id"])
    completed = api.get_production_v2_shot_prompt_preparation(project_id, run["run_id"], "cut-01",
        queued["task_id"])
    assert completed["status"] == "completed"
    assert completed["result"]["resolved_validation_request"]["images"] == [{
        "asset_id": "master-mira", "role": "character_master", "intent": "Preserve Mira's approved identity."}]
    assert completed["result"]["reference_map"] == resolution_by_selection[True]["reference_map"]
    assert provider_calls[0]["provider"] == run["config"]["provider"]
    assert provider_calls[0]["cpu_only"] is True
    final_validation = {"valid": True, "reference_map": resolution_by_selection[True]["reference_map"],
        "asset_fingerprints": resolution_by_selection[True]["asset_fingerprints"],
        "validation_hash": "v" * 64, "workflow_readiness": {"available": True}}
    monkeypatch.setattr(api, "validate_production_v2_shot", lambda *_args, **_kwargs: final_validation)
    resolved_request = api.ProductionV2ShotValidateRequest(**{
        **completed["result"]["resolved_validation_request"], "prompt": generated_prompt})
    with pytest.raises(HTTPException) as render_gate:
        api.queue_production_v2_take(project_id, run["run_id"], "cut-01",
            api.ProductionV2TakeQueueRequest(idempotency_key="valid-prepared-director-take",
                validation_request=resolved_request, prompt_preparation_task_id=queued["task_id"]))
    assert render_gate.value.status_code == 409
    assert render_gate.value.detail["code"] == "automatic_render_controller_unavailable"


def test_manual_run_cannot_request_director_catalog_resolution(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="manual-catalog-run", control_mode="manual")))
    request = api.ProductionV2ShotValidateRequest(
        shot_plan_revision_id="shot_plans-abcdef012345", prompt="A traveler crosses the bridge.")
    payload = api.ProductionV2ShotPromptPrepareRequest(idempotency_key="manual-catalog-prep",
        shot_plan_revision_id=request.shot_plan_revision_id, validation_request=request,
        resolve_catalog=True)
    with pytest.raises(HTTPException) as denied:
        api.enqueue_production_v2_shot_prompt_preparation(project_id, run["run_id"], "shot-01",
            payload, api.BackgroundTasks())
    assert denied.value.status_code == 409
    assert denied.value.detail["code"] == "catalog_resolution_authority_denied"


def test_director_take_requires_prepared_prompt_task_before_render_gate(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="director-take-prepared-run", control_mode="fully_automated")))
    request = api.ProductionV2ShotValidateRequest(
        shot_plan_revision_id="shot_plans-abcdef012345", prompt="A traveler crosses the bridge.")
    with pytest.raises(HTTPException) as missing:
        api.queue_production_v2_take(project_id, run["run_id"], "shot-01",
            api.ProductionV2TakeQueueRequest(idempotency_key="director-no-prep", validation_request=request))
    assert missing.value.status_code == 409
    assert missing.value.detail["code"] == "shot_prompt_preparation_required"
    with pytest.raises(HTTPException) as unknown:
        api.queue_production_v2_take(project_id, run["run_id"], "shot-01",
            api.ProductionV2TakeQueueRequest(idempotency_key="director-unknown-prep",
                validation_request=request, prompt_preparation_task_id="unknown-prompt-task"))
    assert unknown.value.status_code == 409
    assert unknown.value.detail["code"] == "shot_prompt_preparation_unavailable"


def test_shot_validation_enforces_direct_reference_built_and_hybrid_asset_policies(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "validate_and_compile_shot", lambda *_args, **_kwargs: {
        "valid": True, "validation_hash": "b" * 64, "workflow_id": "minimax_h3_r2v_dynamic_v1",
        "reference_map": {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}},
        "asset_fingerprints": {}, "width": 1344, "height": 768, "frame_count": 125,
        "duration_seconds": 5.0, "graph_compiler_version": "1.0.0"})
    capability = api.dynamic_h3_capability()
    capability.update({"available": False, "disabled_reason": "No H3 smoke"})
    monkeypatch.setattr(api, "dynamic_h3_capability", lambda: capability)
    monkeypatch.setattr(api, "get_production_asset_record", lambda *_args: {
        "asset_id": "pa-0123456789abcdef", "project_id": project_id, "kind": "image",
        "roles": ["character_master"], "source": "project_upload", "metadata": {"approval_status": "accepted"}})

    def add_accepted_shot(route, shot_content):
        run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
            idempotency_key=f"route-assets-{route}", making_route=route)))
        revision_id = {"direct_h3": "shot_plans-000000000001",
                       "reference_built": "shot_plans-000000000002",
                       "hybrid": "shot_plans-000000000003"}[route]
        revision = {"schema_version": 1, "revision_id": revision_id,
            "stage": "shot_plans", "review_status": "accepted",
            "items": [{"unit_id": "cut-01", "content": shot_content}]}
        api.production_story_revisions.write_stage_revision(tmp_path / "output", project_id,
            run["run_id"], "shot_plans", revision)
        return run, revision

    content = {"prompt": "A character waits in a world.", "characters": ["character-1"],
        "world_state_id": "world-1", "asset_intents": []}
    direct, direct_revision = add_accepted_shot("direct_h3", content)
    direct_result = api.validate_production_v2_shot(project_id, direct["run_id"], "cut-01",
        api.ProductionV2ShotValidateRequest(shot_plan_revision_id=direct_revision["revision_id"],
            prompt="A character waits in a world."))
    assert direct_result["valid"] is True

    reference, reference_revision = add_accepted_shot("reference_built", content)
    with pytest.raises(HTTPException) as reference_blocked:
        api.validate_production_v2_shot(project_id, reference["run_id"], "cut-01",
            api.ProductionV2ShotValidateRequest(shot_plan_revision_id=reference_revision["revision_id"],
                prompt="A character waits in a world."))
    assert reference_blocked.value.status_code == 422
    assert reference_blocked.value.detail["code"] == "required_master_assets_missing"
    assert reference_blocked.value.detail["details"]["missing_roles"] == {"character_master": 1, "world_master": 1}

    hybrid_content = {**content, "asset_requirements": [{"role": "world_master", "required": False}]}
    hybrid, hybrid_revision = add_accepted_shot("hybrid", hybrid_content)
    hybrid_result = api.validate_production_v2_shot(project_id, hybrid["run_id"], "cut-01",
        api.ProductionV2ShotValidateRequest(shot_plan_revision_id=hybrid_revision["revision_id"],
            prompt="A character waits in a world.",
            images=[api.ProductionV2ImageReference(asset_id="pa-0123456789abcdef", role="character_master")]))
    assert hybrid_result["valid"] is True


def test_shot_take_queue_revalidates_capability_and_is_idempotent(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="queue-run", control_mode="manual")))
    ready = {"available": True, "workflow_id": "minimax_h3_r2v_dynamic_v1", "workflow_version": 1}
    request = api.ProductionV2ShotValidateRequest(shot_plan_revision_id="shot_plans-aaaaaaaaaaaa",
        prompt="A character enters. <Picture 1> is their identity reference.",
        images=[api.ProductionV2ImageReference(asset_id="pa-0123456789abcdef", role="character_master")])
    monkeypatch.setattr(api, "validate_production_v2_shot", lambda *_a, **_k: {
        "valid": True, "validation_hash": "a" * 64, "workflow_id": "minimax_h3_r2v_dynamic_v1",
        "workflow_version": 1, "reference_map": {"pictures": [], "videos": [], "audios": []},
        "workflow_readiness": ready})
    map_only_payload = api.ProductionV2TakeQueueRequest(idempotency_key="map-only-must-not-queue",
        validation_request=request.model_copy(update={"reference_map_only": True}))
    with pytest.raises(HTTPException) as map_only_blocked:
        api.queue_production_v2_take(project_id, run["run_id"], "cut-01", map_only_payload)
    assert map_only_blocked.value.status_code == 422
    assert map_only_blocked.value.detail["code"] == "reference_map_only_not_queueable"
    payload = api.ProductionV2TakeQueueRequest(idempotency_key="queue-click-1", validation_request=request)
    first = api.queue_production_v2_take(project_id, run["run_id"], "cut-01", payload)
    replay = api.queue_production_v2_take(project_id, run["run_id"], "cut-01", payload)
    assert first["take"]["take_id"] == replay["take"]["take_id"]
    assert first["take"]["status"] == "queued"
    stored = asyncio.run(api.get_production_v2_run(project_id, run["run_id"]))
    assert len(stored["takes"]) == 1
    assert len([event for event in stored["events"] if event["event_type"] == "shot_take_queued"]) == 1
    assert stored["takes"][0]["input_snapshot"]["validation_hash"] == "a" * 64


@pytest.mark.parametrize("reason_key", ["reason", "disabled_reason"])
def test_shot_take_queue_fails_closed_when_exact_workflow_is_unavailable(tmp_path: Path, monkeypatch, reason_key):
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="queue-run-disabled", control_mode="manual")))
    request = api.ProductionV2ShotValidateRequest(shot_plan_revision_id="shot_plans-aaaaaaaaaaaa", prompt="Prompt")
    monkeypatch.setattr(api, "validate_production_v2_shot", lambda *_a, **_k: {
        "valid": True, "validation_hash": "a" * 64,
        "workflow_readiness": {"available": False, reason_key: "no live smoke"}})
    with pytest.raises(HTTPException) as unavailable:
        api.queue_production_v2_take(project_id, run["run_id"], "cut-01",
            api.ProductionV2TakeQueueRequest(idempotency_key="disabled", validation_request=request))
    assert unavailable.value.status_code == 503
    assert unavailable.value.detail["details"] == "no live smoke"
    assert asyncio.run(api.get_production_v2_run(project_id, run["run_id"]))["takes"] == []


def test_shot_take_api_rejects_predecessor_from_another_run_before_validation(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    first = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="cross-run-parent-a", control_mode="manual")))
    second = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="cross-run-parent-b", control_mode="manual")))
    parent = api._production_v2_ledger().queue_take(project_id=project_id, run_id=first["run_id"],
        shot_id="cut-01", take_id="foreign-parent", idempotency_key="foreign-parent", input_snapshot={})
    payload = api.ProductionV2TakeQueueRequest(idempotency_key="cross-run-child",
        parent_take_id=parent["take_id"], validation_request=api.ProductionV2ShotValidateRequest(
            shot_plan_revision_id="shot_plans-aaaaaaaaaaaa", prompt="A shot."))

    with pytest.raises(HTTPException) as rejected:
        api.queue_production_v2_take(project_id, second["run_id"], "cut-02", payload)
    assert rejected.value.status_code == 404
    assert rejected.value.detail["code"] == "take_dependency_not_found"
    assert asyncio.run(api.get_production_v2_run(project_id, second["run_id"]))["takes"] == []


def test_manual_queue_checks_same_scene_topology_but_can_wait_for_unaccepted_parent(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="manual-parent-topology", control_mode="manual")))
    revision_id = "shot_plans-aaaaaaaaaaaa"
    plan = {"revision_id": revision_id, "review_status": "accepted", "items": [
        {"unit_id": "cut-1", "content": {"scene_id": "apartment"}},
        {"unit_id": "cut-2", "content": {"scene_id": "apartment"}},
        {"unit_id": "cut-3", "content": {"scene_id": "station"}}]}
    api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id, run["run_id"], "shot_plans", plan)
    parent = api._production_v2_ledger().queue_take(project_id=project_id, run_id=run["run_id"],
        shot_id="cut-1", take_id="parent", idempotency_key="parent", input_snapshot={})
    monkeypatch.setattr(api, "validate_production_v2_shot", lambda *_args: {
        "validation_hash": "a" * 64, "workflow_id": "minimax_h3_t2v_local_v1", "workflow_version": 1,
        "reference_map": {}, "workflow_readiness": {"available": True}})
    payload = api.ProductionV2TakeQueueRequest(idempotency_key="child",
        parent_take_id=parent["take_id"], validation_request=api.ProductionV2ShotValidateRequest(
            shot_plan_revision_id=revision_id, prompt="Next cut"))
    with pytest.raises(HTTPException) as boundary:
        api.queue_production_v2_take(project_id, run["run_id"], "cut-3", payload)
    assert boundary.value.detail["code"] == "shot_predecessor_mismatch"
    with pytest.raises(HTTPException):
        api.queue_production_v2_take(project_id, run["run_id"], "cut-1", payload)
    child = api.queue_production_v2_take(project_id, run["run_id"], "cut-2", payload)["take"]
    assert child["status"] == "waiting_for_predecessor"


def test_take_retake_acceptance_previews_and_confirms_queued_child_invalidation(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="retake-run", control_mode="manual")))
    ledger = api._production_v2_ledger()

    def create_take(shot_id: str, take_id: str, key: str, parent_take_id: str | None = None):
        return ledger.queue_take(project_id=project_id, run_id=run["run_id"], shot_id=shot_id,
            take_id=take_id, idempotency_key=key, input_snapshot={"take": take_id},
            parent_take_id=parent_take_id)

    def finish_for_review(take_id: str):
        ledger.transition_take(project_id=project_id, take_id=take_id, status="submitting")
        prompt_id = ledger.reserve_prompt_id(project_id=project_id, take_id=take_id)["prompt_id"]
        ledger.bind_prompt_id(project_id=project_id, take_id=take_id, prompt_id=prompt_id)
        ledger.transition_take(project_id=project_id, take_id=take_id, status="collecting")
        ledger.transition_take(project_id=project_id, take_id=take_id, status="needs_review")

    create_take("shot-1", "parent-old", "parent-old")
    finish_for_review("parent-old")
    ledger.accept_take(project_id=project_id, run_id=run["run_id"], take_id="parent-old")
    child = create_take("shot-2", "child-queued", "child-queued", "parent-old")
    create_take("shot-1", "parent-new", "parent-new")
    finish_for_review("parent-new")

    preview = api.accept_production_v2_take(project_id, run["run_id"], "parent-new")
    assert preview["accepted"] is False
    assert preview["requires_confirmation"] is True
    assert [row["take_id"] for row in preview["queued_children_to_stale"]] == [child["take_id"]]
    unchanged = asyncio.run(api.get_production_v2_run(project_id, run["run_id"]))
    assert {row["take_id"]: row["status"] for row in unchanged["takes"]}["child-queued"] == "queued"

    accepted = api.accept_production_v2_take(project_id, run["run_id"], "parent-new",
        api.ProductionV2TakeAcceptRequest(confirm_stale_child_take_ids=[child["take_id"]]))
    assert accepted["accepted"] is True
    final = asyncio.run(api.get_production_v2_run(project_id, run["run_id"]))
    statuses = {row["take_id"]: row["status"] for row in final["takes"]}
    assert statuses["parent-new"] == "accepted"
    assert statuses["child-queued"] == "stale"
    assert statuses["parent-old"] == "accepted"


def test_project_asset_route_handlers_upload_list_content_and_link(tmp_path: Path, monkeypatch):
    import tempfile
    from starlette.datastructures import Headers, UploadFile
    from PIL import Image
    project_id = _temporary_project(tmp_path, monkeypatch)
    image = tempfile.SpooledTemporaryFile()
    Image.new("RGB", (8, 6), (20, 40, 60)).save(image, format="PNG")
    image.seek(0)
    png = image.read()
    image.seek(0)
    monkeypatch.setattr(api.video_repertoire, "get_asset", lambda _asset_id: {
        "asset_id": "video-linked", "title": "Library clip", "filename": "original.mp4", "sha256": "hash", "size": 42})

    async def exercise_handlers():
        upload = UploadFile(filename="maya.png", file=image, headers=Headers({"content-type": "image/png"}))
        asset = await api.upload_project_production_asset(project_id, file=upload,
            role="character_master", provenance_notes="approved design")
        assert asset["kind"] == "image" and asset["roles"] == ["character_master"]
        content = await api.project_production_asset_content(project_id, asset["asset_id"])
        assert Path(content.path).read_bytes() == png
        listed = await api.list_project_production_assets(project_id, kind="image", role="character_master")
        assert listed["total"] == 1
        duplicate_file = tempfile.SpooledTemporaryFile()
        duplicate_file.write(png)
        duplicate_file.seek(0)
        duplicate = UploadFile(filename="again.png", file=duplicate_file, headers=Headers({"content-type": "image/png"}))
        repeated = await api.upload_project_production_asset(project_id, file=duplicate, role="character_angle")
        assert repeated["deduplicated"] is True
        invalid = tempfile.SpooledTemporaryFile()
        invalid.write(b"no")
        invalid.seek(0)
        bad = UploadFile(filename="not.png", file=invalid, headers=Headers({"content-type": "image/png"}))
        with pytest.raises(api.HTTPException) as invalid_upload:
            await api.upload_project_production_asset(project_id, file=bad, role="character_master")
        assert invalid_upload.value.status_code == 422
        linked = await api.link_project_repertoire_asset(project_id,
            api.ProductionAssetLinkRequest(repertoire_kind="video", external_asset_id="video-linked"))
        assert linked["source"] == "external_video_repertoire_video"
        assert linked["content_url"] == "/api/video-repertoire/assets/video-linked/content"
        with pytest.raises(api.HTTPException) as missing:
            await api.project_production_asset_content(project_id, "pa-0000000000000000")
        assert missing.value.status_code == 404
    asyncio.run(exercise_handlers())


def test_project_deletion_does_not_remove_shared_video_repertoire_media(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "projects"
    output_root = tmp_path / "outputs"
    shared_root = tmp_path / "shared-video-repertoire"
    project_id = "asset-owner-project"
    store = api.ProjectStore(project_root)
    project_dir = project_root / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "production").mkdir()
    (project_dir / "production" / "assets.json").write_text(json.dumps({"assets": [
        {"asset_id": "video-123", "source": "external_video_repertoire_video",
         "external_asset_id": "video-123", "content_url": "/api/video-repertoire/assets/video-123/content"}
    ]}))
    legacy_output = output_root / project_id / "temporary-output.bin"
    legacy_output.parent.mkdir(parents=True)
    legacy_output.write_bytes(b"project-owned")
    shared_media = shared_root / "video-123" / "source.mp4"
    shared_media.parent.mkdir(parents=True)
    shared_media.write_bytes(b"shared-source-video")

    monkeypatch.setattr(api, "PROJECT_STORE", store)
    monkeypatch.setattr(api, "OUTPUT_ROOT", output_root)
    result = asyncio.run(api.delete_automation_projects(
        api.AutomationDeleteRequest(project_ids=[project_id], confirm=True)))

    assert result == {"deleted": [project_id]}
    assert not project_dir.exists()
    assert not (output_root / project_id).exists()
    assert shared_media.read_bytes() == b"shared-source-video"


def test_recorded_dialogue_upload_requires_run_voice_binding_and_saves_exact_provenance(tmp_path: Path, monkeypatch):
    import tempfile
    from starlette.datastructures import Headers, UploadFile

    project_id = "dialogue-project"
    run_id = "11111111-1111-4111-8111-111111111111"
    character_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    monkeypatch.setattr(api, "_production_v2_run_or_404", lambda _project, _run: {"run_id": run_id})
    monkeypatch.setattr(api, "read_project_canon", lambda *_args: {"characters": [
        {"character_id": character_id, "status": "active"}]})
    monkeypatch.setattr(api, "list_production_voice_bindings", lambda *_args, **_kwargs: {"bindings": [
        {"character_id": character_id, "speaker_id": "S2", "voice_asset_id": "pa-0123456789abcdef"}]})
    captured = {}

    def register(*_args, **kwargs):
        captured.update(kwargs)
        return {"asset_id": "pa-fedcba9876543210", "roles": ["dialogue_take"], "metadata": kwargs["metadata"]}

    monkeypatch.setattr(api, "register_production_asset_upload", register)
    audio_bytes = b"RIFF0000WAVErecorded words"

    async def upload(bindings=True):
        if not bindings:
            monkeypatch.setattr(api, "list_production_voice_bindings", lambda *_args, **_kwargs: {"bindings": []})
        stream = tempfile.SpooledTemporaryFile()
        stream.write(audio_bytes)
        stream.seek(0)
        file = UploadFile(filename="line.wav", file=stream, headers=Headers({"content-type": "audio/wav"}))
        return await api.upload_production_dialogue_take(project_id, run_id, file=file,
            character_id=character_id, transcript="We made it across.")

    result = asyncio.run(upload())
    assert result["roles"] == ["dialogue_take"]
    assert captured["role"] == "dialogue_take"
    assert captured["content"] == audio_bytes
    assert captured["metadata"]["dialogue_take"] == {
        "version": 1, "run_id": run_id, "character_id": character_id,
        "speaker_id": "S2", "transcript": "We made it across.",
        "recording_status": "original_recording"}

    with pytest.raises(HTTPException) as unbound:
        asyncio.run(upload(bindings=False))
    assert unbound.value.status_code == 409
    assert unbound.value.detail["code"] == "dialogue_voice_binding_required"


def test_dialogue_conversion_requires_original_take_and_schedules_local_operation(monkeypatch, tmp_path: Path):
    from fastapi import BackgroundTasks

    project_id = "dialogue-project"
    run_id = "11111111-1111-4111-8111-111111111111"
    character_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    asset_id = "pa-fedcba9876543210"
    monkeypatch.setattr(api, "_production_v2_run_or_404", lambda *_args: {"run_id": run_id})
    monkeypatch.setattr(api, "get_production_asset_record", lambda *_args: {
        "roles": ["dialogue_take"], "metadata": {"dialogue_take": {
            "recording_status": "original_recording", "run_id": run_id,
            "character_id": character_id, "speaker_id": "S2", "transcript": "Exact line."}}})
    monkeypatch.setattr(api, "list_production_voice_bindings", lambda *_args, **_kwargs: {"bindings": [
        {"character_id": character_id, "speaker_id": "S2"}]})
    source = Path("/tmp/original-dialogue.wav")
    monkeypatch.setattr(api, "resolve_production_asset_content", lambda *_args: (source, "audio/wav", source.name))
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "state")
    tasks = BackgroundTasks()
    result = asyncio.run(api.convert_production_dialogue_take(project_id, run_id, asset_id,
        tasks, operation="rvc", settings='{"model":"local-test.pth"}', idempotency_key="same-click"))
    assert result["source_asset_id"] == asset_id
    assert result["speaker_id"] == "S2"
    assert result["sidecar_kind"] == "dialogue_conversion"
    assert result["prompt_id"]
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].func is api._execute_production_audio_sidecar
    assert result["settings"] == {"model": "local-test.pth"}
    repeated = asyncio.run(api.convert_production_dialogue_take(project_id, run_id, asset_id,
        BackgroundTasks(), operation="rvc", settings='{"model":"local-test.pth"}', idempotency_key="same-click"))
    assert repeated["job_id"] == result["job_id"]
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(api.convert_production_dialogue_take(project_id, run_id, asset_id,
            BackgroundTasks(), operation="rvc", settings='{"model":"different.pth"}', idempotency_key="same-click"))
    assert conflict.value.status_code == 409

    with pytest.raises(HTTPException) as invalid:
        asyncio.run(api.convert_production_dialogue_take(project_id, run_id, asset_id,
            BackgroundTasks(), operation="emotion", settings="{}"))
    assert invalid.value.status_code == 422


def test_dialogue_conversion_registers_separate_lineage_asset_and_keeps_source(monkeypatch, tmp_path: Path):
    project_id = "dialogue-project"
    original = tmp_path / "original.wav"
    original.write_bytes(b"original is immutable")
    job = {"job_id": "effect-rvc-123", "operation": "rvc", "source_asset_id": "pa-fedcba9876543210"}
    output_calls = []
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "PROJECT_STORE", api.ProjectStore(tmp_path / "projects"))
    monkeypatch.setattr(api, "_save_effect_job", lambda *_args: None)
    def fake_register(*_args, **kwargs):
        output_calls.append(kwargs)
        return {"asset_id": "pa-1234567890abcdef"}
    monkeypatch.setattr(api, "register_production_asset_output", fake_register)
    def fake_effect(**kwargs):
        kwargs["update"]({"status": "completed", "export_path": "ignored"})
    monkeypatch.setattr(api, "run_effect_job", fake_effect)
    lineage = {"version": 1, "run_id": "run-id", "character_id": "char-id",
        "speaker_id": "S2", "transcript": "Exact line."}
    api._execute_production_dialogue_conversion(project_id, job, original, lineage)
    assert original.read_bytes() == b"original is immutable"
    assert output_calls[0]["relative_path"] == "audio/effect-rvc-123.flac"
    assert output_calls[0]["metadata"]["dialogue_take"] == {
        **lineage, "recording_status": "converted", "source_asset_id": job["source_asset_id"],
        "effect_job_id": job["job_id"], "conversion_operation": "rvc"}

def test_same_run_idempotency_key_cannot_change_mode(tmp_path: Path, monkeypatch) -> None:
    project_id = _temporary_project(tmp_path, monkeypatch)
    first = api.ProductionV2RunRequest(idempotency_key="fixed", control_mode="manual")
    asyncio.run(api.create_production_v2_run(project_id, first))

    changed = api.ProductionV2RunRequest(idempotency_key="fixed", control_mode="fully_automated")
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(api.create_production_v2_run(project_id, changed))
    assert conflict.value.status_code == 409


def test_http_run_routes_are_additive_and_retrievable(tmp_path: Path, monkeypatch) -> None:
    project_id = _temporary_project(tmp_path, monkeypatch)

    async def exercise_routes() -> None:
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/projects/{project_id}/production/v2/runs", json={
                "idempotency_key": "http-start-1", "control_mode": "manual", "making_route": "direct_h3",
            })
            assert response.status_code == 201
            created = response.json()
            assert created["status"] == "draft"
            listed = await client.get(f"/api/projects/{project_id}/production/v2/runs")
            assert listed.status_code == 200
            assert [row["run_id"] for row in listed.json()["runs"]] == [created["run_id"]]
            assert "takes" not in listed.json()["runs"][0]
            assert "events" not in listed.json()["runs"][0]
            fetched = await client.get(f"/api/projects/{project_id}/production/v2/runs/{created['run_id']}")
            assert fetched.status_code == 200
            assert fetched.json()["run_id"] == created["run_id"]
            missing = await client.get(f"/api/projects/{project_id}/production/v2/runs/not-found")
            assert missing.status_code == 404

    asyncio.run(exercise_routes())


def _fake_story_canon(*, title, source_text, provider, **_kwargs):
    return {
        "revision_id": "story-canon-0123456789ab", "title": title,
        "user_story_input": source_text,
        "source_hash": hashlib.sha256(source_text.encode()).hexdigest(),
        "provider": provider, "chunks": [{"chunk_id": "story_chunk_0001", "source_excerpt": source_text}],
        "expanded_story": f"Expanded: {source_text}", "source_facts": [], "inferred_details": [],
        "completeness": {"all_source_chunks_echoed": True, "all_fact_evidence_verified": True},
    }


def test_manual_story_detail_is_pending_revision_and_can_be_accepted(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch, story="A director finds a hidden room.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api.reasoning_provider, "model_for", lambda _provider: "gpt-6-sol")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    run = asyncio.run(api.create_production_v2_run(
        project_id, api.ProductionV2RunRequest(idempotency_key="manual-story", control_mode="manual")))

    response = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    revision = response["revision"]
    assert response["review_required"] is True and response["accepted"] is False
    assert revision["review_status"] == "pending_review"
    assert revision["provider"] == "codex" and revision["model"] == "gpt-6-sol"
    revision_path = tmp_path / "output" / response["output_path"]
    assert revision_path.is_file()
    assert asyncio.run(api.list_production_v2_story_revisions(project_id, run["run_id"]))["revisions"][0]["revision_id"] == revision["revision_id"]

    accepted = asyncio.run(api.accept_production_v2_story_revision(
        project_id, run["run_id"], revision["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=revision["source_hash"])))
    assert accepted["accepted"] is True
    persisted = json.loads(revision_path.read_text())
    assert persisted["review_status"] == "accepted"
    assert persisted["provider"] == "codex" and persisted["model"] == "gpt-6-sol"
    events = asyncio.run(api.get_production_v2_run(project_id, run["run_id"]))["events"]
    assert [event["event_type"] for event in events][-2:] == ["story_revision_created", "story_revision_accepted"]
    # V2 story work stays additive; the old project artifact content is not overwritten.
    assert api.PROJECT_STORE.read_project(project_id)["artifacts"]["story"]["content"] is None


def test_manual_story_edit_creates_child_revision_and_preserves_parent(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch, story="A director finds a hidden room.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="manual-story-edit", control_mode="manual")))
    original = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())["revision"]

    edited = api.save_manual_production_v2_story_revision(project_id, run["run_id"], original["revision_id"],
        api.ProductionV2ManualStoryEditRequest(expanded_story="The director finds a hidden room at dawn.",
            expected_source_hash=original["source_hash"]))

    child = edited["revision"]
    assert edited["review_required"] and not edited["accepted"]
    assert child["revision_id"] != original["revision_id"]
    assert child["parent_revision_id"] == original["revision_id"]
    assert child["review_status"] == "pending_review" and child["author"] == "user"
    assert child["expanded_story"] == "The director finds a hidden room at dawn."
    assert child["chunks"] == original["chunks"]
    assert child["source_facts"] == original["source_facts"]
    assert api.production_story_revisions.load_revision(api.OUTPUT_ROOT, project_id, run["run_id"],
        original["revision_id"])["expanded_story"] == original["expanded_story"]
    assert api.PROJECT_STORE.read_project(project_id)["artifacts"]["story"]["content"] is None


def test_manual_story_edit_rejects_stale_source_and_full_mode(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch, story="A director finds a hidden room.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: {
        "review_id": "director-review-test-only", "decision": "approve", "accepted": True,
        "reviews": [], "issues": [], "repair_instructions": [], "repaired_chunks": {},
    })
    manual_run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="manual-story-stale", control_mode="manual")))
    parent = api.detail_production_v2_story(project_id, manual_run["run_id"], api.ProductionV2StoryDetailRequest())["revision"]
    with pytest.raises(api.HTTPException) as stale:
        api.save_manual_production_v2_story_revision(project_id, manual_run["run_id"], parent["revision_id"],
            api.ProductionV2ManualStoryEditRequest(expanded_story="Changed", expected_source_hash="wrong"))
    assert stale.value.status_code == 409

    full_run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="full-story-edit", control_mode="fully_automated")))
    full_parent = api.detail_production_v2_story(project_id, full_run["run_id"], api.ProductionV2StoryDetailRequest())["revision"]
    with pytest.raises(api.HTTPException) as full:
        api.save_manual_production_v2_story_revision(project_id, full_run["run_id"], full_parent["revision_id"],
            api.ProductionV2ManualStoryEditRequest(expanded_story="Human override", expected_source_hash=full_parent["source_hash"]))
    assert full.value.status_code == 409


def test_story_edit_and_accept_reject_project_source_changed_after_run(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch, story="A director enters a silent theater.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="source-change-after-run", control_mode="manual")))
    revision = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())["revision"]
    api.PROJECT_STORE.update_project(project_id, lambda state: state.update({"story_input": "A completely different source."}))

    with pytest.raises(HTTPException) as edit_error:
        api.save_manual_production_v2_story_revision(project_id, run["run_id"], revision["revision_id"],
            api.ProductionV2ManualStoryEditRequest(expanded_story="Edited canon", expected_source_hash=revision["source_hash"]))
    with pytest.raises(HTTPException) as accept_error:
        asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"], revision["revision_id"],
            api.ProductionV2StoryAcceptRequest(expected_source_hash=revision["source_hash"])))
    assert edit_error.value.status_code == accept_error.value.status_code == 409
    assert api.production_story_revisions.list_revisions(api.OUTPUT_ROOT, project_id, run["run_id"]) == [revision]


def test_text_revision_cannot_be_accepted_after_its_story_ancestor_is_superseded(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch, story="Mira waits for the storm to pass.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="text-ancestor-current", control_mode="manual")))
    first_story = api.detail_production_v2_story(project_id, run["run_id"],
        api.ProductionV2StoryDetailRequest())["revision"]
    asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"],
        first_story["revision_id"], api.ProductionV2StoryAcceptRequest(
            expected_source_hash=first_story["source_hash"])))
    text = api.save_production_v2_manual_text(project_id, run["run_id"], "scenes",
        api.ProductionV2ManualTextRequest(source_revision_id=first_story["revision_id"], units=[
            {"unit_id": "scene-001", "content": {"description": "Mira waits at the ridge."}}]))

    newer_story = api.save_manual_production_v2_story_revision(project_id, run["run_id"],
        first_story["revision_id"], api.ProductionV2ManualStoryEditRequest(
            expanded_story="Mira leaves the ridge before the storm arrives.",
            expected_source_hash=first_story["source_hash"]))["revision"]
    assert newer_story["source_hash"] == first_story["source_hash"]
    asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"],
        newer_story["revision_id"], api.ProductionV2StoryAcceptRequest(
            expected_source_hash=newer_story["source_hash"])))

    with pytest.raises(HTTPException) as stale:
        asyncio.run(api.accept_production_v2_text_revision(project_id, run["run_id"], "scenes",
            text["revision"]["revision_id"], api.ProductionV2StoryAcceptRequest(
                expected_source_hash=text["revision"]["source_story_hash"])))
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "text_revision_story_ancestor_stale"


def test_text_revision_acceptance_rejects_project_source_changed_after_run(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch, story="Mira finds a brass key.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "generate_chunked_units", lambda **kwargs: {
        "stage": kwargs["stage"],
        "items": [{"unit_id": row["unit_id"], "content": {"description": "Mira finds a brass key."}}
                  for row in kwargs["units"]],
        "expected_unit_ids": [row["unit_id"] for row in kwargs["units"]],
        "completed_unit_ids": [row["unit_id"] for row in kwargs["units"]], "complete": True,
    })
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="text-source-change", control_mode="manual")))
    story = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())["revision"]
    asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"], story["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=story["source_hash"])))
    text = api.generate_production_v2_text_stage(project_id, run["run_id"], "scenes",
        api.ProductionV2TextStageRequest(source_revision_id=story["revision_id"],
            units=[{"unit_id": "scene-001", "source": "Mira finds the key."}]))
    api.PROJECT_STORE.update_project(project_id,
        lambda state: state.update({"story_input": "Mira loses a silver coin."}))

    with pytest.raises(api.HTTPException) as stale:
        asyncio.run(api.accept_production_v2_text_revision(project_id, run["run_id"], "scenes",
            text["revision"]["revision_id"],
            api.ProductionV2StoryAcceptRequest(expected_source_hash=text["revision"]["source_story_hash"])))
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "text_revision_stale"


def test_sparse_two_scene_story_facts_flow_through_accepted_canon_to_scene_units(tmp_path: Path, monkeypatch):
    source = "Nila owns a brass key. At dusk, she opens the observatory."
    project_id = _temporary_project(tmp_path, monkeypatch, story=source)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")

    def provider(prompt, **_kwargs):
        marker = "Exact source text as a JSON string (decode it; preserve every character):\n"
        excerpt = json.loads(prompt.split(marker, 1)[1].split("\n\n", 1)[0])
        facts = []
        for quote in ("Nila owns a brass key.", "At dusk, she opens the observatory."):
            start = excerpt.index(quote)
            facts.append({"quote": quote, "start": start, "end": start + len(quote), "category": "event"})
        return {"chunk_id": "story_chunk_0001", "source_excerpt": excerpt,
            "source_facts": facts, "expanded_text": f"{excerpt}\nInferred: A quiet atmosphere surrounds the observatory.",
            "inferred_details": ["Inferred: A quiet atmosphere surrounds the observatory."], "continuity_summary": "The observatory opens.",
            "story_goal": "Open the observatory.", "tone": ["quiet"], "continuity_rules": [], "visual_style_notes": []}

    monkeypatch.setattr(api, "generate_story_canon", lambda **kwargs: generate_story_canon(**kwargs, generator=provider))
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="sparse-two-scene-integration", control_mode="manual")))
    story_result = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    canon = story_result["revision"]
    assert canon["review_status"] == "pending_review"
    assert [fact["text"] for fact in canon["source_facts"]] == [
        "Nila owns a brass key.", "At dusk, she opens the observatory."]
    asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"], canon["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=canon["source_hash"])))

    def generate_scenes(*, stage, units, context, **_kwargs):
        assert stage == "scenes"
        assert "expanded_story" not in context  # use linked source chunks, not the full project graph
        items = []
        for unit in units:
            source_facts = [fact["text"] for linked in unit["source_context"] for fact in linked["source_facts"]]
            items.append({"unit_id": unit["unit_id"], "content": {
                "title": unit["content"]["title"], "description": " ".join(source_facts)}})
        return {"stage": stage, "items": items,
            "expected_unit_ids": [unit["unit_id"] for unit in units],
            "completed_unit_ids": [unit["unit_id"] for unit in units], "complete": True}

    monkeypatch.setattr(api, "generate_chunked_units", generate_scenes)
    scenes = api.generate_production_v2_text_stage(project_id, run["run_id"], "scenes",
        api.ProductionV2TextStageRequest(source_revision_id=canon["revision_id"], units=[
            {"unit_id": "scene-001", "source_chunk_ids": ["story_chunk_0001"], "content": {"title": "The key"}},
            {"unit_id": "scene-002", "source_chunk_ids": ["story_chunk_0001"], "content": {"title": "The observatory"}},
        ]))
    assert scenes["revision"]["completed_unit_ids"] == ["scene-001", "scene-002"]
    assert all("Nila owns a brass key." in item["content"]["description"] for item in scenes["revision"]["items"])
    assert all("At dusk, she opens the observatory." in item["content"]["description"] for item in scenes["revision"]["items"])
    accepted_scenes = asyncio.run(api.accept_production_v2_text_revision(project_id, run["run_id"], "scenes",
        scenes["revision"]["revision_id"], api.ProductionV2StoryAcceptRequest(expected_source_hash=canon["source_hash"])))
    assert accepted_scenes["accepted"] is True


@pytest.mark.parametrize("mode", ["fully_automated", "semi"])
def test_full_auto_story_detail_is_accepted_only_after_director_approval(tmp_path: Path, monkeypatch, mode):
    project_id = _temporary_project(tmp_path, monkeypatch, story="A director finds a hidden room.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: {
        "review_id": "director-review-123456789abc", "decision": "approve", "accepted": True,
        "reviews": [{"chunk_id": "story_chunk_0001", "decision": "approve", "confidence": 0.95,
                     "issues": [], "repair_instruction": "", "repair_attempted": True}], "issues": [],
        "repair_instructions": [], "repaired_chunks": {"story_chunk_0001": {
            "chunk_id": "story_chunk_0001", "source_excerpt": "A director finds a hidden room.",
            "expanded_text": "The Director-repaired story.", "source_facts": [],
            "inferred_details": ["Inference: a quiet bell rings."], "index": 1,
            "continuity_summary": "A discovery is made."}}})
    run = asyncio.run(api.create_production_v2_run(
        project_id, api.ProductionV2RunRequest(idempotency_key="full-story", control_mode=mode, semi_gates={"story_review": False})))
    response = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    assert response["accepted"] is True
    assert response["director_review_pending"] is False
    assert response["revision"]["review_status"] == "accepted"
    assert response["director_review"]["decision"] == "approve"
    assert response["revision"]["expanded_story"] == "The Director-repaired story."
    assert response["revision"]["inferred_details"][0]["is_inference"] is True
    assert "director_story_review" in [event["event_type"] for event in asyncio.run(
        api.get_production_v2_run(project_id, run["run_id"]))["events"]]


@pytest.mark.parametrize("mode", ["fully_automated", "semi"])
def test_full_auto_story_review_repair_decision_holds_without_human_accept_endpoint(tmp_path: Path, monkeypatch, mode):
    project_id = _temporary_project(tmp_path, monkeypatch, story="A director finds a hidden room.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: {
        "review_id": "director-review-repair", "decision": "repair", "accepted": False,
        "reviews": [{"chunk_id": "story_chunk_0001", "decision": "repair", "confidence": 0.9,
                     "issues": ["Missing consequence."], "repair_instruction": "Clarify the consequence."}],
        "issues": ["Missing consequence."], "repair_instructions": ["Clarify the consequence."]})
    run = asyncio.run(api.create_production_v2_run(
        project_id, api.ProductionV2RunRequest(idempotency_key="full-story-repair", control_mode=mode, semi_gates={"story_review": False})))
    response = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    assert response["accepted"] is False
    assert response["revision"]["review_status"] == "pending_director_repair"
    assert response["director_review"]["repair_instructions"] == ["Clarify the consequence."]
    with pytest.raises(HTTPException) as human_gate:
        asyncio.run(api.accept_production_v2_story_revision(
            project_id, run["run_id"], response["revision"]["revision_id"],
            api.ProductionV2StoryAcceptRequest(expected_source_hash=response["revision"]["source_hash"])))
    assert human_gate.value.status_code == 409


def test_story_detail_rejects_stale_source_without_writing_revision(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch, story="Original story.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(
        project_id, api.ProductionV2RunRequest(idempotency_key="stale-story")))
    api.PROJECT_STORE.update_project(project_id, lambda state: state.update({"story_input": "Changed story."}))
    with pytest.raises(HTTPException) as stale:
        asyncio.run(api.detail_production_v2_story(
            project_id, run["run_id"], api.ProductionV2StoryDetailRequest()))
    assert stale.value.status_code == 409
    assert not list((tmp_path / "output").rglob("story-canon-*.json"))


def test_manual_text_revision_requires_accepted_story_and_preserves_stable_ids(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="manual-text")))
    pending = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    with pytest.raises(HTTPException) as unaccepted:
        api.save_production_v2_manual_text(project_id, run["run_id"], "scenes",
            api.ProductionV2ManualTextRequest(source_revision_id=pending["revision"]["revision_id"],
                units=[{"unit_id": "scene-001", "content": {"title": "Bridge"}}]))
    assert unaccepted.value.status_code == 409
    asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"], pending["revision"]["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=pending["revision"]["source_hash"])))
    saved = api.save_production_v2_manual_text(project_id, run["run_id"], "scenes",
        api.ProductionV2ManualTextRequest(source_revision_id=pending["revision"]["revision_id"],
            units=[{"unit_id": "scene-001", "source_chunk_ids": [], "content": {"title": "Bridge"}}]))
    assert saved["revision"]["author"] == "user"
    assert saved["revision"]["review_status"] == "pending_review"
    assert saved["revision"]["items"][0]["unit_id"] == "scene-001"


def test_text_revision_listing_restores_saved_stage_and_rejects_unknown_stage(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="text-reload")))
    revision = {"revision_id": "scenes-0123456789ab", "review_status": "accepted",
                "created_at": "2026-10-02T12:00:00Z", "items": [{"unit_id": "scene-001", "content": {"title": "Saved"}}]}
    api.production_story_revisions.write_stage_revision(tmp_path / "output", project_id, run["run_id"], "scenes", revision)

    result = asyncio.run(api.list_production_v2_text_revisions(project_id, run["run_id"], "scenes"))
    assert result["revisions"] == [revision]
    with pytest.raises(HTTPException) as invalid:
        asyncio.run(api.list_production_v2_text_revisions(project_id, run["run_id"], "not-a-stage"))
    assert invalid.value.status_code == 422


def test_manual_shot_scene_identity_survives_disk_roundtrip_and_continuity_consumers(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="manual-continuity", control_mode="manual")))
    source = api.create_manual_production_v2_story_source(project_id, run["run_id"],
        api.ProductionV2ManualStorySourceRequest(expected_source_hash=run["config"]["source_story_hash"]))["revision"]
    asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"], source["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=source["source_hash"])))
    units = [{"unit_id": "cut-1", "scene_id": "apartment", "content": {"prompt": "First cut"}},
        {"unit_id": "cut-2", "scene_id": "apartment", "content": {"prompt": "Response"}},
        {"unit_id": "cut-3", "content": {"scene_id": "station", "prompt": "Arrival"}}]
    saved = api.save_production_v2_manual_text(project_id, run["run_id"], "shot_plans",
        api.ProductionV2ManualTextRequest(source_revision_id=source["revision_id"], units=units))["revision"]
    persisted = api.production_story_revisions.load_stage_revision(
        api.OUTPUT_ROOT, project_id, run["run_id"], "shot_plans", saved["revision_id"])
    assert persisted["items"][0]["scene_id"] == "apartment"
    take = {"take_id": "accepted-first", "shot_id": "cut-1", "status": "accepted",
        "input_snapshot": {"shot_plan_revision_id": saved["revision_id"]}}
    assert api._next_controller_shot(persisted["items"], [take],
        shot_plan_revision_id=saved["revision_id"]) == (persisted["items"][1], "accepted-first")
    with pytest.raises(HTTPException) as missing_parent:
        api._previous_cut_reference(project_id, run["run_id"], shot_plan_revision=persisted,
            shot_id="cut-2", predecessor_take_id="accepted-first")
    assert missing_parent.value.detail["code"] == "accepted_same_scene_predecessor_required"
    with pytest.raises(HTTPException) as new_scene:
        api._previous_cut_reference(project_id, run["run_id"], shot_plan_revision=persisted,
            shot_id="cut-3", predecessor_take_id="accepted-first")
    assert new_scene.value.detail["code"] == "scene_boundary_predecessor"


def test_text_budget_failure_is_nonretryable_before_provider_call(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch, story="A director enters a theater and finds a note.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="budget-check", control_mode="manual")))
    pending = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"],
        pending["revision"]["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=pending["revision"]["source_hash"])))
    with pytest.raises(HTTPException) as blocked:
        api.generate_production_v2_text_stage(project_id, run["run_id"], "scenes",
            api.ProductionV2TextStageRequest(source_revision_id=pending["revision"]["revision_id"],
                units=[{"unit_id": "scene-001", "source": "s" * 17000}], max_chars_per_batch=16000))
    assert blocked.value.status_code == 422
    assert blocked.value.detail["code"] == "text_stage_budget_exceeded"
    assert blocked.value.detail["retryable"] is False


def test_scene_and_dialogue_text_stage_requires_accepted_story_and_preserves_unit_ids(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch, story="A director enters a theater and finds a note.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: {
        "review_id": "director-review-unsafe", "decision": "approve", "accepted": True,
        "reviews": [{"chunk_id": "story_chunk_0001", "decision": "approve", "confidence": 0.95,
                     "issues": [], "repair_instruction": ""}], "issues": [], "repair_instructions": []})
    captured = {}
    def fake_units(**kwargs):
        captured.update(kwargs)
        return {"stage": kwargs["stage"], "items": [{"unit_id": row["unit_id"], "content": {"description": "Generated."}}
                                                       for row in kwargs["units"]],
                "expected_unit_ids": [row["unit_id"] for row in kwargs["units"]],
                "completed_unit_ids": [row["unit_id"] for row in kwargs["units"]], "complete": True}
    monkeypatch.setattr(api, "generate_chunked_units", fake_units)
    run = asyncio.run(api.create_production_v2_run(
        project_id, api.ProductionV2RunRequest(idempotency_key="story-to-scenes", control_mode="manual")))
    pending = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    with pytest.raises(HTTPException) as blocked:
        api.generate_production_v2_text_stage(project_id, run["run_id"], "scenes",
            api.ProductionV2TextStageRequest(source_revision_id=pending["revision"]["revision_id"],
                                             units=[{"unit_id": "scene-001", "source": "Enter"}]))
    assert blocked.value.status_code == 409

    accepted = asyncio.run(api.accept_production_v2_story_revision(
        project_id, run["run_id"], pending["revision"]["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=pending["revision"]["source_hash"])))
    assert accepted["accepted"] is True
    units = [{"unit_id": "scene-001", "source": "Enter the theater."},
             {"unit_id": "scene-002", "source": "Find the note.", "source_chunk_ids": ["story_chunk_0001"]}]
    response = api.generate_production_v2_text_stage(project_id, run["run_id"], "scenes",
        api.ProductionV2TextStageRequest(source_revision_id=pending["revision"]["revision_id"], units=units))
    assert response["review_required"] is True
    assert response["revision"]["completed_unit_ids"] == ["scene-001", "scene-002"]
    assert "expanded_story" not in captured["context"]
    assert captured["units"][1]["source_context"][0]["chunk_id"] == "story_chunk_0001"
    assert response["revision"]["warnings"][0]["code"] == "units_without_source_chunk_links"
    accepted_scenes = asyncio.run(api.accept_production_v2_text_revision(
        project_id, run["run_id"], "scenes", response["revision"]["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=pending["revision"]["source_hash"])))
    assert accepted_scenes["accepted"] is True


def test_scene_beats_are_validated_before_review_or_revision_persistence(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch, story="Mira follows the blue marker to the stairwell.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: pytest.fail("invalid scene reached Director review"))
    monkeypatch.setattr(api, "generate_chunked_units", lambda **kwargs: {
        "stage": "scenes", "items": [{"unit_id": "scene-1", "content": {"shots": [
            {"beat": "Mira reaches the stairwell."}]}}],
        "expected_unit_ids": ["scene-1"], "completed_unit_ids": ["scene-1"], "complete": True,
    })
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="scene-beat-contract", control_mode="manual")))
    canon = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())["revision"]
    asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"], canon["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=canon["source_hash"])))

    with pytest.raises(HTTPException) as invalid:
        api.generate_production_v2_text_stage(project_id, run["run_id"], "scenes",
            api.ProductionV2TextStageRequest(source_revision_id=canon["revision_id"], units=[{
                "unit_id": "scene-1", "source_chunk_ids": ["story_chunk_0001"],
                "shot_units": [{"unit_id": "shot-1"}],
            }]))
    assert invalid.value.detail["code"] == "scene_output_invalid"
    assert invalid.value.detail["invalid_fields"] == ["shots.unit_id"]
    assert not list((tmp_path / "output" / project_id / "production_v2" / "runs" / run["run_id"]
        / "story" / "revisions" / "scenes").glob("*.json"))


@pytest.mark.parametrize("stage", ["scenes", "dialogue"])
def test_director_repair_cannot_persist_broken_scene_or_speaker_contract(tmp_path: Path, monkeypatch, stage):
    from story_builder.services import director_contract

    project_id = _temporary_project(tmp_path, monkeypatch, story="Mira reaches the stairwell.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: {
        "review_id": "story-review", "accepted": True, "decision": "approve", "reviews": [], "issues": []})
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key=f"repair-contract-{stage}", control_mode="fully_automated")))
    canon = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())["revision"]
    unit = {"unit_id": "scene-1" if stage == "scenes" else "shot-1",
        "source_chunk_ids": ["story_chunk_0001"], "character_ids": ["char-mira"]}
    if stage == "scenes":
        unit["shot_units"] = [{"unit_id": "shot-1"}]
        valid_content = {"shots": [{"unit_id": "shot-1", "beat": "Mira reaches the stairwell."}]}
        broken_content = {"shots": [{"beat": "Mira reaches the stairwell."}]}
    else:
        monkeypatch.setattr(api, "read_project_canon", lambda *_args: {"characters": [
            {"character_id": "char-mira", "display_name": "Mira", "status": "active"}]})
        valid_content = {"dialogue": [{"speaker_id": "char-mira", "text": "We are here."}]}
        broken_content = {"dialogue": [{"character": "Mira", "text": "We are here."}]}
    monkeypatch.setattr(api, "generate_chunked_units", lambda **_kwargs: {
        "stage": stage, "items": [{**unit, "content": valid_content}], "complete": True,
        "expected_unit_ids": [unit["unit_id"]], "completed_unit_ids": [unit["unit_id"]]})
    # Exercise the real review/repair producer rather than mocking its final revision.
    responses = iter([
        {"decision": "repair", "confidence": 0.9, "issues": ["clarify"], "repair_instruction": "Clarify the beat."},
        {"content": broken_content},
        {"decision": "approve", "confidence": 0.9, "issues": []},
    ])
    monkeypatch.setattr(director_contract, "generate_json", lambda **_kwargs: next(responses))
    with pytest.raises(HTTPException) as invalid:
        api.generate_production_v2_text_stage(project_id, run["run_id"], stage,
            api.ProductionV2TextStageRequest(source_revision_id=canon["revision_id"], units=[unit]))
    assert invalid.value.detail["code"] == ("scene_output_invalid" if stage == "scenes" else "dialogue_output_invalid")
    assert invalid.value.detail["retryable"] is True
    assert not api.production_story_revisions.list_stage_revisions(api.OUTPUT_ROOT, project_id, run["run_id"], stage)


def test_text_stage_rejects_unsafe_stage_and_incomplete_units(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: {
        "review_id": "director-review-unsafe", "decision": "approve", "accepted": True,
        "reviews": [{"chunk_id": "story_chunk_0001", "decision": "approve", "confidence": 0.95,
                     "issues": [], "repair_instruction": ""}], "issues": [], "repair_instructions": [], "repaired_chunks": {}})
    run = asyncio.run(api.create_production_v2_run(
        project_id, api.ProductionV2RunRequest(idempotency_key="unsafe-stage", control_mode="fully_automated")))
    story = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    with pytest.raises(HTTPException) as unsafe:
        api.generate_production_v2_text_stage(project_id, run["run_id"], "../../files",
            api.ProductionV2TextStageRequest(source_revision_id=story["revision"]["revision_id"], units=[{"unit_id": "x"}]))
    assert unsafe.value.status_code == 404


@pytest.mark.parametrize("mode", ["fully_automated", "semi"])
def test_full_mode_runs_director_review_before_releasing_text_stage(tmp_path: Path, monkeypatch, mode):
    project_id = _temporary_project(tmp_path, monkeypatch, story="Mira receives a warning.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api.reasoning_provider, "model_for", lambda _provider: "gpt-6-sol")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: {
        "review_id": "story-approved", "decision": "approve", "accepted": True,
        "reviews": [], "issues": [], "repair_instructions": [], "repaired_chunks": {}})
    monkeypatch.setattr(api, "generate_chunked_units", lambda **kwargs: {
        "stage": kwargs["stage"], "items": [{"unit_id": row["unit_id"],
            "content": {"description": "Mira reads the warning."}} for row in kwargs["units"]],
        "expected_unit_ids": [row["unit_id"] for row in kwargs["units"]],
        "completed_unit_ids": [row["unit_id"] for row in kwargs["units"]], "complete": True})
    monkeypatch.setattr(api, "review_text_stage_revision", lambda *, revision, **_kwargs: {
        "review_id": "director-text-review-1", "corpus_version": "h3_prompt_rules_v1",
        "accepted": True, "decision": "approve", "repair_attempts": 0,
        "items": [{**revision["items"][0], "director_review": {"decision": "approve", "confidence": 0.96}}]})
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="full-text-review", control_mode=mode, semi_gates={"story_review": False})))
    story = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    response = api.generate_production_v2_text_stage(project_id, run["run_id"], "scenes",
        api.ProductionV2TextStageRequest(source_revision_id=story["revision"]["revision_id"],
            units=[{"unit_id": "scene-001", "source": "Mira reads the warning.",
                    "source_chunk_ids": ["story_chunk_0001"]}]))
    assert response["accepted"] is True
    assert response["review_required"] is False
    assert response["director_review"]["review_id"] == "director-text-review-1"
    assert response["revision"]["provider"] == "codex"
    assert response["revision"]["model"] == "gpt-6-sol"
    persisted = api.production_story_revisions.load_stage_revision(
        api.OUTPUT_ROOT, project_id, run["run_id"], "scenes", response["revision"]["revision_id"])
    assert persisted["model"] == "gpt-6-sol"
    events = asyncio.run(api.get_production_v2_run(project_id, run["run_id"]))["events"]
    assert any(event["event_type"] == "director_scenes_review" for event in events)


@pytest.mark.parametrize("canon_has_mira", [True, False])
def test_dialogue_generation_and_director_review_share_project_canon_identity_map(tmp_path: Path, monkeypatch, canon_has_mira):
    project_id = _temporary_project(tmp_path, monkeypatch, story="Mira warns Arun about the rising water.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: {
        "review_id": "story-approved", "decision": "approve", "accepted": True,
        "reviews": [], "issues": [], "repair_instructions": [], "repaired_chunks": {}})
    mira_id = "10f943fd-b3b3-40c4-8f16-420022769711"
    canon_characters = [
        {"character_id": "83f56632-f74d-4c60-86bc-d3e5ab73f4e6", "display_name": "Arun", "status": "active"},
    ]
    if canon_has_mira:
        canon_characters.insert(0, {"character_id": mira_id, "display_name": "Mira", "status": "active"})
    monkeypatch.setattr(api, "read_project_canon", lambda *_args: {"characters": canon_characters})
    captured = {}

    def generate_units(**kwargs):
        captured["generation_context"] = kwargs["context"]
        return {"stage": "dialogue", "items": [{"unit_id": "shot-01", "content": {
            "dialogue": [{"speaker_id": mira_id, "text": "The water is rising."}]}}],
            "expected_unit_ids": ["shot-01"], "completed_unit_ids": ["shot-01"], "complete": True}

    def review_revision(*, revision, review_context, **_kwargs):
        captured["review_context"] = review_context
        return {"review_id": "dialogue-review", "corpus_version": "h3_prompt_rules_v1",
            "accepted": True, "decision": "approve", "repair_attempts": 0,
            "items": revision["items"], "issues": []}

    monkeypatch.setattr(api, "generate_chunked_units", generate_units)
    monkeypatch.setattr(api, "review_text_stage_revision", review_revision)
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="dialogue-canon-map", control_mode="fully_automated")))
    story = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    request = api.ProductionV2TextStageRequest(source_revision_id=story["revision"]["revision_id"], units=[{
        "unit_id": "shot-01", "scene_id": "scene-01", "character_ids": [mira_id],
        "scene_context": {"characters": ["Mira"], "shot": {"beat": "Mira warns Arun."}},
        "source_chunk_ids": ["story_chunk_0001"]}])
    if not canon_has_mira:
        with pytest.raises(HTTPException) as unavailable:
            api.generate_production_v2_text_stage(project_id, run["run_id"], "dialogue", request)
        assert unavailable.value.status_code == 409
        assert unavailable.value.detail["code"] == "dialogue_character_identity_unavailable"
        assert unavailable.value.detail["character_ids"] == [mira_id]
        assert captured == {}
        return

    response = api.generate_production_v2_text_stage(project_id, run["run_id"], "dialogue", request)
    expected_map = {mira_id: "Mira"}
    assert response["accepted"] is True
    assert captured["generation_context"]["character_identity_map"] == expected_map
    assert captured["review_context"]["character_identity_map"] == expected_map


def test_shot_plan_generation_uses_frozen_h3_rules_and_rejects_stale_corpus(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch, story="Mira enters the observatory.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: {
        "review_id": "story-approved", "decision": "approve", "accepted": True,
        "reviews": [], "issues": [], "repair_instructions": [], "repaired_chunks": {}})
    captured = {}
    generated_content = {"prompt": "", "duration_seconds": 8, "dialogue": [], "asset_intents": []}
    def fake_shot_units(**kwargs):
        captured.update(kwargs)
        return {"stage": kwargs["stage"], "items": [{"unit_id": "shot-001", "content": generated_content.copy()}],
            "expected_unit_ids": ["shot-001"], "completed_unit_ids": ["shot-001"], "complete": True}
    monkeypatch.setattr(api, "generate_chunked_units", fake_shot_units)
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="shot-h3-snapshot", control_mode="manual")))
    pending = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())
    asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"],
        pending["revision"]["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=pending["revision"]["source_hash"])))
    request = api.ProductionV2TextStageRequest(source_revision_id=pending["revision"]["revision_id"],
        units=[{"unit_id": "shot-001", "source_chunk_ids": ["story_chunk_0001"],
            "approved_dialogue_lines": [{"speaker_id": "character-mira", "text": "The storm is coming."}]}],
        context={"reference_map": {"pictures": [{"tag": "<Picture 1>"}]}})
    with pytest.raises(HTTPException) as incomplete:
        api.generate_production_v2_text_stage(project_id, run["run_id"], "shot_plans", request)
    assert incomplete.value.status_code == 422
    assert incomplete.value.detail["code"] == "shot_plan_output_invalid"
    assert incomplete.value.detail["retryable"] is True
    assert incomplete.value.detail["invalid_fields"] == ["prompt"]
    generated_content.update(prompt="Mira enters the observatory at dusk.")
    generated = api.generate_production_v2_text_stage(project_id, run["run_id"], "shot_plans", request)
    assert generated["revision"]["items"][0]["content"]["dialogue"] == [
        {"speaker_id": "character-mira", "text": "The storm is coming."}]
    rules = captured["context"]["active_h3_prompt_rules"]
    assert rules["version"] == run["config"]["h3_rules_version"]
    assert rules["content_hash"] == run["config"]["h3_rules_hash"]
    assert "Picture" in rules["reference_roles"]
    assert captured["context"]["caller_context"]["reference_map"]["pictures"][0]["tag"] == "<Picture 1>"
    assert captured["context"]["approved_reference_catalog"] == [{
        "shot_id": "shot-001", "scene_id": "", "character_ids": [], "world_id": None,
        "images": [], "videos": [], "voice_references": [],
        "scope": "approved project assets and this run's bound voice excerpts"}]
    assert captured["context"]["supported_asset_roles"] == sorted(api.PRODUCTION_ASSET_ROLE_KINDS)

    original_loader = api.load_prompt_corpus
    monkeypatch.setattr(api, "load_prompt_corpus", lambda: {**original_loader(),
        "version": "different-version"})
    with pytest.raises(HTTPException) as stale:
        api.generate_production_v2_text_stage(project_id, run["run_id"], "shot_plans",
            api.ProductionV2TextStageRequest(source_revision_id=pending["revision"]["revision_id"],
                units=[{"unit_id": "shot-002"}]))
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "h3_rules_snapshot_stale"


def test_deterministic_video_retake_preserves_frozen_inputs_is_idempotent_and_stops_at_two(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    ledger = api._production_v2_ledger()
    run = ledger.create_run(project_id=project_id, idempotency_key="director-retake-run",
        # Exercise the deterministic retake primitive independently of the
        # Director-owned authorization path, which requires a fresh prep task.
        config={"control_mode": "manual", "provider": "codex", "director_profile": {}})
    request = api.ProductionV2ShotValidateRequest(shot_plan_revision_id="shot-plan-v1",
        prompt="A silver train crosses the valley.", seed=42)
    original = ledger.queue_take(project_id=project_id, run_id=run["run_id"], shot_id="shot-01",
        take_id="take-original", idempotency_key="initial", input_snapshot={
            "validation_request": request.model_dump(), "shot_plan_revision_id": "shot-plan-v1",
            "reference_map": {"images": []}})
    validations = []
    monkeypatch.setattr(api, "validate_production_v2_shot", lambda _project, _run, _shot, body:
        (validations.append(body.model_dump()) or {"validation_hash": "h" * 64,
            "reference_map": {"images": []}, "workflow_id": "minimax_h3_r2v_dynamic_v1",
            "workflow_version": "1", "workflow_readiness": {"available": True}}))
    first_decision = {"action": "retake", "prompt_delta": "Keep the train centered."}

    first = api._enqueue_director_video_retake(original, first_decision)
    replay = api._enqueue_director_video_retake(original, first_decision)
    first_take = next(row for row in ledger.get_run(project_id=project_id, run_id=run["run_id"])["takes"]
        if row["take_id"] == first["take_id"])
    second_decision = {"action": "retake", "prompt_delta": "Preserve the same train direction."}
    second = api._enqueue_director_video_retake(first_take, second_decision)
    second_replay = api._enqueue_director_video_retake(first_take, second_decision)
    third = api._enqueue_director_video_retake(second,
        {"action": "retake", "prompt_delta": "Adjust only the camera angle."})

    assert first["take_id"] == replay["take_id"]
    assert second_replay["take_id"] == second["take_id"]
    assert first["input_snapshot"]["validation_request"]["prompt"] == (
        "A silver train crosses the valley.\n\nDirector correction: Keep the train centered.")
    assert first["input_snapshot"]["validation_request"]["seed"] == 42
    assert first["input_snapshot"]["director_retake_root_take_id"] == "take-original"
    assert second["status"] == "queued"
    assert third["status"] == "rejected"
    assert len(validations) == 2
    assert len(ledger.get_run(project_id=project_id, run_id=run["run_id"])["takes"]) == 3


def test_director_video_retake_waits_for_fresh_durable_preparation_then_replays_exact_take(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="director-retake-prep-run", control_mode="fully_automated")))
    ledger = api._production_v2_ledger()
    run_id = run["run_id"]
    revision = {"schema_version": 1, "revision_id": "shot_plans-cafe00000001", "stage": "shot_plans",
        "review_status": "accepted", "created_at": "2026-10-05T00:00:00+00:00",
        "items": [{"unit_id": "shot-01", "scene_id": "scene-01", "content": {
            "prompt": "A silver train crosses the valley.", "duration_seconds": 5.0,
            "dialogue": [], "asset_intents": []}}]}
    api.production_story_revisions.write_stage_revision(tmp_path / "output", project_id, run_id,
        "shot_plans", revision)
    request = api.ProductionV2ShotValidateRequest(shot_plan_revision_id=revision["revision_id"],
        prompt="A silver train crosses the valley.", seed=42)
    take = ledger.queue_take(project_id=project_id, run_id=run_id, shot_id="shot-01",
        take_id="take-prepared", idempotency_key="initial-prepared", input_snapshot={
            "validation_request": request.model_dump(), "shot_plan_revision_id": "shot-plan-v1",
            "prompt_preparation_task_id": "original-preparation-task"})
    validated = []
    reference_map = {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}}
    def validate(_project, _run, _shot, body):
        validated.append(body.model_dump())
        return {"valid": True, "reference_resolution_hash": "r" * 64,
            "asset_fingerprints": {}, "reference_map": reference_map,
            "validation_hash": "h" * 64, "workflow_id": "minimax_h3_t2v_local_v1",
            "workflow_version": 1, "workflow_readiness": {"available": True}}
    monkeypatch.setattr(api, "validate_production_v2_shot", validate)
    decision = {"action": "retake", "prompt_delta": "Keep the train centered."}
    pending = api._enqueue_director_video_retake(take, decision)
    repeated = api._enqueue_director_video_retake(take, decision)
    assert pending["status"] == "preparing"
    assert repeated["prompt_preparation_task_id"] == pending["prompt_preparation_task_id"]
    tasks = api._production_stage_task_store().list_run(project_id=project_id, run_id=run_id)
    task = next(row for row in tasks if row["task_id"] == pending["prompt_preparation_task_id"])
    assert task["status"] == "queued"
    assert task["request"]["director_retake_of_take_id"] == take["take_id"]
    assert task["request"]["director_retake_root_take_id"] == take["take_id"]
    assert len(ledger.get_run(project_id=project_id, run_id=run_id)["takes"]) == 1

    store = api._production_stage_task_store()
    owner = "fresh-retake-preparation-test"
    store.claim(task_id=task["task_id"], owner_token=owner)
    prepared_prompt = task["request"]["validation_request"]["prompt"]
    prepared_request = {**task["request"]["validation_request"], "prompt": prepared_prompt}
    store.complete(task_id=task["task_id"], owner_token=owner, result={
        "accepted": True, "prompt": prepared_prompt,
        "prompt_hash": hashlib.sha256(prepared_prompt.encode()).hexdigest(),
        "resolved_validation_request": prepared_request, "reference_map": reference_map,
        "asset_fingerprints": {}})
    queued = api._enqueue_director_video_retake(take, decision)
    replay = api._enqueue_director_video_retake(take, decision)
    assert queued["status"] == "queued"
    assert replay["take_id"] == queued["take_id"]
    assert queued["input_snapshot"]["prompt_preparation_task_id"] == task["task_id"]
    assert queued["input_snapshot"]["director_retake_root_take_id"] == take["take_id"]
    assert queued["input_snapshot"]["director_retake_of_take_id"] == take["take_id"]
    assert queued["input_snapshot"]["director_retake_decision_hash"]
    assert len(ledger.get_run(project_id=project_id, run_id=run_id)["takes"]) == 2
    assert len(validated) == 2


def test_director_video_retake_replay_recovers_existing_child_before_new_dispatch_gate(tmp_path: Path, monkeypatch):
    project_id = _temporary_project(tmp_path, monkeypatch)
    ledger = api._production_v2_ledger()
    run = ledger.create_run(project_id=project_id, idempotency_key="director-retake-replay-run",
        config={"control_mode": "fully_automated", "provider": "codex", "director_profile": {}})
    original_request = api.ProductionV2ShotValidateRequest(shot_plan_revision_id="shot-plan-v1",
        prompt="A silver train crosses the valley.", seed=42)
    original = ledger.queue_take(project_id=project_id, run_id=run["run_id"], shot_id="shot-01",
        take_id="take-before-restart", idempotency_key="initial-before-restart", input_snapshot={
            "validation_request": original_request.model_dump(), "shot_plan_revision_id": "shot-plan-v1"})
    decision = {"action": "retake", "prompt_delta": "Keep the train centered."}
    root_take_id = original["take_id"]
    decision_hash = hashlib.sha256(json.dumps(decision, sort_keys=True).encode()).hexdigest()[:16]
    key = f"director-retake-{root_take_id}-{decision_hash}"
    child_request = original_request.model_copy(update={
        "prompt": "A silver train crosses the valley.\n\nDirector correction: Keep the train centered."})
    existing = ledger.queue_take(project_id=project_id, run_id=run["run_id"], shot_id="shot-01",
        take_id=str(uuid.uuid5(uuid.UUID(run["run_id"]), key)),
        idempotency_key=key, input_snapshot={
            "validation_request": child_request.model_dump(),
            "director_retake_root_take_id": root_take_id,
            "director_retake_of_take_id": original["take_id"]})
    monkeypatch.setattr(api, "validate_production_v2_shot",
        lambda *_args: pytest.fail("An existing retake replay must not validate or submit again."))

    replay = api._enqueue_director_video_retake(original, decision)

    assert replay["job_id"] == existing["job_id"]
    assert replay["take_id"] == existing["take_id"]
    assert len(ledger.get_run(project_id=project_id, run_id=run["run_id"])["takes"]) == 2


def test_run_status_links_pending_director_retake_to_safe_preparation_status(monkeypatch):
    task = {"task_id": "retake-prep-task", "stage": "controller:resolved_shot_prompt",
        "status": "running", "request": {"director_retake_of_take_id": "source-take",
            "shot_id": "shot-1", "shot_plan_revision_id": "shot_plans-cafe00000001"},
        "request_hash": "private", "owner_token": "private-owner"}
    class Ledger:
        def get_run(self, **_kwargs):
            return {"project_id": "p1", "run_id": "r1", "takes": [{"take_id": "source-take",
                "director_review": {"resolution_status": "review_recovery_pending",
                    "decision": {"action": "retake", "prompt_delta": "private"}}}]}
    class StageStore:
        def list_run(self, **_kwargs):
            return [dict(task)]
    monkeypatch.setattr(api, "_production_v2_ledger", lambda: Ledger())
    monkeypatch.setattr(api, "_production_stage_task_store", lambda: StageStore())

    result = asyncio.run(api.get_production_v2_run("p1", "r1"))

    assert result["takes"][0]["director_review"]["retake_preparation"] == {
        "task_id": "retake-prep-task", "status": "running"}
    assert result["stage_tasks"][0]["shot_id"] == "shot-1"
    assert "request" not in result["stage_tasks"][0]
    assert "request_hash" not in result["stage_tasks"][0]
    assert "owner_token" not in result["stage_tasks"][0]


def test_manual_source_story_creates_verbatim_reviewable_canon_without_provider(tmp_path: Path, monkeypatch):
    story = "Mira warns Arjun about the storm.\n\nAfter a pause, they leave for the station."
    project_id = _temporary_project(tmp_path, monkeypatch, story=story)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("manual source canon must not call a provider")))
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="manual-source-run", control_mode="manual")))
    source_hash = run["config"]["source_story_hash"]

    result = api.create_manual_production_v2_story_source(project_id, run["run_id"],
        api.ProductionV2ManualStorySourceRequest(expected_source_hash=source_hash))
    replay = api.create_manual_production_v2_story_source(project_id, run["run_id"],
        api.ProductionV2ManualStorySourceRequest(expected_source_hash=source_hash))

    revision = result["revision"]
    assert result["review_required"] is True and result["accepted"] is False
    assert replay["reused"] is True
    assert replay["revision"]["revision_id"] == revision["revision_id"]
    assert revision["expanded_story"] == story
    assert revision["review_status"] == "pending_review"
    assert revision["provider"] is None and revision["author"] == "user:source_story"
    assert revision["completeness"]["all_source_chunks_echoed"] is True
    assert revision["completeness"]["all_fact_evidence_verified"] is False
    assert "".join(row["source_excerpt"] for row in revision["chunks"]) == story

    accepted = asyncio.run(api.accept_production_v2_story_revision(project_id, run["run_id"],
        revision["revision_id"], api.ProductionV2StoryAcceptRequest(expected_source_hash=source_hash)))
    assert accepted["accepted"] is True
    stored = api.production_story_revisions.load_revision(api.OUTPUT_ROOT, project_id, run["run_id"], revision["revision_id"])
    assert stored["review_status"] == "accepted"
    assert stored["expanded_story"] == story


@pytest.mark.parametrize(("control_mode", "semi_gates"), [
    ("fully_automated", {}), ("semi", {"story_review": False}),
])
def test_manual_source_story_cannot_bypass_director_owned_gate(tmp_path: Path, monkeypatch,
        control_mode: str, semi_gates: dict[str, bool]):
    project_id = _temporary_project(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key=f"manual-source-{control_mode}", control_mode=control_mode,
        semi_gates=semi_gates)))
    with pytest.raises(HTTPException) as blocked:
        api.create_manual_production_v2_story_source(project_id, run["run_id"],
            api.ProductionV2ManualStorySourceRequest(expected_source_hash=run["config"]["source_story_hash"]))
    assert blocked.value.status_code == 409
    assert blocked.value.detail["code"] == "director_story_gate_owned"


@pytest.mark.parametrize("nested_scene_ids", [False, True])
def test_previous_cut_reference_requires_exact_accepted_immediate_same_scene_video(monkeypatch, nested_scene_ids):
    plan = {"items": [{"unit_id": "cut-1", "scene_id": "scene-a"},
        {"unit_id": "cut-2", "scene_id": "scene-a"},
        {"unit_id": "cut-3", "scene_id": "scene-b"}]}
    if nested_scene_ids:
        plan["items"] = [{"unit_id": row["unit_id"], "content": {"scene_id": row["scene_id"]}}
            for row in plan["items"]]
    take = {"take_id": "take-1", "shot_id": "cut-1", "status": "accepted",
        "output_hashes": [{"kind": "video", "asset_id": "pa-0123456789abcdef", "sha256": "a" * 64}]}
    record = {"asset_id": "pa-0123456789abcdef", "project_id": "p1", "source": "project_output",
        "kind": "video", "roles": ["project_video", "previous_cut_tail"], "filename": "take.mp4",
        "sha256": "a" * 64, "metadata": {"run_id": "r1", "shot_id": "cut-1", "take_id": "take-1"}}
    class Ledger:
        def get_run(self, **_kwargs):
            return {"takes": [take]}
    monkeypatch.setattr(api, "_production_v2_ledger", lambda: Ledger())
    monkeypatch.setattr(api, "get_production_asset_record", lambda *_args: record)
    ref = api._previous_cut_reference("p1", "r1", shot_plan_revision=plan,
        shot_id="cut-2", predecessor_take_id="take-1")
    assert ref == {"asset_id": record["asset_id"], "filename": "take.mp4",
        "sha256": "a" * 64, "role": "previous_cut_tail"}
    with pytest.raises(HTTPException) as boundary:
        api._previous_cut_reference("p1", "r1", shot_plan_revision=plan,
            shot_id="cut-3", predecessor_take_id="take-1")
    assert boundary.value.detail["code"] == "scene_boundary_predecessor"
    with pytest.raises(HTTPException) as wrong_parent:
        api._previous_cut_reference("p1", "r1", shot_plan_revision=plan,
            shot_id="cut-2", predecessor_take_id="take-other")
    assert wrong_parent.value.detail["code"] == "accepted_same_scene_predecessor_required"
    monkeypatch.setattr(api, "get_production_asset_record", lambda *_args: {**record,
        "metadata": {**record["metadata"], "shot_id": "foreign-shot"}})
    with pytest.raises(HTTPException) as wrong_asset:
        api._previous_cut_reference("p1", "r1", shot_plan_revision=plan,
            shot_id="cut-2", predecessor_take_id="take-1")
    assert wrong_asset.value.detail["code"] == "predecessor_video_provenance_mismatch"


def test_targeted_shot_repair_preserves_approved_sibling_and_reopens_canonical_result(tmp_path, monkeypatch):
    import copy
    project_id = _temporary_project(tmp_path, monkeypatch, story="Mira enters the observatory.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **_kwargs: {
        "review_id": "approved", "accepted": True, "decision": "approve", "reviews": [],
        "issues": [], "repair_instructions": [], "repaired_chunks": {}})
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="targeted", control_mode="fully_automated")))
    story = api.detail_production_v2_story(project_id, run['run_id'], api.ProductionV2StoryDetailRequest())['revision']
    units = [{"unit_id": name, "source_chunk_ids": ["story_chunk_0001"], "approved_dialogue_lines": []} for name in ('shot-1', 'shot-2')]
    content = {'prompt': 'Mira enters the observatory.', 'duration_seconds': 5, 'dialogue': [], 'asset_intents': []}
    original_items = [{**copy.deepcopy(unit), 'content': copy.deepcopy(content), 'director_review': {
        'decision': 'repair' if index == 0 else 'approve', 'confidence': .9, 'issues': ['Label inference.'] if index == 0 else []}}
        for index, unit in enumerate(units)]
    base = {'schema_version': 1, 'project_id': project_id, 'run_id': run['run_id'], 'stage': 'shot_plans',
        'revision_id': 'shot_plans-012345abcdef', 'source_revision_id': story['revision_id'],
        'created_at': '2026-01-01T00:00:00Z', 'review_status': 'pending_director_repair',
        'items': original_items, 'expected_unit_ids': ['shot-1', 'shot-2'], 'completed_unit_ids': ['shot-1', 'shot-2'], 'complete': True}
    api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id, run['run_id'], 'shot_plans', base)
    calls = []
    def generate(**kwargs):
        calls.append(('generate', [u['unit_id'] for u in kwargs['units']]))
        assert kwargs['units'][0]['repair_issues'] == ['Label inference.']
        assert kwargs['units'][0]['prior_content'] == content
        return {'items': [{**kwargs['units'][0], 'content': {**content, 'inference': ['Camera is inferred.']}}],
            'expected_unit_ids': ['shot-1'], 'completed_unit_ids': ['shot-1'], 'complete': True}
    def review(**kwargs):
        items = copy.deepcopy(kwargs['revision']['items'])
        calls.append(('review', [item['unit_id'] for item in items]))
        items[0]['director_review'] = {'decision': 'approve', 'confidence': .9, 'issues': []}
        return {'accepted': True, 'items': items, 'review_id': 'targeted-approved', 'decision': 'approve',
            'corpus_version': 'test', 'repair_attempts': 1}
    monkeypatch.setattr(api, 'generate_chunked_units', generate)
    monkeypatch.setattr(api, 'review_text_stage_revision', review)
    body = api.ProductionV2TextStageRequest(source_revision_id=story['revision_id'], units=units,
        repair_from_revision_id=base['revision_id'])
    response = api.generate_production_v2_text_stage(project_id, run['run_id'], 'shot_plans', body)
    saved = api.production_story_revisions.load_stage_revision(api.OUTPUT_ROOT, project_id, run['run_id'],
        'shot_plans', response['revision']['revision_id'])
    assert calls == [('generate', ['shot-1']), ('review', ['shot-1'])]
    assert saved['review_status'] == 'accepted'
    assert saved['parent_revision_id'] == base['revision_id']
    assert saved['items'][1] == base['items'][1]
    assert saved['expected_unit_ids'] == saved['completed_unit_ids'] == ['shot-1', 'shot-2']
    assert saved['inherited_approved_unit_ids'] == ['shot-2']
    assert api.production_story_revisions.load_stage_revision(api.OUTPUT_ROOT, project_id, run['run_id'],
        'shot_plans', base['revision_id']) == base
    with pytest.raises(HTTPException) as stale:
        api.generate_production_v2_text_stage(project_id, run['run_id'], 'shot_plans', body)
    assert stale.value.detail['code'] == 'targeted_repair_stale'
    assert len(calls) == 2


@pytest.mark.parametrize("repair_changes_design", [False, True])
def test_visual_master_consistency_after_director_repair_before_canonical_write(tmp_path, monkeypatch, repair_changes_design):
    import copy
    project_id = _temporary_project(tmp_path, monkeypatch, story="Mira waits, then leaves the stairwell.")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "generate_story_canon", _fake_story_canon)
    monkeypatch.setattr(api, "review_story_revision", lambda **kw: {
        "review_id": "story-ok", "accepted": True, "decision": "approve", "reviews": [], "issues": []})
    run = asyncio.run(api.create_production_v2_run(project_id,
        api.ProductionV2RunRequest(idempotency_key="visual-consistency", control_mode="fully_automated")))
    story = api.detail_production_v2_story(project_id, run["run_id"], api.ProductionV2StoryDetailRequest())["revision"]
    units = [{"unit_id": f"visual-{i}", "source_chunk_ids": ["story_chunk_0001"]} for i in (1, 2)]
    items = [{**unit, "content": {"visual_brief": "Mira waits in the stairwell.", "continuity": {
        "visible_characters_and_animal": [{"id": "mira", "identity": "Mira", "proposed_design_choice": "Dark rain jacket, hair tied back."}],
        "location": {"id": "stairs", "identifier": "Concrete landing, metal rail."}}}} for unit in units]
    monkeypatch.setattr(api, "generate_chunked_units", lambda **kw: {
        "items": copy.deepcopy(items), "complete": True, "expected_unit_ids": [u["unit_id"] for u in units],
        "completed_unit_ids": [u["unit_id"] for u in units]})
    def review(**kw):
        assert kw["review_context"]["caller_context"]["fixed_master_designs"]["mira"] == "Dark rain jacket, hair tied back."
        repaired = copy.deepcopy(kw["revision"]["items"])
        if repair_changes_design:
            repaired[1]["content"]["continuity"]["visible_characters_and_animal"][0]["proposed_design_choice"] = "Blue sweater."
        return {"accepted": True, "items": repaired, "review_id": "visual-ok", "decision": "approve", "corpus_version": "test", "repair_attempts": 1}
    monkeypatch.setattr(api, "review_text_stage_revision", review)
    body = api.ProductionV2TextStageRequest(source_revision_id=story["revision_id"], units=units, context={"fixed_master_designs": {"mira": "Dark rain jacket, hair tied back.", "stairs": "Concrete landing, metal rail."}})
    if repair_changes_design:
        with pytest.raises(HTTPException) as caught:
            api.generate_production_v2_text_stage(project_id, run["run_id"], "visual_briefs", body)
        assert caught.value.detail["code"] == "visual_master_design_invalid"
        assert not api.production_story_revisions.list_stage_revisions(api.OUTPUT_ROOT, project_id, run["run_id"], "visual_briefs")
    else:
        response = api.generate_production_v2_text_stage(project_id, run["run_id"], "visual_briefs", body)
        reopened = api.production_story_revisions.load_stage_revision(api.OUTPUT_ROOT, project_id, run["run_id"], "visual_briefs", response["revision"]["revision_id"])
        assert reopened["review_status"] == "accepted"
        assert api._accepted_visual_master_design("mira", "character_master", reopened)["design"] == "Dark rain jacket, hair tied back."
