"""Opt-in, one-master Full/delegated-Semi production acceptance.

Preparation creates only a disposable project and accepted text/canon fixtures,
or consumes an explicitly supplied accepted-provider artifact and its existing
controller queue. A real ComfyUI render and
saved-provider Director review require --execute-live. Never use this against
the user's production roots; every run gets fresh roots under --artifact-parent.

Run from the repository root on the authorized host:
  PYTHONPATH=/home/riki/web_dev python scripts/acceptance_automatic_image_master.py --execute-live

This is a scoped automatic image-master test, not the complete C2 release gate.
It seeds accepted story/scene/dialogue/visual/shot-plan stages; it does not test
text-provider orchestration. It does exercise the real controller queue, SQLite
image worker, ComfyUI workflow, registry, CPU visual analysis, saved Director
provider, atomic canon assignment, HTTP API and browser readback. The image
worker itself owns shared GPU admission, prompt watchdog, and the 83 C / 2100 MHz
limits. If Director review requests a retake, the harness preserves that queue
and stops; it never silently submits a second image workload.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "app"
sys.path.insert(0, str(ROOT.parent))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_http(url: str, process: subprocess.Popen[str], *, timeout: float = 40) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Owned API/Vite subprocess exited early: {process.returncode}.")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(.2)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def api_get(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        return json.load(response)


def stop_owned(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def acceptance_evidence_root(artifact_root: Path, *, resuming: bool,
                             run_token: str | None = None) -> Path:
    """Keep resumed-run evidence separate while leaving persisted roots in place."""
    artifact_root = artifact_root.resolve()
    if not resuming:
        return artifact_root
    token = run_token or uuid.uuid4().hex
    if not token or Path(token).name != token or token in {".", ".."}:
        raise ValueError("Resume evidence run token must be a single safe path component.")
    return artifact_root / "automatic-image-resume-evidence" / token


def completed_task(store, project_id: str, run_id: str, stage: str, key: str,
                   request: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    task = store.enqueue(project_id=project_id, run_id=run_id, stage=stage,
        idempotency_key=key, request=request)
    owner = f"acceptance-{stage}-{uuid.uuid4().hex[:8]}"
    assert store.claim(task_id=task["task_id"], owner_token=owner)
    return store.complete(task_id=task["task_id"], owner_token=owner, result=result)


def seed_accepted_controller(api, project_id: str, run: dict[str, Any], character_id: str) -> dict[str, str]:
    """Seed stage outputs, then use the real controller to queue one master."""
    from story_builder.services.production_story_revisions import write_revision, write_stage_revision

    run_id = run["run_id"]
    store = api._production_stage_task_store()
    story_id = "story-canon-" + uuid.uuid4().hex[:12]
    scenes_id = "scenes-" + uuid.uuid4().hex[:12]
    dialogue_id = "dialogue-" + uuid.uuid4().hex[:12]
    visual_id = "visual_briefs-" + uuid.uuid4().hex[:12]
    shot_plans_id = "shot_plans-" + uuid.uuid4().hex[:12]
    shot_id = "shot-acceptance-001"
    source_hash = run["config"]["source_story_hash"]
    story = str(api.PROJECT_STORE.read_project(project_id)["story_input"])
    write_revision(api.OUTPUT_ROOT, project_id, run_id, {
        "revision_id": story_id, "project_id": project_id, "run_id": run_id,
        "source_hash": source_hash, "review_status": "accepted", "expanded_story": story,
        "chunks": [{"chunk_id": "story_chunk_0001", "expanded_text": story}], "continuity_rules": []})
    completed_task(store, project_id, run_id, "story_detail", "fixture-story-v1", {},
        {"revision_id": story_id})
    scene_units = [{"unit_id": "scene-acceptance-001", "shot_units": [{"unit_id": shot_id,
        "shot_outline": {"action": "Mira waits at the station entrance."},
        "character_ids": [character_id]}]}]
    completed_task(store, project_id, run_id, "controller:scene_outline", "fixture-outline-v1",
        {"source_revision_id": story_id}, {"units": scene_units})
    source_fields = {"project_id": project_id, "run_id": run_id,
        "source_revision_id": story_id, "source_story_hash": source_hash, "review_status": "accepted"}
    write_stage_revision(api.OUTPUT_ROOT, project_id, run_id, "scenes", {
        **source_fields, "revision_id": scenes_id, "stage": "scenes",
        "items": [{"unit_id": "scene-acceptance-001", "source_chunk_ids": ["story_chunk_0001"],
            "character_ids": [character_id], "shot_units": scene_units[0]["shot_units"],
            "content": {"title": "Station entrance", "shots": [{"unit_id": shot_id,
                "beat": "Mira waits at the station entrance."}]}}]})
    completed_task(store, project_id, run_id, "text:scenes", "fixture-scenes-v1",
        {"source_revision_id": story_id}, {"revision_id": scenes_id})
    write_stage_revision(api.OUTPUT_ROOT, project_id, run_id, "dialogue", {
        **source_fields, "revision_id": dialogue_id, "stage": "dialogue",
        "items": [{"unit_id": shot_id, "scene_id": "scene-acceptance-001",
            "character_ids": [character_id], "content": {"dialogue": []}}]})
    completed_task(store, project_id, run_id, "text:dialogue", "fixture-dialogue-v1",
        {"source_revision_id": story_id}, {"revision_id": dialogue_id})
    write_stage_revision(api.OUTPUT_ROOT, project_id, run_id, "visual_briefs", {
        **source_fields, "revision_id": visual_id, "stage": "visual_briefs",
        "items": [{"unit_id": "visual-acceptance-001", "scene_id": "scene-acceptance-001",
            "character_ids": [character_id], "content": {"visual_brief": "A quiet station entrance."}}]})
    completed_task(store, project_id, run_id, "text:visual_briefs", "fixture-visual-v1",
        {"source_revision_id": story_id}, {"revision_id": visual_id})
    write_stage_revision(api.OUTPUT_ROOT, project_id, run_id, "shot_plans", {
        **source_fields, "revision_id": shot_plans_id, "stage": "shot_plans",
        "items": [{"unit_id": shot_id, "scene_id": "scene-acceptance-001",
            "character_ids": [character_id], "content": {
                "prompt": "A cinematic reference portrait of Mira at the station entrance.",
                "character_ids": [character_id], "duration_seconds": 5}}]})
    completed_task(store, project_id, run_id, "text:shot_plans", "fixture-shot-plans-v1",
        {"source_revision_id": story_id}, {"revision_id": shot_plans_id})

    api._advance_production_text_controller(project_id, run_id)
    image_store = api.ProductionImageJobStore(api.STORAGE_ROOT / "production" / "v2_ledger.sqlite3")
    tasks = store.list_run(project_id=project_id, run_id=run_id)
    queued_events = [event for event in api._production_v2_ledger().get_run(
        project_id=project_id, run_id=run_id).get("events", [])
        if event.get("event_type") == "controller_image_masters_queued"]
    if len(queued_events) != 1:
        raise AssertionError(f"Expected one durable controller master enqueue event; found {len(queued_events)}.")
    pending = queued_events[0].get("payload", {}).get("pending", [])
    if len(pending) != 1:
        raise AssertionError(f"Expected one unique controller identity master; found {len(pending)}.")
    batch_id = pending[0]["batch_id"]
    batch = image_store.list_batch(project_id=project_id, batch_id=batch_id)
    jobs = batch.get("jobs", [])
    if len(jobs) != 1:
        raise AssertionError(f"Full mode should create exactly one candidate; found {len(jobs)}.")
    job = jobs[0]
    if job["settings"].get("review_identity", {}).get("entity_id") != character_id:
        raise AssertionError("Queued automatic master lost its canonical character identity.")
    if job["settings"].get("director_review_required") is not True:
        raise AssertionError("Queued automatic master is missing the Director review gate.")
    if any(row.get("stage") == "controller:resolved_shot_prompt" for row in tasks):
        raise AssertionError("Controller prepared a shot prompt before its required master was accepted.")
    return {"story_revision_id": story_id, "shot_plan_revision_id": shot_plans_id,
        "shot_id": shot_id, "character_id": character_id, "batch_id": batch["batch_id"],
        "job_id": job["job_id"], "workflow_id": job["workflow_id"],
        "candidate_index": job["candidate_index"]}


def classify_persisted_master_jobs(jobs, reviews, pending, *, project_id, run_id,
                                   shot_plan_revision_id):
    """Select one durable leaf per controller identity without enqueueing anything."""
    by_id = {row["job_id"]: row for row in jobs}
    if len(by_id) != len(jobs) or not pending:
        raise RuntimeError("Resume has duplicate jobs or an empty controller master event.")
    children = {}
    for job in jobs:
        if job["project_id"] != project_id or job["run_id"] != run_id:
            raise RuntimeError("Resume contains foreign image work.")
        parent = job.get("settings", {}).get("parent_job_id")
        if parent:
            if parent not in by_id or parent in children:
                raise RuntimeError("Resume contains a missing parent or multiple retake children.")
            children[parent] = job
    identities, visited, leaves = set(), set(), []
    for item in pending:
        identity = (item["role"], item["entity_id"])
        if identity in identities:
            raise RuntimeError("Resume controller identities are duplicated.")
        identities.add(identity)
        roots = [row for row in jobs if row["batch_id"] == item["batch_id"]
                 and not row.get("settings", {}).get("parent_job_id")]
        if len(roots) != 1:
            raise RuntimeError("Resume controller event does not resolve to exactly one original.")
        job = roots[0]
        if job.get("settings", {}).get("controller_shot_plan_revision_id") != shot_plan_revision_id:
            raise RuntimeError("Resume original has a different shot-plan lineage.")
        budget = job.get("settings", {}).get("full_retake_budget")
        index = 0
        while True:
            if job["job_id"] in visited:
                raise RuntimeError("Resume has cyclic or overlapping master lineage.")
            visited.add(job["job_id"])
            settings = job.get("settings", {})
            if (job["asset_role"], (settings.get("review_identity") or {}).get("entity_id")) != identity:
                raise RuntimeError("Resume child changes its parent's canon identity.")
            if (type(budget) is not int or budget < 0
                    or settings.get("full_retake_budget") != budget
                    or type(settings.get("retake_index")) is not int
                    or settings["retake_index"] != index or index > budget
                    or settings.get("controller_shot_plan_revision_id", shot_plan_revision_id) != shot_plan_revision_id):
                raise RuntimeError("Resume child changes the saved retry budget/index or shot-plan lineage.")
            child = children.get(job["job_id"])
            status = job["status"]
            if status == "queued":
                if job.get("prompt_id") is not None or job.get("output_asset_id") is not None or child:
                    raise RuntimeError("Resume queued job has submitted output or a premature child.")
                leaves.append(job)
                break
            if status not in {"completed", "accepted"} or not job.get("prompt_id") or not job.get("output_asset_id"):
                raise RuntimeError("Resume has unreconciled/submitted/failed image work.")
            review = reviews.get(job["job_id"], {})
            if any(review.get(key) != expected for key, expected in {
                "job_id": job["job_id"], "project_id": project_id, "run_id": run_id,
                "asset_id": job["output_asset_id"]}.items()):
                raise RuntimeError("Resume completed candidate lacks its exact persisted review.")
            decision = review.get("decision") or {}
            resolution = review.get("resolution_status")
            if status == "accepted" or resolution == "accepted":
                if resolution != "accepted" or decision.get("action") != "accept" or child:
                    raise RuntimeError("Resume accepted master has an inconsistent review/child.")
                # SQLite stores generation completion separately from review
                # acceptance. Expose the verified leaf state without changing
                # the durable job or replaying its render/review.
                leaves.append({**job, "status": "accepted"})
                break
            if not child:
                raise RuntimeError("Resume completed master is held without a saved correction child.")
            child_index = index + 1
            if resolution == "retake_queued":
                delta = str(decision.get("prompt_delta") or "").strip()
                if (decision.get("action") != "retake" or not delta
                    or review.get("retake_batch_id") != child["batch_id"]
                    or child.get("idempotency_key") != f"director-retake-{job['job_id']}-{child_index}"
                    or child.get("prompt") != f"{job['prompt'].strip()}\n\nDirector correction: {delta}"):
                    raise RuntimeError("Resume Director child differs from the saved decision.")
            elif resolution == "blocked":
                correction = child.get("settings", {}).get("operator_correction_sha256")
                if (decision.get("action") != "blocked"
                    or child.get("idempotency_key") != operator_retake_idempotency_key(job["job_id"], child_index)
                    or not isinstance(correction, str) or not re.fullmatch(r"[0-9a-f]{64}", correction)
                    or not any(hashlib.sha256(child["prompt"][start:].encode()).hexdigest() == correction
                        for start in range(max(0, len(child["prompt"]) - 1000), len(child["prompt"]))
                        if start == 0 or child["prompt"][start - 1].isspace())):
                    raise RuntimeError("Resume blocked original has no exact saved operator correction.")
            else:
                raise RuntimeError("Resume parent review does not authorize its saved child.")
            if child["workflow_id"] != job["workflow_id"]:
                raise RuntimeError("Resume child changes the selected workflow.")
            job, index = child, child_index
    if visited != set(by_id):
        raise RuntimeError("Resume ledger contains jobs outside the controller lineage.")
    return sorted(leaves, key=lambda row: (row["created_at"], row["candidate_index"], row["job_id"]))


def audit_persisted_master_resume(root, *, project_id, run_id, shot_plan_revision_id):
    """Read only: validate saved chains, all prior bytes and queued model prompts."""
    from story_builder.services.production_assets import get_asset_record
    from story_builder.services.production_story_revisions import load_stage_revision
    db_path = root / "storage" / "production" / "v2_ledger.sqlite3"
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        jobs = []
        for row in db.execute("SELECT * FROM production_image_jobs ORDER BY created_at,candidate_index,job_id"):
            job = dict(row)
            job["settings"] = json.loads(job.pop("settings_json"))
            job.pop("graph_json", None)
            jobs.append(job)
        reviews = {}
        for row in db.execute("SELECT * FROM production_image_director_reviews"):
            review = dict(row)
            review["decision"] = json.loads(review.pop("decision_json"))
            reviews[review["job_id"]] = review
        shot_tasks = [dict(row) for row in db.execute(
            "SELECT request_json,result_json FROM production_stage_tasks WHERE project_id=? AND run_id=? AND stage='text:shot_plans' AND status='completed'",
            (project_id, run_id)) if json.loads(row["result_json"] or "{}").get("revision_id") == shot_plan_revision_id]
        events = [json.loads(row[0]) for row in db.execute(
            "SELECT payload_json FROM production_events WHERE project_id=? AND run_id=? AND event_type='controller_image_masters_queued'",
            (project_id, run_id))]
    events = [row for row in events if row.get("shot_plan_revision_id") == shot_plan_revision_id]
    if len(events) != 1:
        raise RuntimeError("Resume requires exactly one saved controller master event.")
    leaves = classify_persisted_master_jobs(jobs, reviews, events[0].get("pending", []),
        project_id=project_id, run_id=run_id, shot_plan_revision_id=shot_plan_revision_id)
    if len(shot_tasks) != 1:
        raise RuntimeError("Resume shot-plan revision lacks an exact completed producer task.")
    request = json.loads(shot_tasks[0]["request_json"])
    visual_id = (request.get("context") or {}).get("visual_brief_revision_id")
    visual = load_stage_revision(root / "output", project_id, run_id, "visual_briefs", visual_id) if visual_id else None
    if not visual or visual.get("review_status") != "accepted" or visual.get("source_revision_id") != request.get("source_revision_id"):
        raise RuntimeError("Resume shot-plan task lost its accepted visual/story pins.")
    cues = {}
    for item in visual.get("items", []):
        continuity = (item.get("content") or {}).get("continuity") or {}
        for design in continuity.get("visible_characters_and_animal", []):
            if design.get("id") and design.get("proposed_design_choice"):
                cues[("character_master", design["id"])] = design["proposed_design_choice"].strip()
        location = continuity.get("location") or {}
        if location.get("id") and location.get("identifier"):
            cues[("world_master", location["id"])] = location["identifier"].strip()
    project_output = (root / "output" / project_id).resolve()
    for job in jobs:
        if job["status"] not in {"completed", "accepted"}:
            continue
        asset = get_asset_record(root / "storage" / "projects", project_id, job["output_asset_id"])
        path = (project_output / asset["relative_path"]).resolve()
        if not path.is_relative_to(project_output) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != asset.get("sha256"):
            raise RuntimeError("Resume prior candidate bytes do not match its canonical hash/path.")
        if (reviews.get(job["job_id"], {}).get("resolution_status") == "accepted"
                and (reviews[job["job_id"]].get("decision") or {}).get("action") == "accept"):
            key = "character_id" if job["asset_role"] == "character_master" else "world_id"
            if (job["asset_role"] not in asset.get("roles", []) or
                    asset.get("metadata", {}).get(key) != job["settings"]["review_identity"]["entity_id"]):
                raise RuntimeError("Resume accepted master lost its canon registry assignment.")
    for job in leaves:
        if job["status"] != "queued":
            continue
        identity = job["settings"]["review_identity"]
        cue = cues.get((job["asset_role"], identity["entity_id"]))
        provenance = job["settings"].get("visual_design_provenance") or identity.get("visual_design_provenance")
        if provenance:
            # A separately corrected visual revision can legitimately replace
            # the old shot-planning visual design without replaying its beats.
            pinned = load_stage_revision(root / "output", project_id, run_id, "visual_briefs", provenance.get("revision_id"))
            if (not pinned or pinned.get("review_status") != "accepted"
                    or pinned.get("source_revision_id") != request.get("source_revision_id")
                    or provenance.get("entity_id") != identity["entity_id"]):
                raise RuntimeError("Resume master lost its accepted visual-design provenance.")
            designs = []
            for item in pinned.get("items", []):
                continuity = (item.get("content") or {}).get("continuity") or {}
                if job["asset_role"] == "character_master":
                    designs.extend(row.get("proposed_design_choice") for row in continuity.get("visible_characters_and_animal", [])
                        if isinstance(row, dict) and row.get("id") == identity["entity_id"])
                else:
                    location = continuity.get("location") or {}
                    if location.get("id") == identity["entity_id"]:
                        designs.append(location.get("identifier"))
            if (not designs or any(not isinstance(value, str) or not value.strip() for value in designs)
                    or len(set(designs)) != 1 or identity.get("approved_visual_design") != designs[0]):
                raise RuntimeError("Resume master appearance differs from its pinned accepted visual revision.")
            cue = designs[0]
        if not cue or cue.casefold() not in job["prompt"].casefold():
            raise RuntimeError("Resume queued prompt drops its approved visual identity cue.")
        if re.search(r"\b(?:entity|character|world|revision|source|visual_design)_?id\b|\bprovenance\b", job["prompt"], re.I) or str(job["settings"]["review_identity"]["entity_id"]).casefold() in job["prompt"].casefold():
            raise RuntimeError("Resume queued prompt contains renderable identity/provenance metadata.")
    return {"leaves": leaves, "preserved_job_ids": [row["job_id"] for row in jobs if row["status"] == "completed"],
            "read_only": True}


def prepare_accepted_text_run(api, root: Path, expected_project_id: str | None = None,
                              expected_run_id: str | None = None,
                              resume_held_job_id: str | None = None,
                              resume_persisted_masters: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fail closed unless the separate persisted provider resume reached accepted shot plans."""
    validate_accepted_text_root_readonly(root, expected_project_id, expected_run_id, resume_held_job_id,
        resume_persisted_masters=resume_persisted_masters)
    result_path = root / "targeted_resume_result.json"
    if not result_path.is_file():
        raise RuntimeError(f"Accepted-text precondition is not ready: missing {result_path}.")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    outcome = result.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("outcome") != "passed" or outcome.get("stage") != "text:shot_plans":
        raise RuntimeError(f"Accepted-text precondition is not ready: targeted resume outcome is {outcome!r}.")
    project_id, run_id = str(result.get("project_id") or ""), str(result.get("run_id") or "")
    if not project_id or not run_id:
        raise RuntimeError("Accepted-text result is missing its project_id/run_id.")
    if expected_project_id and project_id != expected_project_id:
        raise RuntimeError("Accepted-text project ID does not match the supplied project ID.")
    if expected_run_id and run_id != expected_run_id:
        raise RuntimeError("Accepted-text run ID does not match the supplied run ID.")

    ledger_run = api._production_v2_ledger().get_run(project_id=project_id, run_id=run_id)
    config = ledger_run["config"]
    if config.get("control_mode") != "fully_automated" or config.get("making_route") != "reference_built":
        raise RuntimeError("Accepted-text run must be the saved fully automated reference-built route.")
    stage_store = api._production_stage_task_store()
    tasks = stage_store.list_run(project_id=project_id, run_id=run_id)
    active = [row for row in tasks if row.get("status") in {"queued", "running", "recovery_required"}]
    if active:
        raise RuntimeError(f"Accepted-text run still has active/recovery-required tasks: "
            f"{[(row.get('stage'), row.get('status'), row.get('task_id')) for row in active]}.")
    by_stage = {}
    for row in tasks:
        if row.get("status") == "completed":
            by_stage[row["stage"]] = row
    required = {"story_detail": "story_detail", "text:scenes": "scenes",
        "text:dialogue": "dialogue", "text:visual_briefs": "visual_briefs",
        "text:shot_plans": "shot_plans"}
    result_revisions = {row.get("stage"): row for row in result.get("revisions", [])
        if isinstance(row, dict)}
    loaded = {}
    for task_stage, revision_stage in required.items():
        task = by_stage.get(task_stage)
        if not task:
            raise RuntimeError(f"Accepted-text run is missing completed {task_stage!r} task.")
        revision_id = str((task.get("result") or {}).get("revision_id") or "")
        if not revision_id:
            raise RuntimeError(f"Accepted-text {task_stage!r} task has no revision ID.")
        revision = (api.production_story_revisions.load_revision(api.OUTPUT_ROOT,
            project_id, run_id, revision_id) if revision_stage == "story_detail" else
            api.production_story_revisions.load_stage_revision(api.OUTPUT_ROOT,
                project_id, run_id, revision_stage, revision_id))
        report_stage = revision_stage
        report_revision = result_revisions.get(report_stage)
        if not revision or revision.get("review_status") != "accepted":
            raise RuntimeError(f"Persisted {task_stage!r} revision {revision_id!r} is not accepted.")
        if not report_revision or report_revision.get("revision_id") != revision_id \
                or report_revision.get("review_status") != "accepted":
            raise RuntimeError(f"targeted_resume_result.json does not attest accepted {task_stage!r} revision {revision_id!r}.")
        loaded[revision_stage] = revision

    if resume_persisted_masters:
        audit = audit_persisted_master_resume(root, project_id=project_id, run_id=run_id,
            shot_plan_revision_id=loaded["shot_plans"]["revision_id"])
        canon = api.read_project_canon(api.PROJECT_STORE.root_dir, project_id)
        candidates = []
        for job in audit["leaves"]:
            identity = job["settings"]["review_identity"]
            collection, key = (("characters", "character_id") if job["asset_role"] == "character_master" else ("worlds", "world_id"))
            entity = next((row for row in canon.get(collection, []) if row.get(key) == identity["entity_id"]), None)
            if not entity:
                raise RuntimeError("Resume master identity is absent from canon.")
            candidates.append({**job, "role": job["asset_role"], "entity_id": identity["entity_id"],
                "display_name": entity.get("display_name") or identity["entity_id"]})
        return {"project_id": project_id, "run_id": run_id,
            "shot_plan_revision_id": loaded["shot_plans"]["revision_id"],
            "shot_plan_task_id": by_stage["text:shot_plans"]["task_id"],
            "preserved_job_ids": audit["preserved_job_ids"],
            "targeted_resume_result": str(result_path), "targeted_resume_outcome": outcome}, candidates

    image_store = api.ProductionImageJobStore(api.STORAGE_ROOT / "production" / "v2_ledger.sqlite3")
    with image_store._connect() as db:
        before_jobs = db.execute("SELECT job_id,batch_id,project_id,run_id,status,prompt_id,output_asset_id,asset_role,settings_json "
            "FROM production_image_jobs ORDER BY created_at,job_id").fetchall()
    expected_prior = []
    for row in before_jobs:
        value = dict(row)
        settings = json.loads(value.pop("settings_json"))
        if value["project_id"] != project_id or value["run_id"] != run_id:
            raise RuntimeError(f"Isolated image ledger contains another run's job; refusing global worker pickup: {value}.")
        if value["job_id"] == resume_held_job_id:
            if value["status"] != "completed" or not value["prompt_id"] or not value["output_asset_id"]:
                raise RuntimeError("Held original is no longer a completed, persisted image candidate.")
        elif value["status"] != "queued" or value["prompt_id"] is not None:
            raise RuntimeError(f"Automatic master queue contains submitted/nonqueued work; refusing to continue: {value}.")
        expected_prior.append({**value, "settings": settings})
    # Reuse the original, independently validated unsent handoff. Rebuilding
    # after an audited input repair conflicts with the persisted request keys.
    if not expected_prior:
        api._advance_production_text_controller(project_id, run_id)
    refreshed = api._production_v2_ledger().get_run(project_id=project_id, run_id=run_id)
    queued_events = [event for event in refreshed.get("events", [])
        if event.get("event_type") == "controller_image_masters_queued"
        and event.get("payload", {}).get("shot_plan_revision_id") == loaded["shot_plans"]["revision_id"]]
    if len(queued_events) != 1:
        raise RuntimeError(f"Expected one controller automatic-master enqueue event; found {len(queued_events)}.")
    pending = queued_events[0].get("payload", {}).get("pending", [])
    identities = [(row.get("role"), row.get("entity_id")) for row in pending]
    if not pending or len(identities) != len(set(identities)):
        raise RuntimeError(f"Controller did not produce a nonempty unique identity master queue: {pending!r}.")
    if expected_prior and {row["batch_id"] for row in expected_prior} != {row["batch_id"] for row in pending}:
        raise RuntimeError("Existing queued masters do not match the original controller enqueue event; refusing duplicate/ambiguous work.")
    candidates = []
    held_original = None
    canon = api.read_project_canon(api.PROJECT_STORE.root_dir, project_id)
    for item in pending:
        batch = image_store.list_batch(project_id=project_id, batch_id=item["batch_id"])
        jobs = batch.get("jobs", [])
        if len(jobs) != 1:
            raise RuntimeError(f"Expected exactly one candidate in {item['batch_id']}; got {jobs!r}.")
        job = jobs[0]
        if job["job_id"] == resume_held_job_id:
            held_original = job
            continue
        if job.get("status") != "queued":
            raise RuntimeError(f"Expected remaining controller candidate {job['job_id']} queued; got {job['status']}.")
        if job.get("prompt_id") is not None or job.get("settings", {}).get("controller_shot_plan_revision_id") != loaded["shot_plans"]["revision_id"]:
            raise RuntimeError(f"Queued master {job['job_id']} is submitted or bound to a different shot plan.")
        identity_kind, identity_key = (("characters", "character_id") if item["role"] == "character_master"
            else ("worlds", "world_id"))
        entity = next((row for row in canon[identity_kind] if row.get(identity_key) == item["entity_id"]), None)
        if entity is None:
            raise RuntimeError(f"Queued master identity {item!r} is absent from persisted canon.")
        candidates.append({"batch_id": item["batch_id"], "job_id": job["job_id"],
            "candidate_index": job["candidate_index"], "created_at": job["created_at"],
            "workflow_id": job["workflow_id"],
            "role": item["role"], "entity_id": item["entity_id"],
            "display_name": entity.get("display_name") or item["entity_id"]})
    candidates.sort(key=lambda row: (row["created_at"], row["candidate_index"]))
    with image_store._connect() as db:
        after_jobs = db.execute("SELECT job_id,batch_id,project_id,run_id,status,prompt_id "
            "FROM production_image_jobs ORDER BY created_at,job_id").fetchall()
    expected_ids = {row["job_id"] for row in candidates}
    if resume_held_job_id:
        expected_ids.add(resume_held_job_id)
    if {row["job_id"] for row in after_jobs} != expected_ids or any(
            (row["job_id"] == resume_held_job_id and row["status"] != "completed")
            or (row["job_id"] != resume_held_job_id and
                (row["status"] != "queued" or row["prompt_id"] is not None)) for row in after_jobs):
        raise RuntimeError("Controller queue does not exactly equal the unique unsent automatic-master candidates.")
    prefix = {"project_id": project_id, "run_id": run_id,
        "story_revision_id": loaded["story_detail"]["revision_id"],
        "scene_revision_id": loaded["scenes"]["revision_id"],
        "dialogue_revision_id": loaded["dialogue"]["revision_id"],
        "visual_revision_id": loaded["visual_briefs"]["revision_id"],
        "shot_plan_revision_id": loaded["shot_plans"]["revision_id"],
        "shot_plan_task_id": by_stage["text:shot_plans"]["task_id"],
        "targeted_resume_result": str(result_path), "targeted_resume_outcome": outcome}
    if held_original:
        prefix["held_original"] = held_original
    return prefix, candidates


def identity_snapshot(api_url: str, project_id: str, run_id: str, batch_id: str) -> dict[str, Any]:
    run = api_get(f"{api_url}/api/projects/{project_id}/production/v2/runs/{run_id}")
    batch = api_get(f"{api_url}/api/projects/{project_id}/production/v2/image-jobs/{batch_id}")
    assets = api_get(f"{api_url}/api/projects/{project_id}/production/v2/assets?kind=image&limit=100")
    tasks = run.get("stage_tasks", [])
    return {"run_id": run["run_id"], "image_batch": batch,
        "assets": [{"asset_id": row["asset_id"], "sha256": row.get("sha256"),
            "roles": sorted(row.get("roles", [])), "metadata": row.get("metadata", {})}
            for row in assets.get("assets", [])],
        "controller_tasks": [{"task_id": row["task_id"], "stage": row["stage"],
            "status": row["status"], "request": row.get("request"), "result": row.get("result")}
            for row in tasks if row.get("stage", "").startswith("controller:")]}


def classify_resume_state(jobs: list[dict[str, Any]], *, held_job_id: str,
                          held_review: dict[str, Any]) -> dict[str, Any]:
    """Validate a held completed original and return only its unsent siblings.

    This is deliberately a pure gate: it never changes the immutable original
    review or any image-job row. A corrected retake must be a new child job.
    """
    by_id = {str(row.get("job_id")): row for row in jobs}
    if len(by_id) != len(jobs) or held_job_id not in by_id:
        raise RuntimeError("Resume ledger has duplicate jobs or is missing the held original.")
    held = by_id[held_job_id]
    decision = held_review.get("decision") if isinstance(held_review, dict) else None
    if (held.get("status") != "completed" or not held.get("prompt_id")
            or not held.get("output_asset_id")
            or held_review.get("resolution_status") != "blocked"
            or not isinstance(decision, dict) or decision.get("action") != "blocked"):
        raise RuntimeError("Resume requires the original completed image and its immutable blocked Director review.")
    for key in ("job_id", "project_id", "run_id", "asset_id"):
        expected = held.get("output_asset_id") if key == "asset_id" else held.get(key)
        if held_review.get(key) != expected:
            raise RuntimeError(f"Persisted blocked review does not match held original {key}.")
    budget = int((held.get("settings") or {}).get("full_retake_budget", 0))
    used = int((held.get("settings") or {}).get("retake_index", 0))
    if budget < 1 or used >= budget:
        raise RuntimeError("Held original has no remaining saved retake budget.")
    queued = []
    for row in jobs:
        if row["job_id"] == held_job_id:
            continue
        if row.get("status") != "queued" or row.get("prompt_id") is not None or row.get("output_asset_id") is not None:
            raise RuntimeError(f"Resume found nonqueued/submitted/recovery work; refusing dispatch: {row.get('job_id')}.")
        queued.append(row)
    if not queued:
        raise RuntimeError("Resume found no remaining original controller masters to process.")
    queued.sort(key=lambda row: (row.get("created_at", ""), int(row.get("candidate_index", 0))))
    return {"preserved_held_job_id": held_job_id,
        "preserved_review_resolution": held_review["resolution_status"],
        "remaining_retake_budget": budget - used,
        "queued_original_job_ids": [row["job_id"] for row in queued]}


def operator_retake_idempotency_key(parent_job_id: str, retake_index: int) -> str:
    if not parent_job_id or retake_index < 1:
        raise ValueError("Operator retake requires a parent job and positive saved retake index.")
    return f"operator-correction-retake-{parent_job_id}-{retake_index}"


def resolve_accepted_visual_for_shot_plan(api, *, project_id: str, run_id: str,
                                          shot_plan_task_id: str,
                                          shot_plan_revision_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Resolve a visual revision by the completed shot-plan task's pinned context.

    Stage revision source_revision_id is the accepted story revision for both
    visual briefs and shot plans. The task request context carries the direct
    visual-brief-to-shot-plan edge.
    """
    rows = api._production_stage_task_store().list_run(project_id=project_id, run_id=run_id)
    matching_shot_tasks = [row for row in rows if row.get("stage") == "text:shot_plans"
        and row.get("task_id") == shot_plan_task_id
        and row.get("status") == "completed"
        and (row.get("result") or {}).get("revision_id") == shot_plan_revision_id]
    if len(matching_shot_tasks) != 1:
        raise ValueError("Accepted shot-plan revision must resolve to exactly one completed persisted task.")
    shot_task = matching_shot_tasks[0]
    shot_request = shot_task.get("request") or {}
    context = shot_request.get("context") if isinstance(shot_request.get("context"), dict) else {}
    visual_id = str(context.get("visual_brief_revision_id") or "")
    source_story_id = str(shot_request.get("source_revision_id") or "")
    if not visual_id or not source_story_id:
        raise ValueError("Shot-plan task is missing its accepted visual-brief/story request pins.")
    matching_visual_tasks = [row for row in rows if row.get("stage") == "text:visual_briefs"
        and row.get("status") == "completed"
        and (row.get("result") or {}).get("revision_id") == visual_id]
    if len(matching_visual_tasks) != 1:
        raise ValueError("Shot-plan visual pin must resolve to exactly one completed visual-brief task.")
    visual_task = matching_visual_tasks[0]
    if str((visual_task.get("request") or {}).get("source_revision_id") or "") != source_story_id:
        raise ValueError("Accepted visual-brief task does not share the shot plan's accepted story request pin.")

    story_tasks = [row for row in rows if row.get("stage") == "story_detail"
        and row.get("status") == "completed"
        and (row.get("result") or {}).get("revision_id") == source_story_id]
    if len(story_tasks) != 1:
        raise ValueError("Accepted story revision must resolve to exactly one completed persisted task.")
    story = api.production_story_revisions.load_revision(api.OUTPUT_ROOT, project_id, run_id, source_story_id)
    visual = api.production_story_revisions.load_stage_revision(api.OUTPUT_ROOT,
        project_id, run_id, "visual_briefs", visual_id)
    shot_plan = api.production_story_revisions.load_stage_revision(api.OUTPUT_ROOT,
        project_id, run_id, "shot_plans", shot_plan_revision_id)
    if not story or story.get("review_status") != "accepted":
        raise ValueError("Pinned story revision is missing or not accepted.")
    source_hash = str(story.get("source_hash") or "")
    for label, revision, expected_stage in (("visual brief", visual, "visual_briefs"),
            ("shot plan", shot_plan, "shot_plans")):
        if (not revision or revision.get("revision_id") is None
                or revision.get("project_id") != project_id or revision.get("run_id") != run_id
                or revision.get("review_status") != "accepted" or revision.get("stage") != expected_stage
                or revision.get("source_revision_id") != source_story_id
                or not source_hash or revision.get("source_story_hash") != source_hash):
            raise ValueError(f"Pinned accepted {label} revision has mismatched story lineage or source hash.")
    return visual, shot_plan, {"shot_plan_task_id": shot_task["task_id"],
        "visual_brief_task_id": visual_task["task_id"],
        "story_revision_id": source_story_id, "source_story_hash": source_hash}


def enqueue_operator_correction_child(api, store, *, parent: dict[str, Any],
                                      correction: str, shot_plan_task_id: str,
                                      actor: str = "human_operator") -> dict[str, Any]:
    """Create an idempotent new child from current accepted canon/visual guidance.

    The original job and its blocked review remain untouched. The prompt is
    rebuilt through the current controller prompt builder instead of appending
    to a stale original prompt that may contain rejected typography guidance.
    """
    correction = correction.strip()
    if not correction or len(correction) > 1000:
        raise ValueError("Operator correction must contain 1–1000 characters.")
    settings = parent.get("settings") or {}
    budget, used = int(settings.get("full_retake_budget", 0)), int(settings.get("retake_index", 0))
    next_index = used + 1
    if next_index > budget:
        raise ValueError("Operator correction exceeds the saved retake budget.")
    project_id, run_id = parent["project_id"], parent["run_id"]
    run = api._production_v2_ledger().get_run(project_id=project_id, run_id=run_id)
    revision_id = str(settings.get("controller_shot_plan_revision_id") or "")
    if not revision_id:
        raise ValueError("Held master has no accepted shot-plan revision lineage.")
    visual, shot_plan, lineage = resolve_accepted_visual_for_shot_plan(api,
        project_id=project_id, run_id=run_id, shot_plan_task_id=shot_plan_task_id,
        shot_plan_revision_id=revision_id)
    identity = settings.get("review_identity") or {}
    role, entity_id = parent["asset_role"], str(identity.get("entity_id") or "")
    canon = api.read_project_canon(api.PROJECT_STORE.root_dir, project_id)
    collection, id_key = (("characters", "character_id") if role == "character_master"
        else ("worlds", "world_id"))
    entity = next((row for row in canon.get(collection, []) if row.get(id_key) == entity_id), None)
    if not entity:
        raise ValueError("Held master identity is no longer present in saved canon.")
    guidance = api._build_controller_master_prompt(role, entity_id, entity, visual,
        str((run.get("config") or {}).get("visual_treatment") or "realistic"))
    prompt = f"{guidance['prompt']} {correction}"
    request_key = operator_retake_idempotency_key(parent["job_id"], next_index)
    material_hash = hashlib.sha256(f"{project_id}:{request_key}".encode()).hexdigest()[:24]
    workflow_id = str(parent["workflow_id"])
    compiled = api.compile_image_candidates(workflow_id=workflow_id, prompt=prompt,
        control_mode="fully_automated", seed=(int(parent["seed"]) + next_index) & 0xFFFFFFFF,
        width=settings.get("width"), height=settings.get("height"), steps=settings.get("steps"),
        cfg=settings.get("cfg"), output_prefix=f"{project_id}/production_image_jobs/{material_hash}",
        full_retake_budget=budget)
    next_settings = {**compiled["settings"], "source_asset_ids": [], "source_provenance": [],
        "staging_owner_id": None, "control_mode": "fully_automated", "director_review_required": True,
        "director_provider": settings.get("director_provider"), "review_identity": guidance["review_identity"],
        "approved_visual_design": guidance["approved_visual_design"],
        "visual_design_provenance": guidance["visual_design_provenance"],
        "full_retake_budget": budget, "retake_index": next_index,
        "parent_job_id": parent["job_id"], "controller_shot_plan_revision_id": revision_id,
        "controller_shot_plan_task_id": lineage["shot_plan_task_id"],
        "controller_visual_brief_revision_id": visual["revision_id"],
        "controller_visual_brief_task_id": lineage["visual_brief_task_id"],
        "controller_source_story_revision_id": lineage["story_revision_id"],
        "controller_source_story_hash": lineage["source_story_hash"],
        "operator_correction_sha256": hashlib.sha256(correction.encode()).hexdigest(),
        "operator_correction_actor": actor, "operator_correction_basis": "accepted_visual_repair"}
    batch = store.enqueue_batch(project_id=project_id, run_id=run_id,
        idempotency_key=request_key, workflow_id=compiled["workflow_id"],
        workflow_version=compiled["workflow_version"], asset_role=role,
        prompt=compiled["prompt"], settings=next_settings, candidates=compiled["candidates"])
    if len(batch.get("jobs", [])) != 1:
        raise RuntimeError("Corrected child enqueue did not return exactly one idempotent job.")
    child = batch["jobs"][0]
    if child.get("settings", {}).get("parent_job_id") != parent["job_id"]:
        raise RuntimeError("Corrected child lost its held original lineage.")
    return {"batch_id": batch["batch_id"], "job": child,
        "reused": bool(batch.get("reused")), "correction_sha256": hashlib.sha256(correction.encode()).hexdigest(),
        "accepted_shot_plan_revision_id": revision_id,
        "accepted_visual_revision_id": visual.get("revision_id"),
        "accepted_shot_plan_task_id": lineage["shot_plan_task_id"],
        "accepted_visual_task_id": lineage["visual_brief_task_id"],
        "held_original_review_preserved": True}


def validate_accepted_text_root_readonly(root: Path, expected_project_id: str | None = None,
                                         expected_run_id: str | None = None,
                                         resume_held_job_id: str | None = None,
                                         resume_persisted_masters: bool = False) -> dict[str, Any]:
    """Read-only gate for the separate provider run; this function never advances queues."""
    root = root.resolve()
    result_path = root / "targeted_resume_result.json"
    ledger_path = root / "storage" / "production" / "v2_ledger.sqlite3"
    output_root = root / "output"
    if not result_path.is_file() or not ledger_path.is_file() or not output_root.is_dir():
        raise RuntimeError("Accepted-text root lacks targeted_resume_result.json, its SQLite ledger, or output/.")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    outcome = result.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("outcome") != "passed" or outcome.get("stage") != "text:shot_plans":
        raise RuntimeError(f"Accepted-text precondition is not ready: targeted resume outcome is {outcome!r}.")
    project_id, run_id = str(result.get("project_id") or ""), str(result.get("run_id") or "")
    if not project_id or not run_id or (expected_project_id and project_id != expected_project_id) \
            or (expected_run_id and run_id != expected_run_id):
        raise RuntimeError("Accepted-text result has absent or mismatched project/run IDs.")
    db = sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        run_row = db.execute("SELECT config_json FROM production_runs WHERE project_id=? AND run_id=?",
            (project_id, run_id)).fetchone()
        if not run_row:
            raise RuntimeError("Accepted-text result refers to a missing persisted production run.")
        config = json.loads(run_row["config_json"])
        if config.get("control_mode") != "fully_automated" or config.get("making_route") != "reference_built":
            raise RuntimeError("Accepted-text run is not fully automated on the reference-built route.")
        task_rows = [dict(row) for row in db.execute(
            "SELECT * FROM production_stage_tasks WHERE project_id=? AND run_id=? ORDER BY created_at,task_id",
            (project_id, run_id)).fetchall()]
        for task in task_rows:
            for key in ("request_json", "result_json", "error_json"):
                raw = task.pop(key)
                task[key.removesuffix("_json")] = json.loads(raw) if raw else None
        active = [row for row in task_rows if row["status"] in {"queued", "running", "recovery_required"}]
        if active:
            raise RuntimeError(f"Accepted-text root still has active stage tasks: "
                f"{[(row['stage'], row['status'], row['task_id']) for row in active]}.")
        latest = {}
        for task in task_rows:
            if task["stage"] not in latest or (task["created_at"], task["task_id"]) > (
                    latest[task["stage"]]["created_at"], latest[task["stage"]]["task_id"]):
                latest[task["stage"]] = task

        from story_builder.services.production_story_revisions import load_revision, load_stage_revision
        required = {"story_detail": "story_detail", "text:scenes": "scenes",
            "text:dialogue": "dialogue", "text:visual_briefs": "visual_briefs",
            "text:shot_plans": "shot_plans"}
        reported = {row.get("stage"): row for row in result.get("revisions", []) if isinstance(row, dict)}
        revision_ids = {}
        for task_stage, revision_stage in required.items():
            task = latest.get(task_stage)
            revision_id = str((task.get("result") or {}).get("revision_id") or "") if task else ""
            row = reported.get(revision_stage)
            if not task or task["status"] != "completed" or not revision_id or not row \
                    or row.get("revision_id") != revision_id or row.get("review_status") != "accepted":
                raise RuntimeError(f"targeted_resume_result.json does not attest the latest completed accepted {revision_stage} revision.")
            revision = (load_revision(output_root, project_id, run_id, revision_id)
                if revision_stage == "story_detail" else load_stage_revision(output_root,
                    project_id, run_id, revision_stage, revision_id))
            if not revision or revision.get("review_status") != "accepted":
                raise RuntimeError(f"Persisted {revision_stage} revision {revision_id} is not accepted.")
            revision_ids[revision_stage] = revision_id

        if resume_persisted_masters:
            audit = audit_persisted_master_resume(root, project_id=project_id, run_id=run_id,
                shot_plan_revision_id=revision_ids["shot_plans"])
            return {"artifact_root": str(root), "project_id": project_id, "run_id": run_id,
                "accepted_revisions": revision_ids, "read_only": True,
                "preserved_job_ids": audit["preserved_job_ids"],
                "controller_queued_jobs": [{key: row[key] for key in ("job_id", "batch_id", "asset_role", "status", "prompt_id")}
                    for row in audit["leaves"]]}

        has_image_table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='production_image_jobs'").fetchone()
        image_rows = [dict(row) for row in db.execute(
            "SELECT job_id,batch_id,project_id,run_id,status,prompt_id,output_asset_id,asset_role,prompt,settings_json,created_at,candidate_index "
            "FROM production_image_jobs ORDER BY created_at,candidate_index").fetchall()] if has_image_table else []
        if not image_rows and not resume_held_job_id:
            # Text-only continuation intentionally stops before master enqueue.
            # Do not mutate/create schema in a read-only first-use preflight.
            prior_queue = db.execute("SELECT 1 FROM production_events WHERE project_id=? AND run_id=? "
                "AND event_type='controller_image_masters_queued' LIMIT 1", (project_id, run_id)).fetchone()
            prior_take = db.execute("SELECT 1 FROM production_takes WHERE project_id=? AND run_id=? LIMIT 1",
                (project_id, run_id)).fetchone()
            if prior_queue or prior_take:
                raise RuntimeError("Accepted-text run has prior media work but no image queue; reconcile it first.")
            return {"artifact_root": str(root), "project_id": project_id, "run_id": run_id,
                "outcome": outcome, "accepted_revisions": revision_ids,
                "controller_queued_jobs": [], "image_queue_not_prepared": True, "read_only": True}
        if not image_rows or any(row["project_id"] != project_id or row["run_id"] != run_id
                for row in image_rows):
            raise RuntimeError("Accepted-text image ledger is empty or contains foreign work.")
        held_job = None
        if resume_held_job_id:
            matches = [row for row in image_rows if row["job_id"] == resume_held_job_id]
            review_row = db.execute("SELECT * FROM production_image_director_reviews WHERE project_id=? AND job_id=?",
                (project_id, resume_held_job_id)).fetchone()
            if len(matches) != 1 or not review_row:
                raise RuntimeError("Resume held candidate or its persisted Director review is missing.")
            held_job = matches[0]
            held_review = dict(review_row)
            held_review["decision"] = json.loads(held_review.pop("decision_json"))
            classify_resume_state([{**row, "settings": json.loads(row["settings_json"])}
                for row in image_rows], held_job_id=resume_held_job_id, held_review=held_review)
            try:
                from story_builder.services.production_assets import get_asset_record
                asset = get_asset_record(root / "storage" / "projects", project_id,
                    str(held_job["output_asset_id"]))
                asset_path = (output_root / project_id / str(asset["relative_path"])).resolve()
                if not asset_path.is_relative_to((output_root / project_id).resolve()) or not asset_path.is_file():
                    raise RuntimeError("Held original's canonical output is missing or escaped its project root.")
                if hashlib.sha256(asset_path.read_bytes()).hexdigest() != asset.get("sha256"):
                    raise RuntimeError("Held original's canonical asset hash does not match its saved bytes.")
            except Exception as exc:
                raise RuntimeError(f"Cannot verify preserved held-original asset: {exc}") from exc
        allowed_statuses = {"queued"}
        if resume_held_job_id:
            allowed_statuses.add("completed")
        if any(row["status"] not in allowed_statuses
                or (row["job_id"] == resume_held_job_id and row["status"] != "completed")
                or (row["job_id"] != resume_held_job_id and row["prompt_id"] is not None)
                for row in image_rows):
            raise RuntimeError("Accepted-text image ledger contains submitted, recovery, or unexpected terminal work.")
        queued_events = []
        for event in db.execute("SELECT event_type,payload_json FROM production_events WHERE project_id=? AND run_id=?",
                                 (project_id, run_id)):
            if event["event_type"] == "controller_image_masters_queued":
                payload = json.loads(event["payload_json"])
                if payload.get("shot_plan_revision_id") == revision_ids["shot_plans"]:
                    queued_events.append(payload)
        if len(queued_events) != 1:
            raise RuntimeError(f"Expected one original controller queue event for accepted shot plan; found {len(queued_events)}.")
        pending = queued_events[0].get("pending", [])
        if {row["batch_id"] for row in image_rows} != {item.get("batch_id") for item in pending}:
            raise RuntimeError("Persisted queued jobs do not exactly match the original controller event.")
        visual = load_stage_revision(output_root, project_id, run_id, "visual_briefs",
            revision_ids["visual_briefs"])
        visual_items = [row for row in visual.get("items", []) if isinstance(row, dict)]
        identity_cues = {}
        def add_identity_cue(entity_id: str, role: str, design: str) -> None:
            cue = (role, design.strip())
            if not cue[1] or (entity_id in identity_cues and identity_cues[entity_id] != cue):
                raise RuntimeError(f"Accepted visual briefs contain empty or conflicting design cues for {entity_id}.")
            identity_cues[entity_id] = cue
        for item in visual_items:
            content = item.get("content") if isinstance(item.get("content"), dict) else {}
            continuity = content.get("continuity") if isinstance(content.get("continuity"), dict) else {}
            for design in continuity.get("visible_characters_and_animal", []):
                if isinstance(design, dict) and design.get("id") and design.get("proposed_design_choice"):
                    add_identity_cue(str(design["id"]), "character_master", str(design["proposed_design_choice"]))
            location = continuity.get("location") if isinstance(continuity.get("location"), dict) else {}
            if location.get("id") and location.get("identifier"):
                add_identity_cue(str(location["id"]), "world_master", str(location["identifier"]))
        for job in image_rows:
            if job["job_id"] == resume_held_job_id:
                continue
            settings = json.loads(job.pop("settings_json"))
            identity = settings.get("review_identity") or {}
            identity_id = str(identity.get("entity_id") or "")
            cue = identity_cues.get(identity_id)
            if not cue or cue[0] != job["asset_role"]:
                raise RuntimeError(f"Queued job {job['job_id']} has no matching approved visual identity cue.")
            if cue[1].casefold() not in job["prompt"].casefold():
                raise RuntimeError(f"Queued {job['job_id']} prompt drops the approved entity design cue: {cue[1]!r}.")
            forbidden_prompt_metadata = re.search(
                r"\b(?:entity|character|world|revision|source|visual_design)_?id\b|\bprovenance\b",
                job["prompt"], flags=re.IGNORECASE)
            if identity_id.casefold() in job["prompt"].casefold() or forbidden_prompt_metadata:
                raise RuntimeError(f"Queued {job['job_id']} prompt includes identity/revision provenance that could render as typography.")
    finally:
        db.close()
    return {"artifact_root": str(root), "project_id": project_id, "run_id": run_id,
        "outcome": outcome, "accepted_revisions": revision_ids,
        "controller_queued_jobs": [{key: row[key] for key in ("job_id", "batch_id", "asset_role", "status", "prompt_id")}
            for row in image_rows if row["job_id"] != resume_held_job_id],
        "preserved_held_original": ({"job_id": held_job["job_id"], "batch_id": held_job["batch_id"],
            "asset_id": held_job["output_asset_id"], "status": held_job["status"],
            "review_resolution": "blocked"} if held_job else None), "prompt_sha256_by_job": {row["job_id"]:
                hashlib.sha256(row["prompt"].encode()).hexdigest() for row in image_rows},
        "read_only": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-live", action="store_true",
        help="Opt in to one real saved-provider preflight, one ComfyUI image, and one real Director review.")
    parser.add_argument("--validate-accepted-text-root", action="store_true",
        help="Perform only the read-only passed/accepted persisted-text precondition check; never start workers or services.")
    parser.add_argument("--resume-persisted-masters", action="store_true",
        help="Resume exact saved controller master/retake chains, including already accepted leaves; never enqueue a correction.")
    parser.add_argument("--resume-held-job-id",
        help="Resume one accepted-text root while preserving this completed, blocked original master as an immutable record.")
    parser.add_argument("--operator-correction",
        help="Explicit bounded correction text for a new child retake; requires --resume-held-job-id and --execute-live.")
    parser.add_argument("--workflow", choices=("z_image_turbo", "qwen_image_2512"), default="z_image_turbo")
    parser.add_argument("--mode", choices=("full", "delegated-semi"), default="full")
    parser.add_argument("--artifact-parent", type=Path, default=Path(tempfile.gettempdir()))
    parser.add_argument("--accepted-text-root", type=Path,
        help="Reuse a persisted text-provider root only after targeted_resume_result.json attests accepted shot plans.")
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    args = parser.parse_args()
    if args.resume_persisted_masters and (not args.accepted_text_root or args.resume_held_job_id or args.operator_correction):
        parser.error("--resume-persisted-masters requires --accepted-text-root and excludes new correction arguments.")
    if args.validate_accepted_text_root:
        if not args.accepted_text_root:
            parser.error("--validate-accepted-text-root requires --accepted-text-root.")
        print(json.dumps(validate_accepted_text_root_readonly(args.accepted_text_root,
            resume_held_job_id=args.resume_held_job_id, resume_persisted_masters=args.resume_persisted_masters), ensure_ascii=False, indent=2))
        return 0
    if bool(args.resume_held_job_id) != bool(args.operator_correction):
        parser.error("--resume-held-job-id and --operator-correction must be supplied together.")
    if not args.execute_live:
        parser.error("This harness performs real provider/GPU work; pass --execute-live only after separate authorization and readiness checks.")
    if not 60 <= args.timeout_seconds <= 14400:
        parser.error("--timeout-seconds must be 60–14400")

    from story_builder.services.project_store import ProjectStore
    from story_builder.services.production_ledger import ProductionLedger
    from story_builder.services.production_image_jobs import ProductionImageJobStore
    from story_builder.services.production_assets import get_asset_record
    from story_builder.services import production_image_worker as image_worker_module
    import story_builder.api.main as api

    root = (args.accepted_text_root.resolve() if args.accepted_text_root else
        Path(tempfile.mkdtemp(prefix="story-builder-auto-image-acceptance-", dir=args.artifact_parent)).resolve())
    evidence_root = acceptance_evidence_root(root, resuming=bool(args.resume_held_job_id or args.resume_persisted_masters))
    if args.resume_held_job_id or args.resume_persisted_masters:
        evidence_root.mkdir(parents=True, exist_ok=False)
    storage, output = root / "storage", root / "output"
    if args.accepted_text_root and (not storage.is_dir() or not output.is_dir()):
        parser.error("--accepted-text-root must name an existing isolated root with storage/ and output/ directories.")
    api.STORAGE_ROOT = storage
    api.PROJECT_STORE = ProjectStore(storage / "projects")
    api.UPLOADS_ROOT = storage / "uploads"
    api.OUTPUT_ROOT = output
    api.AUDIO_LIBRARY_ROOT = storage / "audio_library"
    api.COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:3008")
    image_worker_module.DEFAULT_TELEMETRY_PATH = evidence_root / "gpu-telemetry.jsonl"
    batch_path = storage / "production" / "v2_ledger.sqlite3"
    initial_store = ProductionImageJobStore(batch_path)
    accepted_prefix: dict[str, Any] | None = None
    if args.accepted_text_root:
        accepted_prefix, candidates = prepare_accepted_text_run(api, root,
            resume_held_job_id=args.resume_held_job_id, resume_persisted_masters=args.resume_persisted_masters)
        project_id, run_id = accepted_prefix["project_id"], accepted_prefix["run_id"]
        run = api._production_v2_ledger().get_run(project_id=project_id, run_id=run_id)
        canon = api.read_project_canon(api.PROJECT_STORE.root_dir, project_id)
        for candidate in candidates:
            queued = initial_store.get_job(project_id=project_id, job_id=candidate["job_id"])
            candidate["workflow_version"] = queued["workflow_version"]
            candidate["seed"] = queued["seed"]
            candidate["settings"] = queued["settings"]
            with initial_store._connect() as db:
                graph_row = db.execute("SELECT graph_json FROM production_image_jobs WHERE project_id=? AND job_id=?",
                    (project_id, candidate["job_id"])).fetchone()
            candidate["graph_sha256"] = hashlib.sha256(json.dumps(json.loads(graph_row["graph_json"]), sort_keys=True).encode()).hexdigest()
            candidate["prompt_sha256"] = hashlib.sha256(queued["prompt"].encode()).hexdigest()
            candidate["source_asset_ids"] = queued["settings"].get("source_asset_ids", [])
            candidate["source_provenance"] = queued["settings"].get("source_provenance", [])
        if args.resume_held_job_id:
            held = accepted_prefix.get("held_original")
            if not held or held.get("job_id") != args.resume_held_job_id:
                raise RuntimeError("Read-only resume audit did not return the requested held original.")
            review = initial_store.get_director_review(project_id=project_id, job_id=args.resume_held_job_id)
            if not review or review.get("resolution_status") != "blocked":
                raise RuntimeError("Held original no longer has the audited immutable blocked review.")
            child = enqueue_operator_correction_child(api, initial_store, parent=held,
                correction=args.operator_correction,
                shot_plan_task_id=accepted_prefix["shot_plan_task_id"])
            child_job = child["job"]
            identity = child_job.get("settings", {}).get("review_identity") or {}
            with initial_store._connect() as db:
                child_graph = db.execute("SELECT graph_json FROM production_image_jobs WHERE project_id=? AND job_id=?",
                    (project_id, child_job["job_id"])).fetchone()
            if not child_graph:
                raise RuntimeError("Persisted corrected child lost its private workflow graph.")
            candidates.append({"batch_id": child["batch_id"], "job_id": child_job["job_id"],
                "candidate_index": child_job["candidate_index"], "created_at": child_job["created_at"],
                "workflow_id": child_job["workflow_id"], "workflow_version": child_job["workflow_version"],
                "seed": child_job["seed"], "settings": child_job["settings"],
                "graph_sha256": hashlib.sha256(json.dumps(json.loads(child_graph["graph_json"]), sort_keys=True).encode()).hexdigest(),
                "prompt_sha256": hashlib.sha256(child_job["prompt"].encode()).hexdigest(),
                "source_asset_ids": [], "source_provenance": [],
                "role": child_job["asset_role"], "entity_id": identity.get("entity_id"),
                "display_name": identity.get("display_name") or identity.get("entity_id"),
                "operator_correction_child": True})
            accepted_prefix["operator_correction_child"] = {
                "batch_id": child["batch_id"], "job_id": child_job["job_id"],
                "reused": child["reused"], "correction_sha256": child["correction_sha256"],
                "held_original_review_preserved": True}
            candidates.sort(key=lambda row: (row["created_at"], row["candidate_index"]))
        fixture_scope = {"accepted_text_source": str(root / "targeted_resume_result.json"),
            "text_and_canon": "real persisted provider stages and saved canon; no seeded revisions or new project"}
    else:
        project = api.PROJECT_STORE.create_project(title="Disposable automatic master acceptance",
            story_input="Mira waits at the station entrance while the late train approaches. The image master must preserve Mira's saved identity and grounded costume description.",
            automation_mode=False)
        project_id = project["id"]
        character_result = asyncio.run(api.create_project_character_identity(project_id,
            api.ProductionCanonCharacterCreateRequest(display_name="Mira Acceptance")))
        character = character_result["character"]
        canon = asyncio.run(api.get_project_production_canon(project_id))
        characters = [{**row, "appearance": "A young adult with short dark hair, a mustard raincoat and a calm, observant expression.",
            "description": "Mira is the central character waiting at a station."} if row["character_id"] == character["character_id"] else row
            for row in canon["characters"]]
        asyncio.run(api.put_project_production_canon(project_id, api.ProductionCanonSaveRequest(
            expected_revision=canon["revision"], characters=characters, worlds=canon["worlds"], actor="acceptance_setup")))
        semi_gates = {"story_review": False, "image_candidate_selection": False,
            "shot_workflow_render_approval": False, "voice_selection": True} if args.mode == "delegated-semi" else {}
        run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
            idempotency_key="auto-image-acceptance-v1", control_mode="fully_automated" if args.mode == "full" else "semi",
            making_route="reference_built", image_workflow_id=args.workflow, semi_gates=semi_gates)))
        seeded = seed_accepted_controller(api, project_id, run, character["character_id"])
        queued = initial_store.get_job(project_id=project_id, job_id=seeded["job_id"])
        with initial_store._connect() as db:
            graph_row = db.execute("SELECT graph_json FROM production_image_jobs WHERE project_id=? AND job_id=?",
                (project_id, queued["job_id"])).fetchone()
        candidates = [{"job_id": queued["job_id"], "batch_id": queued["batch_id"],
            "candidate_index": queued["candidate_index"], "workflow_id": queued["workflow_id"],
            "workflow_version": queued["workflow_version"], "seed": queued["seed"],
            "settings": queued["settings"], "graph_sha256": hashlib.sha256(
                json.dumps(json.loads(graph_row["graph_json"]), sort_keys=True).encode()).hexdigest(),
            "prompt_sha256": hashlib.sha256(queued["prompt"].encode()).hexdigest(),
            "source_asset_ids": queued["settings"].get("source_asset_ids", []),
            "source_provenance": queued["settings"].get("source_provenance", []),
            "role": "character_master", "entity_id": character["character_id"],
            "display_name": character["display_name"]}]
        run_id = run["run_id"]
        fixture_scope = {"seeded_accepted_stage_fixtures": seeded,
            "text_and_canon": "accepted story/scene/dialogue/visual/shot-plan revisions are fixture-seeded"}
    report: dict[str, Any] = {"scope": "controller-owned automatic identity masters; not full C2 gate",
        "artifact_root": str(root), "evidence_root": str(evidence_root),
        "project_id": project_id, "run_id": run_id,
        "mode": "persisted-provider-prefix" if accepted_prefix else args.mode,
        "saved_control_mode": run["config"]["control_mode"],
        "saved_semi_gates": run["config"].get("semi_gates", {}),
        "workflow_id": run["config"].get("image_workflow_id"),
        "accepted_prefix": accepted_prefix, **fixture_scope,
        "consumers": {"text": ("disabled; real accepted provider stages are preserved" if accepted_prefix
                else "disabled; stage fixtures are preaccepted"), "audio": "disabled",
            "video": "disabled", "image": "only explicitly serialized ProductionImageWorker calls"},
        "mocked_or_substituted": ([] if accepted_prefix else ["accepted story/scene/dialogue/visual/shot-plan revisions only"]),
        "provider_inference": "real saved run provider CPU preflight and real Director review; no substitute",
        "media": "real ComfyUI graph/model/inference/output; no fixture media",
        "gpu_admission": {"shared_path": "comfy_submission_guard inside ProductionImageWorker",
            "temperature_cutoff_c": 83, "graphics_clock_ceiling_mhz": 2100,
            "max_concurrent_image_workloads": 1}, "queued_candidates": candidates,
        "started_at": time.time(), "status": "prepared"}
    (evidence_root / "acceptance-plan.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"ARTIFACT_ROOT={root}", flush=True)
    print(f"EVIDENCE_ROOT={evidence_root}", flush=True)
    print("PREPARED_CANDIDATES=" + json.dumps(report["queued_candidates"], sort_keys=True), flush=True)

    api_port, vite_port = free_port(), free_port()
    api_url, vite_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{vite_port}"
    api_log_path, vite_log_path, browser_log_path = (evidence_root / name for name in
        ("api-process.log", "vite.log", "playwright.log"))
    api_process = vite = None
    exit_code = 1
    try:
        api_log = api_log_path.open("w", encoding="utf-8")
        api_process = subprocess.Popen([sys.executable, str(ROOT / "tests" / "persisted_acceptance_api_server.py"),
            "--storage", str(storage), "--output", str(output), "--port", str(api_port)],
            cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT.parent),
                "COMFYUI_URL": "http://127.0.0.1:1"}, text=True, stdout=api_log, stderr=subprocess.STDOUT)
        api_log.close()
        vite_log = vite_log_path.open("w", encoding="utf-8")
        vite = subprocess.Popen(["npm", "run", "dev", "--", "--host", "127.0.0.1",
            "--port", str(vite_port), "--strictPort"], cwd=FRONTEND,
            env={**os.environ, "VITE_BACKEND_TARGET": api_url}, text=True,
            stdout=vite_log, stderr=subprocess.STDOUT)
        vite_log.close()
        wait_http(f"{api_url}/api/projects", api_process)
        wait_http(vite_url, vite)
        # This temporary API starts with lifespan=off: no text, audio, video or
        # image consumers are started. The sole image worker is invoked below.
        browser_env = {**os.environ, "PLAYWRIGHT_BASE_URL": vite_url,
            "IMAGE_MASTER_ACCEPTANCE_PROJECT_ID": project_id,
            "IMAGE_MASTER_ACCEPTANCE_RUN_ID": run_id,
            "IMAGE_MASTER_ACCEPTANCE_EXPECTED_ASSETS": json.dumps([
                {key: candidate[key] for key in ("batch_id", "job_id", "role", "entity_id", "display_name")}
                for candidate in candidates], ensure_ascii=False)}
        for candidate in candidates:
            status_before = api_get(f"{api_url}/api/projects/{project_id}/production/v2/image-jobs/{candidate['batch_id']}")
            http_jobs = status_before.get("jobs", [])
            expected_status = "completed" if candidate.get("status") == "accepted" else candidate.get("status", "queued")
            if (len(http_jobs) != 1 or http_jobs[0]["job_id"] != candidate["job_id"]
                    or http_jobs[0]["status"] != expected_status):
                raise AssertionError(f"HTTP batch status did not expose the saved controller candidate {candidate['job_id']}.")
            if candidate.get("status") == "accepted":
                http_review = http_jobs[0].get("director_review") or {}
                if (http_review.get("resolution_status") != "accepted"
                        or (http_review.get("decision") or {}).get("action") != "accept"
                        or http_review.get("asset_id") != candidate.get("output_asset_id")):
                    raise AssertionError("HTTP readback lost an accepted master review.")

        # No API or browser route stubs. Process one queued candidate and its
        # saved Director review on this serialized main thread only.
        worker = api._make_production_image_supervisor().worker
        worker.timeout_seconds = args.timeout_seconds
        generated_rows, review_rows, monitoring_rows = [], [], []
        telemetry_path = evidence_root / "gpu-telemetry.jsonl"
        def save_progress() -> None:
            report["worker_results"] = generated_rows
            report["director_results"] = review_rows
            report["gpu_monitoring_by_job"] = monitoring_rows
            (evidence_root / "acceptance-progress.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        for candidate in candidates:
            if candidate.get("status") == "accepted":
                generated_rows.append({"status": "completed", "job_id": candidate["job_id"],
                    "asset_id": candidate["output_asset_id"], "reused_accepted": True})
                review_rows.append({"status": "accepted", "job_id": candidate["job_id"],
                    "asset_id": candidate["output_asset_id"], "reused_accepted": True})
                save_progress()
                continue
            generated = worker.process_one()
            generated_rows.append(generated)
            print("WORKER_RESULT=" + json.dumps(generated, sort_keys=True), flush=True)
            save_progress()
            if generated.get("status") != "completed" or generated.get("job_id") != candidate["job_id"]:
                raise RuntimeError(f"Expected the next queued master {candidate['job_id']} to complete; preserved outcome: {generated}")
            telemetry = [json.loads(line) for line in telemetry_path.read_text(encoding="utf-8").splitlines()
                if line.strip()] if telemetry_path.exists() else []
            owned_samples = [row for row in telemetry if row.get("workload_id") == candidate["job_id"]]
            if not owned_samples or not any(row.get("phase") == "render" for row in owned_samples):
                raise AssertionError(f"Actual worker did not retain render telemetry for {candidate['job_id']}.")
            gpu_points = [row.get("gpu") for row in owned_samples if isinstance(row.get("gpu"), dict)]
            temperatures = [float(point["temperature_c"]) for point in gpu_points if point.get("temperature_c") is not None]
            clocks = [float(point["graphics_clock_mhz"]) for point in gpu_points if point.get("graphics_clock_mhz") is not None]
            if not temperatures or not clocks:
                raise AssertionError(f"Owned worker telemetry lacks temperature/clock for {candidate['job_id']}.")
            peak_temperature, peak_clock = max(temperatures), max(clocks)
            if peak_temperature >= 83 or peak_clock > 2100:
                raise AssertionError(f"GPU limit violation for {candidate['job_id']}: {peak_temperature} C / {peak_clock} MHz.")
            monitoring_rows.append({"job_id": candidate["job_id"], "telemetry_path": str(telemetry_path),
                "sample_count": len(owned_samples), "phases": sorted(set(row.get("phase") for row in owned_samples)),
                "measured_gpu_point_count": len(gpu_points), "peak_temperature_c": peak_temperature,
                "peak_graphics_clock_mhz": peak_clock, "temperature_cutoff_c": 83,
                "graphics_clock_ceiling_mhz": 2100})
            save_progress()
            review = worker.review_next_candidate()
            review_rows.append(review)
            print("DIRECTOR_RESULT=" + json.dumps(review, sort_keys=True), flush=True)
            save_progress()
            if review.get("status") != "accepted" or review.get("job_id") != candidate["job_id"]:
                raise RuntimeError(f"Director did not accept {candidate['job_id']}; retake/other outcome preserved and no next master submitted: {review}")
            candidate["output_asset_id"] = review.get("asset_id")
        save_progress()

        # Re-open each disk-backed store before proving the controller readback.
        reopened = ProductionImageJobStore(batch_path)
        saved_jobs = [reopened.get_job(project_id=project_id, job_id=candidate["job_id"])
            for candidate in candidates]
        saved_reviews = [reopened.get_director_review(project_id=project_id, job_id=row["job_id"]) for row in saved_jobs]
        if any(row["status"] != "completed" or not review
                or review.get("resolution_status") != "accepted"
                or (review.get("decision") or {}).get("action") != "accept"
                or review.get("asset_id") != row.get("output_asset_id")
                for row, review in zip(saved_jobs, saved_reviews, strict=True)):
            raise AssertionError("Reconstructed image store lacks completed renders with matching accepted reviews.")
        api._advance_production_text_controller(project_id, run_id)
        api._advance_production_text_controller(project_id, run_id)
        reopened_tasks = api.ProductionStageTaskStore(batch_path).list_run(project_id=project_id, run_id=run_id)
        resolved = [row for row in reopened_tasks if row.get("stage") == "controller:resolved_shot_prompt"]
        if len(resolved) != 1:
            raise AssertionError(f"Expected one idempotent controller prompt-preparation task, found {len(resolved)}.")
        if resolved[0]["status"] != "queued":
            raise AssertionError(f"Expected child prompt preparation queued for browser readback, got {resolved[0]['status']}.")
        assets_http = api_get(f"{api_url}/api/projects/{project_id}/production/v2/assets?kind=image&limit=100")
        accepted_assets = []
        for candidate, saved_job, generated in zip(candidates, saved_jobs, generated_rows, strict=True):
            matching = [asset for asset in assets_http.get("assets", [])
                if asset.get("asset_id") == saved_job.get("output_asset_id")]
            if len(matching) != 1 or candidate["role"] not in matching[0].get("roles", []):
                raise AssertionError(f"Asset registry/status API did not return accepted {candidate['role']}.")
            asset = matching[0]
            metadata_identity = asset.get("metadata", {}).get("character_id" if candidate["role"] == "character_master" else "world_id")
            if metadata_identity != candidate["entity_id"]:
                raise AssertionError(f"Registered master lost canon identity {candidate['entity_id']}.")
            if generated.get("asset_id") != asset["asset_id"]:
                raise AssertionError("Worker output ID and persisted registry asset ID disagree.")
            private_record = get_asset_record(api.PROJECT_STORE.root_dir, project_id, asset["asset_id"])
            relative_path = Path(private_record["relative_path"])
            media_path = (output / project_id / relative_path).resolve()
            project_output = (output / project_id).resolve()
            if not media_path.is_relative_to(project_output) or not media_path.is_file():
                raise AssertionError("Persisted registry path does not resolve to an owned generated media file.")
            output_sha256 = hashlib.sha256(media_path.read_bytes()).hexdigest()
            if output_sha256 != asset.get("sha256"):
                raise AssertionError("Generated media bytes do not match the canonical registry SHA-256.")
            accepted_assets.append({"asset_id": asset["asset_id"], "job_id": candidate["job_id"],
                "batch_id": candidate["batch_id"], "role": candidate["role"],
                "entity_id": candidate["entity_id"], "display_name": candidate["display_name"],
                "asset_sha256": asset.get("sha256"), "output_sha256": output_sha256,
                "output_relative_path": relative_path.as_posix()})
        report["accepted_assets"] = accepted_assets
        report["controller_readback"] = {"prompt_task_id": resolved[0]["task_id"],
            "prompt_task_count": len(resolved), "status": resolved[0]["status"],
            "replay_count": 2, "accepted_master_count": len(accepted_assets),
            "accepted_assets": accepted_assets}
        browser_env["IMAGE_MASTER_ACCEPTANCE_EXPECTED_ASSETS"] = json.dumps([
            {key: row[key] for key in ("asset_id", "job_id", "batch_id", "role", "entity_id", "display_name")}
            for row in accepted_assets], ensure_ascii=False)
        (evidence_root / "acceptance-plan.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        with browser_log_path.open("w", encoding="utf-8") as browser_log:
            browser = subprocess.run([str(FRONTEND / "node_modules/.bin/playwright"), "test",
                "e2e/production-image-master-acceptance.spec.ts", "--config=playwright.config.ts",
                "--output", str(evidence_root / "playwright-artifacts")],
                cwd=FRONTEND, env=browser_env, text=True, stdout=browser_log,
                stderr=subprocess.STDOUT, timeout=120, check=False)
        exit_code = browser.returncode
        report["browser_exit_code"] = exit_code
        report["browser_log"] = str(browser_log_path)
        report["status"] = "passed" if exit_code == 0 else "failed"
        report["completed_at"] = time.time()
        (evidence_root / "acceptance-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(browser_log_path.read_text(encoding="utf-8", errors="replace"), end="", flush=True)
        print(f"RESULT_ARTIFACT={evidence_root / 'acceptance-result.json'}", flush=True)
        return exit_code
    except Exception as exc:
        report["status"] = "failed"
        report["failure"] = f"{type(exc).__name__}: {exc}"
        report["completed_at"] = time.time()
        result_path = evidence_root / "acceptance-result.json"
        result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"FAILURE={report['failure']}", flush=True)
        print(f"RESULT_ARTIFACT={result_path}", flush=True)
        return exit_code
    finally:
        stop_owned(api_process)
        stop_owned(vite)


if __name__ == "__main__":
    raise SystemExit(main())
