import pytest
from types import SimpleNamespace
from uuid import uuid4

from scripts.acceptance_automatic_image_master import (
    acceptance_evidence_root,
    classify_resume_state,
    operator_retake_idempotency_key,
)
from story_builder.services.production_image_jobs import ProductionImageJobStore
from story_builder.services.production_ledger import LedgerConflict
from story_builder.services.production_stage_tasks import ProductionStageTaskStore
from story_builder.services import production_story_revisions
from story_builder.api import main as api


def _held_and_queued():
    held = {"job_id": "original", "project_id": "project", "run_id": "run",
        "status": "completed", "prompt_id": "comfy-1", "output_asset_id": "asset-1",
        "created_at": "1", "candidate_index": 1,
        "settings": {"full_retake_budget": 2, "retake_index": 0}}
    queued = {"job_id": "queued", "project_id": "project", "run_id": "run",
        "status": "queued", "prompt_id": None, "output_asset_id": None,
        "created_at": "2", "candidate_index": 1, "settings": {}}
    review = {"job_id": "original", "project_id": "project", "run_id": "run",
        "asset_id": "asset-1", "resolution_status": "blocked",
        "decision": {"action": "blocked", "reason": "Original remains held."}}
    return held, queued, review


def test_resume_audit_preserves_completed_blocked_original_and_selects_only_unsent_sibling():
    held, queued, review = _held_and_queued()
    plan = classify_resume_state([held, queued], held_job_id="original", held_review=review)
    assert plan == {"preserved_held_job_id": "original",
        "preserved_review_resolution": "blocked", "remaining_retake_budget": 2,
        "queued_original_job_ids": ["queued"]}


@pytest.mark.parametrize("change", [
    {"status": "recovery_required", "prompt_id": "comfy-2"},
    {"status": "queued", "output_asset_id": "unexpected-asset"},
])
def test_resume_audit_fails_closed_for_submitted_or_partially_completed_sibling(change):
    held, queued, review = _held_and_queued()
    queued.update(change)
    with pytest.raises(RuntimeError, match="Resume found"):
        classify_resume_state([held, queued], held_job_id="original", held_review=review)


def test_resume_audit_requires_review_identity_to_match_original():
    held, queued, review = _held_and_queued()
    review["asset_id"] = "other-asset"
    with pytest.raises(RuntimeError, match="does not match held original"):
        classify_resume_state([held, queued], held_job_id="original", held_review=review)


def test_corrected_child_key_is_parent_and_saved_attempt_bound_and_conflicts_on_changed_correction(tmp_path):
    held, _queued, _review = _held_and_queued()
    key = operator_retake_idempotency_key(held["job_id"], 1)
    assert key == operator_retake_idempotency_key(held["job_id"], 1)
    store = ProductionImageJobStore(tmp_path / "image-ledger.sqlite3")
    settings = {"parent_job_id": held["job_id"], "retake_index": 1, "full_retake_budget": 2}
    first = store.enqueue_batch(project_id="project", run_id="run", idempotency_key=key,
        workflow_id="z_image_turbo", workflow_version="1", asset_role="character_master",
        prompt="Clean canon master. Show pale collar.", settings=settings,
        candidates=[{"seed": 8, "graph": {"node": {"class_type": "test", "inputs": {}}}}])
    replay = store.enqueue_batch(project_id="project", run_id="run", idempotency_key=key,
        workflow_id="z_image_turbo", workflow_version="1", asset_role="character_master",
        prompt="Clean canon master. Show pale collar.", settings=settings,
        candidates=[{"seed": 8, "graph": {"node": {"class_type": "test", "inputs": {}}}}])
    assert replay["reused"] is True
    assert replay["batch_id"] == first["batch_id"]
    assert len(replay["jobs"]) == 1
    with pytest.raises(LedgerConflict, match="different inputs"):
        store.enqueue_batch(project_id="project", run_id="run", idempotency_key=key,
            workflow_id="z_image_turbo", workflow_version="1", asset_role="character_master",
            prompt="Different correction at same saved attempt.", settings=settings,
            candidates=[{"seed": 8, "graph": {"node": {"class_type": "test", "inputs": {}}}}])
    with store._connect() as db:
        assert db.execute("SELECT count(*) FROM production_image_jobs").fetchone()[0] == 1


def test_resume_evidence_uses_unique_child_without_moving_persisted_artifact_root(tmp_path):
    source_root = tmp_path / "accepted-provider-root"
    source_root.mkdir()
    (source_root / "acceptance-result.json").write_text("original held result")
    (source_root / "storage").mkdir()
    (source_root / "output").mkdir()

    first = acceptance_evidence_root(source_root, resuming=True, run_token="run-a")
    second = acceptance_evidence_root(source_root, resuming=True, run_token="run-b")
    ordinary = acceptance_evidence_root(source_root, resuming=False)

    assert first != second
    assert first.parent == source_root / "automatic-image-resume-evidence"
    assert ordinary == source_root
    assert (source_root / "storage").is_dir()
    assert (source_root / "output").is_dir()
    assert (source_root / "acceptance-result.json").read_text() == "original held result"


def _complete_stage_task(store, *, project_id, run_id, stage, request, revision_id):
    task = store.enqueue(project_id=project_id, run_id=run_id, stage=stage,
        idempotency_key=f"{stage}-{uuid4().hex}", request=request)
    owner = f"test-{uuid4().hex}"
    assert store.claim(task_id=task["task_id"], owner_token=owner)
    return store.complete(task_id=task["task_id"], owner_token=owner,
        result={"revision_id": revision_id, "revision_stage": stage})


def test_operator_retake_helper_uses_shot_task_visual_pin_and_real_revision_lineage(tmp_path):
    from scripts.acceptance_automatic_image_master import enqueue_operator_correction_child

    project_id, run_id = "resume-helper-project", str(uuid4())
    output_root = tmp_path / "output"
    storage_root = tmp_path / "storage"
    db_path = storage_root / "production" / "v2_ledger.sqlite3"
    tasks = ProductionStageTaskStore(db_path)
    story_id, visual_id, shot_id = (
        "story-canon-aaaaaaaaaaaa", "visual_briefs-bbbbbbbbbbbb", "shot_plans-cccccccccccc")
    story_hash = "a" * 64
    story = {"revision_id": story_id, "project_id": project_id, "run_id": run_id,
        "stage": "story_detail", "review_status": "accepted", "source_hash": story_hash}
    visual = {"revision_id": visual_id, "project_id": project_id, "run_id": run_id,
        "stage": "visual_briefs", "review_status": "accepted", "source_revision_id": story_id,
        "source_story_hash": story_hash, "items": [{"unit_id": "visual-1", "content": {
            "continuity": {"visible_characters_and_animal": [{"id": "character-1",
                "identity": "Mira", "proposed_design_choice": "Dark rain jacket with pale collar"}]}}}]}
    shot = {"revision_id": shot_id, "project_id": project_id, "run_id": run_id,
        "stage": "shot_plans", "review_status": "accepted", "source_revision_id": story_id,
        "source_story_hash": story_hash, "items": []}
    production_story_revisions.write_revision(output_root, project_id, run_id, story)
    production_story_revisions.write_stage_revision(output_root, project_id, run_id,
        "visual_briefs", visual)
    production_story_revisions.write_stage_revision(output_root, project_id, run_id,
        "shot_plans", shot)
    _complete_stage_task(tasks, project_id=project_id, run_id=run_id,
        stage="story_detail", request={}, revision_id=story_id)
    _complete_stage_task(tasks, project_id=project_id, run_id=run_id,
        stage="text:visual_briefs", request={"source_revision_id": story_id}, revision_id=visual_id)
    shot_task = _complete_stage_task(tasks, project_id=project_id, run_id=run_id,
        stage="text:shot_plans", request={"source_revision_id": story_id,
            "context": {"visual_brief_revision_id": visual_id}}, revision_id=shot_id)

    # A later completed visual revision is deliberately not the shot plan's pin.
    other_visual_id = "visual_briefs-dddddddddddd"
    other_visual = {**visual, "revision_id": other_visual_id,
        "items": [{"unit_id": "visual-other", "content": {"continuity": {
            "visible_characters_and_animal": [{"id": "character-1", "identity": "Mira",
                "proposed_design_choice": "Bright blue spacesuit"}]}}}]}
    production_story_revisions.write_stage_revision(output_root, project_id, run_id,
        "visual_briefs", other_visual)
    _complete_stage_task(tasks, project_id=project_id, run_id=run_id,
        stage="text:visual_briefs", request={"source_revision_id": story_id}, revision_id=other_visual_id)

    captured = {}
    class EnqueueSpy:
        def enqueue_batch(self, **kwargs):
            captured.update(kwargs)
            return {"batch_id": "child-batch", "reused": False, "jobs": [{
                "job_id": "child-job", "batch_id": "child-batch", "candidate_index": 1,
                "created_at": "now", "workflow_id": kwargs["workflow_id"],
                "workflow_version": kwargs["workflow_version"], "asset_role": kwargs["asset_role"],
                "seed": kwargs["candidates"][0]["seed"], "settings": kwargs["settings"],
                "prompt": kwargs["prompt"]}]}

    entity = {"character_id": "character-1", "display_name": "Mira",
        "appearance": "Dark rain jacket and pale collar", "description": "A young adult"}
    fake_api = SimpleNamespace(
        _production_v2_ledger=lambda: SimpleNamespace(get_run=lambda **_kw: {"config": {"visual_treatment": "realistic"}}),
        _production_stage_task_store=lambda: tasks,
        production_story_revisions=production_story_revisions,
        OUTPUT_ROOT=output_root,
        PROJECT_STORE=SimpleNamespace(root_dir=storage_root / "projects"),
        read_project_canon=lambda *_args: {"characters": [entity], "worlds": []},
        _build_controller_master_prompt=api._build_controller_master_prompt,
        compile_image_candidates=api.compile_image_candidates)
    parent = {"job_id": "original-job", "project_id": project_id, "run_id": run_id,
        "asset_role": "character_master", "workflow_id": "z_image_turbo", "seed": 55,
        "settings": {"controller_shot_plan_revision_id": shot_id, "full_retake_budget": 2,
            "retake_index": 0, "review_identity": {"entity_id": "character-1"}}}

    result = enqueue_operator_correction_child(fake_api, EnqueueSpy(), parent=parent,
        correction="Remove graphic overlays. Keep the collar visible.",
        shot_plan_task_id=shot_task["task_id"])

    assert result["accepted_visual_revision_id"] == visual_id
    assert result["accepted_shot_plan_revision_id"] == shot_id
    assert "Dark rain jacket with pale collar" in captured["prompt"]
    assert "Bright blue spacesuit" not in captured["prompt"]
    assert "Remove graphic overlays. Keep the collar visible." in captured["prompt"]
    assert captured["settings"]["parent_job_id"] == "original-job"
    assert captured["settings"]["retake_index"] == 1
    assert captured["settings"]["full_retake_budget"] == 2
    assert captured["settings"]["controller_shot_plan_task_id"] == shot_task["task_id"]
    assert captured["settings"]["controller_visual_brief_revision_id"] == visual_id
    assert captured["settings"]["controller_source_story_revision_id"] == story_id
    assert captured["settings"]["controller_source_story_hash"] == story_hash


def _persisted_master_chain():
    from copy import deepcopy
    original = {"job_id": "original", "batch_id": "batch-original", "project_id": "project",
        "run_id": "run", "status": "completed", "prompt_id": "prompt-1", "output_asset_id": "asset-1",
        "asset_role": "character_master", "workflow_id": "z_image_turbo", "prompt": "Solo reference.",
        "candidate_index": 1, "created_at": "1", "settings": {"full_retake_budget": 2,
            "retake_index": 0, "review_identity": {"entity_id": "character"},
            "controller_shot_plan_revision_id": "shots"}}
    delta = "Show only one person."
    child = {**deepcopy(original), "job_id": "child", "batch_id": "batch-child",
        "status": "queued", "prompt_id": None, "output_asset_id": None, "created_at": "3",
        "prompt": "Solo reference.\n\nDirector correction: " + delta,
        "idempotency_key": "director-retake-original-1",
        "settings": {**deepcopy(original["settings"]), "parent_job_id": "original", "retake_index": 1}}
    world = {**deepcopy(original), "job_id": "world", "batch_id": "batch-world", "status": "queued",
        "prompt_id": None, "output_asset_id": None, "created_at": "2", "asset_role": "world_master",
        "settings": {**deepcopy(original["settings"]), "review_identity": {"entity_id": "world"}}}
    review = {"job_id": "original", "project_id": "project", "run_id": "run", "asset_id": "asset-1",
        "resolution_status": "retake_queued", "retake_batch_id": "batch-child",
        "decision": {"action": "retake", "prompt_delta": delta}}
    pending = [{"batch_id": "batch-original", "role": "character_master", "entity_id": "character"},
        {"batch_id": "batch-world", "role": "world_master", "entity_id": "world"}]
    return [original, world, child], {"original": review}, pending


def _classify_persisted(jobs, reviews, pending):
    from scripts.acceptance_automatic_image_master import classify_persisted_master_jobs
    return classify_persisted_master_jobs(jobs, reviews, pending, project_id="project", run_id="run",
        shot_plan_revision_id="shots")


def test_persisted_resume_selects_saved_children_in_queue_order_without_mutating_parents():
    from copy import deepcopy
    jobs, reviews, pending = _persisted_master_chain()
    before = deepcopy((jobs, reviews, pending))
    assert [row["job_id"] for row in _classify_persisted(jobs, reviews, pending)] == ["world", "child"]
    assert (jobs, reviews, pending) == before


def test_persisted_resume_reuses_accepted_leaf_and_retains_other_queued_identity():
    jobs, reviews, pending = _persisted_master_chain()
    jobs[2].update(status="accepted", prompt_id="prompt-2", output_asset_id="asset-2")
    reviews["child"] = {"job_id": "child", "project_id": "project", "run_id": "run", "asset_id": "asset-2",
        "resolution_status": "accepted", "decision": {"action": "accept"}}
    leaves = _classify_persisted(jobs, reviews, pending)
    assert [(row["job_id"], row["status"]) for row in leaves] == [("world", "queued"), ("child", "accepted")]


@pytest.mark.parametrize("mutation", ["foreign", "missing-parent", "wrong-identity", "budget", "index",
    "prompt", "key", "review-batch", "submitted", "duplicate-child", "unreviewed", "held-leaf"])
def test_persisted_resume_rejects_ambiguous_or_changed_durable_chain(mutation):
    from copy import deepcopy
    jobs, reviews, pending = _persisted_master_chain()
    child = jobs[2]
    if mutation == "foreign": child["run_id"] = "foreign"
    elif mutation == "missing-parent": child["settings"]["parent_job_id"] = "unknown"
    elif mutation == "wrong-identity": child["settings"]["review_identity"]["entity_id"] = "other"
    elif mutation == "budget": child["settings"]["full_retake_budget"] = 3
    elif mutation == "index": child["settings"]["retake_index"] = 3
    elif mutation == "prompt": child["prompt"] = "Changed correction"
    elif mutation == "key": child["idempotency_key"] = "different-key"
    elif mutation == "review-batch": reviews["original"]["retake_batch_id"] = "other"
    elif mutation == "submitted": child["prompt_id"] = "uncertain-prompt"
    elif mutation == "duplicate-child": jobs.append({**deepcopy(child), "job_id": "duplicate"})
    elif mutation == "unreviewed": reviews.clear()
    elif mutation == "held-leaf": jobs.pop()
    with pytest.raises(RuntimeError): _classify_persisted(jobs, reviews, pending)


def test_persisted_resume_requires_parent_bound_operator_correction_for_blocked_history():
    jobs, reviews, pending = _persisted_master_chain()
    reviews["original"].update(resolution_status="blocked", decision={"action": "blocked"}, retake_batch_id=None)
    jobs[2]["idempotency_key"] = operator_retake_idempotency_key("original", 1)
    jobs[2]["settings"]["operator_correction_sha256"] = __import__("hashlib").sha256(b"Show only one person.").hexdigest()
    assert [row["job_id"] for row in _classify_persisted(jobs, reviews, pending)] == ["world", "child"]
    jobs[2]["idempotency_key"] = operator_retake_idempotency_key("other-parent", 1)
    with pytest.raises(RuntimeError): _classify_persisted(jobs, reviews, pending)


def test_resume_audit_reopens_real_store_and_verifies_immutable_prior_media(tmp_path):
    import hashlib
    from PIL import Image
    from scripts.acceptance_automatic_image_master import audit_persisted_master_resume
    from story_builder.services.production_ledger import ProductionLedger
    from story_builder.services.production_assets import register_output
    project_id = "resume-sqlite"
    db_path = tmp_path / "storage" / "production" / "v2_ledger.sqlite3"
    ledger = ProductionLedger(db_path)
    run_id = ledger.create_run(project_id=project_id, idempotency_key="run", config={})["run_id"]
    store = ProductionImageJobStore(db_path)
    settings = {"full_retake_budget": 2, "retake_index": 0,
        "review_identity": {"entity_id": "person-1"}, "controller_shot_plan_revision_id": "shot_plans-cccccccccccc"}
    batch = store.enqueue_batch(project_id=project_id, run_id=run_id, idempotency_key="original",
        workflow_id="z_image_turbo", workflow_version="1", asset_role="character_master",
        prompt="Old master", settings=settings, candidates=[{"seed": 8, "graph": {}}])
    original = batch["jobs"][0]
    image = tmp_path / "output" / project_id / "old.png"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (16, 16), (30, 50, 70)).save(image)
    asset = register_output(tmp_path / "storage" / "projects", tmp_path / "output", project_id,
        relative_path="old.png", role="image_candidate")
    assert store.next_queued()["job_id"] == original["job_id"]
    prompt_id = store.reserve_prompt_id(original["job_id"])
    store.transition(original["job_id"], "running", prompt_id=prompt_id)
    store.transition(original["job_id"], "completed", output_asset_id=asset["asset_id"])
    store.record_director_review(project_id=project_id, run_id=run_id, job_id=original["job_id"],
        asset_id=asset["asset_id"], decision={"action": "blocked"})
    store.resolve_director_review(job_id=original["job_id"], resolution_status="blocked")
    correction = "Show the pale collar."
    child = store.enqueue_batch(project_id=project_id, run_id=run_id,
        idempotency_key=operator_retake_idempotency_key(original["job_id"], 1),
        workflow_id="z_image_turbo", workflow_version="1", asset_role="character_master",
        prompt="Dark coat. " + correction, settings={**settings, "retake_index": 1,
            "parent_job_id": original["job_id"], "operator_correction_sha256": hashlib.sha256(correction.encode()).hexdigest()},
        candidates=[{"seed": 9, "graph": {}}])["jobs"][0]
    ledger.record_run_event(project_id=project_id, run_id=run_id, event_type="controller_image_masters_queued",
        payload={"shot_plan_revision_id": "shot_plans-cccccccccccc", "pending": [{"batch_id": batch["batch_id"],
            "role": "character_master", "entity_id": "person-1"}]})
    visual_id = "visual_briefs-bbbbbbbbbbbb"
    production_story_revisions.write_stage_revision(tmp_path / "output", project_id, run_id, "visual_briefs",
        {"revision_id": visual_id, "project_id": project_id, "run_id": run_id, "stage": "visual_briefs",
         "source_revision_id": "story-canon-aaaaaaaaaaaa", "review_status": "accepted",
         "items": [{"content": {"continuity": {"visible_characters_and_animal": [
            {"id": "person-1", "proposed_design_choice": "Dark coat"}]}}}]})
    tasks = ProductionStageTaskStore(db_path)
    _complete_stage_task(tasks, project_id=project_id, run_id=run_id, stage="text:shot_plans",
        revision_id="shot_plans-cccccccccccc", request={"source_revision_id": "story-canon-aaaaaaaaaaaa",
            "context": {"visual_brief_revision_id": visual_id}})
    before_job = store.get_job(project_id=project_id, job_id=original["job_id"])
    before_review = store.get_director_review(project_id=project_id, job_id=original["job_id"])
    audit = audit_persisted_master_resume(tmp_path, project_id=project_id, run_id=run_id,
        shot_plan_revision_id="shot_plans-cccccccccccc")
    assert [row["job_id"] for row in audit["leaves"]] == [child["job_id"]]
    reopened = ProductionImageJobStore(db_path)
    assert reopened.get_job(project_id=project_id, job_id=original["job_id"]) == before_job
    assert reopened.get_director_review(project_id=project_id, job_id=original["job_id"]) == before_review
    image.write_bytes(b"changed prior output")
    with pytest.raises(RuntimeError, match="canonical hash"):
        audit_persisted_master_resume(tmp_path, project_id=project_id, run_id=run_id,
            shot_plan_revision_id="shot_plans-cccccccccccc")


def test_persisted_resume_uses_completed_render_and_separate_accepted_review():
    from copy import deepcopy
    jobs, reviews, pending = _persisted_master_chain()
    jobs[2].update(status="completed", prompt_id="prompt-2", output_asset_id="asset-2")
    reviews["child"] = {"job_id": "child", "project_id": "project", "run_id": "run", "asset_id": "asset-2",
        "resolution_status": "accepted", "decision": {"action": "accept"}}
    before = deepcopy((jobs, reviews, pending))
    leaves = _classify_persisted(jobs, reviews, pending)
    assert [(row["job_id"], row["status"]) for row in leaves] == [("world", "queued"), ("child", "accepted")]
    assert (jobs, reviews, pending) == before
    reviews["child"]["asset_id"] = "wrong-asset"
    with pytest.raises(RuntimeError, match="exact persisted review"):
        _classify_persisted(jobs, reviews, pending)


def test_resume_reads_accepted_review_from_real_sqlite_completed_job(tmp_path):
    import json, sqlite3
    store = ProductionImageJobStore(tmp_path / "ledger.sqlite3")
    settings = {"controller_shot_plan_revision_id": "shots", "full_retake_budget": 2,
        "retake_index": 0, "review_identity": {"entity_id": "person"}}
    batch = store.enqueue_batch(project_id="project", run_id="run", idempotency_key="one",
        workflow_id="z_image_turbo", workflow_version="1", asset_role="character_master",
        prompt="One person", settings=settings, candidates=[{"seed": 1, "graph": {}}])
    job = batch["jobs"][0]
    assert store.next_queued()["job_id"] == job["job_id"]
    prompt_id = store.reserve_prompt_id(job["job_id"])
    store.transition(job["job_id"], "running", prompt_id=prompt_id)
    store.transition(job["job_id"], "completed", output_asset_id="asset")
    store.record_director_review(project_id="project", run_id="run", job_id=job["job_id"],
        asset_id="asset", decision={"action": "accept"})
    store.resolve_director_review(job_id=job["job_id"], resolution_status="accepted")
    reopened = ProductionImageJobStore(tmp_path / "ledger.sqlite3")
    saved = reopened.get_job(project_id="project", job_id=job["job_id"])
    assert saved["status"] == "completed"
    review = reopened.get_director_review(project_id="project", job_id=job["job_id"])
    leaves = _classify_persisted([saved], {job["job_id"]: review},
        [{"batch_id": batch["batch_id"], "role": "character_master", "entity_id": "person"}])
    assert leaves[0]["status"] == "accepted"
    assert reopened.get_job(project_id="project", job_id=job["job_id"])["status"] == "completed"
