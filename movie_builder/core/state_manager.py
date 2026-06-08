import json
from pathlib import Path
from typing import Any, Optional
import config


def ensure_project_dirs() -> None:
    """Create all project state directories if they don't exist."""
    dirs = [
        config.PROJECT_STATE_DIR,
        config.EXPORTS_DIR,
        config.CONFIG_DIR,
        f"{config.PROJECT_STATE_DIR}/intake",
        f"{config.PROJECT_STATE_DIR}/story",
        f"{config.PROJECT_STATE_DIR}/characters",
        f"{config.PROJECT_STATE_DIR}/world",
        f"{config.PROJECT_STATE_DIR}/structure",
        f"{config.PROJECT_STATE_DIR}/units/movie",
        f"{config.PROJECT_STATE_DIR}/units/comic",
        f"{config.PROJECT_STATE_DIR}/units/book",
        f"{config.PROJECT_STATE_DIR}/units/anime",
        f"{config.PROJECT_STATE_DIR}/units/audio_drama",
        f"{config.PROJECT_STATE_DIR}/review",
        f"{config.PROJECT_STATE_DIR}/exports",
        config.EXPORTS_DIR,
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


def load_json(path: str, default: Any = None) -> Any:
    """Load JSON from path. Returns default if file doesn't exist."""
    p = Path(path) if not Path(path).is_absolute() else Path(path)
    if not p.exists():
        return default
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError) as e:
        raise Exception(f"Failed to parse JSON file '{p}': {e}")


def save_json(path: str, data: Any) -> None:
    """Save data as formatted JSON."""
    p = Path(path) if not Path(path).is_absolute() else Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_text(path: str, default: str = "") -> str:
    """Load text from path. Returns default if file doesn't exist."""
    p = Path(path) if not Path(path).is_absolute() else Path(path)
    if not p.exists():
        return default
    with open(p, 'r', encoding='utf-8') as f:
        return f.read()


def save_text(path: str, text: str) -> None:
    """Save text to path."""
    p = Path(path) if not Path(path).is_absolute() else Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)


def project_path(*parts: str) -> str:
    """Resolve a path under project_state."""
    return str(Path(config.PROJECT_STATE_DIR) / Path(*parts))


def export_path(*parts: str) -> str:
    """Resolve a path under exports."""
    return str(Path(config.EXPORTS_DIR) / Path(*parts))


def next_id(prefix: str, existing_ids: list[str]) -> str:
    """Generate next stable ID with given prefix."""
    if not existing_ids:
        return f"{prefix}{1:03d}"
    # Extract numbers from existing IDs matching this prefix
    nums = []
    for eid in existing_ids:
        if eid.startswith(prefix) and eid[len(prefix):].isdigit():
            nums.append(int(eid[len(prefix):]))
    max_num = max(nums) if nums else 0
    return f"{prefix}{max_num + 1:03d}"


def insert_position(items: list[dict], new_item: dict, index: Optional[int] = None) -> list[dict]:
    """Insert item at given position or append. Normalizes positions."""
    if index is None or index >= len(items):
        items.append(new_item)
    else:
        items.insert(index, new_item)
    return normalize_positions(items)


def normalize_positions(items: list[dict]) -> list[dict]:
    """Set position values sequentially starting from 1."""
    for i, item in enumerate(items):
        if isinstance(item, dict) and 'position' in item:
            item['position'] = i + 1
    return items


def append_change_log(entry: dict) -> None:
    """Append an entry to the change log."""
    ensure_project_dirs()
    log_path = project_path("review", "change_log.json")
    existing = load_json(log_path, [])
    if not isinstance(existing, list):
        existing = []
    # Add timestamp if not present
    import datetime
    if 'timestamp' not in entry:
        entry['timestamp'] = datetime.datetime.now().isoformat()
    existing.append(entry)
    save_json(log_path, existing)
