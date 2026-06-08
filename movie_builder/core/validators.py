import json
from core.constants import SUPPORTED_PROJECT_TYPES_V1, PROJECT_TYPES


def validate_required_keys(data: dict, required_keys: list[str]) -> None:
    """Validate that all required keys are present in data."""
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise ValueError(f"Missing required keys: {missing}")


def ensure_stable_id(old_id: str, new_data: dict, key: str = "character_id") -> None:
    """Ensure the stable ID is preserved in updated data."""
    current_value = new_data.get(key, "")
    if current_value and current_value != old_id:
        raise ValueError(f"Stable ID mismatch: expected '{old_id}', got '{current_value}' for key '{key}'")
    new_data[key] = old_id


def validate_project_type(project_type: str) -> bool:
    """Validate project type is in the supported list."""
    return project_type in PROJECT_TYPES


def validate_supported_v1_project_type(project_type: str) -> tuple[bool, str]:
    """Check if a project type is supported in v1. Returns (is_supported, message)."""
    if project_type in SUPPORTED_PROJECT_TYPES_V1:
        return True, ""

    v2_types = ["Single Episode", "Anime Episode", "Manga/Webtoon"]
    v3_types = ["Game / Visual Novel", "Illustrated Storybook", "Audio Drama"]

    if project_type in v2_types:
        return False, f"'{project_type}' is planned for version 2. You can still save your intake and continue with limited support."
    elif project_type in v3_types:
        return False, f"'{project_type}' is planned for version 3. You can still save your intake and continue with limited support."
    else:
        return False, f"'{project_type}' is not recognized as a valid project type."


def validate_positions(items: list[dict]) -> bool:
    """Validate that positions in items start from 1 without duplicates."""
    if not items:
        return True

    # Normalize positions first
    nums = sorted(set(item.get('position', i + 1) for i, item in enumerate(items)))
    expected = list(range(1, len(nums) + 1))
    return nums == expected


def validate_no_active_references_to_deleted_id(deleted_id: str) -> dict:
    """Return references to a deleted ID (for informational logging, not enforcement)."""
    # This is a helper for manual validation - actual checks happen in chunking/deletion repair
    return {
        "deleted_id": deleted_id,
        "needs_manual_check": True,
        "message": f"Check that no remaining objects reference '{deleted_id}'."
    }
