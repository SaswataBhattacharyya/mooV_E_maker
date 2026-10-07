"""Chunked, completeness-checked text generation for production V2.

The source artifact is partitioned before any provider call. Each chunk is
saved/validated as an identified unit so output limits cannot silently erase
later story facts, scenes, or dialogue beats.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from story_builder.services import reasoning_provider
from story_builder.services.reasoning_provider import ReasoningProviderError, generate_json


VISUAL_BRIEF_CONTRACT = """For visual_briefs, produce an image-stage plan for the supplied scene_context.
Preserve the exact cast count, identities, assigned beats and setting; a dog is not a person.
Include a concise visual_brief, continuity identifiers for each visible character/animal and the
location, and first_frame/last_frame descriptions for each supplied scene beat in order.
Reuse accepted appearance details when supplied. If appearance is unspecified, label practical
visual identifiers as proposed design choices, never source facts; keep them consistent across frames.
Use content.continuity.visible_characters_and_animal as an array of objects with id, identity and
proposed_design_choice, and content.continuity.location as an object with id and identifier.
For supplied canonical characters and worlds, id must be that exact stable canon ID. Never substitute
a display name or array position. These explicit per-ID fields feed downstream master prompts.
For the same stable ID, repeat proposed_design_choice or location.identifier exactly across all
scene units. These fields describe permanent appearance, wardrobe and location geometry only.
Keep changing poses, actions, lighting and scene cross-references in visual_brief or scene_beats;
never put them in these master identity fields. Preserve any supplied fixed_master_designs exactly.
Specify coherent lens/framing, lighting direction and palette across the scene and its frame pairs.
Make the final state physically clear without inventing a new event, destination or rescue outcome.
This stage proposes visual design; character/world master images and render-ready shot prompts are
created downstream. Do not demand existing master images, exact millimeter lenses, or missing source
appearance as prerequisites. During repair, retain unaffected valid visual details and check the whole
contract as well as the identified defect; do not replace a detailed brief with a generic synopsis."""


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    index: int
    start: int
    end: int
    text: str


class GenerationBudgetError(ValueError):
    """Input cannot fit its budget; retrying identical input cannot repair it."""


class ChunkedGenerationError(RuntimeError):
    def __init__(self, *, stage: str, unit_id: str, message: str, attempts: int) -> None:
        super().__init__(message)
        self.stage = stage
        self.unit_id = unit_id
        self.attempts = attempts
        self.code = "chunk_generation_incomplete"

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "stage": self.stage, "unit_id": self.unit_id,
                "message": str(self), "attempts": self.attempts, "retryable": True}


def split_source_text(text: str, *, max_chars: int = 2400) -> list[SourceChunk]:
    """Partition text into contiguous exact slices; no source characters drop."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("A non-empty story source is required.")
    if max_chars < 128:
        raise ValueError("max_chars must be at least 128 characters.")
    chunks: list[SourceChunk] = []
    start, index, length = 0, 1, len(text)
    while start < length:
        target = min(length, start + max_chars)
        end = target
        if target < length:
            minimum = start + max(1, max_chars // 2)
            candidates = [text.rfind("\n\n", minimum, target), text.rfind("\n", minimum, target),
                          text.rfind(". ", minimum, target), text.rfind("! ", minimum, target),
                          text.rfind("? ", minimum, target), text.rfind(" ", minimum, target)]
            boundary = max(candidates)
            if boundary >= minimum:
                end = boundary + (2 if text[boundary:boundary + 2] in {"\n\n", ". ", "! ", "? "} else 1)
        if end <= start:
            end = min(length, start + max_chars)
        chunks.append(SourceChunk(f"story_chunk_{index:04d}", index, start, end, text[start:end]))
        start, index = end, index + 1
    if not chunks or chunks[0].start != 0 or chunks[-1].end != length:
        raise RuntimeError("Internal source chunking error: source coverage is incomplete.")
    if any(left.end != right.start for left, right in zip(chunks, chunks[1:])):
        raise RuntimeError("Internal source chunking error: source chunks contain a gap or overlap.")
    return chunks


def _bounded_call(prompt: str, *, provider: str | None, call: Callable[..., dict[str, Any]] | None) -> dict[str, Any]:
    generator = call or generate_json
    result = generator(prompt=prompt, temperature=0.25, provider=provider)
    if not isinstance(result, dict):
        raise ReasoningProviderError("Provider response must be a JSON object.")
    return result


def _story_chunk_prompt(*, source_chunk: SourceChunk, title: str, chunk_count: int,
                        continuity_context: str, director_profile: dict[str, Any] | None = None,
                        narrative_style_guidance: dict[str, Any] | None = None,
                        retry_note: str = "") -> str:
    return f"""You are the story-development writer working under the Director.
Expand exactly one source chunk for a coherent production story. Do not compress or skip the source.
The exact original text must be echoed in source_excerpt. List explicit facts only as verbatim quotes
from this chunk. Do not calculate character offsets; the server locates each exact quote in the source.
Put invented connective detail only in inferred_details and label it as inference. Keep expanded_text tightly grounded in the source. If it
contains any invented action, cause, setting, or outcome, mark that exact sentence in expanded_text
with the literal prefix "Inferred:" and include the same complete sentence in inferred_details. Do not
add details merely to make the story longer. When the source is a fragment list or very sparse, do not
merely echo it: turn it into concise, coherent prose with a minimal connective action that gives the
reader a usable story progression. Mark that connective action as an inference using the rule above.
Do not change names, event order, relationships, or outcomes.
Return one complete JSON object and no markdown.

Required output schema:
{{"chunk_id":"{source_chunk.chunk_id}","source_excerpt":"exact source chunk","source_facts":[{{"quote":"exact substring","category":"character|event|relationship|setting|object|time|other"}}],"expanded_text":"clear, coherent expansion of this chunk; under 10000 characters","inferred_details":["clearly marked creative inference"],"continuity_summary":"short handoff for the next chunk","story_goal":"string","tone":["string"],"continuity_rules":["string"],"visual_style_notes":["string"]}}

Project title: {title}
This is chunk {source_chunk.index} of {chunk_count}; preserve its position in the whole story.
Previously established context (context only; never overrides source):
{continuity_context or "No prior chunk."}

Active production-type Director profile (behavior guidance, not a source of story facts):
{json.dumps(director_profile or {}, ensure_ascii=False)}

Resolved narrative style guidance for this stage (style only; never overrides source facts):
{json.dumps(narrative_style_guidance or {}, ensure_ascii=False)}

Source chunk id: {source_chunk.chunk_id}
Source offsets: {source_chunk.start}..{source_chunk.end}
Exact source text as a JSON string (decode it; preserve every character):
{json.dumps(source_chunk.text, ensure_ascii=False)}

{retry_note}""".strip()


def _validate_story_chunk(result: dict[str, Any], source_chunk: SourceChunk, *, stage: str, attempts: int) -> dict[str, Any]:
    if result.get("chunk_id") != source_chunk.chunk_id:
        raise ChunkedGenerationError(stage=stage, unit_id=source_chunk.chunk_id,
                                     message="Provider returned a missing or mismatched chunk_id.", attempts=attempts)
    if result.get("source_excerpt") != source_chunk.text:
        raise ChunkedGenerationError(stage=stage, unit_id=source_chunk.chunk_id,
                                     message="Provider did not preserve the exact source excerpt.", attempts=attempts)
    expanded = result.get("expanded_text")
    if not isinstance(expanded, str) or not expanded.strip() or len(expanded) > 10000:
        raise ChunkedGenerationError(stage=stage, unit_id=source_chunk.chunk_id,
                                     message="Expanded story text is empty or exceeds the 10000-character per-chunk ceiling.", attempts=attempts)
    raw_facts = result.get("source_facts")
    if not isinstance(raw_facts, list) or (not raw_facts and source_chunk.text.strip()):
        raise ChunkedGenerationError(stage=stage, unit_id=source_chunk.chunk_id,
                                     message="No source-supported facts were returned.", attempts=attempts)
    facts: list[dict[str, Any]] = []
    allowed_categories = {"character", "event", "relationship", "setting", "object", "time", "other"}
    for fact_index, row in enumerate(raw_facts, 1):
        if not isinstance(row, dict):
            raise ChunkedGenerationError(stage=stage, unit_id=source_chunk.chunk_id,
                                         message=f"Fact {fact_index} is not an object.", attempts=attempts)
        quote = row.get("quote")
        if not isinstance(quote, str) or not quote:
            raise ChunkedGenerationError(stage=stage, unit_id=source_chunk.chunk_id,
                                         message=f"Fact {fact_index} lacks a non-empty verbatim source quote.", attempts=attempts)
        # Model-generated character offsets are unreliable. Derive provenance from the exact
        # quotation instead; when it repeats, the first occurrence is a deterministic valid span.
        start = source_chunk.text.find(quote)
        if start < 0:
            raise ChunkedGenerationError(stage=stage, unit_id=source_chunk.chunk_id,
                                         message=f"Fact {fact_index} quote is not a verbatim source substring.", attempts=attempts)
        end = start + len(quote)
        fact_hash = hashlib.sha256(f"{source_chunk.start + start}:{quote}".encode("utf-8")).hexdigest()[:10]
        category = str(row.get("category") or "other")
        if category not in allowed_categories:
            raise ChunkedGenerationError(stage=stage, unit_id=source_chunk.chunk_id,
                                         message=f"Fact {fact_index} uses unsupported category {category!r}.", attempts=attempts)
        facts.append({"fact_id": f"fact-{fact_hash}", "text": quote,
                      "source_start": source_chunk.start + start, "source_end": source_chunk.start + end,
                      "source_chunk_id": source_chunk.chunk_id,
                      "category": category})
    inferences = result.get("inferred_details", [])
    if not isinstance(inferences, list) or any(not isinstance(item, str) for item in inferences):
        raise ChunkedGenerationError(stage=stage, unit_id=source_chunk.chunk_id,
                                     message="inferred_details must be a list of strings.", attempts=attempts)
    for field_name in ("tone", "continuity_rules", "visual_style_notes"):
        field_value = result.get(field_name, [])
        if not isinstance(field_value, list) or any(not isinstance(item, str) for item in field_value):
            raise ChunkedGenerationError(stage=stage, unit_id=source_chunk.chunk_id,
                                         message=f"{field_name} must be a list of strings.", attempts=attempts)
    return {"chunk_id": source_chunk.chunk_id, "index": source_chunk.index,
            "source_start": source_chunk.start, "source_end": source_chunk.end,
            "source_excerpt": source_chunk.text, "source_facts": facts,
            "expanded_text": expanded.strip(), "inferred_details": inferences,
            "continuity_summary": str(result.get("continuity_summary") or "").strip(),
            "story_goal": str(result.get("story_goal") or "").strip(),
            "tone": list(result.get("tone", [])),
            "continuity_rules": list(result.get("continuity_rules", [])),
            "visual_style_notes": list(result.get("visual_style_notes", []))}


def generate_story_canon(*, title: str, source_text: str, provider: str | None = None,
                         max_chars_per_chunk: int = 2400, max_attempts_per_chunk: int = 2,
                         prior_context: str = "", director_profile: dict[str, Any] | None = None,
                         narrative_style_guidance: dict[str, Any] | None = None,
                         generator: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    """Expand a story in bounded requests with exact-source and completeness checks."""
    if max_attempts_per_chunk < 1 or max_attempts_per_chunk > 4:
        raise ValueError("max_attempts_per_chunk must be between 1 and 4.")
    if not isinstance(prior_context, str) or len(prior_context) > 4000:
        raise ValueError("prior_context must be text of at most 4000 characters.")
    source_chunks = split_source_text(source_text, max_chars=max_chars_per_chunk)
    accepted: list[dict[str, Any]] = []
    context = prior_context
    for chunk in source_chunks:
        if not chunk.text.strip():
            accepted.append({"chunk_id": chunk.chunk_id, "index": chunk.index,
                             "source_start": chunk.start, "source_end": chunk.end,
                             "source_excerpt": chunk.text, "source_facts": [],
                             "expanded_text": "", "inferred_details": [],
                             "continuity_summary": context, "story_goal": "", "tone": [],
                             "continuity_rules": [], "visual_style_notes": []})
            continue
        last_error: Exception | None = None
        for attempt in range(1, max_attempts_per_chunk + 1):
            retry_note = ""
            if last_error:
                retry_note = ("Previous response was incomplete or invalid. Return the entire required JSON object again.\n"
                              f"Validation issue: {str(last_error)[:400]}\n")
            prompt = _story_chunk_prompt(source_chunk=chunk, title=title, chunk_count=len(source_chunks),
                                         continuity_context=context, director_profile=director_profile,
                                         narrative_style_guidance=narrative_style_guidance,
                                         retry_note=retry_note)
            try:
                result = _bounded_call(prompt, provider=provider, call=generator)
                row = _validate_story_chunk(result, chunk, stage="story_detail", attempts=attempt)
                accepted.append(row)
                context = row["continuity_summary"] or row["expanded_text"][-1000:]
                break
            except (ChunkedGenerationError, ReasoningProviderError, ValueError, TypeError) as exc:
                last_error = exc
        else:
            raise ChunkedGenerationError(stage="story_detail", unit_id=chunk.chunk_id,
                                         message=f"Chunk failed after {max_attempts_per_chunk} bounded attempt(s): {last_error}",
                                         attempts=max_attempts_per_chunk) from last_error
    expected_ids = [chunk.chunk_id for chunk in source_chunks]
    actual_ids = [row["chunk_id"] for row in accepted]
    if actual_ids != expected_ids:
        raise ChunkedGenerationError(stage="story_detail", unit_id="story_assembly",
                                     message="Assembled story chunks are missing, duplicated, or out of order.",
                                     attempts=max_attempts_per_chunk)
    facts = [fact for row in accepted for fact in row["source_facts"]]
    facts.sort(key=lambda fact: (fact["source_start"], fact["source_end"]))
    if any(source_text[fact["source_start"]:fact["source_end"]] != fact["text"] for fact in facts):
        raise ChunkedGenerationError(stage="story_detail", unit_id="story_assembly",
                                     message="A fact lost its exact source evidence during assembly.",
                                     attempts=max_attempts_per_chunk)
    expanded_story = "\n\n".join(row["expanded_text"] for row in accepted if row["expanded_text"])
    return {
        "schema_version": 1,
        "revision_id": f"story-canon-{uuid.uuid4().hex[:12]}",
        "title": title,
        "user_story_input": source_text,
        "source_hash": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "provider": provider or reasoning_provider.get_settings().get("provider", "codex"),
        "model": reasoning_provider.model_for(provider or reasoning_provider.get_settings().get("provider", "codex")),
        "expanded_story": expanded_story,
        "story_goal": next((row["story_goal"] for row in accepted if row["story_goal"]), ""),
        "tone": list(dict.fromkeys(item for row in accepted for item in row["tone"])),
        "continuity_rules": list(dict.fromkeys(item for row in accepted for item in row["continuity_rules"])),
        "visual_style_notes": list(dict.fromkeys(item for row in accepted for item in row["visual_style_notes"])),
        "source_facts": facts,
        "inferred_details": [{"chunk_id": row["chunk_id"], "text": detail, "is_inference": True}
                             for row in accepted for detail in row["inferred_details"]],
        "chunks": accepted,
        "completeness": {"expected_chunk_ids": expected_ids, "completed_chunk_ids": actual_ids,
                         "source_coverage": [0, len(source_text)], "all_source_chunks_echoed": True,
                         "all_fact_evidence_verified": True},
    }


def chunk_units(units: list[dict[str, Any]], *, unit_id_key: str = "unit_id", max_chars: int = 6000) -> list[list[dict[str, Any]]]:
    """Batch stable scene/dialogue units under a bounded prompt character budget."""
    if max_chars < 256:
        raise ValueError("max_chars must be at least 256 characters.")
    seen: set[str] = set()
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for index, unit in enumerate(units):
        if not isinstance(unit, dict) or not isinstance(unit.get(unit_id_key), str) or not unit[unit_id_key].strip():
            raise ValueError(f"Unit {index} is missing a stable {unit_id_key}.")
        unit_id = unit[unit_id_key]
        if unit_id in seen:
            raise ValueError(f"Duplicate unit ID: {unit_id}")
        seen.add(unit_id)
        size = len(json.dumps(unit, ensure_ascii=False))
        if size > max_chars:
            raise GenerationBudgetError(f"Unit {unit_id} is {size} characters, exceeding the {max_chars}-character batch limit; split that unit into stable sub-units first.")
        if current and current_chars + size > max_chars:
            batches.append(current)
            current, current_chars = [], 0
        current.append(unit)
        current_chars += size
    if current:
        batches.append(current)
    return batches


def generate_chunked_units(*, stage: str, units: list[dict[str, Any]], context: dict[str, Any],
                           provider: str | None = None, unit_id_key: str = "unit_id",
                           max_chars_per_batch: int = 6000, max_attempts: int = 2,
                           generator: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    """Generate records in bounded batches and repair only missing unit IDs."""
    if not units:
        return {"stage": stage, "items": [], "expected_unit_ids": [], "completed_unit_ids": []}
    if max_attempts < 1 or max_attempts > 4:
        raise ValueError("max_attempts must be between 1 and 4.")
    context_json = json.dumps(context, ensure_ascii=False)
    # Reserve space for task instructions/schema and global context so the
    # configured batch bound applies to the whole prompt, not just unit JSON.
    # Keep margin for the largest structured-stage contract and JSON wrapper.
    unit_budget = max_chars_per_batch - len(context_json) - 1500
    if unit_budget < 256:
        raise GenerationBudgetError(f"Generation context uses {len(context_json)} characters; reduce context or increase max_chars_per_batch (currently {max_chars_per_batch}).")
    batches = chunk_units(units, unit_id_key=unit_id_key, max_chars=unit_budget)
    assembled: dict[str, dict[str, Any]] = {}
    for batch in batches:
        remaining = list(batch)
        for attempt in range(1, max_attempts + 1):
            expected = [unit[unit_id_key] for unit in remaining]
            stage_output_contract = (
                'For shot_plans, every content object MUST contain a non-empty "prompt" (plain text), '
                '"duration_seconds" as a number from 5 through 15, "dialogue" as an array, and '
                '"asset_intents" as an array of role/intent descriptions. For each role, use only an '
                'exact key listed in Stage context.supported_asset_roles; never invent or paraphrase a role. '
                'Return an empty asset_intents array when no approved project asset is relevant. Use the '
                'approved_reference_catalog only to understand which approved project roles and '
                'run-bound voice excerpts are available; do not copy IDs or invent reference tags. '
                'Keep concrete reference wiring outside this generated text. The prompt must be a complete, '
                'render-ready visual/audio instruction grounded in the supplied accepted story facts. '
                'Label invented camera, ambience or character actions separately in content.inference; do not present them as source facts. '
                'When prior_content and repair_issues are supplied, repair only those issues while preserving the shot boundary and exact dialogue. '
                'Each requested shot includes approved_dialogue_lines copied from the accepted dialogue stage. '
                'Copy that array exactly into content.dialogue, preserving each speaker_id and text; do not '
                'omit, paraphrase, add, or move lines between shots. Use an empty array only when the '
                'approved_dialogue_lines array is empty. Example content: {"prompt":"Maya speaks in the '
                'apartment.","duration_seconds":5,"dialogue":[{"speaker_id":"character-id",'
                '"text":"The storm is coming."}],"asset_intents":[]}.'
                if stage == "shot_plans" else ""
            )
            if stage == "scenes":
                stage_output_contract = (
                    "For scenes, each requested unit is one already-planned scene. Treat its scene_outline "
                    "and shot_units as the boundary for which dramatic beats belong here. "
                    'Each content MUST contain a "shots" array, with exactly one object per input shot_units entry. '
                    'Each object MUST contain "unit_id" copied exactly from that shot_units entry and a non-empty '
                    '"beat" string describing its assigned action. Preserve shot order; never substitute shot_id, '
                    'description, or action for these required keys. Example content: '
                    '{"summary":"Scene summary","shots":[{"unit_id":"exact-input-shot-unit-id","beat":"Assigned action."}]}. '
                    "Use source_context "
                    "to ground facts, but do not pull later events forward from a shared source chunk, replay "
                    "an event assigned to another scene, or add new scene events, characters, or locations. "
                    "Use prior/future facts only to preserve state and continuity; do not stage off-screen or "
                    "future characters as present in this scene. Keep the assigned beats in their planned order."
                )
            elif stage == "dialogue":
                stage_output_contract = (
                    "Each requested unit is one planned shot. Use only its scene_context, shot_outline, and "
                    "source_context. Output content exactly as {\"dialogue\": []}; the content object must "
                    "have exactly one key, dialogue. Each dialogue line object must contain exactly speaker_id "
                    "and text, with delivery as the only optional third key. Do not add fields such as "
                    "character, character_name, emotion, line_id, timing, or notes at either level. For example, "
                    "a populated content value is {\"dialogue\":[{\"speaker_id\":\"exact-character-id\","
                    "\"text\":\"The exact words spoken.\"}]}; add delivery only when needed. "
                    "Include only this shot's exact lines; do not group beats, move lines, or pull later events "
                    "from shared source. Preserve quoted source dialogue. Speakers must be named characters "
                    "whose IDs are listed in the unit's character_ids. Map IDs to names with "
                    "character_identity_map; never infer by order or role. No speech for unnamed roles, props, "
                    "narrators, or locations. Do not invent IDs or add other content fields."
                )
            elif stage == "visual_briefs":
                stage_output_contract = VISUAL_BRIEF_CONTRACT
            prompt = f"""You are the {stage} writer under the supervising Director. Return valid JSON only.
Generate complete records for every requested unit ID. Do not omit, merge, rename, or reorder IDs.
Preserve all established source facts and exact user-authored dialogue. If the response would be long,
complete this batch and stop; later batches will be requested separately.
{stage_output_contract}

Output shape: {{"items":[{{"unit_id":"one requested ID","content":{{}}}}]}}
Stage context:
{context_json}
Requested units (all IDs are mandatory):
{json.dumps(remaining, ensure_ascii=False)}
Attempt {attempt} of {max_attempts}.""".strip()
            try:
                response = _bounded_call(prompt, provider=provider, call=generator)
            except (ReasoningProviderError, ValueError, TypeError) as exc:
                if attempt == max_attempts:
                    raise ChunkedGenerationError(stage=stage, unit_id=expected[0],
                                                 message=f"Provider output was invalid after {attempt} attempt(s): {exc}",
                                                 attempts=attempt) from exc
                continue
            returned = response.get("items")
            if not isinstance(returned, list):
                returned = []
            expected_set = set(expected)
            observed: dict[str, dict[str, Any]] = {}
            malformed_or_unexpected: list[str] = []
            duplicate_ids: list[str] = []
            for row in returned:
                if not isinstance(row, dict) or not isinstance(row.get(unit_id_key), str):
                    malformed_or_unexpected.append("<malformed>")
                    continue
                key = row[unit_id_key]
                if key not in expected_set or not isinstance(row.get("content"), dict):
                    malformed_or_unexpected.append(key)
                elif key in observed:
                    duplicate_ids.append(key)
                else:
                    observed[key] = row
            if malformed_or_unexpected or duplicate_ids:
                if attempt == max_attempts:
                    details = []
                    if malformed_or_unexpected:
                        details.append(f"unexpected/malformed IDs: {malformed_or_unexpected[:5]}")
                    if duplicate_ids:
                        details.append(f"duplicate IDs: {duplicate_ids[:5]}")
                    raise ChunkedGenerationError(stage=stage, unit_id=expected[0],
                                                 message="Provider returned invalid unit records (" + "; ".join(details) + ").",
                                                 attempts=attempt)
                continue
            assembled.update(observed)
            remaining = [unit for unit in remaining if unit[unit_id_key] not in observed]
            if not remaining:
                break
            if attempt == max_attempts:
                raise ChunkedGenerationError(stage=stage, unit_id=remaining[0][unit_id_key],
                                             message=f"Missing {len(remaining)} unit(s) after bounded continuation attempts.",
                                             attempts=attempt)
    ordered = []
    for unit in units:
        generated = dict(assembled[unit[unit_id_key]])
        # Provider output owns generated content only. Keep authored IDs,
        # source links, speaker fields and provenance attached to the unit
        # instead of asking the model to reproduce trusted input metadata.
        for key, value in unit.items():
            if key != "content":
                generated[key] = value
        generated[unit_id_key] = unit[unit_id_key]
        ordered.append(generated)
    expected_ids = [unit[unit_id_key] for unit in units]
    completed_ids = [row[unit_id_key] for row in ordered]
    if completed_ids != expected_ids:
        raise ChunkedGenerationError(stage=stage, unit_id="assembly",
                                     message="Generated records are incomplete or out of source order.", attempts=max_attempts)
    return {"stage": stage, "items": ordered, "expected_unit_ids": expected_ids,
            "completed_unit_ids": completed_ids, "complete": True}
