import json
from pathlib import Path
import streamlit as st
from core.state_manager import load_json, save_json, project_path


def main():
    st.set_page_config(page_title="Structure Builder", layout="wide")
    st.title("🏗️ mooV-E Studio: Structure Builder")

    story = load_json(project_path("story", "expanded_story.json"))
    if not story or not isinstance(story, dict):
        st.warning("No expanded story found. Please complete Page 1 first.")
        return

    structure_index = load_json(project_path("structure", "structure_index.json"), {'items': []})
    project_type = story.get('project_type', 'Movie / Short Film')

    col1, col2 = st.columns([4, 1])
    with col2:
        st.divider()
        if st.button("Next: Unit Workspace →", type="primary"):
            st.switch_page("pages/05_unit_workspace.py")

    project_type = story.get('project_type', 'Movie / Short Film')
    items = structure_index.get('items', []) if isinstance(structure_index, dict) else []
    is_movie = 'Movie' in project_type
    is_comic = 'Comic' in project_type
    
    ptype_label = "Act" if is_movie else ("Chapter" if is_comic else "Chapter")
    pkid_key = "act_id" if is_movie else "chapter_id"
    sub_key = "scenes" if is_movie else ("pages" if is_comic else "sections")

    with col1:
        st.divider()
        st.subheader(f"Project: {project_type}")

        if not items:
            st.info(f"No {ptype_label}s generated yet. Use the options below.")
            
            with st.expander("Add a new item manually"):
                t_val = st.text_input(f"{ptype_label} Title")
                d_val = st.text_area(f"{ptype_label} Description")
                if st.button("Add", type="primary"):
                    num = len(structure_index.get('items', [])) + 1
                    prefix = pkid_key[:-3]
                    new_item = {
                        pkid_key: f"{prefix}_{num:03d}",
                        'position': num,
                        'title': t_val or f"{ptype_label} {num}",
                        'short_description': d_val or '',
                        sub_key: []
                    }
                    items.append(new_item)
                    save_json(project_path("structure", "structure_index.json"), structure_index)
                    st.success(f"Added {new_item['title']}")
                    st.rerun()

            if st.button("Auto-generate Structure"):
                _generate_structure(story, pkid_key, sub_key)
        
        else:
            st.info(f"{ptype_label}s generated. {len(items)} item(s).")

            for i, it in enumerate(items):
                key_name = pkid_key[:-3]
                display_id = it.get(pkid_key, f"{key_name}_{i}")
                
                with st.expander(f"{i+1}. **[{display_id}]** {it.get('title', '')}", expanded=(i == 0)):
                    n_desc = st.text_input("Description", value=it.get('short_description', ''), key=f"desc_{i}")
                    if n_desc and n_desc != it.get('short_description', ''):
                        it['short_description'] = n_desc

                    subs = it.get(sub_key, [])
                    st.write(f"**{sub_key.capitalize()}** ({len(subs)})")

                    for j, sub in enumerate(subs):
                        sub_id_str = f"scene_{j+1:03d}" if 'Movie' in project_type else (f"page_{i+1}_{j+1:02d}" if is_comic else f"sec_{i+1}_{j+1:02d}")
                        st.text_area(
                            f"  {sub.get('title', sub_id_str)} ({sub_key[:-1]}):",
                            value=sub.get('short_description', ''),
                            key=f"sub_desc_{i}_{j}", height=40
                        )

                    s_c1, s_c2 = st.columns(2)
                    with s_c1:
                        if st.button(f"Add more {sub_key[:-1]}", type="primary", key=f"add_sub_{i}"):
                            num_s = len(subs) + 1
                            if is_movie:
                                new_sub = {'scene_id': f"scene_{num_s:03d}", 'position': num_s, 
                                           'title': f"{it.get('title', '')} Beat {num_s}", 
                                           'short_description': '', 'scene_purpose': '',
                                           'primary_characters': [], 'status': 'draft'}
                            elif is_comic:
                                new_sub = {'page_id': f"page_{i+1}_{num_s:02d}", 'position': num_s,
                                           'short_description': '', 'panel_count_target': 5,
                                           'page_purpose': '', 'status': 'draft'}
                            else:
                                new_sub = {'section_id': f"sec_{i+1}_{num_s:02d}", 'position': num_s,
                                           'short_description': '', 'beat_purpose': '', 'status': 'draft'}
                            subs.append(new_sub)
                            it[sub_key] = subs
                            save_json(project_path("structure", "structure_index.json"), structure_index)
                            st.success(f"Added {sub_key[:-1]}")
                            st.rerun()

                    with s_c2:
                        if st.button(f"Delete this item", key=f"del_{i}"):
                            items.pop(i)
                            for k, it in enumerate(items):
                                it['position'] = k + 1
                            structure_index['items'] = items
                            save_json(project_path("structure", "structure_index.json"), structure_index)
                            st.success(f"Deleted")
                            st.rerun()

        if items:
            st.divider()
            if st.button("💾 Save Structure Index", type="primary"):
                for i, it in enumerate(items):
                    it['position'] = i + 1
                save_json(project_path("structure", "structure_index.json"), structure_index)
                st.success("Structure saved!")


def _generate_structure(story_data, pkid_key, sub_key):
    """Generate structure index via Ollama."""
    from core.ollama_client import is_ollama_ready, generate_text
    from core.prompt_templates import build_structure_index_prompt

    if not is_ollama_ready():
        st.error("Ollama is not running or unreachable.")
        return

    chars = load_json(project_path("characters", "characters_index.json")) or {}
    world = load_json(project_path("world", "world_bible.json"), {}) or {}

    project_type = story_data.get('project_type', 'Movie / Short Film')
    prompt = build_structure_index_prompt(story_data, chars, world, project_type)
    
    with st.spinner("Generating structure index..."):
        try:
            result_text = generate_text(prompt)
            
            import json
            start = result_text.find('{')
            end = result_text.rfind('}')
            if start != -1 and end > start:
                raw_json = result_text[start:end+1]
            else:
                raw_json = result_text

            data = json.loads(raw_json)
            
            # Normalize structure
            is_movie = 'Movie' in project_type
            prefix = pkid_key[:-3]
            sub_prefix = {'scenes': 'scene', 'pages': 'page', 'sections': 'section'}[sub_key] if sub_key else 'unit'
            
            saved = data if isinstance(data, dict) else {}
            save_json(project_path("structure", "structure_index.json"), saved)
            num_items = len(saved.get('items', []))
            st.success(f"✅ Structure index generated with {num_items} item(s)!")
            st.rerun()

        except Exception as e:
            st.error(f"Generation failed: {str(e)[:200]}")


if __name__ == "__main__":
    main()
