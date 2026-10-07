"""Read-only ComfyUI reconciliation for durable V2 take records.

This service never submits or cancels work. When the durable prompt ID is not
visible in ComfyUI queue/history, it marks the take recovery-required rather
than blindly submitting a duplicate.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from story_builder.services.production_ledger import ProductionLedger


def request_json(url: str, *, timeout_seconds: int = 8) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _queue_prompt_ids(rows: list[Any]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        if isinstance(row, (list, tuple)) and len(row) > 1 and isinstance(row[1], str):
            ids.add(row[1])
        elif isinstance(row, dict) and isinstance(row.get("prompt_id"), str):
            ids.add(row["prompt_id"])
    return ids


def history_reports_interrupted(status: dict[str, Any]) -> bool:
    """Recognize the ComfyUI history event used to confirm an owned cancellation."""
    messages = status.get("messages", [])
    return isinstance(messages, list) and any(isinstance(message, (list, tuple)) and message
        and message[0] == "execution_interrupted" for message in messages)


def reconcile_comfyui_takes(
    ledger: ProductionLedger,
    *,
    comfy_url: str,
    project_id: str | None = None,
    get_json: Callable[..., dict[str, Any]] = request_json,
) -> dict[str, Any]:
    """Reconcile only known prompt IDs; failure to reach Comfy leaves rows intact."""
    base = comfy_url.rstrip("/")
    try:
        queue = get_json(f"{base}/queue")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"status": "deferred", "reason": "comfyui_unavailable", "message": f"{type(exc).__name__}: {exc}", "checked": 0, "updated": []}
    pending = _queue_prompt_ids(queue.get("queue_pending", []))
    running = _queue_prompt_ids(queue.get("queue_running", []))
    candidates = ledger.reconciliation_candidates(project_id=project_id)
    updated: list[dict[str, Any]] = []
    for take in candidates:
        prompt_id = take.get("prompt_id")
        details: dict[str, Any] = {"prompt_id": prompt_id, "reconciled_by": "comfyui_queue_history"}
        if prompt_id and prompt_id in running:
            observed = "running"
        elif prompt_id and prompt_id in pending:
            observed = "pending"
        elif prompt_id:
            try:
                history = get_json(f"{base}/history/{prompt_id}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                return {"status": "partial", "reason": "comfyui_history_unavailable", "message": f"{type(exc).__name__}: {exc}", "checked": len(updated), "updated": updated}
            prompt_state = history.get(prompt_id)
            status = prompt_state.get("status", {}) if isinstance(prompt_state, dict) else {}
            if status.get("status_str") == "error":
                observed = "error"
                details["messages"] = status.get("messages", [])
                details["execution_interrupted"] = history_reports_interrupted(status)
            elif status.get("completed") or status.get("status_str") == "success":
                observed = "success"
            else:
                observed = "absent"
                details["reason"] = "reserved_prompt_id_not_in_queue_or_history"
        else:
            observed = "absent"
            details["reason"] = "take_has_no_reserved_prompt_id"
        result = ledger.reconcile_remote_state(
            project_id=take["project_id"], take_id=take["take_id"], observed=observed, details=details,
        )
        updated.append({"take_id": take["take_id"], "prompt_id": prompt_id, "observed": observed, "status": result["status"]})
    return {"status": "completed", "checked": len(candidates), "updated": updated}
