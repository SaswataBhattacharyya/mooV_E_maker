"""Preserve approved units during an explicitly requested bounded text repair."""
from copy import deepcopy
from typing import Any


def select_held_shot_units(base: dict[str, Any], units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if base.get('stage') != 'shot_plans' or base.get('review_status') != 'pending_director_repair' or base.get('complete') is not True:
        raise ValueError('Repair requires a complete held shot-plan revision.')
    items = base.get('items') or []
    ids = [item.get('unit_id') for item in items]
    if len(ids) != len(set(ids)) or ids != [unit.get('unit_id') for unit in units] or ids != base.get('expected_unit_ids') or ids != base.get('completed_unit_ids'):
        raise ValueError('Repair must retain the exact complete ordered unit IDs.')
    held = []
    for item, unit in zip(items, units):
        review = item.get('director_review') or {}
        if review.get('decision') == 'approve' and type(review.get('confidence')) in (int, float) and .7 <= review['confidence'] <= 1:
            continue
        if review.get('decision') != 'repair':
            raise ValueError('Every inherited unit must have a valid saved Director decision.')
        for key in ('scene_id', 'character_ids', 'world_id', 'source_chunk_ids', 'shot_outline'):
            if unit.get(key) != item.get(key):
                raise ValueError(f'Repair cannot change the trusted {key} for {item["unit_id"]}.')
        value = deepcopy(unit)
        value['prior_content'] = deepcopy(item['content'])
        value['repair_issues'] = deepcopy(review.get('issues', []))
        held.append(value)
    if not held:
        raise ValueError('No held shot requires repair.')
    return held


def merge_repaired_shot_revision(base: dict[str, Any], revision: dict[str, Any]) -> dict[str, Any]:
    held_ids = {item['unit_id'] for item in base['items'] if (item.get('director_review') or {}).get('decision') != 'approve'}
    replacement = {item['unit_id']: item for item in revision['items']}
    if len(replacement) != len(revision['items']) or set(replacement) != held_ids:
        raise ValueError('Repair must replace exactly the held units once.')
    value = deepcopy(revision)
    value['items'] = [deepcopy(replacement.get(item['unit_id'], item)) for item in base['items']]
    value['expected_unit_ids'] = deepcopy(base['expected_unit_ids'])
    value['completed_unit_ids'] = [item['unit_id'] for item in value['items']]
    value['parent_revision_id'] = base['revision_id']
    value['inherited_approved_unit_ids'] = [item['unit_id'] for item in base['items'] if item['unit_id'] not in held_ids]
    value['director_review']['items'] = deepcopy(value['items'])
    value['director_review']['inherited_approved_unit_ids'] = value['inherited_approved_unit_ids']
    return value
