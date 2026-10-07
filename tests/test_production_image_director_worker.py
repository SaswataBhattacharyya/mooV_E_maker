import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from story_builder.api import main as api
from story_builder.services import production_assets
from story_builder.services.production_image_jobs import ProductionImageJobStore


def test_full_review_worker_replays_deterministic_retake_and_accepts_identity(tmp_path, monkeypatch):
    project_store = api.ProjectStore(tmp_path / "projects")
    project = project_store.create_project(title="Director review", story_input="A traveler arrives.", automation_mode=False)
    project_id = project["id"]
    monkeypatch.setattr(api, "PROJECT_STORE", project_store)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api, "COMFYUI_INPUT_DIR", tmp_path / "comfy-input")
    run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
        idempotency_key="director-review-run", control_mode="fully_automated")))
    character = asyncio.run(api.create_project_character_identity(project_id,
        api.ProductionCanonCharacterCreateRequest()))["character"]

    source = production_assets.register_upload(project_store.root_dir, project_id, filename="source.png",
        content=_png((8, 12, 16)), role="project_image")
    staged_owners = []
    def fake_stage(_source, *, asset_id, owner_id, **_kwargs):
        staged_owners.append(owner_id)
        return SimpleNamespace(filename=f"{owner_id}-{asset_id}.png", source_sha256=source["sha256"])
    monkeypatch.setattr(api, "stage_image_reference", fake_stage)
    monkeypatch.setattr(api, "image_workflow_catalog", lambda: {"workflows": [{
        "workflow_id": "qwen_image_edit_2511", "available": True, "disabled_reason": None}]})
    queued = asyncio.run(api.queue_production_image_job(project_id, run["run_id"],
        api.ProductionImageJobRequest(idempotency_key="initial-director-image",
            workflow_id="qwen_image_edit_2511", asset_role="character_master",
            prompt="A traveler in a red coat.", seed=25, width=1024, height=1024, steps=4, cfg=1.0,
            source_asset_ids=[source["asset_id"]], entity_id=character["character_id"])))
    store = ProductionImageJobStore(api.STORAGE_ROOT / "production" / "v2_ledger.sqlite3")
    job = store.next_queued()
    candidate_path = api.OUTPUT_ROOT / project_id / "production" / "image_jobs" / job["job_id"] / "candidate.png"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_bytes(_png((100, 20, 20)))
    prompt_id = store.reserve_prompt_id(job["job_id"])
    store.transition(job["job_id"], "running", prompt_id=prompt_id)
    output_asset = production_assets.register_output(project_store.root_dir, api.OUTPUT_ROOT, project_id,
        relative_path=str(candidate_path.relative_to(api.OUTPUT_ROOT / project_id)), role="image_candidate",
        metadata={"production_image_job": {"job_id": job["job_id"], "batch_id": queued["batch_id"],
            "run_id": run["run_id"], "workflow_id": job["workflow_id"], "workflow_version": "1",
            "status": "completed", "intended_role": "character_master", "accepted": False}})
    store.transition(job["job_id"], "completed", output_asset_id=output_asset["asset_id"])

    monkeypatch.setattr(api, "review_production_image_candidate", lambda **_kwargs: {
        "schema_version": 1, "action": "retake", "confidence": 0.91,
        "reason": "The requested collar is obscured.", "criteria": [],
        "prompt_delta": "Show the collar clearly, with no obstruction."})
    supervisor = api._make_production_image_supervisor()
    worker = supervisor.worker
    resolve = worker.store.resolve_director_review
    fail_once = {"armed": True}
    def fail_after_retake_enqueue(**kwargs):
        if kwargs.get("resolution_status") == "retake_queued" and fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("simulated worker exit after durable enqueue")
        return resolve(**kwargs)
    worker.store.resolve_director_review = fail_after_retake_enqueue

    with pytest.raises(RuntimeError, match="simulated worker exit"):
        worker.review_next_candidate()
    pending = store.get_director_review(project_id=project_id, job_id=job["job_id"])
    assert pending["resolution_status"] == "pending"
    assert store.has_idempotency_key(project_id=project_id,
        idempotency_key=f"director-retake-{job['job_id']}-1")

    replay = worker.review_next_candidate()
    assert replay["status"] == "retake_queued"
    assert store.get_director_review(project_id=project_id, job_id=job["job_id"])["resolution_status"] == "retake_queued"
    batch = store.list_batch(project_id=project_id, batch_id=queued["batch_id"])
    review = batch["jobs"][0]["director_review"]
    assert len(review["retake_jobs"]) == 1
    assert review["retake_jobs"][0]["settings"]["retake_index"] == 1
    assert review["retake_jobs"][0]["settings"]["source_asset_ids"] == [source["asset_id"]]
    assert staged_owners[-1] == staged_owners[-2]
    with store._connect() as db:
        rows = db.execute("SELECT count(*) FROM production_image_jobs WHERE project_id=?", (project_id,)).fetchone()[0]
    assert rows == 2

    retake_job = store.next_queued()
    retake_prompt_id = store.reserve_prompt_id(retake_job["job_id"])
    store.transition(retake_job["job_id"], "running", prompt_id=retake_prompt_id)
    retake_path = api.OUTPUT_ROOT / project_id / "production" / "image_jobs" / retake_job["job_id"] / "candidate.png"
    retake_path.parent.mkdir(parents=True)
    retake_path.write_bytes(_png((120, 30, 20)))
    retake_asset = production_assets.register_output(project_store.root_dir, api.OUTPUT_ROOT, project_id,
        relative_path=str(retake_path.relative_to(api.OUTPUT_ROOT / project_id)), role="image_candidate",
        metadata={"production_image_job": {"job_id": retake_job["job_id"],
            "batch_id": retake_job["batch_id"], "run_id": run["run_id"],
            "workflow_id": retake_job["workflow_id"], "workflow_version": "1",
            "status": "completed", "intended_role": "character_master", "accepted": False}})
    store.transition(retake_job["job_id"], "completed", output_asset_id=retake_asset["asset_id"])
    monkeypatch.setattr(api, "review_production_image_candidate", lambda **_kwargs: {
        "schema_version": 1, "action": "accept", "confidence": 0.95,
        "reason": "The active character and requested wardrobe are clear.",
        "criteria": [{"name": "identity", "passed": True, "evidence": "matches saved appearance"}],
        "prompt_delta": ""})
    accepted = worker.review_next_candidate()
    assert accepted["status"] == "accepted"
    indexed = production_assets.get_asset_record(project_store.root_dir, project_id, retake_asset["asset_id"])
    assert indexed["metadata"]["character_id"] == character["character_id"]
    assert indexed["metadata"]["approval_status"] == "accepted"
    assert "character_master" in indexed["roles"]
    assert store.get_director_review(project_id=project_id, job_id=retake_job["job_id"])["resolution_status"] == "accepted"


def test_worker_reassesses_only_same_saved_bytes_and_preserves_original_review(tmp_path):
    import hashlib

    from story_builder.services.production_image_worker import ProductionImageWorker

    store = ProductionImageJobStore(tmp_path / "reassessment.sqlite3")
    batch = store.enqueue_batch(project_id="project-a", run_id="run-a",
        idempotency_key="review-reassessment", workflow_id="test-image", workflow_version="1",
        asset_role="character_master", prompt="A person in a coat.",
        settings={"director_review_required": True}, candidates=[{"seed": 5, "graph": {}}])
    job = store.next_queued()
    store.transition(job["job_id"], "running", prompt_id=store.reserve_prompt_id(job["job_id"]))
    candidate = tmp_path / "candidate.png"
    candidate.write_bytes(_png((20, 40, 60)))
    asset_id = "asset-a"
    store.transition(job["job_id"], "completed", output_asset_id=asset_id)
    original_decision = {"schema_version": 1, "action": "blocked", "confidence": 0.0,
        "reason": "The first review omitted the collar evidence.", "criteria": [], "prompt_delta": "",
        "image_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "provider": "codex", "director_profile_version": "image-v1"}
    store.record_director_review(project_id="project-a", run_id="run-a", job_id=job["job_id"],
        asset_id=asset_id, decision=original_decision)
    store.resolve_director_review(job_id=job["job_id"], resolution_status="blocked")

    accepted_decision = {"schema_version": 1, "action": "accept", "confidence": 0.91,
        "reason": "The saved candidate meets the frozen requirements.",
        "criteria": [{"name": "identity", "passed": True, "evidence": "The same visible person and clothing."}],
        "prompt_delta": "", "evidence": {"summary": "Full figure in a green jacket.", "evidence_valid": True},
        "image_sha256": original_decision["image_sha256"], "provider": "codex",
        "director_profile_version": "image-v1"}
    inference_calls = []
    accepted_assets = []
    worker = ProductionImageWorker(store, comfy_url="http://127.0.0.1:3008", output_root=tmp_path,
        register_output=lambda **_kwargs: {}, resolve_candidate=lambda _project, _asset: candidate,
        review_candidate=lambda _job, _path: (inference_calls.append(1) or accepted_decision),
        accept_candidate=lambda current_job: accepted_assets.append(current_job["output_asset_id"]))

    original_bytes = candidate.read_bytes()
    candidate.write_bytes(_png((99, 99, 99)))
    tampered = worker.reassess_existing_candidate(project_id="project-a", job_id=job["job_id"],
        correction_reason="The former evidence extractor omitted visible clothing details.")
    assert tampered["status"] == "held"
    assert inference_calls == []
    candidate.write_bytes(original_bytes)

    assert store.claim_director_reassessment(project_id="project-a", job_id=job["job_id"], owner_token="other-worker")
    claimed = worker.reassess_existing_candidate(project_id="project-a", job_id=job["job_id"],
        correction_reason="The former evidence extractor omitted visible clothing details.")
    assert claimed["status"] == "review_in_progress"
    assert inference_calls == []
    assert store.release_director_review_claim(job_id=job["job_id"], owner_token="other-worker")

    original_accept = worker.accept_candidate
    worker.accept_candidate = lambda _job: (_ for _ in ()).throw(RuntimeError("acceptance interrupted"))
    with pytest.raises(RuntimeError, match="acceptance interrupted"):
        worker.reassess_existing_candidate(project_id="project-a", job_id=job["job_id"],
            correction_reason="The former evidence extractor omitted visible clothing details.")
    worker.accept_candidate = original_accept
    # Reopen the durable store: saved acceptance cannot promote replaced bytes.
    worker.store = ProductionImageJobStore(store.path)
    candidate.write_bytes(_png((99, 99, 99)))
    assert worker.review_next_candidate()["status"] == "held"
    assert worker.reassess_existing_candidate(project_id="project-a", job_id=job["job_id"],
        correction_reason="Recover interrupted acceptance.")["status"] == "held"
    assert accepted_assets == []
    assert inference_calls == [1]
    assert store.get_director_review(project_id="project-a", job_id=job["job_id"])["resolution_status"] == "pending"
    candidate.write_bytes(original_bytes)
    result = worker.reassess_existing_candidate(project_id="project-a", job_id=job["job_id"],
        correction_reason="Recover interrupted acceptance.")
    assert result["status"] == "accepted"
    assert inference_calls == [1]
    assert accepted_assets == [asset_id]
    effective = store.get_director_review(project_id="project-a", job_id=job["job_id"])
    assert effective["resolution_status"] == "accepted"
    assert effective["superseded_review"]["decision"] == original_decision
    assert effective["superseded_review"]["resolution_status"] == "blocked"
    assert store.list_batch(project_id="project-a", batch_id=batch["batch_id"])["jobs"][0]["director_review"] == effective

    # A retry after a crash/restart replays the saved acceptance without another inference.
    replay = worker.reassess_existing_candidate(project_id="project-a", job_id=job["job_id"],
        correction_reason="The former evidence extractor omitted visible clothing details.")
    assert replay["status"] == "accepted"
    assert inference_calls == [1]
    assert accepted_assets == [asset_id]


def _png(color):
    from io import BytesIO
    stream = BytesIO()
    Image.new("RGB", (32, 32), color).save(stream, format="PNG")
    return stream.getvalue()
