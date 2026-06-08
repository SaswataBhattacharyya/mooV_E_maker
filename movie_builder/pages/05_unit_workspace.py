import json
from pathlib import Path
import streamlit as st
from core.state_manager import load_json, save_json, project_path


def main():
    st.set_page_config(page_title="Unit Workspace", layout="wide")
    st.title("Unit Workspace")

    story = load_json(project_path("story", "expanded_story.json"))
    if not story or not isinstance(story, dict):
        st.warning("No expanded story. Complete Page 1 first.")
        return

    struct = load_json(project_path("structure", "structure_index.json"), {})
    project_type = story.get('project_type', 'Movie / Short Film')
    items = struct.get('items', []) if isinstance(struct, dict) else []

    col1, col2 = st.columns([4, 1])
    with col2:
        st.divider()
        if not items:
            st.info("Build Structure on Page 4 first")
        else:
            if st.button("Next > Review/Continuity", type="primary"):
                st.switch_page("pages/06_review_continuity.py")

    with col1:
        st.divider()
        if not items:
            st.info("No structure items yet.")
            return

        is_movie = 'Movie' in project_type
        is_comic = 'Comic' in project_type
        pkid_key = "act_id" if is_movie else "chapter_id"
        sub_key = "scenes" if is_movie else (
                       "pages" if is_comic else "sections")

        opts_main = []
        for it in items:
            k = str(it.get(pkid_key, ''))
            t = it.get('title', '')
            opts_main.append(k + " | " + t)

        sel_idx = st.selectbox("Select unit", range(len(opts_main)),
                               format_func=lambda i: opts_main[i])
        sel_item = items[sel_idx]
        subs = sel_item.get(sub_key, [])

        with st.expander(sel_item.get('title', ''), expanded=True):
            n_desc = st.text_input(
                "Description",
                value=sel_item.get('short_description', ''),
                key="desc_unit_%d" % sel_idx,
            )
            if n_desc != sel_item.get('short_description', ''):
                sel_item['short_description'] = n_desc

        with st.expander("Sub-items (%d)" % len(subs), expanded=bool(subs)):
            for k, s in enumerate(subs):
                st.text_area(
                    "  Sub-item %d:" % (k + 1),
                    value=s.get('short_description', ''),
                    height=30,
                )

        with st.expander("Generate sub-unit details", expanded=False):
            sel_sub = subs[0] if subs else None
            if sel_sub:
                sid_val = sel_sub.get(
                    'scene_id' if is_movie else 'page_id', '')
                unit_dir = 'movie' if is_movie else (
                    'comic' if is_comic else 'book')

                fp = Path(__import__('config').PROJECT_STATE_DIR) / "units" / unit_dir
                data = None
                for fn in sorted(fp.glob('*')):
                    if str(sid_val) in fn.name:
                        raw = json.loads(fn.read_text())
                        data = {**raw, **sel_sub}

                if data:
                    for field in ['dialogue', 'action_blocking']:
                        val = str(data.get(field, '')) or ''
                        st.text_area(
                            "**%s**" % (field.replace('_', ' ').title()),
                            value=val, height=40)

        story_summary = load_json(
            project_path("story", "story_summary.json"), {}) or {}
        chars = load_json(
            project_path("characters", "characters_index.json"), {}) or {}
        char_names = []
        ch_list = chars.get('characters', []) if isinstance(chars, dict) else []
        for c in ch_list:
            if isinstance(c, dict):
                v = c.get('name', '')
                if v:
                    char_names.append(v)

        with st.expander("Regenerate Unit"):
            if st.button("Generate Unit"):
                _gen_unit(story_summary, sel_item, subs[0], project_type)


def _is_ollama_ready():
    from core.ollama_client import is_ollama_ready as check_ok
    return check_ok()


def _gen_unit(story_summary, sel_item, sel_sub, project_type):
    from core.ollama_client import is_ollama_ready as chk, generate_text as gen
    from core.prompt_templates import build_unit_generation_prompt

    if not chk():
        st.error("Ollama is not running or unreachable.")
        return

    chars_idx = load_json(
        project_path("characters", "characters_index.json")) or {}
    char_names = []
    cl = chars_idx.get('characters', []) if isinstance(chars_idx, dict) else []
    for c in cl:
        if isinstance(c, dict):
            v = c.get('name', '')
            if v:
                char_names.append(v)

    context_data = {
        'story_summary': story_summary,
        'characters_present': char_names,
    }

    prompt = build_unit_generation_prompt(
        context_data, sel_sub, project_type)

    with st.spinner("Generating..."):
        try:
            result_text = gen(prompt)

            sp = result_text.find('{')
            ep = result_text.rfind('}')
            if sp >= 0 and ep > sp:
                raw_json = result_text[sp:ep + 1]
            else:
                raw_json = result_text

            parsed_data = json.loads(raw_json)

            is_movie_flag = 'Movie' in project_type
            is_comic_flag = 'Comic' in project_type
            unit_dir = 'movie' if is_movie_flag else (
                'comic' if is_comic_flag else 'book')

            import config as cfg
            fp = Path(cfg.PROJECT_STATE_DIR) / "units" / unit_dir
            fp.mkdir(parents=True, exist_ok=True)

            sub_id_key = 'scene_id' if is_movie_flag else 'page_id'
            sub_id_val = sel_sub.get(sub_id_key, '')
            out_path = fp / ("%s.json" % sub_id_val)
            save_data = dict(sel_sub)
            save_data.update(parsed_data)
            json.dump(save_data, open(str(out_path), 'w'), indent=2)

            st.success("Unit '%s' generated successfully!" % sel_sub.get('title', 'Untitled'))
        except Exception as e:
            st.error("Generation failed:")
            st.code(str(e)[:500])


if __name__ == "__main__":
    main()
