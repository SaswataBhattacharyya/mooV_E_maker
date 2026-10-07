from __future__ import annotations

import hashlib
import json

import pytest

from story_builder.services.chunked_generation import (
    ChunkedGenerationError,
    GenerationBudgetError,
    chunk_units,
    generate_chunked_units,
    generate_story_canon,
    split_source_text,
)


def test_enriched_scene_unit_fits_controller_budget_without_losing_source():
    unit = {"unit_id": "scene-001", "source_context": "s" * 4700}
    context = {"director_context": "c" * 2080}
    calls = []
    def generator(**kwargs):
        calls.append(kwargs["prompt"])
        return {"items": [{"unit_id": "scene-001", "content": {"summary": "Scene."}}]}
    with pytest.raises(GenerationBudgetError):
        generate_chunked_units(stage="scenes", units=[unit], context=context,
            max_chars_per_batch=8000, generator=generator)
    assert calls == []
    result = generate_chunked_units(stage="scenes", units=[unit], context=context,
        max_chars_per_batch=16000, generator=generator)
    assert result["complete"] is True
    assert unit["source_context"] in calls[0]
    assert len(calls[0]) < 16000


def _story_response(prompt: str, **_kwargs):
    marker = "Exact source text as a JSON string (decode it; preserve every character):\n"
    source = json.loads(prompt.split(marker, 1)[1].split("\n\n", 1)[0])
    # Unit fixtures use a simple first token, with exact local character offsets.
    stripped = source.strip()
    offset = source.index(stripped.split()[0])
    quote = stripped.split()[0]
    return {
        "chunk_id": prompt.split('"chunk_id":"', 1)[1].split('"', 1)[0],
        "source_excerpt": source,
        "source_facts": [{"quote": quote, "start": offset, "end": offset + len(quote), "category": "event"}],
        "expanded_text": f"{source.strip()}\nInferred: A connective detail.",
        "inferred_details": ["Inferred: A connective detail."],
        "continuity_summary": "The established story continues.",
        "story_goal": "Reach the next story beat.",
        "tone": ["dramatic"],
        "continuity_rules": ["Keep event order."],
        "visual_style_notes": ["Night exterior."],
    }


def test_source_chunks_cover_exact_input_without_gaps_or_loss():
    source = ("A first event.\n\n" + "A second event with details. " * 90 + "\n\nThe ending.")
    chunks = split_source_text(source, max_chars=300)
    assert len(chunks) > 2
    assert "".join(chunk.text for chunk in chunks) == source
    assert [chunk.start for chunk in chunks] == [0, *[chunk.end for chunk in chunks[:-1]]]
    assert chunks[-1].end == len(source)


def test_story_canon_runs_in_bounded_chunks_and_verifies_source_facts():
    source = "Asha finds the key.\n\n" + "She follows a trail of blue lanterns. " * 50 + "\n\nAsha opens the gate."
    calls = []

    def generator(**kwargs):
        calls.append(kwargs["prompt"])
        return _story_response(**kwargs)

    result = generate_story_canon(title="Lantern Gate", source_text=source,
                                  max_chars_per_chunk=220, generator=generator)
    assert len(calls) == len(result["chunks"]) > 1
    assert all(len(call) < 3000 for call in calls)
    assert result["user_story_input"] == source
    assert result["source_hash"] == hashlib.sha256(source.encode()).hexdigest()
    assert result["completeness"]["all_source_chunks_echoed"] is True
    assert result["completeness"]["completed_chunk_ids"] == result["completeness"]["expected_chunk_ids"]
    assert all(source[fact["source_start"]:fact["source_end"]] == fact["text"] for fact in result["source_facts"])
    assert result["inferred_details"] and all(item["is_inference"] for item in result["inferred_details"])


def test_story_fact_offsets_are_derived_from_exact_quote_not_provider_indices():
    source = "Asha finds the key and opens the gate."

    def generator(**kwargs):
        result = _story_response(**kwargs)
        result["source_facts"] = [{"quote": "opens the gate", "start": 999, "end": 1000,
                                   "category": "event"}]
        return result

    result = generate_story_canon(title="Gate", source_text=source, generator=generator)
    fact = result["source_facts"][0]
    assert fact["text"] == "opens the gate"
    assert source[fact["source_start"]:fact["source_end"]] == fact["text"]


def test_shot_plan_writer_uses_catalog_without_copying_asset_ids_or_tags():
    prompts = []
    catalog = [{"shot_id": "shot-1", "images": [{"asset_id": "pa-0123456789abcdef",
        "role": "character_master", "entity_id": "character-1"}], "videos": [], "voice_references": []}]

    def generator(*, prompt, **_kwargs):
        prompts.append(prompt)
        return {"items": [{"unit_id": "shot-1", "content": {"prompt": "Asha opens the gate.",
            "duration_seconds": 5, "dialogue": [], "asset_intents": [
                {"role": "character_master", "intent": "Preserve Asha's approved identity."}]}}]}

    result = generate_chunked_units(stage="shot_plans", units=[{"unit_id": "shot-1",
        "approved_dialogue_lines": [{"speaker_id": "char-1", "text": "We should go."}]}],
        context={"approved_reference_catalog": catalog}, generator=generator)

    assert result["items"][0]["unit_id"] == "shot-1"
    assert "approved_reference_catalog" in prompts[0]
    assert "pa-0123456789abcdef" in prompts[0]
    assert "do not copy IDs or invent reference tags" in prompts[0]
    assert "exact key listed in Stage context.supported_asset_roles" in prompts[0]
    assert "Return an empty asset_intents array when no approved project asset is relevant" in prompts[0]
    assert "Copy that array exactly into content.dialogue" in prompts[0]
    assert '"speaker_id":"character-id"' in prompts[0]


def test_dialogue_writer_emits_shot_scoped_lines_from_stable_shot_inputs():
    prompts = []
    unit = {"unit_id": "shot-001-01", "scene_id": "scene-001",
        "character_ids": ["character-maya"], "shot_outline": {"action": "Maya speaks."},
        "scene_context": {"title": "The warning"}}

    def generator(*, prompt, **_kwargs):
        prompts.append(prompt)
        return {"items": [{"unit_id": "shot-001-01", "content": {"dialogue": [
            {"speaker_id": "character-maya", "text": "The storm is coming."}]}}]}

    result = generate_chunked_units(stage="dialogue", units=[unit],
        context={"character_identity_map": {"character-maya": "Maya"}}, generator=generator)

    assert result["items"][0]["content"]["dialogue"][0]["speaker_id"] == "character-maya"
    assert "Each requested unit is one planned shot" in prompts[0]
    assert "do not group beats" in prompts[0]
    assert "move lines" in prompts[0]
    assert '"character-maya": "Maya"' in prompts[0]
    assert 'Output content exactly as {"dialogue": []}' in prompts[0]
    assert "content object must have exactly one key, dialogue" in prompts[0]
    assert "exactly speaker_id and text, with delivery as the only optional third key" in prompts[0]
    assert "Do not add fields such as character, character_name, emotion, line_id, timing, or notes" in prompts[0]


def test_scene_writer_keeps_shared_source_chunk_beats_inside_assigned_scene_unit():
    prompts = []
    unit = {"unit_id": "scene-002", "source_chunk_ids": ["story_chunk_0001"],
        "scene_outline": {"title": "Cafe arrival", "location": "Mira's cafe",
            "summary": "Arun arrives with the key.", "dramatic_turn": "Arun joins Mira."},
        "shot_units": [{"unit_id": "shot-002-01", "shot_outline": {"action": "Arun enters."}}],
        "source_context": [{"chunk_id": "story_chunk_0001", "expanded_text":
            "Arun arrives. Mira explains the key. Later, Arun returns it."}]}

    def generator(*, prompt, **_kwargs):
        prompts.append(prompt)
        assert 'Each content MUST contain a "shots" array' in prompt
        assert '"unit_id" copied exactly' in prompt
        assert '"beat" string' in prompt
        return {"items": [{"unit_id": "scene-002", "content": {"summary": "Arun enters the cafe.",
            "shots": [{"unit_id": "shot-002-01", "beat": "Arun enters the cafe."}]}}]}

    result = generate_chunked_units(stage="scenes", units=[unit], context={}, generator=generator)
    assert result["items"][0]["scene_outline"] == unit["scene_outline"]
    assert result["items"][0]["source_context"] == unit["source_context"]
    assert "scene_outline and shot_units as the boundary" in prompts[0]
    assert "do not pull later events forward from a shared source chunk" in prompts[0]
    assert "do not stage off-screen or future characters as present" in prompts[0]
    from story_builder.api.main import _validate_generated_scene_items
    _validate_generated_scene_items(result["items"], [unit])


def test_story_chunk_invalid_provider_output_is_retried_then_fails_closed():
    source = "Asha finds the key and opens the gate."
    attempts = []

    def generator(**kwargs):
        attempts.append(kwargs["prompt"])
        return {**_story_response(**kwargs), "source_excerpt": "truncated"}

    with pytest.raises(ChunkedGenerationError, match="failed after 2 bounded attempt"):
        generate_story_canon(title="Test", source_text=source, max_attempts_per_chunk=2,
                             generator=generator)
    assert len(attempts) == 2


def test_chunked_units_repairs_only_missing_ids_for_very_long_dialogue_scene():
    units = [{"unit_id": f"scene-1-beat-{index:03d}", "speaker": "A", "line": "A long dialogue line. " * 4}
             for index in range(90)]
    prompts = []

    def generator(*, prompt, **_kwargs):
        prompts.append(prompt)
        requested = prompt.split("Requested units (all IDs are mandatory):\n", 1)[1].split("\nAttempt", 1)[0]
        batch = json.loads(requested)
        # Simulate output truncation for the first two attempts by returning half the IDs.
        selected = batch if len(prompts) % 3 == 0 else batch[:max(1, len(batch) // 2)]
        return {"items": [{"unit_id": item["unit_id"], "content": {"dialogue": item["line"]}} for item in selected]}

    result = generate_chunked_units(stage="dialogue", units=units, context={"scene_id": "scene-1"},
                                    max_chars_per_batch=1800, max_attempts=3, generator=generator)
    assert result["complete"] is True
    assert result["completed_unit_ids"] == [unit["unit_id"] for unit in units]
    assert len(result["items"]) == len(units)
    assert len(prompts) > len(chunk_units(units, max_chars=1800))
    assert len({row["unit_id"] for row in result["items"]}) == len(units)
    assert max(len(prompt) for prompt in prompts) <= 1800


def test_dialogue_prompt_forbids_mapping_unnamed_roles_to_named_character_ids():
    prompts = []

    def generator(*, prompt, **_kwargs):
        prompts.append(prompt)
        return {"items": [{"unit_id": "dialogue-001", "content": {"beats": []}}]}

    generate_chunked_units(stage="dialogue", units=[{
        "unit_id": "dialogue-001", "character_ids": ["mira-id", "arun-id"],
        "scene_context": {"characters": ["Mira", "Arun"], "event": "The unnamed keeper receives a map."},
    }], context={}, generator=generator)

    assert "Speakers must be named characters" in prompts[0]
    assert "Each requested unit is one planned shot" in prompts[0]
    assert "Use only its scene_context, shot_outline, and source_context" in prompts[0]
    assert "pull later events from shared source" in prompts[0]
    assert "whose IDs are listed in the unit's character_ids" in prompts[0]
    assert "No speech for unnamed roles" in prompts[0]


def test_chunked_generation_preserves_authored_source_links_and_speaker_metadata():
    unit = {"unit_id": "line-001", "source": "Say the supplied words.",
            "source_chunk_ids": ["story_chunk_0001"], "speaker_id": "S1",
            "source_context": [{"chunk_id": "story_chunk_0001", "source_facts": [{"text": "Nila."}]}]}
    result = generate_chunked_units(stage="dialogue", units=[unit], context={"story_goal": "Meet."},
        generator=lambda **_kwargs: {"items": [{"unit_id": "line-001", "content": {"exact_words": "Hello."}}]})

    assert result["items"][0]["unit_id"] == "line-001"
    assert result["items"][0]["source_chunk_ids"] == ["story_chunk_0001"]
    assert result["items"][0]["source_context"] == unit["source_context"]
    assert result["items"][0]["source"] == unit["source"]
    assert result["items"][0]["speaker_id"] == "S1"
    assert result["items"][0]["content"] == {"exact_words": "Hello."}


@pytest.mark.parametrize("rows", [
    [{"unit_id": "x", "content": {}}, {"unit_id": "x", "content": {}}],
    [{"unit_id": "not-requested", "content": {}}],
])
def test_chunked_units_rejects_duplicate_or_unexpected_provider_ids(rows):
    with pytest.raises(ChunkedGenerationError):
        generate_chunked_units(stage="scenes", units=[{"unit_id": "x", "source": "scene"}],
                               context={}, generator=lambda **_kwargs: {"items": rows})


def test_chunk_units_rejects_single_oversized_scene_instead_of_exceeding_budget():
    with pytest.raises(ValueError, match="split that unit into stable sub-units"):
        chunk_units([{"unit_id": "large", "body": "x" * 1000}], max_chars=256)


def test_visual_brief_writer_and_bounded_director_repair_share_stage_contract():
    from story_builder.services.chunked_generation import VISUAL_BRIEF_CONTRACT
    from story_builder.services.director_contract import review_text_stage_revision

    prompts = []
    source = {"unit_id": "visual-001", "scene_id": "scene-001",
              "source_chunk_ids": ["chunk-001"], "character_ids": ["mira-id", "arun-id"],
              "scene_context": {"shots": [{"beat": "Four people leave with one dog."}]}}
    content = {"visual_brief": "Four people and a dog evacuate the stairwell.",
               "continuity": {"lighting": "Diffuse daylight from the landing window."},
               "shots": [{"first_frame": "The group waits on the landing.",
                          "last_frame": "Five people leave with the dog."}]}

    def writer(*, prompt, **_kwargs):
        prompts.append(prompt)
        return {"items": [{"unit_id": "visual-001", "content": content}]}

    revision = generate_chunked_units(stage="visual_briefs", units=[source], context={}, generator=writer)
    revision["stage"] = "visual_briefs"

    def director(*, prompt, **_kwargs):
        prompts.append(prompt)
        if "Repair only the content" in prompt:
            return {"content": {**content, "shots": [{**content["shots"][0],
                "last_frame": "Four people leave with the dog."}]}}
        return {"decision": "repair" if 'Five people' in prompt else "approve",
                "confidence": 0.95, "issues": ["Wrong person count."] if 'Five people' in prompt else [],
                "repair_instruction": "Correct five to four; retain the lighting continuity."}

    reviewed = review_text_stage_revision(revision=revision, generator=director)
    assert reviewed["accepted"] is True
    assert len(prompts) == 4
    assert all(VISUAL_BRIEF_CONTRACT in prompt for prompt in prompts)
    item = reviewed["items"][0]
    assert item["scene_id"] == source["scene_id"]
    assert item["source_chunk_ids"] == source["source_chunk_ids"]
    assert item["character_ids"] == source["character_ids"]
    assert item["content"]["continuity"] == content["continuity"]
    assert item["content"]["shots"][0]["last_frame"] == "Four people leave with the dog."
