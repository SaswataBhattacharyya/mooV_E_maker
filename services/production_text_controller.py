"""Narrative scene and shot outline planning for the durable text controller."""
from __future__ import annotations

import re
from typing import Any, Callable

from story_builder.services.reasoning_provider import ReasoningProviderError, generate_json
from story_builder.services.production_world_state import (
    WorldStateError,
    create_anonymous_character,
    create_world,
    read_project_canon,
    save_project_canon,
)


class SceneOutlineError(ValueError):
    """The Director's scene outline cannot safely seed downstream revisions."""


class ShotReferenceResolutionError(ValueError):
    """A generated reference selection is incomplete or outside its approved catalog."""


def resolve_shot_reference_catalog(*, shot_id: str, asset_intents: list[dict[str, Any]],
                                   catalog: list[dict[str, Any]],
                                   selector: Callable[..., dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Resolve declared roles to IDs from one shot's approved catalog only.

    The selector is untrusted: every chosen ID, role, intent and speaker is
    checked against the accepted shot plan and catalog before it can reach the
    compiler. Missing/ambiguous role pools fail closed.
    """
    if (not isinstance(shot_id, str) or not shot_id.strip()
            or not isinstance(asset_intents, list)
            or any(not isinstance(row, dict) or not isinstance(row.get("role"), str)
                or not isinstance(row.get("intent"), str) or not row["intent"].strip()
                for row in asset_intents)
            or not callable(selector)):
        raise ShotReferenceResolutionError("Shot reference selection inputs are malformed.")
    matches = [row for row in catalog if isinstance(row, dict) and row.get("shot_id") == shot_id]
    if len(matches) != 1:
        raise ShotReferenceResolutionError("Exactly one approved catalog row is required for this shot.")
    source = matches[0]
    groups = {
        "images": source.get("images"),
        "videos": source.get("videos"),
        "standalone_audios": source.get("voice_references"),
    }
    role_groups = {"character_master": "images", "world_master": "images",
        "action_reference_video": "videos", "previous_cut_tail": "videos",
        "voice_excerpt": "standalone_audios"}
    if not asset_intents:
        return {"images": [], "videos": [], "standalone_audios": []}
    for intent in asset_intents:
        group = role_groups.get(intent["role"])
        if group is None:
            raise ShotReferenceResolutionError(f"Role {intent['role']!r} is not available to the shot catalog resolver.")
        candidates = groups[group]
        if not isinstance(candidates, list) or not any(
                isinstance(row, dict) and row.get("role") == intent["role"] for row in candidates):
            raise ShotReferenceResolutionError(f"No approved catalog candidate exists for requested role {intent['role']!r}.")
    request = {"shot_id": shot_id, "shot": {key: source.get(key) for key in
        ("scene_id", "character_ids", "world_id")}, "asset_intents": asset_intents,
        "approved_catalog": groups,
        "instruction": "Choose only the supplied IDs, only for declared role/intents. Return JSON with images, videos, standalone_audios arrays; each item has asset_id, role and exact intent; audio also has the catalog speaker_id. Do not invent IDs, roles, tags or intent text."}
    try:
        choice = selector(request=request)
    except Exception as exc:
        raise ShotReferenceResolutionError(f"Shot reference selector failed: {exc}") from exc
    if not isinstance(choice, dict) or set(choice) != set(groups):
        raise ShotReferenceResolutionError("Selector must return exactly images, videos and standalone_audios arrays.")
    limits = {"images": 9, "videos": 3, "standalone_audios": 3}
    result: dict[str, list[dict[str, Any]]] = {}
    selected_ids: set[str] = set()
    used_intents: list[tuple[str, str]] = []
    for group, limit in limits.items():
        rows, allowed_rows = choice[group], groups[group]
        if not isinstance(rows, list) or len(rows) > limit or not isinstance(allowed_rows, list):
            raise ShotReferenceResolutionError(f"Selector returned an invalid or oversized {group} list.")
        allowed = {row.get("asset_id"): row for row in allowed_rows if isinstance(row, dict)
            and isinstance(row.get("asset_id"), str) and row.get("role")}
        normalized = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("asset_id"), str):
                raise ShotReferenceResolutionError(f"Each {group} choice must name a catalog asset ID.")
            asset_id = row["asset_id"]
            candidate = allowed.get(asset_id)
            if candidate is None or asset_id in selected_ids or row.get("role") != candidate.get("role"):
                raise ShotReferenceResolutionError(f"Asset {asset_id!r} is not a unique role-matched choice from this shot's catalog.")
            role, intent_text = candidate["role"], row.get("intent")
            if not isinstance(intent_text, str) or (role, intent_text) not in {
                    (item["role"], item["intent"]) for item in asset_intents}:
                raise ShotReferenceResolutionError("Selected assets must use an exact role/intent declared by the shot plan.")
            selected = {"asset_id": asset_id, "role": role, "intent": intent_text}
            if group == "standalone_audios":
                speaker_id = candidate.get("speaker_id")
                if not isinstance(speaker_id, str) or not speaker_id.strip() or row.get("speaker_id") != speaker_id:
                    raise ShotReferenceResolutionError("Voice references must preserve the catalog-bound speaker ID.")
                selected["speaker_id"] = speaker_id
            elif "speaker_id" in row:
                raise ShotReferenceResolutionError("Only bound voice-reference selections may carry a speaker ID.")
            selected_ids.add(asset_id); used_intents.append((role, intent_text)); normalized.append(selected)
        result[group] = normalized
    requested_intents = [(row["role"], row["intent"]) for row in asset_intents]
    if sorted(used_intents) != sorted(requested_intents):
        raise ShotReferenceResolutionError("Every declared asset intent must be resolved exactly once.")
    return result


def build_shot_reference_catalog(*, units: list[dict[str, Any]], assets: list[dict[str, Any]],
                                 voice_bindings: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    """Give shot planning only project-owned, approved references relevant to each shot.

    This is descriptive context, not authority to use an asset: the final shot
    validation path still resolves IDs and enforces role, ownership and route
    policy before any take can be queued.
    """
    bindings = {str(row.get("character_id")): row for row in voice_bindings
        if isinstance(row, dict) and row.get("run_id") == run_id
        and row.get("character_id") and row.get("voice_asset_id")}
    catalog: list[dict[str, Any]] = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        raw_character_ids = unit.get("character_ids")
        character_ids = list(dict.fromkeys(str(value) for value in raw_character_ids
            if isinstance(value, str) and value)) if isinstance(raw_character_ids, list) else []
        world_id = str(unit.get("world_id") or "")
        images: list[dict[str, Any]] = []
        videos: list[dict[str, Any]] = []
        voice_refs: list[dict[str, Any]] = []
        for asset in assets:
            if not isinstance(asset, dict) or not asset.get("asset_id"):
                continue
            raw_roles = asset.get("roles")
            roles = set(value for value in raw_roles if isinstance(value, str)) if isinstance(raw_roles, list) else set()
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            if metadata.get("approval_status", "accepted") != "accepted":
                continue
            image_job = metadata.get("production_image_job") if isinstance(metadata.get("production_image_job"), dict) else {}
            if "image_candidate" in roles and image_job.get("accepted") is not True:
                continue
            if asset.get("source") == "project_output" and asset.get("kind") == "image":
                accepted_legacy = (image_job.get("status") == "completed"
                    and image_job.get("accepted") is True
                    and image_job.get("accepted_role") in roles)
                if metadata.get("approval_status") != "accepted" and not accepted_legacy:
                    continue
            base = {"asset_id": str(asset["asset_id"]), "filename": str(asset.get("filename") or ""),
                "sha256": str(asset.get("sha256") or "")}
            character_id = str(metadata.get("character_id") or "")
            asset_world_id = str(metadata.get("world_id") or "")
            if asset.get("kind") == "image":
                role = next((name for name in ("character_master", "world_master") if name in roles), None)
                if role == "character_master" and character_id in character_ids:
                    images.append({**base, "role": role, "entity_id": character_id})
                elif role == "world_master" and world_id and asset_world_id == world_id:
                    images.append({**base, "role": role, "entity_id": asset_world_id})
            elif asset.get("kind") == "video" and "action_reference_video" in roles:
                videos.append({**base, "role": "action_reference_video"})
            elif asset.get("kind") == "audio" and "voice_excerpt" in roles:
                excerpt = metadata.get("production_voice_excerpt") if isinstance(metadata.get("production_voice_excerpt"), dict) else metadata
                excerpt_character = str(excerpt.get("character_id") or "")
                binding = bindings.get(excerpt_character)
                if (excerpt.get("run_id") == run_id and excerpt_character in character_ids and binding
                        and excerpt.get("source_voice_asset_id") == binding["voice_asset_id"]):
                    voice_refs.append({**base, "role": "voice_excerpt", "entity_id": excerpt_character,
                        "speaker_id": str(binding.get("speaker_id") or "")})
        for rows in (images, videos, voice_refs):
            rows.sort(key=lambda row: (row.get("role", ""), row.get("entity_id", ""), row["asset_id"]))
        catalog.append({"shot_id": str(unit.get("unit_id") or ""),
            "scene_id": str(unit.get("scene_id") or ""), "character_ids": character_ids,
            "world_id": world_id or None, "images": images, "videos": videos,
            "voice_references": voice_refs,
            "scope": "approved project assets and this run's bound voice excerpts"})
    return catalog


def _name_key(value: Any) -> str:
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def _is_evidenced_name(name: str, text: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, flags=re.IGNORECASE))


def _is_evidenced_location(name: str, text: str, *, character_names: list[str] | None = None) -> bool:
    """Require an exact place phrase in a locative, not a nearby person phrase."""
    if not isinstance(name, str) or not name.strip() or not isinstance(text, str):
        return False
    # A place candidate ending in a known scene character is commonly a role
    # label ("lighthouse keeper Arun") rather than a setting. Place phrases
    # such as "Arun's cafe" remain eligible because their head is the place.
    for character_name in character_names or []:
        if isinstance(character_name, str) and character_name.strip() and re.search(
                rf"(?<!\w){re.escape(character_name.strip())}(?!\w)\s*[.!?,;:]*$",
                name, flags=re.IGNORECASE):
            return False

    locative = r"(?:in|at|inside|outside|near|beside|on|by|under|beneath|within|into|onto|from|for|to)"
    modifiers = r"(?:[\w’'-]+\s+){0,3}"
    person_role = (r"(?:manager|keeper|master|owner|guard|worker|clerk|attendant|officer|"
                   r"captain|director|doctor|nurse|teacher|guide|driver|porter|vendor|"
                   r"waiter|waitress|host|hostess|server|employee|resident|servant)\b")
    pattern = rf"(?<!\w){locative}\s+{modifiers}{re.escape(name)}(?!\w)"
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        if re.match(rf"\s+{person_role}", text[match.end():], flags=re.IGNORECASE):
            continue
        return True
    return False


def reconcile_outline_identities(storage_projects_root, project_id: str, *, story_revision_id: str,
                                 expanded_story: str, source_chunks: list[dict[str, Any]],
                                 units: list[dict[str, Any]],
                                 max_revision_retries: int = 3) -> dict[str, Any]:
    """Resolve accepted outline names to stable project canon IDs, idempotently.

    New identities are created only for names present in the accepted story text;
    existing IDs and descriptions are preserved. Evidence links each new record
    to the accepted story revision, scene and source chunks.
    """
    if not isinstance(expanded_story, str) or not expanded_story.strip():
        raise SceneOutlineError("Accepted story text is required to resolve outline identities.")
    if not isinstance(units, list) or not units:
        raise SceneOutlineError("A non-empty accepted scene outline is required to resolve identities.")
    if not isinstance(source_chunks, list) or not source_chunks:
        raise SceneOutlineError("Accepted source chunks are required to resolve identity evidence.")
    if not re.fullmatch(r"story-canon-[a-f0-9]{12}", story_revision_id):
        raise SceneOutlineError("Identity evidence must reference a valid accepted story revision ID.")
    if not isinstance(max_revision_retries, int) or max_revision_retries < 1 or max_revision_retries > 5:
        raise SceneOutlineError("Canon conflict retry limit must be between one and five.")
    chunk_text_by_id: dict[str, str] = {}
    for chunk in source_chunks:
        if not isinstance(chunk, dict):
            raise SceneOutlineError("Accepted source chunks contain an invalid record.")
        chunk_id = chunk.get("chunk_id")
        chunk_text = chunk.get("expanded_text")
        if (not isinstance(chunk_id, str) or not chunk_id.strip()
                or not isinstance(chunk_text, str) or not chunk_text.strip()
                or chunk_id in chunk_text_by_id):
            raise SceneOutlineError("Accepted source chunks need unique IDs and non-empty expanded text.")
        chunk_text_by_id[chunk_id] = chunk_text

    def evidence_chunks(name: str) -> list[str]:
        return [chunk_id for chunk_id, chunk_text in chunk_text_by_id.items()
                if _is_evidenced_name(name, chunk_text)]

    for attempt in range(max_revision_retries):
        current = read_project_canon(storage_projects_root, project_id)
        characters = [dict(row) for row in current["characters"]]
        worlds = [dict(row) for row in current["worlds"]]
        character_ids: dict[str, str] = {}
        world_ids: dict[str, str] = {}
        changed = False

        for unit in units:
            scene = unit.get("scene_outline") if isinstance(unit, dict) else None
            if not isinstance(scene, dict):
                raise SceneOutlineError("Each outline unit must include scene_outline metadata.")
            scene_id = str(unit.get("unit_id") or "")
            chunk_ids = unit.get("source_chunk_ids")
            shots = unit.get("shot_units")
            if not scene_id or not isinstance(chunk_ids, list) or any(not isinstance(x, str) for x in chunk_ids):
                raise SceneOutlineError("Outline identity evidence requires a scene ID and source chunk IDs.")
            if not isinstance(shots, list) or any(not isinstance(shot, dict) for shot in shots):
                raise SceneOutlineError(f"Scene {scene_id} must include a valid shot-unit list.")

            raw_names = scene.get("characters")
            if not isinstance(raw_names, list):
                raise SceneOutlineError(f"Scene {scene_id} characters must be a list of names.")
            scene_character_ids: list[str] = []
            for raw_name in raw_names:
                name = raw_name.strip() if isinstance(raw_name, str) else ""
                key = _name_key(name)
                if not key or len(name) > 120 or not _is_evidenced_name(name, expanded_story):
                    raise SceneOutlineError(
                        f"Scene {scene_id} character {name or '<empty>'!r} is not evidenced in the accepted story text.")
                character_matches = [row for row in characters if row.get("status") == "active" and
                    key in {_name_key(row.get("display_name")), *(_name_key(alias) for alias in row.get("aliases", []))}]
                if len(character_matches) > 1:
                    raise SceneOutlineError(f"Scene {scene_id} character {name!r} matches multiple active canon identities.")
                match = character_matches[0] if character_matches else None
                if match is None:
                    archived_matches = [row for row in characters if key == _name_key(row.get("display_name")) or
                        key in {_name_key(alias) for alias in row.get("aliases", [])}]
                    if len(archived_matches) > 1:
                        raise SceneOutlineError(f"Scene {scene_id} character {name!r} matches multiple archived canon identities.")
                    if archived_matches:
                        raise SceneOutlineError(f"Scene {scene_id} refers to archived character {name!r}; resolve canon explicitly.")
                    matched_chunk_ids = evidence_chunks(name)
                    if not matched_chunk_ids:
                        raise SceneOutlineError(f"Character {name!r} has no source-chunk evidence in the accepted story.")
                    match = create_anonymous_character(name)
                    match["evidence"] = [{"kind": "accepted_story_character_name",
                        "source_story_revision": story_revision_id, "scene_id": scene_id,
                        "scene_context_chunk_ids": list(chunk_ids),
                        "matched_chunk_ids": matched_chunk_ids, "matched_text": name}]
                    characters.append(match)
                    changed = True
                character_ids[key] = str(match["character_id"])
                if str(match["character_id"]) not in scene_character_ids:
                    scene_character_ids.append(str(match["character_id"]))

            location = scene.get("location")
            location_name = location.strip() if isinstance(location, str) else ""
            scene_character_names = [raw.strip() for raw in raw_names
                if isinstance(raw, str) and raw.strip()]
            if (not location_name or len(location_name) > 120
                    or not _is_evidenced_location(location_name, expanded_story,
                        character_names=scene_character_names)):
                raise SceneOutlineError(
                    f"Scene {scene_id} location {location_name or '<empty>'!r} is not evidenced as a place in the accepted story text. "
                    "Use an exact place phrase in an explicit locative construction; a character or occupation is not a setting.")
            location_key = _name_key(location_name)
            world_matches = [row for row in worlds if row.get("status") == "active" and
                (location_key == _name_key(row.get("display_name")) or
                 location_key in {_name_key(place) for place in row.get("locations", [])})]
            if len(world_matches) > 1:
                raise SceneOutlineError(f"Scene {scene_id} location {location_name!r} matches multiple active canon worlds.")
            world = world_matches[0] if world_matches else None
            if world is None:
                archived_worlds = [row for row in worlds if location_key == _name_key(row.get("display_name")) or
                    location_key in {_name_key(place) for place in row.get("locations", [])}]
                if len(archived_worlds) > 1:
                    raise SceneOutlineError(f"Scene {scene_id} location {location_name!r} matches multiple archived canon worlds.")
                if archived_worlds:
                    raise SceneOutlineError(f"Scene {scene_id} refers to an archived world/location {location_name!r}; resolve canon explicitly.")
                matched_chunk_ids = [chunk_id for chunk_id, chunk_text in chunk_text_by_id.items()
                    if _is_evidenced_location(location_name, chunk_text,
                        character_names=scene_character_names)]
                if not matched_chunk_ids:
                    raise SceneOutlineError(
                        f"Location {location_name!r} has no source-chunk evidence as a place in the accepted story. "
                        "Use an exact place phrase in an explicit locative construction; a character or occupation is not a setting.")
                world = create_world(location_name)
                world["evidence"] = [{"kind": "accepted_story_location",
                    "source_story_revision": story_revision_id, "scene_id": scene_id,
                    "scene_context_chunk_ids": list(chunk_ids),
                    "matched_chunk_ids": matched_chunk_ids, "matched_text": location_name}]
                worlds.append(world)
                changed = True
            world_ids[location_key] = str(world["world_id"])
            unit["character_ids"] = scene_character_ids
            unit["world_id"] = str(world["world_id"])
            unit["shot_units"] = [dict(shot, character_ids=scene_character_ids,
                world_id=str(world["world_id"])) for shot in shots]

        if not changed:
            return {"canon_revision": current["revision"], "characters": character_ids,
                    "worlds": world_ids, "reused": True}
        try:
            saved = save_project_canon(storage_projects_root, project_id,
                expected_revision=current["revision"], characters=characters, worlds=worlds,
                source_story_revision=story_revision_id, actor="production_v2_director")
            return {"canon_revision": saved["revision"], "characters": character_ids,
                    "worlds": world_ids, "reused": False}
        except WorldStateError as exc:
            if exc.code != "canon_revision_conflict" or attempt + 1 == max_revision_retries:
                raise SceneOutlineError(f"Could not safely persist outline identities: {exc}") from exc

    raise SceneOutlineError("Project canon kept changing; scene identity reconciliation was not committed.")


def plan_scene_outline(*, canon: dict[str, Any], provider: str,
                       generator: Callable[..., dict[str, Any]] | None = None,
                       max_scenes: int = 80, retry_note: str = "") -> list[dict[str, Any]]:
    """Create narrative scenes and shot units without equating scenes to text chunks."""
    chunks = canon.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise SceneOutlineError("Accepted story canon has no source chunks to map.")
    chunk_ids = [row.get("chunk_id") for row in chunks if isinstance(row, dict)]
    if len(chunk_ids) != len(chunks) or any(not isinstance(value, str) or not value for value in chunk_ids):
        raise SceneOutlineError("Accepted story canon contains invalid source chunk IDs.")
    expanded_story = canon.get("expanded_story")
    if not isinstance(expanded_story, str) or not expanded_story.strip() or len(expanded_story) > 100_000:
        raise SceneOutlineError("Expanded story must contain 1–100,000 characters for scene planning.")
    prompt = f"""You are the narrative Director. Plan an ordered scene outline from the accepted story.
Make scenes from dramatic action, location/time continuity and meaningful transitions; source chunks
are text windows, not scenes. Do not create one scene per source chunk by default. A scene can cite
several source chunks and a chunk can support multiple scenes. Preserve all explicit facts and event
order. Group consecutive beats into one scene while they remain the same continuous encounter at the
same place and time; create a new scene for a real story transition, not merely because the next beat
has a different purpose. In particular, keep one continuous conversation in one scene and use separate
shots for its successive beats. Do not assign the same dramatic event to multiple scenes: later scenes
may carry its established result forward, but must not replay it as a new action. Cover every source
chunk at least once. Use 1–4 planned shots per scene, each with a distinct
visual action or camera purpose. Do not write final render prompts or invent asset IDs.
For each scene location, return only the place noun phrase, without its locative preposition
(for example, return "the lighthouse", not "beside the lighthouse"; return "her empty cafe", not
"in her empty cafe"). The place phrase must appear verbatim in an explicit locative construction in
the accepted story text. Verbatim presence alone is insufficient: a character or occupation phrase is not a setting;
"lighthouse keeper Arun" describes a person and must never be used as a location. Do not invent a
place name or turn a character's possessive into a named location. If the story does not establish a
scene setting, keep the established place only when the story supports that continuity; otherwise
return the actual explicit setting phrase from the scene event without adding detail. A prop or destination
mentioned within a setting is not itself the scene location: for example, a cabinet located in a cafe does
not make the scene location "the cabinet". Choose the established room, building, or outdoor place where
the characters are physically present. If the text does not establish that place for a scene, use the
nearest explicit setting supported by the event and preserve the location already established for an
ongoing encounter; do not promote an object, landmark clue, or destination mentioned in dialogue into a setting.
For the characters array, use only exact person names explicitly present in the accepted story text.
Do not put role descriptions, occupations, pronouns, or generic people (such as "the lighthouse keeper")
in this identity list. Mention an unnamed person only in the scene summary or shot action; do not create
a canon character for an unnamed role.
Return JSON only in this shape:
{{"scenes":[{{"title":"...","summary":"...","location":"...","time":"...",
"characters":["..."],"dramatic_turn":"...","source_chunk_ids":["story_chunk_0001"],
"shots":[{{"purpose":"...","action":"..."}}]}}]}}
Return between 1 and {max_scenes} scenes. Keep scene and shot order faithful to the story.
{f"Correct this validation issue from the previous bounded attempt: {retry_note}" if retry_note else ""}

Accepted story revision: {canon.get('revision_id')}
Story goal: {canon.get('story_goal', '')}
Continuity rules: {canon.get('continuity_rules', [])}
Source chunk index: {[(row.get('chunk_id'), row.get('continuity_summary', '')) for row in chunks]}
Expanded story:
{expanded_story}""".strip()
    call = generator or generate_json
    try:
        response = call(prompt=prompt, temperature=0.2, provider=provider)
    except ReasoningProviderError:
        raise
    if not isinstance(response, dict) or not isinstance(response.get("scenes"), list):
        raise SceneOutlineError("Scene planner must return a JSON object with a scenes array.")
    scenes = response["scenes"]
    if not scenes or len(scenes) > max_scenes:
        raise SceneOutlineError(f"Scene planner must return between 1 and {max_scenes} scenes.")
    known_chunks = set(chunk_ids)
    covered_chunks: set[str] = set()
    units: list[dict[str, Any]] = []
    shot_count = 0
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise SceneOutlineError(f"Scene {index} must be an object.")
        for field in ("title", "summary", "location", "time", "dramatic_turn"):
            if not isinstance(scene.get(field), str) or not scene[field].strip():
                raise SceneOutlineError(f"Scene {index} needs a non-empty {field}.")
        characters, sources, shots = scene.get("characters"), scene.get("source_chunk_ids"), scene.get("shots")
        if not isinstance(characters, list) or any(not isinstance(x, str) or not x.strip() for x in characters):
            raise SceneOutlineError(f"Scene {index} characters must be a list of names.")
        if not isinstance(sources, list) or not sources or any(not isinstance(value, str) or value not in known_chunks for value in sources):
            raise SceneOutlineError(f"Scene {index} must cite known source chunk IDs.")
        if len(set(sources)) != len(sources):
            raise SceneOutlineError(f"Scene {index} repeats a source chunk ID.")
        if not isinstance(shots, list) or not 1 <= len(shots) <= 4:
            raise SceneOutlineError(f"Scene {index} must plan 1–4 shot beats.")
        scene_id = f"scene-{index:03d}"
        shot_units = []
        for shot_index, shot in enumerate(shots, 1):
            if not isinstance(shot, dict) or any(not isinstance(shot.get(key), str) or not shot[key].strip()
                                                  for key in ("purpose", "action")):
                raise SceneOutlineError(f"Scene {index} shot {shot_index} needs purpose and action.")
            shot_count += 1
            shot_units.append({"unit_id": f"shot-{index:03d}-{shot_index:02d}",
                "scene_id": scene_id, "shot_index": shot_index,
                "source_chunk_ids": list(sources), "shot_outline": dict(shot)})
        covered_chunks.update(sources)
        units.append({"unit_id": scene_id, "scene_index": index,
            "source_chunk_ids": list(sources), "scene_outline": {key: scene[key] for key in
                ("title", "summary", "location", "time", "characters", "dramatic_turn")},
            "shot_units": shot_units})
    missing = sorted(known_chunks - covered_chunks)
    if missing:
        raise SceneOutlineError(f"Scene outline does not cover all accepted source chunks: {missing[:12]}.")
    if shot_count > max_scenes * 4:
        raise SceneOutlineError("Scene outline exceeds the bounded shot count.")
    return units
