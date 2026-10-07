# ACE-Step Refinement/Fine-Tuning Plan

## Decision

ACE-Step refinement will run in a dedicated, on-demand Docker container. It will not install packages into ComfyUI, modify ComfyUI custom nodes, or share ComfyUI's Python environment.

The Story Builder backend will start the refinement service only when a refinement job is requested, monitor it, collect the resulting LoRA adapter/checkpoint, and stop the container when the job finishes or is cancelled. Generated adapters remain on the host in a managed directory and can later be selected by compatible ACE-Step inference code.

This is technically possible, but it must pass an AArch64/CUDA smoke test before the UI may claim that training is available.

This plan also adds a separate **Video & Animation Repertoire** page. The video analyzer consumes a user-selected local folder of videos; it does not download videos as part of analysis. YouTube downloading is a separate optional tool on the same page because downloaded references and analyzed references are reusable visual assets rather than generated music.

## What the local trainer actually requires

The preserved ACE-Step source contains:

- `audio/song_gen/ACE-Step/convert2hf_dataset.py` for converting training triplets into a Hugging Face dataset;
- `audio/song_gen/ACE-Step/trainer.py` for PyTorch Lightning LoRA training;
- `audio/song_gen/ACE-Step/requirements.txt` with PyTorch, PEFT, Lightning, Transformers, Diffusers, audio, and logging dependencies;
- a CUDA Dockerfile, but its current default command starts the generation GUI rather than a refinement worker.

Each training example currently requires three files with the same basename:

```text
song_001.mp3
song_001_prompt.txt
song_001_lyrics.txt
```

The current converter actually requires all three files, despite the upstream prose calling lyrics optional: it skips a sample when either companion text file is absent. Story Builder must therefore treat both text files as required unless its own audited converter is deliberately extended and tested.

### Dataset authoring guidelines

Use one stable, filesystem-safe basename per training item:

```text
data/
  nocturne_001.mp3
  nocturne_001_prompt.txt
  nocturne_001_lyrics.txt
  nocturne_002.mp3
  nocturne_002_prompt.txt
  nocturne_002_lyrics.txt
```

Rules:

- Basenames must match exactly, including capitalization. Use letters, numbers, `_`, and `-`; do not use spaces or duplicate names.
- Audio accepted by the preserved converter is MP3. The preparation layer may accept WAV/FLAC uploads, but must normalize them to MP3 before conversion and retain the originals.
- Use clean, full-quality music with no clipping, corrupt duration, long leading/trailing silence, advertisements, or unrelated material.
- Keep a coherent target concept across a refinement dataset. Do not mix unrelated genres, production styles, languages, or vocal identities unless that mixture is explicitly the intended adapter behavior.
- Split very long tracks into bounded segments before training. Preserve musically sensible boundaries and avoid cutting words, attacks, or sustained notes abruptly. The existing preparation candidate supports configurable segment length and overlap; those values must be validated empirically rather than silently fixed.
- `*_prompt.txt` contains only accurate comma-separated tags: genre, vocal type, instruments, mood/energy, tempo/BPM, key when known, production texture, and relevant performance style. Do not insert prose, filenames, or unsupported JSON.
- `*_lyrics.txt` contains the exact lyrics heard in that audio, including useful `[Verse]`, `[Chorus]`, `[Bridge]`, and instrumental markers. Do not invent unheard words. For instrumental data, use a consistent audited marker such as `[instrumental]`; confirm it survives dataset loading before training.
- Every source must be legally usable for training. Store source/provenance and consent/license metadata in the dataset manifest even though the upstream converter does not consume it.

Example prompt:

```text
melodic techno, female vocal, electronic, emotional, minor key, 124 bpm, synthesizer, driving, atmospheric
```

Example lyrics:

```text
[Verse]
Exact words heard in this segment

[Chorus]
Exact repeated chorus
```

Before conversion, the UI reports matched triplets, missing companions, duplicates, audio duration/sample rate/channels, silence/clipping warnings, transcript emptiness, and total usable duration. It produces a reviewable dataset manifest before the user can start refinement.

The trainer additionally needs:

- the full ACE-Step base checkpoint directory, not only the single ComfyUI `.safetensors` file unless a verified conversion/mapping proves otherwise;
- a LoRA configuration JSON;
- the converted dataset directory;
- MERT `m-a-p/MERT-v1-330M` weights;
- `utter-project/mHuBERT-147` weights;
- writable checkpoint, log, cache, and result directories;
- an NVIDIA GPU visible inside the container.

The current trainer hard-codes `accelerator="gpu"` and uses a distributed strategy. A one-GPU smoke test must prove that this configuration works unchanged; otherwise a small Story Builder-owned launcher will select an appropriate single-device strategy without editing the preserved upstream trainer.

## Isolation and filesystem layout

Create a new runtime separate from the existing audio-utility containers:

```text
runtimes/ace-step-refine/
  Dockerfile
  docker-compose.yml
  worker.py
  entrypoint.sh
  requirements.lock
```

Host-managed data:

```text
storage/projects/<project-id>/music/ace_refine/
  datasets/<dataset-id>/source/
  datasets/<dataset-id>/prepared/
  jobs/<job-id>/request.json
  jobs/<job-id>/status.json
  jobs/<job-id>/logs/
  jobs/<job-id>/checkpoints/
  jobs/<job-id>/validation/

models/ace_step/adapters/<adapter-id>/
  adapter files
  manifest.json
  training_request.json
  dataset_summary.json
  validation_results.json
```

### Refined model placement and selection

The preserved trainer performs LoRA refinement. Its `on_save_checkpoint` calls `save_lora_adapter`, so the expected result is an adapter directory—commonly adapter weights in `.safetensors` plus adapter configuration—not a replacement 3.5B base `.pth`/`.safetensors` model.

The current base model is:

```text
/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/models/checkpoints/ace_step_v1_3.5b.safetensors
```

Do not overwrite or rename that file. Approved refined outputs will be registered alongside the ACE-Step family but kept visibly separate:

```text
/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/models/checkpoints/ace_step_v1_3.5b.safetensors
/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/models/ace_step_adapters/<adapter-name>/adapter_model.safetensors
/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/models/ace_step_adapters/<adapter-name>/adapter_config.json
/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/models/ace_step_adapters/<adapter-name>/manifest.json
```

The exact adapter directory must follow the active ComfyUI ACE-Step node's proven loader contract. Until that is verified, export first to Story Builder's adapter registry and copy nothing into ComfyUI.

Music Creation will present two related selectors:

- **Base model:** the compatible ACE-Step foundation checkpoint.
- **Refinement:** `None (base only)` or one compatible named LoRA adapter.

This is more accurate than displaying a LoRA as an independent base model. The manifest records which base model hash/version the adapter requires. If a future refinement process produces a genuinely merged/full checkpoint, it may appear as another base-model choice only after load and generation tests pass.

Mounted container paths:

- source code: read-only;
- base checkpoints: read-only;
- Hugging Face cache: persistent and separate from ComfyUI;
- project dataset/job directory: read/write only for the selected job;
- final adapter registry: write access only during the controlled export step.

Do not mount the ComfyUI installation as writable. Do not copy adapters into ComfyUI automatically until the active ACE-Step node's adapter-loading contract has been verified.

## Container lifecycle

1. The user creates and validates a dataset in Story Builder.
2. Story Builder performs a host-side preflight: Docker, architecture, NVIDIA runtime, free disk, source triplets, checkpoint directory, and LoRA config.
3. The backend creates an immutable job request and starts `story-ace-refine` for that job.
4. The container converts the dataset when needed and starts a bounded training run.
5. The worker writes structured progress and streams logs; the backend never infers progress by scraping arbitrary console text alone.
6. Checkpoints are written into the project job directory.
7. A validation generation compares the base model and the new adapter with the same prompt/seed.
8. Only a successful, explicitly selected checkpoint is exported to `models/ace_step/adapters/<adapter-id>/`.
9. The container exits and is removed. Persistent model/cache/output volumes remain.

Only one refinement job may use the GPU initially. If ComfyUI holds too much VRAM, the UI must report that clearly. Story Builder must not silently stop ComfyUI; the user can stop it or approve a future GPU scheduler that pauses and resumes services safely.

## Backend contract

Add friendly Story Builder APIs rather than exposing Docker commands:

```text
GET    /api/music/ace-refine/capabilities
GET    /api/music/ace-refine/base-models
GET    /api/music/ace-refine/adapters
POST   /api/projects/{project_id}/music/ace-refine/datasets/validate
POST   /api/projects/{project_id}/music/ace-refine/datasets/prepare
POST   /api/projects/{project_id}/music/ace-refine/jobs
GET    /api/projects/{project_id}/music/ace-refine/jobs/{job_id}
POST   /api/projects/{project_id}/music/ace-refine/jobs/{job_id}/cancel
POST   /api/projects/{project_id}/music/ace-refine/jobs/{job_id}/export
```

The training request will contain only validated high-level settings:

- dataset ID;
- base checkpoint ID;
- adapter name;
- LoRA rank, alpha, dropout, and target modules from safe presets;
- learning rate, maximum steps, batch/accumulation settings, precision, workers, checkpoint interval, and seed;
- smoke, preview, or full training profile.

Hermes and the browser use these APIs. Neither receives shell access to Docker or edits `trainer.py`.

## Music & Sound UI

The existing ACE-Step Fine-tune area becomes five explicit stages:

1. **Dataset** — upload multiple MP3/prompt/lyrics triplets or a folder, show basename matching, duration, missing companions, duplicates, and invalid media.
2. **Preflight** — show Docker/NVIDIA/AArch64 status, base checkpoint availability, cached auxiliary models, disk space, GPU memory, and ComfyUI GPU contention.
3. **Refinement settings** — select base model and a safe LoRA/training preset; advanced values stay collapsed.
4. **Training job** — Start, Cancel, progress, current step, loss, elapsed time, logs, and checkpoint list.
5. **Validate and export** — render the same prompt with base and refined adapters, play both results, select a checkpoint, name it, and export it to the adapter registry.

The Start button remains disabled until every required preflight check passes. It must explain the exact missing requirement rather than showing a generic unavailable state.

The form must expose bounded training controls with safe presets: repeat count, segment length/overlap, LoRA rank/alpha/dropout, learning rate, maximum steps, checkpoint interval, precision, workers, gradient accumulation, gradient clipping, seed, resume checkpoint, and output adapter name. It must explain that more steps or repeated samples can overfit rather than presenting them as automatic quality improvements.

## Video & Animation Repertoire Page

Add a dedicated route such as `/video-repertoire` with two independent tools: **YouTube Download** and **Video Summarizer & Reference Clips**. The summarizer receives an input folder or selected local repertoire assets; it never invokes YouTube downloading implicitly. It must not be mixed into Music & Sound.

### Repertoire storage

Default host library:

```text
/home/riki/web_dev/story_builder/video_repertoire/
  downloads/
  analyses/
  clips/
  manifests/
```

The user may choose another output folder, but the backend must validate it against configured approved roots. A browser-provided arbitrary server path must not grant unrestricted filesystem access. Each imported video receives a stable asset ID and manifest containing source URL, title, uploader/channel where available, download time, yt-dlp metadata, file hash, duration, codec/resolution, license/provenance notes, and derived artifacts.

### YouTube Download

Reuse the behavior in `youtube_code/youtube_dwnld.py` and the existing `video_summariser` search/download functions, but place a safe Story Builder wrapper around them. The page supports exactly three mutually exclusive source modes:

- **Search:** enter a text query and the requested number of links; the service searches YouTube, populates a reviewable URL list, and lets the user remove individual results before downloading;
- **URL file:** upload a UTF-8 `.txt` file containing one URL per non-empty line;
- **Paste URLs:** paste one or multiple URLs, one per line.

Search is optional. File and pasted-list modes bypass search completely. The UI shows the resolved URL list before download, rejects blank/invalid entries, deduplicates URLs, and preserves the source mode in the batch manifest.

All modes then share:
- default output `video_repertoire/downloads/`;
- an optional approved output folder;
- maximum resolution/quality selection, initially defaulting to the existing 720p policy;
- batch status per URL, cancellation, retry, error display, and completed-file links.

The wrapper uses `yt-dlp` arguments constructed by Story Builder, never arbitrary user CLI flags. It retains `noplaylist` by default, merges/remuxes with FFmpeg when required, sanitizes filenames, prevents overwrites through asset IDs or suffixing, and writes a manifest even when one item in a batch fails. Search results are not downloaded until the user confirms the populated list.

The UI must remind users to download only content they are permitted to store and reuse. Authentication cookies, playlist expansion, private content, and site-wide scraping are outside the first implementation gate.

Suggested APIs:

```text
GET  /api/video-repertoire/capabilities
POST /api/video-repertoire/youtube/jobs
GET  /api/video-repertoire/youtube/jobs/{job_id}
POST /api/video-repertoire/youtube/jobs/{job_id}/cancel
GET  /api/video-repertoire/assets
GET  /api/video-repertoire/assets/{asset_id}
```

### Video Summarizer & Reference Clips

The user supplies either:

- an input folder from an approved root;
- selected videos already in the repertoire; or
- uploaded video files.

This analysis tool does not accept a YouTube query and does not download anything. Its default input is the existing `video_repertoire/downloads/` folder, but any approved local input folder may be selected.

Default analysis output is `video_repertoire/analyses/<job-id>/`, with extracted reference clips copied to `video_repertoire/clips/<asset-id>/`.

The local repository contains useful pieces but not one fully proven summarizer contract:

- `youtube_code/frame_extract.py` extracts interval, key, scene, or scene+key frames;
- `youtube_code/video_clipper/` searches sliding video windows and extracts clips;
- its InternVideo2 integration still contains a documented repository-specific loader TODO, so mock scoring must never be presented as real semantic analysis;
- `youtube_code/AI_text_analysis.py` summarizes transcript text for a financial-analysis use case and is not by itself a general video describer.

Before implementation, identify the user's previously created video summarizer entry point if it exists elsewhere and document its exact inputs/model/output schema. Do not silently substitute the mock clip scorer or market-transcript analyzer.

The normalized summarizer output contract will be:

```text
video_repertoire/analyses/<job-id>/<video-id>/
  source_manifest.json
  video_summary.md
  timeline.json
  segments/
    segment_0001.mp4
    segment_0001.txt
    segment_0001.json
  frames/
  run_manifest.json
```

Each timeline/segment record includes start/end timestamps, concise visual description, subjects/actions, setting, camera/framing/motion, notable transitions, transcript/speech when available, confidence/model provenance, source video ID, and clip path. Cropping means temporal clip extraction by default; spatial cropping must be a separate explicit option so aspect ratio/content is not accidentally changed.

The page shows input/output selectors, analysis model/status, scene/interval controls, minimum/maximum clip duration, overlap, whether to extract clips, batch progress, summaries, timeline rows, clip playback, and searchable descriptions. Later Story Builder/Hermes reference selection consumes these manifests rather than rescanning raw video.

Suggested APIs:

```text
GET  /api/video-repertoire/summarizer/capabilities
POST /api/video-repertoire/summarizer/jobs
GET  /api/video-repertoire/summarizer/jobs/{job_id}
POST /api/video-repertoire/summarizer/jobs/{job_id}/cancel
GET  /api/video-repertoire/search?q=...
```

### Video implementation phases

#### Phase V1 — Optional YouTube downloader and library

- Repair/refactor the current interactive downloader into a deterministic service.
- Add search-query + count mode, URL-file mode, pasted-URL mode, review-before-download, safe paths, manifests, batch state, cancellation, and repertoire browsing.
- Test one URL, pasted batches, text-file batches, duplicates, invalid URLs, partial failures, and FFmpeg merge behavior.

**Gate:** downloads are reproducible, attributable, playable, and safely stored in the default or approved output root.

#### Phase V2 — Folder-only summarizer discovery and contract

- Locate and run the real existing folder-based video summarizer.
- Inventory its model/checkpoint, AArch64/GPU requirements, accepted video formats, text schema, clip extraction behavior, and dependencies.
- Adapt its output into the normalized summary/timeline/segment manifest without discarding its originals. Do not add YouTube download calls to this runner.

**Gate:** one representative video produces accurate text plus timestamp-aligned playable clips; no mock scorer is used.

#### Phase V3 — Video & Animation Repertoire UI

- Add navigation, downloader, batch history, asset browser, summarizer form, summary/timeline viewer, clip player, and search.
- Expose the same high-level APIs to Hermes without shell commands or unrestricted paths.

**Gate:** browser and Hermes can import, summarize, inspect, and reuse the same repertoire assets with complete provenance.

## AArch64 and CUDA validation

The container image must be built for `linux/arm64`. Before full training:

1. Build the image locally on AArch64; do not rely on an amd64-only binary layer.
2. Verify `torch.cuda.is_available()` and report the GPU, CUDA, cuDNN, Torch, and compute capability versions.
3. Import TorchAudio, PEFT, Lightning, Transformers, Diffusers, MERT, and mHuBERT.
4. Load the actual base checkpoint read-only.
5. Convert a tiny two-example dataset.
6. Run one forward/backward optimizer step.
7. Save and reload a tiny LoRA checkpoint.
8. Run one short validation generation using that adapter.

Failure at any gate leaves refinement disabled but does not affect ACE-Step generation or ComfyUI.

## Implementation phases

### Phase R1 — Audit and immutable inputs

- Identify the exact base checkpoint directory expected by `ACEStepPipeline`.
- Compare it with the checkpoint currently used by the ComfyUI ACE-Step node.
- Record required auxiliary model revisions and licenses.
- Define the LoRA config presets and adapter output format.
- Add dataset triplet validation tests.
- Confirm MP3 normalization, segment length/overlap policy, prompt-tag rules, exact lyric handling, and dataset repeat-count behavior.

**Gate:** all required files and model formats are known; no assumed checkpoint conversion remains.

### Phase R2 — AArch64 refinement container

- Create the dedicated ARM64 CUDA image and locked dependencies.
- Add a non-root worker and read-only source/model mounts.
- Add capability/preflight reporting.
- Run imports, GPU detection, model loading, and one-step training tests.

**Gate:** the container saves and reloads a LoRA checkpoint without modifying ComfyUI.

### Phase R3 — Managed job backend

- Add dataset preparation, job persistence, structured progress, cancellation, checkpoint collection, safe export, and stale-container recovery.
- Enforce one GPU refinement job at a time.
- Add disk limits, path validation, timeouts, and failure preservation.

**Gate:** a smoke job can be started, monitored, cancelled, resumed from an accepted checkpoint where supported, and exported through Story Builder APIs.

### Phase R4 — Web UI and Hermes contract

- Implement the five-stage refinement UI.
- Add the same typed operations to the Hermes Story Builder runner/skill.
- Do not expose raw Docker commands, host paths outside approved roots, or arbitrary trainer arguments.

**Gate:** browser and Hermes can prepare and run the same bounded smoke job with matching manifests.

### Phase R5 — Inference integration

- Verify how the active ComfyUI ACE-Step node discovers and applies LoRA adapters.
- If supported, add an adapter dropdown and refresh endpoint without restarting ComfyUI when possible.
- If not supported, keep refined inference in an isolated ACE-Step inference container until a fixed compatible ComfyUI workflow is proven.
- Compare base/refined outputs and record adapter/base compatibility in the manifest.
- Add the Base model and Refinement dropdowns to ACE-Step Music Creation after the loader is proven.

**Gate:** a selected adapter reliably changes generation, can be disabled to reproduce the base path, and does not require manual model-file copying.

## Safety rules

- Never install refinement dependencies into ComfyUI's environment.
- Never overwrite a base model or existing adapter.
- Never stop/restart ComfyUI automatically without explicit user approval.
- Never allow arbitrary Docker images, commands, mounts, trainer modules, or output paths from API input.
- Preserve failed-job logs and partial checkpoints inside the project; export only an explicitly selected valid adapter.
- Pin image and Python dependency versions after the first successful AArch64 smoke test.

## Definition of done

ACE-Step refinement is complete only when a real AArch64 GPU run:

- validates and prepares a representative dataset;
- starts the container on demand and releases it afterward;
- trains and reloads a LoRA adapter;
- produces a base-versus-refined validation pair;
- exports the adapter with full provenance;
- makes that adapter selectable through a proven inference path;
- works from both the web UI and Hermes APIs;
- leaves ComfyUI and existing ACE-Step generation unchanged.
