from __future__ import annotations

import json
from typing import Any

from video_scene_summarizer.models.qwen_vl import OllamaTextGenerator
from video_scene_summarizer.models.schemas import SceneBoundary, SceneTransition


def analyze_scene_transitions(
    scenes: list[SceneBoundary],
    generator: OllamaTextGenerator,
    use_transcript_fusion: bool,
) -> list[SceneTransition]:
    transitions: list[SceneTransition] = []
    for previous, current in zip(scenes, scenes[1:]):
        context = _transition_context(previous, current, use_transcript_fusion)
        raw = generator.generate(prompt=_PROMPT, structured_context=json.dumps(context, ensure_ascii=False, indent=2))
        payload = _parse_object(raw)
        if payload is None:
            repair = generator.generate(
                prompt=_REPAIR_PROMPT,
                structured_context=json.dumps({"source": context, "invalid_output": raw}, ensure_ascii=False, indent=2),
            )
            payload = _parse_object(repair)
        transitions.append(_transition_from_payload(previous, current, payload))
    return transitions


def _transition_context(previous: SceneBoundary, current: SceneBoundary, include_transcript: bool) -> dict[str, Any]:
    def scene_payload(scene: SceneBoundary) -> dict[str, Any]:
        return {
            "scene_id": scene.scene_id,
            "start_time_sec": scene.start_time_sec,
            "end_time_sec": scene.end_time_sec,
            "scene_story": scene.scene_story_text or scene.scene_compiled_text,
            "keywords": scene.keywords,
            "transcript": scene.transcript_text if include_transcript else "",
        }
    return {"previous_scene": scene_payload(previous), "current_scene": scene_payload(current)}


def _parse_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _strings(payload: dict[str, Any], key: str, limit: int = 12) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


def _transition_from_payload(previous: SceneBoundary, current: SceneBoundary, payload: dict[str, Any] | None) -> SceneTransition:
    if payload is None:
        return SceneTransition(
            from_scene_id=previous.scene_id, to_scene_id=current.scene_id,
            from_time_sec=previous.end_time_sec, to_time_sec=current.start_time_sec,
            confidence="unknown", uncertainty_notes=["The model did not return valid transition JSON after one repair attempt."],
        )
    confidence = str(payload.get("confidence", "unknown")).strip().lower()
    if confidence not in {"high", "medium", "low", "unknown"}:
        confidence = "unknown"
    return SceneTransition(
        from_scene_id=previous.scene_id, to_scene_id=current.scene_id,
        from_time_sec=previous.end_time_sec, to_time_sec=current.start_time_sec,
        persistent_entities=_strings(payload, "persistent_entities"),
        appearing_entities=_strings(payload, "appearing_entities"),
        disappearing_entities=_strings(payload, "disappearing_entities"),
        location_change=str(payload.get("location_change", "")).strip(),
        time_change=str(payload.get("time_change", "")).strip(),
        visual_transition=str(payload.get("visual_transition", "")).strip(),
        activity_change=str(payload.get("activity_change", "")).strip(),
        narrative_connection=str(payload.get("narrative_connection", "")).strip(),
        transcript_connection=str(payload.get("transcript_connection", "")).strip(),
        evidence=_strings(payload, "evidence", limit=6), confidence=confidence,
        uncertainty_notes=_strings(payload, "uncertainty_notes", limit=6),
    )


_PROMPT = """Compare two adjacent video scene summaries. Return one JSON object only, with these keys:
persistent_entities, appearing_entities, disappearing_entities (arrays of short strings);
location_change, time_change, visual_transition, activity_change, narrative_connection,
transcript_connection (strings); evidence (array of short quotations or factual references);
confidence (high, medium, low, or unknown); uncertainty_notes (array of strings).
Use only supplied evidence. Do not invent identity, causation, location, or chronology."""

_REPAIR_PROMPT = """Repair the supplied invalid transition result into exactly one valid JSON object.
Use only the supplied source scenes. Required keys are persistent_entities, appearing_entities,
disappearing_entities, location_change, time_change, visual_transition, activity_change,
narrative_connection, transcript_connection, evidence, confidence, and uncertainty_notes.
Return JSON only."""
