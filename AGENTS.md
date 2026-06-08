# AGENTS.md

## What this file is

`AGENTS.md` is not part of the Movie Builder app and it does not mean this project needs an autonomous agent.

It is a repository instruction file for Codex/coding assistants. Codex reads it before editing the repository so it keeps the same project rules across multiple prompts.

## Project name

Movie Builder

## Project type

A local Streamlit + Ollama step-by-step movie preproduction builder.

The product helps a user turn a raw story idea into structured movie-development artifacts:

1. project/story input
2. generated and revised story
3. characters
4. scene and subscene breakdown
5. background/location assets
6. props, costumes, makeup, set dressing, VFX/SFX assets
7. dialogues
8. action, blocking, camera, and lighting
9. shot list and storyboard/image prompts
10. audio design
11. continuity checks
12. final JSON/text exports

## Hard project boundaries

This project is:

- Streamlit app
- local Ollama backend
- JSON/text artifact generator
- step-by-step workflow
- modular page-based UI
- local file-based project state

This project is not:

- Hermes Agent
- ComfyUI
- Node/React frontend
- agent console
- website backend
- custom-node manager
- image/video model downloader
- GPU-only application
- autonomous agent swarm

Do not copy Hermes, ComfyUI, Node.js frontend, custom-node, model-download, website server, agent-console, or mandatory NVIDIA GPU logic from reference files.

## Reference files policy

If reference files are provided in `reference/`, use them only for patterns.

Allowed to reuse/adapt from reference scripts:

- root/sudo handling
- apt package install style
- Ollama installation
- Ollama startup and readiness checks
- interactive model selection
- pulling missing Ollama models
- env-file writing/loading
- port detection/killing pattern

Do not reuse/adapt:

- Hermes setup
- Hermes memory sync
- ComfyUI install
- ComfyUI model downloads
- custom node install
- Node.js install
- website/uvicorn server
- agent console
- mandatory GPU exit behavior

## Runtime model roles

The app should use these environment variables:

```bash
OLLAMA_HOST="http://127.0.0.1:11434"
OLLAMA_STORY_MODEL="qwen3.6:35b"
OLLAMA_CODER_MODEL="qwen3-coder:30b"
MOVIE_BUILDER_HOST="0.0.0.0"
MOVIE_BUILDER_PORT="8501"
```

`OLLAMA_STORY_MODEL` is used for creative generation, revision, summarization, and continuity checking.

`OLLAMA_CODER_MODEL` is optional and reserved for future code/debug helper features. The main app must work even if it is empty.

## UI workflow

The app must be page-based.

### Page 0: Project Intake

This is the first page the user sees.

Fields:

- Story heading/title
- Raw story idea text area
- Genre dropdown
- Optional custom genre field
- Tone dropdown
- Visual style dropdown
- Target format/duration dropdown
- Language dropdown
- Optional style/reference notes
- Optional checkbox: "Use web research for genre/style inspiration when available"

At the top of the page, include a `Next` button that goes to Page 1: Story Builder.

Page 0 should not generate the final expanded story. It should save the intake data to:

```text
project_state/project_meta.json
story/story_input.json
```

### Page 1: Story Builder

Generates the expanded story from Page 0.

Must include:

- Generate Story button
- streamed generation output
- editable generated story area
- revision instruction text area
- Revise Story button
- Next button at top

Save:

```text
project_state/story/story_expanded.json
project_state/story/story_summary.json
```

### Page 2: Character Builder

Generate character index first, then generate each character separately.

For every character:

- show name/title
- show generated description
- revision instruction box
- revise button for that character only

Save:

```text
project_state/characters/characters_index.json
project_state/characters/char_001.json
project_state/characters/char_002.json
...
```

### Page 3: Scene and Subscene Breakdown

Generate scene index and individual scene files.

Save:

```text
project_state/scenes/scene_index.json
project_state/scenes/scene_001.json
...
```

### Page 4 onward

Continue with modular pages:

- background assets
- props/costumes/VFX/SFX
- dialogues
- action/camera/lighting
- shot list/storyboard prompts
- audio design
- continuity check
- export

## Context management rule

Never send the whole project to Ollama after the initial story stage.

Use small focused context:

- global story summary
- current object being generated or revised
- relevant linked IDs
- user instruction
- output schema

Examples:

For revising one character, pass:

- story summary
- current character JSON
- revision instruction
- schema
- instruction: "Only revise this character."

For generating dialogue for one scene, pass:

- story summary
- scene JSON
- only characters present in that scene
- character speech styles
- schema

For checking continuity, run scene-by-scene or chunk-by-chunk and then summarize findings.

## File/state rules

Use stable IDs:

```text
char_001
scene_001
scene_001_sub_001
scene_001_shot_001
location_001
prop_001
```

Every page must save immediately after generation or revision.

Do not overwrite unrelated files when revising one block.

Do not regenerate the whole movie unless the user explicitly asks.

Use JSON schemas/Pydantic models where practical.

## Streaming behavior

Ollama output should stream into Streamlit.

For structured JSON, collect the full streamed response, parse it, validate it, and save it.

If JSON parsing fails, attempt one repair call using the same model with a strict "return valid JSON only" prompt.

## Web search policy

Core version must work without web search.

Web search should be optional and isolated behind a small interface such as:

```text
core/web_research.py
```

The app may include a checkbox for genre/style research, but if no web-search backend is configured, show a friendly message and continue with local curated dropdown choices.

Do not make web search a dependency for the core workflow.

## Setup policy

Create:

```text
setup_and_run.sh
run_movie_builder.sh
requirements.txt
config/movie_builder.local.env
```

The setup script should:

1. install apt basics
2. detect GPU only as optional info
3. install/start Ollama
4. ask user to choose Ollama models
5. pull missing models
6. create venv or conda env
7. install Python requirements
8. ask user for Streamlit port
9. save env config
10. start Streamlit

No mandatory GPU requirement.

Do not install CUDA or NVIDIA drivers automatically.

Do not install torch unless the app actually imports it.

## Python package policy

Keep dependencies minimal.

Default `requirements.txt`:

```text
streamlit
ollama
pydantic
jsonschema
python-dotenv
```

Do not add heavy packages unless they are used.

## Code style

Prefer:

- simple Python modules
- clear functions
- no hidden background services
- no unnecessary frameworks
- defensive file handling
- readable schemas
- explicit save/load paths
- idempotent setup scripts

## Initial build order

Build in this order:

1. folder structure
2. config and state manager
3. Ollama client
4. schemas
5. Page 0 Project Intake
6. Page 1 Story Builder
7. Page 2 Character Builder
8. setup_and_run.sh
9. run_movie_builder.sh
10. placeholder pages for later modules

After that, build remaining pages one by one.
