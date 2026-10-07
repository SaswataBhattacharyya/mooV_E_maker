"""Additive hierarchical catalog for the new production flow."""
from __future__ import annotations

from typing import Any

from story_builder.services import prompt_styles
from story_builder.services.production_director_profiles import load_registry
from story_builder.services.narrative_style_library import list_variants


def catalog(style_library_root=None) -> dict[str, Any]:
    """Join legacy narrative packs to new Director profiles without mutating either."""
    registry = load_registry()
    legacy = {str(row["style_id"]): row for row in prompt_styles.list_styles()}
    profile_ids = set(registry["profiles"])
    if set(legacy) != profile_ids:
        missing_legacy = sorted(profile_ids - set(legacy))
        missing_profiles = sorted(set(legacy) - profile_ids)
        raise ValueError(f"Production style catalog is inconsistent (missing legacy={missing_legacy}; missing profiles={missing_profiles}).")
    bases = []
    for production_type in sorted(profile_ids):
        profile = registry["profiles"][production_type]
        bases.append({"production_type": production_type,
                      "display_name": profile["display_name"],
                      "director_profile_version": registry["version"],
                      "director_profile_hash": registry["content_hash"],
                      "director_profile": profile,
                      "base_narrative_style": legacy[production_type],
                      "variants": []})
    if style_library_root is not None:
        by_id = {row["production_type"]: row for row in bases}
        for variant in list_variants(style_library_root):
            if variant.get("base_style_id") in by_id:
                by_id[variant["base_style_id"]]["variants"].append(variant)
    return {"catalog_version": "production_style_tree_v1",
            "director_profiles_version": registry["version"],
            "director_profiles_hash": registry["content_hash"],
            "production_types": bases}
