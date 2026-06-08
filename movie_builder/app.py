import streamlit as st

st.set_page_config(page_title="mooV-E Studio", page_icon="🎬", layout="centered")

st.title("🎬 mooV-E Studio")
st.markdown("")
st.markdown("""
### Movie Builder — Story-to-Preproduction Pipeline

A step-by-step workflow tool for creative preproduction, powered by local LLMs.

**Workflow:**
1. **Project Intake** — Input your raw story idea
2. **Story Expansion** — Generate logline, synopsis, expanded story
3. **Characters** — Build character profiles
4. **World/Style Bible** — Define world rules and visual style
5. **Structure Builder** — Plan acts/chapters/scenes
6. **Unit Workspace** — Detail individual units (scenes, pages, sections)
7. **Review/Continuity** — Check consistency
8. **Export** — Export final artifacts

---

### Getting Started

Click the button below to begin with your Project Intake.
""")

st.markdown("")

from core.state_manager import load_json, project_path

# Check if there's existing data to resume
intake_data = load_json(project_path("intake", "intake.json"))
if intake_data and isinstance(intake_data, dict) and intake_data.get('title'):
    st.success(f"📂 Project **'{intake_data['title']}'** ready. Resume from where you left off!")

st.button("🚀 **Start Project Intake** →", type="primary", on_click=lambda: st.switch_page("pages/00_project_intake.py"))
