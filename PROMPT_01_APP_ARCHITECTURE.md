# PROMPT_01_APP_ARCHITECTURE.md

## Goal

Build the first working version of a local Streamlit + Ollama app called `movie_builder`.

The app should guide a user step by step from a raw story idea into a structured movie bible.

This prompt covers the app architecture and the first functional pages:

1. Project Intake
2. Story Builder
3. Character Builder
4. placeholder pages for later steps

Do not implement the entire movie builder in one pass. Build a clean base that can be extended page by page.

## Important clarification

This is not an autonomous agent project. It is a deterministic step-by-step UI workflow.

The app may use Ollama models for generation and revision, but the user controls when each step runs.

## Required folder structure

Create this structure:

```text
movie_builder/
  app.py
  config.py
  requirements.txt
  AGENTS.md

  pages/
    00_project_intake.py
    01_story_builder.py
    02_character_builder.py
    03_scene_breakdown.py
    04_background_assets.py
    05_props_costumes_vfx.py
    06_dialogue_writer.py
    07_action_camera_lighting.py
    08_shotlist_storyboard.py
    09_audio_design.py
    10_continuity_checker.py
    11_export.py

  core/
    __init__.py
    ollama_client.py
    state_manager.py
    schemas.py
    prompt_templates.py
    validators.py
    revision_engine.py
    chunking.py
    web_research.py

  config/
    .gitkeep

  project_state/
    .gitkeep

  exports/
    .gitkeep
```

## Requirements

If `requirements.txt` does not exist, create:

```text
streamlit
ollama
pydantic
jsonschema
python-dotenv
```

Do not add heavy dependencies.

## Environment variables

Read these from `config/movie_builder.local.env` if present:

```bash
OLLAMA_HOST="http://127.0.0.1:11434"
OLLAMA_STORY_MODEL="qwen3.6:35b"
OLLAMA_CODER_MODEL="qwen3-coder:30b"
MOVIE_BUILDER_HOST="0.0.0.0"
MOVIE_BUILDER_PORT="8501"
```

Also allow normal environment variables to override defaults.

## `config.py`

Create a central config module.

It should expose:

```python
PROJECT_ROOT
PROJECT_STATE_DIR
EXPORTS_DIR
CONFIG_DIR
LOCAL_ENV_FILE
OLLAMA_HOST
OLLAMA_STORY_MODEL
OLLAMA_CODER_MODEL
MOVIE_BUILDER_HOST
MOVIE_BUILDER_PORT
```

It should load `.env` values from `config/movie_builder.local.env` using `python-dotenv`.

## `core/state_manager.py`

Implement safe JSON/text state functions:

```python
ensure_project_dirs() -> None
load_json(path: Path, default=None)
save_json(path: Path, data: dict | list) -> None
load_text(path: Path, default: str = "") -> str
save_text(path: Path, text: str) -> None
project_path(*parts: str) -> Path
export_path(*parts: str) -> Path
next_id(prefix: str, existing_ids: list[str]) -> str
```

Rules:

- Create parent folders automatically.
- Write JSON with UTF-8 and indentation.
- Never crash if a non-existing optional file is loaded; return default.
- Do not silently ignore JSON parse errors; show useful exception.

## `core/ollama_client.py`

Implement a small Ollama wrapper.

Required functions:

```python
is_ollama_ready() -> bool
list_models() -> list[str]
stream_generate(prompt: str, model: str | None = None, options: dict | None = None)
generate_text(prompt: str, model: str | None = None, options: dict | None = None) -> str
generate_json(prompt: str, schema: dict, model: str | None = None, options: dict | None = None) -> dict
repair_json(raw_text: str, schema: dict, model: str | None = None) -> dict
```

Behavior:

- Use `OLLAMA_STORY_MODEL` by default.
- Stream output for UI.
- For JSON generation, collect final text and parse JSON.
- If parsing fails, call `repair_json`.
- JSON repair prompt must say: "Return valid JSON only. No markdown. No commentary."

## `core/schemas.py`

Create Pydantic models or JSON schema dictionaries for:

### Project intake

```json
{
  "project_id": "string",
  "title": "string",
  "raw_story": "string",
  "genre": "string",
  "custom_genre": "string",
  "tone": "string",
  "visual_style": "string",
  "target_format": "string",
  "language": "string",
  "style_reference_notes": "string",
  "allow_web_research": false
}
```

### Expanded story

```json
{
  "project_id": "string",
  "title": "string",
  "genre": "string",
  "logline": "string",
  "short_synopsis": "string",
  "expanded_story": "string",
  "themes": ["string"],
  "tone": "string",
  "world_rules": ["string"],
  "main_conflict": "string",
  "ending": "string",
  "story_summary_for_context": "string"
}
```

### Character index

```json
{
  "characters": [
    {
      "character_id": "char_001",
      "name": "string",
      "role": "protagonist / antagonist / supporting / minor",
      "appears_in_scenes": [],
      "short_purpose": "string"
    }
  ]
}
```

### Character detail

```json
{
  "character_id": "char_001",
  "name": "string",
  "role": "string",
  "age_range": "string",
  "gender_presentation": "string",
  "physical_features": {
    "face": "string",
    "hair": "string",
    "skin": "string",
    "body_type": "string",
    "height_impression": "string",
    "distinctive_marks": "string"
  },
  "costume_style": "string",
  "personality": "string",
  "backstory": "string",
  "motivation": "string",
  "fear": "string",
  "arc": "string",
  "speech_style": "string",
  "visual_generation_prompt": "string",
  "negative_prompt": "string",
  "summary_for_context": "string"
}
```

## `core/prompt_templates.py`

Create prompt builder functions.

Required:

```python
build_story_generation_prompt(project_intake: dict) -> str
build_story_revision_prompt(current_story: dict, revision_instruction: str) -> str
build_story_summary_prompt(expanded_story: dict) -> str
build_character_index_prompt(story_summary: dict, expanded_story: dict | None = None) -> str
build_character_detail_prompt(story_summary: dict, character_index_item: dict) -> str
build_character_revision_prompt(story_summary: dict, current_character: dict, revision_instruction: str) -> str
```

Rules for prompts:

- Include compact context only.
- Always specify the expected JSON schema in the prompt.
- Always say: "Return valid JSON only. No markdown. No commentary."
- Revision prompts must preserve unchanged parts.
- Character revision must explicitly say: "Only revise this one character. Do not modify any other character."

## `core/chunking.py`

Create helper functions that build small context packets.

For now implement:

```python
get_story_context() -> dict
get_character_context(character_id: str) -> dict
```

Later pages will add scene-level context.

## `core/validators.py`

Implement:

```python
validate_required_keys(data: dict, required_keys: list[str]) -> None
ensure_stable_id(old_id: str, new_data: dict, key: str) -> None
```

## `core/revision_engine.py`

Implement:

```python
revise_story(revision_instruction: str) -> dict
revise_character(character_id: str, revision_instruction: str) -> dict
```

These should:

- load current JSON
- build the focused revision prompt
- call `generate_json`
- validate stable ID where relevant
- save updated JSON
- return updated JSON

## `core/web_research.py`

Create a placeholder optional module.

Do not make web search required.

Implement:

```python
def web_research_available() -> bool:
    return False

def research_style_or_genre(query: str) -> dict:
    return {
        "available": False,
        "message": "Web research is not configured yet. Continuing with local genre/style options."
    }
```

The UI can call this if the user checks the web-research box, but it must not fail if unavailable.

## Streamlit navigation

Use Streamlit multipage support.

`app.py` should be the landing page or redirect/instruct the user to start with `pages/00_project_intake.py`.

If Streamlit page switching is available, use:

```python
st.switch_page("pages/01_story_builder.py")
```

If not available, show a clear instruction or a link/button.

## Page 0: `pages/00_project_intake.py`

This is the first real user-facing page.

Title:

```text
Movie Builder: Project Intake
```

Fields:

1. Story heading/title
2. Raw story idea text area
3. Genre dropdown
4. Custom genre text input shown or used when genre is "Custom"
5. Tone dropdown
6. Visual style dropdown
7. Target format/duration dropdown
8. Language dropdown
9. Optional style/reference notes text area
10. Optional checkbox: "Use web research for genre/style inspiration when available"

Suggested genre dropdown:

```text
Horror
Ghost story
Thriller
Mystery
Romance
Drama
Comedy
Action
Adventure
Fantasy
Science fiction
Mythological
Historical
Crime
Slice of life
Children/family
Experimental
Custom
```

Suggested tone dropdown:

```text
Dark
Emotional
Poetic
Realistic
Surreal
Satirical
Suspenseful
Warm
Epic
Minimal
```

Suggested visual style dropdown:

```text
Realistic cinema
Indie film
Animated
Anime-inspired
Graphic novel
Dreamlike
Noir
Found footage
Mythic/fantasy
Indian regional cinema
Custom notes only
```

Suggested target format:

```text
Short film, 3-5 minutes
Short film, 5-10 minutes
Short film, 10-20 minutes
Feature outline
Episode outline
Scene test only
```

Behavior:

- `Save Intake` button saves:
  - `project_state/project_meta.json`
  - `project_state/story/story_input.json`
- A `Next: Generate Story` button at the top should save the current intake and go to Page 1.
- Do not generate the expanded story on this page.

## Page 1: `pages/01_story_builder.py`

Title:

```text
Step 1: Story Builder
```

Behavior:

- Load `project_state/story/story_input.json`.
- If missing, warn user to complete Project Intake.
- Show current intake summary.
- Button: `Generate Story`
- Stream generated text in UI if possible.
- Save final JSON to:
  - `project_state/story/story_expanded.json`
- Also create or update:
  - `project_state/story/story_summary.json`

The generated story should be editable in a text area.

Revision UI:

- text area: "Instructions for story revision"
- button: "Revise Story"
- Revision updates only story files.

Top of page:

- `Next: Characters` button.

## Page 2: `pages/02_character_builder.py`

Title:

```text
Step 2: Character Development
```

Behavior:

- Load story summary.
- If missing, warn user to complete story generation.
- Button: `Generate Character List`
- Save:
  - `project_state/characters/characters_index.json`

After index exists:

- For each character, provide a `Generate / Regenerate Details` button.
- Generate character details separately, one model call per character.
- Save:
  - `project_state/characters/char_001.json`
  - etc.

For every generated character:

- show character name
- show role
- show description fields
- show visual prompt
- revision instruction text area unique to that character
- button: `Revise <character name>`
- revision must update only that character file.

Top of page:

- `Next: Scene Breakdown` button.

## Placeholder pages

Create placeholder files for pages 3-11 with:

- title
- brief description
- "This page will be implemented in the next phase."
- checks for required previous JSON
- no generation yet

## Save/export after each page

Every successful generation or revision must save immediately.

## Important implementation rule

Do not hard-code absolute paths.

Everything must be relative to project root.

## Acceptance criteria

After this prompt is implemented:

1. `streamlit run app.py` starts.
2. User can enter title/story/genre in Project Intake.
3. Intake saves to JSON.
4. User can navigate to Story Builder.
5. Story can be generated via Ollama.
6. Story can be revised.
7. User can navigate to Character Builder.
8. Character list can be generated.
9. Each character detail can be generated separately.
10. Each character can be revised individually.
11. All outputs are saved as JSON files.
12. Missing Ollama or missing prior-step JSON shows clear UI warnings instead of crashes.
