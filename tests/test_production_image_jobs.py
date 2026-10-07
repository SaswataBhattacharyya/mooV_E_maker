import json
from pathlib import Path

import pytest

from story_builder.services.production_image_jobs import ProductionImageJobStore
from story_builder.services.production_ledger import LedgerConflict, LedgerNotFound


def candidate(seed: int) -> dict:
    return {"seed": seed, "graph": {"1": {"class_type": "KSampler", "inputs": {"seed": seed}}}}


def enqueue(store: ProductionImageJobStore, *, key="request-1", candidates=None):
    return store.enqueue_batch(project_id="project-1", run_id="run-1", idempotency_key=key,
        workflow_id="z_image_turbo", workflow_version="1", asset_role="character_master",
        prompt="A cinematic character portrait", settings={"width": 1280, "height": 720},
        candidates=[candidate(100), candidate(101)] if candidates is None else candidates)


def test_batch_is_durable_project_scoped_and_idempotent(tmp_path):
    db = tmp_path / "jobs.sqlite3"
    store = ProductionImageJobStore(db)
    first = enqueue(store)
    again = enqueue(ProductionImageJobStore(db))
    assert first["batch_id"] == again["batch_id"]
    assert again["reused"] is True
    assert len(first["jobs"]) == 2
    assert [row["candidate_index"] for row in first["jobs"]] == [1, 2]
    assert all("graph" not in row for row in first["jobs"])
    assert store.list_batch(project_id="project-1", batch_id=first["batch_id"])["jobs"][0]["status"] == "queued"
    with pytest.raises(LedgerNotFound):
        store.list_batch(project_id="other-project", batch_id=first["batch_id"])


def test_staging_cleanup_waits_until_every_batch_candidate_has_known_terminal_result(tmp_path):
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    batch = enqueue(store, candidates=[candidate(1), candidate(2)])
    first, second = batch["jobs"]
    assert not store.batch_is_settled(project_id="project-1", batch_id=batch["batch_id"])
    for row in (first, second):
        claimed = store.next_queued()
        assert claimed["job_id"] == row["job_id"]
        store.transition(row["job_id"], "failed", error={"code": "fixture"})
    assert store.batch_is_settled(project_id="project-1", batch_id=batch["batch_id"])
    assert not store.batch_is_settled(project_id="other-project", batch_id=batch["batch_id"])


def test_recovery_required_image_batch_keeps_staged_inputs(tmp_path):
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    batch = enqueue(store, candidates=[candidate(1)])
    claimed = store.next_queued()
    store.reserve_prompt_id(claimed["job_id"])
    store.transition(claimed["job_id"], "recovery_required", error={"code": "unknown"})
    assert not store.batch_is_settled(project_id="project-1", batch_id=batch["batch_id"])


def test_worker_cleans_image_staging_only_after_all_candidate_jobs_settle(tmp_path):
    from story_builder.services.production_image_worker import ProductionImageWorker
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    batch = store.enqueue_batch(project_id="project-1", run_id="run-1", idempotency_key="staged-batch",
        workflow_id="qwen_image_edit_2511", workflow_version="1", asset_role="character_master",
        prompt="edit", settings={"source_asset_ids": ["pa-0123456789abcdef"], "staging_owner_id": "image-owner"},
        candidates=[candidate(3), candidate(4)])
    cleaned = []
    worker = ProductionImageWorker(store, comfy_url="http://comfy.test", output_root=tmp_path / "output",
        register_output=lambda **_kwargs: {}, cleanup_staging=cleaned.append)
    first = store.next_queued()
    store.transition(first["job_id"], "failed", error={"code": "known-failure"})
    worker._cleanup_staging_if_batch_settled(first)
    assert cleaned == []
    second = store.next_queued()
    store.transition(second["job_id"], "failed", error={"code": "known-failure"})
    worker._cleanup_staging_if_batch_settled(second)
    assert cleaned == ["image-owner"]


def test_idempotency_conflict_does_not_create_duplicate_jobs(tmp_path):
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    enqueue(store)
    with pytest.raises(LedgerConflict):
        enqueue(store, candidates=[candidate(999), candidate(1000)])
    with store._connect() as db:
        assert db.execute("SELECT count(*) FROM production_image_jobs").fetchone()[0] == 2


def test_director_review_is_durable_immutable_and_attached_to_batch(tmp_path):
    db = tmp_path / "jobs.sqlite3"
    store = ProductionImageJobStore(db)
    batch = enqueue(store, candidates=[candidate(7)])
    job = batch["jobs"][0]
    store.next_queued()
    store.reserve_prompt_id(job["job_id"])
    store.transition(job["job_id"], "running")
    store.transition(job["job_id"], "completed", output_asset_id="asset-1")
    decision = {"schema_version": 1, "action": "accept", "confidence": 0.9,
                "reason": "Identity and requested role are clear.", "criteria": [{"name": "identity", "passed": True, "evidence": "matching hair"}]}

    persisted = ProductionImageJobStore(db).record_director_review(project_id="project-1", run_id="run-1",
        job_id=job["job_id"], asset_id="asset-1", decision=decision)
    assert persisted["resolution_status"] == "pending"
    assert ProductionImageJobStore(db).list_batch(project_id="project-1", batch_id=batch["batch_id"])["jobs"][0]["director_review"]["decision"] == decision
    with pytest.raises(LedgerConflict, match="immutable"):
        store.record_director_review(project_id="project-1", run_id="run-1", job_id=job["job_id"],
            asset_id="asset-1", decision={**decision, "reason": "changed"})
    assert store.resolve_director_review(job_id=job["job_id"], resolution_status="accepted")["resolution_status"] == "accepted"
    with pytest.raises(LedgerConflict, match="resolved differently"):
        store.resolve_director_review(job_id=job["job_id"], resolution_status="blocked")


def test_director_review_claim_is_exclusive_recoverable_and_bounded(tmp_path):
    db = tmp_path / "jobs.sqlite3"
    store = ProductionImageJobStore(db)
    batch = store.enqueue_batch(project_id="project-1", run_id="run-1", idempotency_key="full-review",
        workflow_id="qwen_image_edit_2511", workflow_version="1", asset_role="character_master",
        prompt="A character portrait", settings={"control_mode": "fully_automated"},
        candidates=[candidate(8)])
    job = batch["jobs"][0]
    store.next_queued()
    store.reserve_prompt_id(job["job_id"])
    store.transition(job["job_id"], "running")
    store.transition(job["job_id"], "completed", output_asset_id="asset-8")

    first_store = ProductionImageJobStore(db)
    claim = first_store.claim_next_director_review(owner_token="backend-a", lease_seconds=600, max_attempts=3)
    assert claim["job_id"] == job["job_id"]
    assert claim["review_attempt_count"] == 1
    assert ProductionImageJobStore(db).claim_next_director_review(owner_token="backend-b") is None
    assert store.list_batch(project_id="project-1", batch_id=batch["batch_id"])["jobs"][0]["director_review"]["resolution_status"] == "reviewing"

    with pytest.raises(LedgerConflict, match="lease expired or belongs"):
        first_store.record_director_review(project_id="project-1", run_id="run-1", job_id=job["job_id"],
            asset_id="asset-8", decision={"action": "blocked"}, owner_token="backend-b")
    assert first_store.release_director_review_claim(job_id=job["job_id"], owner_token="backend-a")

    assert store.list_batch(project_id="project-1", batch_id=batch["batch_id"])["jobs"][0]["director_review"]["resolution_status"] == "review_recovery_pending"
    for expected_attempt in (2, 3):
        recovered = ProductionImageJobStore(db).claim_next_director_review(owner_token=f"backend-{expected_attempt}",
            lease_seconds=600, max_attempts=3)
        assert recovered["review_attempt_count"] == expected_attempt
        with ProductionImageJobStore(db)._connect() as connection:
            connection.execute("UPDATE production_image_director_review_claims SET lease_until=? WHERE job_id=?",
                ("2000-01-01T00:00:00+00:00", job["job_id"]))
    exhausted = ProductionImageJobStore(db).claim_next_director_review(owner_token="backend-final",
        lease_seconds=600, max_attempts=3)
    assert exhausted["review_attempts_exhausted"] is True
    assert exhausted["job_id"] == job["job_id"]


def test_comfy_output_cleanup_retries_only_the_exact_owned_file_in_container(tmp_path, monkeypatch):
    import subprocess
    from story_builder.services import production_image_worker as worker_module

    output = tmp_path / "comfy-output"
    owned = output / "nested" / "candidate-1_00001_.png"
    unrelated = output / "nested" / "keep-this.png"
    owned.parent.mkdir(parents=True)
    owned.write_bytes(b"owned duplicate")
    unrelated.write_bytes(b"unrelated output")
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    worker = worker_module.ProductionImageWorker(store, comfy_url="http://comfy.test",
        output_root=tmp_path / "project-output", comfy_output_root=output,
        register_output=lambda **_kwargs: {})
    original_unlink = Path.unlink

    def deny_only_owned(self, *args, **kwargs):
        if self == owned:
            raise PermissionError("container-owned output")
        return original_unlink(self, *args, **kwargs)

    calls = []
    def fake_docker(args, **kwargs):
        calls.append(args)
        remote_path = Path(args[-1])
        relative = remote_path.relative_to(Path("/workspace/ComfyUI/output"))
        host_path = output / relative
        if "rm" in args:
            original_unlink(host_path)
            return subprocess.CompletedProcess(args, 0, "", "")
        if "test" in args:
            return subprocess.CompletedProcess(args, 1 if host_path.exists() else 0, "", "")
        raise AssertionError(f"unexpected docker command: {args}")

    monkeypatch.setattr(worker_module.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr(worker_module.subprocess, "run", fake_docker)
    monkeypatch.setattr(Path, "unlink", deny_only_owned)
    graph = {"76": {"class_type": "SaveImage", "inputs": {"filename_prefix": "nested/candidate-1"}}}
    history = {"outputs": {"76": {"images": [
        {"filename": owned.name, "subfolder": "nested", "type": "output"},
        {"filename": unrelated.name, "subfolder": "nested", "type": "output"},
    ]}}}

    worker._cleanup_owned_comfy_outputs(graph, history)

    assert not owned.exists()
    assert unrelated.exists()
    assert len(calls) == 2
    assert calls[0][0:6] == ["/usr/bin/docker", "exec", "--user", "0", "comfy-stack", "rm"]
    assert calls[0][-1] == "/workspace/ComfyUI/output/nested/candidate-1_00001_.png"
    assert calls[1][calls[1].index("test"):] == ["test", "!", "-e", calls[0][-1]]


def test_single_claim_and_stable_prompt_id_before_running(tmp_path):
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    batch = enqueue(store)
    claimed = store.next_queued()
    assert claimed and claimed["status"] == "preparing"
    assert claimed["graph"]["1"]["inputs"]["seed"] == 100
    assert store.next_queued()["candidate_index"] == 2
    with pytest.raises(LedgerConflict):
        store.transition(claimed["job_id"], "running")
    prompt_id = store.reserve_prompt_id(claimed["job_id"])
    running = store.transition(claimed["job_id"], "running")
    assert running["prompt_id"] == prompt_id
    assert store.list_batch(project_id="project-1", batch_id=batch["batch_id"])["jobs"][0]["status"] == "running"


def test_restart_marks_unknown_remote_work_for_manual_reconciliation(tmp_path):
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    claimed = store.next_queued() if enqueue(store) else None
    assert claimed
    prompt_id = store.reserve_prompt_id(claimed["job_id"])
    assert store.mark_orphaned_submissions_for_recovery() == 1
    recovered = store.list_batch(project_id="project-1", batch_id=claimed["batch_id"])["jobs"][0]
    assert recovered["status"] == "recovery_required"
    assert recovered["prompt_id"] == prompt_id
    assert "no automatic resubmission" in recovered["error"]["message"]
    assert store.mark_orphaned_submissions_for_recovery() == 0


def test_startup_requeues_preparing_jobs_without_prompt_id_but_holds_submitted_jobs(tmp_path):
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    batch = enqueue(store, candidates=[candidate(1), candidate(2)])
    preparing = store.next_queued()
    submitting = store.next_queued()
    assert preparing and submitting
    prompt_id = store.reserve_prompt_id(submitting["job_id"])

    summary = store.reconcile_after_restart()

    assert summary == {"requeued_unsubmitted": 1, "held_for_reconciliation": 1}
    jobs = store.list_batch(project_id="project-1", batch_id=batch["batch_id"])["jobs"]
    by_id = {job["job_id"]: job for job in jobs}
    assert by_id[preparing["job_id"]]["status"] == "queued"
    assert by_id[preparing["job_id"]]["prompt_id"] is None
    assert by_id[submitting["job_id"]]["status"] == "recovery_required"
    assert by_id[submitting["job_id"]]["prompt_id"] == prompt_id
    assert store.reconcile_after_restart() == {"requeued_unsubmitted": 0, "held_for_reconciliation": 0}


def test_startup_quarantines_inconsistent_preparing_row_with_prompt_id(tmp_path):
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    batch = enqueue(store)
    job = store.next_queued()
    assert job
    # Simulate a corrupt/legacy record which must never be considered safe to resend.
    with store._connect() as db:
        db.execute("UPDATE production_image_jobs SET prompt_id=? WHERE job_id=?", ("unexpected-prompt", job["job_id"]))

    assert store.reconcile_after_restart() == {"requeued_unsubmitted": 0, "held_for_reconciliation": 1}
    recovered = store.list_batch(project_id="project-1", batch_id=batch["batch_id"])["jobs"][0]
    assert recovered["status"] == "recovery_required"
    assert recovered["prompt_id"] == "unexpected-prompt"


def test_invalid_batch_rejected(tmp_path):
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    with pytest.raises(ValueError):
        enqueue(store, candidates=[])
    with pytest.raises(ValueError):
        enqueue(store, candidates=[{"seed": 1}])


def test_worker_keeps_candidate_backend_queued_when_comfy_health_is_unknown(tmp_path):
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    batch = enqueue(store, candidates=[candidate(5)])
    calls = []

    def not_idle(url, **kwargs):
        calls.append((url, kwargs))
        raise RuntimeError("queue health unavailable")

    # Health uncertainty keeps the row backend-queued and does not POST a graph.
    from story_builder.services.production_image_worker import ProductionImageWorker
    worker = ProductionImageWorker(store, comfy_url="http://comfy.invalid", output_root=tmp_path / "out",
        register_output=lambda **_kwargs: pytest.fail("must not register without a render"),
        request_json=not_idle)
    result = worker.process_one()
    assert result["status"] == "waiting_for_comfyui"
    record = store.list_batch(project_id="project-1", batch_id=batch["batch_id"])["jobs"][0]
    assert record["status"] == "queued"
    assert record["prompt_id"] is None
    assert calls


def test_full_image_worker_blocks_before_gpu_when_saved_director_provider_fails_preflight(tmp_path):
    from story_builder.services.production_image_worker import ProductionImageWorker

    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    batch = store.enqueue_batch(project_id="project-1", run_id="run-1", idempotency_key="full-provider-preflight",
        workflow_id="z_image_turbo", workflow_version="1", asset_role="character_master",
        prompt="A fictional traveler", settings={"director_review_required": True,
            "director_provider": "codex"}, candidates=[candidate(19)])
    preflights = []

    def preflight(provider):
        preflights.append(provider)
        raise RuntimeError("provider configuration is invalid")

    worker = ProductionImageWorker(store, comfy_url="http://comfy.test", output_root=tmp_path / "out",
        register_output=lambda **_kwargs: pytest.fail("blocked provider cannot register an image"),
        request_json=lambda *_args, **_kwargs: pytest.fail("provider preflight must run before ComfyUI access"),
        gpu_inspector=lambda **_kwargs: pytest.fail("provider preflight must run before GPU admission"),
        director_provider_preflight=preflight)

    result = worker.process_one()

    job = store.list_batch(project_id="project-1", batch_id=batch["batch_id"])["jobs"][0]
    assert preflights == ["codex"]
    assert result["status"] == "failed"
    assert job["status"] == "failed"
    assert job["prompt_id"] is None
    assert job["error"]["code"] == "director_provider_unavailable"


def test_worker_registers_completed_image_output_and_records_provenance(tmp_path, monkeypatch):
    from story_builder.services import production_image_worker as worker_module
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    batch = enqueue(store, candidates=[candidate(44)])
    calls = []
    prompt_ids = []

    def request(url, *, method="GET", payload=None, **kwargs):
        calls.append((url, method, payload))
        if url.endswith("/queue"):
            return {"queue_running": [], "queue_pending": []}
        if url.endswith("/prompt"):
            prompt_ids.append(payload["prompt_id"])
            return {"prompt_id": payload["prompt_id"]}
        if prompt_ids and url.endswith(f"/history/{prompt_ids[0]}"):
            return {prompt_ids[0]: {"status": {"completed": True}, "outputs": {}}}
        raise AssertionError(url)

    monkeypatch.setattr(worker_module, "collect_outputs", lambda *_args, destination_dir, **_kwargs: [
        {"kind": "image", "relative_path": "candidate.png", "filename": "candidate.png"}])
    registrations = []
    worker = worker_module.ProductionImageWorker(store, comfy_url="http://comfy.test", output_root=tmp_path / "output",
        register_output=lambda **kwargs: registrations.append(kwargs) or {"asset_id": "pa-1234567890abcdef"},
        request_json=request, release_idle=lambda **_kwargs: {"status": "requested"},
        sleep=lambda _seconds: None)
    result = worker.process_one()
    assert result == {"status": "completed", "job_id": batch["jobs"][0]["job_id"], "asset_id": "pa-1234567890abcdef"}
    saved = store.list_batch(project_id="project-1", batch_id=batch["batch_id"])["jobs"][0]
    assert saved["status"] == "completed" and saved["prompt_id"] == prompt_ids[0]
    assert saved["output_asset_id"] == "pa-1234567890abcdef"
    assert registrations[0]["relative_path"].endswith("candidate.png")
    assert registrations[0]["metadata"]["production_image_job"]["seed"] == 44
    assert [call[1] for call in calls].count("POST") == 1


def test_worker_does_not_retry_when_prompt_submission_outcome_is_unknown(tmp_path):
    from story_builder.services.production_image_worker import ProductionImageWorker
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    batch = enqueue(store, candidates=[candidate(8)])
    posted = []
    def request(url, *, method="GET", **_kwargs):
        if url.endswith("/queue"):
            return {"queue_running": [], "queue_pending": []}
        if url.endswith("/prompt"):
            posted.append(url)
            raise TimeoutError("socket closed after request")
        raise AssertionError(url)
    worker = ProductionImageWorker(store, comfy_url="http://comfy.test", output_root=tmp_path / "out",
        register_output=lambda **_kwargs: pytest.fail("unknown submit cannot register"),
        request_json=request, release_idle=lambda **_kwargs: {}, sleep=lambda _seconds: None)
    result = worker.process_one()
    row = store.list_batch(project_id="project-1", batch_id=batch["batch_id"])["jobs"][0]
    assert result["status"] == "recovery_required"
    assert row["status"] == "recovery_required" and row["prompt_id"]
    assert len(posted) == 1


def test_worker_cleanup_removes_only_output_files_with_its_owned_prefix(tmp_path):
    from story_builder.services.production_image_worker import ProductionImageWorker
    store = ProductionImageJobStore(tmp_path / "jobs.sqlite3")
    comfy_output = tmp_path / "comfy-output"
    owned_dir = comfy_output / "project" / "production_image_jobs" / "batch"
    owned_dir.mkdir(parents=True)
    owned = owned_dir / "candidate-1_00001_.png"
    unrelated = owned_dir / "other-workflow_00001_.png"
    temp = owned_dir / "candidate-1_00002_.png"
    for path in (owned, unrelated, temp):
        path.write_bytes(b"file")
    worker = ProductionImageWorker(store, comfy_url="http://comfy.test", output_root=tmp_path / "output",
        comfy_output_root=comfy_output, register_output=lambda **_kwargs: {})
    graph = {"1": {"class_type": "SaveImage", "inputs": {
        "filename_prefix": "project/production_image_jobs/batch/candidate-1"}}}
    history = {"outputs": {"1": {"images": [
        {"filename": owned.name, "subfolder": "project/production_image_jobs/batch", "type": "output"},
        {"filename": unrelated.name, "subfolder": "project/production_image_jobs/batch", "type": "output"},
        {"filename": temp.name, "subfolder": "project/production_image_jobs/batch", "type": "temp"},
        {"filename": "escape.png", "subfolder": "../../outside", "type": "output"},
    ]}}}
    worker._cleanup_owned_comfy_outputs(graph, history)
    assert not owned.exists()
    assert unrelated.exists() and temp.exists()


def test_accepted_image_candidate_adds_role_without_copying_media(tmp_path, monkeypatch):
    from story_builder.services import production_assets
    root = tmp_path / "projects"
    output = tmp_path / "output" / "project-1" / "production" / "image_jobs" / "job-1"
    output.mkdir(parents=True)
    media = output / "candidate.png"
    media.write_bytes(b"one canonical candidate")
    monkeypatch.setattr(production_assets, "_probe_media", lambda *_args, **_kwargs: {"width": 1280, "height": 720})
    candidate_asset = production_assets.register_output(root, tmp_path / "output", "project-1",
        relative_path="production/image_jobs/job-1/candidate.png", role="image_candidate",
        metadata={"production_image_job": {"status": "completed", "intended_role": "character_master"}})
    accepted = production_assets.accept_image_candidate(root, "project-1", candidate_asset["asset_id"], role="character_master")
    assert accepted["asset_id"] == candidate_asset["asset_id"]
    assert accepted["roles"] == ["image_candidate", "character_master"]
    assert accepted["metadata"]["production_image_job"]["accepted"] is True
    assert media.read_bytes() == b"one canonical candidate"
    repeated = production_assets.accept_image_candidate(root, "project-1", candidate_asset["asset_id"], role="character_master")
    assert repeated["roles"].count("character_master") == 1
