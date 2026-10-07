"""Small, project-local continuity graph.

The graph is deliberately JSON and dependency-free. It is the durable source
that can later be imported into Graphiti without making the production run
depend on a separate graph database.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(kind: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    return f"{kind}:{digest}"


def _graph_path(project_dir: Path) -> Path:
    return project_dir / "graph" / "continuity.json"


def _load(project_dir: Path) -> dict[str, Any]:
    path = _graph_path(project_dir)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"schema_version": 1, "project_id": project_dir.name, "nodes": [], "edges": [], "events": [], "updated_at": _now()}


def _save(project_dir: Path, graph: dict[str, Any]) -> dict[str, Any]:
    path = _graph_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    graph["updated_at"] = _now()
    path.write_text(json.dumps(graph, indent=2, ensure_ascii=True), encoding="utf-8")
    return graph


def update_artifact(project_dir: Path, artifact_type: str, content: Any) -> dict[str, Any]:
    """Upsert an artifact node and useful stable entity nodes after a stage."""
    graph = _load(project_dir)
    nodes = {item["id"]: item for item in graph.get("nodes", []) if item.get("id")}
    edges = {(item.get("source"), item.get("target"), item.get("relation")): item for item in graph.get("edges", [])}
    artifact_id = _id("artifact", f"{project_dir.name}:{artifact_type}")
    nodes[artifact_id] = {"id": artifact_id, "kind": "artifact", "artifact_type": artifact_type, "updated_at": _now()}

    def entity(kind: str, value: str, parent: str) -> None:
        value = str(value).strip()
        if not value:
            return
        node_id = _id(kind, f"{project_dir.name}:{value.lower()}")
        nodes.setdefault(node_id, {"id": node_id, "kind": kind, "name": value})
        key = (artifact_id, node_id, "mentions")
        edges.setdefault(key, {"source": artifact_id, "target": node_id, "relation": "mentions"})

    if isinstance(content, dict):
        for item in content.get("characters", []) if isinstance(content.get("characters"), list) else []:
            if isinstance(item, dict): entity("character", item.get("id") or item.get("name", ""), artifact_id)
        for item in content.get("scenes", []) if isinstance(content.get("scenes"), list) else []:
            if isinstance(item, dict): entity("scene", item.get("id") or item.get("title", ""), artifact_id)
        for item in content.get("subscenes", []) if isinstance(content.get("subscenes"), list) else []:
            if isinstance(item, dict): entity("subscene", item.get("id", ""), artifact_id)
        for item in content.get("dialogue_tracks", []) if isinstance(content.get("dialogue_tracks"), list) else []:
            if isinstance(item, dict): entity("subscene", item.get("subscene_id", ""), artifact_id)
        for key in ("title", "story_goal", "tone", "visual_style_notes"):
            value = content.get(key)
            if isinstance(value, list):
                for entry in value[:12]: entity(key, str(entry), artifact_id)
            elif isinstance(value, str): entity(key, value, artifact_id)

    graph["nodes"] = list(nodes.values())
    graph["edges"] = list(edges.values())
    graph.setdefault("events", []).append({"at": _now(), "type": "artifact_completed", "artifact_type": artifact_type, "artifact_id": artifact_id})
    return _save(project_dir, graph)


def read(project_dir: Path) -> dict[str, Any]:
    return _load(project_dir)
