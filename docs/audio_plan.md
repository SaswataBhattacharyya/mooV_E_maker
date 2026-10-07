# Modular Audio Workflow Plan

## Next implementation revision — Audio layout, Control-Foley, and Automation

This section records the implemented Audio layout, Control-Foley, and Automation pass. Where older Phase 9 or Phase 11 text below conflicts with it, this section wins.

### 1. Audio Studio layout cleanup

Audio Studio remains the place for configuring and manually running individual speech operations, but it will no longer contain the pipeline builder.

- Move **Add reference voice** and **Project character map** above both the capability/block library and the voice/model/system catalogs.
- Replace the always-expanded block-card column with a compact **Block Library** disclosure/dropdown. Opening it shows the registered blocks, phase/status, executor, and short capability description.
- Remove **Noise Cleanup** from the Audio Studio block catalog and operation controls. Noise Cleanup is already implemented on **Audio Utilities** and must have one UI home only.
- Keep Voice Repair in Audio Studio; it is distinct from deterministic noise cleanup.
- Remove the planned unified audio pipeline UI from Audio Studio. Individual block forms and their direct API jobs remain there.
- Preserve all already working Phase 1–8 forms, APIs, workflows, voice discovery, character maps, TTS, split/stitch, and effects while changing layout.

### 2. Replace Hunyuan Foley with Control-Foley

The **Music & Sound** page will remove the blocked Hunyuan Foley card and replace it with a working **Control-Foley Sound Effects** section based on the preserved source workflows in:

```text
workflows/ricky/control folley/
```

The original workflow files remain untouched. Story Builder will create one cleaned, fixed API-format workflow per supported mode under `workflows/api/audio/control_foley/`. Users and Hermes select a friendly mode; neither edits node IDs or constructs ComfyUI graphs.

#### Verified mode mapping

| UI mode | Source workflow | Required inputs | Disabled inputs | Primary output |
|---|---|---|---|---|
| **Text → Audio** | `05_t2a_basic.json` | text prompt | video, reference audio | WAV audio |
| **Text + Video → Audio** | `02_tcv2a_text_controlled.json` (with `control_folley.json` retained as a comparison fixture) | text prompt, video | reference audio | WAV audio |
| **Reference Audio + Video → Audio** | `03_acv2a_audio_controlled.json` | reference audio, video | text prompt by default | WAV audio |

Important discovery: the supplied “audio controlled” workflow contains `LoadControlFoleyVideo` and connects video to `ControlFoleyGenerate`. It is therefore not a true audio-only Audio → Audio workflow. The UI must not claim otherwise. If a genuine audio-only workflow is later supplied and passes schema/live validation, it can replace this label or become a fourth mode.

`control_folley_research.json` is a video-only research fixture and `06_advanced_chain.json` is an advanced text-to-audio optimization fixture. Neither is initially exposed as a normal user mode. Advanced compile/offload controls may be added only after the three primary API workflows pass.

#### Dynamic Control-Foley form

- A mode dropdown controls which fields are enabled and required.
- Text field: enabled for Text → Audio and Text + Video → Audio; disabled for reference-audio-controlled mode unless live node validation proves prompt blending is useful.
- Video upload/selection: enabled for the two video-conditioned modes; disabled for Text → Audio.
- Reference-audio upload/selection: enabled only for Reference Audio + Video → Audio.
- Shared friendly controls: duration, seed, seed mode, inference steps, guidance/CFG, frame rate, output filename, and safe tested model/device/dtype controls.
- The backend stages uploads into approved ComfyUI input locations, injects only validated values into a fixed workflow, queues through ComfyUI, collects the WAV, and exports it under `output/<project-id>/audio/` with request/workflow/result provenance.
- Although video workflows also contain mux nodes, the required primary result is the audio file. A muxed preview may be retained as a secondary artifact when produced, but it is not required by downstream pipelines.
- Capability discovery must verify the Control-Foley node classes, model path/assets, active schemas, and ComfyUI reachability before enabling Run.

#### Control-Foley API/Hermes contract

Expose friendly endpoints equivalent to:

```text
GET  /api/music/control-foley/capabilities
GET  /api/music/control-foley/schema
POST /api/projects/{project_id}/music/control-foley/jobs
GET  /api/projects/{project_id}/music/control-foley/jobs/{job_id}
```

The job request contains `mode`, typed input artifact IDs/uploads, and friendly settings. The response contains job status, resolved mode, input provenance, ComfyUI prompt ID, primary audio artifact, optional muxed artifact, and export path. Hermes calls Story Builder only; it does not call ComfyUI localhost directly.

### 3. ACE-Step remains Music Maker

The existing ACE-Step Music Maker stays on **Music & Sound**. Its fixed API workflow and successful live music-generation path remain unchanged. Control-Foley is the Sound Effects section beside it; it does not replace ACE-Step music generation.

### 4. Move unified pipelines to Automation

Phase 9 moves from Audio Studio to the existing `/automation` page. **Audio Automation** becomes one automation type alongside later story/image/video automation.

The first version is an ordered pipeline editor, not a free-form ComfyUI graph editor. Users add registered Story Builder blocks, reorder them, configure each step, connect compatible artifacts, validate, save, and run. Hermes uses the same saved pipeline schema and runner APIs.

#### Pipeline definition

Each saved project pipeline records:

- pipeline ID, name, version, project, creator (`user` or `hermes`), and timestamps;
- ordered step IDs and registered operation IDs;
- typed parameter values;
- explicit input bindings (`upload`, `project artifact`, or `previous step output`);
- expected output artifact types;
- retry/caching policy and whether a completed upstream step may be reused;
- validation errors, run state, step job IDs, output manifests, and final export.

Hermes never writes raw workflow JSON. It calls a block registry/schema endpoint, creates or updates a pipeline using friendly JSON, validates it, and starts a run. The UI performs the same calls.

#### Dynamic manual inputs

Selecting a block renders its actual typed form rather than a generic path box:

- **Timed Multi-Character TTS:** SRT text or `.srt` upload, saved character map, shared base model, language/timing/generation settings, and optional project artifact binding. The UI validates the SRT character labels against the map before running.
- **Split Audio:** source audio binding plus the split definition required by the registered splitter—structured scene rows or the accepted JSON/text manifest. The UI offers both a row editor and file import, then previews boundaries.
- **Emotion/Style/Voice effects:** source audio or selected split-clip binding plus transcript/instruction and operation-specific settings.
- **Stitch Audio:** ordered clip bindings/replacements plus the accepted edit/timing manifest. The UI shows the resolved filename/clip order before execution; it does not rely on unexplained filename sorting.
- **Noise Cleanup:** source audio, denoiser model, dry/wet value, and output collection. The block executes through Audio Utilities even though it is configured inside Automation.
- **Demucs/extraction/music/Control-Foley:** their existing typed schemas are reused when added to a compatible automation.

The editor asks for uploads only when an input is not connected to an earlier compatible output. When a previous step supplies the artifact, the upload/path field is disabled and the binding is shown explicitly.

#### First Audio Automation acceptance pipeline

```text
Timed Multi-Character TTS
  → generated dialogue audio + adjusted SRT/timing artifacts
  → Split Audio using an explicit validated split manifest
  → Emotion Change on exactly one chosen clip
  → Stitch Audio using explicit ordered clip/replacement bindings
  → final project audio export
```

The runner persists each step. Retrying Emotion or Stitch must reuse completed TTS and Split results. The run manifest records all child job IDs and proves which edited and untouched clips entered Stitch.

#### Automation APIs and Hermes instructions

Provide a stable high-level contract such as:

```text
GET    /api/automation/blocks
GET    /api/automation/blocks/{operation_id}/schema
POST   /api/projects/{project_id}/automation/pipelines
PUT    /api/projects/{project_id}/automation/pipelines/{pipeline_id}
POST   /api/projects/{project_id}/automation/pipelines/{pipeline_id}/validate
POST   /api/projects/{project_id}/automation/pipelines/{pipeline_id}/runs
GET    /api/projects/{project_id}/automation/runs/{run_id}
POST   /api/projects/{project_id}/automation/runs/{run_id}/steps/{step_id}/retry
```

Create/update Hermes documentation or skill instructions that explain: working directory, Story Builder base URL, block discovery, pipeline creation, required fields, validation, execution/polling, artifact reuse, and output location. Include complete examples for the acceptance pipeline and each Control-Foley mode. Hermes must never be instructed to merge workflow files, use raw node IDs, or bypass Story Builder with localhost ComfyUI calls.

### 5. Implementation record and remaining live gates

1. **Implemented:** Audio Studio reorder, collapsible Block Library, and removal of duplicate Noise Cleanup controls.
2. **Implemented and offline-tested:** Control-Foley discovery, fixed API workflow copies, typed validation, upload staging, job persistence, and output collection.
3. **Implemented and browser-tested:** dynamic Control-Foley mode form, job progress, and audio playback.
4. **Implemented:** Automation block registry and typed schemas.
5. **Implemented and offline-tested:** pipeline persistence, validation, ordered execution, step state, artifact binding, and downstream retry/reuse.
6. **Implemented and browser-tested:** `/automation` Audio Automation editor, saved pipelines, validation, run state, and retry controls.
7. **Implemented and API-tested:** trusted Hermes runner and skill contract. Hermes calls Story Builder only.
8. **Passed:** backend unit suite, frontend production build, and Playwright desktop/narrow layout checks.
9. **Pending a running ComfyUI:** live renders for all three Control-Foley modes and the full Timed TTS → Split → Emotion → Stitch acceptance run. These are not claimed as passed until output audio is collected.

No block is marked available merely because a form exists. Every mode must pass offline schema validation, API/job tests, artifact checks, live execution where its runtime is available, and browser validation.

## Implemented already

### Foundation and safety baseline

- Progressive `/audio` page and phased block-status display
- Configurable ComfyUI connection targeting `http://127.0.0.1:3008` by default
- Capability and architecture diagnostics
- Audio output collection and offline bridge tests
- Story Builder-owned code and artifacts, without modifying TTS-Audio-Suite custom-node source

The live `/prompt`, history, progress, and output-collection gate still requires a running ComfyUI instance.

### Catalogs, reference voices, and character maps

- Read-only discovery of installed reference voices and TTS model families
- Atomic installation of a user reference audio file and its exact transcript
- Project-owned character-map loading and persistence
- Existing API contracts for capabilities, catalogs, reference-voice installation, and character maps

Live catalog refresh and clean-restart discovery validation still require a running ComfyUI instance.

### Audio Studio UI polish

- Clearly labelled and responsively sized **Character name**, **Language**, and **Reference voice** controls
- Character name and language on the first row; reference voice and Remove action on the second row
- Searchable, fixed-height scrolling voice and model catalogs showing approximately five or six entries
- Result counts, empty-result messages, long-name truncation, and full-name tooltips
- Successful frontend production build and focused Audio Studio lint check

### Phase 2 timed TTS — offline implementation complete

- Cleaned ChatterBox UI workflow copy, fixed API workflow, and Story Builder-owned workflow adapter
- Per-request SRT character/language rewriting from the saved project character map; no global alias-file mutation
- Queued job submission and polling endpoints for Hermes and the browser
- Project run artifacts plus final FLAC export under `output/<project-id>/audio/`
- Audio Studio SRT import/editor, shared model and timing controls, job state, playback, and downloads
- Offline validation, backend unit tests, frontend build, and focused UI lint pass

Phase 2 passed its live API gate on 2026-08-15. The current `SaveAudioAdvanced` schema required the Story Builder-owned API workflow to use `format: "flac"`; multi-character jobs then completed both before and after a clean ComfyUI restart. The retained validation project contains FLAC exports, adjusted SRT, generation information, and timing reports. Human listening remains available through its Audio Studio player.

### Phase 3 live voice discovery — implemented and validated

- Refresh through `CharacterVoicesNode` discovery without changing TTS-Audio-Suite source or global aliases
- Installation results include the live voice key, discovery result, and genuine restart requirement
- Audio Studio refresh/retry controls plus a Hermes-friendly refresh endpoint
- Temporary user voice installed, discovered without restart, used in a real generation, removed, and confirmed absent
- Bundled voices rediscovered after a clean ComfyUI restart

### Phase 4 F5 dataset preparation — implemented and validated

- Preparation support for `F5TTS_v1_Base`, `F5TTS_Base`, and `E2TTS_Base`
- Project-scoped metadata/audio upload and dataset validation
- AArch64, CUDA, dependency, checkpoint, FFmpeg, and source preflight reporting
- Compatible generation of `raw.arrow`, `duration.json`, and `vocab.txt` without editing the installed suite
- Command preview and explicit blockers; training and checkpoint downloads remain disabled pending approval
- Synthetic 24 kHz preparation fixture passed on the active AArch64/NVIDIA GB10 system

### Phase 5 structural editing — implemented and locally validated

- Project-scoped wrappers around the existing suite split, simple concat, and timed concat scripts
- Immutable source audio and split clips, enriched manifests, replacement provenance, and deterministic staging
- Upload or project-relative sources, structured edit rows or JSON import, replacement uploads, explicit timed gaps, previews, and downloads
- Queued browser/Hermes APIs and final WAV export under `output/<project-id>/audio/`
- Split → stitch round trip, timed gap, replacement precedence, validation, backend tests, frontend build, and focused lint pass

### Phases 6–8 audio effects — implemented; live validation recorded

- Five working, Story Builder-owned API workflows: Voice Repair, Voice Changer, RVC, Emotion Change, and Style Change
- One validated backend runner with project-owned inputs, job state, provenance, deterministic FLAC exports, and friendly parameters; Hermes never edits ComfyUI node IDs
- Audio Studio operation controls, source upload/project-output selection, A/B playback, local RVC model/index selection, and direct effect-output selection during Stitch
- Official VoiceFixer checkpoints installed and checksum-verified; no TTS-Audio-Suite source was modified
- Live API passes: Voice Repair, Chatterbox Voice Changer, RVC with pitch/index, Step Audio EditX Emotion, and Step Audio EditX Style
- **Change of plan — Noise Cleanup moves outside ComfyUI:** the attempted ComfyUI workflow reaches `VocalRemovalNode`, but the installed separator rejects `UVR-DeNoise.pth` under Python 3.13. We will not alter the working ComfyUI environment to solve it. The repository already contains Facebook Research's speech-enhancement Demucs implementation under `audio/denoiser`; Phase 6 will first validate and wrap that code as an isolated Python executor. The separate `youtube_code/demucs_split.py` remains a music-stem separator, not the default speech denoiser.

## Remaining implementation status

- **Phase 2 — implemented:** live generation and clean-restart rerun passed.
- **Phase 3 — implemented:** install, refresh, use, cleanup, and restart discovery passed.
- **Phase 4 — preparation implemented:** F5 validation/preparation passed; real training remains approval-gated and has reported dependency/staging blockers.
- **Phase 5 — implemented:** Split and Stitch are available without ComfyUI.
- **Phase 6 — partial live pass, cleanup replanned:** Voice Repair is operational. Noise Cleanup will use the repository's direct speech-enhancement code after isolated compatibility and quality tests; no ComfyUI dependency changes are planned.
- **Phase 7 — implemented and live-tested:** Chatterbox Voice Changer and local RVC model/index/pitch execution passed.
- **Phase 8 — implemented and live-tested:** separate Step Audio EditX Emotion and Style operations passed. Human listening review remains recommended before marking creative presets final.
- **Phase 9 — implemented, live acceptance pending:** the ordered runner, editor, persistence, validation, retry, and Hermes contract are available on `/automation`. The full Timed TTS → Split → Emotion → Stitch render still requires running ComfyUI.
- **Phase 10 — implemented and live-tested:** dedicated Music & Sound page, fixed ACE-Step API workflow, friendly job API, polling/player, deterministic project export, and a successful five-second AArch64/ComfyUI acceptance render.
- **Phase 11 — implemented, live renders pending:** the Hunyuan Foley surface was replaced by fixed Control-Foley Text → Audio, Text + Video → Audio, and Reference Audio + Video → Audio workflows and friendly Story Builder APIs.
- **Phase 12 — preparation surface implemented:** ACE-Step source/converter/trainer/AArch64 preflight is visible. Standalone training checkpoints are absent, so smoke/full training remain disabled and no training capability is claimed.
- **Phase 13 — implemented and tested:** dedicated Audio Utilities page, hash-deduplicated curated library, safe batch/folder staging, FFmpeg video-to-MP3, isolated Facebook denoiser, and isolated Demucs 2/4/6-stem runtimes. MP3, denoiser, and two-stem acceptance fixtures passed; the working ComfyUI environment was not modified.
- **Phase 14 — planned:** complete the ordered Web Audio process builder after its underlying blocks are proven.

## Goal

Turn the installed TTS-Audio-Suite capabilities into a small catalog of reliable, API-compatible operations that Hermes can run one at a time or compose into a larger audio job.

This is not a plan to make Hermes construct or merge arbitrary ComfyUI graphs. We will prepare and validate one workflow JSON for each supported audio operation. Hermes will select operations and supply their parameters; the bridge will execute them in sequence.

## Three-page boundary

1. **Audio Studio:** generative speech and its direct auxiliaries—timed TTS, voices, character maps, fine-tuning preparation, voice conversion, repair, emotion/style, and split/stitch. Pipeline authoring belongs to Automation.
2. **Music & Sound:** ACE-Step Music Maker, ACE-Step LoRA preparation/training when proven, and Control-Foley sound effects. It contains no curated-audio library.
3. **Audio Utilities:** user-curated audio management and deterministic processing—speech noise cleanup, video/audio extraction, and Demucs music-stem separation. These are manual file/folder tools rather than generative creation controls.

The existing timed, multi-character workflow is the starting point:

```text
workflows/ricky/TTS_audio_multichar_timed_wf.json
```

It provides the first operation: text/SRT + timing + multiple characters/languages → generated dialogue audio. It is currently a ComfyUI UI-format workflow and must be converted/exported to ComfyUI API format before automated submission.

## Core Model

There are two kinds of blocks:

1. **ComfyUI workflow blocks** for model-powered generation, voice conversion, emotion/style changes, restoration, and enhancement.
2. **Python audio utility blocks** for deterministic splitting, stitching, timing, fades, format conversion, and manifest handling.

Each block accepts a documented JSON request and produces files plus a JSON result. A job runner passes the outputs of one block into the inputs of the next.

```text
Job request
    ↓
Validate block sequence and parameters
    ↓
Run workflow or Python utility
    ↓
Record output artifact and metadata
    ↓
Pass artifact to next block
    ↓
Save final audio and manifest in output/
```

ComfyUI still receives one complete API workflow JSON for every ComfyUI submission. Composition happens between jobs, not by asking Hermes to splice node graphs together.

## Verified Voice Architecture

The installed TTS-Audio-Suite code separates the base speech model from reference-voice material. These are different layers, and the UI must name them clearly.

### Layer 1: base or trained TTS model

This is the model that supplies the engine's learned speech and language behavior. Installed examples are under:

```text
/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/models/TTS/
```

Current model families visible there include F5-TTS, CosyVoice, IndexTTS, VibeVoice, Qwen3-TTS, Echo TTS, and Step Audio EditX support files. Qwen3-TTS, for example, has separate Base, CustomVoice, and VoiceDesign model variants.

A person-specific model fine-tuned from many recordings and transcripts belongs in this model layer, in the engine-specific model location expected by that engine. It does **not** belong in `voices_examples` merely because it represents a voice.

The current TTS-Audio-Suite installation exposes model loading and inference, but the inspected character/voice system is not a general fine-tuning pipeline. Before promising “train a new voice model” in the web UI, we must choose a training method supported by the selected engine, define its dataset format, and verify how its resulting checkpoint is loaded by that engine.

### Base-model capability classification

Before building the model dropdown or training controls, create a verified catalog of the installed base models. Every model family/version must be classified as one of:

- **Locally fine-tunable:** a supported training method can be installed and run through this application.
- **Externally fine-tunable:** training is possible, but the current system can only import/register the resulting checkpoint.
- **Not fine-tunable here:** inference, reference cloning, presets, or voice design may work, but no supported fine-tuning path is available.
- **Unverified:** do not expose a training button until the method and output loading have been tested.

The classification must be evidence-based per exact model variant. A model accepting one-shot reference audio does not prove that its weights can be fine-tuned locally.

The catalog entry should record:

- Engine and exact base-model ID
- Installed model path
- Capability classification
- Supported languages
- One-shot reference support
- Reference transcript requirement
- Built-in/custom voice preset support
- Fine-tuning implementation or external training project
- Dataset format and audio requirements
- Required compute/VRAM and estimated duration
- Training parameters that may be safely exposed
- Output artifact type: `.pth`, `.safetensors`, or a multi-file model directory
- Destination path and inference loader used for the result
- Whether a fine-tuned result can also accept one-shot reference conditioning

Fine-tuned outputs must be stored in an engine-specific user-model area alongside the corresponding model family, without overwriting the original base checkpoint. They must also be entered in the model catalog with provenance, training configuration, dataset reference, and compatibility metadata.

### Layer 2: one-shot reference voice

`voices_examples` is this second category. It is a reference-voice library, not a folder of fine-tuned person-specific model checkpoints:

```text
/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/custom_nodes/TTS-Audio-Suite/voices_examples/
```

It contains audio recordings such as WAV files plus companion text. The discovery code scans this directory recursively and also scans these user-model locations:

```text
/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/models/voices/
/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/models/TTS/voices/
```

For a reference recording named `speaker.wav`, discovery requires a non-empty companion transcript:

```text
speaker.reference.txt   # preferred: exact words spoken in speaker.wav
speaker.txt             # fallback when .reference.txt is absent
```

The transcript is especially important for engines such as F5-TTS and other audio-plus-text engines. It is not the character-to-voice assignment file.

Bundled examples should remain in `voices_examples`; new user/project reference voices should preferably be stored in `ComfyUI/models/voices/`, `ComfyUI/models/TTS/voices/`, or a configured extra voices path so suite updates do not mix examples with user assets.

### What the character voice selector chooses

The timed TTS block selects one engine and one base/fine-tuned model for the entire dialogue part. The character form then exposes one character-specific voice dropdown:

1. **TTS block model dropdown:** select the shared original base model or compatible fine-tuned checkpoint.
2. **Per-character one-shot voice dropdown:** select a compatible audio-plus-transcript reference, or choose `none` when the engine/model does not need one.

The TTS engine is either derived from the selected model or selected immediately before it. The second dropdown is filtered after the engine/model selection so it only shows compatible references.

Therefore, when a user wants both the “base voice model” and the “outer/reference voice,” the pipeline chooses both. Conceptually:

```text
Base TTS engine/model
    + one-shot reference audio
    + exact reference transcript when required
    + character's dialogue text and language
    → generated character speech
```

These are not two interchangeable voice dropdowns. The base model controls the underlying model capabilities and general speech behavior; the reference audio conditions speaker identity and may also transfer some prosody/style. The exact balance is engine-dependent.

A fine-tuned checkpoint belongs in the **model dropdown**. It replaces the original base checkpoint for that TTS block; it does not replace the one-shot reference entry. When the selected engine supports the combination, generation is:

```text
Selected fine-tuned model for the whole dialogue part
    + one-shot reference selected independently for each character
    + timed dialogue and pacing controls
    → generated multi-character speech
```

The initial production mode deliberately uses one model for all characters in a dialogue part. Per-character base models are deferred to an advanced renderer that generates character/segment clips in model-grouped batches and reconstructs the SRT timeline.

### Pacing and delivery control

Pacing must not be represented by temperature alone. The system needs explicit timing at two levels:

- **Timeline pacing:** SRT cue start/end times, pauses, overlaps, and timing mode determine when each utterance occurs and how much time is available.
- **Performance pacing:** speaking-rate/style instructions and model-specific controls determine how words are delivered inside that interval.

The existing timed TTS node supports `stretch_to_fit`, `pad_with_silence`, `smart_natural`, and `concatenate`. It also supports explicit pause tags in dialogue content. These controls can make a line start/end at specified times, insert silence, or safely stretch/compress generated audio. They do not guarantee that the model naturally performs every internal pause exactly as intended.

The Audio page should therefore support:

- SRT start/end time for every cue
- Explicit pause markers inside a cue
- Optional target speaking rate
- Timing mode
- Safe minimum/maximum stretch ratios
- Timing tolerance
- Optional per-cue performance/style instruction when the selected engine supports it
- Preview plus timing report before accepting a render

Fine-tuning can teach recurring cadence, pronunciation habits, and delivery style from a multi-recording dataset. A one-shot reference can transfer some local cadence/style. Temperature, exaggeration, CFG, and seed influence variation, intensity, and adherence, but are not direct, dependable controls for pitch, timbre, depth, or precise pacing. Explicit style/emotion workflows and RVC/pitch/formant processing remain separate tools.

Not every engine supports every pairing. The UI must filter reference and model choices using an engine compatibility matrix rather than allowing arbitrary combinations. The first implementation should test the engines actually used by the production timed-dialogue workflow and record for each:

- Whether it accepts a one-shot reference
- Whether it requires the reference transcript
- Whether it offers built-in/custom voice presets
- Whether a preset can be combined with a reference or is mutually exclusive
- Whether it can load a user-fine-tuned checkpoint
- Supported languages
- Expected identity, style, and timing behavior
- Whether a fine-tuned checkpoint can still be combined with one-shot reference audio

### Project character map versus suite-global alias map

The installed suite already has a global alias file:

```text
/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/custom_nodes/TTS-Audio-Suite/voices_examples/#character_alias_map.txt
```

Its lines map dialogue tags to discovered reference-voice stems, optionally with a default language:

```text
Alice = female_01, de
Bob = male_01, fr
Narrator = david_attenborough cc3
```

The discovery code also searches for `#character_alias_map.txt` in `models/TTS/voices`, `models/voices`, and configured extra voice paths, with later/higher-priority locations overriding bundled examples.

This global file is **not** currently selected as an input by `TTS_audio_multichar_timed_wf.json`. The `UnifiedTTSSRTNode` receives SRT text directly, finds `[Character]` tags, then resolves those names through the suite's global discovery cache and global alias maps. The workflow contains `CharacterVoicesNode` inputs for individual selected/direct reference voices, but it has no file-path input for a project character map.

Consequently, changing the bundled global alias file for every project would cause cross-project collisions and is not acceptable for the API runner.

### Required project-level character configuration

The Audio page and Hermes should create a project-owned character configuration file, separate from every voice transcript and separate from the suite-global alias map. JSON should be canonical because it can express the two voice layers and metadata without ambiguous text parsing:

```json
{
  "version": 1,
  "project": "example-project",
  "default_engine": {
    "type": "qwen3_tts",
    "model": "Qwen3-TTS-12Hz-1.7B-Base"
  },
  "characters": [
    {
      "name": "Alice",
      "language": "en",
      "reference_voice": "voices_examples/female/female_01.wav"
    },
    {
      "name": "Bob",
      "language": "de",
      "reference_voice": "voices_examples/male/male_01.wav"
    }
  ]
}
```

If human-readable `.txt` compatibility is useful, the bridge may also export an alias-map-style text file, but JSON remains the authoritative project document.

For API execution, the bridge must load this project configuration and supply an explicit character mapping to the prepared workflow. There are two implementation options to evaluate:

1. Add a small project-character-map loader node/input to the production workflow and TTS-Audio-Suite integration.
2. Have the bridge resolve reference paths/transcripts and inject explicit mapping data into a dedicated workflow node before submitting the prompt.

The preferred result is an explicit **Character Map Loader** workflow input, not modifying a fixed file before each run. The loader should accept a validated project map path or already-parsed map object, resolve the reference voice for every character, and emit mapping data directly to the timed TTS node. The base/fine-tuned model is supplied separately at the TTS-block level. This prevents concurrent jobs from overwriting one another and allows the same workflow JSON to serve every project.

The prepared workflow must not silently depend on `#character_alias_map.txt` after this change. The global map may remain a manual/default ComfyUI convenience, but the API path will use the project configuration supplied with the job.

### Audio page voice-management forms

The Audio page needs four distinct actions:

- **TTS Model:** choose one engine and one base/fine-tuned model for the entire dialogue part.
- **Character Assignment:** add/remove character rows; choose language and a compatible one-shot reference for each character.
- **Add Reference Voice:** upload one clean recording plus its exact transcript; validate duration/format; store and refresh the reference-voice catalog.
- **Fine-tune Voice Model:** select a locally fine-tunable base model and open the form generated from that model's verified training specification.
- **Import Trained Model:** register a compatible externally produced checkpoint or model directory after validating that the selected engine can load it.

The reference-voice dropdown can be populated by a backend catalog endpoint that uses the same discovery rules as TTS-Audio-Suite. The browser should never receive permission to browse arbitrary server paths.

### Fine-tuning form and job lifecycle

The Fine-tune Voice Model form is engine-specific, not one universal form. It should request only the inputs required by the selected training implementation, potentially including:

- Training recordings or dataset directory
- Exact transcript per recording
- Dataset manifest and speaker ID
- Language
- Required sample rate, channel format, clip length, and cleaning rules
- Starting base checkpoint
- Training/validation split
- Steps or epochs
- Learning rate
- Batch size and gradient accumulation
- Checkpoint/save interval
- Output model name

The backend validates and prepares the dataset before enabling **Start Fine-tuning**. Training runs as a tracked background job with status, logs, progress, cancellation, validation samples, and checkpoint recovery.

On successful completion:

1. Preserve the original base model.
2. Save the produced `.pth`, `.safetensors`, or complete model directory under the proper engine-specific user-model location.
3. Store training metadata and dataset provenance beside it.
4. Verify that TTS-Audio-Suite can load it for inference.
5. Add it to the base/trained-model dropdown only after the inference check passes.
6. Record whether it may be paired with a one-shot reference voice.

This training subsystem is a separate pipeline block/job type. It prepares reusable models; it is not executed inside every dialogue-generation flow.

The training form includes dataset-audio directory, transcript/manifest location, optional validation directory, selected starting model, engine-specific settings, and output directory. The default output directory must be the verified user-model directory for that engine—not necessarily the original vendor checkpoint directory. Users may override it only with a validated writable model-library path. A successful checkpoint is registered only after an inference test.

### Voice and processed-audio storage

Keep reusable library assets separate from project outputs:

- **Bundled one-shot examples:** remain under `TTS-Audio-Suite/voices_examples/`.
- **User-added one-shot references:** store under `ComfyUI/models/voices/` or the configured user voices path as `name.wav` plus `name.reference.txt`.
- **Original/fine-tuned models:** remain in engine-specific directories under `ComfyUI/models/TTS/`, with user outputs in a non-destructive engine-specific subdirectory.
- **Project uploads and intermediate clips:** store under a project/run workspace, not the reusable voice library.
- **Cleanup, emotion, style, and RVC results:** store under the current project/run artifacts directory with immutable source files and operation metadata.
- **Approved final files:** copy/export to `/home/riki/web_dev/story_builder/output/`.

Every derived audio filename should include the source stem, operation, run/job ID, and segment ID when applicable. The artifact manifest is authoritative; filenames alone must not carry all workflow state.

## Blocks to Prepare

### A. Timed Multi-Character TTS

**Purpose:** Generate a complete dialogue from timed text with multiple characters, voice references, and language switches.

**Starting workflow:**

```text
workflows/ricky/TTS_audio_multichar_timed_wf.json
```

**Inputs:**

- SRT or supported timed-dialogue text
- Project character configuration path or object
- Character-to-reference-voice mapping
- TTS engine/base model
- Optional trained model/checkpoint when supported by the selected engine
- Narrator voice
- Language tags per character or segment
- Selected TTS engine and engine settings
- Timing mode
- Seed

**Outputs:**

- Generated WAV
- Adjusted SRT
- Generation information
- Timing report

**Implementation work:**

- Choose and retain the intended engine path; remove disconnected experimental engine paths from the production copy.
- Add a proper audio-save node if the workflow currently only previews audio.
- Export/convert the production copy into ComfyUI API prompt format.
- Replace reliance on the suite-global alias file with an explicit project character-map input.
- Define stable parameter mappings so Hermes never edits node IDs directly.
- Add and enforce an engine/model/reference-voice compatibility matrix.
- Test multilingual character tags, overlapping dialogue, pauses, and missing voice aliases.

**Planned API workflow:**

```text
workflows/api/audio/tts_multichar_timed_api.json
```

### B. Split Audio

**Purpose:** Split one source recording into independently editable clips.

This should normally be a Python utility, not a ComfyUI workflow.

**Split modes:**

- Explicit start/end timestamps
- SRT cue boundaries
- Scene/segment manifest
- Silence-based detection, as an optional later mode

**Inputs:**

- Source audio path
- Edit-instructions file path: JSON or supported text
- Output clips directory
- Optional full transcript file path
- Optional clip filename template

The installed implementation is:

```text
TTS-Audio-Suite/scripts/split_scene_audio.py
TTS-Audio-Suite/utils/audio/scene_splitter.py
```

Its current command contract is:

```text
--audio
--instructions
--output-dir
--transcript       # optional
--name-template    # optional
```

The edit instructions accept a list or `{ "edits": [...] }`; each edit requires numeric `start` and `end`, normally includes exact `text`, and may include the intended edit operation. Ranges must be valid, in bounds, and non-overlapping. The splitter sorts them, writes numbered edit and untouched-gap clips, and creates enriched JSON containing the generated `file_name` values.

**Outputs:**

- One lossless clip per segment
- A segment manifest preserving order, original timestamps, duration, and source identity

**Manifest shape:**

```json
{
  "version": 1,
  "source_audio": "input/dialogue.wav",
  "sample_rate": 48000,
  "segments": [
    {
      "id": "segment-001",
      "order": 1,
      "start_ms": 1000,
      "end_ms": 4200,
      "source_path": "work/segment-001.wav",
      "current_path": "work/segment-001.wav",
      "speaker": "Alice",
      "text": "Example line",
      "operations": []
    }
  ]
}
```

The manifest is the contract used by selective editing and stitching. Original clips remain untouched; an edit updates `current_path` and appends an operation record.

The web form for this block therefore includes source-audio upload/selection, instruction JSON upload/editor, optional transcript upload, output workspace, and naming template. Its output-directory default is the current run's `split/` artifacts directory.

### C. Emotion Change

**Purpose:** Change the emotion of one clip while preserving intelligibility and, as far as the selected model allows, speaker identity.

This may require more than one curated workflow depending on which TTS-Audio-Suite node gives the best results:

- Text-described emotion
- Emotion-vector control
- Emotion reference-audio control

These should be separate workflow variants if their required inputs or node graphs differ materially.

**Inputs:**

- Input clip
- Emotion description, vector, or reference audio
- Strength/intensity
- Optional transcript
- Optional speaker reference
- Seed

**Outputs:**

- Emotion-edited clip
- Duration comparison
- Operation metadata

**Planned API workflows:**

```text
workflows/api/audio/emotion_text_api.json
workflows/api/audio/emotion_reference_api.json
```

The exact engine—such as IndexTTS-2 or another installed suite engine—must be chosen through hands-on quality and identity-preservation tests before freezing the production workflow.

The block form accepts an uploaded/project audio clip and stores the result in the run's `emotion/` artifacts directory. Reference-emotion audio, when used, is a job input and is stored under the same run's inputs unless the user explicitly promotes it to a reusable reference library.

### D. Speaking Style / Performance Edit

**Purpose:** Change delivery independently from broad emotion: whispering, shouting, calm delivery, dramatic delivery, laughter, sighs, breathing, pacing, or other supported performance instructions.

**Inputs:**

- Input clip
- Style instruction
- Edit strength
- Optional transcript
- Optional voice reference
- Seed

**Outputs:**

- Style-edited clip
- Operation metadata

**Planned API workflow:**

```text
workflows/api/audio/style_edit_api.json
```

Step Audio EditX is a candidate, but its actual installed nodes and behavior must be validated before it becomes the fixed engine.

Emotion and style should initially remain separate operations. They may be combined into one workflow later only if testing proves that the same engine reliably handles both in one pass.

The style form must include explicit delivery/pacing instructions where supported. Results go to the run's `style/` artifacts directory and retain links to the input clip and instruction in the artifact manifest.

### E. Background Noise / Echo Removal

**Purpose:** Clean an uploaded or generated recording without changing its voice unnecessarily.

**Inputs:**

- Input audio
- Noise-removal strength
- Vocal isolation option
- Echo/reverb reduction option
- Optional VoiceFixer pass

**Outputs:**

- Cleaned audio
- Processing metadata

**Executors:**

```text
audio/denoiser/denoiser/enhance.py          # candidate isolated Python speech enhancer
workflows/api/audio/voice_repair_api.json
```

The existing ComfyUI Noise Cleanup workflow is provisional and failed in the installed Python 3.13 separator environment. Speech cleanup therefore moves to the direct Python candidate after AArch64/runtime and listening tests. Noise removal and ComfyUI Voice Repair remain separate blocks because a VoiceFixer pass is not always desirable; the caller can chain them when both are needed.

The cleanup form belongs on Audio Utilities and accepts single/multiple/folder audio upload, curated/project selection, model (`dns64` or `master64` after testing), dry/wet strength, and output collection. The immutable upload stays under run inputs; cleaned speech goes to the run's `cleanup/` directory. Echo/reverb improvement is best-effort and must be confirmed by listening rather than exposed as a guaranteed switch.

### E2. Music Stem Separation — Demucs

**Purpose:** Separate a mixed song or speech-over-music recording into named music stems so vocals/dialogue or accompaniment can be edited independently.

The repository's `youtube_code/demucs_split.py` uses music Demucs (`htdemucs` or `htdemucs_6s`) and is suitable for vocals/no-vocals or vocals/drums/bass/other separation. It is not the primary solution for hiss, fan noise, traffic, room noise, or reverberation. `youtube_code/asteroid_split.py` targets two overlapping speakers at 8 kHz and must remain a separate speech-source-separation experiment, not a Noise Cleanup block.

**Planned inputs:** source audio, 2/4/6-stem mode, verified model, CPU/CUDA selection, output format, and optional chunk/resource controls.

**Required implementation correction:** retain numbered outputs such as `filename_1.mp3`, `filename_2.mp3`, and so on, while writing the authoritative semantic mapping (`vocals`, `no_vocals`, `drums`, `bass`, `other`) into the manifest. The wrapper must derive that mapping from Demucs stem names before numbering, not from alphabetic sorting.

**Outputs:** one lossless file per named stem, separation manifest, model/settings, duration report, and per-stem previews. A chosen vocal/dialogue stem may then feed Noise Cleanup, Voice Repair, or another editing block; stems can be remixed only through an explicit later mixer block.

**Gate:** 2-stem and 4-stem tests produce correctly identified, synchronized stems on representative music and speech-over-music inputs, with human artifact review.

### F. Voice Changer — ChatterBox Reference Conversion

**Purpose:** Change the perceived speaker identity of existing speech using a selected one-shot target/reference voice while preserving the source recording's words, timing, pauses, rhythm, emotion, and delivery as closely as the converter allows.

This is voice conversion, not text-to-speech. The production workflow uses the installed `ChatterboxVCNode` and its direct audio inputs:

```text
source_audio + target_audio + refinement_passes → converted_audio
```

**Inputs:**

- Source speech audio
- Target one-shot/reference voice from the reference catalog or a project upload
- Refinement passes
- Device
- Language/model compatibility when required by ChatterBox VC
- Output name

**Outputs:**

- Voice-changed audio
- Source/target provenance
- Duration comparison
- Conversion metadata

**Planned API workflow:**

```text
workflows/api/audio/voice_changer_chatterbox_api.json
```

The first UI version should recommend 1–5 refinement passes and warn that additional passes may increase distortion. The target-reference transcript is not required by the current ChatterBox VC node because conversion accepts target audio directly.

Noise cancellation, vocal isolation, echo removal, and repair do not belong inside this workflow. They remain separate blocks. A user who needs them constructs:

```text
Uploaded audio
  → Noise Cleanup
  → Voice Changer
  → optional normalization/export
```

The source performance is expected to be substantially preserved because the speech is converted rather than regenerated, but preservation is not guaranteed to be exact. Male-to-female conversion may alter pitch contour, breathiness, consonant clarity, sibilance, and fine emotional detail. The page must provide source/output A/B preview.

Voice Changer results go to the current run's `voice_changer/` artifacts directory. A target reference promoted to the reusable library is stored separately under the configured user reference-voice path.

### G. RVC Voice and Pitch Modulation

**Purpose:** Convert speaker identity or adjust vocal pitch/depth after generation or on uploaded audio.

**Inputs:**

- Input audio or selected clip
- RVC model/voice
- Pitch shift in semitones
- Conversion strength and supported RVC settings
- Optional formant or tone settings, if the installed nodes expose them

**Outputs:**

- Converted/modulated audio
- Operation metadata

**Planned API workflow:**

```text
workflows/api/audio/rvc_voice_pitch_api.json
```

“Deeper,” “thicker,” and “shriller” must map to explicit presets rather than vague graph edits. For example, a preset may combine an RVC model, semitone shift, formant setting, EQ, and compression. Exact values should be calibrated by listening tests.

The RVC form accepts audio upload/project selection, RVC model, semitone shift, supported index/protection/conversion controls, optional formant/tone controls, and output name. Results go to the run's `rvc/` directory. RVC models belong in the appropriate reusable RVC model catalog; converted audio does not.

### H. Stitch Audio

**Purpose:** Reassemble original and edited clips into the final recording while preserving their intended timing.

This should normally be a Python utility.

**Inputs:**

- Clips directory
- Stitch mode
- Optional timed-concat manifest
- Output file path

The installed implementations are:

```text
TTS-Audio-Suite/scripts/concat_scene_audio.py
TTS-Audio-Suite/scripts/timed_concat_scene_audio.py
TTS-Audio-Suite/utils/audio/scene_concat.py
TTS-Audio-Suite/utils/audio/timed_scene_concat.py
```

Simple concatenation requires `--clips-dir` and optional `--output`. It discovers names matching numbered scene clips and automatically prefers `edited_...` over the original clip with the same index.

Timed concatenation requires `--clips-dir`, `--manifest`, and optional `--output`. Its current manifest is:

```json
{
  "version": 1,
  "sample_rate": 48000,
  "items": [
    {"file": "scene_001.wav", "gap_after_seconds": 0.5},
    {"file": "edited_scene_002.wav", "gap_after_seconds": 0.0}
  ]
}
```

The current timed stitcher preserves explicit order and inserts gaps; it does not yet position clips by absolute start timestamp, mix overlapping dialogue, crossfade, or apply duration correction. Those features require an extension or a new timeline assembler and must not be claimed as already implemented.

**Stitch modes:**

- Sequential concatenation — already implemented
- Ordered concatenation with explicit gaps — already implemented
- Preserve original absolute timeline positions — planned extension
- Preserve SRT timing and mix overlaps — planned extension

**Outputs:**

- Final lossless audio
- Updated manifest
- Timing/drift report
- Optional adjusted SRT

The future timeline assembler must handle edited clips whose duration changed. Planned policies include preserving natural duration, padding shorter clips, trimming or time-stretching within safe limits, and shifting later clips with an adjusted-timing report.

## Valid Pipeline Combinations

The blocks are reusable and can be chained without modifying their internal workflow JSON.

### Generate complete dialogue

```text
Timed Multi-Character TTS → final WAV
```

### Edit selected lines

```text
Source audio
  → Split
  → Apply emotion/style only to selected segment IDs
  → Stitch edited and untouched segments
  → final WAV
```

### Change one character's voice

```text
Source audio
  → Split using SRT/manifest
  → RVC only on segments belonging to that character
  → Stitch
  → final WAV
```

### Clean and deepen an uploaded voice

```text
Uploaded audio
  → Noise Cleanup
  → optional Voice Repair
  → RVC/Pitch preset: deeper
  → final WAV
```

### Clean speech and change speaker identity from a reference

```text
Uploaded audio
  → optional Noise Cleanup
  → Voice Changer with selected one-shot target voice
  → optional normalization
  → final WAV
```

Cleanup is not automatically hidden inside Voice Changer. The user/Hermes adds the cleanup block explicitly when the source needs it.

### Repair one noisy section only

```text
Source audio
  → Split by explicit time range
  → Noise Cleanup on selected segment
  → Stitch with original surrounding audio
  → final WAV
```

### Full production chain

```text
Timed Multi-Character TTS
  → Split
  → Emotion edits on selected clips
  → Style edits on selected clips
  → RVC on selected characters/clips
  → Stitch
  → optional whole-file cleanup/normalization
  → final WAV
```

## Block Request Format

Hermes and the web UI should submit a high-level request, never raw ComfyUI node mutations:

```json
{
  "pipeline": [
    {
      "operation": "split",
      "input": "output/dialogue.wav",
      "params": {
        "mode": "srt",
        "srt_path": "output/dialogue.srt"
      }
    },
    {
      "operation": "emotion_text",
      "select": {
        "segment_ids": ["segment-003", "segment-007"]
      },
      "params": {
        "emotion": "restrained anger",
        "intensity": 0.7
      }
    },
    {
      "operation": "stitch",
      "params": {
        "mode": "preserve_timeline",
        "duration_policy": "pad_or_safe_stretch",
        "crossfade_ms": 20
      }
    }
  ],
  "output": {
    "directory": "/home/riki/web_dev/story_builder/output",
    "filename": "dialogue_edited.wav"
  }
}
```

The runner resolves operation names through a registry:

```json
{
  "tts_multichar_timed": {
    "executor": "comfyui",
    "workflow": "workflows/api/audio/tts_multichar_timed_api.json"
  },
  "split": {
    "executor": "python",
    "handler": "audio_split"
  },
  "emotion_text": {
    "executor": "comfyui",
    "workflow": "workflows/api/audio/emotion_text_api.json"
  },
  "voice_changer": {
    "executor": "comfyui",
    "workflow": "workflows/api/audio/voice_changer_chatterbox_api.json"
  },
  "rvc_voice_pitch": {
    "executor": "comfyui",
    "workflow": "workflows/api/audio/rvc_voice_pitch_api.json"
  },
  "stitch": {
    "executor": "python",
    "handler": "audio_stitch"
  }
}
```

The bridge owns the mapping from friendly parameters to workflow node inputs. This keeps node IDs and ComfyUI implementation details out of Hermes prompts.

## Workflow Development Procedure

Prepare the workflows one at a time. A workflow is not registered for Hermes until all of these steps pass:

1. Build or simplify the workflow manually in ComfyUI.
2. Confirm it works manually on a representative audio sample.
3. Add a deterministic save-output node and filename prefix.
4. Export it in API format.
5. Identify only the values that callers are allowed to change.
6. Add the workflow and its friendly parameter mapping to the registry.
7. Submit it through the bridge, not through the browser UI.
8. Verify output discovery, timeout handling, and error reporting.
9. Listen to the output and compare timing, speaker identity, artifacts, and loudness.
10. Add a small regression fixture and mark the block ready.

## Phased Implementation and Test Plan

Each phase has a gate. Do not begin the next model-powered block until the current block runs through its real API path, produces a discoverable output, and passes a listening check.

### Phase 2 — First vertical slice: timed multi-character TTS

**Work:**

- Preserve `workflows/ricky/TTS_audio_multichar_timed_wf.json` as the reference UI workflow.
- Create a cleaned production UI copy without overwriting the original.
- Choose one active engine/model path and remove disconnected experimental branches from the production copy.
- Add deterministic Save Audio behavior.
- Export/create its API-format counterpart.
- Add friendly mappings for SRT, model, reference voices, language, timing mode, seed, and output prefix.
- Implement the project Character Map Loader through an additive extension only if fixed API injection cannot supply the mapping cleanly.
- Keep the suite-global alias behavior as a backward-compatible fallback.

**Tests:**

- Manual ComfyUI UI run
- Direct `/prompt` API run
- Story Builder bridge run
- Hermes high-level operation run
- Multiple characters and one shared base/fine-tuned model
- Different one-shot reference per character
- Language tags, pauses, overlaps, and all timing modes
- Saved WAV, adjusted SRT, generation information, and timing report
- ComfyUI restart followed by rerun to catch cache-only success

**Gate:** the same prepared workflow works manually and through the API, and the final output is registered under the Story Builder run and export locations.

### Phase 3 — Live voice discovery validation

**Work:**

- Add catalog refresh using the suite's supported refresh path.
- Detect and report when restart is genuinely required.
- Validate the already-implemented reference-voice installer and project character-map operations against the live TTS-Audio-Suite discovery behavior.

**Tests:**

- Add a new voice and confirm it appears after refresh without restart where supported.
- Restart ComfyUI and confirm the voice remains discoverable.
- Select it in manual ComfyUI and through an API TTS run.
- Reject missing/empty transcripts, unsafe names, duplicate collisions, and unsupported audio.

**Gate:** a voice added through the backend can be discovered and used by a real ComfyUI generation job.

### Phase 4 — Fine-tuning research, then one engine at a time

Research and implement fine-tuning independently for each relevant family: ChatterBox, F5-TTS, Qwen3-TTS, CosyVoice3, IndexTTS-2, Higgs Audio, VibeVoice, and RVC. Do not create one fictional universal trainer.

For each model family:

1. Identify authoritative training/fine-tuning code and its license.
2. Verify that it fine-tunes the installed inference-compatible model variant.
3. Document required recordings, transcripts, manifest format, sample rate, clip duration, language labels, preprocessing, and validation data.
4. Audit AArch64, CUDA, PyTorch, and compiled dependency compatibility.
5. Run dataset validation and preprocessing on a tiny fixture.
6. Start the smallest meaningful training smoke test.
7. Save a checkpoint/model directory.
8. Place a copy in a non-destructive engine-specific user-model directory.
9. Refresh or restart ComfyUI as required.
10. Confirm the TTS-Audio-Suite engine can discover and load it.
11. Run inference and listen to the result.
12. Only then implement that engine's backend training adapter and form schema.

The backend form for a verified engine includes dataset audio directory/upload, transcripts/manifest, validation data, selected base checkpoint, exposed safe training settings, output name, and validated output directory. Training runs as a tracked process with logs, progress, cancellation, checkpoint recovery, and post-training inference validation.

**Gate per engine:** real training output loads in the active ComfyUI/TTS-Audio-Suite installation and generates valid audio. Unsupported engines remain research-only or import-only.

### Phase 5 — Structural editing: split and stitch

**Work:**

- Wrap the existing Python split utility with validated inputs and structured results.
- Wrap simple and timed stitch utilities without changing their existing source initially.
- Standardize enriched edit/segment manifests and immutable originals.
- Add a later timeline-assembler extension for absolute positions and overlap mixing only after current round-trip behavior is verified.

**Tests:**

- Split from JSON instructions and optional transcript.
- Verify untouched gap clips and enriched filenames.
- Split → no edit → simple stitch and compare duration/audio boundaries.
- Timed stitch with explicit gaps.
- Prefer edited clip over its same-index original.
- Fail cleanly on overlaps, missing files, invalid ranges, or unsafe paths.

**Gate:** deterministic split/stitch round trips work outside ComfyUI and produce auditable manifests.

### Phase 6 — Cleanup and repair blocks

**Work:**

- Keep the live-tested ComfyUI API workflow for optional Voice Repair.
- Replace the provisional ComfyUI Noise Cleanup workflow with an isolated Story Builder executor around `audio/denoiser` if compatibility and quality gates pass.
- Place the resulting Noise Cleanup controls on the Phase 13 Audio Utilities page, not Audio Studio.
- Keep `youtube_code/demucs_split.py` as a separate **Music Stem Separation** candidate: vocals/no-vocals or vocals/drums/bass/other. It may precede speech cleanup when dialogue is mixed with music, but it does not replace a speech denoiser for stationary noise, room noise, or reverb.
- Define friendly parameters and deterministic output saving.
- Keep cleanup and repair independently attachable.

**Tests:** preflight the old denoiser dependencies on AArch64 in a separate environment; test `dns64` and `master64` on clean speech plus stationary/non-stationary noise; expose a dry/wet control; verify sample rate, channel handling, duration, intelligibility, artifacts, deterministic outputs, and cleanup → Voice Repair composition. Separately test Demucs 2-stem output labels on speech-over-music and reject treating Asteroid's two-speaker separation as denoising. Voice Repair retains its existing ComfyUI live test.

**Gate:** the isolated speech-enhancement executor is AArch64-compatible and improves representative noisy speech without unacceptable damage; sequential cleanup → Voice Repair works without hidden state. If the legacy code cannot run safely, keep Phase 6 pinned and replace only its runtime—not ComfyUI.

### Phase 7 — Voice Changer and RVC blocks

**Work:**

- Prepare ChatterBox Voice Changer API workflow using source audio plus one-shot target audio.
- Keep Noise Cleanup as an explicit optional preceding block.
- Add refinement-pass guardrails and A/B preview metadata.
- Prepare the separate RVC API workflow using `.pth`, optional `.index`, pitch, index ratio, consonant protection, and volume-envelope settings.

**Tests:** male/female directions, clean and noisy inputs, different reference voices/RVC models, performance/timing preservation, artifacts, output duration, API execution, restart rerun, and catalog discovery.

**Gate:** Voice Changer and RVC are independently callable and clearly select different target asset types.

### Phase 8 — Emotion and style blocks

**Work:**

- Validate `audio_emotion.json` manually and convert a cleaned copy to API format.
- Determine whether text emotion and reference emotion require separate workflows.
- Prepare the style/performance workflow separately.
- Expose pacing/style instructions only when the selected workflow genuinely supports them.
- Integrate selection of individual split segment IDs.

**Tests:** emotion preservation/change comparisons, style instructions, duration drift, speaker-identity preservation, selected-segment edits, and split → edit → stitch.

**Gate:** emotion and style are independently proven, or deliberately combined only if one tested workflow reliably supports both.

### Phase 9 — Unified pipeline runner and Hermes contract on Automation

**Status:** implemented on `/automation`; full live acceptance remains pending. Noise Cleanup is not part of the first acceptance pipeline, but remains an optional registered Automation block backed by Audio Utilities.

**Work:**

- Register every proven block with typed inputs/outputs and parameter schemas.
- Start with an ordered, top-to-bottom pipeline runner; branching and parallel execution are deferred.
- Pass typed artifacts between ComfyUI and Python blocks without asking Hermes to manipulate workflow JSON or filesystem paths.
- Persist job state and artifacts so a failed block can be retried without repeating completed work.
- Add Hermes instructions/tools that expose operation names and friendly schemas only.

**First acceptance pipeline:**

```text
Timed Multi-Character TTS
  → generated dialogue audio + SRT/timing artifacts
  → Split into at least two clips
  → Emotion Change on exactly one selected clip
  → Stitch the edited clip and untouched clip(s)
  → final project audio export
```

The test must prove that the selected clip is replaced by the Emotion output while every unselected clip comes from the original split. The runner must preserve the TTS, split, emotion, and stitch job IDs and their artifacts as one auditable pipeline run.

**Tests:** run the acceptance pipeline above on a real timed multi-character TTS result; verify segment selection and replacement precedence; compare final duration and manifest; verify failure/retry from the Emotion step without repeating TTS or Split; reject invalid artifact connections; verify output provenance; and execute through the Hermes-facing API without raw localhost browser/curl access.

**Gate:** the saved TTS → Split → one-clip Emotion → Stitch pipeline completes through one high-level run, exports final audio, and can retry a failed downstream step without raw ComfyUI graph editing or repeating completed upstream work.

### Phase 10 — Music & Sound page and ACE-Step Music Maker

**Status:** implemented and live-tested. Generation is distinct from ACE-Step fine-tuning.

**Page boundary:** create a dedicated **Music & Sound** page instead of adding these controls to the speech/dialogue-focused Audio Studio. Its first sections are **Music Maker** and **Sound Effects**; ACE-Step fine-tuning appears as a separate preparation/training section only after Phase 12 gates pass. Do not build or duplicate a curated sound-effect library on this page.

**Chosen execution path:** use ComfyUI for generation because ACE-Step V1 is already installed as `models/checkpoints/ace_step_v1_3.5b.safetensors`, and the repository already contains separate song and instrumental UI workflows. Preserve those originals and create fixed API-format copies under Story Builder.

**Work:**

- Clean and convert `workflows/qwen_image/audio_ace_step_1_t2a_song.json` and `audio_ace_step_1_t2a_instrumentals.json` into fixed API workflows.
- Map friendly parameters to fixed nodes: mode (`song` or `instrumental`), tags/prompt, structured lyrics, duration, seed, steps, CFG, scheduler, sampler, model shift, lyrics strength, and deterministic output prefix.
- Supply safe presets while retaining an Advanced section for proven values. Hermes submits the friendly schema and never edits node IDs.
- Add the **Music Maker** section to the dedicated Music & Sound page with mode, tags, lyrics editor, duration, seed, quality controls, job status, playback, download, and project-output selection.
- Save request, submitted workflow, seed/settings, model identifier, generated audio, and generation report under the project; export the accepted result under `output/<project-id>/audio/`.
- Record the installed ComfyUI limitation for multilingual lyrics: non-English lyrics may require explicit language markers and romanization rather than silently promising automatic conversion.
- Treat retake, repaint, lyric edit, audio-to-audio, and extend as later sub-blocks. They are not part of the first Music Maker gate merely because the standalone ACE-Step GUI advertises them.

**Tests:** validate the live ComfyUI node schemas and checkpoint; run one short instrumental and one short structured-lyrics song through `/prompt`; verify seed repeatability, duration, output collection, restart rerun, browser execution, Hermes execution, and human listening. Confirm no image/video workflow regressions and no modifications to ComfyUI core or the original workflows.

**Gate:** both Song and Instrumental presets generate playable project-owned audio through the Story Builder API and WebUI with auditable parameters.

### Phase 11 — Control-Foley sound effects (replaces Hunyuan Foley)

**Status:** implemented offline and in the browser; live generation for all three modes remains pending. Hunyuan Foley is removed from the product surface and replaced by the supplied Control-Foley workflows.

**Modes:** Text → Audio uses `05_t2a_basic.json`; Text + Video → Audio uses `02_tcv2a_text_controlled.json`; Reference Audio + Video → Audio uses `03_acv2a_audio_controlled.json`. The third workflow is not true audio-only because it has a required video loader/connection.

**Work:** preserve all sources in `workflows/ricky/control folley/`; produce fixed API copies; validate live node/model schemas; stage only required uploads per selected mode; expose friendly generation settings; collect WAV as the primary output; retain muxed video only as an optional secondary artifact; add dynamic Music & Sound controls; and expose the same typed contract to Hermes. The detailed authoritative contract is in **Next implementation revision — Audio layout, Control-Foley, and Automation** above.

**Tests:** schema and invalid-input tests; one live job for every enabled mode; duration/seed/settings checks; audio collection and optional mux collection; project export; restart rerun; browser and Hermes execution; and human listening.

**Gate:** every displayed mode completes through a fixed Story Builder-owned API workflow with exactly its required fields, a playable audio output, complete provenance, and no raw ComfyUI manipulation by Hermes.

### Phase 12 — ACE-Step LoRA fine-tuning

**Status:** research/planned and approval-gated. The checked-in code trains LoRA adapters; it does not produce a replacement all-in-one ComfyUI base checkpoint automatically.

**Dataset contract found in the repository:** every sample uses an exact basename triplet:

```text
track.mp3
track_prompt.txt   # comma-separated genre, vocals, instruments, mood, tempo/key tags
track_lyrics.txt   # structured lyrics; required by the current converter even if conceptually optional
```

`convert2hf_dataset.py` converts those triplets into a Hugging Face dataset containing the audio filename, tag list, normalized lyrics, and metadata. The training code loads that dataset, the ACE-Step base checkpoint, MERT, and a JSON LoRA configuration; it saves adapter directories such as `epoch=<n>-step=<n>_lora` rather than `.pth` voice examples.

**Work:**

- Audit licenses/consent, duplicate audio, clipping, silence, corrupt files, exact triplet matching, prompt-tag quality, lyric structure/language, duration, sample rate, and train/validation split before training.
- Build a project-owned dataset uploader/editor that groups the three files by basename, shows missing/mismatched files, previews audio, and lets the user correct tags and lyrics.
- Convert into a project-owned Hugging Face dataset without using the source repository's example/output directories or unsafe `repeat_count=2000` default. Repetition is an explicit advanced setting with a displayed effective sample count.
- Run an AArch64/CUDA preflight in a separate ACE-Step Python environment: Python version, PyTorch/CUDA build, `transformers==4.50.0`, `pytorch_lightning==2.5.1`, `datasets==3.4.1`, PEFT, MERT download/cache, disk, RAM/VRAM, BF16 support, and a one-batch forward/backward smoke test.
- Expose only verified training controls initially: base checkpoint, dataset, experiment/adapter name, LoRA preset/rank/alpha, learning rate, max steps, checkpoint interval, precision, gradient accumulation, workers, resume checkpoint, and validated output directory.
- Track training as a cancellable job with logs, metrics, checkpoints, disk usage, failure reason, and resume support. Never run the repository default `max_steps=2000000` without an explicit bounded user choice.
- Save LoRA adapters in a Story Builder training registry with base-model identity, dataset provenance, configuration, hashes, and validation audio—not in the reference-voice library.
- Prove inference in the standalone ACE-Step pipeline first. Then determine whether the produced PEFT adapter can be loaded by the installed ComfyUI ACE-Step implementation. The current Comfy workflows use `CheckpointLoaderSimple` with an all-in-one checkpoint and contain no LoRA loader, so ComfyUI compatibility must not be assumed.
- If a compatible ComfyUI loader/conversion exists, create a copied API workflow and register the adapter in a dedicated ACE-Step LoRA catalog. Otherwise, keep fine-tuned inference in an isolated ACE-Step service and let Story Builder call it through the same job contract.
- Add an **ACE-Step Fine-tune** section to the dedicated Music & Sound page only after the smoke test passes. It shows Dataset, Preflight, Training, Checkpoints, and Validation sections and clearly distinguishes base model, LoRA adapter, and generated music.

**Tests:** dataset triplet validation; converter fixture; empty/corrupt/mismatched rejection; AArch64 dependency preflight; one-batch and short bounded training smoke tests; cancellation/resume; adapter reload; before/after fixed-seed inference; output hashing/provenance; clean restart; and, only if proven, ComfyUI adapter discovery and API generation.

**Gate:** a consented small dataset produces a reloadable LoRA adapter on the active AArch64 system, fixed-seed validation audio is reviewed, and exactly one tested inference route—ComfyUI or isolated ACE-Step—is registered. Until then the WebUI remains preparation/research-only and cannot start full training.

### Phase 13 — Audio Utilities page

**Status:** planned. This page contains curated assets and deterministic/manual processing, separate from generative speech and music creation.

#### Curated audio manager

- Add one or many audio files by drag-and-drop, ordinary file picker, or folder picker while preserving relative folder structure.
- Store reusable curated assets in a dedicated Story Builder-managed library, not in ComfyUI models, ACE-Step training data, or project generation runs.
- Show filename, relative source path, duration, format, sample rate, channels, size, tags/notes, waveform preview, and playback.
- Support search, rename/metadata editing, project copy/link, download, and explicit removal. Hash files for duplicate detection; never silently overwrite a same-named asset.
- This is user-managed source material only. It is not used as Hunyuan reference conditioning.

#### Speech Noise Cleanup

- Move the planned `audio/denoiser` Noise Cleanup form from Audio Studio to Audio Utilities; Voice Repair remains in Audio Studio because it is a generative-speech auxiliary.
- Accept one audio file, multiple dropped files, or a folder upload. Also allow selecting curated/project audio.
- Require an output collection name/folder. Browser folder uploads preserve relative paths; backend destinations are resolved inside approved library/project/output roots rather than accepting unrestricted filesystem writes.
- Run each input as a tracked batch item with model, dry/wet setting, status, logs, source/output preview, and failure isolation.

#### Extract MP3 from video

- Wrap `youtube_code/mp3_extract.py` without interactive terminal prompts.
- Accept one video, multiple videos, drag-and-drop, or a folder containing supported `.mp4`, `.mkv`, `.webm`, `.mov`, and `.avi` files.
- Accept an output collection/folder and preserve relative input structure for batch jobs.
- Use FFmpeg to extract audio-only MP3 with an explicit quality setting; default output is `<video-stem>.mp3`. Report files with no usable audio stream individually rather than failing the whole batch.

#### Demucs instrument/stem separation

- Wrap `youtube_code/demucs_split.py` as a non-interactive batch executor.
- Accept one audio file, multiple dropped files, a folder upload, curated audio, or project audio, plus an output collection/folder.
- Expose 2 stems (`vocals`, `no_vocals`), 4 stems (`vocals`, `drums`, `bass`, `other`), and 6 stems only when the selected installed model genuinely supports it.
- Preserve the requested numbered filenames—`filename_1`, `filename_2`, and so on—but write a manifest mapping every number to its semantic stem name. Never infer `_1 = vocals` merely from alphabetic file sorting.
- Produce separate playable/downloadable output files, model/device/settings, duration/synchronization report, and partial-failure status for batch inputs.

#### Common file/folder behavior

- Every tool supports a single-input mode and a batch/folder mode. The WebUI shows discovered input count before execution.
- A browser cannot safely expose arbitrary local paths by default. Folder selection therefore uses drag/drop or a directory-upload picker; output folders are Story Builder-managed collections. A trusted-local path mode may be added only with strict configured allowlisted roots and traversal checks.
- Originals are immutable. Jobs stage inputs, write to a new job directory, maintain an artifact manifest, and optionally copy accepted outputs to `output/<project-id>/audio/`.
- The backend APIs use the same batch schemas for the browser and Hermes.

**Tests:** single and folder upload; nested relative paths; duplicates; unsupported/corrupt files; missing FFmpeg/audio stream; CPU/CUDA preflight; cancellation and partial batch failure; denoiser AArch64/quality tests; Demucs 2/4-stem name mapping and synchronization; safe output-root enforcement; playback/download; and browser/Hermes execution.

**Gate:** curated import, batch speech cleanup, batch video-to-MP3 extraction, and Demucs 2/4-stem separation operate safely from the new page with deterministic manifests and no writes outside configured roots.

### Phase 14 — Complete the Web Audio process builder

Extend the existing Audio Studio only after the underlying blocks and contracts are stable. It should configure and order registered operations, not expose ComfyUI node wiring.

The remaining UI work includes:

- Extend the existing block library into an n8n-style ordered process canvas
- Source audio, SRT, transcript, manifest, model, and reference selection
- One shared engine/base-or-fine-tuned model per timed TTS block
- Fine-tuning forms only for verified supported engines
- Timeline/segment selection
- Per-block settings, run, status, logs, retry, and outputs
- Source/output A/B audio previews
- Final stitch and export
- Music Maker as a source block after Phase 10 passes
- Control-Foley as a text/video/reference-conditioned audio block after its live Phase 11 gate passes
- A fine-tuned ACE-Step adapter selector only after Phase 12 proves its inference route

The browser, Hermes, and tests must all call the same backend registry and runner.

**Gate:** every visible control maps to a tested backend capability; the UI does not advertise unverified model training or audio transformations.

## Protection of ComfyUI and TTS-Audio-Suite

- Do not edit the original reference workflows; create named production copies.
- Do not overwrite original model checkpoints, bundled reference voices, or global alias maps.
- Prefer Story Builder adapters and fixed API workflows over custom-node edits.
- If a custom-node extension is unavoidable, keep it minimal, additive, version-controlled as a patch/overlay, and backward-compatible.
- Back up and checksum the exact files before applying an extension.
- Test extensions first against a copied/sandboxed custom-node checkout when practical.
- Never let the web UI accept arbitrary destination paths into ComfyUI directories; resolve catalog destinations server-side.
- Use temporary staging, validation, then atomic placement for voices and models.
- Preserve ownership and permissions expected by the ComfyUI process.
- Refresh catalogs through supported mechanisms; restart ComfyUI only when testing proves refresh is insufficient.
- After every model/voice installation test both warm-cache and clean-restart discovery.
- Keep all generated/intermediate project audio outside model and reference libraries.
- Record every external file installed into ComfyUI with source, checksum, destination, compatibility, and removal instructions.

## First Deliverable

The first vertical slice should be:

```text
TTS_audio_multichar_timed_wf.json
  → production API-format copy
  → bridge parameter mapping
  → Hermes request
  → ComfyUI execution
  → saved WAV + SRT + reports in output/
```

The pinned Phase 9 acceptance slice combines generation and modular editing:

```text
Timed multi-character TTS audio
  → Python split into at least two clips + manifest
  → Emotion Change on exactly one selected clip
  → Python stitch
  → saved final audio + provenance/timing report
```

This proves both halves of the architecture in one resumable run: API-ready generation followed by selected-segment split/edit/stitch composition.

## Definition of Done for Each Block

A block is complete only when:

- Its purpose is narrow and documented.
- Its input/output JSON schema is validated.
- Its required models and custom nodes are listed.
- Its ComfyUI workflow is API format, if applicable.
- Friendly parameters map to fixed workflow inputs.
- It saves output deterministically.
- It runs through the bridge without browser or localhost web tools.
- Hermes can invoke it by operation name.
- Errors name the failed operation and useful cause.
- A representative end-to-end test succeeds.
- The resulting audio passes a listening check.
