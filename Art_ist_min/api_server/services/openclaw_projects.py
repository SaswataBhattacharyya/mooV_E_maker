"""Project storage and orchestration state for the website planning flow."""

from __future__ import annotations

import json
import shutil
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_TYPES = ("story", "characters", "scenes", "subscenes", "dialogue", "image_jobs")
UNSET = object()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_slug(value: str) -> str:
    clean = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in clean:
        clean = clean.replace("--", "-")
    return clean.strip("-") or "project"


def _default_project_state(
    *,
    project_id: str,
    title: str,
    story_input: str,
    automation_mode: bool,
) -> dict[str, Any]:
    artifacts = {
        artifact_type: {
            "type": artifact_type,
            "status": "pending",
            "path": f"artifacts/{artifact_type}.json",
            "updated_at": None,
            "content": None,
        }
        for artifact_type in ARTIFACT_TYPES
    }
    return {
        "id": project_id,
        "title": title,
        "story_input": story_input,
        "automation_mode": automation_mode,
        "status": "draft",
        "current_stage": "story",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "runtime": {
            "job_id": None,
            "state": "IDLE",
            "current_task": "Draft saved. No active generation task.",
            "progress": 0,
            "completed_tasks": [],
            "last_error": None,
            "automation_active": False,
            "automation_task_id": None,
            "supervisor": {
                "current_review": None,
                "last_decision": None,
                "last_rationale": None,
                "mode": "idle",
                "waiting_for_user": False,
                "active_project_id": project_id,
                "last_event_at": None,
                "actionable_diagnosis": None,
                "stage_retry_counts": {},
                "image_retry_counts": {},
                "events": [],
            },
        },
        "artifacts": artifacts,
        "image_queue": {
            "current_index": 0,
            "batches": [],
            "accepted": [],
        },
        "context_layers": {
            "artifact_chain": True,
            "graphify_enabled": False,
            "graphify_refs": [],
            "optional_supervisor": "native_openclaw",
            "supervisor_enabled": True,
        },
        "logs": [],
    }


@dataclass
class ProjectStore:
    root_dir: Path

    def __post_init__(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        return self.root_dir / project_id

    def create_project(
        self,
        *,
        title: str,
        story_input: str,
        automation_mode: bool,
    ) -> dict[str, Any]:
        slug = sanitize_slug(title)
        project_id = f"{slug}-{uuid.uuid4().hex[:8]}"
        project_dir = self.project_dir(project_id)
        (project_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        (project_dir / "images").mkdir(parents=True, exist_ok=True)

        state = _default_project_state(
            project_id=project_id,
            title=title,
            story_input=story_input,
            automation_mode=automation_mode,
        )
        self._write_state(project_id, state)
        self._log(project_id, "info", "Project created")
        return self.read_project(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for entry in self.root_dir.iterdir():
            if not entry.is_dir():
                continue
            try:
                projects.append(self.read_project(entry.name))
            except FileNotFoundError:
                continue
        return projects

    def read_project(self, project_id: str) -> dict[str, Any]:
        state_path = self.project_dir(project_id) / "project.json"
        if not state_path.exists():
            raise FileNotFoundError(project_id)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return self._materialize_project(project_id, state)

    def update_project(self, project_id: str, mutator: Any) -> dict[str, Any]:
        state = self._read_state(project_id)
        mutator(state)
        state["updated_at"] = utc_now()
        self._write_state(project_id, state)
        return self._materialize_project(project_id, state)

    def save_artifact(self, project_id: str, artifact_type: str, content: Any, *, status: str = "ready") -> dict[str, Any]:
        if artifact_type not in ARTIFACT_TYPES:
            raise ValueError(f"Unsupported artifact type: {artifact_type}")

        state = self._read_state(project_id)
        artifact_rel = Path(state["artifacts"][artifact_type]["path"])
        artifact_path = self.project_dir(project_id) / artifact_rel
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(content, indent=2, ensure_ascii=True), encoding="utf-8")

        state["artifacts"][artifact_type]["content"] = content
        state["artifacts"][artifact_type]["status"] = status
        state["artifacts"][artifact_type]["updated_at"] = utc_now()
        state["current_stage"] = artifact_type
        state["updated_at"] = utc_now()
        self._write_state(project_id, state)
        return self._materialize_project(project_id, state)

    def set_artifact_status(self, project_id: str, artifact_type: str, status: str) -> dict[str, Any]:
        if artifact_type not in ARTIFACT_TYPES:
            raise ValueError(f"Unsupported artifact type: {artifact_type}")

        def mutate(state: dict[str, Any]) -> None:
            artifact = state["artifacts"][artifact_type]
            artifact["status"] = status
            artifact["updated_at"] = utc_now()
            state["current_stage"] = artifact_type

        return self.update_project(project_id, mutate)

    def update_draft(
        self,
        project_id: str,
        *,
        title: str,
        story_input: str,
        automation_mode: bool,
    ) -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> None:
            state["title"] = title
            state["story_input"] = story_input
            state["automation_mode"] = automation_mode
            if state["runtime"]["state"] == "IDLE":
                state["runtime"]["current_task"] = "Draft saved. No active generation task."

        return self.update_project(project_id, mutate)

    def add_log(self, project_id: str, level: str, message: str) -> dict[str, Any]:
        self._log(project_id, level, message)
        return self.read_project(project_id)

    def append_image_batch(self, project_id: str, batch: dict[str, Any]) -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> None:
            state["image_queue"]["batches"].append(batch)
            state["current_stage"] = "image_review"

        return self.update_project(project_id, mutate)

    def replace_image_batch(self, project_id: str, batch_id: str, batch: dict[str, Any]) -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> None:
            batches = state["image_queue"]["batches"]
            for index, existing in enumerate(batches):
                if existing["batch_id"] == batch_id:
                    batches[index] = batch
                    break
            else:
                raise ValueError(f"Unknown batch id: {batch_id}")

        return self.update_project(project_id, mutate)

    def accept_candidate(self, project_id: str, batch_id: str, candidate_id: str) -> dict[str, Any]:
        state = self._read_state(project_id)
        for batch in state["image_queue"]["batches"]:
            if batch["batch_id"] != batch_id:
                continue
            accepted = None
            retained_candidates: list[dict[str, Any]] = []
            for candidate in batch["candidates"]:
                if candidate["candidate_id"] == candidate_id:
                    candidate["status"] = "accepted"
                    accepted = deepcopy(candidate)
                    retained_candidates.append(candidate)
                else:
                    candidate["status"] = "rejected"
                    file_path = self.project_dir(project_id) / candidate["relative_path"]
                    if file_path.exists():
                        file_path.unlink()
            if accepted is None:
                raise ValueError(f"Unknown candidate id: {candidate_id}")
            batch["status"] = "accepted"
            batch["selected_candidate_id"] = candidate_id
            state["image_queue"]["accepted"].append(
                {
                    "job_id": batch["job_id"],
                    "batch_id": batch["batch_id"],
                    "candidate_id": candidate_id,
                    "relative_path": accepted["relative_path"],
                    "prompt": batch["prompt"],
                    "accepted_at": utc_now(),
                }
            )
            batch["candidates"] = retained_candidates
            state["image_queue"]["current_index"] = min(
                state["image_queue"]["current_index"] + 1,
                len((state["artifacts"].get("image_jobs") or {}).get("content", {}).get("jobs", [])),
            )
            state["updated_at"] = utc_now()
            self._write_state(project_id, state)
            return self._materialize_project(project_id, state)
        raise ValueError(f"Unknown batch id: {batch_id}")

    def set_status(self, project_id: str, status: str) -> dict[str, Any]:
        return self.update_project(project_id, lambda state: state.__setitem__("status", status))

    def set_runtime(
        self,
        project_id: str,
        *,
        state_value: str,
        current_task: str,
        progress: int | None = None,
        job_id: str | None = None,
        last_error: str | None = None,
        completed_task: str | None = None,
    ) -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> None:
            runtime = state.setdefault("runtime", {})
            runtime["state"] = state_value
            runtime["current_task"] = current_task
            if progress is not None:
                runtime["progress"] = progress
            if job_id is not None:
                runtime["job_id"] = job_id
            if last_error is not None or state_value != "FAILED":
                runtime["last_error"] = last_error
            if completed_task and completed_task not in runtime.setdefault("completed_tasks", []):
                runtime["completed_tasks"].append(completed_task)

        return self.update_project(project_id, mutate)

    def set_automation_active(self, project_id: str, active: bool) -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> None:
            state.setdefault("runtime", {}).setdefault("automation_active", active)
            state["runtime"]["automation_active"] = active

        return self.update_project(project_id, mutate)

    def set_automation_task_id(self, project_id: str, task_id: str | None) -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> None:
            runtime = state.setdefault("runtime", {})
            runtime["automation_task_id"] = task_id

        return self.update_project(project_id, mutate)

    def set_supervisor_state(
        self,
        project_id: str,
        *,
        current_review: str | None | object = UNSET,
        last_decision: str | None | object = UNSET,
        last_rationale: str | None | object = UNSET,
        mode: str | None | object = UNSET,
        waiting_for_user: bool | object = UNSET,
        actionable_diagnosis: dict[str, Any] | None | object = UNSET,
        stage_retry_counts: dict[str, int] | None = None,
        image_retry_counts: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> None:
            supervisor = state.setdefault("runtime", {}).setdefault(
                "supervisor",
                {
                    "current_review": None,
                    "last_decision": None,
                    "last_rationale": None,
                    "mode": "idle",
                    "waiting_for_user": False,
                    "active_project_id": project_id,
                    "last_event_at": None,
                    "actionable_diagnosis": None,
                    "stage_retry_counts": {},
                    "image_retry_counts": {},
                    "events": [],
                },
            )
            if current_review is not UNSET:
                supervisor["current_review"] = current_review
            if last_decision is not UNSET:
                supervisor["last_decision"] = last_decision
            if last_rationale is not UNSET:
                supervisor["last_rationale"] = last_rationale
            if mode is not UNSET:
                supervisor["mode"] = mode
            if waiting_for_user is not UNSET:
                supervisor["waiting_for_user"] = waiting_for_user
            if actionable_diagnosis is not UNSET:
                supervisor["actionable_diagnosis"] = actionable_diagnosis
            if stage_retry_counts is not None:
                supervisor["stage_retry_counts"] = stage_retry_counts
            if image_retry_counts is not None:
                supervisor["image_retry_counts"] = image_retry_counts
            supervisor["active_project_id"] = project_id

        return self.update_project(project_id, mutate)

    def add_supervisor_event(
        self,
        project_id: str,
        *,
        kind: str,
        message: str,
        level: str = "info",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> None:
            supervisor = state.setdefault("runtime", {}).setdefault(
                "supervisor",
                {
                    "current_review": None,
                    "last_decision": None,
                    "last_rationale": None,
                    "mode": "idle",
                    "waiting_for_user": False,
                    "active_project_id": project_id,
                    "last_event_at": None,
                    "actionable_diagnosis": None,
                    "stage_retry_counts": {},
                    "image_retry_counts": {},
                    "events": [],
                },
            )
            event = {
                "id": uuid.uuid4().hex,
                "timestamp": utc_now(),
                "kind": kind,
                "level": level,
                "message": message,
                "details": details or {},
            }
            events = supervisor.setdefault("events", [])
            events.append(event)
            supervisor["events"] = events[-200:]
            supervisor["last_event_at"] = event["timestamp"]
            supervisor["active_project_id"] = project_id
            if kind == "operator_note":
                supervisor["waiting_for_user"] = False

        return self.update_project(project_id, mutate)

    def reset_project(self, project_id: str) -> dict[str, Any]:
        state = self._read_state(project_id)
        project_dir = self.project_dir(project_id)
        artifacts_dir = project_dir / "artifacts"
        images_dir = project_dir / "images"
        if artifacts_dir.exists():
            shutil.rmtree(artifacts_dir)
        if images_dir.exists():
            shutil.rmtree(images_dir)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        fresh = _default_project_state(
            project_id=project_id,
            title=state["title"],
            story_input=state["story_input"],
            automation_mode=state.get("automation_mode", False),
        )
        self._write_state(project_id, fresh)
        self._log(project_id, "warning", "Project reset")
        return self.read_project(project_id)

    def _read_state(self, project_id: str) -> dict[str, Any]:
        state_path = self.project_dir(project_id) / "project.json"
        if not state_path.exists():
            raise FileNotFoundError(project_id)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return self._normalize_state(state)

    def _write_state(self, project_id: str, state: dict[str, Any]) -> None:
        project_dir = self.project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "project.json").write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")

    def _log(self, project_id: str, level: str, message: str) -> None:
        state = self._read_state(project_id)
        state["logs"].append(
            {
                "id": uuid.uuid4().hex,
                "timestamp": utc_now(),
                "level": level,
                "message": message,
            }
        )
        state["updated_at"] = utc_now()
        self._write_state(project_id, state)

    def _normalize_state(self, state: dict[str, Any]) -> dict[str, Any]:
        artifacts = state.setdefault("artifacts", {})
        for artifact_type in ARTIFACT_TYPES:
            artifacts.setdefault(
                artifact_type,
                {
                    "type": artifact_type,
                    "status": "pending",
                    "path": f"artifacts/{artifact_type}.json",
                    "updated_at": None,
                    "content": None,
                },
            )

        state.setdefault(
            "context_layers",
            {
                "artifact_chain": True,
                "graphify_enabled": False,
                "graphify_refs": [],
                "optional_supervisor": "openclaw",
                "supervisor_enabled": False,
            },
        )
        state.setdefault(
            "runtime",
            {
                "job_id": None,
                "state": "IDLE",
                "current_task": "Draft saved. No active generation task.",
                "progress": 0,
                "completed_tasks": [],
                "last_error": None,
                "automation_active": False,
                "automation_task_id": None,
                "supervisor": {
                    "current_review": None,
                    "last_decision": None,
                    "last_rationale": None,
                    "mode": "idle",
                    "waiting_for_user": False,
                    "active_project_id": None,
                    "last_event_at": None,
                    "actionable_diagnosis": None,
                    "stage_retry_counts": {},
                    "image_retry_counts": {},
                    "events": [],
                },
            },
        )
        runtime = state["runtime"]
        runtime.setdefault("automation_active", False)
        runtime.setdefault("automation_task_id", None)
        runtime.setdefault(
            "supervisor",
            {
                "current_review": None,
                "last_decision": None,
                "last_rationale": None,
                "mode": "idle",
                "waiting_for_user": False,
                "active_project_id": None,
                "last_event_at": None,
                "actionable_diagnosis": None,
                "stage_retry_counts": {},
                "image_retry_counts": {},
                "events": [],
            },
        )
        return state

    def _materialize_project(self, project_id: str, state: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(self._normalize_state(state))
        for artifact_type, artifact in result["artifacts"].items():
            if artifact.get("content") is not None:
                continue
            artifact_path = self.project_dir(project_id) / artifact["path"]
            if artifact_path.exists():
                artifact["content"] = json.loads(artifact_path.read_text(encoding="utf-8"))
            elif artifact_type == "story":
                artifact["content"] = None
        return result
