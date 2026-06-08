import json
from pathlib import Path
import streamlit as st
from core.state_manager import load_json, save_json, project_path


def main():
    st.set_page_config(page_title="World/Style Bible", layout="wide")
    st.title("🌍 mooV-E Studio: World & Style Bible")

    story = load_json(project_path("story", "expanded_story.json"))
    if not story or not isinstance(story, dict):
        st.warning("No expanded story found. Please complete Page 1 first.")
        if st.button("Go to Story Expansion"):
            st.switch_page("pages/01_story_expansion.py")
        return

    col1, col2 = st.columns([4, 1])
    with col2:
        st.divider()
        st.button("⬇ Next: Structure Builder →", on_click=lambda: st.switch_page("pages/04_structure_builder.py"), type="primary")

    world_bible = load_json(project_path("world", "world_bible.json"))
    style_bible = load_json(project_path("world", "style_bible.json"))
    locations = load_json(project_path("world", "locations.json"), {})

    characters_index = load_json(project_path("characters", "characters_index.json"), {})

    with col1:
        st.divider()

        if not any([world_bible, style_bible]):
            st.info("No World/Style Bible generated yet.")
            if st.button("🎲 Generate World & Style Bible", type="primary"):
                _generate(story, characters_index)

        else:
            st.success("World/Style Bible has been generated.")

    with col1:
        if world_bible and isinstance(world_bible, dict):
            st.subheader("World Rules")
            rules_text = st.text_area("World Rules (editable)", value='\n'.join(world_bible.get('world_rules', [])), height=100)
            
            st.subheader("Locations")
            locs = world_bible.get('locations', [])
            for i, loc in enumerate(locs):
                with st.expander(f"Location {i+1}: {loc.get('name', 'Unnamed')}", expanded=False):
                    st.text_input("Name", value=loc.get('name', ''))
                    st.text_area("Description", value=loc.get('short_description', ''), height=50)
            
            visual_style = st.text_input("Visual Style", value=world_bible.get('visual_style', ''))
            color_palette = st.text_input("Color Palette", value=', '.join(world_bible.get('color_palette', [])))
            mood = st.text_input("Mood", value=world_bible.get('mood', ''))
            
            if st.button("💾 Save World Bible"):
                rules_list = [r.strip() for r in rules_text.split('\n') if r.strip()]
                palette_list = [c.strip() for c in color_palette.split(',') if c.strip()]
                
                save_json(project_path("world", "world_bible.json"), {
                    'world_rules': rules_list,
                    'locations': locs,
                    'visual_style': visual_style,
                    'color_palette': palette_list,
                    'mood': mood,
                    'genre_conventions': world_bible.get('genre_conventions', []),
                    'reference_style_notes': world_bible.get('reference_style_notes', ''),
                })
                st.success("World Bible saved!")

        if style_bible and isinstance(style_bible, dict):
            st.subheader("Style Notes")
            ref_note = st.text_area("Reference Style Notes", value=style_bible.get('reference_style_notes', ''), height=80)
            st.text_input("Genre Conventions", value=', '.join(style_bible.get('genre_conventions', [])))
            
            if st.button("💾 Save Style Bible"):
                save_json(project_path("world", "style_bible.json"), style_bible)
                st.success("Style Bible saved!")
            
            genres = st.multiselect("Genre Conventions", ["Action", "Comedy", "Drama", "Horror", "Mystery", "Romance", "Sci-fi", "Fantasy"], 
                                     default=style_bible.get('genre_conventions', []))

    with col1:
        if style_bible and isinstance(style_bible, dict):
            s_st = st.text_area("Narrative Voice (Book)", value=style_bible.get('narrative_voice', ''))
            a_st = st.text_input("Art Style (Comic/Anime)", value=style_bible.get('art_style', ''))


def _generate(story_data, characters_index):
    """Generate world and style bible data via Ollama."""
    from core.ollama_client import is_ollama_ready, generate_text
    from core.prompt_templates import build_world_bible_prompt
    
    if not is_ollama_ready():
        st.error("Ollama is not running.")
        return

    prompt = build_world_bible_prompt(story_data, characters_index, story_data.get('project_type', 'Movie / Short Film'))
    
    with st.spinner("Generating World & Style Bible..."):
        try:
            result_text = generate_text(prompt)
            
            import json
            start = result_text.find('{')
            end = result_text.rfind('}')
            raw_json = result_text[start:end+1] if start != -1 and end > start else result_text

            data = json.loads(raw_json)
            save_json(project_path("world", "world_bible.json"), data)
            st.success("✅ World & Style Bible generated!")
            st.rerun()

        except Exception as e:
            st.error(f"Generation failed: {e}")


if __name__ == "__main__":
    main()
