"""Typed, deterministic compiler for local MiniMax H3 reference-to-video graphs.

This module deliberately does not submit ComfyUI jobs or accept paths from a
browser. Callers must resolve project-scoped asset IDs, stage media into the
ComfyUI input directory, and pass the staged basenames as ``ResolvedAsset``
records. The compiler only adds allowlisted loader nodes to a copied API graph.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_GRAPH_PATH = PROJECT_ROOT / "workflows" / "api" / "minimax_h3_r2v_api.json"
MAX_IMAGES = 9
MAX_VIDEOS = 3
MAX_AUDIOS = 3
MAX_REFERENCE_SECONDS = 15.0
H3_FPS = 24
RESOLUTION_PRESETS: dict[float, tuple[int, int]] = {
    0.98: (1344, 768),
    0.4: (864, 480),
}
ALLOWED_LOADERS = {"LoadImage", "LoadAudio", "VHS_LoadVideo"}
TAG_PATTERN = re.compile(r"<(Picture|Video|Audio)\s+(\d+)>", re.IGNORECASE)
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]{0,254}$")


class GraphPlanError(ValueError):
    """Validation error with a stable machine-readable code and context."""

    def __init__(self, code: str, message: str, *, context: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "context": self.context}


@dataclass(frozen=True)
class ImageReference:
    asset_id: str
    role: str
    intent: str


@dataclass(frozen=True)
class VideoReference:
    asset_id: str
    role: str
    intent: str
    start_sec: float | None = None
    end_sec: float | None = None
    include_paired_soundtrack: bool = False
    audio_intent: str = ""


@dataclass(frozen=True)
class AudioReference:
    asset_id: str
    role: str
    intent: str
    speaker_id: str | None = None


@dataclass(frozen=True)
class ReferencePlan:
    schema_version: int
    project_id: str
    run_id: str
    shot_id: str
    prompt: str
    duration_seconds: float
    resolution_preset: float = 0.98
    aspect_ratio: str = "16:9"
    steps: int = 20
    ref_image_size: Literal["match", "max"] = "match"
    seed: int = 1
    images: tuple[ImageReference, ...] = field(default_factory=tuple)
    videos: tuple[VideoReference, ...] = field(default_factory=tuple)
    standalone_audios: tuple[AudioReference, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResolvedAsset:
    """Internal asset resolution result; never construct from a client path."""

    asset_id: str
    media_type: Literal["image", "video", "audio"]
    comfy_filename: str
    sha256: str
    prepared_start_sec: float | None = None
    prepared_end_sec: float | None = None
    has_audio: bool = False


@dataclass(frozen=True)
class ResolvedReferenceMap:
    pictures: tuple[dict[str, Any], ...]
    videos: tuple[dict[str, Any], ...]
    audios: tuple[dict[str, Any], ...]
    speaker_audio_tags: Mapping[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "pictures": [dict(item) for item in self.pictures],
            "videos": [dict(item) for item in self.videos],
            "audios": [dict(item) for item in self.audios],
            "speaker_audio_tags": dict(self.speaker_audio_tags),
        }


@dataclass(frozen=True)
class CompiledGraph:
    workflow_id: str
    graph: Mapping[str, Any]
    reference_map: ResolvedReferenceMap
    width: int
    height: int
    frame_count: int


def _require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise GraphPlanError("invalid_identifier", f"{field_name} must be a non-empty string of at most 160 characters.", context={"field": field_name})


def _safe_comfy_filename(asset: ResolvedAsset) -> None:
    name = asset.comfy_filename
    if not SAFE_FILENAME.fullmatch(name) or name in {".", ".."}:
        raise GraphPlanError("unsafe_staged_filename", "Resolved media must use a safe staged filename, not a path.", context={"asset_id": asset.asset_id})
    if Path(name).name != name or "/" in name or "\\" in name:
        raise GraphPlanError("unsafe_staged_filename", "Resolved media filename cannot contain a directory path.", context={"asset_id": asset.asset_id})
    if not re.fullmatch(r"[a-fA-F0-9]{64}", asset.sha256):
        raise GraphPlanError("invalid_asset_hash", "Resolved asset must include its SHA-256 digest.", context={"asset_id": asset.asset_id})


def _aligned_frame_count(duration_seconds: float) -> int:
    """Return the next supported 17k+5 frame count at 24 fps."""
    requested = max(5, math.ceil(duration_seconds * H3_FPS))
    while requested % 17 != 5:
        requested += 1
    return requested


def validate_reference_plan(plan: ReferencePlan) -> None:
    """Validate user intent before resolving or staging any file."""
    if plan.schema_version != 1:
        raise GraphPlanError("unsupported_schema", "ReferencePlan schema_version must be 1.")
    for field_name in ("project_id", "run_id", "shot_id"):
        _require_identifier(getattr(plan, field_name), field_name)
    if not isinstance(plan.prompt, str) or not plan.prompt.strip():
        raise GraphPlanError("missing_prompt", "A non-empty H3 prompt is required.", context={"shot_id": plan.shot_id})
    if not math.isfinite(plan.duration_seconds) or not 5.0 <= plan.duration_seconds <= 15.0:
        raise GraphPlanError("invalid_duration", "Local H3 R2V duration must be between 5 and 15 seconds.", context={"requested_seconds": plan.duration_seconds})
    if plan.aspect_ratio != "16:9":
        raise GraphPlanError("unsupported_aspect_ratio", "The first dynamic R2V release supports the tested 16:9 canvas only.", context={"aspect_ratio": plan.aspect_ratio})
    if plan.resolution_preset not in RESOLUTION_PRESETS:
        raise GraphPlanError("unsupported_resolution_preset", "Choose the tested 0.98 final or 0.4 preview preset.", context={"preset": plan.resolution_preset})
    if not isinstance(plan.steps, int) or not 8 <= plan.steps <= 40:
        raise GraphPlanError("invalid_steps", "H3 steps must be an integer between 8 and 40.", context={"steps": plan.steps})
    if not isinstance(plan.seed, int) or not 0 <= plan.seed <= 0xFFFFFFFF:
        raise GraphPlanError("invalid_seed", "Seed must be an unsigned 32-bit integer.")
    if plan.ref_image_size not in {"match", "max"}:
        raise GraphPlanError("invalid_ref_image_size", "ref_image_size must be 'match' or 'max'.")
    if len(plan.images) > MAX_IMAGES or len(plan.videos) > MAX_VIDEOS or len(plan.standalone_audios) > MAX_AUDIOS:
        raise GraphPlanError("reference_limit_exceeded", "Reference counts exceed local H3 limits.", context={"images": len(plan.images), "videos": len(plan.videos), "standalone_audios": len(plan.standalone_audios), "limits": {"images": MAX_IMAGES, "videos": MAX_VIDEOS, "standalone_audios": MAX_AUDIOS}})
    refs: list[tuple[str, str]] = []
    refs.extend((row.asset_id, "image") for row in plan.images)
    refs.extend((row.asset_id, "video") for row in plan.videos)
    refs.extend((row.asset_id, "audio") for row in plan.standalone_audios)
    for asset_id, _ in refs:
        _require_identifier(asset_id, "asset_id")
    if len({asset_id for asset_id, _ in refs}) != len(refs):
        raise GraphPlanError("duplicate_reference", "The same asset cannot occupy multiple reference slots in one shot.")
    for item in plan.videos:
        if (item.start_sec is None) != (item.end_sec is None):
            raise GraphPlanError("incomplete_video_interval", "Video reference start_sec and end_sec must be provided together.", context={"asset_id": item.asset_id})
        if item.start_sec is not None:
            if not math.isfinite(item.start_sec) or not math.isfinite(item.end_sec or float("nan")) or item.start_sec < 0 or item.end_sec <= item.start_sec:
                raise GraphPlanError("invalid_video_interval", "Video reference interval must have start >= 0 and end > start.", context={"asset_id": item.asset_id})
            if item.end_sec - item.start_sec > MAX_REFERENCE_SECONDS:
                raise GraphPlanError("video_interval_too_long", "A local H3 reference-video excerpt cannot exceed 15 seconds.", context={"asset_id": item.asset_id})
        if item.include_paired_soundtrack and not item.audio_intent.strip():
            raise GraphPlanError("missing_paired_audio_intent", "A paired soundtrack needs an explicit audio intent.", context={"asset_id": item.asset_id})
    speakers = [row.speaker_id for row in plan.standalone_audios if row.speaker_id]
    if len(set(speakers)) != len(speakers):
        raise GraphPlanError("duplicate_speaker_voice", "A speaker may have only one standalone voice reference in a shot.", context={"speaker_ids": speakers})


def resolve_reference_assets(plan: ReferencePlan, asset_index: Mapping[str, ResolvedAsset]) -> dict[str, ResolvedAsset]:
    """Resolve IDs against a trusted, already project-scoped asset index."""
    validate_reference_plan(plan)
    requested: list[tuple[str, str, float | None, float | None]] = []
    requested.extend((r.asset_id, "image", None, None) for r in plan.images)
    requested.extend((r.asset_id, "video", r.start_sec, r.end_sec) for r in plan.videos)
    requested.extend((r.asset_id, "audio", None, None) for r in plan.standalone_audios)
    result: dict[str, ResolvedAsset] = {}
    for asset_id, expected_type, start_sec, end_sec in requested:
        asset = asset_index.get(asset_id)
        if asset is None:
            raise GraphPlanError("asset_not_found", "Reference asset is not available in the authorized project/repertoire index.", context={"asset_id": asset_id, "project_id": plan.project_id})
        if asset.asset_id != asset_id or asset.media_type != expected_type:
            raise GraphPlanError("asset_type_mismatch", "Reference asset ID or media type does not match its selected slot.", context={"asset_id": asset_id, "expected_type": expected_type, "actual_type": asset.media_type})
        _safe_comfy_filename(asset)
        if expected_type == "video":
            if start_sec is None:
                interval_matches = (asset.prepared_start_sec == 0.0 and asset.prepared_end_sec is not None
                                    and 0.0 < asset.prepared_end_sec <= MAX_REFERENCE_SECONDS)
            else:
                interval_matches = (asset.prepared_start_sec == start_sec and asset.prepared_end_sec == end_sec)
            if not interval_matches:
                raise GraphPlanError("asset_interval_not_staged", "Selected video interval must be staged and probed before graph compilation.", context={"asset_id": asset_id, "requested_interval": [start_sec, end_sec], "staged_interval": [asset.prepared_start_sec, asset.prepared_end_sec]})
        result[asset_id] = asset
    for video_ref in plan.videos:
        if video_ref.include_paired_soundtrack and not result[video_ref.asset_id].has_audio:
            raise GraphPlanError("paired_audio_missing", "A paired soundtrack was selected, but the staged video has no audio stream.", context={"asset_id": video_ref.asset_id})
    return result


def _node_id(graph: Mapping[str, Any]) -> str:
    numeric = [int(key) for key in graph if str(key).isdigit()]
    return str(max(numeric, default=0) + 1)


def _connect(node: dict[str, Any], key: str, upstream_id: str, output_index: int = 0) -> None:
    node.setdefault("inputs", {})[key] = [upstream_id, output_index]


def _safe_prefix(run_id: str, shot_id: str) -> str:
    def clean(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")[:80] or "item"
    return f"story_builder/{clean(run_id)}/{clean(shot_id)}"


def _build_reference_map(plan: ReferencePlan, resolved: Mapping[str, ResolvedAsset] | None = None) -> ResolvedReferenceMap:
    pictures: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    audios: list[dict[str, Any]] = []
    for index, ref in enumerate(plan.images, start=1):
        pictures.append({"tag": f"<Picture {index}>", "asset_id": ref.asset_id, "role": ref.role, "intent": ref.intent})
    audio_index = 1
    for index, ref in enumerate(plan.videos, start=1):
        paired_tag = None
        if ref.include_paired_soundtrack:
            paired_tag = f"<Audio {audio_index}>"
            audios.append({"tag": paired_tag, "asset_id": ref.asset_id, "source": "paired_video_soundtrack", "paired_video_tag": f"<Video {index}>", "role": "paired_video_audio", "intent": ref.audio_intent})
            audio_index += 1
        staged = (resolved or {}).get(ref.asset_id)
        interval = ([ref.start_sec, ref.end_sec] if ref.start_sec is not None else
                    [staged.prepared_start_sec, staged.prepared_end_sec] if staged and staged.prepared_end_sec is not None else None)
        videos.append({"tag": f"<Video {index}>", "asset_id": ref.asset_id, "role": ref.role, "intent": ref.intent, "paired_audio_tag": paired_tag, "interval": interval})
    speakers: dict[str, str] = {}
    for ref in plan.standalone_audios:
        tag = f"<Audio {audio_index}>"
        audios.append({"tag": tag, "asset_id": ref.asset_id, "source": "standalone_audio", "role": ref.role, "intent": ref.intent, "speaker_id": ref.speaker_id})
        if ref.speaker_id:
            speakers[ref.speaker_id] = tag
        audio_index += 1
    return ResolvedReferenceMap(tuple(pictures), tuple(videos), tuple(audios), speakers)


def lint_prompt_tags(prompt: str, reference_map: ResolvedReferenceMap) -> None:
    """Require exact correspondence between connected references and prompt tags."""
    available = {row["tag"] for section in (reference_map.pictures, reference_map.videos, reference_map.audios) for row in section}
    mentioned: set[str] = set()
    for kind, number in TAG_PATTERN.findall(prompt):
        canonical_kind = {"picture": "Picture", "video": "Video", "audio": "Audio"}[kind.lower()]
        mentioned.add(f"<{canonical_kind} {int(number)}>")
    unknown = mentioned - available
    unused = available - mentioned
    if unknown or unused:
        raise GraphPlanError("prompt_reference_tags_mismatch", "Prompt reference tags must match every connected reference exactly.", context={"unknown_tags": sorted(unknown), "unused_tags": sorted(unused), "available_tags": sorted(available)})
    for speaker_id, audio_tag in reference_map.speaker_audio_tags.items():
        explicit_binding = re.search(re.escape(audio_tag) + r"[^.\n]{0,240}\(" + re.escape(speaker_id) + r"\)", prompt)
        if not explicit_binding or audio_tag not in mentioned:
            raise GraphPlanError("speaker_reference_unbound", "Each selected speaker voice must be linked to its Audio tag and stable speaker ID in the same prompt statement.", context={"speaker_id": speaker_id, "audio_tag": audio_tag})


def load_base_graph(path: Path = BASE_GRAPH_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphPlanError("base_graph_unavailable", "Could not read the versioned H3 R2V API base graph.", context={"path": str(path), "reason": str(exc)}) from exc
    if not isinstance(value, dict) or not value:
        raise GraphPlanError("invalid_base_graph", "The H3 base graph must be a non-empty ComfyUI API graph.", context={"path": str(path)})
    return value


def validate_comfy_capabilities(object_info: Mapping[str, Any]) -> dict[str, Any]:
    """Validate installed node names and required sockets from live object_info."""
    required = {"MiniMaxH3ReferenceToVideo", "LoadImage", "LoadAudio", "VHS_LoadVideo", "CreateVideo", "SaveVideo"}
    missing = sorted(required - set(object_info))
    if missing:
        raise GraphPlanError("comfy_nodes_missing", "Installed ComfyUI lacks nodes needed by the dynamic H3 route.", context={"missing_nodes": missing})
    r2v = object_info["MiniMaxH3ReferenceToVideo"].get("input", {}).get("required", {})
    r2v_optional = object_info["MiniMaxH3ReferenceToVideo"].get("input", {}).get("optional", {})
    if not {"clip", "vae", "audio_vae", "prompt", "width", "height", "length", "ref_image_size"}.issubset(r2v):
        raise GraphPlanError("comfy_r2v_schema_mismatch", "Installed H3 R2V node lacks required base inputs.")
    for group in ("ref_images", "ref_videos", "ref_video_audios", "ref_audios"):
        if group not in r2v_optional and group not in r2v:
            raise GraphPlanError("comfy_r2v_schema_mismatch", "Installed H3 R2V node lacks an expected autogrow reference input.", context={"input_group": group})
    video_inputs = object_info["VHS_LoadVideo"].get("input", {}).get("required", {})
    if not {"video", "force_rate", "custom_width", "custom_height", "frame_load_cap", "skip_first_frames", "select_every_nth"}.issubset(video_inputs):
        raise GraphPlanError("comfy_video_loader_schema_mismatch", "Installed Video Helper Suite loader lacks required inputs for deterministic frame/audio loading.")
    return {"status": "ready", "required_nodes": sorted(required), "video_loader": "VHS_LoadVideo", "h3_reference_groups": ["ref_images", "ref_videos", "ref_video_audios", "ref_audios"]}


def compile_r2v_graph(
    plan: ReferencePlan,
    asset_index: Mapping[str, ResolvedAsset],
    *,
    base_graph: Mapping[str, Any] | None = None,
    reference_map_only: bool = False,
) -> CompiledGraph:
    """Compile a stable API prompt graph; all media must already be staged."""
    validate_reference_plan(plan)
    if not (plan.images or plan.videos or plan.standalone_audios):
        raise GraphPlanError("zero_reference_route", "R2V needs at least one reference. Route a zero-reference shot to the separately validated H3 T2V workflow.", context={"shot_id": plan.shot_id})
    resolved = resolve_reference_assets(plan, asset_index)
    ref_map = _build_reference_map(plan, resolved)
    compiled_prompt = plan.prompt
    if reference_map_only:
        # This graph is an internal validation artifact only. Derive placeholder
        # tags from the compiler map so selection can precede prompt authorship.
        rows = [*ref_map.pictures, *ref_map.videos, *ref_map.audios]
        statements = []
        for row in rows:
            tag = row["tag"]
            speaker_id = row.get("speaker_id")
            source = row.get("source")
            if speaker_id:
                statements.append(f"{tag} is the voice reference for Subject ({speaker_id}).")
            elif source == "paired_video_soundtrack":
                statements.append(f"{tag} is the paired soundtrack for {row['paired_video_tag']}.")
            else:
                statements.append(f"{tag} is a {row['role']} reference.")
        compiled_prompt = " ".join(statements)
        if not compiled_prompt:
            raise GraphPlanError("zero_reference_route", "Reference-map-only R2V compilation needs at least one reference.")
    graph = copy.deepcopy(dict(base_graph if base_graph is not None else load_base_graph()))
    r2v_nodes = [(str(key), value) for key, value in graph.items() if isinstance(value, dict) and value.get("class_type") == "MiniMaxH3ReferenceToVideo"]
    if len(r2v_nodes) != 1:
        raise GraphPlanError("base_graph_node_count", "H3 R2V base graph must contain exactly one MiniMaxH3ReferenceToVideo node.", context={"count": len(r2v_nodes)})
    h3_id, h3_node = r2v_nodes[0]
    inputs = h3_node.setdefault("inputs", {})
    for key in list(inputs):
        if key.startswith(("ref_images.", "ref_videos.", "ref_video_audios.", "ref_audios.")):
            del inputs[key]
    # Remove only LoadImage nodes that were connected to the template's R2V input.
    old_image_ids = {str(value[0]) for key, value in (base_graph or load_base_graph()).get(h3_id, {}).get("inputs", {}).items() if key.startswith("ref_images.") and isinstance(value, list) and value}
    for old_id in old_image_ids:
        if graph.get(old_id, {}).get("class_type") == "LoadImage":
            del graph[old_id]
    original_node_ids = set(graph)
    next_id = int(_node_id(graph))
    for index, ref in enumerate(plan.images):
        asset = resolved[ref.asset_id]
        node_id = str(next_id); next_id += 1
        graph[node_id] = {"class_type": "LoadImage", "inputs": {"image": asset.comfy_filename}}
        _connect(h3_node, f"ref_images.ref_image_{index}", node_id)
    video_loader_ids: list[str] = []
    for index, ref in enumerate(plan.videos):
        asset = resolved[ref.asset_id]
        node_id = str(next_id); next_id += 1
        graph[node_id] = {"class_type": "VHS_LoadVideo", "inputs": {
            "video": asset.comfy_filename, "force_rate": H3_FPS, "custom_width": 0,
            "custom_height": 0, "frame_load_cap": 0, "skip_first_frames": 0,
            "select_every_nth": 1,
        }}
        video_loader_ids.append(node_id)
        _connect(h3_node, f"ref_videos.ref_video_{index}", node_id, 0)
        if ref.include_paired_soundtrack:
            _connect(h3_node, f"ref_video_audios.ref_video_audio_{index}", node_id, 2)
    for index, ref in enumerate(plan.standalone_audios):
        asset = resolved[ref.asset_id]
        node_id = str(next_id); next_id += 1
        graph[node_id] = {"class_type": "LoadAudio", "inputs": {"audio": asset.comfy_filename}}
        _connect(h3_node, f"ref_audios.ref_audio_{index}", node_id)
    frame_count = _aligned_frame_count(plan.duration_seconds)
    width, height = RESOLUTION_PRESETS[plan.resolution_preset]
    inputs.update({"prompt": compiled_prompt, "width": width, "height": height, "length": frame_count, "ref_image_size": plan.ref_image_size})
    schedulers = [node.get("inputs", {}) for node in graph.values() if node.get("class_type") == "BasicScheduler"]
    if len(schedulers) != 1:
        raise GraphPlanError("base_graph_scheduler_count", "Expected one BasicScheduler in the H3 R2V base graph.", context={"count": len(schedulers)})
    schedulers[0]["steps"] = plan.steps
    noises = [node.get("inputs", {}) for node in graph.values() if node.get("class_type") == "RandomNoise"]
    if len(noises) != 1:
        raise GraphPlanError("base_graph_noise_count", "Expected one RandomNoise node in the H3 R2V base graph.", context={"count": len(noises)})
    noises[0]["noise_seed"] = plan.seed
    for node in graph.values():
        if node.get("class_type") == "SaveVideo":
            node.setdefault("inputs", {})["filename_prefix"] = _safe_prefix(plan.run_id, plan.shot_id)
    lint_prompt_tags(compiled_prompt, ref_map)
    added_classes = [node.get("class_type") for key, node in graph.items() if key not in original_node_ids]
    if any(cls not in ALLOWED_LOADERS for cls in added_classes):
        raise GraphPlanError("disallowed_loader", "Compiler attempted to add a non-allowlisted media loader.")
    LOGGER.info("Compiled H3 R2V graph project=%s run=%s shot=%s images=%d videos=%d paired_audio=%d standalone_audio=%d frames=%d resolution=%dx%d seed=%d",
                plan.project_id, plan.run_id, plan.shot_id, len(plan.images), len(plan.videos),
                sum(1 for video in plan.videos if video.include_paired_soundtrack), len(plan.standalone_audios),
                frame_count, width, height, plan.seed)
    return CompiledGraph("minimax_h3_r2v_dynamic_v1", graph, ref_map, width, height, frame_count)


def plan_to_dict(plan: ReferencePlan) -> dict[str, Any]:
    """Serialize the typed request for manifests/tests without exposing paths."""
    return asdict(plan)
