# OpenClaw Knowledge

This file describes how the repo works so OpenClaw can supervise it correctly.

## Core Product Shape

The product is a website-first pipeline.

The user works through the website, not through an OpenClaw terminal session.

The backend orchestrates:

- project state
- artifact chain
- Ollama generation
- ComfyUI image execution
- review flow

OpenClaw reads and improves this system from the side.

## Current Artifact Chain

Current structured artifact order:

1. `story`
2. `characters`
3. `scenes`
4. `subscenes`
5. `dialogue`
6. `image_jobs`

Each stage consumes approved upstream artifacts.

This artifact chain is the current project context.

## Current Website Runtime

The website now supports:

- saving a draft
- restoring the current project
- generating artifacts stage by stage
- viewing project runtime logs
- viewing dependency status
- generating image batches
- accepting image candidates

Primary UI port:

- `3010`

Supervisor UI port:

- `3009`

ComfyUI service port:

- `3008`

Ollama API:

- `11434`

## Ollama Usage

Ollama currently returns text payloads, but the backend instructs it to emit JSON-only responses.

The backend then parses and stores those responses as JSON artifacts.

Current backend prompt builders are in:

- `api_server/services/story_pipeline.py`

Current Ollama API wrapper is in:

- `api_server/services/ollama_client.py`

Memory retention can be tuned with:

- `OLLAMA_KEEP_ALIVE`
- `OLLAMA_REASONING_KEEP_ALIVE`
- `OLLAMA_VISION_KEEP_ALIVE`

For constrained machines, the repo may set these to `0m` so large Ollama models unload after each request instead of staying resident between stages.

## Current Models

### Reasoning

- env var: `OLLAMA_REASONING_MODEL`
- current default: `gemma4:latest`

This model currently handles:

- story generation
- character generation
- scene generation
- subscene generation
- dialogue generation
- image job generation

### Vision

- env var: `OLLAMA_VISION_MODEL`
- current default: `qwen2.5vl:7b`

This is reserved for later:

- image review
- frame review
- continuity review from visuals

### Coder

- env var: `OLLAMA_CODER_MODEL`
- current default: `qwen2.5-coder:14b`

This is reserved for later:

- code diagnosis
- command diagnosis
- log-oriented technical debugging

## Current Image Workflows

Important image-related workflows in `workflows/ricky`:

- `gsl_starter_1_1.json`
- `image_qwen_Image_2512.json`
- `02_qwen_Image_edit_subgraphed.json`
- `Qwen 2511 multi angle (Single Sampler)+ZImageTurbo.json`

Current API-ready image path in the app uses the `gsl_starter_1_1` family through the API workflow copy in:

- `workflows/api/gsl_starter_1_1_api.json`

OpenClaw should understand:

- `gsl_starter_1_1` is the current text-to-image starter path
- scene editing and multi-angle work are separate workflows
- workflow choice should match task type, not be arbitrary

## Prompt Reference

Reference prompt examples live in:

- `prompt_example.md`

These include:

- Z Turbo text-to-image style examples
- Qwen image examples
- TTS multilingual prompt examples
- scene split/edit/concat command examples

OpenClaw should treat these as examples and conventions, not blindly copy them.

## Audio Knowledge

Important TTS scripts:

- `split_scene_audio.py`
- `partition_scene_edits.py`
- `edit_scene_clips.py`
- `concat_scene_audio.py`
- `timed_concat_scene_audio.py`
- `convert_audio_to_mp3.py`

### Key Audio Facts

- `split_scene_audio.py` is explicit-range based, not silence-aware
- `concat_scene_audio.py` is simple sequential concat
- `timed_concat_scene_audio.py` supports manifest-driven concat with explicit gaps
- localized edits should prefer split/edit/concat over full regeneration

### Voice Alias Source

Source of truth:

- `TTS-Audio-Suite/voices_examples/#character_alias_map.txt`

Important current facts:

- `Alice`, `Bob`, and `Narrator` already exist
- alias entries may also carry default language
- future characters can be added by mapping alias names to voice assets

## Audio Rules OpenClaw Must Respect

### Narration

- plain narration does not need an explicit `Narrator` tag every time

### Speaker Defaults

- female default lead: `Alice`
- male default lead: `Bob`

### Language Formatting

Use canonical short tags consistently.

Avoid mixed styles like:

- `En`
- `USA`
- `German`
- `Norwegian`

unless the system explicitly requires a different format for a specific workflow.

### Pause Usage

- pause tags are optional
- only use them inside the same speaker’s continuous line
- do not place them at the start or end of a line
- do not use them when simple timing design is enough

## Visual Logic OpenClaw Must Respect

- character consistency is critical
- clothing continuity matters
- time-of-day continuity matters
- scene continuity matters
- transitions are still scene units
- lip sync should be selective and expensive, not used everywhere

For visuals-first planning:

- define story
- define characters
- define scenes
- define sub-scenes
- define dialogue against approved visual intent
- define image jobs

## Commands OpenClaw Should Know

### Startup

```bash
./bootstrap_vm.sh
```

### Supervisor First-Time Setup

```bash
./setup_openclaw_supervisor.sh
```

This setup path:

- verifies Ollama
- verifies required Ollama models
- attempts OpenClaw installation
- best-effort clones Graphify and Ruflo into `openclaw/support`
- prepares the separate supervisor runtime on `3009`

### Supervisor Daily Start

```bash
./run_openclaw_supervisor.sh
```

The current repo implementation exposes a separate supervisor UI on:

```text
http://<vm-ip>:3009
```

This UI is a repo-local supervisor wrapper that reads project state and logs directly.

### Health Checks

```bash
curl http://127.0.0.1:11434/api/tags
curl http://127.0.0.1:3008/system_stats
curl http://127.0.0.1:3010/api/health
```

### Audio Local Tools

```bash
python3 TTS-Audio-Suite/scripts/split_scene_audio.py ...
python3 TTS-Audio-Suite/scripts/partition_scene_edits.py ...
python3 TTS-Audio-Suite/scripts/edit_scene_clips.py ...
python3 TTS-Audio-Suite/scripts/concat_scene_audio.py ...
python3 TTS-Audio-Suite/scripts/timed_concat_scene_audio.py ...
```

OpenClaw should not run such commands autonomously in production flow unless the app explicitly allows that bounded action.

## Future Knowledge Hooks

### Graphify

Graphify should later hold:

- project facts
- continuity facts
- scene facts
- character facts
- reusable memory for supervision

### AutoResearch

AutoResearch should later help with:

- controlled prompt comparisons
- workflow comparisons
- improvement loops
- evidence-backed optimization
