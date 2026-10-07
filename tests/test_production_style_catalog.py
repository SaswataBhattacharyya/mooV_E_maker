from __future__ import annotations

from story_builder.services.production_style_catalog import catalog


def test_nested_catalog_keeps_six_legacy_bases_and_distinct_director_profiles():
    result = catalog()
    assert result["catalog_version"] == "production_style_tree_v1"
    assert len(result["director_profiles_hash"]) == 64
    bases = {row["production_type"]: row for row in result["production_types"]}
    assert set(bases) == {"story_film", "social_profile", "corporate_pitch", "informative", "news_report", "advertisement"}
    for style_id, row in bases.items():
        assert row["base_narrative_style"]["style_id"] == style_id
        assert row["variants"] == []
        assert row["director_profile"]["behavior"]


def test_nested_catalog_api_does_not_replace_legacy_flat_style_route():
    from story_builder.api import main as api

    catalog_route = asyncio_run(api.production_v2_styles())
    legacy_route = asyncio_run(api.automation_styles())
    assert len(catalog_route["production_types"]) == 6
    assert {row["style_id"] for row in legacy_route} == {
        "story_film", "social_profile", "corporate_pitch", "informative", "news_report", "advertisement"
    }


def asyncio_run(awaitable):
    import asyncio

    return asyncio.run(awaitable)
