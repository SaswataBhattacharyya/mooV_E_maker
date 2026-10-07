from __future__ import annotations

import pytest

from story_builder.services.production_route_assets import RouteAssetError, enforce_route_assets


def _asset(asset_id, *, source="project_upload", status=None):
    return {"asset_id": asset_id, "kind": "image", "roles": ["character_master", "world_master"],
            "source": source, "metadata": {"approval_status": status}}


def test_direct_h3_skips_image_generation_requirements():
    result = enforce_route_assets(route="direct_h3", shot_content={"characters": ["c1"], "world_state_id": "w1"},
        selected_images=[], get_asset=lambda _asset_id: {})
    assert result["satisfied"] is True and result["required_roles"] == {}


def test_reference_built_requires_declared_character_and_world_masters():
    content = {"characters": ["c1", "c2"], "world_state_id": "world-night"}
    with pytest.raises(RouteAssetError) as missing:
        enforce_route_assets(route="reference_built", shot_content=content, selected_images=[], get_asset=lambda _id: {})
    assert missing.value.code == "required_master_assets_missing"
    images = [{"asset_id": "a", "role": "character_master"},
              {"asset_id": "b", "role": "character_master"},
              {"asset_id": "w", "role": "world_master"}]
    accepted = enforce_route_assets(route="reference_built", shot_content=content,
        selected_images=images, get_asset=lambda asset_id: {**_asset(asset_id), "metadata":
            {"character_id": {"a": "c1", "b": "c2"}.get(asset_id), "world_id": "world-night"}})
    assert accepted["required_roles"] == {"character_master": 2, "world_master": 1}


def test_hybrid_requires_only_shot_declared_selected_masters_and_acceptance():
    content = {"characters": ["c1", "c2"], "asset_requirements": [
        {"role": "character_master", "count": 1}, {"role": "world_master", "required": False}]}
    selected = [{"asset_id": "image-1", "role": "character_master"}]
    result = enforce_route_assets(route="hybrid", shot_content=content, selected_images=selected,
        get_asset=lambda asset_id: _asset(asset_id, source="project_output", status="accepted"))
    assert result["required_roles"] == {"character_master": 1}
    with pytest.raises(RouteAssetError) as candidate:
        enforce_route_assets(route="hybrid", shot_content=content, selected_images=selected,
            get_asset=lambda asset_id: _asset(asset_id, source="project_output", status="candidate"))
    assert candidate.value.code == "generated_asset_not_accepted"


def test_route_asset_requirements_reject_invalid_contract():
    with pytest.raises(RouteAssetError) as role:
        enforce_route_assets(route="hybrid", shot_content={"asset_requirements": [{"role": "sfx_candidate"}]},
            selected_images=[], get_asset=lambda _id: {})
    assert role.value.code == "asset_requirements_invalid"
