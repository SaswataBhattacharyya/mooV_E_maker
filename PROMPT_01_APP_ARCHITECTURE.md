# PROMPT_01_APP_ARCHITECTURE.md

## Goal

Build the first working architecture for a local Streamlit + Ollama app called:

```text
mooV-E Studio
```

Product description:

```text
A story-to-format builder for movies, comics, anime, episodes, books, audio dramas, and visual novels.
```

The app should use:

```text
One common pipeline + format-specific workspaces
```

Do not build separate full apps for movie, comic, book, anime, audio, and game formats. Build one shared story-development pipeline, then switch the structure and unit workspace behavior based on the selected project type.

The user controls the workflow step by step. This is not an autonomous agent project.

## Hard boundaries

This project is:

- a Streamlit app
- a local Ollama app
- a JSON/text artifact generator
- a modular page-based UI
- a local file-based project state workflow
- a deterministic user-triggered generation/revision tool

This project is not:

- Hermes Agent
- ComfyUI
- Node/React frontend
- web backend
- agent console
- model downloader UI
- autonomous agent swarm
- GPU-only application

Do not copy Hermes, ComfyUI, Node.js frontend, custom-node, website server, agent-console, or mandatory NVIDIA GPU logic from reference files.

## Core architecture

Use this page flow:

```text
Page 0: Project Intake
Page 1: Story Expansion
Page 2: Characters
Page 3: World / Style Bible
Page 4: Structure Builder
Page 5: Unit Workspace
Page 6: Review / Continuity
Page 7: Export
```

The most important architectural change is:

```text
Page 5: Unit Workspace
```

Do not create separate full pages for dialogue, backgrounds, camera, audio, props, costumes, and storyboard. Instead, open one selected unit and show all relevant blocks for that unit.

Examples:

```text
Movie        -> one scene workspace
Comic        -> one chapter/page/panel workspace
Book         -> one chapter/section workspace
Anime        -> one scene/cut workspace
Audio drama  -> one scene/sound workspace
Game story   -> one node/choice workspace
```

This keeps Ollama context small, makes revision easier, and avoids giant pages that try to display an entire project at once.

## Version plan

Do not build every format fully in v1.

### Version 1

Build the shared architecture and support:

```text
Movie / Short Film
Comic / Graphic Novel
Book / Novel
```

Pages required in v1:

```text
Project Intake
Story Expansion
Characters
World / Style Bible
Structure Builder
Unit Workspace
Review / Continuity placeholder
Export
```

### Version 2

Add:

```text
Single Episode
Anime Episode
Manga / Webtoon
Illustrated Storybook
Audio Drama
```

### Version 3

Add:

```text
Game / Visual Novel
Web research module
Advanced continuity checker
Image prompt export
```

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
    01_story_expansion.py
    02_characters.py
    03_world_style_bible.py
    04_structure_builder.py
    05_unit_workspace.py
    06_review_continuity.py
    07_export.py

  core/
    __init__.py
    constants.py
    ollama_client.py
    state_manager.py
    schemas.py
    prompt_templates.py
    validators.py
    revision_engine.py
    structure_engine.py
    unit_engine.py
    continuity_engine.py
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

Do not add heavy dependencies unless the app imports and uses them.

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

`OLLAMA_STORY_MODEL` is used for creative generation, revision, summarization, and continuity checking.

`OLLAMA_CODER_MODEL` is optional and reserved for future code/debug helper features. The main app must work even if it is empty.

## Project types

The Page 0 project type dropdown should include:

```text
Movie / Short Film
Single Episode
Anime Episode
Comic / Graphic Novel
Manga / Webtoon
Book / Novel
Illustrated Storybook
Audio Drama
Game / Visual Novel
```

In v1, only these should be fully active:

```text
Movie / Short Film
Comic / Graphic Novel
Book / Novel
```

For other types, allow the user to select them, save the intake, and show a clear message that full structure/workspace support is planned for a later version.

## Format hierarchies

Use stable IDs everywhere.

### Movie / Short Film

Hierarchy:

```text
Movie
  Act
    Scene
      Subscene / Beat
        Shot
```

Flow:

```text
Story idea
-> expanded story
-> characters
-> world/style bible
-> act structure
-> scene list
-> scene workspace
-> final screenplay + production bible
```

Scene workspace blocks:

```text
Scene summary
Subscenes / beats
Characters present
Dialogue
Action / blocking
Background / location
Props
Costume / makeup
Camera
Lighting
Sound effects
Music
VFX/SFX
Storyboard prompts
Continuity notes
```

### Single Episode

Hierarchy:

```text
Episode
  Teaser / Act
    Scene
      Beat
```

Extra fields:

```text
Cold open
A-plot
B-plot
C-plot
Cliffhanger
Episode theme
Continuity with previous/future episodes
```

This is v2.

### Anime Episode

Hierarchy:

```text
Anime Episode
  Sequence
    Scene
      Cut
        Keyframe / Pose
```

Anime-specific outputs:

```text
Character model sheet prompts
Background art prompts
Cut list
Key animation notes
Voice direction
Color script
Opening/ending music notes
```

This is v2.

### Comic / Graphic Novel

Hierarchy:

```text
Comic
  Chapter
    Page
      Panel
```

Flow:

```text
Story
-> characters
-> art/world style
-> chapter outline
-> page list per chapter
-> panel layout per page
-> captions/dialogue/SFX
-> image prompts
-> final comic script
```

Do not show all chapters on one page. Use:

```text
Select Chapter
Select Page
```

Then show panels for that page.

Comic page workspace:

```text
Chapter 1, Page 4

Panel 1
- panel size
- visual description
- characters visible
- pose/expression
- background
- caption
- speech bubbles
- SFX text
- image prompt

Panel 2
...
```

### Manga / Webtoon

Manga hierarchy:

```text
Chapter
  Page
    Panel
```

Webtoon hierarchy:

```text
Episode / Chapter
  Scroll section
    Panel
```

Webtoon-specific fields:

```text
Panel height
Vertical gap after panel
Slow reveal
Reaction panel
Silent panel
Impact panel
Cliffhanger panel
```

This is v2.

### Book / Novel

Hierarchy:

```text
Book
  Part, optional
    Chapter
      Section
        Beat
```

Flow:

```text
Story idea
-> expanded plot
-> themes
-> characters
-> world bible
-> book outline
-> chapter outline
-> chapter workspace
-> section-by-section prose
-> final manuscript
```

For books, do not generate a whole long chapter in one call. Use:

```text
Chapter outline
-> beat list
-> generate section 1
-> generate section 2
-> generate section 3
-> merge chapter
```

Chapter workspace:

```text
Chapter summary
Chapter beats
POV
Setting
Characters present
Emotional arc
Section draft
Continuity notes
```

### Illustrated Storybook

Hierarchy:

```text
Storybook
  Page
    Text block
    Illustration
```

Each page:

```text
Page text
Illustration description
Characters visible
Background
Image prompt
```

This is v2.

### Audio Drama / Podcast Episode

Hierarchy:

```text
Audio Episode
  Scene
    Dialogue block
    SFX cue
    Music cue
```

This format focuses less on visuals and more on:

```text
Voice
Sound effects
Ambience
Music
Silence
Narration
```

This is v2.

### Game / Visual Novel

Hierarchy:

```text
Game Story
  Route
    Scene Node
      Choice
        Consequence
```

This is v3.

## State structure

Save project data under:

```text
project_state/
  project_meta.json

  intake/
    intake.json

  story/
    expanded_story.json
    story_summary.json

  characters/
    characters_index.json
    char_001.json
    char_002.json

  world/
    world_bible.json
    style_bible.json
    locations.json

  structure/
    structure_index.json

  units/
    movie/
      scene_001.json
      scene_002.json

    comic/
      chapter_001/
        chapter_001.json
        page_001.json
        page_002.json

    book/
      chapter_001/
        outline.json
        section_001.txt
        section_002.txt

    anime/
      scene_001/
        scene_001.json
        cut_001.json

  review/
    continuity_report.json

  exports/
    final_project_bible.json
    screenplay.txt
    comic_script.txt
    manuscript.txt
```

The app should write export files to both `project_state/exports/` and the root `exports/` folder when practical.

## Stable ID rules

Use stable IDs:

```text
char_001
scene_001
scene_001_sub_001
scene_001_shot_001
chapter_001
page_001
panel_001
section_001
location_001
prop_001
```

Rules:

- Do not reuse a deleted ID in the same project.
- Do not rename IDs during ordinary revisions.
- Keep a `position` integer on list items so the UI can reorder and insert items without changing stable IDs.
- Store `status` on list items where useful: `draft`, `approved`, `needs_revision`, `deleted`.
- Prefer soft delete for major story objects so continuity repair can still understand what changed.

## List editing and coherence repair

Early pages must give the user short, editable lists before detailed generation.

The user must be able to:

- add a character
- delete a character
- insert a character between existing characters
- add an act/chapter/scene/page/section
- delete an act/chapter/scene/page/section
- insert an act/chapter/scene/page/section at the start, middle, or end
- reorder items where the format needs it
- edit short descriptions before full detail generation

This is required because the user needs to visualize and approve the project shape before expensive long generation.

### Character list

Page 2 should generate a character index first, not full character details.

Each list row should show:

```text
Character ID
Name
Role
Short description / purpose
Appears in units, if known
Status
```

The UI should provide:

```text
Add Character
Delete Character
Insert Character
Edit Short Description
Save Character List
Repair Story Coherence
Generate / Regenerate Details
```

Deleting a character must not blindly remove files and leave references broken. It should:

1. mark the character as deleted or remove it from active index
2. find linked references in story summary, structure, units, dialogue, and prompts
3. call the LLM with compact context to repair affected summaries and lists
4. update only affected files
5. create a short change note in `project_state/review/change_log.json`

### Structure lists

Page 4 should generate a short structure index before detailed unit generation.

For movies, show:

```text
Acts
Scenes per act
Short scene descriptions
Primary characters
Scene purpose
Status
```

For comics, show:

```text
Chapters
Pages per chapter
Short page descriptions
Panel count target
Page purpose
Status
```

For books, show:

```text
Parts, optional
Chapters
Sections per chapter
Short chapter/section descriptions
POV
Chapter purpose
Status
```

The UI should provide:

```text
Add
Delete
Insert Before
Insert After
Move Up
Move Down
Edit Short Description
Save Structure
Repair Story Coherence
Generate / Regenerate Selected Unit
```

Deleting or inserting a structure item must trigger a focused coherence repair option. Do not regenerate the whole project automatically.

Coherence repair should use small context:

```text
story summary
affected list before change
affected list after change
affected neighboring items
linked characters
user instruction
schema
```

It should update:

```text
story_summary.json, if needed
structure_index.json
only affected unit files
continuity notes
change_log.json
```

Do not overwrite unrelated units.

## Context management

Never send the whole project to Ollama after the initial story stage.

Use small focused context:

```text
global story summary
current object being generated or revised
relevant linked IDs
neighboring objects, if needed
user instruction
output schema
```

Examples:

For revising one character:

```text
story summary
current character JSON
revision instruction
schema
instruction: "Only revise this character."
```

For deleting one character:

```text
story summary
character index before deletion
character index after deletion
deleted character summary
affected linked units
schema
instruction: "Repair continuity only for affected summaries and references."
```

For generating dialogue for one movie scene:

```text
story summary
scene JSON
only characters present in that scene
character speech styles
schema
```

For checking continuity:

```text
run scene-by-scene, chapter-by-chapter, or page-by-page
summarize findings afterward
```

## Streaming behavior

Ollama output should stream into Streamlit for text generation.

For structured JSON:

1. collect the full streamed response
2. parse JSON
3. validate it
4. save it
5. if JSON parsing fails, attempt one repair call

The repair prompt must say:

```text
Return valid JSON only. No markdown. No commentary.
```

## `config.py`

Create a central config module exposing:

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

Load `.env` values from `config/movie_builder.local.env` using `python-dotenv`.

## `core/constants.py`

Define shared constants:

```python
SUPPORTED_PROJECT_TYPES_V1 = [
    "Movie / Short Film",
    "Comic / Graphic Novel",
    "Book / Novel",
]

PROJECT_TYPES = [
    "Movie / Short Film",
    "Single Episode",
    "Anime Episode",
    "Comic / Graphic Novel",
    "Manga / Webtoon",
    "Book / Novel",
    "Illustrated Storybook",
    "Audio Drama",
    "Game / Visual Novel",
]
```

Also define genre, tone, language, target length, and style-reference dropdown values.

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
insert_position(items: list[dict], new_item: dict, index: int) -> list[dict]
normalize_positions(items: list[dict]) -> list[dict]
append_change_log(entry: dict) -> None
```

Rules:

- Create parent folders automatically.
- Write JSON with UTF-8 and indentation.
- Never crash if a non-existing optional file is loaded; return default.
- Do not silently ignore JSON parse errors; show a useful exception.
- Do not overwrite unrelated files when revising one block.

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
- If parsing fails, call `repair_json` once.
- JSON repair prompt must say: "Return valid JSON only. No markdown. No commentary."

## `core/schemas.py`

Create Pydantic models or JSON schema dictionaries for the shared objects and v1 format-specific objects.

### Intake schema

```json
{
  "project_id": "string",
  "title": "string",
  "project_type": "Movie / Short Film",
  "raw_story": "string",
  "genre": "string",
  "custom_genre": "string",
  "tone": "string",
  "custom_tone": "string",
  "language": "string",
  "target_length": "string",
  "style_references": "string",
  "things_to_avoid": "string",
  "allow_web_research": false
}
```

### Expanded story schema

```json
{
  "project_id": "string",
  "title": "string",
  "project_type": "string",
  "genre": "string",
  "logline": "string",
  "short_synopsis": "string",
  "expanded_story": "string",
  "themes": ["string"],
  "ending": "string",
  "story_summary_for_context": "string"
}
```

### Character index schema

```json
{
  "characters": [
    {
      "character_id": "char_001",
      "position": 1,
      "name": "string",
      "role": "protagonist / antagonist / supporting / minor",
      "short_description": "string",
      "story_purpose": "string",
      "appears_in_units": [],
      "status": "draft"
    }
  ]
}
```

### Character detail schema

Use format-specific fields where relevant.

```json
{
  "character_id": "char_001",
  "name": "string",
  "role": "string",
  "age_range": "string",
  "gender_presentation": "string",
  "personality": "string",
  "backstory": "string",
  "motivation": "string",
  "fear": "string",
  "arc": "string",
  "speech_style": "string",
  "physical_description": "string",
  "costume": "string",
  "expression_notes": "string",
  "pose_notes": "string",
  "visual_prompt": "string",
  "book_voice": "string",
  "inner_conflict": "string",
  "pov_style": "string",
  "audio_voice_profile": "string",
  "accent": "string",
  "pace": "string",
  "emotion_range": "string",
  "summary_for_context": "string"
}
```

### World / style bible schema

```json
{
  "world_rules": ["string"],
  "locations": [
    {
      "location_id": "location_001",
      "name": "string",
      "short_description": "string",
      "visual_notes": "string",
      "story_use": "string"
    }
  ],
  "visual_style": "string",
  "color_palette": ["string"],
  "mood": "string",
  "genre_conventions": ["string"],
  "reference_style_notes": "string",
  "narrative_voice": "string",
  "prose_style": "string",
  "chapter_rhythm": "string",
  "art_style": "string",
  "linework": "string",
  "panel_or_cut_style": "string",
  "color_style": "string"
}
```

### Structure index schema

Use one `structure_index.json` with a `project_type` and a format-specific `items` tree.

Movie example:

```json
{
  "project_type": "Movie / Short Film",
  "items": [
    {
      "act_id": "act_001",
      "position": 1,
      "title": "Act 1",
      "short_description": "string",
      "scenes": [
        {
          "scene_id": "scene_001",
          "position": 1,
          "title": "string",
          "short_description": "string",
          "scene_purpose": "string",
          "primary_characters": ["char_001"],
          "status": "draft"
        }
      ]
    }
  ]
}
```

Comic example:

```json
{
  "project_type": "Comic / Graphic Novel",
  "items": [
    {
      "chapter_id": "chapter_001",
      "position": 1,
      "title": "string",
      "short_description": "string",
      "pages": [
        {
          "page_id": "page_001",
          "position": 1,
          "short_description": "string",
          "panel_count_target": 5,
          "page_purpose": "string",
          "status": "draft"
        }
      ]
    }
  ]
}
```

Book example:

```json
{
  "project_type": "Book / Novel",
  "items": [
    {
      "chapter_id": "chapter_001",
      "position": 1,
      "title": "string",
      "short_description": "string",
      "pov": "string",
      "chapter_purpose": "string",
      "sections": [
        {
          "section_id": "section_001",
          "position": 1,
          "short_description": "string",
          "beat_purpose": "string",
          "status": "draft"
        }
      ]
    }
  ]
}
```

## `core/prompt_templates.py`

Create prompt builder functions.

Required:

```python
build_story_generation_prompt(project_intake: dict) -> str
build_story_revision_prompt(current_story: dict, revision_instruction: str) -> str
build_story_summary_prompt(expanded_story: dict) -> str
build_character_index_prompt(story_summary: dict, project_type: str) -> str
build_character_detail_prompt(story_summary: dict, character_index_item: dict, project_type: str) -> str
build_character_revision_prompt(story_summary: dict, current_character: dict, revision_instruction: str) -> str
build_world_bible_prompt(story_summary: dict, characters_index: dict, project_type: str) -> str
build_structure_index_prompt(story_summary: dict, characters_index: dict, world_bible: dict, project_type: str) -> str
build_structure_repair_prompt(context: dict, changed_item: dict, change_type: str) -> str
build_character_delete_repair_prompt(context: dict, deleted_character: dict) -> str
build_unit_generation_prompt(context: dict, selected_unit: dict, project_type: str) -> str
build_unit_block_revision_prompt(context: dict, selected_unit: dict, block_name: str, revision_instruction: str) -> str
```

Prompt rules:

- Include compact context only.
- Always specify the expected JSON schema in the prompt.
- Always say: "Return valid JSON only. No markdown. No commentary."
- Revision prompts must preserve unchanged parts.
- Single-character revision must say: "Only revise this one character. Do not modify any other character."
- Unit block revision must say: "Only revise this block in the selected unit. Preserve all other blocks unless a tiny reference update is required."
- Deletion/insert repair prompts must not ask the model to regenerate the whole story.

## `core/chunking.py`

Create helper functions that build small context packets.

Implement:

```python
get_story_context() -> dict
get_character_context(character_id: str) -> dict
get_structure_context() -> dict
get_selected_unit_context(unit_id: str) -> dict
get_neighboring_units_context(unit_id: str) -> dict
get_deletion_repair_context(object_type: str, object_id: str) -> dict
```

## `core/validators.py`

Implement:

```python
validate_required_keys(data: dict, required_keys: list[str]) -> None
ensure_stable_id(old_id: str, new_data: dict, key: str) -> None
validate_project_type(project_type: str) -> None
validate_supported_v1_project_type(project_type: str) -> None
validate_positions(items: list[dict]) -> None
validate_no_active_references_to_deleted_id(deleted_id: str) -> None
```

## `core/revision_engine.py`

Implement:

```python
revise_story(revision_instruction: str) -> dict
revise_character(character_id: str, revision_instruction: str) -> dict
revise_unit_block(unit_id: str, block_name: str, revision_instruction: str) -> dict
repair_after_character_delete(character_id: str) -> dict
repair_after_structure_change(change: dict) -> dict
```

These should:

- load current JSON
- build focused revision/repair prompts
- call `generate_json`
- validate stable IDs where relevant
- save only affected files
- append to `project_state/review/change_log.json`
- return updated JSON

## `core/structure_engine.py`

Implement helpers for list editing:

```python
load_structure_index() -> dict
save_structure_index(structure: dict) -> None
add_structure_item(parent_id: str | None, item: dict, index: int | None = None) -> dict
delete_structure_item(item_id: str, soft_delete: bool = True) -> dict
move_structure_item(item_id: str, direction: str) -> dict
update_structure_item_description(item_id: str, short_description: str) -> dict
find_structure_item(item_id: str) -> dict | None
```

Deleting or inserting an item should not automatically regenerate all downstream units. It should mark affected units as `needs_revision` and offer a `Repair Story Coherence` button.

## `core/unit_engine.py`

Implement helpers for selected unit files:

```python
get_unit_options(project_type: str, structure_index: dict) -> dict
load_unit(project_type: str, unit_id: str) -> dict
save_unit(project_type: str, unit_id: str, data: dict) -> None
generate_or_regenerate_unit(project_type: str, unit_id: str) -> dict
revise_unit_block(project_type: str, unit_id: str, block_name: str, instruction: str) -> dict
```

The unit engine decides where files are saved:

```text
Movie scene -> project_state/units/movie/scene_001.json
Comic page  -> project_state/units/comic/chapter_001/page_001.json
Book section -> project_state/units/book/chapter_001/section_001.txt or section_001.json
```

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

## Streamlit navigation

Use Streamlit multipage support.

`app.py` should introduce `mooV-E Studio` and tell the user to start with `pages/00_project_intake.py`.

If Streamlit page switching is available, use:

```python
st.switch_page("pages/01_story_expansion.py")
```

If not available, show a clear instruction.

## Page 0: Project Intake

File:

```text
pages/00_project_intake.py
```

Title:

```text
mooV-E Studio: Project Intake
```

Fields:

```text
Project title / story heading
Project type
Genre
Custom genre
Tone
Custom tone
Language
Target length
Raw story input
Style references
Things to avoid
Allow web research? Yes / No
```

Project type options:

```text
Movie / Short Film
Single Episode
Anime Episode
Comic / Graphic Novel
Manga / Webtoon
Book / Novel
Illustrated Storybook
Audio Drama
Game / Visual Novel
```

Suggested genres:

```text
Horror
Thriller
Romance
Sci-fi
Fantasy
Mystery
Comedy
Drama
Historical
Supernatural
Mythological
Action
Slice of Life
Children
Custom
```

Suggested tones:

```text
Dark
Emotional
Funny
Poetic
Cinematic
Gritty
Dreamlike
Fast-paced
Slow-burn
Custom
```

Behavior:

- This page should not generate the expanded story.
- It only saves intake.
- `Save Intake` saves:
  - `project_state/project_meta.json`
  - `project_state/intake/intake.json`
- A `Next: Story Expansion` button at the top should save current intake and go to Page 1.
- If web research is checked and unavailable, show the placeholder message and continue.

## Page 1: Story Expansion

File:

```text
pages/01_story_expansion.py
```

Generates:

```text
Logline
Short synopsis
Expanded story
Themes
Ending
Story summary for context
```

Behavior:

- Load `project_state/intake/intake.json`.
- If missing, warn user to complete Project Intake.
- Show current intake summary.
- Button: `Generate Story`.
- Stream generated output where practical.
- Save:
  - `project_state/story/expanded_story.json`
  - `project_state/story/story_summary.json`
- The generated story should be editable.

Revision UI:

```text
Instructions for story revision
Revise Story
```

Revision updates only story files.

Top of page:

```text
Next: Characters
```

## Page 2: Characters

File:

```text
pages/02_characters.py
```

Behavior:

- Load story summary.
- If missing, warn user to complete story generation.
- Button: `Generate Character List`.
- Save:
  - `project_state/characters/characters_index.json`

After index exists, show the character list before details.

Each row should include:

```text
Character ID
Name
Role
Short description
Story purpose
Appears in units
Status
```

User actions:

```text
Add Character
Delete Character
Insert Character
Move Up
Move Down
Edit Short Description
Save Character List
Repair Story Coherence
Generate / Regenerate Details
```

Character details:

- Generate details separately, one model call per character.
- Save:
  - `project_state/characters/char_001.json`
  - etc.
- Show format-specific fields.
- Include a revision instruction box unique to each character.
- `Revise <character name>` updates only that character file.

For visual formats include:

```text
Physical description
Costume
Expression
Pose
Visual prompt
```

For book include:

```text
Voice
Arc
Inner conflict
POV style
```

For audio include:

```text
Voice profile
Accent
Pace
Emotion range
```

Top of page:

```text
Next: World / Style Bible
```

## Page 3: World / Style Bible

File:

```text
pages/03_world_style_bible.py
```

Generates:

```text
World rules
Locations
Visual style
Color palette
Mood
Genre conventions
Reference style notes
```

For book:

```text
Narrative voice
Prose style
Chapter rhythm
```

For comic/anime:

```text
Art style
Linework
Panel/cut style
Color style
```

Save:

```text
project_state/world/world_bible.json
project_state/world/style_bible.json
project_state/world/locations.json
```

Locations should be shown as a short editable list before any detailed unit generation.

Top of page:

```text
Next: Structure Builder
```

## Page 4: Structure Builder

File:

```text
pages/04_structure_builder.py
```

This page changes by project type.

```text
Movie -> acts and scenes
Comic -> chapters, pages, panels
Book -> parts, chapters, sections
Anime -> sequences, scenes, cuts
Audio -> scenes and sound cue structure
Game -> routes and scene nodes
```

In v1, fully support:

```text
Movie / Short Film
Comic / Graphic Novel
Book / Novel
```

Behavior:

- Generate a short structure index first.
- Do not generate full scene/page/chapter details yet.
- Save:
  - `project_state/structure/structure_index.json`
- Show the structure as an editable list/tree.

The user must be able to:

```text
Add item
Delete item
Insert item at start
Insert item before selected item
Insert item after selected item
Append item at end
Move item up/down
Edit short description
Save structure
Repair Story Coherence
Generate / Regenerate Selected Unit
```

Important:

- The list should contain enough description for the user to visualize the project.
- The descriptions should be short, not elaborate.
- Adding/deleting/reordering should not automatically regenerate the whole project.
- Mark affected units as `needs_revision`.
- Offer repair after structural edits.

Top of page:

```text
Next: Unit Workspace
```

## Page 5: Unit Workspace

File:

```text
pages/05_unit_workspace.py
```

This is the most important page.

For movie:

```text
Select Act
Select Scene
```

For comic:

```text
Select Chapter
Select Page
```

For book:

```text
Select Chapter
Select Section
```

For anime:

```text
Select Scene
Select Cut
```

Then show all details for that selected unit.

### Movie scene workspace

Blocks:

```text
Scene summary
Subscenes / beats
Characters present
Dialogue
Action / blocking
Background / location
Props
Costume / makeup
Camera
Lighting
Sound effects
Music
VFX/SFX
Storyboard prompts
Continuity notes
```

Each block should have:

```text
User instruction box
Revise this block button
```

### Comic page workspace

Show selected chapter and page.

For each panel:

```text
Panel size
Visual description
Characters visible
Pose/expression
Background
Caption
Speech bubbles
SFX text
Image prompt
```

Each panel and page-level block should have:

```text
User instruction box
Revise this block button
```

### Book section workspace

Show selected chapter and section.

Blocks:

```text
Chapter summary
Chapter beats
POV
Setting
Characters present
Emotional arc
Section draft
Continuity notes
```

Books must generate prose section by section. Do not generate a full long chapter in one call.

Each block should have:

```text
User instruction box
Revise this block button
```

## Page 6: Review / Continuity

File:

```text
pages/06_review_continuity.py
```

In v1, this can be a focused continuity checker.

Behavior:

- Let the user run checks by selected scope:
  - current unit
  - changed units
  - whole structure, chunked
- Do not send the entire project in one prompt.
- Save:
  - `project_state/review/continuity_report.json`

Continuity output:

```text
Issue ID
Severity
Affected IDs
Problem
Suggested fix
Status
```

## Page 7: Export

File:

```text
pages/07_export.py
```

Export depends on project type.

For movie:

```text
final_project_bible.json
screenplay.txt
production_bible.txt
```

For comic:

```text
final_project_bible.json
comic_script.txt
image_prompts.txt
```

For book:

```text
final_project_bible.json
manuscript.txt
chapter_outline.txt
```

Save under:

```text
project_state/exports/
exports/
```

## Implementation order

Build in this order:

1. folder structure
2. requirements
3. config and constants
4. state manager
5. Ollama client
6. schemas
7. prompt templates
8. Page 0 Project Intake
9. Page 1 Story Expansion
10. Page 2 Characters with editable character index
11. Page 3 World / Style Bible
12. Page 4 Structure Builder with editable structure index
13. Page 5 Unit Workspace for Movie / Comic / Book
14. setup/run scripts in the separate setup prompt
15. Page 6 Review / Continuity
16. Page 7 Export

## Setup script note

Setup script details belong in `PROMPT_02_SETUP_SCRIPT.md`.

This architecture prompt should only require that the app is compatible with:

```text
setup_and_run.sh
run_movie_builder.sh
requirements.txt
config/movie_builder.local.env
```

The setup script should not require GPU, CUDA, NVIDIA drivers, Node.js, ComfyUI, Hermes, or a website backend.
