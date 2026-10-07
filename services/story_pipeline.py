"""Prompt builders for the story -> image planning pipeline."""

from __future__ import annotations

import json
from typing import Any

from story_builder.services.reasoning_provider import generate_json

STAGE_GUARDRAILS = """
Rules:
- return valid JSON only
- improve only the current stage artifact
- do not invent or rename workflow stages
- preserve continuity with all approved upstream artifacts
- do not discard established characters, locations, or story facts unless the upstream context explicitly changes them
""".strip()


def _json_block(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True)


def _style_block(style_context: dict[str, Any] | None) -> str:
    if not style_context:
        return ""
    return "\n\nPRODUCTION STYLE CONTRACT (follow this in every output):\n" + _json_block(style_context)


def generate_story_artifact(story_input: str, style_context: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt = f"""
You are preparing a story blueprint for AI-assisted image and video production.
{STAGE_GUARDRAILS}

Output schema:
{{
  "title": "string",
  "user_story_input": "string",
  "expanded_story": "2-5 paragraphs expanding the user's idea without writing screenplay formatting",
  "story_goal": "string",
  "tone": ["string"],
  "continuity_rules": ["string"],
  "visual_style_notes": ["string"]
}}

{_style_block(style_context)}

User story input:
{story_input}
""".strip()
    return generate_json(prompt=prompt)


def generate_characters_artifact(story_artifact: dict[str, Any], style_context: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt = f"""
Create production-ready character descriptions from this story blueprint.
{STAGE_GUARDRAILS}

Output schema:
{{
  "characters": [
    {{
      "id": "char_slug",
      "name": "string",
      "role": "lead/support/narrator/antagonist/etc",
      "gender_presentation": "string",
      "age_band": "string",
      "appearance": "single detailed paragraph",
      "wardrobe_baseline": "single detailed paragraph",
      "personality": ["string"],
      "visual_prompt": "string",
      "voice_alias_suggestion": "Alice/Bob/Narrator or custom"
    }}
  ]
}}

{_style_block(style_context)}

Story blueprint:
{_json_block(story_artifact)}
""".strip()
    return generate_json(prompt=prompt)


def generate_scenes_artifact(story_artifact: dict[str, Any], characters_artifact: dict[str, Any], style_context: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt = f"""
Create a scene-by-scene plan for an end video.
{STAGE_GUARDRAILS}

Output schema:
{{
  "scenes": [
    {{
      "id": "scene_slug",
      "scene_number": 1,
      "title": "string",
      "summary": "short paragraph",
      "location": "string",
      "time_of_day": "string",
      "continuity_notes": ["string"],
      "visible_characters": ["character ids"],
      "background_prompt": "string"
    }}
  ]
}}

{_style_block(style_context)}

Story blueprint:
{_json_block(story_artifact)}

Characters:
{_json_block(characters_artifact)}
""".strip()
    return generate_json(prompt=prompt)


def generate_subscenes_artifact(
    story_artifact: dict[str, Any],
    characters_artifact: dict[str, Any],
    scenes_artifact: dict[str, Any],
    style_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = f"""
Create cut-level sub-scenes for image generation planning.
{STAGE_GUARDRAILS}

Output schema:
{{
  "subscenes": [
    {{
      "id": "subscene_slug",
      "scene_id": "scene_slug",
      "shot_number": 1,
      "camera": "string",
      "blocking": "string",
      "action": "string",
      "mood": "string",
      "dialogue": [
        {{
          "speaker": "Narrator/Alice/Bob/or character name",
          "line": "string"
        }}
      ],
      "image_prompt": "string",
      "start_frame_brief": "string",
      "end_frame_brief": "string"
    }}
  ]
}}

{_style_block(style_context)}

Story blueprint:
{_json_block(story_artifact)}

Characters:
{_json_block(characters_artifact)}

Scenes:
{_json_block(scenes_artifact)}
""".strip()
    return generate_json(prompt=prompt)


def generate_dialogue_artifact(
    story_artifact: dict[str, Any],
    characters_artifact: dict[str, Any],
    scenes_artifact: dict[str, Any],
    subscenes_artifact: dict[str, Any],
    style_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = f"""
Create dialogue and narration plans for each approved sub-scene.
{STAGE_GUARDRAILS}

Output schema:
{{
  "dialogue_tracks": [
    {{
      "subscene_id": "subscene_slug",
      "beats": [
        {{
          "beat_id": "beat_slug",
          "speaker": "Narrator/Alice/Bob/or character name",
          "line": "string",
          "delivery_notes": ["string"],
          "timing_intent": "short description of pause/rhythm expectations",
          "onscreen_visibility": "onscreen/offscreen/cutaway"
        }}
      ],
      "narration_notes": ["string"],
      "sfx_notes": ["string"],
      "music_notes": ["string"]
    }}
  ]
}}

{_style_block(style_context)}

Story blueprint:
{_json_block(story_artifact)}

Characters:
{_json_block(characters_artifact)}

Scenes:
{_json_block(scenes_artifact)}

Sub-scenes:
{_json_block(subscenes_artifact)}
""".strip()
    return generate_json(prompt=prompt)


def generate_image_jobs_artifact(
    story_artifact: dict[str, Any],
    characters_artifact: dict[str, Any],
    scenes_artifact: dict[str, Any],
    subscenes_artifact: dict[str, Any],
    dialogue_artifact: dict[str, Any],
    style_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = f"""
Create an ordered image generation queue.
{STAGE_GUARDRAILS}

Output schema:
{{
  "jobs": [
    {{
      "job_id": "job_slug",
      "kind": "character_asset/background/scene_frame",
      "title": "string",
      "prompt": "string",
      "width": 1280,
      "height": 720,
      "scene_id": "optional scene slug or null",
      "subscene_id": "optional subscene slug or null"
    }}
  ]
}}

Requirements:
- include character asset jobs first
- then background jobs
- then scene frame jobs
- prompts should be ready for text-to-image generation
- preserve continuity from scene to scene

{_style_block(style_context)}

Story blueprint:
{_json_block(story_artifact)}

Characters:
{_json_block(characters_artifact)}

Scenes:
{_json_block(scenes_artifact)}

Sub-scenes:
{_json_block(subscenes_artifact)}

Dialogue:
{_json_block(dialogue_artifact)}
""".strip()
    return generate_json(prompt=prompt)
