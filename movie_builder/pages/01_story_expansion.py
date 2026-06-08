import json
from pathlib import Path
import streamlit as st
from core.state_manager import load_json, save_json, project_path, ensure_project_dirs


def main():
    st.set_page_config(page_title="Story Expansion", layout="wide")
    st.title("📖 mooV-E Studio: Story Expansion")

    intake = load_json(project_path("intake", "intake.json"))
    if not intake or not isinstance(intake, dict):
        st.warning("No Project Intake data found. Please complete Page 0 first.")
        if st.button("Go to Project Intake"):
            st.switch_page("pages/00_project_intake.py")
        return

    title = intake.get('title', 'Untitled')
    genre = intake.get('genre', 'Drama')
    tone = intake.get('tone', 'Emotional')
    raw_story = intake.get('raw_story', '')
    
    st.markdown(f"**Project:** {title} | **Genre:** {genre} | **Tone:** {tone}")

    # Load existing expanded story if any
    expanded = load_json(project_path("story", "expanded_story.json"))
    summary = load_json(project_path("story", "story_summary.json"))

    col1, col2 = st.columns([4, 2])
    with col1:
        st.divider()
        st.subheader("Generated Story")

        if expanded and isinstance(expanded, dict) and expanded.get('expanded_story'):
            st.markdown("---")
            st.info(f"**Logline:** {expanded.get('logline', 'N/A')}")
            st.info(f"**Ending:** {expanded.get('ending', 'N/A')}")
            st.info(f"**Themes:** {', '.join(expanded.get('themes', []))}")

            editable_story = st.text_area("Expanded Story (editable)", value=expanded.get('expanded_story', ''), height=300)

            # Revision section
            with st.expander("Revise the Story"):
                rev_instruction = st.text_area("Revision Instructions", height=100, placeholder="Describe what you want to change about the story.")
                if st.button("Revise Story", type="primary"):
                    do_revision(editable_story, rev_instruction)
        else:
            st.info("Click **Generate Story** below to expand your raw idea into a full story.")

        # Generate button
        if not expanded or not isinstance(expanded, dict):
            with st.expander("Generation Settings (optional)", expanded=False):
                st.write(f"**Raw Story:** {raw_story[:200]}...")
                st.write(f"**Genre:** {genre} | **Tone:** {tone}")
        
        if st.button("🎲 Generate Story", type="primary"):
            do_generate(intake)

    with col2:
        st.divider()
        st.subheader("Project Info")
        st.json(intake)
        
        st.divider()
        st.button("⬇ Next: Characters →", on_click=lambda: st.switch_page("pages/02_characters.py"), type="primary")


def do_generate(intake):
    """Generate the expanded story using Ollama."""
    from core.ollama_client import is_ollama_ready, generate_text
    from core.prompt_templates import build_story_generation_prompt
    
    if not is_ollama_ready():
        st.error("Ollama is not running or not reachable at the configured host.")
        return

    prompt = build_story_generation_prompt(intake)
    
    with st.spinner("Generating your story..."):
        try:
            result_text = generate_text(prompt)
            
            # Parse JSON from text
            import json
            start = result_text.find('{')
            end = result_text.rfind('}')
            if start != -1 and end > start:
                raw_json = result_text[start:end+1]
            else:
                raw_json = result_text

            data = json.loads(raw_json)
            
            # Save
            save_data = {
                'project_id': intake.get('project_id', ''),
                'title': intake.get('title', ''),
                'project_type': intake.get('project_type', ''),
                'genre': genre,
                **data,
            }
            save_json(project_path("story", "expanded_story.json"), save_data)
            st.success("✅ Story generated!")

        except Exception as e:
            st.error(f"Generation failed: {e}")


def do_revision(story_text, instruction):
    """Revise the story."""
    from core.ollama_client import is_ollama_ready, generate_text
    
    if not is_ollama_ready():
        st.error("Ollama is not running.")
        return

    from core.prompt_templates import build_story_revision_prompt
    current = load_json(project_path("story", "expanded_story.json")) or {}

    full_story_data = dict(current)
    full_story_data['expanded_story'] = story_text
    
    prompt = build_story_revision_prompt(full_story_data, instruction)
    
    with st.spinner("Revising your story..."):
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
            
            existing = load_json(project_path("story", "expanded_story.json"), {})
            existing.update(data)
            save_json(project_path("story", "expanded_story.json"), existing)
            st.success("✅ Story revised!")
            st.rerun()

        except Exception as e:
            st.error(f"Revision failed: {e}")


if __name__ == "__main__":
    main()
