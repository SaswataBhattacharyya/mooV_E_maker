from core.state_manager import load_json, save_json, project_path


def _find_id_field():
    """Identify the correct ID field name based on structure content."""
    structure = load_structure_index()
    items = structure.get('items', [])
    if not items:
        return 'act_id'
    first = items[0]
    for key in ['chapter_id', 'section_id', 'act_id']:
        if first.get(key):
            return key
    return 'act_id'


def load_structure_index() -> dict:
    """Load the structure index."""
    return load_json(project_path("structure", "structure_index.json"), {"project_type": "", "items": []})


def save_structure_index(structure: dict) -> None:
    """Save the structure index."""
    save_json(project_path("structure", "structure_index.json"), structure)


def add_structure_item(item: dict, index: int = None) -> dict:
    """Add an item to the structure top-level list."""
    structure = load_structure_index()

    existing_positions = [i.get('position', 0) for i in structure.get('items', [])]
    new_position = max(existing_positions, default=0) + 1
    item.setdefault('position', new_position)

    if index is None or index >= len(structure['items']):
        structure['items'].append(item)
    else:
        structure['items'].insert(index, item)

    for i, it in enumerate(structure['items']):
        it['position'] = i + 1

    save_structure_index(structure)
    return structure


def delete_structure_item(item_id: str, soft_delete: bool = True) -> dict:
    """Delete or soft-delete a structure item."""
    structure = load_structure_index()
    items = structure.get('items', [])

    id_fields = ['act_id', 'chapter_id', 'section_id']
    found_idx = -1
    for i, it in enumerate(items):
        for kf in id_fields:
            if str(it.get(kf)) == item_id:
                found_idx = i
                break
        if found_idx != -1:
            break

    if found_idx == -1:
        return structure

    removed = items.pop(found_idx)
    if soft_delete:
        removed['_soft_deleted'] = True
        structure.setdefault('_deleted_items', []).append(removed)

    for i, it in enumerate(structure['items']):
        it['position'] = i + 1

    save_structure_index(structure)
    return structure


def move_structure_item(item_id: str, direction: str) -> dict:
    """Move an item up or down in the structure."""
    structure = load_structure_index()
    items = structure.get('items', [])

    id_fields = ['act_id', 'chapter_id', 'section_id']
    idx = None
    for i, it in enumerate(items):
        for kf in id_fields:
            if str(it.get(kf)) == item_id:
                idx = i
                break
        if idx is not None:
            break

    if idx is None:
        return structure

    if direction == "up" and idx > 0:
        items[idx], items[idx - 1] = items[idx - 1], items[idx]
        idx -= 1
    elif direction == "down" and idx < len(items) - 1:
        items[idx], items[idx + 1] = items[idx + 1], items[idx]

    for i, it in enumerate(structure['items']):
        it['position'] = i + 1

    save_structure_index(structure)
    return structure


def update_structure_item_description(item_id: str, new_description: str) -> dict:
    """Update the short description of a structure item."""
    structure = load_structure_index()
    id_fields = ['act_id', 'chapter_id', 'section_id']

    for it in structure.get('items', []):
        found = False
        for kf in id_fields:
            if str(it.get(kf)) == item_id:
                found = True
                break
        if found:
            it['short_description'] = new_description
            save_structure_index(structure)
            return structure

    return structure


def find_structure_item(item_id: str):
    """Find a structure item by its ID."""
    structure = load_structure_index()
    id_fields = ['act_id', 'chapter_id', 'section_id']
    for it in structure.get('items', []):
        for kf in id_fields:
            if str(it.get(kf)) == item_id:
                return it
    return None
