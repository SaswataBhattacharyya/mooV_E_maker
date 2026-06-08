# mooV-E Studio — Movie Builder

A local Streamlit + Ollama step-by-step movie preproduction builder.

Turn a raw story idea into structured movie-development artifacts: characters, scenes, backgrounds, props, costumes, VFX/SFX, dialogues, camera/lighting notes, shot lists, storyboard prompts, audio design, continuity checks, and final JSON/text exports.

---

## Features

- **8-page guided workflow** — Project Intake, Story Builder, Character Builder, World/Style Bible, Structure Builder, Unit Workspace, Review/Continuity, Export
- **Local AI** — all generation runs via Ollama; no cloud APIs or API keys required
- **Multi-format support (v1)** — Movie / Short Film, Comic / Graphic Novel, Book / Novel
- **Modular pages** — each page is an independent Streamlit page (`pages/`), easy to extend
- **File-based state** — project data saved as JSON under `project_state/`; no database dependency
- **Context-aware generation** — uses small focused context packets, never sends the whole project to the LLM
- **Revision workflow** — revise any single character, scene, page, or block without regenerating everything
- **Stable IDs** — all items get persistent IDs (`char_001`, `scene_001`) that survive edits and revisions
- **Change log** — every edit is tracked in `project_state/review/change_log.json`
- **Continuity checker** — cross-reference characters, structure, and units to catch inconsistency issues

---

## Workflow Pages

| # | Page | What it does |
|---|------|-------------|
| 0 | Project Intake | Enter title, genre, tone, visual style, raw story idea |
| 1 | Story Builder | Generate logline, synopsis, expanded story; revise iteratively |
| 2 | Character Builder | Generate character index + per-character profiles; revise individually |
| 3 | World / Style Bible | Define world rules, locations, visual style, color palette, mood |
| 4 | Structure Builder | Plan acts/chapters/scenes with editable tree (add, delete, reorder) |
| 5 | Unit Workspace | Detail individual units — scenes (movie), pages/panels (comic), sections (book) |
| 6 | Review / Continuity | Run consistency checks across characters, structure, and units |
| 7 | Export | Generate final project bible, screenplay/script/manuscript exports |

---

## Requirements

- **Python 3.11**
- **Ollama** installed and running (on `http://127.0.0.1:11434` by default)
- **Ollama models** — `qwen3.6:35b` (story/reasoning), optionally `qwen3-coder:30b` (code/debug)

No GPU required. No CUDA, NVIDIA drivers, PyTorch, or cloud services.

---

## Installation & Setup

### First-time setup (installs everything):

```bash
cd /root/mooV_E_maker/movie_builder
bash setup_and_run.sh
```

This script will:
1. Install system packages (apt)
2. Detect GPU (optional — continues if absent)
3. Install/start Ollama
4. Pull the selected AI models
5. Create a Python venv and install dependencies
6. Ask you to pick a Streamlit port
7. Write `config/movie_builder.local.env`
8. Launch Streamlit

### Runtime only (after initial setup):

```bash
cd /root/mooV_E_maker/movie_builder
bash run_movie_builder.sh
```

This checks that Ollama is running and starts the app — no package installs or model downloads.

---

## Project Structure

```
movie_builder/
├── app.py                    # Streamlit home page
├── config.py                 # Configuration loader (.env + os env vars)
├── requirements.txt          # Python dependencies (streamlit, ollama, pydantic, jsonschema, python-dotenv)
│
├── pages/                    # Streamlit multipage app (8 pages)
│   ├── 00_project_intake.py
│   ├── 01_story_expansion.py
│   ├── 02_characters.py
│   ├── 03_world_style_bible.py
│   ├── 04_structure_builder.py
│   ├── 05_unit_workspace.py
│   ├── 06_review_continuity.py
│   └── 07_export.py
│
├── core/                     # Application logic
│   ├── chunking.py           # Context packet builders for Ollama
│   ├── constants.py          # Project types, genres, tones, etc.
│   ├── continuity_engine.py  # Consistency checker
│   ├── ollama_client.py      # Ollama wrapper (generate/stream/repair)
│   ├── prompt_templates.py   # Prompt builders for every generation step
│   ├── revision_engine.py    # Story, character, unit revision functions
│   ├── schemas.py            # Pydantic models (intake, characters, scenes, etc.)
│   ├── state_manager.py      # Safe JSON/text I/O + stable ID generators
│   ├── structure_engine.py   # Add/delete/move/reorder structure items
│   ├── unit_engine.py        # Load/save/generate/unit revision for Movie/Comic/Book
│   ├── validators.py         # Input validation helpers
│   └── web_research.py       # Placeholder (optional, v3)
│
├── config/                   # Local env config
│   └── movie_builder.local.env
├── project_state/            # Project data (JSON)
├── exports/                  # Exported files
└── tests/                    # Test suite (76 tests, 100% pass rate)
    ├── conftest.py
    ├── test_chunking.py
    ├── test_config_constants.py
    ├── test_ollama_client.py
    ├── test_prompt_templates.py
    ├── test_schemas.py
    ├── test_state_manager.py
    ├── test_structure_engine.py
    └── test_validators.py
```

---

## Configuration

Environment variables (set in `config/movie_builder.local.env` or system env):

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API endpoint |
| `OLLAMA_STORY_MODEL` | `qwen3.6:35b` | Main creative/reasoning model |
| `OLLAMA_CODER_MODEL` | `qwen3-coder:30b` | Optional code/debug model (empty to skip) |
| `MOVIE_BUILDER_HOST` | `0.0.0.0` | Streamlit bind address |
| `MOVIE_BUILDER_PORT` | `8501` | Streamlit port |

---

## Running Tests

```bash
cd /root/mooV_E_maker/movie_builder
venv/bin/pytest tests/ -v
```

76 tests covering all core modules (config, constants, state manager, schemas, validators, Ollama client, prompt templates, chunking, structure engine). All pass 100%.

---

## Roadmap

### v1 (current)

- Movie / Short Film support
- Comic / Graphic Novel support
- Book / Novel support
- Continuity checking (by-unit)

### v2 (planned)

- Single Episode, Anime Episode, Manga/Webtoon, Illustrated Storybook, Audio Drama
- Full panel-level workspace for comics
- Web research integration

### v3 (planned)

- Game / Visual Novel support
- Advanced continuity checker
- Image prompt export for AI image generators
