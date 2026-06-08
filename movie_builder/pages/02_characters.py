import json
from pathlib import Path
import streamlit as st
from core.state_manager import load_json, save_json, project_path, ensure_project_dirs


def main():
    st.set_page_config(page_title="Characters", layout="wide")
    st.title("👥 mooV-E Studio: Characters")

    story = load_json(project_path("story", "expanded_story.json"))
    if not story or not isinstance(story, dict):
        st.warning("No expanded story found. Please complete Page 1 first.")
        if st.button("Go to Story Expansion"):
            st.switch_page("pages/01_story_expansion.py")
        return

    summary_text = story.get('expanded_story', '') or story.get('story_summary_for_context', '')

    col1, col2 = st.columns([4, 1])
    with col2:
        st.divider()
        st.button("⬇ Next: World/Style Bible →", on_click=lambda: st.switch_page("pages/03_world_style_bible.py"), type="primary")

    characters_index = load_json(project_path("characters", "characters_index.json"), {})
    char_list = characters_index.get('characters', []) if isinstance(characters_index, dict) else []

    with col1:
        st.divider()
        
        if not char_list:
            st.info("No character index yet. Click below to generate one from the story.")
            if st.button("🎲 Generate Character Index", type="primary"):
                _generate_index(story)
        else:
            st.success(f"Built {len(char_list)} character(s).")

            for i, char in enumerate(char_list):
                with st.expander(f"**{char.get('name', 'Unknown')}** ({char.get('role', 'N/A')})", expanded=False):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**ID:** {char.get('character_id', 'N/A')}")
                        st.write(f"**Role:** {char.get('role', 'N/A')}")
                    with c2:
                        st.write(f"**Status:** {char.get('status', 'N/A')}")

                    char_detail = load_json(project_path("characters", f"{char.get('character_id', '')}.json"))

                    if char_detail and isinstance(char_detail, dict):
                        fields_to_show = ['physical_description', 'backstory', 'motivation', 'arc',
                                         'speech_style', 'personality', 'costume']
                        for field in fields_to_show:
                            val = char_detail.get(field, '')
                            if val:
                                st.text_area(f"**{field.replace('_', ' ').title()}** (editable)", value=val, height=60)

                    with st.expander("Revise this Character", expanded=False):
                        rev_instr = st.text_area("Revision Instructions", height=50, 
                                                  placeholder="e.g. Make them more villainous, change their age range")
                        if st.button(f"Revise {char.get('name', 'this character')}", type="primary"):
                            _revise_character(char, story, rev_instr)
                
                # Action buttons per character
                a1, a2, a3 = st.columns(3)
                with a1:
                    if st.button(f"Generate Details", key=f"gen_{i}"):
                        _generate_detail(char, story)
                with a2:
                    if st.button("Move Up", key=f"up_{i}"):
                        _move_char(i, -1)
                with a3:
                    if st.button("Move Down", key=f"down_{i}"):
                        _move_char(i, 1)

        # Add Character button
        st.divider()
        if st.button("+ Add Blank Character"):
            if not isinstance(characters_index, dict):
                characters_index = {'characters': []}
            idx_list = characters_index.get('characters', [])
            chars = list(idx_list)
            num = len(chars) + 1
            char_id = "char_00%d" % num
            chars.append({
                'character_id': char_id,
                'position': num,
                'name': '',
                'role': 'supporting',
                'short_description': '',
                'story_purpose': '',
                'appears_in_units': [],
                'status': 'draft'
            })
            save_json(project_path("characters", "characters_index.json"), {'characters': chars})
            st.success(f"Added {char_id}")
            st.rerun()


def _generate_index(story):
    """Generate character index using Ollama."""
    from core.ollama_client import is_ollama_ready, generate_text
    from core.prompt_templates import build_character_index_prompt
    
    if not is_ollama_ready():
        st.error("Ollama is not running.")
        return

    prompt = build_character_index_prompt(story, story.get('project_type', 'Movie / Short Film'))
    
    with st.spinner("Generating character index..."):
        try:
            result_text = generate_text(prompt)
            
            import json
            start = result_text.find('{')
            end = result_text.rfind('}')
            raw_json = result_text[start:end+1] if start != -1 and end > start else result_text

            data = json.loads(raw_json)
            char_list = data.get('characters', [])
            save_json(project_path("characters", "characters_index.json"), data)
            st.success(f"✅ Generated {len(char_list)} character(s)!")
            st.rerun()

        except Exception as e:
            st.error(f"Generation failed: {e}")


def _generate_detail(char_entry, story):
    """Generate detail for one character."""
    from core.ollama_client import is_ollama_ready, generate_text
    from core.prompt_templates import build_character_detail_prompt
    
    if not is_ollama_ready():
        st.error("Ollama is not running.")
        return

    prompt = build_character_detail_prompt(story, char_entry, story.get('project_type', 'Movie / Short Film'))
    
    with st.spinner(f"Generating details for {char_entry.get('name', 'this character')}..."):
        try:
            result_text = generate_text(prompt)
            
            import json
            start = result_text.find('{')
            end = result_text.rfind('}')
            raw_json = result_text[start:end+1] if start != -1 and end > start else result_text

            data = json.loads(raw_json)
            cid = char_entry.get('character_id', '')
            save_json(project_path("characters", f"{cid}.json"), data)
            
            # Update index with name/role from detail if missing
            idx = load_json(project_path("characters", "characters_index.json"), {})
            chars = idx.get('characters', [])
            for c in chars:
                if c.get('character_id') == cid:
                    if c.get('name') != data.get('name'):
                        c['name'] = data.get('name')
                    if not c.get('short_description'):
                        c['short_description'] = data.get('personality', '')
            save_json(project_path("characters", "characters_index.json"), idx)
            
            st.success(f"✅ {char_entry.get('name', 'Character')} details generated!")

        except Exception as e:
            st.error(f"Details generation failed: {e}")


def _revise_character(char_entry, story, instruction):
    """Revise one character."""
    from core.ollama_client import is_ollama_ready, generate_text
    
    if not is_ollama_ready():
        st.error("Ollama is not running.")
        return

    current = load_json(project_path("characters", f"{char_entry.get('character_id', '')}.json"), {}) or {}
    
    from core.prompt_templates import build_character_revision_prompt
    prompt = build_character_revision_prompt(story, current, instruction)
    prompt = prompt.replace("return valid JSON only. No markdown.", "Return valid JSON only. No markdown.")

    with st.spinner(f"Revising {char_entry.get('name', 'this character')}..."):
        try:
            result_text = generate_text(prompt)
            
            import json
            start = result_text.find('{')
            end = result_text.rfind('}')
            raw_json = result_text[start:end+1] if start != -1 and end > start else result_text

            data = json.loads(raw_json)
            cid = char_entry.get('character_id', '')
            save_json(project_path("characters", f"{cid}.json"), data)
            st.success("✅ Character revised!")
            st.rerun()

        except Exception as e:
            st.error(f"Revision failed: {e}")


def _move_char(idx, direction):
    """Move character up or down in the list."""
    idx_data = load_json(project_path("characters", "characters_index.json"), {})
    chars = idx_data.get('characters', [])
    
    new_idx = idx + direction
    if 0 <= new_idx < len(chars):
        chars[idx], chars[new_idx] = chars[new_idx], chars[idx]
        
        for i, c in enumerate(chars):
            c['position'] = i + 1
        
        save_json(project_path("characters", "characters_index.json"), {'characters': chars})
        st.rerun()


if __name__ == "__main__":
    main()
