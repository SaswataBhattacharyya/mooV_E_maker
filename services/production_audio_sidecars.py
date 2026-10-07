"""Durable optional audio queue with idempotency and exact-prompt recovery."""
from __future__ import annotations

import fcntl
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class SidecarConflict(ValueError):
    pass


class AudioSidecarStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, run_id TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL, job TEXT NOT NULL, UNIQUE(project_id, run_id, request_key))")

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def enqueue(self, project_id, run_id, key, request, job):
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT request_hash, job FROM jobs WHERE project_id=? AND run_id=? AND request_key=?", (project_id, run_id, key)).fetchone()
            if row:
                if row[0] != digest:
                    raise SidecarConflict("Idempotency key already belongs to a different audio request.")
                return json.loads(row[1])
            job = {**job, "project_id": project_id, "production_run_id": run_id, "idempotency_key": key}
            connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?)", (job["job_id"], project_id, run_id, key, digest, json.dumps(job)))
            return job

    def get(self, project_id, run_id, job_id):
        with self.connect() as connection:
            row = connection.execute("SELECT job FROM jobs WHERE project_id=? AND run_id=? AND job_id=?", (project_id, run_id, job_id)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, job):
        with self.connect() as connection:
            connection.execute("UPDATE jobs SET job=? WHERE job_id=? AND project_id=? AND run_id=?", (json.dumps(job), job["job_id"], job["project_id"], job["production_run_id"]))

    def unsettled(self):
        with self.connect() as connection:
            rows = connection.execute("SELECT job FROM jobs").fetchall()
        return [job for row in rows if (job := json.loads(row[0])).get("status") in {"queued", "preparing", "running", "submitting", "recovery_required"}
                or (job.get("status") == "completed" and not job.get("production_asset_id"))]

    @contextmanager
    def own(self, job_id):
        safe = hashlib.sha256(job_id.encode()).hexdigest()
        with (self.path.parent / f".audio-sidecar-{safe}.lock").open("a+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
