import os
from core.state_manager import load_json, save_json, project_path, ensure_project_dirs


def get_unit_options(project_type: str, structure_index: dict) -> dict:
    """Get available units for selection based on project type."""
    ensure_project_dirs()

    if "Movie" in project_type:
        acts = []
        for item in structure_index.get('items', []):
            acts.append({
                'id': item.get('act_id', ''),
                'title': item.get('title', ''),
                'scenes': [s['scene_id'] for s in item.get('scenes', [])],
            })
        return {"type": "movie", "acts": acts, "items": "scenes", "prefix": "scene"}

    elif "Comic" in project_type:
        chapters = []
        for item in structure_index.get('items', []):
            chap_id = item.get('chapter_id', '')
            pages = [p['page_id'] for p in item.get('pages', [])]
            chapters.append({
                'id': chap_id,
                'title': item.get('title', ''),
                'pages': pages,
            })
        return {"type": "comic", "chapters": chapters, "items": "pages", "prefix": "page"}

    elif "Book" in project_type:
        chapters = []
        for item in structure_index.get('items', []):
            chap_id = item.get('chapter_id', '')
            sections = [s['section_id'] for s in item.get('sections', [])]
            chapters.append({
                'id': chap_id,
                'title': item.get('title', ''),
                'sections': sections,
            })
        return {"type": "book", "chapters": chapters, "items": "sections", "prefix": "section"}

    else:
        return {"type": "generic", "items": [], "prefix": ""}


def load_unit(project_type: str, unit_id: str) -> dict:
    """Load a unit file by type and ID."""
    ensure_project_dirs()

    unit_map = {
        "Movie / Short Film": "movie",
        "Comic / Graphic Novel": "comic",
        "Book / Novel": "book",
    }
    dir_name = unit_map.get(project_type, "movie")

    file_path = f"units/{dir_name}/{unit_id}.json"
    return load_json(project_path(file_path)) or {}


def save_unit(project_type: str, unit_id: str, data: dict) -> None:
    """Save a unit file by type and ID."""
    ensure_project_dirs()

    unit_map = {
        "Movie / Short Film": "movie",
        "Comic / Graphic Novel": "comic",
        "Book / Novel": "book",
    }
    dir_name = unit_map.get(project_type, "movie")

    file_path = f"units/{dir_name}/{unit_id}.json"
    save_json(project_path(file_path), data)


def generate_or_regenerate_unit(project_type: str, unit_id: str) -> dict:
    """Trigger regeneration of a unit. (Placeholder - calls LLM in real usage)."""
    # In practice this would use ollama_client + prompt_templates
    from core.chunking import get_selected_unit_context
    ctx = get_selected_unit_context(unit_id)

    if not ctx:
        return {"error": f"Unit {unit_id} context not available. Ensure structure index exists."}

    return {"status": "pending", "unit_id": unit_id, "context_available": bool(ctx)}


def revise_unit_block(project_type: str, unit_id: str, block_name: str, instruction: str) -> dict:
    """Revise a specific block within a unit. (Placeholder - calls LLM in real usage)."""
    from core.chunking import get_selected_unit_context
    from core.prompt_templates import build_unit_block_revision_prompt

    ctx = get_selected_unit_context(unit_id)
    if not ctx:
        return {"error": f"Unit {unit_id} not found."}

    prompt = build_unit_block_revision_prompt(
        {"story_summary": (ctx.get('expanded_story') or {}).get('story_summary_for_context', '')},
        {"unit_id": unit_id},
        block_name, instruction
    )

    # In a real implementation, this would call ollama_client.generate_json(prompt)

    return {"status": "pending", "block_name": block_name, "prompt": prompt[:200] + "..."}
