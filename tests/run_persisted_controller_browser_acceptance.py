"""Isolated real-HTTP/SQLite/browser acceptance for controller retake replay.

Run from the repository root with the project environment and loopback access:
  PYTHONPATH=/home/riki/web_dev python tests/run_persisted_controller_browser_acceptance.py

Provider and ComfyUI consumers are disabled. The saved video decision is replayed
by the production worker against SQLite; deterministic fixture callbacks stand in
only for prepared prompt output and rendered media. The browser uses real project,
run, and asset APIs and does not intercept API routes.
"""
from __future__ import annotations

import os
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "app"
sys.path.insert(0, str(ROOT.parent))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_http(url: str, process: subprocess.Popen[str] | None = None) -> None:
    deadline = time.monotonic() + 30
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process and process.poll() is not None:
            raise RuntimeError(f"Vite exited early ({process.returncode}).")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # startup race only
            last_error = exc
        time.sleep(.2)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def start_api_process(port: int, storage: Path, output: Path, log_path: Path) -> subprocess.Popen[str]:
    log = log_path.open("a", encoding="utf-8")
    try:
        return subprocess.Popen([sys.executable, str(ROOT / "tests" / "persisted_acceptance_api_server.py"),
            "--storage", str(storage), "--output", str(output), "--port", str(port)],
            cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT.parent), "COMFYUI_URL": "http://127.0.0.1:1"},
            text=True, stdout=log, stderr=subprocess.STDOUT)
    finally:
        log.close()


def stop_owned_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def api_identity(api_url: str, project_id: str, run_id: str) -> dict:
    url = f"{api_url}/api/projects/{project_id}/production/v2/runs/{run_id}"
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.status == 200
        run = json.load(response)
    return {"run_id": run["run_id"], "status": run["status"], "takes": [
        {"take_id": row["take_id"], "job_id": row["job_id"], "shot_id": row["shot_id"],
         "status": row["status"], "parent_take_id": row.get("parent_take_id"),
         "prompt_preparation_task_id": (row.get("input_snapshot") or {}).get("prompt_preparation_task_id"),
         "director_review": row.get("director_review")}
        for row in run["takes"]]}


def wait_for_file(path: Path, process: subprocess.Popen[str], timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Playwright exited before restart gate ({process.returncode}).")
        if path.exists():
            return
        time.sleep(.05)
    raise RuntimeError(f"Timed out waiting for browser restart gate {path}.")


def main() -> int:
    from story_builder.services.project_store import ProjectStore
    from story_builder.services.production_ledger import ProductionLedger
    from story_builder.services.production_stage_tasks import ProductionStageTaskStore
    from story_builder.services.production_job_worker import ProductionJobWorker
    import story_builder.api.main as api

    root = Path(tempfile.mkdtemp(prefix="story-builder-persisted-browser-"))
    print(f"ARTIFACT_ROOT={root}", flush=True)
    storage = root / "storage"
    api.STORAGE_ROOT = storage
    api.PROJECT_STORE = ProjectStore(storage / "projects")
    api.UPLOADS_ROOT = storage / "uploads"
    api.OUTPUT_ROOT = root / "output"
    api.AUDIO_LIBRARY_ROOT = storage / "audio_library"
    api.COMFYUI_URL = "http://127.0.0.1:1"  # inert sentinel; no consumer is started

    project = api.PROJECT_STORE.create_project(title="Persisted controller acceptance",
        story_input="A courier crosses a station as rain begins.", automation_mode=False)
    project_id = project["id"]
    ledger_path = storage / "production" / "v2_ledger.sqlite3"
    ledger = ProductionLedger(ledger_path)
    tasks = ProductionStageTaskStore(ledger_path)
    run = ledger.create_run(project_id=project_id, idempotency_key="browser-acceptance-run-v1",
        config={"control_mode": "fully_automated", "making_route": "direct_h3",
            "production_type": "story_film", "provider": "codex", "full_retake_budget": 2,
            "source_story_hash": hashlib.sha256(project["story_input"].strip().encode()).hexdigest(),
            "director_profile": {"profile_version": "fixture-v1", "review_priorities": []}})
    run_id = run["run_id"]
    shot_plan_id = "shot_plans-abcdef123456"
    source_id = "fixture-source-take-001"
    source = ledger.queue_take(project_id=project_id, run_id=run_id, shot_id="shot-01",
        take_id=source_id, idempotency_key="source-take-v1",
        input_snapshot={"validation_request": {"prompt": "A courier crosses the station."},
            "shot_plan_revision_id": shot_plan_id})
    ledger.transition_take(project_id=project_id, take_id=source_id, status="submitting")
    prompt = ledger.reserve_prompt_id(project_id=project_id, take_id=source_id)["prompt_id"]
    ledger.bind_prompt_id(project_id=project_id, take_id=source_id, prompt_id=prompt)
    ledger.transition_take(project_id=project_id, take_id=source_id, status="collecting")
    ledger.set_take_outputs(project_id=project_id, take_id=source_id, outputs=[{
        "asset_id": "pa-0123456789abcdef", "kind": "video", "sha256": "a" * 64}])
    ledger.transition_take(project_id=project_id, take_id=source_id, status="needs_review")

    decision = {"schema_version": 1, "action": "retake", "confidence": .94,
        "reason": "Keep the courier centered.",
        "criteria": [{"name": "framing", "passed": False, "evidence": "Courier is left of frame."}],
        "prompt_delta": "Keep the courier centered in the frame."}
    claim = ledger.claim_next_director_video_review(owner_token="fixture-review-owner")
    assert claim and claim["take_id"] == source_id
    ledger.record_director_video_review(take=claim, decision=decision, owner_token="fixture-review-owner")
    ledger.release_director_video_review_claim(job_id=source["job_id"], owner_token="fixture-review-owner")

    # Model the durable, accepted fresh prompt task created by the bounded prep
    # worker. The video-review worker below replays the saved decision from SQLite.
    preparation = tasks.enqueue(project_id=project_id, run_id=run_id,
        stage="controller:resolved_shot_prompt", idempotency_key="retake-prep-v1",
        request={"shot_id": "shot-01", "director_retake_of_take_id": source_id,
            "shot_plan_revision_id": "shot-plans-fixture-v1"})
    claimed_task = tasks.claim(task_id=preparation["task_id"], owner_token="fixture-prompt-owner")
    assert claimed_task
    tasks.complete(task_id=preparation["task_id"], owner_token="fixture-prompt-owner",
        result={"accepted": True, "resolved_prompt": "A courier crosses the station. Keep the courier centered."})

    callback_calls: list[str] = []
    retake_id = "fixture-retake-take-002"
    def enqueue_retake(take: dict, saved_decision: dict) -> dict:
        callback_calls.append(saved_decision["reason"])
        assert tasks.get(project_id=project_id, run_id=run_id, task_id=preparation["task_id"])["status"] == "completed"
        return ledger.queue_take(project_id=project_id, run_id=run_id, shot_id="shot-01",
            take_id=retake_id, idempotency_key="fixture-retake-idempotency-v1",
            input_snapshot={"validation_request": {"prompt": "A courier crosses the station. Keep the courier centered."},
                "shot_plan_revision_id": shot_plan_id,
                "prompt_preparation_task_id": preparation["task_id"],
                "director_retake_of_take_id": source_id,
                "director_retake_root_take_id": source_id,
                "director_retake_decision_hash": __import__("hashlib").sha256(
                    __import__("json").dumps(saved_decision, sort_keys=True).encode()).hexdigest()[:16]})

    def make_review_worker(current: ProductionLedger) -> ProductionJobWorker:
        return ProductionJobWorker(current, comfy_url="http://127.0.0.1:1", prepare=lambda _: None,
            collect=lambda *_: [], cleanup=lambda _: None, resolve_video_output=lambda _: Path("unused"),
            director_video_review=lambda *_: (_ for _ in ()).throw(AssertionError("unexpected provider inference")),
            enqueue_director_retake=enqueue_retake)

    result = make_review_worker(ProductionLedger(ledger_path)).review_next_take()
    assert result["status"] == "retake_queued" and result["retake"]["take_id"] == retake_id
    assert callback_calls == [decision["reason"]]
    # Reopen again: the immutable saved decision is settled and cannot duplicate
    # inference, retake scheduling, or a second child.
    replay = make_review_worker(ProductionLedger(ledger_path)).review_next_take()
    assert replay["status"] == "idle"
    assert callback_calls == [decision["reason"]]

    ledger = ProductionLedger(ledger_path)
    ledger.transition_take(project_id=project_id, take_id=retake_id, status="submitting")
    retake_prompt = ledger.reserve_prompt_id(project_id=project_id, take_id=retake_id)["prompt_id"]
    ledger.bind_prompt_id(project_id=project_id, take_id=retake_id, prompt_id=retake_prompt)
    ledger.transition_take(project_id=project_id, take_id=retake_id, status="collecting")
    api.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    video_path = api.OUTPUT_ROOT / project_id / "fixture" / "accepted-retake.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
        "color=c=blue:s=32x32:d=1", "-an", "-c:v", "mpeg4", "-y", str(video_path)],
        check=True, capture_output=True, text=True)
    video_record = api.register_production_asset_output(api.PROJECT_STORE.root_dir, api.OUTPUT_ROOT,
        project_id, relative_path="fixture/accepted-retake.mp4", role="previous_cut_tail",
        metadata={"run_id": run_id, "shot_id": "shot-01", "take_id": retake_id})
    ledger.set_take_outputs(project_id=project_id, take_id=retake_id, outputs=[{
        "asset_id": video_record["asset_id"], "kind": "video", "sha256": video_record["sha256"]}])
    ledger.transition_take(project_id=project_id, take_id=retake_id, status="needs_review")
    accepted = ledger.accept_take(project_id=project_id, run_id=run_id, take_id=retake_id, actor="fixture_acceptance")
    assert accepted["accepted"] is True
    # Seed the controller's immutable accepted text outputs as real files and
    # completed stage-task rows. The next take itself is created only by the
    # production controller after it resolves the accepted retake lineage.
    story_id = "story-canon-012345abcdef"
    api.production_story_revisions.write_revision(api.OUTPUT_ROOT, project_id, run_id, {
        "revision_id": story_id, "project_id": project_id, "run_id": run_id,
        "source_hash": run["config"]["source_story_hash"], "review_status": "accepted",
        "expanded_story": project["story_input"], "chunks": [], "continuity_rules": []})
    def completed_task(stage: str, key: str, result_value: dict) -> dict:
        task = tasks.enqueue(project_id=project_id, run_id=run_id, stage=stage,
            idempotency_key=key, request={"source_revision_id": story_id})
        claimed = tasks.claim(task_id=task["task_id"], owner_token=f"fixture-{stage}")
        assert claimed
        return tasks.complete(task_id=task["task_id"], owner_token=f"fixture-{stage}", result=result_value)

    shot_units = [
        {"unit_id": "shot-01", "scene_id": "scene-01", "shot_outline": {"action": "Courier enters."}},
        {"unit_id": "shot-02", "scene_id": "scene-01", "shot_outline": {"action": "Courier crosses the station."}},
    ]
    completed_task("story_detail", "fixture-story-v1", {"revision_id": story_id})
    outline = tasks.enqueue(project_id=project_id, run_id=run_id, stage="controller:scene_outline",
        idempotency_key="fixture-outline-v1", request={"source_revision_id": story_id})
    assert tasks.claim(task_id=outline["task_id"], owner_token="fixture-outline")
    tasks.complete(task_id=outline["task_id"], owner_token="fixture-outline", result={
        "units": [{"unit_id": "scene-01", "shot_units": shot_units}]})
    scenes_revision = {"revision_id": "scenes-abcdef123456", "project_id": project_id,
        "run_id": run_id, "stage": "scenes", "source_revision_id": story_id,
        "source_story_hash": run["config"]["source_story_hash"], "review_status": "accepted",
        "items": [{"unit_id": "scene-01", "shot_units": shot_units,
            "content": {"shots": [{"unit_id": row["unit_id"], "beat": row["shot_outline"]["action"]}
                for row in shot_units]}}]}
    api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id, run_id, "scenes", scenes_revision)
    completed_task("text:scenes", "fixture-scenes-v1", {"revision_id": scenes_revision["revision_id"]})
    dialogue_revision = {"revision_id": "dialogue-abcdef123456", "project_id": project_id,
        "run_id": run_id, "stage": "dialogue", "source_revision_id": story_id,
        "source_story_hash": run["config"]["source_story_hash"], "review_status": "accepted",
        "items": [{"unit_id": row["unit_id"], "scene_id": "scene-01", "content": {"dialogue": []}}
            for row in shot_units]}
    api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id, run_id, "dialogue", dialogue_revision)
    completed_task("text:dialogue", "fixture-dialogue-v1", {"revision_id": dialogue_revision["revision_id"]})
    visual_revision = {"revision_id": "visual_briefs-abcdef123456", "project_id": project_id,
        "run_id": run_id, "stage": "visual_briefs", "source_revision_id": story_id,
        "source_story_hash": run["config"]["source_story_hash"], "review_status": "accepted",
        "items": [{"unit_id": "scene-01", "content": {"visual_brief": "Station entrance at dusk."}}]}
    api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id, run_id,
        "visual_briefs", visual_revision)
    completed_task("text:visual_briefs", "fixture-visual-v1", {"revision_id": visual_revision["revision_id"]})
    shot_plan = {"revision_id": shot_plan_id, "project_id": project_id, "run_id": run_id,
        "stage": "shot_plans", "source_revision_id": story_id,
        "source_story_hash": run["config"]["source_story_hash"], "review_status": "accepted",
        "items": [{"unit_id": "shot-01", "scene_id": "scene-01", "content": {
                "prompt": "A courier enters the station.", "duration_seconds": 5}},
            {"unit_id": "shot-02", "scene_id": "scene-01", "content": {
                "prompt": "A courier crosses the station.", "duration_seconds": 5}}]}
    api.production_story_revisions.write_stage_revision(api.OUTPUT_ROOT, project_id, run_id, "shot_plans", shot_plan)
    completed_task("text:shot_plans", "fixture-shot-plans-v1", {"revision_id": shot_plan_id})

    second_request = api.ProductionV2ShotValidateRequest(shot_plan_revision_id=shot_plan_id,
        prompt="A courier crosses the station.", videos=[{"asset_id": video_record["asset_id"],
            "role": "previous_cut_tail", "intent": "Continue from the accepted retake."}])
    current_config_hash = hashlib.sha256(json.dumps(run["config"], ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    preparation = tasks.enqueue(project_id=project_id, run_id=run_id,
        stage="controller:resolved_shot_prompt", idempotency_key="fixture-next-shot-prompt-v1",
        request={"shot_id": "shot-02", "shot_plan_revision_id": shot_plan_id,
            "predecessor_take_id": retake_id, "run_config_hash": current_config_hash,
            "validation_request": second_request.model_dump()})
    assert tasks.claim(task_id=preparation["task_id"], owner_token="fixture-next-prompt")
    prompt = second_request.prompt
    reference_map = {"videos": [{"asset_id": video_record["asset_id"], "role": "previous_cut_tail"}]}
    tasks.complete(task_id=preparation["task_id"], owner_token="fixture-next-prompt", result={
        "accepted": True, "prompt": prompt, "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest(),
        "resolved_validation_request": second_request.model_dump(), "reference_map": reference_map,
        "asset_fingerprints": {}})

    api.validate_production_v2_shot = lambda _project, _run, _shot, _request: {
        "validation_hash": "v" * 64, "reference_map": reference_map, "asset_fingerprints": {},
        "workflow_id": "minimax_h3_r2v_dynamic_v1", "workflow_version": "fixture",
        "workflow_readiness": {"available": True}}
    api._advance_production_text_controller(project_id, run_id)
    advanced_ledger = ProductionLedger(ledger_path)
    advanced_tasks = ProductionStageTaskStore(ledger_path)
    advanced = advanced_ledger.get_run(project_id=project_id, run_id=run_id)
    next_takes = [row for row in advanced["takes"] if row["shot_id"] == "shot-02"]
    assert len(next_takes) == 1 and next_takes[0]["status"] == "queued"
    next_id = next_takes[0]["take_id"]
    assert next_takes[0]["parent_take_id"] == retake_id
    assert next_takes[0]["input_snapshot"]["prompt_preparation_task_id"] == preparation["task_id"]
    api._production_v2_ledger = lambda: advanced_ledger
    api._production_stage_task_store = lambda: advanced_tasks
    api._advance_production_text_controller(project_id, run_id)
    replayed = ProductionLedger(ledger_path).get_run(project_id=project_id, run_id=run_id)
    assert [row["take_id"] for row in replayed["takes"] if row["shot_id"] == "shot-02"] == [next_id]

    api_port, vite_port = free_port(), free_port()
    api_url = f"http://127.0.0.1:{api_port}"
    api_log_path = root / "api-process.log"
    vite_log_path = root / "vite.log"
    browser_log_path = root / "playwright.log"
    api_process = start_api_process(api_port, storage, api.OUTPUT_ROOT, api_log_path)
    vite_log = vite_log_path.open("w", encoding="utf-8")
    vite = subprocess.Popen(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(vite_port), "--strictPort"],
        cwd=FRONTEND, env={**os.environ, "VITE_BACKEND_TARGET": f"http://127.0.0.1:{api_port}"},
        text=True, stdout=vite_log, stderr=subprocess.STDOUT)
    exit_code = 1
    browser_process = None
    ready_gate = root / "browser-ready-for-api-restart"
    continue_gate = root / "continue-browser-after-api-restart"
    restart_record: dict = {}
    try:
        wait_http(f"{api_url}/api/projects", api_process)
        wait_http(f"http://127.0.0.1:{vite_port}/", vite)
        before_identity = api_identity(api_url, project_id, run_id)
        assert [take["take_id"] for take in before_identity["takes"]].count(retake_id) == 1
        assert [take["take_id"] for take in before_identity["takes"]].count(next_id) == 1
        before_path = root / "before-restart-identity.json"
        before_path.write_text(json.dumps(before_identity, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        env = {**os.environ, "PLAYWRIGHT_BASE_URL": f"http://127.0.0.1:{vite_port}",
            "PERSISTED_ACCEPTANCE_PROJECT_ID": project_id, "PERSISTED_ACCEPTANCE_RUN_ID": run_id,
            "PERSISTED_ACCEPTANCE_ORIGINAL_TAKE_ID": source_id,
            "PERSISTED_ACCEPTANCE_RETAKE_TAKE_ID": retake_id,
            "PERSISTED_ACCEPTANCE_NEXT_TAKE_ID": next_id,
            "PERSISTED_ACCEPTANCE_RESTART_READY_FILE": str(ready_gate),
            "PERSISTED_ACCEPTANCE_RESTART_CONTINUE_FILE": str(continue_gate)}
        command = [str(FRONTEND / "node_modules/.bin/playwright"), "test",
            "e2e/production-persisted-controller.spec.ts", "--config=playwright.config.ts"]
        with browser_log_path.open("w", encoding="utf-8") as browser_log:
            browser_process = subprocess.Popen(command, cwd=FRONTEND, env=env, text=True,
                stdout=browser_log, stderr=subprocess.STDOUT)
            wait_for_file(ready_gate, browser_process)
            before_pid = api_process.pid
            stop_owned_process(api_process)
            api_process = start_api_process(api_port, storage, api.OUTPUT_ROOT, api_log_path)
            wait_http(f"{api_url}/api/projects", api_process)
            after_identity = api_identity(api_url, project_id, run_id)
            after_path = root / "after-restart-identity.json"
            after_path.write_text(json.dumps(after_identity, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            assert after_identity == before_identity, "persisted take identity changed across API process restart"
            assert [take["take_id"] for take in after_identity["takes"]].count(retake_id) == 1
            assert [take["take_id"] for take in after_identity["takes"]].count(next_id) == 1
            restart_record = {"first_api_pid": before_pid, "restarted_api_pid": api_process.pid,
                "before_identity_file": str(before_path), "after_identity_file": str(after_path),
                "identity_sha256_before": hashlib.sha256(before_path.read_bytes()).hexdigest(),
                "identity_sha256_after": hashlib.sha256(after_path.read_bytes()).hexdigest(),
                "identical": True}
            continue_gate.write_text("restarted\n", encoding="utf-8")
            exit_code = browser_process.wait(timeout=45)
        result_path = root / "result.json"
        result_path.write_text(json.dumps({"exit_code": exit_code, "project_id": project_id,
            "run_id": run_id, "source_take_id": source_id, "accepted_retake_id": retake_id,
            "automatic_next_take_id": next_id, "workflow_id_fixture": "minimax_h3_r2v_dynamic_v1",
            "provider_inference": "disabled; saved decision replay asserted callback was not invoked",
            "gpu_consumers": "disabled", "browser_test_log": str(browser_log_path),
            "vite_log": str(vite_log_path), "api_process_log": str(api_log_path),
            "api_process_restart": restart_record}, indent=2) + "\n", encoding="utf-8")
        print(browser_log_path.read_text(encoding="utf-8"), end="", flush=True)
        print(f"RESULT_ARTIFACT={result_path}", flush=True)
        return exit_code
    finally:
        if browser_process and browser_process.poll() is None:
            continue_gate.write_text("cleanup\n", encoding="utf-8")
            browser_process.terminate()
            try:
                browser_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                browser_process.kill()
        stop_owned_process(api_process)
        vite.terminate()
        try:
            vite.wait(timeout=5)
        except subprocess.TimeoutExpired:
            vite.kill()
        vite_log.close()
        if not (root / "result.json").exists():
            (root / "result.json").write_text(json.dumps({"exit_code": exit_code,
                "project_id": project_id, "run_id": run_id, "artifact_root": str(root),
                "vite_log": str(vite_log_path), "browser_test_log": str(browser_log_path),
                "api_process_log": str(api_log_path), "api_process_restart": restart_record}, indent=2) + "\n",
                encoding="utf-8")
            print(f"RESULT_ARTIFACT={root / 'result.json'}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
