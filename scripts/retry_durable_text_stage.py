"""Run one reviewed durable text-stage attempt, stopping before controller advancement.

This is intentionally a narrow operator tool, not a replacement for the normal
controller worker. Dry-run is the default. Execution requires two explicit
flags because it sends the saved request to the configured provider and spends
one additional attempt beyond the controller's built-in retry.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any


def retry_idempotency_key(*, task_id: str, model: str) -> str:
    """Stable key: rerunning the tool cannot create a second operator attempt."""
    return f"stage-only:{task_id}:{model}:v1"


def validate_retry_history(tasks: list[dict[str, Any]], *, task_id: str,
                           key: str) -> dict[str, Any]:
    """Require exactly two terminal failed shot-plan attempts and no active work."""
    target = next((task for task in tasks if task.get("task_id") == task_id), None)
    if not target:
        raise ValueError("The requested task does not exist in this project/run.")
    if target.get("stage") != "text:shot_plans":
        raise ValueError("Only the durable text:shot_plans stage is supported.")
    siblings = [task for task in tasks if task.get("stage") == target["stage"]]
    if any(task.get("idempotency_key") == key for task in tasks):
        raise ValueError("The single stage-only retry key has already been used; inspect its result.")
    if any(task.get("status") in {"queued", "running", "recovery_required"} for task in tasks):
        raise ValueError("The run has queued, running, or recovery-required work; reconcile it first.")
    if len(siblings) != 2 or any(task.get("status") != "failed" for task in siblings):
        raise ValueError("Expected exactly two terminal failed shot-plan attempts; refusing another retry.")
    if max(siblings, key=lambda row: (row.get("created_at", ""), row.get("task_id", ""))) is not target:
        raise ValueError("The requested task is not the latest shot-plan attempt.")
    if any(not (task.get("error") or {}).get("retryable") for task in siblings):
        raise ValueError("A previous shot-plan attempt is not marked retryable.")
    if len({task.get("request_hash") for task in siblings}) != 1:
        raise ValueError("Failed shot-plan attempts do not share one exact saved request.")
    return target


def _require_api_stopped(port: int) -> None:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            pass
    except ConnectionRefusedError:
        return
    except OSError as exc:
        raise RuntimeError(f"Cannot verify the API is stopped on 127.0.0.1:{port}: {type(exc).__name__}.") from exc
    raise RuntimeError(f"Story Builder API is listening on 127.0.0.1:{port}; stop before stage-only execution.")


def settled_retry_outcome(task: dict[str, Any], revision: dict[str, Any] | None,
                          *, project_id: str, run_id: str, model: str) -> dict[str, Any]:
    """Task completion is generation, not Director acceptance of canonical bytes."""
    if task.get("status") != "completed":
        return {"outcome": "held", "reason": "task_not_completed"}
    result = task.get("result") or {}
    expected = {"project_id": project_id, "run_id": run_id, "stage": "shot_plans",
        "revision_id": result.get("revision_id"), "stage_task_id": task.get("task_id"),
        "stage_task_request_hash": task.get("request_hash"), "provider": "codex", "model": model}
    if (not revision or not expected["revision_id"]
            or any(revision.get(field) != value for field, value in expected.items())
            or result.get("provider") != "codex" or result.get("model") != model):
        return {"outcome": "held", "reason": "canonical_revision_or_provenance_mismatch"}
    if revision.get("review_status") != "accepted":
        return {"outcome": "held", "reason": "director_not_accepted",
            "review_status": revision.get("review_status")}
    return {"outcome": "passed", "review_status": "accepted"}


def _require_accepted_predecessors(api, project_id: str, run_id: str,
                                  task: dict[str, Any], all_tasks: list[dict[str, Any]]) -> None:
    request = task.get("request") or {}
    source_revision_id = request.get("source_revision_id")
    context = request.get("context") or {}
    if not isinstance(source_revision_id, str) or not source_revision_id:
        raise ValueError("Saved shot-plan request has no accepted story revision.")

    story_task = next((row for row in all_tasks if row.get("stage") == "story_detail"
        and (row.get("result") or {}).get("revision_id") == source_revision_id
        and row.get("status") == "completed"), None)
    story = api.production_story_revisions.load_revision(api.OUTPUT_ROOT, project_id, run_id,
        source_revision_id)
    if not story_task or not story or story.get("review_status") != "accepted":
        raise ValueError("The saved shot-plan request's story ancestor is missing or unaccepted.")

    outline = next((row for row in all_tasks if row.get("stage") == "controller:scene_outline"
        and row.get("status") == "completed"
        and (row.get("request") or {}).get("source_revision_id") == source_revision_id), None)
    if not outline:
        raise ValueError("The accepted story has no completed scene-outline task.")

    expected_context = {
        "scene_revision_id": "text:scenes",
        "dialogue_revision_id": "text:dialogue",
        "visual_brief_revision_id": "text:visual_briefs",
    }
    for context_key, stage in expected_context.items():
        revision_id = context.get(context_key)
        predecessor = next((row for row in all_tasks if row.get("stage") == stage
            and row.get("status") == "completed"
            and (row.get("request") or {}).get("source_revision_id") == source_revision_id
            and (row.get("result") or {}).get("revision_id") == revision_id), None)
        if not revision_id or not predecessor:
            raise ValueError(f"Saved shot-plan request is missing its completed {stage} predecessor.")
        revision = api.production_story_revisions.load_stage_revision(api.OUTPUT_ROOT,
            project_id, run_id, stage.split(":", 1)[1], revision_id)
        if not revision or revision.get("review_status") != "accepted":
            raise ValueError(f"Saved shot-plan request's {stage} revision is not accepted.")

    if api.production_story_revisions.list_stage_revisions(api.OUTPUT_ROOT, project_id,
            run_id, "shot_plans"):
        raise ValueError("This run already has a shot-plan revision; inspect it instead of retrying.")


def _ensure_no_image_jobs_or_takes(api, project_id: str, run_id: str) -> None:
    run = api._production_v2_ledger().get_run(project_id=project_id, run_id=run_id)
    if run.get("takes"):
        raise ValueError("This run already has takes; this stage-only tool cannot resume media work.")
    db_path = api.STORAGE_ROOT / "production" / "v2_ledger.sqlite3"
    import sqlite3
    with sqlite3.connect(db_path) as db:
        active = db.execute("SELECT 1 FROM production_image_jobs WHERE project_id=? AND run_id=? "
            "AND status IN ('queued','running','recovery_required') LIMIT 1", (project_id, run_id)).fetchone()
    if active:
        raise ValueError("This run has an active image job; reconcile it before retrying text.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task-id", required=True, help="Latest failed text:shot_plans task ID")
    parser.add_argument("--model", choices=("gpt-6-sol",), required=True)
    parser.add_argument("--api-port", type=int, default=int(os.environ.get(
        "STORY_BUILDER_BACKEND_PORT", "3010")))
    parser.add_argument("--execute", action="store_true", help="Execute one provider call; default is dry-run")
    parser.add_argument("--authorize-one-extra-attempt", action="store_true",
        help="Explicitly authorize one attempt beyond the two already persisted failures")
    parser.add_argument("--confirm-provider-content-egress", action="store_true",
        help="Confirm the saved shot-plan request may be sent to configured Codex")
    args = parser.parse_args(argv)

    os.environ["CODEX_REASONING_MODEL"] = args.model
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from story_builder.api import main as api
    from story_builder.services import reasoning_provider
    reasoning_provider.DEFAULT_CODEX_MODEL = args.model

    key = retry_idempotency_key(task_id=args.task_id, model=args.model)
    store = api._production_stage_task_store()
    tasks = store.list_run(project_id=args.project_id, run_id=args.run_id)
    target = validate_retry_history(tasks, task_id=args.task_id, key=key)
    run = api._production_v2_ledger().get_run(project_id=args.project_id, run_id=args.run_id)
    if run.get("config", {}).get("provider") != "codex":
        raise ValueError("The saved run is not pinned to the configured Codex provider.")
    if run.get("config", {}).get("control_mode") != "fully_automated":
        raise ValueError("This bounded acceptance retry requires the saved Full control mode.")
    _require_accepted_predecessors(api, args.project_id, args.run_id, target, tasks)
    _ensure_no_image_jobs_or_takes(api, args.project_id, args.run_id)
    _require_api_stopped(args.api_port)

    summary = {"mode": "stage-only", "provider": "codex", "model": args.model,
        "project_id": args.project_id, "run_id": args.run_id, "stage": target["stage"],
        "source_task_id": target["task_id"], "source_request_hash": target["request_hash"],
        "retry_idempotency_key": key, "controller_advancement": False,
        "image_work_queued": False, "execute": args.execute}
    if not args.execute:
        print(json.dumps({**summary, "outcome": "preflight_passed"}, indent=2))
        return 0
    if not args.authorize_one_extra_attempt or not args.confirm_provider_content_egress:
        raise ValueError("Execution requires --authorize-one-extra-attempt and --confirm-provider-content-egress.")

    retry = store.enqueue(project_id=args.project_id, run_id=args.run_id,
        stage=target["stage"], idempotency_key=key, request=target["request"])
    if retry["status"] != "queued":
        raise ValueError(f"The reserved stage-only task is {retry['status']}; inspect it instead of replaying.")
    print(json.dumps({**summary, "outcome": "started", "task_id": retry["task_id"]}), flush=True)
    # The process handles this one task synchronously. The opt-out is passed
    # through the normal owner/lease path, so success and retryable failure
    # both stop before `_advance_production_text_controller` can enqueue images.
    api._execute_production_story_stage_task(retry["task_id"], advance_controller=False)
    settled = store.get(project_id=args.project_id, run_id=args.run_id, task_id=retry["task_id"])
    revision_id = (settled.get("result") or {}).get("revision_id")
    revision = (api.production_story_revisions.load_stage_revision(api.OUTPUT_ROOT,
        args.project_id, args.run_id, "shot_plans", revision_id) if revision_id else None)
    result = {**summary, "task_id": retry["task_id"], "status": settled["status"],
        "result": settled.get("result"), "error": settled.get("error"),
        **settled_retry_outcome(settled, revision, project_id=args.project_id,
            run_id=args.run_id, model=args.model)}
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2), flush=True)
    return 0 if result["outcome"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
