import json
import zipfile
from datetime import datetime
from pathlib import Path
import streamlit as st
from core.state_manager import load_json, project_path


def main():
    st.set_page_config(page_title="Export", layout="wide")
    st.title("Export Artifacts")

    story = load_json(project_path("story", "expanded_story.json"))
    if not story or not isinstance(story, dict):
        st.warning("No expanded story found. Complete Page 1 first.")
        return

    title = (story.get('title', '') or 'untitled_project').replace('/', '_')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_filename = f"{title}_{timestamp}.zip"

    st.subheader("Export Options")

    col1, col2 = st.columns(2)

    with col1:
        export_all = st.checkbox("Export All Artifacts (ZIP)", value=True)
        if st.button("Download ZIP", type="primary") and export_all:
            _export_zip(title, zip_filename)

    with col2:
        st.markdown("**Individual Exports**")
        for label, key in [
            ("Story Expanded", "story_expanded"),
            ("Story Summary", "story_summary"),
            ("Characters Index", "characters_index"),
            ("Character Details (all)", "characters_all"),
            ("World/Style Bible", "world_bible"),
            ("Structure Index", "structure_index"),
        ]:
            if st.button(f"Download {label}"):
                _export_json(label.lower().replace(' ', '_'), key)

    # Preview section
    st.divider()
    st.subheader("Preview Export Content")

    tabs = st.tabs(["Story", "Characters", "Structure"])

    with tabs[0]:
        expanded = load_json(project_path("story", "expanded_story.json"), {}) or {}
        summary = load_json(project_path("story", "story_summary.json"), {}) or {}
        col_a, col_b = st.columns(2)
        with col_a:
            st.text_area("Expanded Story", value=expanded.get('expanded_story', '(empty)'), height=150)
        with col_b:
            st.text_area("Summary", value=summary.get('story_summary_for_context', 'N/A'), height=150)

    with tabs[1]:
        chars_idx = load_json(project_path("characters", "characters_index.json"), {}) or {}
        char_list = chars_idx.get('characters', []) if isinstance(char_idx, dict) else []
        if char_list:
            for c in char_list:
                if isinstance(c, dict):
                    name = c.get('name', 'Unknown')
                    role = c.get('role', '')
                    st.write(f"**{name}** ({role})")
        else:
            st.info("No characters generated yet.")

    with tabs[2]:
        struct = load_json(project_path("structure", "structure_index.json"), {}) or {}
        items = struct.get('items', []) if isinstance(struct, dict) else []
        if items:
            for item in items:
                title_val = item.get('title', 'Untitled')
                pos = item.get('position', '')
                st.write(f"- [{pos}] {title_val}")
        else:
            st.info("No structure items generated yet.")


def _export_zip(title: str, zip_filename: str):
    """Create and download a ZIP of all project artifacts."""
    import config

    state_dir = Path(config.PROJECT_STATE_DIR)
    tmp_zip = Path("/tmp") / zip_filename

    with zipfile.ZipFile(tmp_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for dirpath in ['intake', 'story', 'characters', 'structure']:
            target_path = state_dir / dirpath
            if target_path.exists():
                for json_file in sorted(target_path.glob('**/*.json')):
                    arcname = f"{dirpath}/{json_file.relative_to(state_dir)}"
                    zf.write(json_file, arcname)

    st.markdown(f'### Downloading `{zip_filename}`')
    with open(tmp_zip, 'rb') as f:
        st.download_button(
            label="Click to download",
            data=f.read(),
            file_name=zip_filename,
            mime='application/zip',
        )

    tmp_zip.unlink(missing_ok=True)


def _export_json(label_key: str, key: str):
    """Export a single artifact as JSON download."""
    if key == 'characters_all':
        # Collect all char files
        chars_dir = project_path("characters")
        output = {}
        try:
            for fp in Path(chars_dir).glob('char_*.json'):
                data = load_json(str(fp), {})
                output[fp.stem] = data
        except Exception:
            pass
        st.download_button(
            label=f"Download {label_key}.json",
            data=json.dumps(output, indent=2),
            file_name=f"{key}.json",
            mime='application/json',
        )
    else:
        # Single file exports
        key_to_file = {
            'story_expanded': ('story', 'expanded_story.json'),
            'story_summary': ('story', 'story_summary.json'),
            'characters_index': ('characters', 'characters_index.json'),
            'world_bible': ('structure', 'world_style_bible.json'),
            'structure_index': ('structure', 'structure_index.json'),
        }
        subpath, filename = key_to_file.get(key, ('story', 'expanded_story.json'))
        data = load_json(project_path(subpath, filename), {}) or {}

        st.download_button(
            label=f"Download {label_key}.json",
            data=json.dumps(data, indent=2),
            file_name=f"{key}.json",
            mime='application/json',
        )


if __name__ == "__main__":
    main()
