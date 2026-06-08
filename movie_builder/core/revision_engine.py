from core.ollama_client import generate_json, repair_json
from core.chunking import get_story_context, get_character_context, get_deletion_repair_context
from core.state_manager import save_json, load_json, append_change_log, project_path
import config as cfg


def revise_story(revision_instruction: str) -> dict:
    """Revise the story based on instructions."""
    from core.schemas import ExpandedStory
    from core.ollama_client import generate_json, generate_text
    from core.prompt_templates import build_story_revision_prompt

    current = load_json(project_path("story", "expanded_story.json")) or {}
    prompt = build_story_revision_prompt(current, revision_instruction)

    # Parse the text response directly
    full_text = generate_text(prompt)
    try:
        import json as j
        result = j.loads(full_text) if full_text else {}
        return result
    except Exception:
        return {"error": "Failed to parse story revision. Check the raw output."}


def revise_character(character_id: str, revision_instruction: str) -> dict:
    """Revise a single character."""
    from core.prompt_templates import build_character_revision_prompt
    from core.chunking import get_character_context

    ctx = get_character_context(character_id)
    if not ctx:
        return {"error": f"Character {character_id} not found."}

    current_char = ctx["current_character"]
    prompt = build_character_revision_prompt(ctx, current_char, revision_instruction)

    from core.ollama_client import generate_json
    result = generate_json(prompt)
    save_json(project_path("characters", f"{character_id}.json"), result)

    append_change_log({
        "action": "revise_character",
        "character_id": character_id,
        "instruction": revision_instruction,
    })

    return result


def revise_unit_block(unit_id: str, block_name: str, revision_instruction: str) -> dict:
    """Revise a specific block in a unit file."""
    from core.chunking import get_selected_unit_context
    from core.prompt_templates import build_unit_block_revision_prompt
    from core.state_manager import save_json

    ctx = get_selected_unit_context(unit_id)
    if not ctx:
        return {"error": f"Unit {unit_id} not found."}

    current_data = load_json(project_path("units", f"{unit_id}.json")) if isinstance(ctx, dict) else {}
    structure_context = {**ctx, "current_data": current_data}

    prompt = build_unit_block_revision_prompt(
        structure_context, {"unit_id": unit_id}, block_name, revision_instruction
    )

    from core.ollama_client import generate_json
    result = generate_json(prompt)
    save_json(project_path("units", f"{unit_id}.json"), result)

    append_change_log({
        "action": "revise_unit_block",
        "unit_id": unit_id,
        "block_name": block_name,
        "instruction": revision_instruction,
    })

    return result


def repair_after_character_delete(character_id: str) -> dict:
    """Repair story coherence after character deletion."""
    from core.prompt_templates import build_character_delete_repair_prompt
    from core.chunking import get_deletion_repair_context

    ctx = get_deletion_repair_context("character", character_id)
    deleted_char = ctx.get("deleted_character", {})

    prompt = build_character_delete_repair_prompt(ctx, deleted_char)

    from core.ollama_client import generate_json
    result = generate_json(prompt)

    # Apply changes if any story_summary update is returned
    if "story_summary_for_context" in result:
        save_json(project_path("story", "story_summary.json"), {
            "story_summary_for_context": result["story_summary_for_context"]
        })

    append_change_log({
        "action": "repair_after_character_delete",
        "character_id": character_id,
    })

    return result


def repair_after_structure_change(change: dict) -> dict:
    """Repair story coherence after a structure change."""
    from core.prompt_templates import build_structure_repair_prompt
    from core.chunking import get_structure_context

    structure = get_structure_context()
    ctx = {
        "before": change.get("before", {}),
        "after": change.get("after", {}),
        "changed_item": change.get("changed_item", {}),
        "change_type": change.get("change_type", "unknown"),
    }

    prompt = build_structure_repair_prompt(ctx, change.get("changed_item", {}), change.get("change_type", "unknown"))

    from core.ollama_client import generate_json
    result = generate_json(prompt)

    if "items" in result:
        save_json(project_path("structure", "structure_index.json"), result)

    append_change_log({
        "action": "repair_after_structure_change",
        "change": change,
    })

    return result
