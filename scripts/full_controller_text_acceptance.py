"""Text-only configured-provider acceptance; never starts media supervisors.

Run on the authorized host from the project root with PYTHONPATH=/home/riki/web_dev.
This proves text orchestration only, not HTTP/browser/media acceptance.
"""
from __future__ import annotations


def terminal_outcome(tasks, revisions):
    """Call after five seconds of unchanged durable state, allowing controller retries."""
    if not tasks or any(row["status"] in {"queued", "running"} for row in tasks):
        return None
    latest = {}
    for row in tasks:
        key = (row["stage"], (row.get("request") or {}).get("source_revision_id"))
        if key not in latest or (row.get("created_at", ""), row["task_id"]) > (
                latest[key].get("created_at", ""), latest[key]["task_id"]):
            latest[key] = row
    rows = list(latest.values())
    for row in rows:
        if row["status"] != "completed":
            return {"outcome": "held", "stage": row["stage"], "status": row["status"],
                    "error": row.get("error")}
        revision_id = (row.get("result") or {}).get("revision_id")
        if revision_id:
            revision = revisions.get(revision_id)
            if not revision or revision.get("review_status") != "accepted":
                return {"outcome": "held", "stage": row["stage"],
                        "status": "revision_missing_or_not_accepted", "revision_id": revision_id}
    if any(row["stage"] == "text:shot_plans" for row in rows):
        return {"outcome": "passed", "stage": "text:shot_plans"}
    return {"outcome": "held", "status": "controller_stalled_before_shot_plans"}


def write_terminal_result(root, result):
    """Atomically retain the last known outcome, including on interruption."""
    import json
    from pathlib import Path

    root = Path(root)
    target = root / "acceptance_result.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(target)
    return target


def main():
    import argparse
    import asyncio
    import json
    import os
    import sys
    import tempfile
    import threading
    import time
    import uuid
    from datetime import datetime, timezone
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Run one isolated, text-only configured-provider controller acceptance.")
    parser.add_argument("--model", required=True, choices=("gpt-6-sol", "gpt-6-luna"),
                        help="Pin the Codex model for this acceptance run.")
    args = parser.parse_args()
    # Set before importing the provider adapter; no stored application setting changes.
    os.environ["CODEX_REASONING_MODEL"] = args.model

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from story_builder.api import main as api
    from story_builder.services.project_store import ProjectStore
    from story_builder.services import reasoning_provider
    from fastapi import BackgroundTasks
    # An embedding caller may have imported the adapter before this CLI entry point.
    reasoning_provider.DEFAULT_CODEX_MODEL = args.model

    root = Path(tempfile.mkdtemp(prefix="storybuilder-full-controller-acceptance-20261006-"))
    api.STORAGE_ROOT = root / "storage"
    api.STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    api.PROJECT_STORE = ProjectStore(api.STORAGE_ROOT / "projects")
    api.UPLOADS_ROOT = api.STORAGE_ROOT / "uploads"
    api.OUTPUT_ROOT = root / "output"
    api.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    api.AUDIO_LIBRARY_ROOT = api.STORAGE_ROOT / "audio_library"
    api._production_story_task_stop = threading.Event()

    result = {"root": str(root), "provider": "codex", "model": args.model,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "outcome": {"outcome": "running"}}
    worker = None
    project_id = None
    run_id = None
    exit_code = 2
    try:
        print("ACCEPTANCE_START", json.dumps({"root": str(root), "provider": "codex",
              "model": args.model, "media_supervisors": False}), flush=True)
        smoke = reasoning_provider.test_provider("codex")
        result["provider_smoke"] = smoke
        print("PROVIDER_SMOKE", json.dumps(smoke), flush=True)

        story = ("Mira and Arun are siblings in a low-lying neighborhood during a sudden flood. "
                 "The rescue takes place inside the stairwell of their mother's apartment building. "
                 "Two neighbors wait there with a dog belonging to Mira and Arun's mother. "
                 "Mira wants to leave immediately; Arun insists they organize the neighbors first. "
                 "They coordinate a safe evacuation and leave together. Keep the story grounded and preserve these facts.")
        project = asyncio.run(api.create_project(api.ProjectCreateRequest(
            title="Disposable Full Controller Provider Resume Acceptance", story_input=story,
            automation_mode=False)))
        project_id = project["id"]
        run = asyncio.run(api.create_production_v2_run(project_id, api.ProductionV2RunRequest(
            idempotency_key="full-controller-provider-resume-20261006", control_mode="fully_automated",
            making_route="reference_built", image_workflow_id="z_image_turbo")))
        run_id = run["run_id"]
        result.update({"project_id": project_id, "run_id": run_id,
                      "run_provider": run["config"].get("provider"),
                      "run_model": run["config"].get("model")})
        print("PROJECT_RUN", json.dumps({"root": str(root), "project_id": project_id,
              "run_id": run_id, "provider": result["run_provider"],
              "model": args.model}), flush=True)
        request = api.ProductionV2StoryTaskRequest(idempotency_key="full-controller-story-20261006")
        api.enqueue_production_v2_story_task(project_id, run_id, request, BackgroundTasks())
        worker = threading.Thread(target=api._consume_production_story_stage_tasks,
            name="isolated-text-only-production-worker", daemon=False)
        worker.start()

        last = None
        unchanged_since = time.monotonic()
        outcome = None
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            tasks = api._production_stage_task_store().list_run(project_id=project_id, run_id=run_id)
            summary = [(row["stage"], row["status"], row.get("attempt_count"),
                        (row.get("error") or {}).get("code")) for row in tasks]
            if summary != last:
                print("TASKS", json.dumps(summary), flush=True)
                last = summary
                unchanged_since = time.monotonic()
            revisions = {}
            for row in tasks:
                revision_id = (row.get("result") or {}).get("revision_id")
                if revision_id:
                    if row["stage"] == "story_detail":
                        revision = api.production_story_revisions.load_revision(
                            api.OUTPUT_ROOT, project_id, run_id, revision_id)
                    else:
                        revision = api.production_story_revisions.load_stage_revision(
                            api.OUTPUT_ROOT, project_id, run_id,
                            row["stage"].split(":", 1)[-1], revision_id)
                    revisions[revision_id] = revision
            if time.monotonic() - unchanged_since >= 5:
                outcome = terminal_outcome(tasks, revisions)
                if outcome:
                    break
            time.sleep(1)
        result["outcome"] = outcome or {"outcome": "held", "status": "deadline_reached"}
        result["deadline_reached"] = time.monotonic() >= deadline
        exit_code = 0 if outcome and outcome["outcome"] == "passed" else 2
    except KeyboardInterrupt:
        result["outcome"] = {"outcome": "interrupted", "status": "operator_interrupt"}
        exit_code = 130
    except Exception as exc:
        result["outcome"] = {"outcome": "error", "error_type": type(exc).__name__,
                              "message": str(exc)[:1800]}
        exit_code = 2
    finally:
        api._production_story_task_stop.set()
        if worker is not None:
            while worker.is_alive():
                worker.join(timeout=30)
                if worker.is_alive():
                    print("SETTLING: waiting for owned provider call; do not restart or retry this run.",
                          flush=True)
        result["owned_worker_settled"] = worker is None or not worker.is_alive()
        if project_id and run_id:
            try:
                tasks = api._production_stage_task_store().list_run(project_id=project_id, run_id=run_id)
                result["tasks"] = [(row["stage"], row["status"], row.get("attempt_count"),
                                    row.get("error")) for row in tasks]
                accepted = []
                for row in tasks:
                    revision_id = (row.get("result") or {}).get("revision_id")
                    if not revision_id:
                        continue
                    if row["stage"] == "story_detail":
                        revision = api.production_story_revisions.load_revision(
                            api.OUTPUT_ROOT, project_id, run_id, revision_id)
                    else:
                        revision = api.production_story_revisions.load_stage_revision(
                            api.OUTPUT_ROOT, project_id, run_id,
                            row["stage"].split(":", 1)[-1], revision_id)
                    if revision:
                        accepted.append({"stage": row["stage"], "revision_id": revision_id,
                            "review_status": revision.get("review_status"),
                            "director_accepted": (revision.get("director_review") or {}).get("accepted")})
                result["revisions"] = accepted
            except Exception as exc:
                result["snapshot_error"] = f"{type(exc).__name__}: {exc}"[:1200]
                if result.get("outcome", {}).get("outcome") == "running":
                    result["outcome"] = {"outcome": "error", "status": "final_snapshot_failed"}
                    exit_code = 2
        if result.get("outcome", {}).get("outcome") == "running":
            result["outcome"] = {"outcome": "error", "status": "runner_exited_without_terminal_outcome"}
            exit_code = 2
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        path = write_terminal_result(root, result)
        print("ACCEPTANCE_RESULT", json.dumps({**result, "result_path": str(path)},
              ensure_ascii=False, default=str), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
