from typing import Any, Optional
import json
from core.schemas import CharacterIndex


def get_story_context() -> dict:
    """Get compact story context for downstream generation."""
    from core.state_manager import load_json
    from config import PROJECT_STATE_DIR

    if not PROJECT_STATE_DIR:
        return {}

    expanded = load_json(f"{PROJECT_STATE_DIR}/story/expanded_story.json")
    summary = load_json(f"{PROJECT_STATE_DIR}/story/story_summary.json")

    return {
        "story_text": (expanded or {}).get('expanded_story', ''),
        "logline": (expanded or {}).get('logline', ''),
        "story_summary_for_context": (summary or {}).get('story_summary_for_context', ''),
    }


def get_character_context(character_id: str) -> Optional[dict]:
    """Get full context for one character."""
    from core.state_manager import load_json, project_path

    char = load_json(project_path("characters", f"{character_id}.json"))
    if not char:
        return None

    story_summary = load_json(project_path("story", "story_summary.json"))

    index = load_json(project_path("characters", "characters_index.json"), {})
    idx_item = {}
    for c in index.get('characters', []):
        if c.get('character_id') == character_id:
            idx_item = c
            break

    return {
        "current_character": char,
        "index_entry": idx_item,
        "story_summary_for_context": (story_summary or {}).get('story_summary_for_context', ''),
    }


def get_structure_context() -> dict:
    """Get structure index context."""
    from core.state_manager import load_json, project_path

    structure = load_json(project_path("structure", "structure_index.json"))
    return structure or {}


def get_selected_unit_context(unit_id: str) -> Optional[dict]:
    """Get full data for a selected unit."""
    from core.state_manager import load_json
    from config import PROJECT_STATE_DIR

    unit_types = ["movie", "comic"]
    project_type_dir = ""
    file_path = None

    # Determine which type file structure contains this unit
    for utype in unit_types:
        fp = f"{PROJECT_STATE_DIR}/units/{utype}/{unit_id}.json"
        if __import__('os').path.isfile(fp):
            return load_json(fp) or {}

    # Fallback: try common paths
    for utype in unit_types:
        fp = f"{PROJECT_STATE_DIR}/units/{utype}"
        import os
        if os.path.isdir(fp):
            for fn in os.listdir(fp):
                fpath = f"{fp}/{fn}"
                if os.path.isfile(fpath) and (unit_id in fn or "scene" in fn or "page" in fn or "chapter" in fn or "section" in fn):
                    data = load_json(fpath)
                    if data:
                        return data

    return None


def get_neighboring_units_context(unit_id: str, count: int = 2) -> list[dict]:
    """Get context for neighboring units."""
    from core.state_manager import load_json
    from config import PROJECT_STATE_DIR
    import os

    neighbors = []
    for utype in ["movie", "comic"]:
        dir_path = f"{PROJECT_STATE_DIR}/units/{utype}"
        if not os.path.isdir(dir_path):
            continue
        files = sorted(os.listdir(dir_path))
        idx = -1
        for i, fn in enumerate(files):
            if unit_id in fn or int(fn[:-4]) == int(unit_id[-3:]):
                idx = i
                break
        if idx != -1:
            start = max(0, idx - count)
            end = min(len(files), idx + count + 1)
            for j in range(start, end):
                if files[j] != fn or True:
                    data = load_json(f"{dir_path}/{files[j]}")
                    if data:
                        neighbors.append({"file": files[j], "data": data})

    return neighbors[:count * 2]


def get_deletion_repair_context(object_type: str, object_id: str) -> dict:
    """Gather context needed for deletion repair."""
    from core.state_manager import load_json, project_path
    import os as _os

    ctx = {"object_type": object_type, "object_id": object_id}

    if object_type == "character":
        ctx["deleted_character"] = load_json(project_path("characters", f"{object_id}.json"))
        ctx["characters_after"] = load_json(project_path("characters", "characters_index.json"), {})
        ctx["story_summary"] = load_json(project_path("story", "story_summary.json"), {})

        # Find references in structure
        structure = load_json(project_path("structure", "structure_index.json"))
        if structure:
            ctx["affected_units"] = _find_references(structure, object_id)

    ctx["story_context"] = get_story_context()
    return ctx


def _find_references(obj: Any, target_id: str) -> list[str]:
    """Recursively find references to an ID in a data structure."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if target_id in str(v):
                found.append(f"{k} contains {target_id}")
            elif isinstance(v, (dict, list)):
                found.extend(_find_references(v, target_id))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if target_id in str(item):
                found.append(f"[{i}] = {item}")
            elif isinstance(item, (dict, list)):
                found.extend(_find_references(item, target_id))
    return found
