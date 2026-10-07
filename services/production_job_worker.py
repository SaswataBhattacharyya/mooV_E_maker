"""Serialized, durable, testable ComfyUI worker for production V2 H3 takes."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import logging
import time
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from story_builder.services.media_jobs import comfy_submission_guard, release_comfyui_models_if_idle
from story_builder.services.gpu_runtime import (
    DEFAULT_TELEMETRY_PATH, GPU_RENDER_CLOCK_CEILING_MHZ, GPU_RENDER_TEMP_CUTOFF,
    GPUAdmissionError, inspect_gpu_runtime, interrupt_if_owned_prompt,
    read_gpu_operating_point, record_gpu_telemetry,
)
from story_builder.services.production_ledger import LedgerConflict, ProductionLedger


from story_builder.services.gpu_watchdog import ensure_prompt_watchdog, finish_prompt_watchdog
from story_builder.services.production_authority import director_controls

from story_builder.services.production_reconciliation import history_reports_interrupted as _history_reports_interrupted

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedTake:
    graph: dict[str, Any]
    cleanup: Callable[[], Any]


def _request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
                  timeout_seconds: int = 30) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data is not None else {})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
        # ComfyUI command endpoints such as /interrupt acknowledge with HTTP
        # success and an empty body. Empty success is an acknowledgment, not a
        # malformed JSON response; callers needing fields still validate them.
        return json.loads(body.decode("utf-8")) if body else {}


class ProductionJobWorker:
    """Claims at most one H3 take globally and never retries an unknown submit.

    Media resolution/staging/collection are injected so this state machine can
    be tested without ComfyUI, model loads or GPU access.
    """
    def __init__(self, ledger: ProductionLedger, *, comfy_url: str,
                 prepare: Callable[[dict[str, Any]], PreparedTake],
                 collect: Callable[[dict[str, Any], dict[str, Any]], list[dict[str, Any]]],
                 cleanup: Callable[[dict[str, Any]], Any],
                 director_provider_preflight: Callable[[str], dict[str, Any]] | None = None,
                 director_video_review: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
                 resolve_video_output: Callable[[dict[str, Any]], Any] | None = None,
                 enqueue_director_retake: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
                 release_idle: Callable[..., dict[str, Any]] = release_comfyui_models_if_idle,
                 request_json: Callable[..., dict[str, Any]] = _request_json,
                 gpu_inspector: Callable[..., dict[str, Any]] | None = None,
                 operating_point_reader: Callable[[], dict[str, float]] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 worker_id: str = "production-v2-worker", poll_interval: float = 2.0,
                 render_timeout_seconds: int = 8 * 60 * 60,
                 lease_seconds: int = 300, heartbeat_interval_seconds: float = 20.0):
        self.ledger = ledger
        self.comfy_url = comfy_url.rstrip("/")
        self.prepare = prepare
        self.collect = collect
        self.cleanup = cleanup
        self.director_provider_preflight = director_provider_preflight
        self.director_video_review = director_video_review
        self.resolve_video_output = resolve_video_output
        self.enqueue_director_retake = enqueue_director_retake
        self.release_idle = release_idle
        self.request_json = request_json
        self.gpu_inspector = gpu_inspector or inspect_gpu_runtime
        self.operating_point_reader = operating_point_reader or read_gpu_operating_point
        self.sleep = sleep
        self.worker_id = worker_id
        self.poll_interval = max(0.1, poll_interval)
        self.render_timeout_seconds = render_timeout_seconds
        self.lease_seconds = max(1, min(3600, lease_seconds))
        self.heartbeat_interval_seconds = max(0.05, heartbeat_interval_seconds)

    def process_one(self) -> dict[str, Any]:
        take = self.ledger.claim_next_queued_take(lease_owner=self.worker_id, lease_seconds=self.lease_seconds)
        if take is None:
            return {"status": "idle"}
        prepared: PreparedTake | None = None
        reserved_prompt = False
        workload_started_at: str | None = None
        # ComfyUI has its own in-memory queue. Keep production V2 jobs in the
        # durable website ledger until the shared Comfy queue is empty.
        busy_reason = self._comfy_queue_busy_reason()
        if busy_reason:
            self.ledger.requeue_unsubmitted_take(project_id=take["project_id"], take_id=take["take_id"],
                lease_owner=self.worker_id, reason=busy_reason)
            LOGGER.info("Production H3 remains in backend queue take=%s reason=%s", take["take_id"], busy_reason)
            return {"status": "waiting_for_comfyui", "take_id": take["take_id"], "reason": busy_reason}
        try:
            LOGGER.info("Production H3 prepare begin project=%s run=%s shot=%s take=%s attempt=%s",
                take["project_id"], take["run_id"], take["shot_id"], take["take_id"], take["attempt"])
            # Media staging can take longer than the lease. Keep the durable
            # claim alive while preparation runs, so recovery cannot mistake
            # a slow but active worker for a crashed pre-submit worker.
            heartbeat_stop = threading.Event()
            def keep_preparation_lease() -> None:
                while not heartbeat_stop.wait(self.heartbeat_interval_seconds):
                    try:
                        self.ledger.heartbeat(project_id=take["project_id"], take_id=take["take_id"],
                            lease_owner=self.worker_id, lease_seconds=self.lease_seconds)
                    except Exception:
                        LOGGER.warning("Could not refresh preparation lease take=%s", take["take_id"], exc_info=True)
            heartbeat_thread = threading.Thread(target=keep_preparation_lease,
                name=f"production-take-lease-{take['take_id']}", daemon=True)
            heartbeat_thread.start()
            try:
                run = self.ledger.get_run(project_id=take["project_id"], run_id=take["run_id"])
                config = run.get("config") or {}
                if director_controls(config, "shot_workflow_render_approval"):
                    provider = str(config.get("provider") or "").strip()
                    try:
                        if not provider or self.director_provider_preflight is None:
                            raise RuntimeError("The saved Director provider is unavailable for preflight.")
                        self.director_provider_preflight(provider)
                    except Exception as exc:
                        message = f"Saved Director provider preflight failed: {type(exc).__name__}: {exc}"[:1200]
                        self.ledger.transition_take(project_id=take["project_id"], take_id=take["take_id"],
                            status="failed", payload={"code": "director_provider_unavailable",
                                "provider": provider or None, "message": message})
                        return {"status": "failed", "take_id": take["take_id"], "reason": message}
                prepared = self.prepare(take)
            finally:
                heartbeat_stop.set()
                heartbeat_thread.join(timeout=max(0.1, self.heartbeat_interval_seconds * 2))
            # Preparation/staging can take time; recheck immediately before
            # reserving an ID or POSTing so a newly-busy ComfyUI never receives
            # a second queued render from this worker.
            with comfy_submission_guard():
                # All Story Builder submitters take the same cross-process
                # admission lock. Check again under that lock so no website
                # submission races into ComfyUI's pending queue.
                busy_reason = self._comfy_queue_busy_reason()
                if busy_reason:
                    self._cleanup_owned(take, prepared)
                    self.ledger.requeue_unsubmitted_take(project_id=take["project_id"], take_id=take["take_id"],
                        lease_owner=self.worker_id, reason=busy_reason)
                    LOGGER.info("Production H3 returned to backend queue before submit take=%s reason=%s",
                        take["take_id"], busy_reason)
                    return {"status": "waiting_for_comfyui", "take_id": take["take_id"], "reason": busy_reason}
                try:
                    workload_started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    sample = self.gpu_inspector(comfy_url=self.comfy_url,
                                                workload_started_at=workload_started_at)
                except GPUAdmissionError as exc:
                    self._cleanup_owned(take, prepared)
                    reason = f"GPU admission failed closed: {exc}"
                    self.ledger.requeue_unsubmitted_take(project_id=take["project_id"], take_id=take["take_id"],
                        lease_owner=self.worker_id, reason=reason)
                    return {"status": "waiting_for_gpu", "take_id": take["take_id"], "reason": reason}
                record_gpu_telemetry(DEFAULT_TELEMETRY_PATH, sample, workload_id=take["take_id"], phase="admission")
                reserved = self.ledger.reserve_prompt_id(project_id=take["project_id"], take_id=take["take_id"])
                prompt_id = reserved["prompt_id"]
                reserved_prompt = True
                try:
                    ensure_prompt_watchdog(comfy_url=self.comfy_url, prompt_id=prompt_id).check()
                except GPUAdmissionError:
                    finish_prompt_watchdog(comfy_url=self.comfy_url, prompt_id=prompt_id)
                    raise
                try:
                    response = self.request_json(f"{self.comfy_url}/prompt", method="POST",
                        payload={"prompt": prepared.graph, "prompt_id": prompt_id}, timeout_seconds=60)
                except urllib.error.HTTPError as exc:
                    finish_prompt_watchdog(comfy_url=self.comfy_url, prompt_id=prompt_id)
                    detail = exc.read().decode("utf-8", errors="replace")[-2000:]
                    self.ledger.reconcile_remote_state(project_id=take["project_id"], take_id=take["take_id"],
                        observed="error", details={"code": "comfy_submission_rejected", "http_status": exc.code,
                                                    "message": detail, "prompt_id": prompt_id})
                    self._cleanup_owned(take, prepared)
                    self.release_idle(comfy_url=self.comfy_url)
                    return {"status": "failed", "take_id": take["take_id"], "reason": "comfy_submission_rejected"}
                except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                    self.ledger.reconcile_remote_state(project_id=take["project_id"], take_id=take["take_id"],
                        observed="absent", details={"code": "comfy_submit_outcome_unknown",
                            "message": f"{type(exc).__name__}: {exc}", "prompt_id": prompt_id})
                    # Keep staged inputs: ComfyUI may have accepted the prompt before
                    # the connection failed. Recovery must establish the remote state.
                    return {"status": "recovery_required", "take_id": take["take_id"], "prompt_id": prompt_id}
                returned_id = response.get("prompt_id")
                if returned_id != prompt_id:
                    self.ledger.reconcile_remote_state(project_id=take["project_id"], take_id=take["take_id"],
                        observed="absent", details={"code": "comfy_prompt_id_mismatch", "reserved_prompt_id": prompt_id,
                                                     "returned_prompt_id": returned_id})
                    return {"status": "recovery_required", "take_id": take["take_id"], "prompt_id": prompt_id}
                self.ledger.bind_prompt_id(project_id=take["project_id"], take_id=take["take_id"], prompt_id=prompt_id)
                return self._wait_collect(take, prompt_id, prepared,
                                          workload_started_at=workload_started_at)
        except Exception as exc:
            LOGGER.exception("Production H3 worker failed project=%s run=%s shot=%s take=%s",
                take.get("project_id"), take.get("run_id"), take.get("shot_id"), take.get("take_id"))
            if reserved_prompt:
                try:
                    current = next((item for item in self.ledger.reconciliation_candidates(project_id=take["project_id"])
                                    if item.get("take_id") == take["take_id"]), None)
                    if current and current.get("status") in {"submitting", "running", "collecting"}:
                        self.ledger.transition_take(project_id=take["project_id"], take_id=take["take_id"],
                            status="recovery_required", payload={"code": "worker_state_uncertain", "message": str(exc)[:1000]})
                except Exception:
                    LOGGER.exception("Could not mark uncertain take for recovery take=%s", take.get("take_id"))
            else:
                try:
                    self.ledger.transition_take(project_id=take["project_id"], take_id=take["take_id"],
                        status="failed", payload={"code": "production_prepare_failed", "message": str(exc)[:1000]})
                    if prepared:
                        self._cleanup_owned(take, prepared)
                except Exception:
                    LOGGER.exception("Could not persist pre-submit take failure take=%s", take.get("take_id"))
            return {"status": "recovery_required" if reserved_prompt else "failed",
                    "take_id": take["take_id"], "reason": str(exc)[:500]}

    def _comfy_queue_busy_reason(self) -> str | None:
        """Return a reason to defer submission unless ComfyUI explicitly reports idle."""
        try:
            queue = self.request_json(f"{self.comfy_url}/queue", timeout_seconds=10)
            running = queue.get("queue_running")
            pending = queue.get("queue_pending")
            if not isinstance(running, list) or not isinstance(pending, list):
                return "comfy_queue_status_invalid"
            if running or pending:
                return f"comfy_queue_busy:running={len(running)}:pending={len(pending)}"
            return None
        except Exception as exc:
            # Fail closed. A transient health/API failure is not proof that GPU
            # capacity is free, so retain the job in the website-owned queue.
            LOGGER.warning("Cannot confirm ComfyUI is idle; keeping work backend-queued error=%s: %s",
                type(exc).__name__, exc)
            return f"comfy_queue_unavailable:{type(exc).__name__}"

    def reconcile_existing_once(self) -> dict[str, Any]:
        """Observe known prompt IDs after process restart; never resubmit them."""
        observed_count = 0
        # A crash before prompt reservation is known not to have reached
        # ComfyUI. Expired claims can be safely failed and retried by the UI.
        for take in self.ledger.fail_expired_unsubmitted_takes():
            try:
                self.cleanup(take)
            except Exception:
                LOGGER.warning("Could not clean expired pre-submit staging take=%s", take.get("take_id"), exc_info=True)
            observed_count += 1
        candidates = self.ledger.reconciliation_candidates()
        if not candidates:
            return {"observed": observed_count}
        # A prompt may be accepted but not yet appear in /history. Inspect the
        # live queue before declaring it absent; an unchanged queued/running
        # result is retried after the supervisor's bounded idle wait below.
        try:
            queue = self.request_json(f"{self.comfy_url}/queue", timeout_seconds=10)
            running_rows = queue.get("queue_running") if isinstance(queue, dict) else None
            pending_rows = queue.get("queue_pending") if isinstance(queue, dict) else None
            if not isinstance(running_rows, list) or not isinstance(pending_rows, list):
                raise ValueError("ComfyUI returned a malformed queue response")
            def prompt_ids(rows: list[Any]) -> set[str]:
                ids: set[str] = set()
                for row in rows:
                    if isinstance(row, (list, tuple)) and len(row) > 1 and isinstance(row[1], str):
                        ids.add(row[1])
                    elif isinstance(row, dict) and isinstance(row.get("prompt_id"), str):
                        ids.add(row["prompt_id"])
                    else:
                        raise ValueError("ComfyUI returned a malformed queue entry")
                return ids
            running_ids = prompt_ids(running_rows)
            pending_ids = prompt_ids(pending_rows)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
            LOGGER.warning("Cannot reconcile saved H3 prompts without a valid ComfyUI queue: %s", exc)
            return {"observed": observed_count, "deferred": len(candidates), "reason": "comfy_queue_unavailable"}
        for take in candidates:
            prompt_id = take.get("prompt_id")
            if not prompt_id:
                continue
            ensure_prompt_watchdog(comfy_url=self.comfy_url, prompt_id=prompt_id)
            if prompt_id in running_ids or prompt_id in pending_ids:
                observed = "running" if prompt_id in running_ids else "pending"
                reconciled = self.ledger.reconcile_remote_state(project_id=take["project_id"],
                    take_id=take["take_id"], observed=observed,
                    details={"prompt_id": prompt_id, "recovered_after_restart": True})
                if reconciled["status"] != take.get("status"):
                    observed_count += 1
                if take.get("status") != "recovery_required":
                    try:
                        self.ledger.heartbeat(project_id=take["project_id"], take_id=take["take_id"],
                            lease_owner=self.worker_id, lease_seconds=300)
                    except Exception:
                        LOGGER.debug("Recovery heartbeat not refreshed take=%s", take.get("take_id"), exc_info=True)
                continue
            try:
                history = self.request_json(f"{self.comfy_url}/history/{prompt_id}", timeout_seconds=20)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    reconciled = self.ledger.reconcile_remote_state(project_id=take["project_id"], take_id=take["take_id"],
                        observed="absent", details={"code": "comfy_prompt_not_found", "prompt_id": prompt_id})
                    observed_count += int(reconciled["status"] != take.get("status"))
                continue
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
                # Network unavailability is not evidence that a prompt is absent.
                continue
            state = history.get(prompt_id)
            if not isinstance(state, dict):
                reconciled = self.ledger.reconcile_remote_state(project_id=take["project_id"], take_id=take["take_id"],
                    observed="absent", details={"code": "comfy_prompt_not_in_history", "prompt_id": prompt_id})
                observed_count += int(reconciled["status"] != take.get("status"))
                continue
            status = state.get("status", {})
            if status.get("status_str") == "error":
                interrupted = _history_reports_interrupted(status)
                details = {"code": "comfy_render_interrupted_after_restart" if interrupted
                    else "comfy_render_failed_after_restart", "execution_interrupted": interrupted,
                    "prompt_id": prompt_id, "messages": status.get("messages", [])}
                self.ledger.reconcile_remote_state(project_id=take["project_id"], take_id=take["take_id"],
                    observed="error", details=details)
                self.cleanup(take)
                self.release_idle(comfy_url=self.comfy_url)
                observed_count += 1
                continue
            if status.get("completed") or status.get("status_str") == "success":
                self.ledger.reconcile_remote_state(project_id=take["project_id"], take_id=take["take_id"],
                    observed="success", details={"prompt_id": prompt_id, "recovered_after_restart": True})
                outputs = self.collect(take, state)
                if outputs:
                    self.ledger.set_take_outputs(project_id=take["project_id"], take_id=take["take_id"], outputs=outputs)
                    self.ledger.transition_take(project_id=take["project_id"], take_id=take["take_id"],
                        status="needs_review", payload={"output_count": len(outputs), "recovered_after_restart": True})
                    self.cleanup(take)
                else:
                    self.ledger.transition_take(project_id=take["project_id"], take_id=take["take_id"],
                        status="failed", payload={"code": "output_missing", "recovered_after_restart": True})
                    self.cleanup(take)
                self.release_idle(comfy_url=self.comfy_url)
                observed_count += 1
                continue
            is_running = status.get("status_str") == "running"
            reconciled = self.ledger.reconcile_remote_state(project_id=take["project_id"], take_id=take["take_id"],
                observed="running" if is_running else "pending",
                details={"prompt_id": prompt_id, "recovered_after_restart": True})
            if take.get("status") != "recovery_required":
                try:
                    self.ledger.heartbeat(project_id=take["project_id"], take_id=take["take_id"],
                        lease_owner=self.worker_id, lease_seconds=300)
                except Exception:
                    LOGGER.debug("Recovery heartbeat not refreshed take=%s", take.get("take_id"), exc_info=True)
            observed_count += int(reconciled["status"] != take.get("status"))
        return {"observed": observed_count}

    def review_next_take(self) -> dict[str, Any]:
        """Review one delegated completed take; persist before replayable resolution."""
        import uuid
        pending = self.ledger.unresolved_director_video_reviews(limit=1)
        if pending:
            review = pending[0]
            owner = str(uuid.uuid4())
            take = self.ledger.claim_pending_director_video_review(job_id=review["job_id"], owner_token=owner)
            if take is None:
                return {"status": "review_in_progress", "take_id": review["take_id"]}
            run = self.ledger.get_run(project_id=review["project_id"], run_id=review["run_id"])
            try:
                return self._resolve_director_video_decision(take, review["decision"], run)
            finally:
                self.ledger.release_director_video_review_claim(job_id=review["job_id"], owner_token=owner)
        if not all((self.director_video_review, self.resolve_video_output)):
            return {"status": "reviewer_unavailable"}
        owner = str(uuid.uuid4())
        take = self.ledger.claim_next_director_video_review(owner_token=owner)
        if take is None:
            return {"status": "idle"}
        run = self.ledger.get_run(project_id=take["project_id"], run_id=take["run_id"])
        if take.get("review_attempts_exhausted"):
            decision = {"schema_version": 1, "action": "blocked", "confidence": 0.0,
                "reason": "Director video review exceeded its bounded restart retry count.",
                "criteria": [], "prompt_delta": "", "evidence": []}
        else:
            try:
                video_path = self.resolve_video_output(take)
                decision = self.director_video_review(take, {**run, "video_path": str(video_path)})
                if not isinstance(decision, dict) or decision.get("action") not in {"accept", "retake", "blocked"}:
                    raise ValueError("Director returned no valid video review action.")
            except Exception as exc:
                LOGGER.exception("Director video review failed take=%s", take["take_id"])
                decision = {"schema_version": 1, "action": "blocked", "confidence": 0.0,
                    "reason": f"Director video review unavailable: {type(exc).__name__}: {exc}"[:1200],
                    "criteria": [], "prompt_delta": "", "evidence": []}
        review = self.ledger.record_director_video_review(take=take, decision=decision,
            owner_token=None if take.get("review_attempts_exhausted") else owner)
        try:
            return self._resolve_director_video_decision(take, review["decision"], run)
        finally:
            if not take.get("review_attempts_exhausted"):
                self.ledger.release_director_video_review_claim(job_id=take["job_id"], owner_token=owner)

    def _resolve_director_video_decision(self, take: dict[str, Any], decision: dict[str, Any],
                                         run: dict[str, Any]) -> dict[str, Any]:
        action = decision.get("action")
        if action == "accept":
            expected_hash = decision.get("video_sha256")
            if expected_hash is not None:
                valid = False
                try:
                    path = Path(self.resolve_video_output(take))
                    digest = hashlib.sha256()
                    with path.open("rb") as source:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            digest.update(chunk)
                    valid = isinstance(expected_hash, str) and digest.hexdigest() == expected_hash
                except (OSError, ValueError):
                    pass
                if not valid:
                    return {"status": "held", "take_id": take["take_id"],
                        "reason": "Video bytes do not match the saved Director review."}
            current = next((row for row in run["takes"] if row["take_id"] == take["take_id"]), take)
            if current["status"] != "accepted":
                preview = self.ledger.accept_take(project_id=take["project_id"], run_id=take["run_id"],
                    take_id=take["take_id"], confirm_stale_child_ids=[], actor="director_review")
                if preview.get("requires_confirmation"):
                    child_ids = [item["take_id"] for item in preview["queued_children_to_stale"]]
                    preview = self.ledger.accept_take(project_id=take["project_id"], run_id=take["run_id"],
                        take_id=take["take_id"], confirm_stale_child_ids=child_ids, actor="director_review")
                if (preview.get("accepted") is False or preview.get("blocked_by_active_children")
                        or preview.get("requires_confirmation")):
                    error = {"code": "director_video_acceptance_conflict",
                        "message": "The reviewed take has active or changed child dependencies."}
                    self.ledger.resolve_director_video_review(job_id=take["job_id"], status="blocked", error=error)
                    return {"status": "blocked", "take_id": take["take_id"], "error": error}
            self.ledger.resolve_director_video_review(job_id=take["job_id"], status="accepted")
            return {"status": "accepted", "take_id": take["take_id"]}
        if action == "retake":
            from story_builder.services.production_video_director import (
                name_spelling_is_only_audio_issue, contradictory_group_evidence_only, subject_limit_evidence_gap)
            if subject_limit_evidence_gap(decision):
                error = {"code": "native_video_evidence_incomplete",
                    "message": "Old three-subject frame evidence omits members of a larger group; preserve the clip for complete evidence review."}
                self.ledger.resolve_director_video_review(job_id=take["job_id"], status="blocked", error=error)
                return {"status": "blocked", "take_id": take["take_id"], "error": error}
            if contradictory_group_evidence_only(decision):
                error = {"code": "native_video_evidence_uncertain",
                    "message": "Frame descriptions disagree on people count; preserve this clip for evidence reassessment before any retake."}
                self.ledger.resolve_director_video_review(job_id=take["job_id"], status="blocked", error=error)
                return {"status": "blocked", "take_id": take["take_id"], "error": error}
            if name_spelling_is_only_audio_issue(decision.get("native_audio") or {}, decision.get("criteria") or []):
                error = {"code": "native_audio_name_uncertain",
                    "message": "ASR name spelling alone cannot prove a pronunciation defect; audio verification remains required and no retake is dispatched."}
                self.ledger.resolve_director_video_review(job_id=take["job_id"], status="blocked", error=error)
                return {"status": "blocked", "take_id": take["take_id"], "error": error}
            if self.enqueue_director_retake is None:
                error = {"code": "director_video_retake_unavailable", "message": "Bounded video retake dispatch is unavailable."}
                self.ledger.resolve_director_video_review(job_id=take["job_id"], status="blocked", error=error)
                return {"status": "blocked", "take_id": take["take_id"], "error": error}
            try:
                child = self.enqueue_director_retake(take, decision)
            except Exception as exc:
                LOGGER.exception("Director video retake enqueue failed take=%s", take["take_id"])
                error = {"code": "director_video_retake_failed", "message": f"{type(exc).__name__}: {exc}"[:1000]}
                self.ledger.resolve_director_video_review(job_id=take["job_id"], status="blocked", error=error)
                return {"status": "blocked", "take_id": take["take_id"], "error": error}
            if child.get("status") == "preparing":
                # Keep the immutable decision pending until its fresh durable
                # prompt preparation finishes. The next supervisor pass will
                # replay this side effect without repeating video inference.
                return {"status": "preparing", "take_id": take["take_id"],
                    "prompt_preparation_task_id": child.get("prompt_preparation_task_id")}
            if child.get("status") == "rejected":
                self.ledger.resolve_director_video_review(job_id=take["job_id"], status="rejected",
                    error={"code": "director_video_retake_budget_exhausted",
                        "message": "The two-retake limit is exhausted."})
                return {"status": "rejected", "take_id": take["take_id"]}
            self.ledger.resolve_director_video_review(job_id=take["job_id"], status="retake_queued",
                retake_take_id=child["take_id"])
            return {"status": "retake_queued", "take_id": take["take_id"], "retake": child}
        self.ledger.resolve_director_video_review(job_id=take["job_id"], status="blocked",
            error={"code": "director_video_review_blocked", "message": str(decision.get("reason") or "Review inconclusive.")[:1200]})
        return {"status": "blocked", "take_id": take["take_id"]}

    def _wait_collect(self, take: dict[str, Any], prompt_id: str,
                      prepared: PreparedTake | None, *,
                      workload_started_at: str | None = None) -> dict[str, Any]:
        watchdog = ensure_prompt_watchdog(comfy_url=self.comfy_url, prompt_id=prompt_id)
        deadline = time.monotonic() + self.render_timeout_seconds
        last_heartbeat = 0.0
        next_telemetry = 0.0
        next_limit_check = 0.0
        while time.monotonic() < deadline:
            if time.monotonic() >= next_limit_check:
                try:
                    watchdog.check()
                    point = self.operating_point_reader()
                except GPUAdmissionError as exc:
                    self.ledger.transition_take(project_id=take["project_id"], take_id=take["take_id"],
                        status="recovery_required", payload={"code": "gpu_limit_monitor_failed",
                                                              "message": str(exc), "prompt_id": prompt_id})
                    return {"status": "recovery_required", "take_id": take["take_id"],
                            "prompt_id": prompt_id, "reason": str(exc)}
                record_gpu_telemetry(DEFAULT_TELEMETRY_PATH,
                    {"recorded_at": datetime.now(timezone.utc).isoformat(), "gpu": point,
                     "temperature_cutoff_c": GPU_RENDER_TEMP_CUTOFF,
                     "graphics_clock_ceiling_mhz": GPU_RENDER_CLOCK_CEILING_MHZ},
                    workload_id=take["take_id"], phase="gpu_limit_watch")
                if (point["temperature_c"] >= GPU_RENDER_TEMP_CUTOFF or
                        point["graphics_clock_mhz"] > GPU_RENDER_CLOCK_CEILING_MHZ):
                    interrupted, detail = interrupt_if_owned_prompt(comfy_url=self.comfy_url,
                        prompt_id=prompt_id, request_json=self.request_json)
                    self.ledger.transition_take(project_id=take["project_id"], take_id=take["take_id"],
                        status="recovery_required", payload={"code": "gpu_render_limit_reached",
                            "temperature_c": point["temperature_c"],
                            "graphics_clock_mhz": point["graphics_clock_mhz"],
                            "interrupt_requested": interrupted, "message": detail,
                            "prompt_id": prompt_id})
                    LOGGER.error("GPU render guard reached limit take=%s prompt=%s details=%s",
                                 take["take_id"], prompt_id, detail)
                    return {"status": "recovery_required", "take_id": take["take_id"],
                            "prompt_id": prompt_id, "reason": detail}
                next_limit_check = time.monotonic() + 1.0
            if time.monotonic() >= next_telemetry:
                try:
                    sample = self.gpu_inspector(comfy_url=self.comfy_url, expected_prompt_id=prompt_id,
                                                workload_started_at=workload_started_at)
                except GPUAdmissionError as exc:
                    self.ledger.transition_take(project_id=take["project_id"], take_id=take["take_id"],
                        status="recovery_required", payload={"code": "gpu_monitor_failed",
                                                              "message": str(exc), "prompt_id": prompt_id})
                    return {"status": "recovery_required", "take_id": take["take_id"],
                            "prompt_id": prompt_id, "reason": str(exc)}
                record_gpu_telemetry(DEFAULT_TELEMETRY_PATH, sample, workload_id=take["take_id"], phase="render")
                next_telemetry = time.monotonic() + 10
            try:
                history = self.request_json(f"{self.comfy_url}/history/{prompt_id}", timeout_seconds=30)
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                self.sleep(self.poll_interval)
                if time.monotonic() - last_heartbeat > 20:
                    self.ledger.heartbeat(project_id=take["project_id"], take_id=take["take_id"],
                        lease_owner=self.worker_id, lease_seconds=300)
                    last_heartbeat = time.monotonic()
                LOGGER.warning("Comfy history poll transient failure take=%s error=%s", take["take_id"], exc)
                continue
            state = history.get(prompt_id)
            status = state.get("status", {}) if isinstance(state, dict) else {}
            if status.get("status_str") == "error":
                messages = status.get("messages", [])
                interrupted = _history_reports_interrupted(status)
                error = {"code": "comfy_render_interrupted" if interrupted else "comfy_render_failed",
                    "execution_interrupted": interrupted, "messages": messages}
                reconciled = self.ledger.reconcile_remote_state(project_id=take["project_id"], take_id=take["take_id"],
                    observed="error", details=error)
                if prepared:
                    self._cleanup_owned(take, prepared)
                self.release_idle(comfy_url=self.comfy_url)
                if reconciled["status"] == "cancelled":
                    return {"status": "cancelled", "take_id": take["take_id"],
                            "prompt_id": prompt_id, "reason": "comfy_execution_interrupted"}
                return {"status": "failed", "take_id": take["take_id"], "reason": "comfy_render_failed"}
            if status.get("completed") or status.get("status_str") == "success":
                self.ledger.reconcile_remote_state(project_id=take["project_id"], take_id=take["take_id"],
                    observed="success", details={"prompt_id": prompt_id})
                outputs = self.collect(take, state)
                if not outputs:
                    self.ledger.transition_take(project_id=take["project_id"], take_id=take["take_id"],
                        status="failed", payload={"code": "output_missing", "message": "ComfyUI completed but no playable video output was collected."})
                    if prepared:
                        self._cleanup_owned(take, prepared)
                    self.release_idle(comfy_url=self.comfy_url)
                    return {"status": "failed", "take_id": take["take_id"], "reason": "output_missing"}
                self.ledger.set_take_outputs(project_id=take["project_id"], take_id=take["take_id"], outputs=outputs)
                self.ledger.transition_take(project_id=take["project_id"], take_id=take["take_id"],
                    status="needs_review", payload={"output_count": len(outputs)})
                if prepared:
                    self._cleanup_owned(take, prepared)
                unload = self.release_idle(comfy_url=self.comfy_url)
                return {"status": "needs_review", "take_id": take["take_id"], "outputs": outputs,
                        "comfy_cleanup": unload}
            self.sleep(self.poll_interval)
            if time.monotonic() - last_heartbeat > 20:
                self.ledger.heartbeat(project_id=take["project_id"], take_id=take["take_id"],
                    lease_owner=self.worker_id, lease_seconds=300)
                last_heartbeat = time.monotonic()
        current = self.ledger.reconcile_remote_state(project_id=take["project_id"],
            take_id=take["take_id"], observed="absent", details={"code": "render_poll_timeout",
            "message": "Render exceeded worker timeout; do not resubmit until ComfyUI state is reconciled."})
        return {"status": current["status"], "take_id": take["take_id"], "prompt_id": prompt_id}

    def _cleanup_owned(self, take: dict[str, Any], prepared: PreparedTake) -> None:
        try:
            prepared.cleanup()
            self.cleanup(take)
        except Exception as exc:
            LOGGER.warning("Owned Comfy staging cleanup failed take=%s error=%s", take.get("take_id"), exc)


class ProductionWorkerSupervisor:
    """Idle-safe daemon consumer: no Comfy request occurs without durable work."""
    def __init__(self, worker: ProductionJobWorker, *, idle_sleep_seconds: float = 2.0):
        self.worker = worker
        self.idle_sleep_seconds = max(0.25, idle_sleep_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="production-v2-worker", daemon=True)
        self._thread.start()
        return True

    def stop(self, timeout_seconds: float = 2.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(0.0, timeout_seconds))

    def _run(self) -> None:
        LOGGER.info("Production V2 worker supervisor started; ComfyUI is contacted only for queued/known jobs")
        while not self._stop.is_set():
            try:
                recovered = self.worker.reconcile_existing_once()
                result = self.worker.process_one()
                review = self.worker.review_next_take()
                if result.get("status") == "idle" and review.get("status") == "idle":
                    self._stop.wait(self.idle_sleep_seconds)
            except Exception:
                LOGGER.exception("Production V2 worker supervisor iteration failed; continuing after bounded idle")
                self._stop.wait(self.idle_sleep_seconds)
        LOGGER.info("Production V2 worker supervisor stopped")
