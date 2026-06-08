import time
import json
from pathlib import Path

import streamlit as st
from core.state_manager import save_json, load_json, project_path, ensure_project_dirs


def _load_existing():
    existing = load_json(project_path("intake", "intake.json"))
    if existing and isinstance(existing, dict) and existing.get('raw_story'):
        return existing
    ptypes = [
        "Movie / Short Film", "Single Episode", "Anime Episode",
        "Comic / Graphic Novel", "Manga/Webtoon", "Book / Novel",
        "Illustrated Storybook", "Audio Drama", "Game / Visual Novel"
    ]
    for k, v in st.session_state.items():
        if k.startswith('_intake_'):
            del st.session_state[k]
    return None


def main():
    st.set_page_config(page_title="Project Intake", layout="wide")
    st.title("📂 mooV-E Studio: Project Intake")

    existing = _load_existing() if not st.session_state else None
    if existing:
        ptypes = [
            "Movie / Short Film", "Single Episode", "Anime Episode",
            "Comic / Graphic Novel", "Manga/Webtoon", "Book / Novel",
            "Illustrated Storybook", "Audio Drama", "Game / Visual Novel"
        ]
        genres = ["Horror", "Thriller", "Romance", "Sci-fi", "Fantasy", "Mystery", "Comedy", "Drama", "Historical", "Supernatural", "Mythological", "Action", "Slice of Life", "Children", "Custom"]
        tones = ["Dark", "Emotional", "Funny", "Poetic", "Cinematic", "Gritty", "Dreamlike", "Fast-paced", "Slow-burn", "Custom"]
        vs = ["Photorealistic", "Stylized", "Animated", "Noir", "Impressionist", "Minimalist", "Surreal", "Custom"]
        fmts = [
            "Short Film (under 10 min)", "Short Film (10-30 min)",
            "Feature Film (90-120 min)", "Limited Series (6 episodes)",
            "Pilot Episode", "Web Series", "Music Video", "Custom"
        ]
        langs = ["English", "Spanish", "French", "German", "Japanese", "Korean", "Chinese (Mandarin)", "Hindi", "Arabic", "Other"]

        title_val = existing.get('title', '')
        type_idx = ptypes.index(existing['project_type']) if existing.get('project_type') in ptypes else 0
        raw_story_val = existing.get('raw_story', '')
        genre_idx = genres.index(existing['genre']) if existing.get('genre') in genres else 7
        tone_idx = tones.index(existing['tone']) if existing.get('tone') in tones else 1
        vis_idx = vs.index(existing['visual_style']) if existing.get('visual_style') in vs else 0
        fmt_idx = -2  # Feature Film default fallback
        fmts_ = fmts
        try:
            fmt_idx = fmts.index(existing['target_format'])if existing.get('target_format') in fmts else 2
        except ValueError:
            fmt_idx = 2
        lang_idx = langs.index(existing['language']) if existing.get('language') in langs else 0
        style_refs = existing.get('style_references', '')
        things_avoid = existing.get('things_to_avoid', '')
        web_research = bool(existing.get('allow_web_research', False))
    else:
        ptypes = [
            "Movie / Short Film", "Single Episode", "Anime Episode",
            "Comic / Graphic Novel", "Manga/Webtoon", "Book / Novel",
            "Illustrated Storybook", "Audio Drama", "Game / Visual Novel"
        ]
        genres = ["Horror", "Thriller", "Romance", "Sci-fi", "Fantasy", "Mystery", "Comedy", "Drama", "Historical", "Supernatural", "Mythological", "Action", "Slice of Life", "Children", "Custom"]
        tones = ["Dark", "Emotional", "Funny", "Poetic", "Cinematic", "Gritty", "Dreamlike", "Fast-paced", "Slow-burn", "Custom"]
        vs = ["Photorealistic", "Stylized", "Animated", "Noir", "Impressionist", "Minimalist", "Surreal", "Custom"]
        fmts_ = [
            "Short Film (under 10 min)", "Short Film (10-30 min)",
            "Feature Film (90-120 min)", "Limited Series (6 episodes)",
            "Pilot Episode", "Web Series", "Music Video", "Custom"
        ]
        langs = ["English", "Spanish", "French", "German", "Japanese", "Korean", "Chinese (Mandarin)", "Hindi", "Arabic", "Other"]

        title_val = ''
        type_idx = 0
        raw_story_val = ''
        genre_idx = 7
        tone_idx = 1
        vis_idx = 0
        fmt_idx = 2
        lang_idx = 0
        style_refs = ''
        things_avoid = ''
        web_research = False

    st.header("Project Info")
    c1, c2 = st.columns(2)
    with c1:
        title_val = st.text_input("Project Title / Story Heading", value=title_val or '')
    with c2:
        type_sel = st.selectbox("Project Type", ptypes, index=type_idx)

    v1_types = ["Movie / Short Film", "Comic / Graphic Novel", "Book / Novel"]
    if type_sel not in v1_types:
        st.warning(f"'{type_sel}' is planned for a future version. Saving intake and continuing with limited support.")

    st.divider()
    st.subheader("Story Details")

    c3, c4, c5 = st.columns(3)
    with c3:
        genre_sel = st.selectbox("Genre", genres, index=genre_idx)
    with c4:
        tone_sel = st.selectbox("Tone", tones, index=tone_idx)
    with c5:
        vis_sel = st.selectbox("Visual Style", vs, index=vis_idx)

    fmt_sel = st.selectbox("Target Format/Duration", fmts_, index=fmt_idx)
    lang_sel = st.selectbox("Language", langs, index=lang_idx)
    web_research_flag = st.checkbox("Allow web research for genre/style inspiration when available", value=web_research)

    st.divider()
    st.subheader("Raw Story Idea")
    raw_story_val = st.text_area(
        "Your raw story idea (describe the core concept, characters, plot in any format)",
        value=raw_story_val or '', height=150
    )

    st.divider()
    st.subheader("Additional Notes")
    r1, r2 = st.columns(2)
    with r1:
        style_refs = st.text_area("Style/Reference Notes", value=style_refs or '', height=60, 
                                   placeholder="e.g. Cinematic lighting like Blade Runner")
    with r2:
        things_avoid = st.text_area("Things to Avoid", value=things_avoid or '', height=60,
                                     placeholder="e.g. Overly comedic moments in dramatic scenes")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save Intake", type="primary"):
            _save_data(title_val or f"Untitled ({time.strftime('%H-%M')})", type_sel, raw_story_val, 
                       genre_sel, tone_sel, vis_sel, fmt_sel, lang_sel, web_research_flag, style_refs, things_avoid)

    with col2:
        if st.button("⬇ Next: Story Expansion →", type="primary"):
            _save_data(title_val or f"Untitled ({time.strftime('%H-%M')})", type_sel, raw_story_val, 
                       genre_sel, tone_sel, vis_sel, fmt_sel, lang_sel, web_research_flag, style_refs, things_avoid)
            st.switch_page("pages/01_story_expansion.py")


def _save_data(title, project_type, raw_story, genre, tone, visual_style, target_format, language, allow_web, style_refs, things_avoid):
    ensure_project_dirs()

    save_data = {
        'project_id': f"mooV_{int(time.time()):X}",
        'title': title,
        'project_type': project_type,
        'raw_story': raw_story,
        'genre': genre,
        'tone': tone,
        'visual_style': visual_style,
        'target_format': target_format,
        'language': language,
        'style_references': style_refs,
        'things_to_avoid': things_avoid,
        'allow_web_research': allow_web,
    }

    save_json(project_path("project_meta.json"), save_data)
    save_json(project_path("intake", "intake.json"), save_data)
    st.success("✅ Intake saved successfully!")


if __name__ == "__main__":
    main()
