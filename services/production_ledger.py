"""Durable, project-scoped ledger for the new production pipeline.

This is deliberately separate from the legacy project JSON store and never
stores media bytes. External ComfyUI submission is not performed here.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from story_builder.services.production_authority import director_controls


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_PATH = PROJECT_ROOT / "storage" / "production" / "v2_ledger.sqlite3"
JOB_STATES = {
    "draft", "validated", "queued", "waiting_for_predecessor", "waiting_for_user",
    "submitting", "running", "collecting", "needs_review", "accepted", "failed",
    "cancel_requested", "cancelled", "retrying", "stale", "recovery_required",
}
ALLOWED_TRANSITIONS = {
    "draft": {"validated", "cancelled"},
    "validated": {"queued", "waiting_for_predecessor", "waiting_for_user", "cancelled"},
    "queued": {"submitting", "cancelled", "stale", "waiting_for_user"},
    "waiting_for_predecessor": {"queued", "stale", "cancelled"},
    "waiting_for_user": {"validated", "queued", "cancelled", "stale"},
    "submitting": {"running", "collecting", "failed", "cancel_requested", "recovery_required"},
    "running": {"collecting", "failed", "cancel_requested", "recovery_required"},
    "collecting": {"needs_review", "failed", "cancel_requested", "recovery_required"},
    "needs_review": {"accepted", "retrying", "stale"},
    "retrying": {"queued", "failed", "cancelled"},
    "cancel_requested": {"cancelled", "collecting", "failed"},
    "recovery_required": {"submitting", "running", "collecting", "failed", "retrying", "cancel_requested", "cancelled"},
    "accepted": set(), "failed": {"retrying"}, "cancelled": set(), "stale": set(),
}


class LedgerError(RuntimeError):
    """Base class for durable production ledger failures."""


class LedgerConflict(LedgerError):
    """An idempotency key or requested state conflicts with stored facts."""


class LedgerNotFound(LedgerError):
    """A project-scoped run or take does not exist."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ProductionLedger:
    """SQLite WAL ledger with atomic idempotent transitions."""

    def __init__(self, path: Path | str | None = None) -> None:
        configured = os.environ.get("STORY_BUILDER_PRODUCTION_LEDGER_PATH")
        self.path = Path(path or configured or DEFAULT_LEDGER_PATH).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            # Switching/confirming journal mode takes a database-wide lock and
            # SQLite may return SQLITE_BUSY immediately even with busy_timeout.
            # Several API workers can instantiate this ledger simultaneously;
            # retry only this transient startup contention, not schema errors.
            for attempt in range(12):
                try:
                    db.execute("PRAGMA journal_mode = WAL")
                    break
                except sqlite3.OperationalError as exc:
                    message = str(exc).lower()
                    if not ("locked" in message or "busy" in message) or attempt == 11:
                        raise
                    time.sleep(min(0.01 * (2 ** attempt), 0.5))
            db.executescript("""
                CREATE TABLE IF NOT EXISTS production_runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS production_takes (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL REFERENCES production_runs(run_id) ON DELETE CASCADE,
                    shot_id TEXT NOT NULL,
                    take_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    input_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    parent_take_id TEXT,
                    prompt_id TEXT UNIQUE,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    lease_owner TEXT,
                    lease_until TEXT,
                    heartbeat_at TEXT,
                    output_hashes_json TEXT NOT NULL DEFAULT '[]',
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    UNIQUE(project_id, idempotency_key),
                    UNIQUE(project_id, take_id)
                );
                CREATE INDEX IF NOT EXISTS production_takes_run_idx ON production_takes(project_id, run_id, created_at);
                CREATE INDEX IF NOT EXISTS production_takes_parent_idx ON production_takes(project_id, parent_take_id, status);
                CREATE INDEX IF NOT EXISTS production_takes_run_parent_idx ON production_takes(project_id, run_id, parent_take_id, status);
                CREATE TABLE IF NOT EXISTS production_events (
                    event_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL REFERENCES production_runs(run_id) ON DELETE CASCADE,
                    job_id TEXT REFERENCES production_takes(job_id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS production_events_run_idx ON production_events(project_id, run_id, created_at);
                CREATE TABLE IF NOT EXISTS production_video_director_reviews (
                    review_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL UNIQUE REFERENCES production_takes(job_id) ON DELETE CASCADE,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL REFERENCES production_runs(run_id) ON DELETE CASCADE,
                    take_id TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    resolution_status TEXT NOT NULL,
                    retake_take_id TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS production_video_director_review_claims (
                    job_id TEXT PRIMARY KEY REFERENCES production_takes(job_id) ON DELETE CASCADE,
                    owner_token TEXT NOT NULL,
                    lease_until TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS production_video_review_pending_idx
                    ON production_video_director_reviews(resolution_status, created_at);
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(production_takes)")}
            if "input_snapshot_json" not in columns:
                db.execute("ALTER TABLE production_takes ADD COLUMN input_snapshot_json TEXT NOT NULL DEFAULT '{}' ")
            review_columns = {row["name"] for row in db.execute("PRAGMA table_info(production_video_director_reviews)")}
            if "retake_take_id" not in review_columns:
                db.execute("ALTER TABLE production_video_director_reviews ADD COLUMN retake_take_id TEXT")

    @staticmethod
    def _event(db: sqlite3.Connection, *, project_id: str, run_id: str, event_type: str,
               payload: dict[str, Any], job_id: str | None = None) -> None:
        db.execute(
            "INSERT INTO production_events(event_id, project_id, run_id, job_id, event_type, payload_json, created_at) VALUES(?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), project_id, run_id, job_id, event_type,
             json.dumps(payload, sort_keys=True, ensure_ascii=False), _now()),
        )

    def create_run(self, *, project_id: str, idempotency_key: str, config: dict[str, Any]) -> dict[str, Any]:
        project_id = project_id.strip()
        key = idempotency_key.strip()
        if not project_id or not key or not isinstance(config, dict):
            raise ValueError("project_id, idempotency_key, and an object config are required")
        config_json = json.dumps(config, sort_keys=True, ensure_ascii=False)
        config_hash = stable_hash(config)
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM production_runs WHERE project_id=? AND idempotency_key=?", (project_id, key)).fetchone()
            if existing:
                if existing["config_hash"] != config_hash:
                    raise LedgerConflict("Run idempotency key was already used with a different configuration.")
                db.commit()
                return self._row(existing)
            run_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO production_runs(run_id, project_id, status, idempotency_key, config_json, config_hash, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (run_id, project_id, "draft", key, config_json, config_hash, now, now),
            )
            self._event(db, project_id=project_id, run_id=run_id, event_type="run_created", payload={"config_hash": config_hash})
            row = db.execute("SELECT * FROM production_runs WHERE run_id=?", (run_id,)).fetchone()
            db.commit()
            return self._row(row)

    def queue_take(self, *, project_id: str, run_id: str, shot_id: str, take_id: str,
                   idempotency_key: str, input_snapshot: dict[str, Any], parent_take_id: str | None = None) -> dict[str, Any]:
        if not all(value and value.strip() for value in (project_id, run_id, shot_id, take_id, idempotency_key)):
            raise ValueError("project_id, run_id, shot_id, take_id, and idempotency_key are required")
        if not isinstance(input_snapshot, dict):
            raise ValueError("input_snapshot must be a JSON object")
        input_hash = stable_hash(input_snapshot)
        input_snapshot_json = json.dumps(input_snapshot, sort_keys=True, ensure_ascii=False)
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = db.execute("SELECT run_id FROM production_runs WHERE project_id=? AND run_id=?", (project_id, run_id)).fetchone()
            if not run:
                raise LedgerNotFound("Production run not found in this project.")
            existing = db.execute("SELECT * FROM production_takes WHERE project_id=? AND idempotency_key=?", (project_id, idempotency_key)).fetchone()
            if existing:
                if (existing["input_hash"] != input_hash or existing["shot_id"] != shot_id
                        or existing["run_id"] != run_id or existing["take_id"] != take_id
                        or existing["parent_take_id"] != parent_take_id):
                    raise LedgerConflict("Take idempotency key was already used with a different shot or frozen input snapshot.")
                db.commit()
                return self._row(existing)
            status = "queued"
            if parent_take_id:
                parent = db.execute("SELECT status FROM production_takes WHERE project_id=? AND run_id=? AND take_id=?",
                                    (project_id, run_id, parent_take_id)).fetchone()
                if not parent:
                    raise LedgerNotFound("Parent take not found in this project/run.")
                status = "queued" if parent["status"] == "accepted" else "waiting_for_predecessor"
            job_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO production_takes(job_id, project_id, run_id, shot_id, take_id, idempotency_key, input_hash, input_snapshot_json, status, parent_take_id, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, project_id, run_id, shot_id, take_id, idempotency_key, input_hash, input_snapshot_json, status, parent_take_id, now, now),
            )
            self._event(db, project_id=project_id, run_id=run_id, job_id=job_id, event_type="take_created", payload={"shot_id": shot_id, "take_id": take_id, "status": status, "input_hash": input_hash, "parent_take_id": parent_take_id})
            row = db.execute("SELECT * FROM production_takes WHERE job_id=?", (job_id,)).fetchone()
            db.commit()
            return self._row(row)

    def transition_take(self, *, project_id: str, take_id: str, status: str,
                        payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if status not in JOB_STATES:
            raise ValueError(f"Unknown production take state: {status}")
        if status == "accepted":
            raise LedgerConflict("Use accept_take so parent-retake dependencies are previewed and reconciled atomically.")
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM production_takes WHERE project_id=? AND take_id=?", (project_id, take_id)).fetchone()
            if not row:
                raise LedgerNotFound("Take not found in this project.")
            current = row["status"]
            if status != current and status not in ALLOWED_TRANSITIONS.get(current, set()):
                raise LedgerConflict(f"Illegal take transition: {current} -> {status}")
            started_at = row["started_at"] or (now if status in {"submitting", "running"} else None)
            finished_at = now if status in {"needs_review", "accepted", "failed", "cancelled", "stale"} else row["finished_at"]
            retry_reset = current == "retrying" and status == "queued"
            clear_current_error = retry_reset or status == "needs_review"
            error_json = (json.dumps(payload, ensure_ascii=False)
                          if status == "failed" and payload else
                          None if clear_current_error else row["error_json"])
            retry_attempt = row["attempt"] + 1 if retry_reset else row["attempt"]
            prompt_id = None if current == "retrying" and status == "queued" else row["prompt_id"]
            if current == "retrying" and status == "queued":
                started_at = None
                finished_at = None
            release_lease = status in {"needs_review", "accepted", "failed", "cancelled", "stale"}
            db.execute("UPDATE production_takes SET status=?, updated_at=?, started_at=?, finished_at=?, error_json=?, attempt=?, prompt_id=?, lease_owner=?, lease_until=? WHERE job_id=?",
                       (status, now, started_at, finished_at, error_json, retry_attempt, prompt_id,
                        None if release_lease else row["lease_owner"],
                        None if release_lease else row["lease_until"], row["job_id"]))
            self._event(db, project_id=project_id, run_id=row["run_id"], job_id=row["job_id"], event_type="take_transition", payload={"from": current, "to": status, **(payload or {})})
            if status == "accepted":
                children = db.execute("SELECT job_id, run_id, take_id FROM production_takes WHERE project_id=? AND run_id=? AND parent_take_id=? AND status='waiting_for_predecessor'",
                                      (project_id, row["run_id"], take_id)).fetchall()
                db.execute("UPDATE production_takes SET status='queued', updated_at=? WHERE project_id=? AND run_id=? AND parent_take_id=? AND status='waiting_for_predecessor'",
                           (now, project_id, row["run_id"], take_id))
                for child in children:
                    self._event(db, project_id=project_id, run_id=child["run_id"], job_id=child["job_id"],
                                event_type="predecessor_accepted", payload={"parent_take_id": take_id, "status": "queued"})
            updated = db.execute("SELECT * FROM production_takes WHERE job_id=?", (row["job_id"],)).fetchone()
            db.commit()
            return self._row(updated)

    def fail_recovery_if_absent(self, *, project_id: str, run_id: str, take_id: str,
                                prompt_id: str, details: dict[str, Any]) -> dict[str, Any]:
        """Atomically settle only the exact unresolved, output-free prompt as failed."""
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM production_takes WHERE project_id=? AND run_id=? AND take_id=?",
                             (project_id, run_id, take_id)).fetchone()
            if not row:
                raise LedgerNotFound("Take not found in this project and run.")
            if row["status"] != "recovery_required" or row["prompt_id"] != prompt_id:
                raise LedgerConflict("Take recovery state or reserved prompt changed during remote reconciliation.")
            try:
                outputs = json.loads(row["output_hashes_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise LedgerConflict("Take output metadata is invalid; recovery cannot be resolved automatically.") from exc
            if outputs:
                raise LedgerConflict("Take already has registered outputs; recovery cannot be resolved as absent.")
            error_json = json.dumps(details, ensure_ascii=False, sort_keys=True)
            db.execute("UPDATE production_takes SET status='failed', updated_at=?, finished_at=?, error_json=?, lease_owner=NULL, lease_until=NULL WHERE job_id=?",
                       (now, now, error_json, row["job_id"]))
            self._event(db, project_id=project_id, run_id=run_id, job_id=row["job_id"],
                        event_type="take_absence_confirmed", payload=details)
            updated = db.execute("SELECT * FROM production_takes WHERE job_id=?", (row["job_id"],)).fetchone()
            db.commit()
            return self._row(updated)

    def accept_take(self, *, project_id: str, run_id: str, take_id: str,
                    confirm_stale_child_ids: list[str] | None = None,
                    actor: str = "user_review") -> dict[str, Any]:
        """Accept a reviewed take, requiring explicit confirmation to stale queued descendants.

        Preview and mutation happen under one SQLite write transaction. The
        client must echo the exact queued child IDs from the preview so a newly
        queued dependency cannot be silently invalidated after confirmation.
        Accepted descendants are preserved with their original parent lineage.
        """
        confirmed = set(confirm_stale_child_ids or [])
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            candidate = db.execute(
                "SELECT * FROM production_takes WHERE project_id=? AND run_id=? AND take_id=?",
                (project_id, run_id, take_id),
            ).fetchone()
            if not candidate:
                raise LedgerNotFound("Take not found in this project/run.")
            if candidate["status"] != "needs_review":
                raise LedgerConflict("Only a collected take awaiting review can be accepted.")

            old_parents = db.execute(
                "SELECT take_id FROM production_takes WHERE project_id=? AND run_id=? AND shot_id=? "
                "AND status='accepted' AND take_id<>?",
                (project_id, run_id, candidate["shot_id"], take_id),
            ).fetchall()
            old_ids = [row["take_id"] for row in old_parents]
            queued_children: list[sqlite3.Row] = []
            if old_ids:
                marks = ",".join("?" for _ in old_ids)
                queued_children = db.execute(
                    f"SELECT * FROM production_takes WHERE project_id=? AND run_id=? "
                    f"AND parent_take_id IN ({marks}) AND status IN ('queued','waiting_for_predecessor','waiting_for_user') "
                    "ORDER BY created_at, take_id",
                    (project_id, run_id, *old_ids),
                ).fetchall()
            current_child_ids = {row["take_id"] for row in queued_children}
            if current_child_ids != confirmed:
                db.rollback()
                return {"accepted": False, "requires_confirmation": bool(current_child_ids),
                    "take_id": take_id, "superseded_parent_take_ids": old_ids,
                    "queued_children_to_stale": [self._row(row) for row in queued_children],
                    "confirmation_changed": bool(confirmed)}

            # A child already in an external/active state cannot be rewritten.
            # Keep its recorded parent and require it to settle before accepting
            # a replacement parent shot.
            active_children: list[sqlite3.Row] = []
            if old_ids:
                marks = ",".join("?" for _ in old_ids)
                active_children = db.execute(
                    f"SELECT * FROM production_takes WHERE project_id=? AND run_id=? "
                    f"AND parent_take_id IN ({marks}) AND status IN "
                    "('submitting','running','collecting','cancel_requested','recovery_required')",
                    (project_id, run_id, *old_ids),
                ).fetchall()
            if active_children:
                db.rollback()
                return {"accepted": False, "blocked_by_active_children": True,
                    "take_id": take_id, "active_children": [self._row(row) for row in active_children],
                    "queued_children_to_stale": [self._row(row) for row in queued_children]}

            for child in queued_children:
                db.execute("UPDATE production_takes SET status='stale', finished_at=?, updated_at=? "
                    "WHERE job_id=? AND status IN ('queued','waiting_for_predecessor','waiting_for_user')",
                    (now, now, child["job_id"]))
                self._event(db, project_id=project_id, run_id=child["run_id"], job_id=child["job_id"],
                    event_type="child_staled_by_parent_retake", payload={
                        "parent_take_id": child["parent_take_id"], "replacement_take_id": take_id})

            db.execute("UPDATE production_takes SET status='accepted', updated_at=?, finished_at=? "
                "WHERE job_id=? AND status='needs_review'", (now, now, candidate["job_id"]))
            self._event(db, project_id=project_id, run_id=run_id, job_id=candidate["job_id"],
                event_type="take_transition", payload={"from": "needs_review", "to": "accepted",
                    "actor": actor, "supersedes_take_ids": old_ids,
                    "staled_child_take_ids": sorted(current_child_ids)})
            waiting_children = db.execute(
                "SELECT * FROM production_takes WHERE project_id=? AND run_id=? "
                "AND parent_take_id=? AND status='waiting_for_predecessor'",
                (project_id, run_id, take_id),
            ).fetchall()
            run_config_row = db.execute("SELECT config_json FROM production_runs WHERE project_id=? AND run_id=?",
                (project_id, run_id)).fetchone()
            control_mode = str(json.loads(run_config_row["config_json"]).get("control_mode") or "manual")
            draft_events = db.execute("SELECT payload_json FROM production_events WHERE project_id=? AND run_id=? "
                "AND event_type='shot_composer_draft_saved' ORDER BY created_at, event_id", (project_id, run_id)).fetchall()
            latest_drafts: dict[str, dict[str, Any]] = {}
            for event in draft_events:
                payload = json.loads(event["payload_json"])
                shot_id = payload.get("shot_id")
                if (isinstance(shot_id, str) and (shot_id not in latest_drafts or
                        int(payload.get("revision", 0)) > int(latest_drafts[shot_id].get("revision", 0)))):
                    latest_drafts[shot_id] = payload
            released_child_ids: list[str] = []
            held_child_ids: list[str] = []
            for child in waiting_children:
                snapshot = json.loads(child["input_snapshot_json"])
                frozen_request = snapshot.get("validation_request")
                current_draft = latest_drafts.get(child["shot_id"])
                # Older direct ledger callers have no composer request; retain
                # their existing dependency behavior. Production API takes do
                # carry a frozen validation request and must prove it is still
                # the latest saved Manual draft before auto-submission.
                if not isinstance(frozen_request, dict):
                    child_status, reason = "queued", "legacy_snapshot_without_composer_draft"
                elif control_mode == "manual" and current_draft:
                    saved_draft = current_draft.get("draft")
                    same_plan = current_draft.get("shot_plan_revision_id") == snapshot.get("shot_plan_revision_id")
                    unchanged = isinstance(saved_draft, dict) and stable_hash(saved_draft) == stable_hash(frozen_request)
                    child_status, reason = (("queued", "manual_draft_unchanged") if same_plan and unchanged
                        else ("waiting_for_user", "manual_draft_changed_or_stale"))
                else:
                    child_status, reason = "waiting_for_user", "manual_child_requires_human_review"
                db.execute("UPDATE production_takes SET status=?, updated_at=? WHERE job_id=? "
                    "AND status='waiting_for_predecessor'", (child_status, now, child["job_id"]))
                self._event(db, project_id=project_id, run_id=child["run_id"], job_id=child["job_id"],
                    event_type="predecessor_accepted", payload={"parent_take_id": take_id,
                        "status": child_status, "reason": reason,
                        "frozen_input_hash": child["input_hash"]})
                (released_child_ids if child_status == "queued" else held_child_ids).append(child["take_id"])
            updated = db.execute("SELECT * FROM production_takes WHERE job_id=?", (candidate["job_id"],)).fetchone()
            db.commit()
            return {"accepted": True, "take": self._row(updated),
                "superseded_parent_take_ids": old_ids,
                "staled_child_take_ids": sorted(current_child_ids),
                "released_child_take_ids": released_child_ids,
                "held_child_take_ids": held_child_ids}

    def bind_prompt_id(self, *, project_id: str, take_id: str, prompt_id: str) -> dict[str, Any]:
        if not prompt_id.strip():
            raise ValueError("prompt_id is required")
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM production_takes WHERE project_id=? AND take_id=?", (project_id, take_id)).fetchone()
            if not row:
                raise LedgerNotFound("Take not found in this project.")
            if row["prompt_id"] and row["prompt_id"] != prompt_id:
                raise LedgerConflict("A different ComfyUI prompt ID is already bound to this take.")
            if not row["prompt_id"]:
                raise LedgerConflict("Reserve the ComfyUI prompt ID before submitting the workflow.")
            if row["status"] not in {"submitting", "running"}:
                raise LedgerConflict("A ComfyUI prompt ID can be bound only to a submitting or running take.")
            if row["status"] == "running":
                db.commit()
                return self._row(row)
            db.execute("UPDATE production_takes SET prompt_id=?, status='running', heartbeat_at=?, updated_at=?, started_at=COALESCE(started_at, ?) WHERE job_id=?",
                       (prompt_id, now, now, now, row["job_id"]))
            self._event(db, project_id=project_id, run_id=row["run_id"], job_id=row["job_id"], event_type="comfy_prompt_bound", payload={"prompt_id": prompt_id})
            updated = db.execute("SELECT * FROM production_takes WHERE job_id=?", (row["job_id"],)).fetchone()
            db.commit()
            return self._row(updated)

    def reserve_prompt_id(self, *, project_id: str, take_id: str) -> dict[str, Any]:
        """Persist a stable ComfyUI UUID before network submission.

        ComfyUI's `/prompt` accepts a caller-provided UUID. After a backend
        restart, reconciliation can query this ID before considering retry.
        """
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM production_takes WHERE project_id=? AND take_id=?", (project_id, take_id)).fetchone()
            if not row:
                raise LedgerNotFound("Take not found in this project.")
            if row["status"] != "submitting":
                raise LedgerConflict("Reserve a ComfyUI prompt ID only after the take enters submitting state.")
            if row["prompt_id"]:
                db.commit()
                return self._row(row)
            prompt_id = str(uuid.uuid5(uuid.UUID(row["job_id"]), f"comfy-submit-attempt-{row['attempt']}"))
            db.execute("UPDATE production_takes SET prompt_id=?, updated_at=?, started_at=COALESCE(started_at, ?) WHERE job_id=?",
                       (prompt_id, now, now, row["job_id"]))
            self._event(db, project_id=project_id, run_id=row["run_id"], job_id=row["job_id"],
                        event_type="comfy_prompt_reserved", payload={"prompt_id": prompt_id, "attempt": row["attempt"]})
            updated = db.execute("SELECT * FROM production_takes WHERE job_id=?", (row["job_id"],)).fetchone()
            db.commit()
            return self._row(updated)

    def reconciliation_candidates(self, *, project_id: str | None = None) -> list[dict[str, Any]]:
        """Return submitted/unknown external jobs; callers must not resubmit blindly."""
        with self._connect() as db:
            if project_id:
                rows = db.execute("SELECT * FROM production_takes WHERE project_id=? AND status IN ('submitting','running','collecting','cancel_requested','recovery_required') ORDER BY created_at", (project_id,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM production_takes WHERE status IN ('submitting','running','collecting','cancel_requested','recovery_required') ORDER BY created_at").fetchall()
            return [self._row(row) for row in rows]

    def fail_expired_unsubmitted_takes(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Fail only expired pre-submit claims that never reserved a Comfy prompt ID.

        The worker persists its prompt ID before POST /prompt. Therefore a
        submitting row with no prompt ID and an expired lease is safe to release
        after a crash; a row with any prompt ID still requires remote
        reconciliation and is deliberately excluded.
        """
        observed_at = now or datetime.now(timezone.utc)
        if observed_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        timestamp = observed_at.astimezone(timezone.utc).isoformat()
        failed: list[dict[str, Any]] = []
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM production_takes WHERE status='submitting' AND prompt_id IS NULL "
                "AND lease_until IS NOT NULL AND lease_until < ? ORDER BY created_at", (timestamp,)
            ).fetchall()
            for row in rows:
                error = {"code": "worker_interrupted_before_submit",
                    "message": "The worker lease expired before a ComfyUI prompt ID was reserved; no external submission was made.",
                    "retryable": True}
                encoded = json.dumps(error, ensure_ascii=False)
                db.execute("UPDATE production_takes SET status='failed', error_json=?, finished_at=?, updated_at=? WHERE job_id=? AND status='submitting' AND prompt_id IS NULL",
                    (encoded, timestamp, timestamp, row["job_id"]))
                self._event(db, project_id=row["project_id"], run_id=row["run_id"], job_id=row["job_id"],
                    event_type="unsubmitted_take_recovered", payload=error)
                updated = db.execute("SELECT * FROM production_takes WHERE job_id=?", (row["job_id"],)).fetchone()
                failed.append(self._row(updated))
            db.commit()
        return failed

    def claim_next_queued_take(self, *, lease_owner: str, lease_seconds: int = 180) -> dict[str, Any] | None:
        """Atomically claim one queued take, while enforcing one active GPU job.

        Any submitted/recovery-required job blocks another H3 submission until
        reconciliation or a terminal state establishes what happened remotely.
        """
        if not lease_owner or len(lease_owner) > 160 or not 1 <= lease_seconds <= 3600:
            raise ValueError("lease_owner and lease_seconds 1–3600 are required")
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        expires = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT 1 FROM production_takes WHERE status IN ('submitting','running','collecting','cancel_requested','recovery_required') LIMIT 1").fetchone()
            if active:
                db.commit()
                return None
            row = db.execute("SELECT * FROM production_takes WHERE status='queued' ORDER BY created_at, job_id LIMIT 1").fetchone()
            if not row:
                db.commit()
                return None
            parent = row["parent_take_id"]
            if parent:
                parent_row = db.execute("SELECT status FROM production_takes WHERE project_id=? AND run_id=? AND take_id=?",
                                        (row["project_id"], row["run_id"], parent)).fetchone()
                if not parent_row or parent_row["status"] != "accepted":
                    db.execute("UPDATE production_takes SET status='waiting_for_predecessor', updated_at=? WHERE job_id=?",
                               (now.isoformat(), row["job_id"]))
                    self._event(db, project_id=row["project_id"], run_id=row["run_id"], job_id=row["job_id"],
                                event_type="take_waiting_for_predecessor", payload={"parent_take_id": parent})
                    db.commit()
                    return None
            db.execute("UPDATE production_takes SET status='submitting', lease_owner=?, lease_until=?, heartbeat_at=?, started_at=COALESCE(started_at, ?), updated_at=? WHERE job_id=? AND status='queued'",
                       (lease_owner, expires, now.isoformat(), now.isoformat(), now.isoformat(), row["job_id"]))
            self._event(db, project_id=row["project_id"], run_id=row["run_id"], job_id=row["job_id"],
                        event_type="take_claimed", payload={"lease_owner": lease_owner, "lease_until": expires})
            claimed = db.execute("SELECT * FROM production_takes WHERE job_id=?", (row["job_id"],)).fetchone()
            db.commit()
            return self._row(claimed)

    def requeue_unsubmitted_take(self, *, project_id: str, take_id: str,
                                 lease_owner: str, reason: str) -> dict[str, Any]:
        """Return a safely unsubmitted claim to the backend queue.

        This is permitted only before a Comfy prompt ID is reserved. Once a
        prompt ID exists, submission may be ambiguous and recovery must inspect
        ComfyUI instead of risking a duplicate render.
        """
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM production_takes WHERE project_id=? AND take_id=?",
                             (project_id, take_id)).fetchone()
            if not row:
                raise LedgerNotFound("Take not found in this project.")
            if row["status"] != "submitting" or row["prompt_id"] is not None:
                raise LedgerConflict("Only a pre-submit claim with no Comfy prompt ID can be returned to the backend queue.")
            if row["lease_owner"] != lease_owner:
                raise LedgerConflict("Only the worker that owns the pre-submit lease can requeue this take.")
            db.execute("UPDATE production_takes SET status='queued', lease_owner=NULL, lease_until=NULL, heartbeat_at=NULL, started_at=NULL, updated_at=? WHERE job_id=? AND status='submitting' AND prompt_id IS NULL AND lease_owner=?",
                       (now, row["job_id"], lease_owner))
            self._event(db, project_id=project_id, run_id=row["run_id"], job_id=row["job_id"],
                        event_type="take_requeued_before_comfy_submit",
                        payload={"reason": reason[:240], "status": "queued"})
            updated = db.execute("SELECT * FROM production_takes WHERE job_id=?", (row["job_id"],)).fetchone()
            db.commit()
            return self._row(updated)

    def claim_next_director_video_review(self, *, owner_token: str,
                                         lease_seconds: int = 7200,
                                         max_attempts: int = 3) -> dict[str, Any] | None:
        """Claim one completed take whose saved run delegates render review."""
        if not owner_token or len(owner_token) > 200:
            raise ValueError("Director review owner token is invalid.")
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        expires = (now + timedelta(seconds=max(60, min(lease_seconds, 7200)))).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("""SELECT t.*, r.config_json, c.owner_token AS claim_owner,
                    c.lease_until AS claim_lease_until, c.attempt_count AS claim_attempt_count
                FROM production_takes t
                JOIN production_runs r ON r.run_id=t.run_id AND r.project_id=t.project_id
                LEFT JOIN production_video_director_reviews v ON v.job_id=t.job_id
                LEFT JOIN production_video_director_review_claims c ON c.job_id=t.job_id
                WHERE t.status='needs_review' AND v.job_id IS NULL
                    AND (c.job_id IS NULL OR c.lease_until<=?)
                ORDER BY t.created_at,t.job_id""", (now_text,)).fetchall()
            for row in rows:
                config = json.loads(row["config_json"])
                if not director_controls(config, "shot_workflow_render_approval"):
                    continue
                attempts = int(row["claim_attempt_count"] or 0)
                take = self._row(row)
                take.pop("config_json", None)
                allowed = max(1, max_attempts)
                # One explicit new-evidence reassessment, never an automatic retry.
                reassessments = db.execute("SELECT payload_json FROM production_events WHERE job_id=? "
                    "AND event_type IN ('director_video_reference_evidence_reassessment', "
                    "'director_video_human_speaker_reassessment')", (row["job_id"],)).fetchall()
                for reassessment in reassessments:
                    allowed = max(allowed, int(json.loads(reassessment["payload_json"])["review_attempt_ceiling"]))
                if attempts >= allowed:
                    db.commit()
                    return {**take, "review_attempts_exhausted": True}
                attempt = attempts + 1
                db.execute("""INSERT INTO production_video_director_review_claims
                    (job_id,owner_token,lease_until,attempt_count,updated_at) VALUES(?,?,?,?,?)
                    ON CONFLICT(job_id) DO UPDATE SET owner_token=excluded.owner_token,
                    lease_until=excluded.lease_until,attempt_count=excluded.attempt_count,
                    updated_at=excluded.updated_at""",
                    (row["job_id"], owner_token, expires, attempt, now_text))
                take["review_attempt_count"] = attempt
                db.commit()
                return take
            db.commit()
        return None

    def release_director_video_review_claim(self, *, job_id: str, owner_token: str) -> bool:
        now = _now()
        with self._connect() as db:
            cursor = db.execute("UPDATE production_video_director_review_claims "
                "SET owner_token='',lease_until=?,updated_at=? WHERE job_id=? AND owner_token=?",
                (now, now, job_id, owner_token))
            return cursor.rowcount == 1

    def claim_pending_director_video_review(self, *, job_id: str, owner_token: str,
                                           lease_seconds: int = 7200) -> dict[str, Any] | None:
        """Lease a persisted decision so only one worker performs its side effect."""
        if not owner_token or len(owner_token) > 200:
            raise ValueError("Director review owner token is invalid.")
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        expires = (now + timedelta(seconds=max(60, min(lease_seconds, 7200)))).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            review = db.execute("SELECT * FROM production_video_director_reviews WHERE job_id=? "
                "AND resolution_status='pending'", (job_id,)).fetchone()
            if review is None:
                db.commit()
                return None
            claim = db.execute("SELECT * FROM production_video_director_review_claims WHERE job_id=?", (job_id,)).fetchone()
            if claim and claim["lease_until"] > now_text:
                db.commit()
                return None
            attempts = int(claim["attempt_count"] or 0) if claim else 0
            db.execute("""INSERT INTO production_video_director_review_claims
                (job_id,owner_token,lease_until,attempt_count,updated_at) VALUES(?,?,?,?,?)
                ON CONFLICT(job_id) DO UPDATE SET owner_token=excluded.owner_token,
                lease_until=excluded.lease_until,attempt_count=excluded.attempt_count,
                updated_at=excluded.updated_at""",
                (job_id, owner_token, expires, attempts, now_text))
            take = db.execute("SELECT * FROM production_takes WHERE job_id=?", (job_id,)).fetchone()
            db.commit()
        result = self._row(take)
        result["director_review"] = self._video_review_row(review)
        return result

    def retry_unavailable_director_video_review(self, *, project_id: str, run_id: str,
                                               take_id: str, review_id: str) -> dict[str, Any]:
        """Explicit bounded retry of provider failure, preserving the old decision in audit.

        This never resets a quality verdict, render attempt, prompt, or output.
        The exact review ID prevents concurrent/replayed operator requests.
        """
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            take = db.execute("SELECT * FROM production_takes WHERE project_id=? AND run_id=? AND take_id=?",
                (project_id, run_id, take_id)).fetchone()
            if take is None:
                raise LedgerNotFound("Take not found in this project and run.")
            review = db.execute("SELECT * FROM production_video_director_reviews WHERE job_id=? AND review_id=?",
                (take["job_id"], review_id)).fetchone()
            if review is None:
                raise LedgerConflict("The exact saved review is no longer current.")
            decision = json.loads(review["decision_json"])
            # Compatibility for already persisted provider failures from earlier workers.
            unavailable = decision.get("error_code") == "director_video_provider_unavailable" or (
                str(decision.get("reason", "")).startswith("Director video review unavailable: ReasoningProviderError:"))
            if (take["status"] != "needs_review" or review["resolution_status"] != "blocked"
                    or decision.get("action") != "blocked" or not unavailable):
                raise LedgerConflict("Only an unavailable provider review can be retried; quality decisions remain held.")
            claim = db.execute("SELECT * FROM production_video_director_review_claims WHERE job_id=?",
                (take["job_id"],)).fetchone()
            if claim and claim["lease_until"] > now:
                raise LedgerConflict("Director review is still owned by a worker.")
            attempts = int(claim["attempt_count"] or 0) if claim else 0
            if attempts >= 3:
                raise LedgerConflict("Director video review retry budget is exhausted.")
            self._event(db, project_id=project_id, run_id=run_id, job_id=take["job_id"],
                event_type="director_video_unavailable_review_retried",
                payload={"take_id": take_id, "archived_review": self._video_review_row(review),
                    "review_attempt_count": attempts, "render_resubmitted": False})
            db.execute("DELETE FROM production_video_director_reviews WHERE job_id=? AND review_id=?",
                (take["job_id"], review_id))
            db.commit()
        return {"take_id": take_id, "status": "needs_review", "render_resubmitted": False}

    def reopen_name_uncertain_review_with_human_verification(self, *, project_id: str,
            run_id: str, take_id: str, review_id: str, video_sha256: str,
            statement: str, verification_scope: str = "name_spelling_only",
            refresh_visual_evidence: bool = False) -> dict[str, Any]:
        """Archive one scoped audio hold for final Director reassessment with new evidence."""
        from story_builder.services.production_video_director import (
            name_spelling_is_only_audio_issue, matching_dialogue_audio_uncertainty, subject_limit_evidence_gap)
        if (not isinstance(refresh_visual_evidence, bool) or (refresh_visual_evidence and verification_scope != "name_spelling_only")
                or verification_scope not in {"name_spelling_only", "matching_dialogue_audio_uncertainty"}):
            raise ValueError("Unknown human audio verification scope.")
        if not isinstance(statement, str) or not 0 < len(statement.strip()) <= 1200:
            raise ValueError("A scoped human native-audio confirmation is required.")
        now = _now()
        verification = {"source": "human_native_audio_review", "confirmed": True,
            "video_sha256": video_sha256, "statement": statement.strip(), "recorded_at": now,
            "scope": verification_scope}
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            take = db.execute("SELECT * FROM production_takes WHERE project_id=? AND run_id=? AND take_id=?",
                (project_id, run_id, take_id)).fetchone()
            if take is None:
                raise LedgerNotFound("Take not found in this project and run.")
            review = db.execute("SELECT * FROM production_video_director_reviews WHERE job_id=? AND review_id=?",
                (take["job_id"], review_id)).fetchone()
            if review is None:
                raise LedgerConflict("The exact saved audio hold is no longer current.")
            decision = json.loads(review["decision_json"])
            error = json.loads(review["error_json"] or '{}')
            if (take["status"] != "needs_review" or review["resolution_status"] != "blocked"
                    or error.get("code") != ("native_video_evidence_incomplete" if refresh_visual_evidence else "native_audio_name_uncertain" if verification_scope == "name_spelling_only"
                        else "director_video_review_blocked")
                    or decision.get("video_sha256") != video_sha256
                    or not any(item.get("sha256") == video_sha256
                        for item in json.loads(take["output_hashes_json"]))
                    or not (subject_limit_evidence_gap(decision) if refresh_visual_evidence else name_spelling_is_only_audio_issue(decision.get("native_audio") or {}, decision.get("criteria") or [])
                        if verification_scope == "name_spelling_only" else matching_dialogue_audio_uncertainty(decision))):
                raise LedgerConflict("Verification is limited to the exact registered scoped audio hold.")
            claim = db.execute("SELECT * FROM production_video_director_review_claims WHERE job_id=?",
                (take["job_id"],)).fetchone()
            if claim and claim["lease_until"] > now:
                raise LedgerConflict("Director review is still owned by a worker.")
            if claim and int(claim["attempt_count"] or 0) >= 3:
                raise LedgerConflict("Director video review retry budget is exhausted.")
            self._event(db, project_id=project_id, run_id=run_id, job_id=take["job_id"],
                event_type="director_video_human_audio_verification_recorded",
                payload={"take_id": take_id, "archived_review": self._video_review_row(review),
                    "verification": verification, "refresh_visual_evidence": refresh_visual_evidence, "render_resubmitted": False})
            db.execute("DELETE FROM production_video_director_reviews WHERE job_id=? AND review_id=?",
                (take["job_id"], review_id))
            db.commit()
        return verification

    def reopen_speaker_uncertain_review_with_human_verification(self, *, project_id: str,
            run_id: str, take_id: str, review_id: str, video_sha256: str,
            statement: str, authorize_one_extra_attempt: bool = False) -> dict[str, Any]:
        """One explicitly confirmed speaker review; retain every spent claim/decision."""
        from story_builder.services.production_video_director import speaker_uncertainty_with_accepted_pronunciation
        if authorize_one_extra_attempt is not True:
            raise ValueError("Explicit authorization for one additional evidence-only review is required.")
        if not isinstance(statement, str) or not 0 < len(statement.strip()) <= 1200:
            raise ValueError("An exact-clip human speaker confirmation is required.")
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            take = db.execute("SELECT * FROM production_takes WHERE project_id=? AND run_id=? AND take_id=?",
                (project_id, run_id, take_id)).fetchone()
            if take is None:
                raise LedgerNotFound("Take not found in this project and run.")
            review = db.execute("SELECT * FROM production_video_director_reviews WHERE job_id=? AND review_id=?",
                (take["job_id"], review_id)).fetchone()
            if review is None:
                raise LedgerConflict("The exact speaker hold is no longer current.")
            decision = json.loads(review["decision_json"])
            if (take["status"] != "needs_review" or review["resolution_status"] != "blocked"
                    or json.loads(review["error_json"] or '{}').get("code") != "director_video_review_blocked"
                    or review["retake_take_id"] or decision.get("video_sha256") != video_sha256
                    or not any(item.get("sha256") == video_sha256 for item in json.loads(take["output_hashes_json"]))
                    or not speaker_uncertainty_with_accepted_pronunciation(decision)):
                raise LedgerConflict("Only the exact registered speaker-evidence hold with accepted pronunciation can reopen.")
            claim = db.execute("SELECT * FROM production_video_director_review_claims WHERE job_id=?",
                (take["job_id"],)).fetchone()
            if not claim or claim["lease_until"] > now or int(claim["attempt_count"] or 0) != 3:
                raise LedgerConflict("Review is owned or is outside the one extra claim boundary.")
            if db.execute("SELECT 1 FROM production_events WHERE job_id=? AND "
                    "event_type='director_video_human_speaker_reassessment'", (take["job_id"],)).fetchone():
                raise LedgerConflict("Human speaker reassessment is already spent.")
            verification = {"source": "human_native_audio_review", "confirmed": True,
                "video_sha256": video_sha256, "statement": statement.strip(), "recorded_at": now,
                "scope": "speaker_with_accepted_pronunciation",
                "prior_pronunciation_verification": decision["audio_verification"]}
            payload = {"take_id": take_id, "archived_review": self._video_review_row(review),
                "verification": verification, "render_resubmitted": False, "review_attempt_ceiling": 4}
            self._event(db, project_id=project_id, run_id=run_id, job_id=take["job_id"],
                event_type="director_video_human_speaker_reassessment", payload=payload)
            self._event(db, project_id=project_id, run_id=run_id, job_id=take["job_id"],
                event_type="director_video_human_audio_verification_recorded", payload=payload)
            db.execute("DELETE FROM production_video_director_reviews WHERE job_id=? AND review_id=?",
                (take["job_id"], review_id))
            db.commit()
        return verification

    def human_audio_review_evidence(self, *, project_id: str, run_id: str, job_id: str) -> dict[str, Any] | None:
        """Load durable confirmation directly, independent of the 500-event public window."""
        with self._connect() as db:
            row = db.execute("SELECT payload_json FROM production_events WHERE project_id=? AND run_id=? "
                "AND job_id=? AND event_type='director_video_human_audio_verification_recorded' "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1", (project_id, run_id, job_id)).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def reopen_contradictory_count_review(self, *, project_id: str, run_id: str,
            take_id: str, review_id: str, video_sha256: str, observation: str) -> None:
        """One explicit evidence recheck within the ordinary budget; never accept/render."""
        from story_builder.services.production_video_director import contradictory_group_evidence_only
        if not isinstance(observation, str) or not 0 < len(observation.strip()) <= 1200:
            raise ValueError("An exact-clip inspection observation is required.")
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            take = db.execute("SELECT * FROM production_takes WHERE project_id=? AND run_id=? AND take_id=?",
                (project_id, run_id, take_id)).fetchone()
            if take is None:
                raise LedgerNotFound("Take not found in this project and run.")
            review = db.execute("SELECT * FROM production_video_director_reviews WHERE job_id=? AND review_id=?",
                (take["job_id"], review_id)).fetchone()
            if review is None:
                raise LedgerConflict("The exact evidence hold is no longer current.")
            decision = json.loads(review["decision_json"])
            error = json.loads(review["error_json"] or '{}')
            if (take["status"] != "needs_review" or review["resolution_status"] != "blocked"
                    or error.get("code") != "native_video_evidence_uncertain"
                    or decision.get("video_sha256") != video_sha256
                    or not any(row.get("sha256") == video_sha256 for row in json.loads(take["output_hashes_json"]))
                    or not contradictory_group_evidence_only(decision) or review["retake_take_id"]):
                raise LedgerConflict("Only an exact registered contradictory-count hold can be rechecked.")
            claim = db.execute("SELECT * FROM production_video_director_review_claims WHERE job_id=?", (take["job_id"],)).fetchone()
            if claim and (claim["lease_until"] > now or int(claim["attempt_count"] or 0) >= 3):
                raise LedgerConflict("Review is owned or its ordinary three-attempt budget is exhausted.")
            if db.execute("SELECT 1 FROM production_events WHERE job_id=? AND event_type='director_video_count_evidence_reassessment'",
                    (take["job_id"],)).fetchone():
                raise LedgerConflict("Count evidence reassessment is already spent.")
            self._event(db, project_id=project_id, run_id=run_id, job_id=take["job_id"],
                event_type="director_video_count_evidence_reassessment", payload={"take_id": take_id,
                    "archived_review": self._video_review_row(review), "observation": observation.strip(),
                    "render_resubmitted": False, "review_attempt_ceiling": 3})
            db.execute("DELETE FROM production_video_director_reviews WHERE job_id=? AND review_id=?", (take["job_id"], review_id))
            db.commit()

    def reopen_incomplete_reference_review(self, *, project_id: str, run_id: str,
            take_id: str, review_id: str, video_sha256: str,
            reference_evidence: list[dict[str, Any]]) -> None:
        """One explicit reassessment after missing master evidence is supplied.

        Archive the old hold and keep the render and review-attempt history.
        The ordinary three review attempts remain; only this evidenced operator
        recovery permits one additional claim, never a second reassessment.
        """
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            take = db.execute("SELECT * FROM production_takes WHERE project_id=? AND run_id=? AND take_id=?",
                (project_id, run_id, take_id)).fetchone()
            if take is None:
                raise LedgerNotFound("Take not found in this project and run.")
            review = db.execute("SELECT * FROM production_video_director_reviews WHERE job_id=? AND review_id=?",
                (take["job_id"], review_id)).fetchone()
            if review is None:
                raise LedgerConflict("The exact reference evidence hold is no longer current.")
            decision = json.loads(review["decision_json"])
            images = (json.loads(take["input_snapshot_json"]).get("validation_request") or {}).get("images") or []
            if (take["status"] != "needs_review" or review["resolution_status"] != "blocked"
                    or decision.get("action") != "blocked" or decision.get("reference_evidence")
                    or decision.get("video_sha256") != video_sha256
                    or not any(item.get("sha256") == video_sha256 for item in json.loads(take["output_hashes_json"]))
                    or not 1 <= len(images) == len(reference_evidence) <= 9):
                raise LedgerConflict("Only a registered clip held without its selected reference evidence may be reassessed.")
            for image, evidence in zip(images, reference_evidence):
                frame = evidence.get("observed_features") or {}
                if (image.get("asset_id") != evidence.get("asset_id")
                        or not isinstance(evidence.get("sha256"), str) or len(evidence["sha256"]) != 64
                        or frame.get("evidence_valid") is not True or not frame.get("summary")):
                    raise LedgerConflict("Complete observed evidence for each exact selected reference is required.")
            if db.execute("SELECT 1 FROM production_events WHERE job_id=? AND "
                    "event_type='director_video_reference_evidence_reassessment'", (take["job_id"],)).fetchone():
                raise LedgerConflict("Reference evidence reassessment is already spent.")
            claim = db.execute("SELECT * FROM production_video_director_review_claims WHERE job_id=?",
                (take["job_id"],)).fetchone()
            if claim and (claim["lease_until"] > now or int(claim["attempt_count"] or 0) >= 4):
                raise LedgerConflict("Review is owned or its bounded reassessment budget is exhausted.")
            self._event(db, project_id=project_id, run_id=run_id, job_id=take["job_id"],
                event_type="director_video_reference_evidence_reassessment", payload={"take_id": take_id,
                    "archived_review": self._video_review_row(review), "reference_evidence": reference_evidence,
                    "review_attempt_ceiling": max(3, int(claim["attempt_count"] or 0) + 1) if claim else 3,
                    "render_resubmitted": False})
            db.execute("DELETE FROM production_video_director_reviews WHERE job_id=? AND review_id=?",
                (take["job_id"], review_id))
            db.commit()

    def record_director_video_review(self, *, take: dict[str, Any], decision: dict[str, Any],
                                     owner_token: str | None = None) -> dict[str, Any]:
        """Persist an immutable decision before any acceptance/retake side effect."""
        encoded = json.dumps(decision, sort_keys=True, ensure_ascii=False)
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM production_takes WHERE project_id=? AND run_id=? "
                "AND take_id=? AND job_id=? AND status='needs_review'",
                (take["project_id"], take["run_id"], take["take_id"], take["job_id"])).fetchone()
            if row is None:
                raise LedgerConflict("Director review does not match a completed take awaiting review.")
            if owner_token is not None:
                claim = db.execute("SELECT owner_token,lease_until FROM production_video_director_review_claims WHERE job_id=?",
                    (take["job_id"],)).fetchone()
                if claim is None or claim["owner_token"] != owner_token or claim["lease_until"] <= now:
                    raise LedgerConflict("Director video review lease expired or belongs to another worker.")
            existing = db.execute("SELECT * FROM production_video_director_reviews WHERE job_id=?",
                (take["job_id"],)).fetchone()
            if existing:
                if existing["decision_json"] != encoded:
                    raise LedgerConflict("Director video review decision is immutable.")
                db.commit()
                return self._video_review_row(existing)
            review_id = str(uuid.uuid4())
            db.execute("""INSERT INTO production_video_director_reviews
                (review_id,job_id,project_id,run_id,take_id,decision_json,resolution_status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,'pending',?,?)""",
                (review_id, take["job_id"], take["project_id"], take["run_id"], take["take_id"], encoded, now, now))
            self._event(db, project_id=take["project_id"], run_id=take["run_id"], job_id=take["job_id"],
                event_type="director_video_decision_recorded", payload={"review_id": review_id,
                    "take_id": take["take_id"], "action": decision.get("action")})
            saved = db.execute("SELECT * FROM production_video_director_reviews WHERE review_id=?", (review_id,)).fetchone()
            db.commit()
            return self._video_review_row(saved)

    @staticmethod
    def _video_review_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result["decision"] = json.loads(result.pop("decision_json"))
        result["error"] = json.loads(result.pop("error_json")) if result.get("error_json") else None
        result.pop("error_json", None)
        return result

    def unresolved_director_video_reviews(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM production_video_director_reviews WHERE resolution_status='pending' "
                "ORDER BY created_at LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
        return [self._video_review_row(row) for row in rows]

    def resolve_director_video_review(self, *, job_id: str, status: str,
                                      retake_take_id: str | None = None,
                                      error: dict[str, Any] | None = None) -> dict[str, Any]:
        if status not in {"accepted", "retake_queued", "blocked", "rejected"}:
            raise ValueError("Invalid Director video review resolution status.")
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM production_video_director_reviews WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise LedgerNotFound("Director video review was not found.")
            current = row["resolution_status"]
            if current not in {"pending", status}:
                raise LedgerConflict("Director video review has already been resolved differently.")
            db.execute("UPDATE production_video_director_reviews SET resolution_status=?, "
                "retake_take_id=COALESCE(?,retake_take_id),error_json=?,updated_at=? WHERE job_id=?",
                (status, retake_take_id, json.dumps(error, sort_keys=True) if error else None, now, job_id))
            saved = db.execute("SELECT * FROM production_video_director_reviews WHERE job_id=?", (job_id,)).fetchone()
            db.commit()
        return self._video_review_row(saved)

    def set_take_outputs(self, *, project_id: str, take_id: str,
                         outputs: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(outputs, list) or any(not isinstance(row, dict) for row in outputs):
            raise ValueError("outputs must be a list of object records")
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM production_takes WHERE project_id=? AND take_id=?", (project_id, take_id)).fetchone()
            if not row:
                raise LedgerNotFound("Take not found in this project.")
            if row["status"] not in {"collecting", "needs_review", "cancel_requested"}:
                raise LedgerConflict("Outputs can be attached only while collecting or reviewing a take.")
            encoded = json.dumps(outputs, sort_keys=True, ensure_ascii=False)
            db.execute("UPDATE production_takes SET output_hashes_json=?, updated_at=? WHERE job_id=?",
                       (encoded, now, row["job_id"]))
            self._event(db, project_id=project_id, run_id=row["run_id"], job_id=row["job_id"],
                        event_type="take_outputs_registered", payload={"count": len(outputs), "outputs": outputs})
            updated = db.execute("SELECT * FROM production_takes WHERE job_id=?", (row["job_id"],)).fetchone()
            db.commit()
            return self._row(updated)

    def reconcile_remote_state(self, *, project_id: str, take_id: str, observed: str,
                               details: dict[str, Any] | None = None) -> dict[str, Any]:
        """Record a ComfyUI observation without triggering another submission."""
        targets = {"pending", "running", "success", "error", "absent"}
        if observed not in targets:
            raise ValueError(f"Unsupported ComfyUI observation: {observed}")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM production_takes WHERE project_id=? AND take_id=?", (project_id, take_id)).fetchone()
            if not row:
                raise LedgerNotFound("Take not found in this project.")
            current = row["status"]
            target = {
                "pending": current if current in {"running", "cancel_requested"} else "submitting",
                "running": "cancel_requested" if current == "cancel_requested" else "running",
                "success": "collecting",
                "error": "cancelled" if current == "cancel_requested" and
                    (details or {}).get("execution_interrupted") is True else "failed",
                "absent": "recovery_required",
            }[observed]
            # Restart reconciliation can observe the same remote state on
            # every supervisor pass. Treat an unchanged observation as a
            # read: writing an event/updated_at on each pass caused unbounded
            # WAL growth and a busy-looping worker to monopolize SQLite.
            if target == current:
                db.commit()
                return self._row(row)
            if target != current and target not in ALLOWED_TRANSITIONS.get(current, set()):
                if not (current == "collecting" and target == "failed"):
                    raise LedgerConflict(f"Observed ComfyUI state {observed} conflicts with ledger state {current}.")
            now = _now()
            error_json = json.dumps(details or {"code": "comfy_prompt_failed"}, ensure_ascii=False) if target == "failed" else row["error_json"]
            terminal = target in {"failed", "cancelled"}
            finished_at = now if terminal else row["finished_at"]
            db.execute("UPDATE production_takes SET status=?, updated_at=?, heartbeat_at=?, finished_at=?, error_json=?, lease_owner=?, lease_until=? WHERE job_id=?",
                       (target, now, now, finished_at, error_json,
                        None if terminal else row["lease_owner"],
                        None if terminal else row["lease_until"], row["job_id"]))
            self._event(db, project_id=project_id, run_id=row["run_id"], job_id=row["job_id"],
                        event_type="comfy_state_reconciled", payload={"observed": observed, "status": target, **(details or {})})
            updated = db.execute("SELECT * FROM production_takes WHERE job_id=?", (row["job_id"],)).fetchone()
            db.commit()
            return self._row(updated)

    def heartbeat(self, *, project_id: str, take_id: str, lease_owner: str, lease_seconds: int = 60) -> dict[str, Any]:
        if lease_seconds < 1 or lease_seconds > 3600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        until = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self._connect() as db:
            cursor = db.execute("UPDATE production_takes SET lease_owner=?, lease_until=?, heartbeat_at=?, updated_at=? WHERE project_id=? AND take_id=? AND status IN ('submitting','running','collecting')",
                                (lease_owner, until, now.isoformat(), now.isoformat(), project_id, take_id))
            if cursor.rowcount != 1:
                raise LedgerNotFound("Active take not found in this project; heartbeat was not recorded.")
            row = db.execute("SELECT * FROM production_takes WHERE project_id=? AND take_id=?", (project_id, take_id)).fetchone()
            return self._row(row)

    def get_run(self, *, project_id: str, run_id: str, event_limit: int = 500) -> dict[str, Any]:
        """Load a run and its latest events without materializing unbounded history."""
        bounded_event_limit = max(1, min(5000, int(event_limit)))
        with self._connect() as db:
            row = db.execute("SELECT * FROM production_runs WHERE project_id=? AND run_id=?", (project_id, run_id)).fetchone()
            if not row:
                raise LedgerNotFound("Production run not found in this project.")
            result = self._row(row)
            result["takes"] = [self._row(item) for item in db.execute("SELECT * FROM production_takes WHERE project_id=? AND run_id=? ORDER BY created_at, take_id", (project_id, run_id)).fetchall()]
            for take in result["takes"]:
                review = db.execute("SELECT * FROM production_video_director_reviews WHERE job_id=?",
                    (take["job_id"],)).fetchone()
                public_review = self._video_review_row(review)
                if public_review and public_review["resolution_status"] == "pending":
                    claim = db.execute("SELECT lease_until,attempt_count FROM production_video_director_review_claims WHERE job_id=?",
                        (take["job_id"],)).fetchone()
                    if claim and claim["lease_until"] > _now():
                        public_review["resolution_status"] = "reviewing"
                        public_review["attempt_count"] = int(claim["attempt_count"] or 0)
                        public_review["lease_until"] = claim["lease_until"]
                    elif claim:
                        public_review["resolution_status"] = "review_recovery_pending"
                        public_review["attempt_count"] = int(claim["attempt_count"] or 0)
                take["director_review"] = public_review
            recent_events = db.execute(
                "SELECT * FROM production_events WHERE project_id=? AND run_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (project_id, run_id, bounded_event_limit + 1),
            ).fetchall()
            result["event_history_truncated"] = len(recent_events) > bounded_event_limit
            window = sorted(recent_events[:bounded_event_limit], key=lambda item: (item["created_at"], item["event_id"]))
            result["events"] = [self._event_row(item) for item in window]
            return result

    def list_runs(self, *, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """List recent project-scoped run snapshots without loading their take/event histories."""
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id is required")
        bounded_limit = max(1, min(200, int(limit)))
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM production_runs WHERE project_id=? ORDER BY created_at DESC,run_id DESC LIMIT ?",
                (project_id.strip(), bounded_limit),
            ).fetchall()
        return [self._row(row) for row in rows]

    def record_run_event(self, *, project_id: str, run_id: str, event_type: str,
                         payload: dict[str, Any], dedupe_key: str | None = None) -> dict[str, Any]:
        """Append an event; an optional run/type/key identity retains its first payload.

        Deduplication uses the primary key under the write transaction, never
        the bounded event window returned to the UI. No schema change is needed.
        """
        if not event_type or not isinstance(payload, dict):
            raise ValueError("event_type and an object payload are required")
        if dedupe_key is not None and (not isinstance(dedupe_key, str) or not dedupe_key.strip()):
            raise ValueError("dedupe_key must be a non-empty string")
        event_id = (str(uuid.uuid5(uuid.NAMESPACE_URL,
            json.dumps([project_id, run_id, event_type, dedupe_key], ensure_ascii=False)))
            if dedupe_key is not None else None)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            exists = db.execute("SELECT 1 FROM production_runs WHERE project_id=? AND run_id=?",
                                (project_id, run_id)).fetchone()
            if not exists:
                raise LedgerNotFound("Production run not found in this project.")
            if event_id is None:
                self._event(db, project_id=project_id, run_id=run_id,
                            event_type=event_type, payload=payload)
            else:
                db.execute("INSERT OR IGNORE INTO production_events "
                    "(event_id,project_id,run_id,job_id,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?,?)",
                    (event_id, project_id, run_id, None, event_type, json.dumps(payload, sort_keys=True), _now()))
            row = db.execute("SELECT * FROM production_runs WHERE project_id=? AND run_id=?",
                             (project_id, run_id)).fetchone()
            db.commit()
            return self._row(row)

    def save_shot_composer_draft(self, *, project_id: str, run_id: str, shot_id: str,
                                 expected_revision: int, shot_plan_revision_id: str,
                                 draft: dict[str, Any]) -> dict[str, Any]:
        """Persist one optimistic composer revision and hold changed queued children atomically."""
        if (not shot_id or not shot_plan_revision_id or expected_revision < 0
                or not isinstance(draft, dict)):
            raise ValueError("shot_id, shot-plan revision, nonnegative draft revision, and object draft are required")
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = db.execute("SELECT 1 FROM production_runs WHERE project_id=? AND run_id=?",
                (project_id, run_id)).fetchone()
            if not run:
                raise LedgerNotFound("Production run not found in this project.")
            prior_events = db.execute("SELECT payload_json FROM production_events WHERE project_id=? AND run_id=? "
                "AND event_type='shot_composer_draft_saved' ORDER BY created_at, event_id", (project_id, run_id)).fetchall()
            prior = None
            for event in prior_events:
                payload = json.loads(event["payload_json"])
                if (payload.get("shot_id") == shot_id and
                        (prior is None or int(payload.get("revision", 0)) > int(prior.get("revision", 0)))):
                    prior = payload
            current_revision = int(prior.get("revision", 0)) if prior else 0
            if expected_revision != current_revision:
                raise LedgerConflict("This shot draft changed in another tab. Reload before saving to avoid overwriting it.")
            revision = current_revision + 1
            payload = {"shot_id": shot_id, "revision": revision,
                "shot_plan_revision_id": shot_plan_revision_id, "draft": draft, "saved_at": now}
            self._event(db, project_id=project_id, run_id=run_id,
                event_type="shot_composer_draft_saved", payload=payload)

            changed_children: list[str] = []
            children = db.execute("SELECT * FROM production_takes WHERE project_id=? AND run_id=? AND shot_id=? "
                "AND status IN ('queued','waiting_for_predecessor')", (project_id, run_id, shot_id)).fetchall()
            for child in children:
                snapshot = json.loads(child["input_snapshot_json"])
                frozen = snapshot.get("validation_request")
                if not isinstance(frozen, dict):
                    continue
                unchanged = (shot_plan_revision_id == snapshot.get("shot_plan_revision_id")
                    and stable_hash(draft) == stable_hash(frozen))
                if unchanged:
                    continue
                cursor = db.execute("UPDATE production_takes SET status='waiting_for_user', updated_at=? "
                    "WHERE job_id=? AND status IN ('queued','waiting_for_predecessor')", (now, child["job_id"]))
                if cursor.rowcount:
                    changed_children.append(child["take_id"])
                    self._event(db, project_id=project_id, run_id=run_id, job_id=child["job_id"],
                        event_type="child_draft_changed_after_queue", payload={
                            "shot_id": shot_id, "take_id": child["take_id"],
                            "frozen_input_hash": child["input_hash"], "saved_draft_hash": stable_hash(draft),
                            "status": "waiting_for_user"})
            db.commit()
            return {"shot_id": shot_id, "revision": revision, "draft": draft,
                "shot_plan_revision_id": shot_plan_revision_id, "stale": False,
                "saved_at": now, "held_child_take_ids": changed_children}

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        for key in ("config_json", "input_snapshot_json", "output_hashes_json"):
            if key in value and value[key] is not None:
                target = key.removesuffix("_json")
                value[target] = json.loads(value[key])
                del value[key]
        if "error_json" in value:
            value["error"] = json.loads(value["error_json"]) if value["error_json"] else None
            del value["error_json"]
        # A completed take's current error is resolved even if an older
        # database still contains the failure JSON from a prior attempt.
        # Keep this projection scoped to the take row; review records retain
        # their own independent error field.
        if "take_id" in value and value.get("status") in {"needs_review", "accepted"}:
            value["error"] = None
        return value

    @staticmethod
    def _event_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["payload"] = json.loads(value.pop("payload_json"))
        return value
