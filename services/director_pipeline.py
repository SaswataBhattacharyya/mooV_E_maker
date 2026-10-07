"""Director-level scene brief generation used by the production coordinator."""

from __future__ import annotations

from typing import Any

from .reasoning_provider import generate_json
from .story_pipeline import _json_block, _style_block, STAGE_GUARDRAILS


def generate_director_plan(story: Any, characters: Any, scenes: Any, subscenes: Any, dialogue: Any, style: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt = f"""
You are the supervising film director. Turn the approved production artifacts into a coherent shot plan.
{STAGE_GUARDRAILS}
Every shot must preserve character identity and story facts. Explicitly coordinate camera, lens/framing,
lighting, palette, tone, emotion, blocking, dialogue delivery, music, foley, first/end frames, and duration.
Use 2-10 second shot durations unless the scene requires a shorter shot. Never invent a source asset or workflow.

Return JSON with this shape:
{{
  "director_contract": {{"continuity_rules": [], "visual_language": "", "audio_language": ""}},
  "shots": [{{"shot_id":"", "scene_id":"", "duration_seconds": 2, "camera":"", "lighting":"", "tone":"", "emotion":"", "blocking":"", "dialogue_beats":[], "music_cue":"", "foley_cue":"", "start_frame_brief":"", "end_frame_brief":"", "continuity_checks":[]}}],
  "review_policy": {{"must_retry_if": [], "human_approval_required": true}}
}}

{_style_block(style)}
STORY:\n{_json_block(story)}
CHARACTERS:\n{_json_block(characters)}
SCENES:\n{_json_block(scenes)}
SUBSCENES:\n{_json_block(subscenes)}
DIALOGUE:\n{_json_block(dialogue)}
""".strip()
    return generate_json(prompt=prompt)
