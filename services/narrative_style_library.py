"""Validated, revisioned narrative style drafts and immutable published versions."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from story_builder.services import prompt_styles
from story_builder.services.narrative_style_sources import StyleSourceError, _source_paths, list_style_sources
from story_builder.services.reasoning_provider import ReasoningProviderError, generate_json


STAGES = ("story", "scene_direction", "image", "audio", "video", "review")
OVERRIDE_FIELDS = {"tone", "pacing", "point_of_view", "dialogue", "structure", "constraints"}


class StyleLibraryError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


def _root(path: Path) -> Path:
    root = Path(path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_variant_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"variant-[a-f0-9]{16}", value):
        raise StyleLibraryError("invalid_style_variant_id", "Style variant ID must be a canonical generated variant ID.")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".style-library-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _validate_evidence(library_root: Path, evidence: Any, source_ids: list[str]) -> list[dict[str, Any]]:
    if not isinstance(evidence, list):
        raise StyleLibraryError("invalid_style_evidence", "Evidence must be a list of cited evidence cards.")
    verified: list[dict[str, Any]] = []
    for index, card in enumerate(evidence):
        if not isinstance(card, Mapping):
            raise StyleLibraryError("invalid_style_evidence", f"Evidence card {index + 1} must be an object.")
        source_id, locator = card.get("source_id"), card.get("locator")
        quote, statement = card.get("quote"), card.get("statement")
        kind, confidence = card.get("kind", "explicit"), card.get("confidence", 1.0)
        if not isinstance(statement, str) or not statement.strip() or len(statement) > 1000:
            raise StyleLibraryError("invalid_style_evidence", f"Evidence card {index + 1} must contain a non-empty statement.")
        if kind not in {"explicit", "inferred", "user_authored"}:
            raise StyleLibraryError("invalid_style_evidence", f"Evidence card {index + 1} has an unsupported kind.")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            raise StyleLibraryError("invalid_style_evidence", f"Evidence card {index + 1} confidence must be between 0 and 1.")
        if kind == "user_authored":
            source_id = source_id if source_id is None else source_id
            locator = "user-authored" if not locator else locator
            if source_id is not None or locator != "user-authored":
                raise StyleLibraryError("invalid_style_evidence", f"User-authored evidence card {index + 1} must not claim a document citation.")
        else:
            if source_id not in source_ids or not isinstance(locator, str):
                raise StyleLibraryError("invalid_style_evidence", f"Evidence card {index + 1} must cite one of the selected sources and contain a locator.")
            if not isinstance(quote, str) or not quote.strip() or len(quote) > 280:
                raise StyleLibraryError("invalid_style_evidence", f"Evidence card {index + 1} requires a source quote of at most 280 characters.")
            try:
                source_path, metadata_path = _source_paths(library_root, str(source_id))
                source = json.loads(metadata_path.read_text(encoding="utf-8"))
                if not source_path.is_file() or not any(
                    row.get("locator") == locator and quote in row.get("text", "")
                    for row in source.get("evidence_blocks", []) if isinstance(row, dict)
                ):
                    raise StyleLibraryError("style_evidence_not_found", f"Evidence quote/locator for card {index + 1} does not match the stored source.")
            except (OSError, json.JSONDecodeError, StyleSourceError) as exc:
                if isinstance(exc, StyleLibraryError):
                    raise
                raise StyleLibraryError("style_source_unavailable", f"Could not verify evidence source {source_id}: {exc}") from exc
        verified.append({"source_id": source_id, "locator": locator, "statement": statement.strip(),
                         "quote": quote.strip() if isinstance(quote, str) else "",
                         "kind": kind, "confidence": float(confidence)})
    return verified


def _normalize_payload(library_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    base_style_id = payload.get("base_style_id")
    try:
        base = prompt_styles.get_style(str(base_style_id))
    except KeyError as exc:
        raise StyleLibraryError("unknown_base_style", f"Unknown base style {base_style_id!r}.") from exc
    display_name = payload.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip() or len(display_name.strip()) > 100:
        raise StyleLibraryError("invalid_style_name", "Style variant display_name must be 1–100 characters.")
    source_ids = payload.get("source_ids", [])
    if not isinstance(source_ids, list) or any(not isinstance(item, str) for item in source_ids) or len(set(source_ids)) != len(source_ids):
        raise StyleLibraryError("invalid_style_sources", "source_ids must be a unique list of stored style source IDs.")
    known_sources = {row["source_id"] for row in list_style_sources(library_root)}
    if not set(source_ids) <= known_sources:
        raise StyleLibraryError("style_source_not_found", "A selected source is missing or failed integrity validation.")
    rules = payload.get("rules_by_stage")
    if not isinstance(rules, Mapping) or set(rules) != set(STAGES):
        raise StyleLibraryError("invalid_style_rules", f"rules_by_stage must contain exactly: {', '.join(STAGES)}.")
    normalized_rules: dict[str, list[str]] = {}
    for stage in STAGES:
        items = rules[stage]
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, list) or not items or any(not isinstance(item, str) or not item.strip() for item in items):
            raise StyleLibraryError("invalid_style_rules", f"rules_by_stage.{stage} must be a non-empty string or list of strings.")
        normalized_rules[stage] = [item.strip() for item in items]
    overrides = payload.get("director_behavior_overrides", {})
    if not isinstance(overrides, Mapping) or not set(overrides) <= OVERRIDE_FIELDS:
        raise StyleLibraryError("invalid_style_overrides", f"Director overrides may use only: {', '.join(sorted(OVERRIDE_FIELDS))}.")
    if any(not isinstance(value, (str, list)) or
           (isinstance(value, str) and (not value.strip() or len(value) > 1000)) or
           (isinstance(value, list) and (not value or any(not isinstance(item, str) or not item.strip() or len(item) > 1000 for item in value)))
           for value in overrides.values()):
        raise StyleLibraryError("invalid_style_overrides", "Director override values must be bounded non-empty text or lists of bounded non-empty text.")
    evidence = _validate_evidence(library_root, payload.get("evidence", []), source_ids)
    if source_ids and not any(item["kind"] != "user_authored" for item in evidence):
        raise StyleLibraryError("style_evidence_required", "A sourced style draft needs at least one verified evidence card.")
    negative = payload.get("negative_constraints", [])
    if not isinstance(negative, list) or any(not isinstance(item, str) or not item.strip() for item in negative):
        raise StyleLibraryError("invalid_style_constraints", "negative_constraints must be a list of non-empty strings.")
    example = payload.get("example_brief", "")
    if not isinstance(example, str) or len(example) > 6000:
        raise StyleLibraryError("invalid_style_example", "example_brief must be text of at most 6000 characters.")
    normalized = {"base_style_id": base["style_id"], "base_style_version": base["version"],
            "display_name": display_name.strip(), "source_ids": list(source_ids),
            "rules_by_stage": normalized_rules, "director_behavior_overrides": dict(overrides),
            "evidence": evidence, "negative_constraints": [item.strip() for item in negative],
            "example_brief": example.strip()}
    if len(json.dumps(normalized, ensure_ascii=False)) > 24000:
        raise StyleLibraryError("style_draft_too_large", "Style draft exceeds the 24,000-character data limit.")
    return normalized


def analyze_style_sources(root: Path, *, base_style_id: str, source_ids: list[str],
                          provider: str | None = None, generator=None) -> dict[str, Any]:
    """Use the configured text provider to propose a cited style draft, never publish it."""
    library_root = Path(root).resolve()
    if not isinstance(source_ids, list) or not source_ids or len(source_ids) > 5 or any(not isinstance(item, str) for item in source_ids):
        raise StyleLibraryError("invalid_style_sources", "Select between one and five stored style sources for analysis.")
    if len(set(source_ids)) != len(source_ids):
        raise StyleLibraryError("invalid_style_sources", "Duplicate style source IDs are not allowed.")
    corpus_sources: list[dict[str, Any]] = []
    char_count = 0
    for source_id in source_ids:
        try:
            raw_path, metadata_path = _source_paths(library_root, source_id)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            raw = raw_path.read_bytes()
        except (OSError, json.JSONDecodeError, StyleSourceError) as exc:
            raise StyleLibraryError("style_source_not_found", f"Style source {source_id} is unavailable: {exc}") from exc
        if hashlib.sha256(raw).hexdigest() != metadata.get("sha256"):
            raise StyleLibraryError("style_source_hash_conflict", f"Style source {source_id} failed integrity validation.")
        blocks = metadata.get("evidence_blocks", [])
        if not isinstance(blocks, list):
            raise StyleLibraryError("style_source_corrupt", f"Style source {source_id} has invalid extracted-text metadata.")
        char_count += sum(len(str(row.get("text", ""))) for row in blocks if isinstance(row, dict))
        if char_count > 30000:
            raise StyleLibraryError("style_analysis_input_too_large", "Selected source text exceeds 30,000 characters; analyze fewer or shorter references at a time.")
        corpus_sources.append({"source_id": source_id, "filename": metadata.get("filename"),
                               "blocks": blocks})
    try:
        base = prompt_styles.get_style(base_style_id)
    except KeyError as exc:
        raise StyleLibraryError("unknown_base_style", f"Unknown base style {base_style_id!r}.") from exc
    prompt = f"""You are drafting reusable narrative style guidance, not adapting the source's story.
Analyze only the supplied text extracts. Never reuse their plot, named characters, dialogue, or distinctive long wording.
Return JSON only with this schema:
{{"display_name":"short style name","rules_by_stage":{{"story":["..."],"scene_direction":["..."],"image":["..."],"audio":["..."],"video":["..."],"review":["..."]}},"director_behavior_overrides":{{}},"negative_constraints":["..."],"example_brief":"a new generic example with no source plot or character names","evidence":[{{"source_id":"exact ID","locator":"exact locator","quote":"verbatim excerpt under 280 chars","statement":"short paraphrase of the rule","kind":"explicit|inferred","confidence":0.0}}]}}.
Every evidence quote must be an exact short substring of its cited locator. Mark inferred recommendations as inferred. Prefer a small number of reusable principles, not a summary of the document. Do not make factual claims unsupported by the extract.

Base production type: {base_style_id} ({base.get('name')})
Existing base guidance (preserve its purpose; propose refinements only):
{json.dumps(base['stages'], ensure_ascii=False)}
Extracts:
{json.dumps(corpus_sources, ensure_ascii=False)}""".strip()
    call = generator or generate_json
    result = call(prompt=prompt, temperature=0.2, provider=provider)
    if not isinstance(result, dict):
        raise StyleLibraryError("style_analysis_invalid", "Style analysis provider must return a JSON object.")
    candidate = {"base_style_id": base_style_id, "source_ids": source_ids, **result}
    normalized = _normalize_payload(library_root, candidate)
    if not normalized["evidence"]:
        raise StyleLibraryError("style_analysis_uncited", "Style analysis returned no verifiable evidence cards.")
    return {"status": "draft_proposal", "persisted": False, "published": False,
            "provider": provider, "payload": normalized,
            "evidence_hash": hashlib.sha256(json.dumps(normalized["evidence"], ensure_ascii=False,
                sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()}


def create_draft(root: Path, payload: Mapping[str, Any], *, variant_id: str | None = None,
                 version: int = 1, parent_version: int | None = None) -> dict[str, Any]:
    library_root = _root(root)
    normalized = _normalize_payload(library_root, payload)
    variant_id = _safe_variant_id(variant_id) if variant_id else f"variant-{uuid.uuid4().hex[:16]}"
    if not isinstance(version, int) or version < 1:
        raise StyleLibraryError("invalid_style_version", "Style version must be a positive integer.")
    draft = {"schema_version": 1, "variant_id": variant_id, "version": version,
             "draft_revision": 1, "status": "draft", **normalized,
             "parent_version": parent_version,
             "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
    draft_path = library_root / "drafts" / f"{variant_id}.json"
    if draft_path.exists():
        raise StyleLibraryError("style_draft_exists", "This style variant already has an unpublished draft.")
    _atomic_json(draft_path, draft)
    return draft


def fork_published(root: Path, variant_id: str, *, version: int = 1) -> dict[str, Any]:
    """Create a new editable draft from an immutable published version."""
    library_root = _root(root)
    published = load_published(library_root, variant_id, version)
    if published is None:
        raise StyleLibraryError("style_version_not_found", "Published style version was not found.")
    latest = max((int(row.get("version", 0)) for row in list_variants(library_root, include_archived=True)
                 if row.get("variant_id") == variant_id), default=version)
    payload = {key: published[key] for key in ("base_style_id", "display_name", "source_ids", "rules_by_stage",
              "director_behavior_overrides", "evidence", "negative_constraints", "example_brief")}
    return create_draft(library_root, payload, variant_id=variant_id, version=latest + 1, parent_version=version)


def save_draft(root: Path, variant_id: str, *, expected_revision: int,
               payload: Mapping[str, Any]) -> dict[str, Any]:
    library_root = _root(root)
    variant_id = _safe_variant_id(variant_id)
    path = library_root / "drafts" / f"{variant_id}.json"
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StyleLibraryError("style_draft_not_found", "Style draft was not found.") from exc
    except json.JSONDecodeError as exc:
        raise StyleLibraryError("style_draft_corrupt", f"Style draft JSON is invalid: {exc}") from exc
    if current.get("status") != "draft":
        raise StyleLibraryError("style_draft_immutable", "Only an unpublished draft can be edited.")
    if expected_revision != current.get("draft_revision"):
        raise StyleLibraryError("style_draft_stale", "Style draft changed since it was loaded; refresh before saving.")
    normalized = _normalize_payload(library_root, payload)
    updated = {**current, **normalized, "draft_revision": expected_revision + 1,
               "updated_at": datetime.now(timezone.utc).isoformat()}
    _atomic_json(path, updated)
    return updated


def publish_draft(root: Path, variant_id: str, *, expected_revision: int) -> dict[str, Any]:
    library_root = _root(root)
    variant_id = _safe_variant_id(variant_id)
    draft_path = library_root / "drafts" / f"{variant_id}.json"
    try:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StyleLibraryError("style_draft_not_found", "Style draft was not found.") from exc
    if draft.get("status") != "draft":
        raise StyleLibraryError("style_draft_immutable", "Only a draft can be published.")
    if expected_revision != draft.get("draft_revision"):
        raise StyleLibraryError("style_draft_stale", "Style draft changed since it was loaded; refresh before publishing.")
    published = {**draft, "status": "published", "published_at": datetime.now(timezone.utc).isoformat()}
    published["content_hash"] = hashlib.sha256(json.dumps(published, sort_keys=True, ensure_ascii=False,
                                                           separators=(",", ":")).encode("utf-8")).hexdigest()
    version_path = library_root / "variants" / variant_id / "versions" / f"v{draft['version']}.json"
    if version_path.exists():
        existing = load_published(library_root, variant_id, draft["version"])
        if not existing or existing.get("content_hash") != published.get("content_hash"):
            raise StyleLibraryError("style_version_conflict", "Published style version already exists; published versions are immutable.")
        published = existing
    else:
        _atomic_json(version_path, published)
    index_path = library_root / "variants" / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"variants": {}}
    except json.JSONDecodeError as exc:
        raise StyleLibraryError("style_index_corrupt", f"Style variant index is invalid: {exc}") from exc
    index.setdefault("variants", {})[variant_id] = {"variant_id": variant_id, "version": draft["version"],
        "base_style_id": published["base_style_id"], "display_name": published["display_name"],
        "status": "published", "content_hash": published["content_hash"]}
    _atomic_json(index_path, index)
    draft_path.unlink()
    return published


def list_variants(root: Path, *, include_archived: bool = False) -> list[dict[str, Any]]:
    library_root = Path(root).resolve()
    index_path = library_root / "variants" / "index.json"
    if not index_path.exists():
        return []
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StyleLibraryError("style_index_corrupt", f"Style variant index is invalid: {exc}") from exc
    rows = list(index.get("variants", {}).values())
    return sorted((row for row in rows if include_archived or row.get("status") != "archived"),
                  key=lambda row: (row.get("base_style_id", ""), row.get("display_name", "").casefold()))


def list_drafts(root: Path) -> list[dict[str, Any]]:
    library_root = Path(root).resolve()
    directory = library_root / "drafts"
    if not directory.is_dir():
        return []
    drafts: list[dict[str, Any]] = []
    for path in sorted(directory.glob("variant-*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("status") == "draft" and value.get("variant_id") == path.stem:
            drafts.append(value)
    return sorted(drafts, key=lambda row: (row.get("base_style_id", ""), row.get("display_name", "").casefold()))


def list_published_versions(root: Path, variant_id: str) -> list[dict[str, Any]]:
    library_root = Path(root).resolve()
    variant_id = _safe_variant_id(variant_id)
    directory = library_root / "variants" / variant_id / "versions"
    if not directory.is_dir():
        return []
    versions: list[dict[str, Any]] = []
    for path in sorted(directory.glob("v*.json"), key=lambda item: int(item.stem[1:]) if item.stem[1:].isdigit() else -1):
        if path.stem[1:].isdigit():
            version = load_published(library_root, variant_id, int(path.stem[1:]))
            if version is not None:
                versions.append(version)
    return versions


def load_published(root: Path, variant_id: str, version: int = 1) -> dict[str, Any] | None:
    variant_id = _safe_variant_id(variant_id)
    if not isinstance(version, int) or version < 1:
        raise StyleLibraryError("invalid_style_version", "Style version must be a positive integer.")
    path = Path(root).resolve() / "variants" / variant_id / "versions" / f"v{version}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if value.get("variant_id") != variant_id or value.get("version") != version or value.get("status") != "published":
        raise StyleLibraryError("style_version_corrupt", "Published style version failed its identity/status validation.")
    expected = value.get("content_hash")
    without_hash = {key: item for key, item in value.items() if key != "content_hash"}
    actual = hashlib.sha256(json.dumps(without_hash, sort_keys=True, ensure_ascii=False,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()
    if expected != actual:
        raise StyleLibraryError("style_version_hash_mismatch", "Published style version hash does not match its content.")
    return value


def resolve_active_variant(root: Path, variant_id: str, version: int | None = None) -> dict[str, Any]:
    """Resolve only a published, non-archived variant and verify its content hash."""
    variant_id = _safe_variant_id(variant_id)
    index_path = Path(root).resolve() / "variants" / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StyleLibraryError("style_variant_not_found", "Published style variant was not found.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise StyleLibraryError("style_index_corrupt", f"Style variant index is invalid: {exc}") from exc
    indexed = index.get("variants", {}).get(variant_id)
    if not indexed:
        raise StyleLibraryError("style_variant_not_found", "Published style variant was not found.")
    if indexed.get("status") == "archived":
        raise StyleLibraryError("style_variant_archived", "Archived style variants cannot be selected for a new production run.")
    selected_version = version or indexed.get("version")
    result = load_published(root, variant_id, int(selected_version))
    if result is None:
        raise StyleLibraryError("style_version_not_found", "Published style version was not found.")
    return result


def archive_variant(root: Path, variant_id: str) -> dict[str, Any]:
    library_root = Path(root).resolve()
    variant_id = _safe_variant_id(variant_id)
    index_path = library_root / "variants" / "index.json"
    if not index_path.is_file():
        raise StyleLibraryError("style_variant_not_found", "Published style variant was not found.")
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StyleLibraryError("style_index_corrupt", f"Style variant index is invalid: {exc}") from exc
    row = index.get("variants", {}).get(variant_id)
    if not row:
        raise StyleLibraryError("style_variant_not_found", "Published style variant was not found.")
    row["status"] = "archived"
    row["archived_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_json(index_path, index)
    return row
