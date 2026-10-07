from copy import deepcopy
import asyncio
from io import BytesIO
from types import SimpleNamespace
import wave

from fastapi import BackgroundTasks, HTTPException
import pytest

from story_builder.api import main as api
from story_builder.services import audio_effects, production_job_worker, media_jobs


def setup_project(tmp_path, monkeypatch, config=None):
    store = api.ProjectStore(tmp_path / "projects")
    project = store.create_project(title="Audio recovery", story_input="Two people wait.", automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", store)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project["id"], api.ProductionV2RunRequest(idempotency_key="run", **(config or {}))))
    return project["id"], run["run_id"]


def test_sidecar_api_retries_use_same_durable_job_and_validate_scope(tmp_path, monkeypatch):
    project, run = setup_project(tmp_path, monkeypatch)
    request = api.ProductionAudioSidecarRequest(idempotency_key="click", kind="music", prompt="quiet strings", duration_seconds=8)
    first = asyncio.run(api.create_production_audio_sidecar(project, run, request, BackgroundTasks()))
    repeated = asyncio.run(api.create_production_audio_sidecar(project, run, request, BackgroundTasks()))
    assert first["job_id"] == repeated["job_id"]
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(api.create_production_audio_sidecar(project, run, request.model_copy(update={"prompt": "drums"}), BackgroundTasks()))
    assert conflict.value.status_code == 409
    durable = api._production_audio_store()
    first.update(status="recovery_required", prompt_id="saved-prompt")
    durable.save(first)
    assert asyncio.run(api.get_production_audio_sidecar(project, run, first["job_id"]))["prompt_id"] == "saved-prompt"


def test_sidecar_restart_collects_exact_prompt_without_posting(tmp_path, monkeypatch):
    project, run = setup_project(tmp_path, monkeypatch)
    job = asyncio.run(api.create_production_audio_sidecar(project, run,
        api.ProductionAudioSidecarRequest(idempotency_key="click", kind="sfx", prompt="rain"), BackgroundTasks()))
    job.update(status="submitting", prompt_id="reserved-before-crash")
    api._production_audio_store().save(job)
    calls = []
    monkeypatch.setattr(api, "ensure_prompt_watchdog", lambda **kwargs: calls.append(kwargs["prompt_id"]))
    monkeypatch.setattr(api, "run_control_foley_job", lambda *args, **kwargs: pytest.fail("Recovery resubmitted a workflow"))
    monkeypatch.setattr(production_job_worker, "_request_json", lambda url, **kwargs: {
        "reserved-before-crash": {"status": {"completed": True}, "outputs": {}}})
    def collect(history, *, destination_dir, **kwargs):
        destination_dir.mkdir(parents=True, exist_ok=True)
        with wave.open(str(destination_dir / "sound.wav"), "wb") as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(32000)
            audio.writeframes(b"\0\0" * 32000)
        return [{"kind": "audio", "filename": "sound.wav", "relative_path": "sound.wav"}]
    monkeypatch.setattr(media_jobs, "collect_outputs", collect)
    api._execute_production_audio_sidecar(project, run, deepcopy(job))
    completed = api._production_audio_store().get(project, run, job["job_id"])
    assert completed["status"] == "completed" and completed["production_asset_id"]
    asset = api.get_production_asset_record(api.PROJECT_STORE.root_dir, project, completed["production_asset_id"])
    assert asset["roles"] == ["sfx_candidate"]
    api._execute_production_audio_sidecar(project, run, deepcopy(job))
    assert calls == ["reserved-before-crash"], "Repeated request recollected an already registered output"


def test_dialogue_conversion_restart_uses_exact_prompt_and_registers_separate_lineage(tmp_path, monkeypatch):
    project, run = setup_project(tmp_path, monkeypatch)
    job = {"job_id": "effect-rvc-recovery", "project_id": project, "production_run_id": run,
        "idempotency_key": "convert-once", "status": "recovery_required", "prompt_id": "reserved-rvc",
        "sidecar_kind": "dialogue_conversion", "operation": "rvc", "source_asset_id": "pa-original",
        "character_id": "character-a", "speaker_id": "S1", "transcript": "Exact words.", "settings": {}}
    store = api._production_audio_store()
    store.enqueue(project, run, "convert-once", {"source_asset_id": "pa-original"}, job)
    calls = []
    monkeypatch.setattr(api, "ensure_prompt_watchdog", lambda **kwargs: calls.append(kwargs["prompt_id"]))
    resolve_asset = api.resolve_production_asset_content
    def resolve_for_registration(*args):
        if args[-1] == "pa-original":
            pytest.fail("Recovery should not reread the original source")
        return resolve_asset(*args)
    monkeypatch.setattr(api, "resolve_production_asset_content", resolve_for_registration)
    monkeypatch.setattr(audio_effects, "run_effect_job", lambda **kwargs: pytest.fail("Recovery must not POST another prompt"))
    monkeypatch.setattr(production_job_worker, "_request_json", lambda url, **kwargs: {
        "reserved-rvc": {"status": {"completed": True}, "outputs": {}}})
    def collect(history, *, destination_dir, **kwargs):
        destination_dir.mkdir(parents=True, exist_ok=True)
        with wave.open(str(destination_dir / "converted.wav"), "wb") as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(32000)
            audio.writeframes(b"\0\0" * 32000)
        return [{"kind": "audio", "filename": "converted.wav", "relative_path": "converted.wav"}]
    monkeypatch.setattr(media_jobs, "collect_outputs", collect)
    api._execute_production_audio_sidecar(project, run, deepcopy(job))
    completed = store.get(project, run, job["job_id"])
    assert completed["status"] == "completed", completed.get("error")
    assert completed["production_asset_id"] != "pa-original"
    registered = api.get_production_asset_record(api.PROJECT_STORE.root_dir, project, completed["production_asset_id"])
    assert registered["metadata"]["dialogue_take"] == {
        "version": 1, "run_id": run, "character_id": "character-a", "speaker_id": "S1",
        "transcript": "Exact words.", "recording_status": "converted", "source_asset_id": "pa-original",
        "effect_job_id": job["job_id"], "conversion_operation": "rvc"}
    assert calls == ["reserved-rvc"]


def test_dialogue_conversion_pre_submit_restart_rebuilds_using_same_reserved_prompt(tmp_path, monkeypatch):
    project, run = setup_project(tmp_path, monkeypatch)
    source = tmp_path / "source.wav"
    source.write_bytes(b"original")
    job = {"job_id": "effect-rvc-pre-submit", "project_id": project, "production_run_id": run,
        "idempotency_key": "pre-submit", "status": "preparing", "prompt_id": "reserved-before-preflight",
        "sidecar_kind": "dialogue_conversion", "operation": "rvc", "source_asset_id": "pa-original",
        "character_id": "character-a", "speaker_id": "S1", "transcript": "Exact words.", "settings": {}}
    store = api._production_audio_store()
    store.enqueue(project, run, "pre-submit", {"source_asset_id": "pa-original"}, job)
    monkeypatch.setattr(api, "resolve_production_asset_content", lambda *_args: (source, "audio/wav", source.name))
    observed = {}
    def resume(**kwargs):
        observed.update(kwargs["job"])
        kwargs["update"]({"status": "submitting", "prompt_id": kwargs["job"]["prompt_id"]})
    monkeypatch.setattr(audio_effects, "run_effect_job", resume)
    api._execute_production_audio_sidecar(project, run, deepcopy(job))
    persisted = store.get(project, run, job["job_id"])
    assert observed, (persisted.get("status"), persisted.get("error"), persisted.get("sidecar_kind"))
    assert observed["prompt_id"] == "reserved-before-preflight"
    assert store.get(project, run, job["job_id"])["status"] == "submitting"


@pytest.mark.parametrize("mode", ["fully_automated", "semi"])
def test_delegated_render_gate_cannot_fall_back_to_manual_submission(tmp_path, monkeypatch, mode):
    project, run = setup_project(tmp_path, monkeypatch, {"control_mode": mode, "semi_gates": {"shot_workflow_render_approval": False}})
    monkeypatch.setattr(api, "validate_production_v2_shot", lambda *a, **k: pytest.fail("Blocked render reached workflow validation"))
    with pytest.raises(HTTPException) as blocked:
        api.queue_production_v2_take(project, run, "shot", api.ProductionV2TakeQueueRequest(idempotency_key="click",
            validation_request=api.ProductionV2ShotValidateRequest(shot_plan_revision_id="revision", prompt="Wait.")))
    assert blocked.value.detail["code"] == "shot_prompt_preparation_required"
