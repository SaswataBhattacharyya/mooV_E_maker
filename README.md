# Story Builder

Full backend and frontend source for UI planning and development. Start with
[the developer checkout guide](docs/DEVELOPER_CHECKOUT.md) for an empty installation
without ComfyUI, Ollama, media or model downloads.

The operator documentation below retains the original Spark paths and optional
runtime instructions. The developer guide provides the clone setup.

---

# Story Builder Web Workspace

Story Builder is a shared project workspace for writing stories, preparing generation jobs, running approved ComfyUI workflows, managing audio voices, and monitoring Hermes-assisted production.

For the new production workspace, see [the operator walkthrough](plan/new_complete_plan/25_PRODUCTION_OPERATOR_GUIDE.md) and [current acceptance status](plan/new_complete_plan/12_CURRENT_STATUS.md). Required release gates have passed and the new navigation is enabled; legacy routes remain available.

## Services and Ports

| Service | Default address | Purpose |
|---|---|---|
| Story Builder backend | `http://127.0.0.1:3010` | FastAPI, project storage, generation jobs, and production web UI |
| Frontend development server | `http://127.0.0.1:8080` | React/Vite hot-reload UI |
| ComfyUI | `http://127.0.0.1:3008` | Image, video, TTS, and model-powered audio execution |
| Ollama | `http://127.0.0.1:11434` | Local story assistance |
| Hermes supervisor UI | `http://127.0.0.1:3009` | Optional supervisor status and conversation |

ComfyUI and Ollama may be offline while editing projects, but their related generation features will not run.

## Prerequisites

- Python 3.11 or newer
- Node.js and npm
- The local ComfyUI installation when using media/audio generation
- Ollama when using story assistance

The expected ComfyUI installation is currently:

```text
/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI
```

## First-Time Setup

Install the backend dependencies:

```bash
cd /home/riki/web_dev/story_builder
python3 -m pip install -r requirements.txt
```

Install the frontend dependencies:

```bash
cd /home/riki/web_dev/story_builder/frontend/app
npm install
```

## Start the Web UI for Development

Development mode uses two terminals and provides frontend hot reload.

### Terminal 1: backend

The Python package is named `story_builder`, so start it from its parent directory:

```bash
cd /home/riki/web_dev
python3 -m uvicorn story_builder.api.main:app \
  --host 0.0.0.0 \
  --port 3010 \
  --reload
```

Backend health check:

```text
http://127.0.0.1:3010/api/health
```

### Terminal 2: frontend

```bash
cd /home/riki/web_dev/story_builder/frontend/app
npm run dev
```

Open:

```text
http://127.0.0.1:8080
```

Vite automatically proxies `/api` requests to the backend on port `3010`.

### Start both services with one command

From the repository root, use the bundled launcher:

```bash
./run_story_builder.sh
```

It starts FastAPI on port `3010` and Vite on port `8080`; press `Ctrl+C` once
to stop both processes. Override ports with `STORY_BUILDER_BACKEND_PORT` and
`STORY_BUILDER_FRONTEND_PORT` when needed.

## Start the Built Web UI on One Port

Build the frontend first:

```bash
cd /home/riki/web_dev/story_builder/frontend/app
npm run build
```

Then start FastAPI from `/home/riki/web_dev`:

```bash
cd /home/riki/web_dev
python3 -m uvicorn story_builder.api.main:app \
  --host 0.0.0.0 \
  --port 3010
```

Open:

```text
http://127.0.0.1:3010
```

The frontend must be built before starting FastAPI because the backend detects the `dist` directory during application startup.

### Production workspace

The `/production` workspace provides the released story-to-shot workflow, with independent Manual/Semi/Full control and Direct H3/Reference-built/Hybrid making routes. Mandatory story planning, revisioned approvals, character/world masters, voice bindings, reference composition, editable Refine proposals, durable jobs and native-audio review are implemented. Existing Story Builder, Automation, Manual Director and legacy production routes remain available.

Required acceptance gates passed: real configured-provider Direct and Reference-built paths, three accepted Reference masters, reviewed native media, two-scene continuity/reset, persisted worker recovery, no-duplicate continuation, cancellation and browser playback/reload. The [final release record](plan/new_complete_plan/27_FINAL_RELEASE_2026_10_07.md) distinguishes real model evidence from deterministic browser/regression coverage. Acceptance uses representative short productions; it does not guarantee every generated take will pass quality review. Optional FL2VA and unavailable advanced guide models remain disabled. Final-film stitching is outside this upgrade.

The new navigation is enabled in `frontend/app/.env.local`. Set `VITE_STORY_BUILDER_NEW_PRODUCTION_NAV=false` and restart/rebuild the frontend to restore the legacy entry. The currently running website is `http://127.0.0.1:8081/production`; the launcher's default frontend port remains8080. See the [operator guide](plan/new_complete_plan/25_PRODUCTION_OPERATOR_GUIDE.md) for the tested Python/H3 environment and safe restart.

Generate queues a durable take; wait for output collection and its actual review. Extra or garbled speech remains a quality hold. Same-scene descendants use accepted predecessors; fresh scenes reset video references. Before heavy generation, inspect ComfyUI ownership/queue and continuously monitor temperature, utilization and clocks. Website jobs are serialized; unrelated direct clients remain outside that queue. GPU intervention is83°C below the user's85°C maximum.

## Start the Local AI Stack

The existing local launcher is:

```bash
cd /home/riki/web_dev/setup_comfy_and-stuff/opencode/hermes_agent
./start_local_ai_stack.sh
```

Confirm ComfyUI is available at:

```text
http://127.0.0.1:3008
```

The Audio Studio and Media Composer show whether ComfyUI is reachable. Starting the Story Builder backend does not automatically start ComfyUI.

### Optional isolated audio utilities

Noise Cleanup and Demucs stem separation run in their own containers so their dependencies cannot alter ComfyUI:

```bash
cd /home/riki/web_dev/story_builder/runtimes/audio-utilities
docker compose build
docker compose up -d
```

The Audio Utilities page detects whether `story-audio-denoiser` and `story-audio-demucs` are running. Video-to-MP3 only requires host FFmpeg.

## Web UI Components

The main audio routes are:

- `/audio` — dialogue/TTS, voices, split/stitch, repair, conversion, emotion, and style.
- `/music-sound` — ACE-Step music generation, Control-Foley sound effects, and ACE fine-tuning preflight.
- `/audio-tools` — curated audio plus noise cleanup, video-to-MP3, and Demucs batch/folder tools.
- `/video-repertoire` — managed reference-video library, YouTube intake, scene analysis, clips, and searchable reports.
- `/automation` — saved, validated audio pipelines that users and Hermes run through the same API.

### Overview — `/`

The landing page shows the active project and links to the main work areas. Story Builder and the media/audio modules share the selected project through browser local storage and backend project state.

### Story Builder — `/story`

Use this page to:

- Create or select a project
- Write and revise the source story
- Generate and edit structured artifacts
- Progress through story, characters, scenes, subscenes, dialogue, and image jobs
- Ask the local assistant for focused revisions and questions

Start here before using project-dependent media or audio features.

### Media Composer — `/media`

Use this page for registered API-compatible ComfyUI image and video workflows:

- Select a workflow
- Enter prompts and supported parameters
- Upload required images or frames
- Submit the workflow to ComfyUI
- Review generated project media

Only workflows under the API workflow catalog are directly runnable. Other workflow files may appear as catalog-only entries.

### Video Repertoire — `/video-repertoire`

Use this page to register existing reference videos, upload local videos, review YouTube search/URL inputs before downloading, and run the standalone video scene summarizer as a persisted background job. Results include final summaries, scene timelines, keyframes, frame deltas, transcript slices, extracted clips, and searchable descriptions.

The backend uses `video_repertoire/` for managed assets and invokes `video_summariser` in a subprocess. Set `VIDEO_SUMMARIZER_PYTHON` when its dependencies live in a different Python environment from Story Builder. Analysis requires FFmpeg, Whisper, a reachable Ollama vision model, and the dependencies listed in `video_summariser/requirements.txt`.

### Audio Studio — `/audio`

Audio Studio provides:

- ComfyUI and TTS-Audio-Suite diagnostics
- Read-only reference-voice and TTS-model catalogs
- Reference-voice installation using an audio file and exact transcript
- Per-project character-to-reference-voice maps
- A compact block library showing available and future audio operations
- Timed multi-character TTS, split/stitch, repair, voice conversion, RVC, emotion, and style operations

Noise cleanup and Demucs live on Audio Utilities rather than Audio Studio. Unproven training operations remain disabled until their implementation and live gates pass.

User-added one-shot voices are installed as:

```text
ComfyUI/models/voices/<voice-name>.<audio-extension>
ComfyUI/models/voices/<voice-name>.reference.txt
```

Generated and edited project audio does not go into the model or voice libraries.

### Automation — `/automation`

Automation contains the ordered Audio Automation runner. Its first supported sequence is Timed TTS → Split → Emotion → Stitch. Pipelines are saved per project, validated before execution, retain child jobs and outputs, and can retry a failed downstream step while reusing completed upstream work.

Hermes uses the trusted wrapper rather than ComfyUI or raw workflow JSON:

```bash
cd /home/riki/web_dev/story_builder
python3 hermes_story_builder/runner/story_builder_audio.py blocks
```

The complete Hermes contract is in `TTS_skills/story-builder-audio-automation/SKILL.md`.

### Status — `/status`

Use this page to monitor:

- Current project stage and runtime state
- Progress and errors
- ComfyUI and Ollama availability
- Accepted images and recent project logs
- Hermes/supervisor status and actionable diagnoses

The Supervisor button opens the optional supervisor UI on port `3009`.

## Configuration

Common environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `COMFYUI_URL` | `http://127.0.0.1:3008` | ComfyUI API base URL |
| `COMFYUI_ROOT` | `/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI` | ComfyUI installation used for model/voice discovery |
| `TTS_AUDIO_SUITE_ROOT` | `<COMFYUI_ROOT>/custom_nodes/TTS-Audio-Suite` | Active TTS-Audio-Suite directory |
| `COMFYUI_INPUT_DIR` | `<COMFYUI_ROOT>/input` | ComfyUI upload staging directory |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server |
| `VITE_API_BASE` | `/api` | Frontend API base |
| `VITE_BACKEND_TARGET` | `http://127.0.0.1:3010` | Vite development proxy target |
| `VIDEO_REPERTOIRE_ROOT` | `<project>/video_repertoire` | Managed downloads, uploads, analyses, clips, manifests, and jobs |
| `VIDEO_SUMMARIZER_PYTHON` | Story Builder Python | Python executable used by the isolated analysis/download worker |
| `VIDEO_SUMMARIZER_ANALYSIS_MODEL` | `qwen3.6:35b` | Ollama vision model used for video analysis |

For the current ComfyUI installation, set the input directory when starting the backend:

```bash
export COMFYUI_INPUT_DIR=/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/input
```

## Storage

Project state and artifacts are stored under:

```text
/home/riki/web_dev/story_builder/storage/projects/
```

General uploaded media is stored under:

```text
/home/riki/web_dev/story_builder/storage/uploads/
```

Accepted final exports are intended for:

```text
/home/riki/web_dev/story_builder/output/
```

Do not manually place generated audio inside ComfyUI model or voice directories.

## Timed Multi-Character TTS

Audio Studio provides the Phase 2 ChatterBox timed-dialogue panel. Select a Story Builder project, save its character map, paste or import an SRT file, choose the shared base-language model and timing settings, then run the job. The browser polls Story Builder; it does not contact ComfyUI directly.

Hermes can use the same API:

```text
POST /api/projects/{project_id}/audio/tts/timed
GET  /api/projects/{project_id}/audio/tts/jobs/{job_id}
GET  /api/projects/{project_id}/audio/tts/jobs
```

The POST body contains `srt_content`, `language`, `seed`, `timing_mode`, and optional safe ChatterBox/timing overrides. Character voices and default languages come from the project's saved character map. Poll the returned `job_id` until its status is `completed` or `failed`.

Completed run files are kept under `storage/projects/<project-id>/audio/runs/<job-id>/`. The final FLAC is also copied to `output/<project-id>/audio/`. The original reference workflow and TTS-Audio-Suite global character alias file are never changed.

## Live Voice Discovery

Adding a reference voice asks the running TTS-Audio-Suite to refresh its voice dropdown immediately. The response states whether the expected voice was discovered or a ComfyUI restart is required. Hermes can also refresh explicitly:

```text
POST /api/audio/voices/refresh
```

The optional JSON field `expected_voice_id` verifies one particular catalog entry.

## F5-TTS Dataset Preparation

Audio Studio can validate and prepare project-owned datasets for `F5TTS_v1_Base`, `F5TTS_Base`, and `E2TTS_Base`:

```text
GET  /api/audio/finetune/f5/preflight
POST /api/projects/{project_id}/audio/finetune/f5/prepare
GET  /api/projects/{project_id}/audio/finetune/f5/jobs/{job_id}
```

The multipart POST accepts `dataset_name`, `base_model`, `metadata`, and repeated `audio_files`. The metadata header must be `audio_file|text`. Successful preparation creates `raw.arrow`, `duration.json`, and `vocab.txt` inside the project. Training and checkpoint downloads remain disabled until the user separately approves a consented dataset and exact command.

## Split and Stitch Audio

Audio Studio can split uploaded or project-owned audio from structured time ranges, preview every generated clip, optionally upload edited replacements, and reassemble with either direct concatenation or explicit per-clip gaps. This path runs locally without ComfyUI.

## Audio Effects (Phases 6–8)

Audio Studio exposes fixed API-backed operations for voice repair, Chatterbox voice conversion, RVC pitch/timbre conversion, and separate Step Audio EditX emotion/style edits. Noise Cleanup is an isolated Python operation on Audio Utilities and is intentionally absent from Audio Studio.

Hermes should call Story Builder on port 3010, never ComfyUI localhost directly and never mutate workflow JSON:

```text
GET  /api/audio/effects/capabilities
GET  /api/audio/rvc/models
POST /api/projects/{project_id}/audio/effects/{operation}
GET  /api/projects/{project_id}/audio/effects/jobs/{job_id}
GET  /api/projects/{project_id}/audio/effects/jobs
```

The POST is multipart form data with a JSON `payload` field and either an uploaded `source` file or `source_relative_path` inside the project. Audio Studio operation names are `voice_repair`, `voice_changer`, `rvc`, `emotion`, and `style`. Completed FLAC files are retained under the project and copied to `output/<project-id>/audio/`.

## Music, Sound Effects, and Automation

Music & Sound keeps ACE-Step music generation and provides three fixed Control-Foley modes: Text → Audio, Text + Video → Audio, and Reference Audio + Video → Audio. The form enables only the uploads required by its selected workflow. Jobs export their primary audio under `output/<project-id>/audio/`.

```text
GET  /api/music/control-foley/capabilities
GET  /api/music/control-foley/schema
POST /api/projects/{project_id}/music/control-foley/jobs
GET  /api/projects/{project_id}/music/control-foley/jobs/{job_id}
```

The Automation page and Hermes share the block registry and pipeline endpoints under `/api/automation`. Neither client contacts port 3008 directly; the Story Builder backend stages inputs, selects fixed workflows, polls ComfyUI, and records outputs.

Emotion and Style require the exact source transcript and accept only 0.5–30 second inputs. Voice Changer requires a discovered one-shot `target_voice_id`. RVC requires a catalog model and only an index paired with that model. Effect outputs can be selected directly as replacements in the Split/Stitch panel.

```text
POST /api/projects/{project_id}/audio/scenes/split
POST /api/projects/{project_id}/audio/scenes/{split_job_id}/stitch
GET  /api/projects/{project_id}/audio/scenes/jobs/{job_id}
```

Scene jobs and immutable originals are stored under `storage/projects/<project-id>/audio/scenes/`. Final stitched WAV files are also copied to `output/<project-id>/audio/`.

## Verification Commands

Backend tests:

```bash
cd /home/riki/web_dev/story_builder
PYTHONPATH=/home/riki/web_dev python3 -m unittest discover -s tests -v
```

Frontend production build:

```bash
cd /home/riki/web_dev/story_builder/frontend/app
npm run build
```

Focused checks for the Audio Studio:

```bash
cd /home/riki/web_dev/story_builder/frontend/app
npx eslint src/pages/AudioStudio.tsx src/App.tsx src/components/AppShell.tsx
```

## Audio Implementation Plan

The detailed phased audio plan and current implementation status are maintained in [docs/audio_plan.md](docs/audio_plan.md).






Download:

cd /home/riki/web_dev/story_builder/video_summariser
mkdir -p models

wget -O models/yolov8n.pt \
  https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt

yolov8n.pt is the lightweight object-detection model recommended for this first setup. Ultralytics documents this model and its automatic download behavior officially.
citeturn6view0

### 2. Florence-2 model

Official Microsoft model: Florence-2-large on Hugging Face

Download into the expected directory:

cd /home/riki/web_dev/story_builder
mkdir -p video_summariser/models/,

python3 - <<'PY'
from huggingface_hub import snapshot_download

python3 - <<'PY'
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="microsoft/Florence-2-large",
    local_dir="video_summariser/models/florence-2-large",
)
PY

Florence-2 provides detailed captioning, object detection, grounding and OCR tasks. citeturn6view1

If huggingface_hub is missing:

python3 -m pip install huggingface_hub

### 3. Tesseract OCR

Tesseract is not stored inside the Image Detailer model folder. It is a system OCR engine.

sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-eng
python3 -m pip install pytesseract

Official installation instructions are documented by Tesseract and pytesseract. citeturn6view2turn6view3

Verify:

tesseract --version
python3 -c "import pytesseract; print(pytesseract.get_tesseract_version())"

### 4. Restart Story Builder

The backend must be restarted after installing these:

cd /home/riki/web_dev/story_builder
./run_story_builder.sh
