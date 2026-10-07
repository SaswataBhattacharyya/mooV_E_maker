"""Deterministic compiler for the installed local MiniMax H3 text-to-video graph."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Mapping

from story_builder.services.minimax_h3_graph_compiler import GraphPlanError, ReferencePlan, RESOLUTION_PRESETS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
T2V_GRAPH_PATH = PROJECT_ROOT / "workflows" / "api" / "minimax_h3_t2v_api.json"
T2V_WORKFLOW_ID = "minimax_h3_t2v_local_v1"


def compile_t2v_graph(plan: ReferencePlan, *, base_graph: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compile an explicit zero-reference plan; any supplied media is rejected."""
    if plan.images or plan.videos or plan.standalone_audios:
        raise GraphPlanError("t2v_references_unsupported", "H3 T2V accepts no reference assets; choose a supported R2V workflow for references.")
    if not isinstance(plan.prompt, str) or not plan.prompt.strip():
        raise GraphPlanError("missing_prompt", "A non-empty H3 prompt is required.")
    if not math.isfinite(plan.duration_seconds) or not 5 <= plan.duration_seconds <= 10:
        raise GraphPlanError("invalid_duration", "Local H3 T2V duration must be between 5 and 10 seconds.")
    if plan.aspect_ratio != "16:9" or plan.resolution_preset not in RESOLUTION_PRESETS:
        raise GraphPlanError("unsupported_t2v_canvas", "H3 T2V supports the validated 16:9 resolution presets only.")
    graph = copy.deepcopy(dict(base_graph if base_graph is not None else json.loads(T2V_GRAPH_PATH.read_text(encoding="utf-8"))))
    generators = [(node_id, node) for node_id, node in graph.items() if isinstance(node, dict) and node.get("class_type") == "MiniMaxH3ImageToVideo"]
    if len(generators) != 1:
        raise GraphPlanError("t2v_graph_contract", "H3 T2V base graph must contain exactly one MiniMaxH3ImageToVideo node.")
    _node_id, generator = generators[0]
    inputs = generator.setdefault("inputs", {})
    width, height = RESOLUTION_PRESETS[plan.resolution_preset]
    frames = max(5, math.ceil(plan.duration_seconds * 24))
    while frames % 17 != 5:
        frames += 1
    inputs.update({"prompt": plan.prompt, "width": width, "height": height, "length": frames})
    schedulers = [node["inputs"] for node in graph.values() if isinstance(node, dict) and node.get("class_type") == "BasicScheduler"]
    noises = [node["inputs"] for node in graph.values() if isinstance(node, dict) and node.get("class_type") == "RandomNoise"]
    if len(schedulers) != 1 or len(noises) != 1:
        raise GraphPlanError("t2v_graph_contract", "H3 T2V graph must contain exactly one scheduler and noise node.")
    schedulers[0]["steps"] = plan.steps
    noises[0]["noise_seed"] = plan.seed
    for node in graph.values():
        if isinstance(node, dict) and node.get("class_type") == "SaveVideo":
            node.setdefault("inputs", {})["filename_prefix"] = f"production_v2/{plan.run_id}/{plan.shot_id}"
    return {"workflow_id": T2V_WORKFLOW_ID, "graph": graph, "width": width, "height": height, "frame_count": frames}
