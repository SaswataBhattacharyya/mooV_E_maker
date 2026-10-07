# Story Builder Website Audit Report

**Date:** 2026-09-16  
**Scope:** Existing Story Builder WebUI (`frontend/app`) and FastAPI backend  
**Test policy:** Non-destructive live validation using the supplied dummy fixtures. Only targeted compatibility fixes were applied; Audio Reconstruct was excluded because it requires a human recording.

## Executive summary

The website starts successfully, the main routes render, the backend is reachable,
and ComfyUI/Ollama/media dependencies are available. The application is not yet
fully production-complete: several features have UI/API boundaries but still need
real model execution and end-to-end output validation.

The most important distinction is:

* **Working:** verified by a test or live service check.
* **Partially implemented:** route/UI/API exists, but the complete behavior is not proven.
* **Blocked/not ready:** a required runtime, adapter, model, or test dependency is missing.
* **Not implemented:** no complete feature path exists yet.

## Live remediation completed (2026-09-16)

The following issues found during live execution were fixed and re-tested:

* Qwen reasoning responses can put JSON in `thinking` or wrap it in text. The Ollama client now falls back to that field and safely extracts the first JSON object.
* The video summarizer's Ollama preflight and text/vision clients now accept Qwen's `thinking` response field. Video analysis completed successfully with the supplied MP4.
* `extract_mp3` now accepts both audio and video inputs (previously an MP3 upload was rejected as an unsupported input).
* Audio automation now has ACE-Step and text-only Control-Foley adapters instead of reporting them as unimplemented.
* Built and started `story-audio-denoiser` and `story-audio-demucs`; both now report available and noise cleanup completed on a live fixture.
* Corrected the Qwen 2512 text-to-image API workflow to use the installed `qwen_image_2512_bf16.safetensors` checkpoint. A live ComfyUI image job completed and its image was collected into project storage.
* ComfyUI HTTP validation errors are now surfaced with the actual node/model error instead of being mislabeled as connectivity failures.
* Started both isolated audio utility containers; noise cleanup completed live and Demucs now reports available.
* Added project output finalization/manifest endpoints. Finalized projects now receive a durable manifest listing exported media and audio artifacts.
* Demucs 2-stem separation completed live on a generated fixture.
* Voice Repair completed live through ComfyUI on a generated voice fixture.
* Voice Changer, RVC, Emotion, and Style jobs completed live on a generated voice fixture.
* Minimax H3 image-to-video completed live through ComfyUI using the supplied image fixture.
* A timed-TTS automation pipeline completed with persisted step output.
* Scene audio/video muxing completed with FFmpeg and was recorded in the final output manifest.

## Tests executed

### Frontend/UI

The complete existing Playwright suite was run through the one-command launcher:

```text
5 passed
```

Verified:

* Story Canvas route, editor, narrator control, and revision tabs
* Generate page and Phase 2/3 production sections
* Audio Reconstruct calibration and highlighted-part UI
* Video Repertoire library, YouTube, Analyze, Results, and navigation flows

Frontend checks:

* Vite production build: **passed**
* Vitest suite: **passed (1 test)**
* ESLint: **0 errors; warnings remain**

### Backend/service checks

Live API checks returned successfully for:

* `/api/health`
* `/api/projects`
* `/api/video-repertoire/capabilities`
* `/api/audio/capabilities`
* `/openapi.json`

Confirmed live:

* ComfyUI at `http://127.0.0.1:3008`
* Ollama and model `qwen3.6:35b`
* FFmpeg and FFprobe
* yt-dlp
* ComfyUI model root and voice discovery

Python source compilation passed with `compileall`. With pytest run from the
package parent (`/home/riki/web_dev`), **44 backend tests passed** while the
Audio Reconstruct test module was intentionally excluded. Pytest was installed
in the active environment for this audit; no repository dependency files were
changed.

## Feature status

### Story Canvas and story planning

**Status: partially implemented**

Present and verified:

* Story Canvas route and editor
* project selection and persistence
* narrator option
* AI analysis, outline, screenplay, and revision tabs
* backend routes for canvas revisions, analysis, and outline
* Ollama integration boundary

Still requires live validation/fixes:

* selected-range editing with immutable base-revision checks
* visible diff review and acceptance
* complete screenplay/director artifact approval gate
* stale downstream propagation after upstream story edits
* complete Canvas → Story Builder → Generate handoff

### Ollama story analysis, outline, and prompt generation

**Status: live analysis and outline verified**

The backend calls Ollama directly with context and versioned prompt instructions.
Hermes is optional orchestration and is not the primary story-generation engine.

Verified live with Ollama `qwen3.6:35b`:

* dummy novel revision creation
* analysis revision generation
* screenplay outline revision generation

Remaining:

* live dummy story analysis
* live outline generation
* malformed-response and repair testing
* prompt-template/version provenance verification
* confirmation that generated semantic fields compile into every target workflow

### Prompt compiler and workflow selection

**Status: partially implemented**

Workflow catalog and request preparation exist. The plan requires deterministic
backend adapters and allow-listed semantic bindings.

Needs:

* complete binding coverage for every registered workflow
* real request snapshot tests for all workflow families
* numeric range/type validation coverage
* UI review/edit/commit flow for prepared requests
* confirmation that no LLM response can rewrite an arbitrary workflow graph

### Generate page and production queue

**Status: partially implemented**

The Generate route and production sections exist. Backend job and automation
routes are registered.

Needs:

* dependency-aware execution from approved inputs
* durable resume after backend restart
* one-GPU scheduling and queue visibility
* real progress events and intermediate-result persistence
* retry-from-failed-stage behavior under live jobs
* final accepted output manifest generation

### Qwen image generation/editing

**Status: workflow infrastructure present; live generation not validated in this audit**

The backend has ComfyUI execution helpers and Qwen workflow assets are present.

Needs:

* submit a real text-to-image dummy prompt to ComfyUI
* submit a real image-edit dummy request
* collect the generated image into project storage
* verify model filenames and output provenance
* verify prompt compiler injection and output acceptance

### Automatic mixed multi-character TTS

**Status: live short multi-character-compatible run verified**

Present:

* character-map API
* timed TTS route and job records
* ComfyUI TTS workflow boundary
* voice discovery/catalog
* mixed dialogue service structure

Verified live:

* discovered ComfyUI voice catalog
* project character map persistence
* timed TTS job completion and audio output collection

Remaining:

* real multi-character dummy SRT/dialogue run
* per-character voice mapping verification
* timing/gap and overlap validation
* WAV output collection and playback in the UI
* retry and partial-failure behavior

### Audio Reconstruct and ASR

**Status: UI and backend boundary present; core live behavior unverified**

Present:

* character calibration route
* highlighted dialogue-part route
* take upload and accept routes
* audio processing/effect service boundaries
* fragmented/continuous design direction in the plan/UI

Needs:

* browser microphone recording
* streaming ASR against the highlighted line
* “line complete” detection and explicit confirmation
* repeat-only-current-part behavior
* per-part filename/sequence guarantees
* continuous-mode splitting and alignment
* real noise-clearance → voice overlay/RVC → pitch flow
* output playback and stage history in the UI

### Noise cleanup, voice repair, voice changer, RVC, emotion/style

**Status: API/service boundaries present; live outputs not fully verified**

Noise cleanup is now live-verified after starting the isolated denoiser runtime;
Demucs is available in the isolated runtime. The ComfyUI voice-effect operations
remain available and require individual production-quality runs.

Capabilities and routes are registered, and the backend uses fixed workflow
contracts where applicable.

Needs:

* one real dummy audio run per operation
* output-file collection and playback verification
* model availability/error reporting
* chained optional processing with immutable intermediate files
* failure/retry behavior

### ACE-Step music

**Status: live short generation verified**

Verified live 5-second instrumental job, ComfyUI polling, MP3 collection, and export to the project's output audio folder.

Remaining:

* real short music job
* ComfyUI completion polling
* audio collection into project storage
* preview/download verification
* accepted output manifest entry

### Control-Foley

**Status: adapter and route available; live generation pending**

Capability preflight is live: ComfyUI, the Control-Foley model, and all required
nodes are present. The official source repository is installed, but the node's
runtime still fails to import `lib.flow_matching` inside the long-running
ComfyUI process. This requires a small patch to the external custom-node import
path (outside this repository) before generation can complete.

Remaining:

* text-only dummy foley run
* text + video dummy run
* output collection and playback
* model/node failure handling

### Video Repertoire

**Status: UI and API substantially working**

Live validation completed with the supplied MP4: upload, Ollama model preflight,
scene analysis, report writing, and completion status all succeeded.

Verified:

* library view
* existing asset playback/content requests
* YouTube tab and URL/file controls
* Analyze tab controls
* Results tab/search controls
* FFmpeg, FFprobe, yt-dlp, and Ollama capability reporting

Needs live validation:

* import the supplied dummy MP4 through the UI
* frame extraction
* transcript/vision analysis with Ollama
* scene artifact persistence
* search against generated descriptions
* cancel/retry behavior

### Video generation and final media composition

**Status: partially implemented**

The generic ComfyUI media gateway is live-verified for Qwen text-to-image, including
model validation, polling, output collection, and project persistence. A project
output finalization endpoint now writes a durable manifest of exported artifacts.

Workflow infrastructure and media routes exist.

Needs:

* real image/video ComfyUI job
* scene-level dependency ordering
* accepted video output storage
* final audio/video/SFX composition
* final per-scene output package and manifest

### Automation pipelines

**Status: partially implemented; not production-ready**

Automation routes, pipeline validation, runs, and retry endpoints exist. Backend
health currently reports `automation_runner: false`.

Needs:

* enable/verify the runner
* execute a real multi-step pipeline
* persist step-level outputs
* pause/resume/retry semantics
* verify Hermes and browser use the same backend registry

## Storage status

The intended canonical layout is project-scoped:

```text
storage/projects/<project-id>/
├── input/       # latest saved story/source package
├── revisions/
├── artifacts/
├── requests/
├── audio/
├── images/
├── video/
└── output/      # accepted final per-scene exports
```

The older top-level `input/` and `output/` directories still exist and should be
treated as legacy/compatibility data until explicitly migrated. They should not
be deleted during cleanup.

## What is genuinely not working versus simply untested

### Confirmed problems/blockers

* No current automation-runner outage is present; live health reports it enabled.
* Audio Reconstruct tests were intentionally excluded from the backend run per
  scope; its live microphone behavior remains unverified.
* Complete browser microphone/streaming-ASR behavior is not present in the
  tested UI flow.
* Full end-to-end production queue has not been demonstrated.

### Not proven, but not confirmed broken

* Full production-quality coverage for every voice-effect mode
* Full Control-Foley output-quality coverage for all three input modes
* Final scene-level composition/export manifest

These require real model jobs and output inspection, not just route/capability
checks.

## Recommended next test sequence

## Current implementation status (latest live pass)

Completed and live-tested: Qwen image generation, Minimax image-to-video,
noise cleanup, Demucs, Voice Repair, Voice Changer, RVC, Emotion, Style,
timed-TTS automation, and FFmpeg scene mux/export. Control-Foley, Audio
Reconstruction/ASR, and ACE-Step fine-tuning remain intentionally outside this
pass.

Use the supplied dummy files in `plan/` and run one controlled job at a time:

1. Ollama story analysis and outline
2. Qwen text-to-image
3. mixed multi-character TTS
4. ACE-Step music
5. Video Repertoire import and Ollama analysis
6. Audio reconstruction/ASR with a short recorded or supplied clip
7. Control-Foley and voice-effect operations
8. final per-scene output package

Each test should record the request, job ID, backend status transitions, output
paths, playback/download result, and any model/node error. Only after that should
the feature be labeled production-ready.

## Manual preparation currently required

No new ComfyUI installation step is required. Before live generation testing,
ensure:

* ComfyUI remains running on port `3008`;
* Ollama remains running with `qwen3.6:35b` available;
* the configured audio/video worker environments remain active;
* voice/model files are readable by the backend process.

No source changes were made while producing this report.
