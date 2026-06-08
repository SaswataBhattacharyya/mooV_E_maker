import json
from pathlib import Path
import streamlit as st
from core.state_manager import load_json, save_json, project_path


def main():
    st.set_page_config(page_title="Review & Continuity", layout="wide")
    st.title("Review / Continuity")

    story = load_json(project_path("story", "expanded_story.json"))
    if not story or not isinstance(story, dict):
        st.warning("No expanded story found. Please complete Page 1 first.")
        return

    project_type = story.get('project_type', 'Movie / Short Film')

    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("Export ->", type="primary"):
            st.switch_page("pages/07_export.py")

    with col1:
        st.subheader("Run Continuity Check")
        scope = st.radio(
            "Check scope",
            ["current unit", "changed units", "whole project (chunked)"],
            horizontal=True,
        )

        if st.button("Run Continuity Check", type="primary"):
            with st.spinner("Running continuity check..."):
                report = _run_check(project_type, scope)
                save_json(
                    project_path("review", "continuity_report.json"),
                    {
                        'project_type': project_type,
                        'scope': scope,
                        'generated_at': str(Path.cwd()),
                        **report,
                    },
                )
                st.session_state['continuity_report'] = report
                st.success("Continuity check complete.")

    report = st.session_state.get('continuity_report') or load_json(
        project_path("review", "continuity_report.json"),
    ) or {}

    if not report:
        return

    issues = report.get('issues', [])
    if isinstance(issues, list) and len(issues) > 0:
        st.subheader("Continuity Issues")
        for i in issues:
            if isinstance(i, dict):
                severity = i.get('severity', 'warning')
                with st.expander(f"[{severity.upper()}] {i.get('unit', '')}: {i.get('problem', '')}"):
                    st.write("**Detail:**", i.get('detail', 'No detail provided'))
                    st.json(i)
            else:
                st.write("-", i)

        if st.button("Clear Report"):
            del st.session_state['continuity_report']
            st.rerun()
    elif not issues:
        st.success(f"Continuity check completed. Scope: {report.get('scope', 'unknown')}")
        checked = report.get('checked_units', 0)
        if checked and isinstance(checked, (int, float)):
            st.write(f"Units checked: {checked}")


def _run_check(project_type: str, scope: str) -> dict:
    """Run a continuity check and return the report dict."""
    from core.ollama_client import generate_text
    from core.state_manager import load_json as lj

    # Gather minimal context chunks for the check
    story_summary = lj(project_path("story", "story_summary.json"), {}) or {}
    summary_text = story_summary.get('story_summary_for_context', '')
    if not summary_text:
        expanded = lj(project_path("story", "expanded_story.json"))
        if expanded and isinstance(expanded, dict):
            summary_text = str(expanded.get('expanded_story', ''))

    char_idx = lj(project_path("characters", "characters_index.json"), {}) or {}
    chars_list = char_idx.get('characters', []) if isinstance(char_idx, list) else []
    character_names = [c.get('name', '') for c in chars_list if isinstance(c, dict)]

    context_block = {
        'summary': summary_text,
        'character_names': '|'.join(character_names),
        'project_type': project_type,
    }

    # Load all unit files to check
    units_dir = Path(__import__('config').PROJECT_STATE_DIR) / "units"
    units: list[dict] = []
    if units_dir.exists():
        for root_dir in units_dir.iterdir():
            if root_dir.is_dir():
                for uf in root_dir.glob("*.json"):
                    data = json.loads(uf.read_text())
                    data['_file'] = str(uf)
                    units.append(data)

    # Simple structural checks across units
    issues: list[dict] = []

    # Check 1: Character name references against known characters
    for u in units:
        unit_str = json.dumps(u)
        for name in character_names:
            if 'characters' not in [k.lower() for k in u.keys()] and name.lower() in unit_str.lower():
                issues.append({
                    'severity': 'info',
                    'unit': Path(u.get('_file', '')).name,
                    'problem': f"Character '{name}' may be referenced implicitly",
                    'detail': 'Verify character presence is intentional.',
                })

    return {
        'scope': scope,
        'checked_units': len(units),
        'issues': issues,
    }


if __name__ == "__main__":
    main()
