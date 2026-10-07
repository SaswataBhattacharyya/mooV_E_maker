from __future__ import annotations

import json

import pytest

from story_builder.services import narrative_style_library as library
from story_builder.services.narrative_style_sources import store_style_source


def _payload(source_id=None):
    return {
        "base_style_id": "story_film",
        "display_name": "Quiet Suspense",
        "source_ids": [source_id] if source_id else [],
        "rules_by_stage": {stage: [f"Use the quiet-suspense approach for {stage}."] for stage in library.STAGES},
        "director_behavior_overrides": {"pacing": ["Allow silence before reveals."]},
        "evidence": ([{"source_id": source_id, "locator": "line:1-1",
                       "quote": "Use pauses before a reveal.",
                       "statement": "Favor pauses before reveals.", "kind": "explicit", "confidence": 0.98}]
                    if source_id else [{"source_id": None, "locator": "user-authored",
                                        "quote": "", "statement": "User-authored pacing rule.",
                                        "kind": "user_authored", "confidence": 1.0}]),
        "negative_constraints": ["Do not copy the source plot or characters."],
        "example_brief": "A character waits in a dark hallway.",
    }


def test_draft_publish_fork_archive_preserves_immutable_versions(tmp_path):
    root = tmp_path / "styles"
    source = store_style_source(root, "style.txt", b"Use pauses before a reveal.\n")
    draft = library.create_draft(root, _payload(source["source_id"]))
    assert draft["status"] == "draft" and draft["version"] == 1
    assert library.list_drafts(root)[0]["variant_id"] == draft["variant_id"]
    updated = library.save_draft(root, draft["variant_id"], expected_revision=1,
                                 payload={**_payload(source["source_id"]), "display_name": "Quiet Mystery"})
    assert updated["draft_revision"] == 2
    with pytest.raises(library.StyleLibraryError) as stale:
        library.save_draft(root, draft["variant_id"], expected_revision=1, payload=_payload(source["source_id"]))
    assert stale.value.code == "style_draft_stale"

    published_v1 = library.publish_draft(root, draft["variant_id"], expected_revision=2)
    original_bytes = (root / "variants" / draft["variant_id"] / "versions" / "v1.json").read_bytes()
    assert published_v1["status"] == "published"
    assert library.load_published(root, draft["variant_id"], 1)["display_name"] == "Quiet Mystery"
    assert library.list_variants(root)[0]["version"] == 1
    assert [row["version"] for row in library.list_published_versions(root, draft["variant_id"])] == [1]

    next_draft = library.fork_published(root, draft["variant_id"], version=1)
    assert next_draft["version"] == 2 and next_draft["parent_version"] == 1
    library.save_draft(root, draft["variant_id"], expected_revision=1,
                        payload={**_payload(source["source_id"]), "display_name": "Quiet Suspense v2"})
    library.publish_draft(root, draft["variant_id"], expected_revision=2)
    assert library.load_published(root, draft["variant_id"], 2)["display_name"] == "Quiet Suspense v2"
    assert [row["version"] for row in library.list_published_versions(root, draft["variant_id"])] == [1, 2]
    assert (root / "variants" / draft["variant_id"] / "versions" / "v1.json").read_bytes() == original_bytes
    assert library.resolve_active_variant(root, draft["variant_id"])["version"] == 2

    archived = library.archive_variant(root, draft["variant_id"])
    assert archived["status"] == "archived"
    assert library.list_variants(root) == []
    with pytest.raises(library.StyleLibraryError) as inactive:
        library.resolve_active_variant(root, draft["variant_id"])
    assert inactive.value.code == "style_variant_archived"


def test_draft_rejects_forged_citation_and_incomplete_stage_coverage(tmp_path):
    root = tmp_path / "styles"
    source = store_style_source(root, "style.txt", b"Evidence on line one.\n")
    forged = _payload(source["source_id"])
    forged["evidence"][0]["quote"] = "This sentence is not in the source."
    with pytest.raises(library.StyleLibraryError) as error:
        library.create_draft(root, forged)
    assert error.value.code == "style_evidence_not_found"

    incomplete = _payload()
    incomplete["rules_by_stage"].pop("review")
    with pytest.raises(library.StyleLibraryError) as missing:
        library.create_draft(root, incomplete)
    assert missing.value.code == "invalid_style_rules"


def test_user_authored_style_rules_do_not_fabricate_document_citations(tmp_path):
    draft = library.create_draft(tmp_path / "styles", _payload())
    assert draft["evidence"][0]["kind"] == "user_authored"
    assert draft["source_ids"] == []


def test_published_hash_tampering_is_detected(tmp_path):
    root = tmp_path / "styles"
    draft = library.create_draft(root, _payload())
    library.publish_draft(root, draft["variant_id"], expected_revision=1)
    path = root / "variants" / draft["variant_id"] / "versions" / "v1.json"
    value = json.loads(path.read_text())
    value["rules_by_stage"]["story"] = ["tampered"]
    path.write_text(json.dumps(value))
    with pytest.raises(library.StyleLibraryError) as error:
        library.load_published(root, draft["variant_id"])
    assert error.value.code == "style_version_hash_mismatch"


def test_source_analysis_returns_only_a_verified_unpublished_proposal(tmp_path):
    root = tmp_path / "styles"
    source = store_style_source(root, "guide.md", b"Use pauses before reveals.\n")

    def generator(*, prompt, **_kwargs):
        assert "Never reuse their plot" in prompt
        return {"display_name": "Quiet Suspense", "rules_by_stage": _payload()["rules_by_stage"],
                "director_behavior_overrides": {"pacing": ["Allow pauses before reveals."]},
                "negative_constraints": ["Do not copy the source plot."],
                "example_brief": "A visitor waits outside a locked door.",
                "evidence": [{"source_id": source["source_id"], "locator": "line:1-1",
                    "quote": "Use pauses before reveals.", "statement": "Use pauses before reveals.",
                    "kind": "explicit", "confidence": 0.94}]}

    result = library.analyze_style_sources(root, base_style_id="story_film",
        source_ids=[source["source_id"]], provider="codex", generator=generator)
    assert result["status"] == "draft_proposal"
    assert result["persisted"] is False and result["published"] is False
    assert result["payload"]["evidence"][0]["quote"] == "Use pauses before reveals."
    assert library.list_variants(root) == []


def test_source_analysis_rejects_fabricated_evidence_quote(tmp_path):
    root = tmp_path / "styles"
    source = store_style_source(root, "guide.md", b"Use pauses before reveals.\n")

    def generator(**_kwargs):
        return {"display_name": "Bad", "rules_by_stage": _payload()["rules_by_stage"],
                "director_behavior_overrides": {}, "negative_constraints": [], "example_brief": "New example.",
                "evidence": [{"source_id": source["source_id"], "locator": "line:1-1",
                    "quote": "Invented passage.", "statement": "A made-up rule.", "kind": "explicit", "confidence": 1.0}]}

    with pytest.raises(library.StyleLibraryError) as error:
        library.analyze_style_sources(root, base_style_id="story_film",
            source_ids=[source["source_id"]], generator=generator)
    assert error.value.code == "style_evidence_not_found"
