"""Making-route policy for required and accepted character/world image masters."""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Mapping


IMAGE_MASTER_ROLES = {"character_master", "world_master"}


class RouteAssetError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


def enforce_route_assets(*, route: str, shot_content: Mapping[str, Any], selected_images: list[Mapping[str, Any]],
                         get_asset: Callable[[str], Mapping[str, Any]]) -> dict[str, Any]:
    """Require only route-declared masters and reject unaccepted generated candidates.

    Direct H3 has no implicit image-generation requirement. Reference-built
    defaults to one accepted character master per character plus one world
    master when the shot names a world. Hybrid uses only explicit requirements.
    """
    if route not in {"direct_h3", "reference_built", "hybrid"}:
        raise RouteAssetError("making_route_invalid", "Run has an unsupported making route.")
    requirements: Counter[str] = Counter()
    if route == "reference_built":
        characters = shot_content.get("characters", [])
        if isinstance(characters, list):
            requirements["character_master"] = len({str(item) for item in characters if item})
        if shot_content.get("world_state_id") or shot_content.get("world_id"):
            requirements["world_master"] = 1
    if route == "hybrid" or shot_content.get("asset_requirements"):
        requested = shot_content.get("asset_requirements", [])
        if not isinstance(requested, list):
            raise RouteAssetError("asset_requirements_invalid", "Shot asset_requirements must be a list.")
        for item in requested:
            if not isinstance(item, dict) or item.get("required", True) is not True:
                continue
            role = item.get("role")
            count = item.get("count", 1)
            if role not in IMAGE_MASTER_ROLES or not isinstance(count, int) or not 1 <= count <= 9:
                raise RouteAssetError("asset_requirements_invalid", "Required image assets need a supported master role and count 1–9.")
            requirements[str(role)] = max(requirements[str(role)], count)
    selected: Counter[str] = Counter()
    seen: set[str] = set()
    seen_characters: set[str] = set()
    for ref in selected_images:
        asset_id = str(ref.get("asset_id", ""))
        role = str(ref.get("role", ""))
        if asset_id in seen:
            raise RouteAssetError("duplicate_master_asset", "One image cannot count as multiple required masters.", details={"asset_id": asset_id})
        seen.add(asset_id)
        record = get_asset(asset_id)
        if record.get("kind") != "image" or role not in record.get("roles", []):
            raise RouteAssetError("asset_role_mismatch", "Selected image role must match its registered project role.", details={"asset_id": asset_id, "role": role})
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        if record.get("source") == "project_output":
            legacy = metadata.get("production_image_job", {})
            accepted_legacy = (isinstance(legacy, dict) and legacy.get("status") == "completed"
                and legacy.get("accepted") is True and legacy.get("accepted_role") == role)
            if metadata.get("approval_status") != "accepted" and not accepted_legacy:
                raise RouteAssetError("generated_asset_not_accepted",
                    "A generated image candidate must be explicitly accepted before shot use.",
                    details={"asset_id": asset_id, "role": role})
        character_id = metadata.get("character_id")
        world_id = metadata.get("world_id") or metadata.get("world_state_id")
        if route == "reference_built" and role in IMAGE_MASTER_ROLES:
            identity = character_id if role == "character_master" else world_id
            if not identity:
                raise RouteAssetError("master_identity_required", "Assign this master to its character or world in the project asset library before shot use.", details={"asset_id": asset_id, "role": role})
        if role == "character_master" and character_id and character_id not in shot_content.get("characters", []):
            raise RouteAssetError("master_identity_mismatch", "Character master belongs to a different character.")
        if role == "character_master" and character_id:
            if character_id in seen_characters:
                raise RouteAssetError("duplicate_character_master", "Multiple images of one character cannot satisfy different character masters.")
            seen_characters.add(character_id)
        if role == "world_master" and world_id and world_id != (shot_content.get("world_state_id") or shot_content.get("world_id")):
            raise RouteAssetError("master_identity_mismatch", "World master belongs to a different world.")
        selected[role] += 1
    missing = {role: count - selected[role] for role, count in requirements.items() if selected[role] < count}
    if missing:
        raise RouteAssetError("required_master_assets_missing",
            "This making route requires accepted character/world master images before this shot can proceed.",
            details={"missing_roles": missing, "route": route})
    return {"making_route": route, "required_roles": dict(requirements),
            "selected_roles": dict(selected), "satisfied": True}
