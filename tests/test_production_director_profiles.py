from __future__ import annotations

import json

import pytest

from story_builder.services.chunked_generation import generate_story_canon
from story_builder.services.production_director_profiles import (
    DirectorProfileError,
    load_registry,
    resolve_profile,
)


def test_six_profiles_are_versioned_distinct_and_hashable():
    registry = load_registry()
    expected = {"story_film", "social_profile", "corporate_pitch", "informative", "news_report", "advertisement"}
    assert set(registry["profiles"]) == expected
    assert len(registry["content_hash"]) == 64
    assert len({tuple(item["behavior"]) for item in registry["profiles"].values()}) == 6
    assert resolve_profile("news_report")["profile_version"] == registry["version"]
    assert "Do not dramatize" in " ".join(resolve_profile("news_report")["behavior"])


def test_unknown_profile_fails_with_valid_choices():
    with pytest.raises(DirectorProfileError, match="Unknown production type"):
        resolve_profile("unsupported")


def test_malformed_profile_registry_fails_closed(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"version": "v1", "profiles": {"bad": {"purpose": "missing fields"}}}))
    with pytest.raises(DirectorProfileError, match="missing valid fields"):
        load_registry(path)


def test_production_type_profile_is_given_to_story_generation_as_guidance():
    prompts = []
    profile = {"production_type": "advertisement", "purpose": "Supported product story.",
               "behavior": ["Never invent product claims."], "review_priorities": ["claim substantiation"]}

    def generator(*, prompt, **_kwargs):
        prompts.append(prompt)
        marker = "Exact source text as a JSON string (decode it; preserve every character):\n"
        source = json.loads(prompt.split(marker, 1)[1].split("\n\n", 1)[0])
        return {"chunk_id": "story_chunk_0001", "source_excerpt": source,
                "source_facts": [{"quote": "The", "start": 0, "end": 3, "category": "other"}],
                "expanded_text": "The product solves the supplied problem.", "inferred_details": [],
                "continuity_summary": "", "story_goal": "Explain the product.", "tone": [],
                "continuity_rules": [], "visual_style_notes": []}

    generate_story_canon(title="Demo", source_text="The product solves a problem.",
                         director_profile=profile, generator=generator)
    assert len(prompts) == 1
    assert "Active production-type Director profile" in prompts[0]
    assert "Never invent product claims" in prompts[0]
