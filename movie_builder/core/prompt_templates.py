def build_story_generation_prompt(project_intake: dict) -> str:
    """Build prompt for expanding a raw story idea."""
    genre = project_intake.get("custom_genre", "") or project_intake.get("genre", "Drama")
    tone = project_intake.get("custom_tone", "") or project_intake.get("tone", "Emotional")
    visual_style = project_intake.get("visual_style", "Photorealistic")
    target_format = project_intake.get("target_format", "Feature Film (90-120 min)")

    prompt = f"""You are a creative story development assistant.

**Project Title:** {project_intake.get('title', 'Untitled')}
**Project Type:** {project_intake.get('project_type', 'Movie / Short Film')}
**Genre:** {genre}
**Tone:** {tone}
**Visual Style:** {visual_style}
**Target Format/Duration:** {target_format}
**Language:** {project_intake.get('language', 'English')}

**Raw Story Idea:**
{project_intake.get('raw_story', '')}

**Style References:**
{project_intake.get('style_references', 'None')}

**Things to Avoid:**
{project_intake.get('things_to_avoid', 'None')}

Please generate the expanded story. Return ONLY valid JSON with this structure and nothing else:

{{
  "logline": "One-sentence summary of the story.",
  "short_synopsis": "A 2-3 paragraph synopsis.",
  "expanded_story": "A detailed multi-paragraph expanded story with full narrative arc.",
  "themes": ["theme1", "theme2", "theme3"],
  "ending": "Description of the story's ending."
}}

Return valid JSON only. No markdown. No commentary. Keep all fields concise but complete."""

    return prompt


def build_story_revision_prompt(current_story: dict, revision_instruction: str) -> str:
    """Build prompt for revising a generated story."""
    prompt = f"""Revise the following story based on the user's instructions.

**Revision Instructions:**
{revision_instruction}

**Current Expanded Story:**
{current_story.get('expanded_story', '')}

**Current Logline:**
{current_story.get('logline', '')}

**Current Themes (JSON):**
{current_story.get('themes', [])}

**Current Ending:**
{current_story.get('ending', '')}

**Current Short Synopsis:**
{current_story.get('short_synopsis', '')}

Revise the expanded story, logline, themes, and ending based on the instructions. Return ONLY valid JSON with this structure and nothing else:

{{
  "logline": "...",
  "short_synopsis": "...",
  "expanded_story": "...",
  "themes": ["..."],
  "ending": "..."
}}

Return valid JSON only. No markdown. No commentary."""

    return prompt


def build_story_summary_prompt(expanded_story: dict) -> str:
    """Build prompt to generate a compact story summary for context."""
    prompt = f"""Read the following story and produce a compact summary suitable for use as project context in future generations.

**Expanded Story Text:**
{expanded_story.get('expanded_story', '')}

Summarize the core story with key details that any downstream generation would need:
- Main plot points (3-5 key events)
- Primary characters and their roles
- Setting/time period
- Central conflict
- Tone/style notes
- Genre specifics

Return ONLY valid JSON with this structure and nothing else:

{{
  "story_summary_for_context": "Concise paragraph summary."
}}

Return valid JSON only. No markdown. No commentary."""

    return prompt


def build_character_index_prompt(story_summary: dict, project_type: str) -> str:
    """Build prompt to generate a character index from the story."""
    story_text = story_summary.get('expanded_story', '') or story_summary.get('story_summary_for_context', '')

    prompt = f"""Analyze this story and generate a character index (list of characters with their roles).

**Story Summary:**
{story_text}

**Project Type:** {project_type}

Generate the required JSON format. Return ONLY valid JSON with this structure and nothing else:

{{
  "characters": [
    {{
      "character_id": "char_001",
      "position": 1,
      "name": "",
      "role": "protagonist/antagonist/supporting/minor",
      "short_description": "Brief description (1-2 sentences).",
      "story_purpose": "Why this character exists in the story.",
      "appears_in_units": [],
      "status": "draft"
    }}
  ]
}}

Return valid JSON only. No markdown. No commentary."""

    return prompt


def build_character_detail_prompt(story_summary: dict, character_index_item: dict, project_type: str) -> str:
    """Build prompt to generate full character detail."""
    story_text = story_summary.get('expanded_story', '') or story_summary.get('story_summary_for_context', '')

    fields_by_type = {
        "Movie / Short Film": "physical_description, costume, expression_notes, pose_notes, visual_prompt, speech_style, backstory, motivation, fear, arc",
        "Comic / Graphic Novel": "physical_description, costume, expression_notes, pose_notes, visual_prompt, speech_style, backstory, motivation, fear, arc",
        "Book / Novel": "book_voice, personality, inner_conflict, pov_style, backstory, motivation, fear, arc, speech_style",
    }
    key_fields = fields_by_type.get(project_type, "physical_description, costume, speech_style, backstory")

    prompt = f"""Generate the full character detail for this character ONLY. Do not modify or mention any other characters.

**Story Summary:**
{story_text}

**Character Index Entry:**
Name: {character_index_item.get('name', '')}
Role: {character_index_item.get('role', '')}
Short Description: {character_index_item.get('short_description', '')}

**Project Type:** {project_type}

Generate ALL of these fields. Return ONLY valid JSON with this structure and nothing else:

{{
  "character_id": "{character_index_item.get('character_id', 'char_001')}",
  "name": "{character_index_item.get('name', '')}",
  "role": "{character_index_item.get('role', '')}",
  "age_range": "",
  "gender_presentation": "string",
  "personality": "string",
  "backstory": "string",
  "motivation": "string",
  "fear": "string",
  "arc": "string",
  "{key_fields}": ""
}}

Return valid JSON only. No markdown. No commentary. Only revise this one character."""

    return prompt


def build_character_revision_prompt(story_summary: dict, current_character: dict, revision_instruction: str) -> str:
    """Build prompt for revising a single character."""
    story_text = story_summary.get('expanded_story', '') or story_summary.get('story_summary_for_context', '')

    existing_fields_str = ""
    for k, v in current_character.items():
        if k not in ('summary_for_context',) and isinstance(v, str):
            if v:
                existing_fields_str += f'  "k": "{v}",\n'

    character_fields = (
        '  "age_range": "",\n  "gender_presentation": "",\n  "personality": "",\n'
        '  "backstory": "",\n  "motivation": "",\n  "fear": "",\n  "arc": "",\n'
        '  "speech_style": "",\n  "physical_description": "",\n  "costume": "",\n'
        '  "expression_notes": "",\n  "pose_notes": "",\n  "visual_prompt": "",\n'
        '  "book_voice": "",\n  "inner_conflict": "",\n  "pov_style": "",\n'
        '  "audio_voice_profile": "",\n  "accent": "",\n  "pace": "",\n'
        '  "emotion_range": ""'
    )

    prompt = f"""Revise ONLY this character based on the following instructions. Do NOT modify any other character.

**Revision Instructions:**
{revision_instruction}

**Story Summary (for context):**
{story_text}

**Current Character Data:**
{str(current_character)}

Only revise this one character. Update only the fields that need changing. Return ONLY valid JSON with the same structure as above and nothing else:

{{
  "character_id": "{current_character.get('character_id', '')}",
  "name": "{current_character.get('name', '')}",
  "role": "{current_character.get('role', '')}",
{character_fields}
}}

Return valid JSON only. No markdown. No commentary."""

    return prompt


def build_world_bible_prompt(story_summary: dict, characters_index: dict, project_type: str) -> str:
    """Build prompt to generate World/Style Bible."""
    story_text = story_summary.get('expanded_story', '') or story_summary.get('story_summary_for_context', '')

    extra_fields = ""
    if "Book" in project_type:
        extra_fields = ', "narrative_voice": "string", "prose_style": "string", "chapter_rhythm": "string"'
    elif "Comic" in project_type or "Anime" in project_type:
        extra_fields = ', "art_style": "string", "linework": "string", "panel_or_cut_style": "string", "color_style": "string"'

    prompt = f"""Generate a World Bible and Style Bible for this story.

**Story Summary:**
{story_text}

**Project Type:** {project_type}

**Characters (names):**
{str(list(characters_index.get('characters', []))) if isinstance(characters_index, dict) else 'None'}

Generate the required JSON format with world rules, locations, visual style notes, color palette, mood, genre conventions and reference style notes:{extra_fields} 

Return ONLY valid JSON with this structure and nothing else:

{{
  "world_rules": ["string"],
  "locations": [{{"location_id": "location_001", "name": "", "short_description": "", "visual_notes": "", "story_use": ""}}],
  "visual_style": "string",
  "color_palette": ["string"],
  "mood": "string",
  "genre_conventions": ["string"],
  "reference_style_notes": "string"{extra_fields}
}}

Return valid JSON only. No markdown. No commentary."""

    return prompt


def build_structure_index_prompt(story_summary: dict, characters_index: dict, world_bible: dict, project_type: str) -> str:
    """Build prompt to generate structure index (Acts/Chapters)."""
    story_text = story_summary.get('expanded_story', '') or story_summary.get('story_summary_for_context', '')

    # Determine output format based on project type
    if "Movie" in project_type:
        item_hint = 'Act items with scenes arrays. Each act has title, short_description, and scenes[] each with scene_id, position, title, short_description, scene_purpose, primary_characters, status.'
        items_template = '{{"act_id": "act_001", "position": 1, "title": "", "short_description": "", "scenes": []}}'
    elif "Comic" in project_type:
        item_hint = 'Chapter items with pages arrays. Each chapter has title, short_description, and pages[] each with page_id, position, short_description, panel_count_target, page_purpose, status.'
        items_template = '{{"chapter_id": "ch_001", "position": 1, "title": "", "short_description": "", "pages": []}}'
    elif "Book" in project_type:
        item_hint = 'Chapter items with sections arrays. Each chapter has title, short_description, pov, chapter_purpose, and sections[] each with section_id, position, short_description, beat_purpose, status.'
        items_template = '{{"chapter_id": "ch_001", "position": 1, "title": "", "short_description": "", "pov": "", "chapter_purpose": "", "sections": []}}'
    else:
        item_hint = 'Top-level items relevant to the project type.'
        items_template = '{}'

    prompt = f"""Generate a structure index for this story.

**Story Summary:**
{story_text}

**Project Type:** {project_type}

{item_hint}

Return ONLY valid JSON with this structure and nothing else:

{{
  "project_type": "{project_type}",
  "items": [{items_template}]
}}

Return valid JSON only. No markdown. No commentary."""

    return prompt


def build_structure_repair_prompt(context: dict, changed_item: dict, change_type: str) -> str:
    """Build prompt for structure repair after add/delete/move."""
    prompt = f"""Repair the structure index after a structural change.

**Change Type:** {change_type}

**Changed Item:**
{str(changed_item)}

**Current Structure Before Change (if available):**
{str(context.get('before', 'N/A'))}

**Current Structure After Change (if available):**
{str(context.get('after', 'N/A'))}

Update the structure_index to reflect this change consistently. Preserve all unaffected items exactly as they are. Update position values sequentially. Mark any affected downstream units with status "needs_revision" if needed.

Return ONLY valid JSON and nothing else."""

    return prompt


def build_character_delete_repair_prompt(context: dict, deleted_character: dict) -> str:
    """Build prompt for coherence repair after character deletion."""
    prompt = f"""Repair story continuity after a character was deleted.

**Deleted Character:**
Name: {deleted_character.get('name', 'Unknown')}
Summary: {deleted_character.get('short_description', '')}

**Story Summary:**
{context.get('story_summary', 'N/A')}

**Character Index After Deletion:**
{str(context.get('characters_after', 'N/A'))}

**Affected Units (if any):**
{str(context.get('affected_units', 'None specified'))}

Repair only the affected references in story summaries, structure indices, and affected unit files. Update continuity notes where appropriate. Do NOT regenerate the whole story.

Return ONLY valid JSON for the changes needed (story_summary update, affected items) and nothing else."""

    return prompt


def build_unit_generation_prompt(context: dict, selected_unit: dict, project_type: str) -> str:
    """Build prompt to generate a unit's full details."""
    story_text = context.get('story_summary', '') or 'N/A'
    chars = context.get('characters_present', 'Unknown')

    block_instructions = {
        "Movie / Short Film": "scene_summary, subscenes, characters_present, dialogue, action_blocking, background_location, props, costume_makeup, camera_notes, lighting_notes, sound_effects, music, vfx_sfx, storyboard_prompts, continuity_notes",
        "Comic / Graphic Novel": "page-level notes and panel blocks (panel_size, visual_description, characters_visible, pose_expression, background, caption, speech_bubbles, sfx_text, image_prompt)",
        "Book / Novel": "chapter_summary, chapter_beats, pov, setting, characters_present, emotional_arc, section_draft, continuity_notes",
    }

    prompt = f"""Generate the full details for this {project_type} unit.

**Story Summary:**
{story_text}

**Characters Present:**
{str(chars)}

**Project Type:** {project_type}

**Selected Unit:**
{str(selected_unit)}

Generate all blocks for {block_instructions.get(project_type, 'the relevant structure')}. Return ONLY valid JSON matching the target schema and nothing else. No markdown. No commentary."""

    return prompt


def build_unit_block_revision_prompt(context: dict, selected_unit: dict, block_name: str, revision_instruction: str) -> str:
    """Build prompt for revising a specific block in a unit."""
    current_data = context.get('current_data', {})

    prompt = f"""Revise ONLY the '{block_name}' block of this unit. Preserve all other blocks.

**Revision Instruction:**
{revision_instruction}

**Current Unit Data (relevant blocks):**
{str(current_data)}

**Story Summary (context only):**
{context.get('story_summary', 'N/A')}

Only revise this block in the selected unit. Preserve all other blocks unless a tiny reference update is required. Return ONLY valid JSON with the updated full data and nothing else."""

    return prompt
