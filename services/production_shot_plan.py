"""Structured, immutable shot-plan revision helpers for production V2."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from story_builder.services.production_assets import ROLE_KINDS
from story_builder.services import production_story_revisions
from story_builder.services.production_authority import director_controls


class ShotPlanError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


def canonical_content_hash(content: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_editable_shot_content(content: Any, *, allow_reference_fields: bool = False) -> dict[str, Any]:
    if not isinstance(content, dict) or len(json.dumps(content, ensure_ascii=False)) > 50000:
        raise ShotPlanError("shot_content_invalid", "Shot content must be an object under 50,000 characters.")
    protected = {"asset_ids", "selected_asset_ids", "reference_map", "reference_plan", "compiled_graph"}
    if not allow_reference_fields and protected.intersection(content):
        raise ShotPlanError("reference_wiring_is_immutable_here", "Edit asset selection in the reference composer; shot text revisions cannot replace selected asset IDs or compiled wiring.")
    for key in ("prompt", "prompt_text", "shot_intent", "camera", "light"):
        if key in content and (not isinstance(content[key], str) or len(content[key]) > 20000):
            raise ShotPlanError("shot_text_field_invalid", f"{key} must be text up to 20,000 characters.")
    duration = content.get("duration_seconds")
    if duration is not None and (not isinstance(duration, (int, float)) or not 5 <= duration <= 15):
        raise ShotPlanError("shot_duration_invalid", "Shot duration must be between 5 and 15 seconds.")
    intents = content.get("asset_intents", [])
    if not isinstance(intents, list) or len(intents) > 15:
        raise ShotPlanError("shot_asset_intents_invalid", "Shot asset_intents must contain at most 15 records.")
    for intent in intents:
        if not isinstance(intent, dict) or intent.get("role") not in ROLE_KINDS:
            raise ShotPlanError("shot_asset_intents_invalid", "Each asset intent needs a supported project asset role.")
        if not isinstance(intent.get("intent", ""), str) or len(intent.get("intent", "")) > 2000:
            raise ShotPlanError("shot_asset_intents_invalid", "Each asset intent must be text up to 2,000 characters.")
    characters = content.get("characters", [])
    if not isinstance(characters, list) or len(characters) > 20 or any(not isinstance(x, str) or len(x) > 120 for x in characters):
        raise ShotPlanError("shot_characters_invalid", "Shot characters must be a list of at most 20 stable IDs/names.")
    dialogue = content.get("dialogue", [])
    if not isinstance(dialogue, list) or len(dialogue) > 200 or any(not isinstance(x, dict) for x in dialogue):
        raise ShotPlanError("shot_dialogue_invalid", "Shot dialogue must be a list of at most 200 structured lines.")
    return json.loads(json.dumps(content, ensure_ascii=False))


def latest_accepted_shot_plan(output_root, project_id: str, run_id: str) -> dict[str, Any] | None:
    revisions = production_story_revisions.list_stage_revisions(output_root, project_id, run_id, "shot_plans")
    accepted = [row for row in revisions if row.get("review_status") == "accepted"]
    return max(accepted, key=lambda row: str(row.get("accepted_at") or row.get("created_at") or "")) if accepted else None


def read_shot(output_root, project_id: str, run_id: str, shot_id: str,
               revision_id: str | None = None) -> dict[str, Any]:
    revision = (production_story_revisions.load_stage_revision(output_root, project_id, run_id,
                 "shot_plans", revision_id) if revision_id else latest_accepted_shot_plan(output_root, project_id, run_id))
    if not revision:
        raise ShotPlanError("accepted_shot_plan_required", "No accepted shot-plan revision exists for this run.")
    item = next((row for row in revision.get("items", []) if row.get("unit_id") == shot_id), None)
    if not item:
        raise ShotPlanError("shot_not_found", "Shot was not found in the selected shot-plan revision.")
    return {"revision_id": revision["revision_id"], "review_status": revision.get("review_status"),
            "parent_revision_id": revision.get("parent_revision_id"), "shot": item}


def edit_shot(output_root, project_id: str, run_id: str, *, expected_revision_id: str,
              expected_content_hash: str, shot_id: str, content: Any,
              control_mode: str, semi_gates: dict[str, bool] | None = None) -> dict[str, Any]:
    if director_controls({"control_mode": control_mode, "semi_gates": semi_gates or {}}, "story_review"):
        raise ShotPlanError("director_review_required", "Director-controlled shot text is edited by the Director review stage.")
    accepted = latest_accepted_shot_plan(output_root, project_id, run_id)
    if not accepted or accepted.get("revision_id") != expected_revision_id:
        raise ShotPlanError("shot_plan_stale", "A newer accepted shot-plan revision exists; reload before editing.")
    item = next((row for row in accepted.get("items", []) if row.get("unit_id") == shot_id), None)
    if not item or not isinstance(item.get("content"), dict):
        raise ShotPlanError("shot_not_found", "Shot was not found in the accepted shot-plan revision.")
    if canonical_content_hash(item["content"]) != expected_content_hash:
        raise ShotPlanError("shot_content_stale", "Shot content changed after it was loaded; reload before editing.")
    patch = validate_editable_shot_content(content)
    revised_content = json.loads(json.dumps(item["content"]))
    for key in patch:
        if key in {"asset_ids", "selected_asset_ids", "reference_map", "reference_plan", "compiled_graph"}:
            if patch[key] != revised_content.get(key):
                raise ShotPlanError("reference_wiring_is_immutable_here", "Edit asset selection in the reference composer; shot text revisions cannot replace selected asset IDs or compiled wiring.")
            continue
        revised_content[key] = patch[key]
    revised_content = validate_editable_shot_content(revised_content, allow_reference_fields=True)
    updated = json.loads(json.dumps(accepted))
    updated["revision_id"] = f"shot_plans-{uuid.uuid4().hex[:12]}"
    updated["parent_revision_id"] = expected_revision_id
    updated["created_at"] = datetime.now(timezone.utc).isoformat()
    updated.pop("accepted_at", None)
    updated["review_status"] = "pending_review"
    updated["author"] = "user"
    updated["edit_scope"] = "shot_content_only"
    target = next(row for row in updated["items"] if row.get("unit_id") == shot_id)
    target["content"] = revised_content
    path = production_story_revisions.write_stage_revision(output_root, project_id, run_id, "shot_plans", updated)
    return {"revision": updated, "shot": target, "output_path": str(path)}
