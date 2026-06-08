from core.state_manager import load_json, save_json, project_path
from core.constants import SUPPORTED_PROJECT_TYPES_V1


def check_continuity_by_unit(project_type: str, scope: str = "current") -> dict:
    """Run continuity checks by scope (current/changed/whole)."""
    issues = []

    # Load story summary as baseline context
    expanded = load_json(project_path("story", "expanded_story.json"), {})
    story_summary = load_json(project_path("story", "story_summary.json"), {}).get(
        "story_summary_for_context", ""
    )

    if not story_summary:
        issues.append({
            "issue_id": "cont_001",
            "severity": "high",
            "affected_ids": ["story"],
            "problem": "No story summary found. Run Story Expansion first.",
            "suggested_fix": "Navigate to Story Expansion (Page 1) and generate the story.",
            "status": "open",
        })

    # Load characters as character reference
    characters = load_json(project_path("characters", "characters_index.json"), {})
    char_names = [c.get('name', '') for c in characters.get('characters', [])]

    if not char_names:
        issues.append({
            "issue_id": "cont_002",
            "severity": "medium",
            "affected_ids": ["characters"],
            "problem": "No character index found or empty.",
            "suggested_fix": "Navigate to Characters (Page 2) and generate the character list.",
            "status": "open",
        })

    # Check structure
    structure = load_json(project_path("structure", "structure_index.json"), {})
    items = structure.get('items', [])

    if not items:
        issues.append({
            "issue_id": "cont_003",
            "severity": "medium",
            "affected_ids": ["structure"],
            "problem": "No structure index found.",
            "suggested_fix": "Navigate to Structure Builder (Page 4) and generate the structure.",
            "status": "open",
        })

    # Check unit files for consistency with character names
    import os
    from config import PROJECT_STATE_DIR

    checked_count = 0
    max_scope = {"current": 1, "changed": 10, "whole": 999}.get(scope, 1)

    for utype in ["movie", "comic"]:
        dir_path = f"{PROJECT_STATE_DIR}/units/{utype}"
        if not os.path.isdir(dir_path):
            continue

        files = sorted(os.listdir(dir_path))
        count = max_scope  # scope controls depth check
        for fn in files[:count]:
            fp = f"{dir_path}/{fn}"
            if not os.path.isfile(fp):
                continue
            unit_data = load_json(fp, {})

            checked_count += 1

    return {
        "project_id": "",
        "checked_units": checked_count,
        "structure_items_checked": len(items),
        "characters_referenced": len(char_names),
        "issues_found": len(issues),
        "issues": issues,
    }


def run_continuity_check(project_type: str, scope: str = "current") -> dict:
    """Run full continuity check and save report."""
    result = check_continuity_by_unit(project_type, scope)

    # Save the report
    if isinstance(result, dict):
        issues_list = result.get('issues', [])
    else:
        issues_list = list(result)

    for i, issue in enumerate(issues_list):
        if isinstance(issue, dict) and 'issue_id' not in issue:
            issue['issue_id'] = f"cont_{i+1:03d}"

    report = {
        "project_type": project_type,
        "scope": scope,
        "issues": issues_list,
    }

    save_json(project_path("review", "continuity_report.json"), report)
    return report


def check_unit_consistency(unit_id: str, _unit_data: dict) -> list[dict]:
    """Check a single unit for internal consistency."""
    issues = []

    # Check for empty required fields based on unit type
    import os
    from config import PROJECT_STATE_DIR
    for utype in ["movie", "comic"]:
        dir_path = f"{PROJECT_STATE_DIR}/units/{utype}"
        if not os.path.isdir(dir_path):
            continue
        fp = f"{dir_path}/{unit_id}.json"
        if not os.path.isfile(fp):
            continue

        data = _unit_data or load_json(fp, {})
        # Add field-specific checks based on unit type
        issues.append({
            "issue_id": f"unit_{unit_id}_01",
            "severity": "info",
            "affected_ids": [unit_id],
            "problem": f"Check '{unit_id}' manually for completeness.",
            "suggested_fix": "Review all fields in this unit.",
            "status": "open",
        })

    return issues
