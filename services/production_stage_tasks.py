"""Durable, idempotent queue for text-stage work in Production V2.

Tasks contain request metadata, never media bytes. A worker crash leaves an
expired claim in ``recovery_required``; startup does not silently duplicate
provider inference. An operator can explicitly enqueue a new attempt with a
new idempotency key after inspecting the run.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class StageTaskConflict(ValueError):
    """An idempotency key or task transition conflicts with durable state."""


class ProductionStageTaskStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS production_stage_tasks (
                task_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                request_json TEXT NOT NULL,
                status TEXT NOT NULL,
                owner_token TEXT,
                lease_until TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                result_json TEXT,
                error_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, run_id, stage, idempotency_key)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS production_stage_tasks_queue_idx "
                       "ON production_stage_tasks(status, created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS production_stage_tasks_run_idx "
                       "ON production_stage_tasks(project_id, run_id, created_at)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 30000")
        return db

    @contextmanager
    def execution_lock(self, task_id: str):
        """Fence live execution from operator recovery, across backend processes.

        The kernel releases this lock on process exit. Lease expiry alone never
        proves that a provider call or its output writer has stopped.
        """
        try:
            safe_id = str(uuid.UUID(task_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise StageTaskConflict("Invalid stage task ID.") from exc
        root = self.path.parent / "stage_execution_locks"
        root.mkdir(parents=True, exist_ok=True)
        with (root / f"{safe_id}.lock").open("a") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StageTaskConflict("The task's execution is still active; wait for it to exit before recovery.") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        for source, target in (("request_json", "request"), ("result_json", "result"),
                               ("error_json", "error")):
            raw = value.pop(source, None)
            value[target] = json.loads(raw) if raw else None
        return value

    def enqueue(self, *, project_id: str, run_id: str, stage: str,
                idempotency_key: str, request: dict[str, Any]) -> dict[str, Any]:
        if not all(isinstance(item, str) and item.strip() for item in
                   (project_id, run_id, stage, idempotency_key)):
            raise ValueError("project_id, run_id, stage, and idempotency_key are required")
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        request_json = json.dumps(request, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        now = self._iso(self._now())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM production_stage_tasks WHERE project_id=? AND run_id=? "
                "AND stage=? AND idempotency_key=?", (project_id, run_id, stage, idempotency_key)).fetchone()
            if existing:
                if existing["request_hash"] != digest:
                    raise StageTaskConflict("Idempotency key already belongs to a different stage request.")
                db.commit()
                return self._row(existing)  # type: ignore[return-value]
            active = db.execute("SELECT task_id,status FROM production_stage_tasks WHERE project_id=? AND run_id=? "
                "AND stage=? AND status IN ('queued','running','recovery_required') ORDER BY created_at LIMIT 1",
                (project_id, run_id, stage)).fetchone()
            if active:
                raise StageTaskConflict(f"Stage already has task {active['task_id']} in {active['status']} state; "
                    "inspect or reconcile it before starting another attempt.")
            task_id = str(uuid.uuid4())
            db.execute("INSERT INTO production_stage_tasks(task_id,project_id,run_id,stage,idempotency_key,"
                "request_hash,request_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (task_id, project_id, run_id, stage, idempotency_key, digest, request_json, "queued", now, now))
            row = db.execute("SELECT * FROM production_stage_tasks WHERE task_id=?", (task_id,)).fetchone()
            db.commit()
            return self._row(row)  # type: ignore[return-value]

    def get(self, *, project_id: str, run_id: str, task_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM production_stage_tasks WHERE project_id=? AND run_id=? AND task_id=?",
                             (project_id, run_id, task_id)).fetchone()
            if row and row["status"] == "running" and row["lease_until"] and row["lease_until"] <= self._iso(self._now()):
                error = json.dumps({"code": "stage_task_lease_expired",
                    "message": "The worker lease expired before a durable result was recorded. Inspect the run before explicitly retrying."})
                db.execute("UPDATE production_stage_tasks SET status='recovery_required',error_json=?,updated_at=? "
                    "WHERE task_id=? AND status='running' AND lease_until<=?",
                    (error, self._iso(self._now()), task_id, self._iso(self._now())))
                row = db.execute("SELECT * FROM production_stage_tasks WHERE task_id=?", (task_id,)).fetchone()
            db.commit()
            return self._row(row)

    def list_run(self, *, project_id: str, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT task_id FROM production_stage_tasks WHERE project_id=? AND run_id=? "
                              "ORDER BY created_at,task_id", (project_id, run_id)).fetchall()
        return [task for row in rows if (task := self.get(project_id=project_id, run_id=run_id,
                                                          task_id=row["task_id"])) is not None]

    def queued(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM production_stage_tasks WHERE status='queued' "
                              "ORDER BY created_at,task_id LIMIT ?", (max(1, min(100, limit)),)).fetchall()
        return [self._row(row) for row in rows if row is not None]  # type: ignore[list-item]

    def controller_candidates(self, *, limit: int = 100) -> list[tuple[str, str]]:
        """Runs with prior work that may need an idempotent progression step."""
        with self._connect() as db:
            rows = db.execute("SELECT DISTINCT project_id,run_id,MAX(updated_at) AS touched "
                "FROM production_stage_tasks WHERE stage='story_detail' OR stage LIKE 'controller:%' "
                "OR stage LIKE 'text:%' GROUP BY project_id,run_id ORDER BY touched DESC LIMIT ?",
                (max(1, min(500, limit)),)).fetchall()
        return [(str(row["project_id"]), str(row["run_id"])) for row in rows]

    def get_by_id(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM production_stage_tasks WHERE task_id=?", (task_id,)).fetchone()
        if row and row["status"] == "running" and row["lease_until"] and row["lease_until"] <= self._iso(self._now()):
            return self.get(project_id=row["project_id"], run_id=row["run_id"], task_id=task_id)
        return self._row(row)

    def claim_next(self, *, owner_token: str, lease_seconds: int = 300) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT task_id FROM production_stage_tasks WHERE status='queued' "
                             "ORDER BY created_at,task_id LIMIT 1").fetchone()
        return self.claim(task_id=row["task_id"], owner_token=owner_token,
                          lease_seconds=lease_seconds) if row else None

    def claim(self, *, task_id: str, owner_token: str, lease_seconds: int = 3600) -> dict[str, Any] | None:
        if not owner_token.strip() or lease_seconds < 1:
            raise ValueError("owner_token and a positive lease are required")
        now = self._now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM production_stage_tasks WHERE task_id=?", (task_id,)).fetchone()
            if not row or row["status"] != "queued":
                db.commit()
                return None
            db.execute("UPDATE production_stage_tasks SET status='running',owner_token=?,lease_until=?,"
                "attempt_count=attempt_count+1,error_json=NULL,updated_at=? WHERE task_id=? AND status='queued'",
                (owner_token, self._iso(now + timedelta(seconds=lease_seconds)), self._iso(now), task_id))
            claimed = db.execute("SELECT * FROM production_stage_tasks WHERE task_id=?", (task_id,)).fetchone()
            db.commit()
            return self._row(claimed)

    def heartbeat(self, *, task_id: str, owner_token: str, lease_seconds: int = 3600) -> bool:
        now = self._now()
        with self._connect() as db:
            cursor = db.execute("UPDATE production_stage_tasks SET lease_until=?,updated_at=? "
                "WHERE task_id=? AND status='running' AND owner_token=?",
                (self._iso(now + timedelta(seconds=lease_seconds)), self._iso(now), task_id, owner_token))
            return cursor.rowcount == 1

    def complete(self, *, task_id: str, owner_token: str, result: dict[str, Any]) -> dict[str, Any]:
        return self._settle(task_id=task_id, owner_token=owner_token, status="completed", value=result)

    def fail(self, *, task_id: str, owner_token: str, error: dict[str, Any]) -> dict[str, Any]:
        return self._settle(task_id=task_id, owner_token=owner_token, status="failed", value=error)

    def resolve_recovery(self, *, project_id: str, run_id: str, task_id: str,
                         confirm_no_durable_result: bool) -> dict[str, Any]:
        """Explicitly close an ambiguous expired task after operator inspection.

        This does not replay work. A later retry must use a new idempotency key.
        """
        if confirm_no_durable_result is not True:
            raise StageTaskConflict("Explicit confirmation that no durable result exists is required.")
        now = self._iso(self._now())
        with self.execution_lock(task_id), self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT stage FROM production_stage_tasks WHERE project_id=? AND run_id=? AND task_id=? AND status='recovery_required'",
                (project_id, run_id, task_id)).fetchone()
            if existing is None:
                raise StageTaskConflict("Task is not awaiting recovery in this project and run.")
            task_stage = str(existing["stage"])
            retryable = task_stage.startswith(("controller:", "text:"))
            error = json.dumps({"code": "stage_task_reconciled_without_result",
                "message": "An operator inspected the run and confirmed no durable result; a new attempt may be enqueued with a new idempotency key.",
                "retryable": retryable})
            cursor = db.execute("UPDATE production_stage_tasks SET status='failed',error_json=?,owner_token=NULL,"
                "lease_until=NULL,updated_at=? WHERE project_id=? AND run_id=? AND task_id=? AND status='recovery_required'",
                (error, now, project_id, run_id, task_id))
            if cursor.rowcount != 1:
                raise StageTaskConflict("Task is not awaiting recovery in this project and run.")
            row = db.execute("SELECT * FROM production_stage_tasks WHERE task_id=?", (task_id,)).fetchone()
            db.commit()
            return self._row(row)  # type: ignore[return-value]

    def complete_recovery(self, *, project_id: str, run_id: str, task_id: str,
                          result: dict[str, Any]) -> dict[str, Any]:
        """Settle a verified durable result after a worker crashed before commit."""
        if not isinstance(result, dict) or not result.get("revision_id"):
            raise ValueError("A reconciled canonical revision ID is required.")
        now = self._iso(self._now())
        encoded = json.dumps(result, sort_keys=True, ensure_ascii=False)
        with self.execution_lock(task_id), self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute("UPDATE production_stage_tasks SET status='completed',result_json=?,error_json=NULL,"
                "owner_token=NULL,lease_until=NULL,updated_at=? WHERE project_id=? AND run_id=? AND task_id=? "
                "AND status='recovery_required'", (encoded, now, project_id, run_id, task_id))
            if cursor.rowcount != 1:
                raise StageTaskConflict("Task is not awaiting recovery in this project and run.")
            row = db.execute("SELECT * FROM production_stage_tasks WHERE task_id=?", (task_id,)).fetchone()
            db.commit()
            return self._row(row)  # type: ignore[return-value]

    def _settle(self, *, task_id: str, owner_token: str, status: str,
                value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("terminal value must be a JSON object")
        now = self._iso(self._now())
        column = "result_json" if status == "completed" else "error_json"
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(f"UPDATE production_stage_tasks SET status=?,{column}=?,owner_token=NULL,"
                "lease_until=NULL,updated_at=? WHERE task_id=? AND status IN ('running','recovery_required') AND owner_token=?",
                (status, json.dumps(value, sort_keys=True, ensure_ascii=False), now, task_id, owner_token))
            if cursor.rowcount != 1:
                raise StageTaskConflict("Stage task is no longer owned by this worker.")
            row = db.execute("SELECT * FROM production_stage_tasks WHERE task_id=?", (task_id,)).fetchone()
            db.commit()
            return self._row(row)  # type: ignore[return-value]
