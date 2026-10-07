"""GPU-free, project-scoped validation and compilation of one H3 R2V shot."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Mapping

from story_builder.services.minimax_h3_graph_compiler import (
    AudioReference, GraphPlanError, ImageReference, ReferencePlan, ResolvedAsset,
    VideoReference, compile_r2v_graph, plan_to_dict,
)
from story_builder.services.minimax_h3_t2v import compile_t2v_graph


MAX_VIDEO_REFERENCE_TOTAL_SECONDS = 15.0
MAX_STANDALONE_AUDIO_TOTAL_SECONDS = 15.0


def validate_and_compile_shot(plan: ReferencePlan, *,
                              get_asset: Callable[[str], Mapping[str, Any]],
                              inspect_asset: Callable[[Mapping[str, Any]], Mapping[str, Any]],
                              voice_bindings: list[Mapping[str, Any]] | None = None,
                              reference_map_only: bool = False) -> dict[str, Any]:
    """Resolve stable IDs to trusted metadata, compile a placeholder graph, and hash it.

    ``inspect_asset`` must resolve the asset within its actual owner and return
    type/hash/duration/audio facts only. This function never accepts filesystem
    paths from the plan and never stages, submits, or loads media.
    """
    if not (plan.images or plan.videos or plan.standalone_audios):
        compiled = compile_t2v_graph(plan)
        graph_json = json.dumps(compiled["graph"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        plan_json = json.dumps(plan_to_dict(plan), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(json.dumps({"plan": plan_json, "graph": graph_json,
            "asset_hashes": {}, "compiler": "h3-t2v-1.0.0"}, sort_keys=True,
            ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        return {"valid": True, "reference_map_only": reference_map_only,
            "prompt_tags_validated": not reference_map_only,
            "workflow_id": compiled["workflow_id"], "workflow_version": 1,
            "graph_compiler_version": "h3-t2v-1.0.0", "validation_hash": digest,
            "shot_id": plan.shot_id, "width": compiled["width"], "height": compiled["height"],
            "frame_count": compiled["frame_count"], "duration_seconds": plan.duration_seconds,
            "video_reference_seconds": 0.0, "standalone_audio_reference_seconds": 0.0,
            "reference_map": {"pictures": [], "videos": [], "audios": [], "speaker_audio_tags": {}},
            "asset_fingerprints": {}, "plan": plan_to_dict(plan)}

    if type(reference_map_only) is not bool:
        raise GraphPlanError("reference_resolution_mode_invalid", "reference_map_only must be a boolean.")

    requested = [(row.asset_id, "image", row.role) for row in plan.images]
    requested += [(row.asset_id, "video", row.role) for row in plan.videos]
    requested += [(row.asset_id, "audio", row.role) for row in plan.standalone_audios]
    records: dict[str, Mapping[str, Any]] = {}
    trusted: dict[str, Mapping[str, Any]] = {}
    index: dict[str, ResolvedAsset] = {}
    bindings_by_speaker = {
        str(row.get("speaker_id")): row for row in (voice_bindings or [])
        if isinstance(row, Mapping) and row.get("run_id") == plan.run_id
        and isinstance(row.get("speaker_id"), str) and row.get("speaker_id")
    }
    for asset_id, expected_kind, ref_role in requested:
        if asset_id in records:
            raise GraphPlanError("duplicate_reference", "The same asset cannot occupy more than one reference slot.",
                                 context={"asset_id": asset_id})
        try:
            record = get_asset(asset_id)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            raise GraphPlanError("asset_not_found", "Reference asset is not available in this project.",
                                 context={"asset_id": asset_id, "project_id": plan.project_id}) from exc
        if record.get("asset_id") != asset_id or record.get("project_id") != plan.project_id:
            raise GraphPlanError("asset_project_mismatch", "Reference asset does not belong to this project index.",
                                 context={"asset_id": asset_id, "project_id": plan.project_id})
        if record.get("kind") != expected_kind:
            raise GraphPlanError("asset_type_mismatch", "Reference asset type does not match its selected slot.",
                                 context={"asset_id": asset_id, "expected_type": expected_kind,
                                          "actual_type": record.get("kind")})
        roles = record.get("roles")
        if not isinstance(roles, list) or ref_role not in roles:
            raise GraphPlanError("asset_role_mismatch", "Selected reference role must be registered on the selected project asset.",
                                 context={"asset_id": asset_id, "role": ref_role,
                                          "registered_roles": roles if isinstance(roles, list) else []})
        if expected_kind == "audio":
            metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
            excerpt = metadata.get("production_voice_excerpt") if isinstance(metadata.get("production_voice_excerpt"), Mapping) else metadata
            binding = bindings_by_speaker.get(str(next((row.speaker_id for row in plan.standalone_audios
                if row.asset_id == asset_id), "")))
            if (ref_role != "voice_excerpt" or metadata.get("approval_status") != "accepted"
                    or excerpt.get("run_id") != plan.run_id or not binding
                    or excerpt.get("character_id") != binding.get("character_id")
                    or excerpt.get("source_voice_asset_id") != binding.get("voice_asset_id")
                    or excerpt.get("source_sha256") != binding.get("voice_asset_hash")
                    or binding.get("source_project_id") != plan.project_id
                    or not isinstance(binding.get("voice_asset_id"), str)):
                raise GraphPlanError("voice_reference_binding_mismatch",
                    "Standalone H3 audio must be an accepted excerpt from this run's saved speaker voice binding.",
                    context={"asset_id": asset_id, "speaker_id": next((row.speaker_id for row in plan.standalone_audios if row.asset_id == asset_id), None),
                             "run_id": plan.run_id})
        if expected_kind == "audio" and {"music_candidate", "sfx_candidate"}.intersection(record.get("roles", [])):
            raise GraphPlanError("audio_sidecar_not_voice_reference",
                                 "Music and sound-effect candidates are separate sidecars and cannot occupy an H3 standalone voice-reference slot.",
                                 context={"asset_id": asset_id, "roles": record.get("roles", [])})
        try:
            facts = dict(inspect_asset(record))
        except (FileNotFoundError, ValueError, OSError) as exc:
            raise GraphPlanError("asset_unavailable", f"Reference asset could not be safely inspected: {exc}",
                                 context={"asset_id": asset_id}) from exc
        if facts.get("media_type") != expected_kind:
            raise GraphPlanError("asset_type_mismatch", "Inspected media type differs from the project asset record.",
                                 context={"asset_id": asset_id, "expected_type": expected_kind,
                                          "actual_type": facts.get("media_type")})
        digest = str(facts.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise GraphPlanError("asset_hash_missing", "Selected reference has no verified SHA-256 hash.",
                                 context={"asset_id": asset_id})
        filename = Path(str(facts.get("filename") or "asset")).name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".mkv", ".webm",
                          ".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac"}:
            raise GraphPlanError("asset_format_unsupported", "Selected reference format is not supported by the H3 adapter.",
                                 context={"asset_id": asset_id, "filename": filename})
        records[asset_id] = record
        trusted[asset_id] = facts
        index[asset_id] = ResolvedAsset(asset_id=asset_id, media_type=expected_kind,
            comfy_filename=f"validated-{asset_id[3:]}{suffix}", sha256=digest)

    video_refs: list[VideoReference] = []
    total_video_seconds = 0.0
    for ref in plan.videos:
        facts = trusted[ref.asset_id]
        duration = facts.get("duration_seconds")
        if not isinstance(duration, (float, int)) or not math.isfinite(float(duration)) or float(duration) <= 0:
            raise GraphPlanError("asset_duration_unavailable", "Video reference duration could not be verified.", context={"asset_id": ref.asset_id})
        start = 0.0 if ref.start_sec is None else float(ref.start_sec)
        end = min(float(duration), 15.0) if ref.end_sec is None else float(ref.end_sec)
        length = end - start
        if start < 0 or end > float(duration) or length < 2.0 or length > 15.0:
            raise GraphPlanError("invalid_video_interval", "Video reference excerpt must be 2–15 seconds and fit within the source video.",
                                 context={"asset_id": ref.asset_id, "interval": [start, end], "source_duration": duration})
        total_video_seconds += length
        if ref.include_paired_soundtrack and not facts.get("has_audio"):
            raise GraphPlanError("paired_audio_missing", "Selected video has no audio stream to pair.", context={"asset_id": ref.asset_id})
        video_refs.append(replace(ref, start_sec=start, end_sec=end))
        index[ref.asset_id] = replace(index[ref.asset_id], prepared_start_sec=start,
            prepared_end_sec=end, has_audio=bool(facts.get("has_audio")))
    if total_video_seconds > MAX_VIDEO_REFERENCE_TOTAL_SECONDS:
        raise GraphPlanError("video_reference_total_too_long", "Combined video-reference excerpts cannot exceed 15 seconds.",
                             context={"total_seconds": total_video_seconds,
                                      "maximum_seconds": MAX_VIDEO_REFERENCE_TOTAL_SECONDS})

    total_audio_seconds = 0.0
    for ref in plan.standalone_audios:
        duration = trusted[ref.asset_id].get("duration_seconds")
        if not isinstance(duration, (float, int)) or not math.isfinite(float(duration)):
            raise GraphPlanError("asset_duration_unavailable", "Standalone audio duration could not be verified.", context={"asset_id": ref.asset_id})
        if not 2.0 <= float(duration) <= 15.0:
            raise GraphPlanError("audio_reference_duration_invalid", "H3 standalone reference audio must be 2–15 seconds; prepare a derived excerpt first.",
                                 context={"asset_id": ref.asset_id, "duration_seconds": duration})
        total_audio_seconds += float(duration)
    if total_audio_seconds > MAX_STANDALONE_AUDIO_TOTAL_SECONDS:
        raise GraphPlanError("audio_reference_total_too_long", "Combined standalone audio references cannot exceed 15 seconds.",
                             context={"total_seconds": total_audio_seconds,
                                      "maximum_seconds": MAX_STANDALONE_AUDIO_TOTAL_SECONDS})

    prepared_plan = replace(plan, videos=tuple(video_refs))
    compiled = compile_r2v_graph(prepared_plan, index, reference_map_only=reference_map_only)
    graph_json = json.dumps(compiled.graph, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    plan_json = json.dumps(plan_to_dict(prepared_plan), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    asset_hashes = {asset_id: str(trusted[asset_id]["sha256"]) for asset_id, _, _ in requested}
    validation_hash = hashlib.sha256(json.dumps({"plan": plan_json, "graph": graph_json,
        "asset_hashes": asset_hashes, "compiler": "1.0.0"}, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"valid": True, "reference_map_only": reference_map_only,
            "prompt_tags_validated": not reference_map_only,
            "workflow_id": compiled.workflow_id, "workflow_version": 1,
            "graph_compiler_version": "1.0.0", "validation_hash": validation_hash,
            "shot_id": plan.shot_id, "width": compiled.width, "height": compiled.height,
            "frame_count": compiled.frame_count, "duration_seconds": plan.duration_seconds,
            "video_reference_seconds": total_video_seconds,
            "standalone_audio_reference_seconds": total_audio_seconds,
            "reference_map": compiled.reference_map.as_dict(),
            "asset_fingerprints": asset_hashes,
            "plan": plan_to_dict(prepared_plan)}
