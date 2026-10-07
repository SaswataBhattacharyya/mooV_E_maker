# Story Builder: Full Product and Implementation Plan

## 1. Outcome

Build a reviewable, local-first production workspace that takes a rough idea through:

```text
Story Canvas → screenplay → production plan → workflow-specific request drafts
→ image generation → dialogue/music → video → sound effects
```

The system edits only user-selected story ranges, preserves revision history and continuity, allows manual review at every boundary, and uses Ollama to generate structured creative plans and target-specific prompt drafts. The Story Builder backend remains the only browser-facing execution authority; the browser never submits directly to ComfyUI or rewrites workflow JSON.

Two pages are added without deleting existing pages:

- **Story Canvas** for novel drafting, analysis, and scene-by-scene screenplay creation.
- **Generate** for dependency-aware, ordered execution and review of all prepared media.

The existing `/story` becomes the director-style production planning page. `/media`, `/audio`, `/music-sound`, `/audio-tools`, `/automation`, and `/status` remain and are integrated rather than replaced.

## 2. Evidence from the current repository

This plan is based on the current React/FastAPI WebUI, the Graphify report, workflow catalog, audio services, and existing plans.

### What already works

- React routes exist for Story Builder, Media Composer, Audio Studio, Music & Sound, Audio Utilities, Automation, and Status.
- Project selection is shared via `story-builder.currentProjectId` in local storage.
- FastAPI owns project persistence and mediates Ollama/ComfyUI calls.
- The story pipeline already produces `story`, `characters`, `scenes`, `subscenes`, `dialogue`, and `image_jobs` JSON artifacts.
- Media Composer discovers workflows and directly runs allow-listed files under `workflows/api/`.
- Timed multi-character TTS, character voice maps, split/stitch with explicit gaps, voice repair, voice conversion, RVC, emotion/style, ACE-Step music, Control-Foley, and saved audio automation have working service boundaries.
- Generated project media, inputs, revisions, artifacts, and accepted exports are all persisted beneath `storage/projects/<project-id>/`; the final accepted export tree is `storage/projects/<project-id>/output/`.
- API-safe Minimax H3 text/image/reference-video adapters and Qwen/Wan image/video adapters already exist under `workflows/api/`.

### Gaps that shape the design

- The current “canvas” is a textarea plus whole-artifact editors; it has no selection-based patch protocol, diff acceptance, or story revision graph.
- Story and production planning are mixed on one page and use a short linear artifact chain.
- The current project schema does not contain novel revisions, analysis issues, screenplay scenes, director plans, prompt packs, dependency state, or stale/rebuild metadata.
- The earlier split between top-level `input/`/`output/` and project storage was ambiguous; both are now project-scoped beneath `storage/projects/<project-id>/`.
- The Media Composer currently both prepares and executes a job synchronously. It does not save a batch of reviewable request drafts for later generation.
- Workflow inference is heuristic. It does not yet provide authoritative semantic input bindings for every workflow, especially UI-only `ricky/` files.
- Current media records are generic rather than tied to scene/shot/line/cue IDs.
- There is no Generate page, ASR service, browser microphone flow, transcript-to-line alignment, repertoire search integration, or scene-wide readiness graph.
- Graphify found `StoryPipeline`, `ComfyUIEngine`, and the legacy `app.py` as low-cohesion “god nodes” and found documentation concepts weakly connected to code. New work should be split by domain and described by explicit contracts.
- The Graphify manifest covers only the older 11-file pipeline and predates much of the React/FastAPI/audio code. Regenerate it after each major implementation phase; do not treat the current graph as a complete dependency map.

## 3. Architectural decisions

### 3.1 Canonical state and filesystem roles

`/home/riki/web_dev/story_builder/storage/projects/<project-id>/` is the canonical runtime/database-like workspace already used by the current `ProjectStore`. It owns revisions, job state, logs, uploads, intermediate outputs, and immutable request/history records. The `<project-id>` is the existing generated project ID, not the display title.

`storage/projects/<project-id>/input/` is the project’s human-readable **published source package**. Story Canvas Save Revision writes/rewrites the current project story file there; it does not run analysis or generation. Re-saving the same project updates that project’s story file. A different project always receives a separate `input/` directory. Older request revisions remain available under `storage/projects/<project-id>/requests/` and are referenced by the published manifest.

`storage/projects/<project-id>/output/` is the accepted final export tree. Generated candidates remain in runtime storage until the user accepts or explicitly exports them.

The project storage layout is:

```text
storage/projects/<project-id>/
  input/                 # latest saved story/source package for this project
  revisions/             # immutable novel, analysis, screenplay revisions
  artifacts/             # generated/editable production artifacts
  requests/              # immutable prompt/request history
  audio/                 # automatic TTS and reconstruction intermediates
  images/                # accepted and candidate image assets
  video/                 # accepted and candidate video assets
  output/                # final accepted per-scene export tree
    scene_001/
      audio/
      images/
      video/
      sfx/
      manifest.json
```

The project manifest stores `project_id`, stable `story_slug`, display title, and both paths. Renaming a title does not silently rename folders. Slug collisions are resolved once at project creation (for example `the-scar-a1b2c3d4`). All backend paths are resolved beneath configured roots; client-provided absolute paths are rejected.

Browser local storage stores only current project ID, unsaved editor recovery, and the Canvas→Story Builder handoff token/revision. It is not the authoritative copy of the novel or screenplay.

### 3.2 Immutable creative intent, replaceable target compilation

Canonical artifacts describe creative intent without model-specific fields. The user may choose a different workflow and recompile request drafts without regenerating the story or director plan.

```text
approved scene/shot/cue
        + selected workflow manifest
        + resolved accepted assets
        ↓
versioned request draft
        ↓ user commits
executable request snapshot
```

Ollama writes semantic prompt fields. Deterministic backend adapters map them to allow-listed workflow nodes, validate types/ranges/assets, compute a workflow hash, and save the exact executable snapshot. Ollama never receives permission to edit arbitrary node graphs.

### 3.3 Revision and invalidation model

Every artifact has a stable ID, revision, status (`draft`, `approved`, `stale`, `blocked`, `ready`, `running`, `completed`, `failed`, `accepted`), parent revision IDs, and content hash.

Changing an upstream artifact does not delete downstream work. It marks affected descendants stale and shows a diff/rebuild choice. Examples:

- novel edit → analysis and relevant screenplay scenes stale;
- screenplay line edit → that scene's dialogue/timing and dependent video/audio request drafts stale;
- character identity edit → that character asset and referencing frames/videos stale;
- workflow change → only compiled requests for that target stale;
- accepted image replacement → dependent video requests stale.

### 3.4 Long-running jobs

Ollama, ComfyUI, ASR finalization, and batch generation are asynchronous jobs with polling or server events. Requests return `202` plus job ID; closing the page does not lose execution state. The backend enforces one-GPU scheduling initially and clearly reports VRAM contention rather than silently stopping another service.

## 4. User experience and routing

### 4.1 Story Canvas (`/canvas`)

Layout resembles a document editor with a narrower collaborator pane:

- project/title controls and explicit Save Draft;
- rich/plain text novel editor with stable paragraph/block IDs;
- selection toolbar: revise, expand, shorten, connect, clarify, custom instruction;
- proposed replacement diff with Apply/Reject;
- AI Analysis pane listing loose ends, contradictions, motivation/chronology/continuity issues, severity, story anchors, possible resolutions, and resolved/dismissed state;
- version history and restore-as-new-revision;
- narrator toggle (`With narrator` / `Without narrator`);
- `Create screenplay` step, first producing a full scene outline and then generating one scene at a time;
- per-scene progress, retry, edit, approve, and coverage/continuity review;
- Next button enabled only when a novel revision and screenplay revision are approved.

The Canvas should not regenerate the full novel for a local instruction. The client sends selected block IDs, exact selected text, surrounding anchors, current revision, and instruction. The backend rejects an apply if the base revision changed meanwhile.

### 4.2 Story Builder (`/story`)

This becomes the production planning page. It can receive the Canvas handoff, select an existing backend project, or import a supported novel/script pair. Direct entry offers:

- choose existing project;
- upload novel `.txt` plus screenplay `.txt`/`.json`;
- create a project and parse imported material before committing;
- show validation and scene mapping for user approval.

The page is organized per scene with collapsible panels:

1. scene summary and transition/continuity;
2. character assets;
3. people-free scene background;
4. shots/keyframes (first frame and optional last frame);
5. dialogue/narration with emotion, style, approximate timing, and gaps;
6. background music cues with timing/instruments/energy;
7. camera, lighting, blocking, and transitions;
8. sound effects with timing/spatial intent;
9. video intent and mode.

Generation occurs scene by scene with edit/approve controls. A global continuity panel shows reusable character/location/prop canon and conflicts across scenes.

### 4.3 Media Composer (`/media`)

Media Composer becomes the **target selection and request preparation** workspace while retaining ad-hoc single-job use.

- filter by artifact type and target capability;
- select workflow/model per category, scene, or individual item;
- bulk apply defaults with per-item override;
- show required inputs, missing dependencies, unsupported intent, model availability, and API-submission status;
- invoke Ollama target compiler;
- preview the semantic request and deterministic workflow mapping;
- validate without running;
- `Commit requests` writes approved request snapshots to runtime storage and the published `input` package;
- `Send to Generate` navigates without starting ComfyUI work.

UI-only workflows remain visible as catalog entries but cannot be committed as runnable until a verified API adapter exists. The existing `workflows/api/*` adapters are preferred. The specific `ricky/vid_minmax_h3_r2v.json` intent should use/verify the existing `workflows/api/minimax_h3_r2v_api.json` adapter rather than directly mutating the UI graph.

### 4.4 Generate (`/generate`)

Generate is a resumable dependency dashboard, not a single fire-and-forget button.

Sections are collapsible and ordered:

1. Characters
2. Scene backgrounds
3. Scene/key frames
4. Dialogues
5. Music
6. Video clips
7. Sound effects

Each item shows request version, dependencies, status, selected workflow, attempt history, progress, previews, logs, retry, cancel where supported, accept/reject, and regenerate-with-adjustment. Top-level actions run `Ready items in this section` or `Run all ready`; failures do not erase successful items. Batch scheduling is sequential by default for GPU safety.

Video dependencies depend on chosen mode:

- text-to-video: approved text request only;
- image-to-video: accepted first frame;
- first/last-frame: accepted first and last frames;
- image+audio reference: accepted image and audio;
- image+video+audio reference: accepted image/audio and selected repertoire video.

Sound effects run after accepted video when video-conditioned. Text-only SFX can run without video but remains aligned against the final clip before acceptance.

### 4.5 Audio route integration

Clicking Generate Dialogue opens `/audio` with project/scene context and two collapsible flows.

**Automatic dialogue**

- load the approved scene dialogue and `auto_dialogue_char_map`;
- resolve every speaker to a voice and language;
- validate emotion/style against live catalogs, prompting the user to map or omit unavailable values;
- compile/run timed multi-character TTS;
- split to stable line IDs;
- run optional per-line emotion/style processing;
- variable-stitch using explicit `gap_before_seconds`;
- preview and accept each stage/final scene track.

**Audio Reconstruct**

- default to **Fragmented** recording mode: show exactly one approved dialogue part at a time, display its text in the recorder, highlight the active part, and record only that part with the user's own inflection, sounds, emotion, and style;
- after the user starts the recorder, stream ASR against the highlighted expected line. When the line is complete, show an explicit confirmation and advance to the next part; never advance or cut silently;
- provide a **Continuous** mode toggle. In Continuous mode the user records the whole written section first; final ASR alignment segments the recording against the known dialogue lines and presents every proposed split for user confirmation before processing;
- provide a dedicated recorder button for character calibration. For each character, record one common calibration sentence, then optionally run Noise Cleanup, Voice Changer/reference-voice overlay, and/or RVC/pitch/depth processing in any selected sequence;
- every processing stage is optional and independently runnable. Each output is saved under project storage and immediately shown with an in-page audio player, provenance, and Accept/Use as next input controls;
- save the accepted per-character calibration, including character ID, calibration recording, selected overlay voice, RVC model/index, pitch/depth values, noise-cleanup settings, stage outputs, and skipped stages;
- expose the verified Audio Studio operations directly in reconstruction: Noise Cleanup first if selected, then Voice Changer/reference overlay or RVC, with optional pitch adjustment. Do not force a preset chain;
- save each part as its own immutable versioned take while preserving a stable accepted alias: raw takes are `char1_1_take_001.wav`, `char1_1_take_002.wav`, etc.; the currently accepted logical file is `char1_1.wav` and points to the selected take in the manifest;
- apply the selected character calibration by the part's character ID and provide before/after previews for every selected stage;
- let the user click any prior part and repeat only that part, keeping the same sequence ID while superseding its prior take;
- stitch accepted parts by numeric dialogue sequence, preserving intentional overlap metadata and providing a manual overlap/gap adjustment step;
- keep raw, processed, and accepted versions; do not use speaker diarization because the highlighted script part and filename identify the character.

The source chain is non-destructive: raw → cleaned → overlay → RVC → accepted. The “hear after each stage” preference controls autoplay/preview prompts, not whether files are retained.

### 4.6 Video repertoire

Use the separate Video & Animation Repertoire page and storage contract already planned in `docs/Ace_step_refine.md`. Story Builder consumes only stable repertoire asset IDs and searchable sidecar/manifest descriptions. Initial search is lexical/full-text over normalized descriptions; semantic embeddings are a later measured enhancement. Manual upload/file selection remains available.

## 5. Data contracts and filesystem layout

### 5.1 Runtime workspace

```text
storage/projects/<project-id>/
  project.json
  input/
    story.txt                 # latest saved Canvas story for this project
    manifest.json
  revisions/
    novel/<revision-id>.json
    screenplay/<revision-id>.json
  artifacts/
  analysis/<revision-id>.json
  canon/canon.json
  production/scenes/<scene-id>.json
  prompt_packs/<artifact-kind>/<artifact-id>/<revision-id>.json
  requests/<artifact-kind>/<request-id>/
    request.json
    workflow_snapshot.json
    validation.json
  jobs/<domain>/<job-id>/
  audio/
  images/
  video/
  output/<scene-id>/
  logs/
```

Keep compatibility readers/migration for existing `artifacts/*.json`, `media_jobs`, audio job directories, and existing project JSON.

### 5.2 Project input package

```text
storage/projects/<project-id>/input/
  manifest.json
  story.txt
  story_script.txt
  story_script.json
  planning.json
  characters/
    characters.json
    prompts/
  scene_backgrounds/
    prompts/
  keyframes/
    prompts/
  dialogues/
    <scene-id>.txt
    <scene-id>.json
  character_maps/
    auto_dialogue_char_map.json
    audio_reconstruct_char_map.json
  audio_reconstruct/
    calibration/
    takes/
    processed/
    stitch/
  background_music/
    <scene-id>.txt
    <scene-id>.json
  video_clips/
    <shot-id>.txt
    <shot-id>.json
  sound_effects/
    <scene-id>.txt
    <scene-id>.json
  camera_lighting/
    <scene-id>.json
  requests/
    images/
    dialogues/
    music/
    video/
    sound_effects/
```

Folders contain approved prompts/plans and committed request snapshots, not generated binaries. Text projections are for people; JSON is authoritative for the application.

### 5.3 Accepted output package

```text
storage/projects/<project-id>/output/
  manifest.json
  characters/
  scene_backgrounds/
  keyframes/
  dialogues/
  background_music/
  video_clips/
  sound_effects/
```

Every accepted output manifest links project ID, source artifact/revision, request ID, workflow ID/hash, seed/settings, candidate origin, timestamps, and relative file path. Do not duplicate story source text into `output` unless creating a deliberate archival export.

## 6. Backend design

Split new functionality into focused services rather than expanding `api/main.py` or `StoryPipeline`:

```text
services/story_revisions.py
services/story_analysis.py
services/screenplay.py
services/production_planning.py
services/prompt_compiler.py
services/request_store.py
services/dependency_graph.py
services/generation_queue.py
services/project_publish.py
services/asr/
  base.py
  qwen.py
  whisper.py
  alignment.py
```

Add Pydantic/JSON Schemas under a central `schemas/` package. API routes should be separated by domain routers. All writes use atomic temp-file replacement and project-level locking/version checks.

Suggested API groups:

```text
POST /api/projects/{id}/novel/revisions
POST /api/projects/{id}/novel/patches/preview
POST /api/projects/{id}/novel/patches/{patch_id}/apply
POST /api/projects/{id}/analysis/jobs
POST /api/projects/{id}/screenplay/outlines
POST /api/projects/{id}/screenplay/scenes/{scene_id}/jobs
POST /api/projects/{id}/production/scenes/{scene_id}/jobs
PUT  /api/projects/{id}/artifacts/{kind}/{artifact_id}
POST /api/projects/{id}/compile/jobs
POST /api/projects/{id}/requests/commit
GET  /api/projects/{id}/dependencies
POST /api/projects/{id}/generation/runs
GET  /api/projects/{id}/generation/runs/{run_id}
POST /api/projects/{id}/outputs/{candidate_id}/accept
POST /api/projects/{id}/publish
POST /api/projects/import
```

Existing APIs remain during migration. New queue workers initially run in-process with persisted job state and recovery-on-start; move to a dedicated worker only if concurrency/reliability measurements justify it.

## 7. Workflow registry and compiler

Replace filename/class-name guessing as the execution contract with versioned, reviewed manifests:

```json
{
  "workflow_id": "minimax_h3_r2v",
  "workflow_version": "1",
  "sha256": "...",
  "category": "video",
  "modes": ["image_video_audio_reference"],
  "api_safe": true,
  "inputs": {
    "prompt": {"type": "string", "required": true, "binding": "reviewed adapter key"},
    "image": {"type": "asset:image", "required": true},
    "reference_video": {"type": "asset:video", "required": true},
    "audio": {"type": "asset:audio", "required": true}
  },
  "outputs": ["video"]
}
```

Each adapter must pass fixture tests proving prompt injection, every asset binding, safe numeric overrides, filename prefixing, and output collection. Changes to the JSON hash invalidate prior unrun snapshots. Raw `ricky/` workflows are source references; execution uses audited API copies.

## 8. ASR decision

Do not bake one ASR engine into UI or audio services. Define an engine interface for session start, chunk ingestion, partial transcript, final transcript, and optional alignment.

No additional launch-language requirement is being introduced. Benchmark against the languages and accents actually used in the project.

Recommended first benchmark:

- **Primary candidate:** Qwen3-ASR-0.6B for local provisional streaming.
- **Fallback/baseline:** Whisper via `whisper.cpp` or faster-whisper for mature multilingual chunked transcription.
- **Final split:** saved audio + expected script line alignment; use a forced aligner or timestamp-capable offline pass.

Qwen3-ASR streaming is currently vLLM-only, single-stream, and does not return timestamps. Therefore it cannot alone produce reliable cut points. Its 0.6B weights are roughly 1.9 GB, but runtime memory is higher and vLLM compatibility on the actual AArch64/CUDA machine must be proven. Whisper's microphone example is pseudo-streaming and repeatedly transcribes sampled chunks, which is suitable as a fallback but not a reason to couple the UI to Whisper.

**Download decision:** do not download Qwen yet merely to write or begin the core plan. First implement an isolated ASR service/container contract and run architecture, CUDA, disk, and VRAM preflight. Then benchmark Qwen3-ASR-0.6B and one appropriately sized Whisper model on representative project recordings and select defaults from measured streaming latency and transcript quality. The selected engine provides incremental checks; each accepted audio part remains user-confirmed.

The browser microphone requires secure context (`localhost` or HTTPS), explicit permission, selectable input device, level meter, pause/resume/cancel, maximum-duration safeguards, and recovery of the raw recording.

## 9. Three implementation phases and gates

The plan is delivered in exactly three releases. The detailed workstreams below belong to these releases:

1. **Phase 1 — Foundation and story production:** contracts, migrations, Story Canvas, screenplay, and director Story Builder.
2. **Phase 2 — Prompt/media production:** prompt compilation, Media Composer request preparation, Generate page, image generation, and automatic mixed TTS dialogue.
3. **Phase 3 — Audio reconstruction and finishing:** per-character voice calibration, highlighted-part recording/streaming ASR, reconstruction stitching, music, video, sound effects, and hardening.

An implementation phase is not considered complete until its gate passes; later phases may consume only approved artifacts from earlier phases.

### Phase 1A — Freeze contracts and inventory

- Approve the route responsibilities and canonical/runtime/published storage roles above.
- Snapshot example current projects and build a backwards-compatible migration fixture.
- Turn `docs/prompt_gen_story.md` schemas into versioned Pydantic/JSON Schemas.
- Audit all API workflows and record semantic manifests, node bindings, model/node requirements, and hashes.
- Regenerate Graphify over the actual React/FastAPI/services scope and record dependency baselines.

**Gate:** schemas validate representative Trial-I data; no existing project or page is removed; every initially exposed workflow has an audited status.

### Phase 1B — Project schema, revisions, and publishing

- Add stable slug, schema version, artifact registry, revision lineage, status, dependency edges, and migration loader.
- Implement atomic revision storage, optimistic concurrency, stale propagation, publish/export, and safe import.
- Create/update `storage/projects/<project-id>/input/story.txt` on explicit Canvas Save Revision. Saving again for the same project replaces that project’s current story projection; a different project has a separate input directory. Do not trigger analysis, refine, outline, or downstream regeneration automatically.
- Create per-scene directories under `storage/projects/<project-id>/output/` only when the user accepts final scene assets.
- Keep current audio/media paths readable and add stable artifact IDs to new jobs.

**Gate:** create, rename, reopen, migrate, publish, re-publish, and import round-trip without data loss or path escape.

### Phase 1C — Story Canvas

- Add `/canvas`, navigation, document editor, block IDs, autosave recovery, revision history, range-patch preview/diff/apply, and conflict handling.
- Add structured analysis with issue lifecycle.
- Save Revision persists the immutable revision and updates the project input story projection, then hands the same project/revision to `/story`; Analyze, Refine, and Outline remain explicit user actions.
- Load every story-assistance and planning instruction from the versioned contracts in `docs/prompt_gen_story.md`; remove duplicated inline prompt text from backend execution paths. Store prompt template ID/version, model, input revision IDs, raw response, validation, and repaired response when applicable.
- Add narrator choice, screenplay outline, per-scene generation, scene retry/edit/approve, coverage and continuity checks.
- Navigate to `/story` using project/revision IDs, not story text in local storage.

**Gate:** a long sample story can change one paragraph without unrelated changes and generate all screenplay scenes without duplicate/missing scene IDs.

### Phase 1D — Director Story Builder

- Migrate `/story` from raw JSON editors to scene/canon forms while retaining an advanced JSON view.
- Add direct entry/import, production-plan generation per scene, catalogs for emotion/style, timing validation, and global continuity review.
- Add dependency/staleness display and granular regeneration.

**Gate:** all required character, background, keyframe, dialogue, music, camera/lighting, video, and SFX artifacts are editable, schema-valid, and publishable.

**Phase 1 gate:** a user can create or import a story, revise selected text with diffs, review analysis, choose narrator mode, approve the complete screenplay, build director artifacts, and publish a valid input package.

### Phase 2A — Prompt compiler and Media Composer

- Add category/scene/item workflow assignment.
- Make `docs/prompt_gen_story.md` the versioned source of truth for Story Builder, story assistance, scene planning, dialogue, music, video, SFX, and target-specific compiler prompts. Backend prompt builders load the named template/version instead of embedding divergent prompt strings.
- Keep prompt templates separate from deterministic workflow adapters. The LLM may fill declared semantic fields only; the backend injects authoritative manifests and validates the result.
- Implement meta-prompt compiler plus deterministic target adapters, schema repair, missing dependency reporting, preview, validation, and commit.
- Preserve ad-hoc Media Composer execution as a separate mode.

**Gate:** changing an image workflow recompiles only image requests; committed snapshots reproduce the exact workflow input mapping; no UI-only workflow is mislabeled runnable.

### Phase 2B — Generate page: images first

- Add persisted generation runs, sequential queue, cancellation state, retry, recovery, candidate preview, accept/reject, and export provenance.
- Implement Characters → Backgrounds → Keyframes sections and dependency unlocking.
- Reuse existing media execution/output collection through audited adapters.

**Gate:** stop/restart the backend mid-batch, resume safely, accept outputs, and verify the exported tree/manifest.

### Phase 2C — Automatic mixed dialogue

- Connect scene dialogue to the existing timed TTS, character maps, effects, split/stitch, and automation APIs.
- Introduce stable line IDs and `gap_before_seconds` schema.
- Add automatic flow, catalog mismatch resolution, line/stage previews, and accepted scene dialogue export.

**Gate:** a multi-character scene generates, splits, optionally processes, variable-stitches, and exports while preserving speaker/order/timing provenance.

**Phase 2 gate:** selected workflow requests are validated and committed; image assets generate in dependency order; automatic dialogue produces one accepted mixed scene track through the character map.

### Phase 3A — Audio Reconstruct and ASR benchmark

- Build isolated ASR service interface and preflight.
- Benchmark Qwen3-ASR-0.6B and Whisper fallback on the target hardware/data before selecting a default.
- Implement a recorder button for calibration and a recorder button for dialogue parts, with Fragmented as the default and Continuous as an explicit mode toggle.
- In Fragmented mode, highlight one line, stream ASR against that line, confirm completion, then advance. In Continuous mode, record the full section, align/split afterward, and require confirmation for every proposed segment.
- Make Noise Cleanup, Voice Changer/reference overlay, and RVC independently optional processing stages. Show every generated output with an audio player and retain it in project storage.
- Implement calibration recordings per character, overlay/RVC previews, highlighted one-part recording, incremental ASR matching, explicit accept/repeat, deterministic `character_sequence` filenames, per-part processing, and manual overlap/gap adjustment.
- Store automatic and reconstruct character maps separately, with raw/replacement/processed takes.

**Gate:** inaccurate live text cannot silently create cuts; every cut is traceable to audio time ranges and confirmed line IDs; raw takes remain recoverable.

### Phase 3B — Music

- Compile canonical cues to the verified ACE-Step request schema only after target selection.
- Generate after accepted/approved dialogue timing when sync matters; show cue drift and allow adjustment.
- Reuse the existing Music & Sound service and keep refinement work governed by `Ace_step_refine.md`.

**Gate:** cues, request snapshot, output, timing, base checkpoint, and optional adapter are linked and playable.

### Phase 3C — Video and repertoire dependencies

- Add explicit video modes and deterministic readiness rules.
- Integrate accepted frames/audio and repertoire asset selection/search.
- Verify Minimax H3 API adapters and other chosen video workflows with real inputs.
- Generate per shot/scene, retain candidates, and accept clips before downstream SFX.

**Gate:** every mode blocks on exactly its real prerequisites and produces traceable playable video without invented paths.

### Phase 3D — Sound effects and final export

- Reconcile cue timings with accepted video duration.
- Route text-only or video/audio-conditioned cues to verified Control-Foley/Hunyuan paths.
- Generate/preview/accept per scene and publish the complete output manifest.

**Gate:** final output package is complete, internally linked, replayable, and reports any deliberately omitted artifact.

**Phase 3 gate:** reconstructed dialogue is reviewable part-by-part and stitch-adjustable; music, video, and SFX dependencies resolve; the final output package is complete and reproducible.

### Phase 3E — Hardening and documentation

- End-to-end tests for recovery, stale propagation, malformed LLM JSON, offline Ollama/ComfyUI/ASR, unavailable models/nodes, disk exhaustion, path validation, upload limits, and concurrent edits.
- Accessibility/keyboard testing for Canvas, diff, collapsibles, recording, and media previews.
- Performance tests for long stories and many-scene queues.
- Update README, API reference, workflow matrix, Graphify report, and operator runbooks.

**Gate:** all existing backend tests and frontend builds pass, new E2E fixtures pass, and documentation matches the running routes/storage.

## 10. Test strategy

- **Schema/unit:** IDs, timing ranges, slug/path validation, compiler mappings, workflow hashes, invalidation rules.
- **Prompt contract:** mocked Ollama outputs, malformed JSON repair, narrator modes, scene coverage, unsupported capability warnings.
- **Storage:** migrations, atomic writes, publish idempotence, title rename, collisions, restore, stale descendants.
- **Integration:** Ollama offline/online, each approved ComfyUI adapter, TTS/effects/music/foley services, ASR adapters, output collection.
- **Frontend:** selection patching, revision conflicts, page reload recovery, direct `/story` import, request commit, dependency dashboard, per-part rerecord, calibration setup, and overlap adjustment.
- **E2E acceptance fixture:** use `storage/projects/<project-id>/input/` to produce an approved novel/script, one planned scene, image candidates, multi-character dialogue, music, video, SFX, and a verified per-scene output manifest.

Never require live AI services for the full unit suite. Mark hardware/live workflow tests separately and retain their manifests as evidence.

## 11. Risks and mitigations

- **LLM output drift:** strict schemas, one bounded repair, stable IDs, review gates, stored raw responses.
- **Long-context loss:** outline first, scene-by-scene generation, compact canon/handoffs, coverage validator.
- **Continuity damage after edits:** revision lineage and dependency-driven stale markers, never silent cascade regeneration.
- **Workflow graph fragility:** reviewed semantic adapters and hashes; do not let an LLM patch arbitrary nodes.
- **GPU contention:** persistent queue, one active GPU job, preflight and visible resource errors.
- **ASR mismatch:** incremental text is a guidance/check signal; the user explicitly accepts or repeats each highlighted part, so no automatic speaker diarization or hidden cut decision is allowed.
- **Local-storage loss:** backend is authoritative; local storage only recovers drafts/navigation.
- **Folder/title collisions and path traversal:** immutable slug, configured roots, normalized server-side paths.
- **Accidental overwrite of generated/voice assets:** immutable raw/candidate storage, explicit acceptance/export, separate character maps.
- **Scope explosion:** deliver vertical slices in the gated order above; existing pages stay usable throughout.

## 12. Resolved ambiguities and remaining decisions

Resolved here:

- Add Story Canvas and Generate; keep all current pages.
- Use FastAPI as the WebUI backend and sole execution gateway.
- Use Ollama for story/script/planning and target prompt compilation, with deterministic validation/mapping.
- Store runtime truth in `storage`, publish approved inputs to `input`, and export accepted binaries to `output`.
- Generate screenplay scene by scene after a global outline and narrator choice.
- Keep automatic and Audio Reconstruct voice maps project-specific and separate.
- Use explicit per-line gaps keyed by stable segment IDs.
- Put video before final video-conditioned SFX.
- Reuse the Video & Animation Repertoire plan rather than duplicating it here.
- Benchmark Qwen3-ASR 0.6B behind an adapter; retain Whisper fallback; do not download until preflight exists.

Decisions to make during gated workflow audit, not by assumption:

- which workflows are approved defaults for each video mode after live validation;
- project `input/` contains the latest saved story and approved request projections; complete request history remains under `storage/projects/<project-id>/requests/` and is referenced from `storage/projects/<project-id>/input/manifest.json`.

None of these blocks Phases 0–3. They become explicit gates before the affected execution feature is labeled available.

## 13. Definition of done

The full feature is complete when a user can create or import a story, revise only selected passages with visible diffs, review loose ends, choose narrator mode, generate/approve every screenplay scene, prepare director-level scene artifacts, select workflows, commit validated request snapshots, and run the dependency-ordered production queue. They can choose automatic dialogue or record/reconstruct every line, preview intermediate voice stages, control dialogue gaps, select repertoire references, and generate/accept images, dialogue, music, video, and sound effects. Closing/reopening the app preserves state; upstream edits expose stale downstream work; and the published `input` plus accepted `output` trees are reproducible from manifests without deleting or breaking the existing WebUI modules.
