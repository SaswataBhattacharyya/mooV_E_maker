# Video Summariser Upgrade Plan

## Status and scope

This is a planning document. It does not authorize implementation by itself.

The goal is to improve the existing Video Repertoire & Summariser without disturbing the parts that already work well:

- source-video registration and playback;
- scene/cut division;
- current frame extraction and representative-frame selection;
- resumable analysis jobs;
- clip extraction and timestamp preservation;
- current Video Repertoire page and existing Story Builder routes;
- existing audio, image, story, ComfyUI, Ollama, Hermes, and automation features.

The current Story Builder integration is additive and still runs the legacy frame/image-report path. That is an interim state, not the intended final analyzer. The authoritative target is now a clip-first, direct-video understanding pipeline defined immediately below. Existing scene/cut boundaries and timestamped clip extraction remain the temporal partition; sampled frames may be used internally for those deterministic utilities or as transient thumbnails/evidence, but must not be persisted as a large frame collection or sent one-by-one through an image captioning loop.

## Authoritative clip-first replacement contract (2026-09-28)

This section is the source of truth for the analyzer replacement and supersedes conflicting earlier wording in this document, especially any wording that makes frame-by-frame Image Detailer prose the primary report, describes InternVideo as merely optional, or treats the already integrated legacy visual report as the completed replacement. The dated implementation ledger later in the file records what was actually built; it does not redefine the target.

### Product outcome

For each source video, retain the original and create timestamped scene/cut clips. Do not persist every decoded frame. InternVideo3-8B-Instruct is the intended primary video-understanding and narrative-summary model: its processor receives the clip/video path directly and internally samples video frames. Any decoded frames needed by scene detection, frame shaving, OCR, a thumbnail, or a specialist tool are transient/selected evidence only and follow the existing cleanup policy.

Every source video gets one coherent video-level summary. Every clip gets a context-aware text record that combines:

- the clip's visual/action summary from InternVideo3;
- timed transcript segments overlapping that clip, with language and source/confidence;
- speaker IDs and voice metadata when enabled/available;
- timestamped music, SFX, ambience, and other audio events overlapping the clip;
- whole-video context, neighboring clip context, evidence references, uncertainty, and model provenance.

The source clip asset keeps its original synchronized audio. Audio/event excerpts are separate derived assets only when the relevant per-job collection toggle is enabled or an explicit SAM Audio save is approved. A clip summary must not claim that sound was isolated merely because an event was detected or text-labelled.

### Summary/context pass order

Default long-video path is deliberately hierarchical and bounded:

1. **Clip evidence pass:** preserve existing scene/cut boundaries and timestamps; run InternVideo3 directly on each clip (clips may be batched/processed concurrently within GPU-memory limits). Produce a compact, evidence-grounded draft summary and visual/action cues for that interval. Do not run a vision-language model on every sampled frame.
2. **Whole-video synthesis:** order clip drafts chronologically and combine them with the timed transcript, speaker turns, and audio-event/music records. Ask InternVideo3 to synthesize the overall narrative, progression, recurring entities, and audio context from this compact timeline. If a tested duration/token budget allows, an optional direct whole-source-video pass may contribute evidence, but it does not replace the timestamped clip pass or audio timeline.
3. **Context refinement:** revise each clip's text using the whole-video summary plus only that clip's draft/evidence, overlapping transcript/audio events, and immediate neighboring clip summaries. This backward context pass resolves references and progression without re-decoding the video. It may be batched as text-only requests to reduce overhead. Preserve the initial draft and refinement provenance; never allow the global summary to overwrite conflicting local evidence silently.

For short videos, a benchmarked whole-video-first route may be used: summarize the video directly, then analyze each clip with that summary as context. The chosen route must be deterministic/configurable, recorded in the manifest, and selected by preflighted duration/token/GPU limits—not by an unbounded retry loop. Both routes must yield the same versioned output schema. No repeated refinement loop is required; exactly one bounded refinement pass is the default. If confidence remains low, keep uncertainty explicit rather than repeatedly asking the model.

InternVideo3's documented quickstart accepts a video path with an FPS argument (example 4 FPS); this is model-internal sampling, not a requirement to extract/persist all source frames. The model is a video-understanding generator, not a semantic vector index. PE-AV has the separate retrieval responsibility below.

### Canonical InternVideo3 checkpoint and manual staging

- Official project/inference documentation: [OpenGVLab/InternVideo3](https://github.com/OpenGVLab/InternVideo/tree/main/InternVideo3).
- The official quickstart points to Hugging Face snapshot [`yanziang/InternVideo3-8B-Instruct`](https://huggingface.co/yanziang/InternVideo3-8B-Instruct). Treat this as the documented checkpoint source; do not silently swap in an unrelated InternVideo/InternVL model.
- Stage the complete Hugging Face snapshot (all five language safetensors shards, vision/projector weights, index/config/tokenizer/processor files and the model's Python implementation) at:

  `/home/riki/web_dev/story_builder/video_audio_analyzer/models/internvideo3-8b-instruct/`

- The Hub currently reports about 18.7 GB of files. Keep additional free disk for download/cache and runtime; the snapshot size is not the inference-memory requirement. Do not put the model in the legacy `video_summariser`, ComfyUI models, `video_repertoire`, or a shared Conda environment.
- A full repository clone is not required for the Transformers quickstart. The complete model snapshot is required. The isolated analyzer worker must load it by local path with network access disabled during analysis; pin the Hub revision and record its commit/hash. As the model uses `trust_remote_code`, inspect/pin the shipped model code and run it only inside the isolated analyzer worker.
- Manual staging command (run in an environment with `huggingface_hub` installed; this command is documentation only and is not run as part of plan editing):

  ```bash
  python3 -c 'from huggingface_hub import snapshot_download; snapshot_download(repo_id="yanziang/InternVideo3-8B-Instruct", local_dir="/home/riki/web_dev/story_builder/video_audio_analyzer/models/internvideo3-8b-instruct")'
  ```

- The official quickstart lists `transformers>=4.57.3`, PyTorch, and `qwen-vl-utils`, and uses `trust_remote_code=True`, `device_map="auto"`, BF16 and SDPA. These are starting requirements, not permission to upgrade an existing image blindly. Preflight the host architecture, CUDA/PyTorch, Transformers compatibility with the existing PE-AV worker, video decoder, processor, VRAM/RAM, model license and a real clip smoke test. Put incompatible requirements in a dedicated `video-caption-worker` image/runtime under `video_audio_analyzer/`; never modify ComfyUI, other Docker projects, or shared Conda packages.
- Do not claim speed or quality before measuring cold-start/load time, per-minute inference throughput, peak GPU/RAM, output completeness, and summary quality on both the 8.73-second supplied meme and a longer representative video. InternVideo3 is the designated primary replacement candidate, but it becomes the active production backend only after that preflight/benchmark gate passes.

### Retrieval/index contract: PE-AV plus generated text

PE-AV remains the primary semantic retrieval encoder, not the narrative generator. For every clip, create linked, separately typed and versioned retrieval records for (when enabled/available): raw clip video embedding, clip audio embedding, joint audiovisual embedding, and canonical clip-text embedding. The clip-text input includes the refined clip summary, transcript, speaker/voice tags, and timestamped sound/music/ambience descriptions. Also index the whole-video summary as a video-level text record, and optionally a video/joint AV vector. All records share stable `video_id`, `scene_id`, `clip_id`, and time ranges and point back to the same playable source clip.

Do not concatenate independently trained vectors or silently average away their meaning. Keep PE-AV modality vectors in their documented aligned space and CLAP in its separate versioned space. A text query is embedded by PE-AV and can retrieve both video/AV and text records; rank/fuse the matching per-modality scores with documented late fusion, then deduplicate/group by clip. Keyword search remains available. A video-level summary hit opens the matching video and can expand into its ranked clips. Missing PE-AV must result in explicit lexical-only/unavailable semantic status, never fabricated semantic results.

### One authoritative asset/storage rule

`video_repertoire/` is the sole durable location for source videos and reusable clips/audio/voice/SFX/music assets, their manifests, and shared indexes. `video_audio_analyzer/runs/` is transient/resumable processing workspace only; after a successful commit, promote the canonical outputs to `video_repertoire/` and clean redundant run copies according to the established retention/rollback rules. Do not create a second durable copy of the same media in another analyzer folder. Frames are not a durable asset category for this target; keep only specifically selected thumbnails/evidence if a UI feature needs them and treat them as disposable/regenerable.

### Replacement and verification gate

The current additive integration does **not** satisfy this contract because it still invokes the legacy frame/Image Detailer/scene-prose path before/alongside PE-AV. The replacement phase must route website analysis to the clip-first worker behind the existing reversible backend switch only after direct-video inference works, outputs are useful, the same-source comparison and storage checks pass, and Playwright confirms no regressions. Preserve the current UI routes, library/source flow, cut boundaries, timestamps, audio toggles, job lifecycle, and semantic-search API contract; update only the analyzer stage contract/results needed for these clip summaries and vector records.

### Per-job Stop/Delete controls

Every analysis job card (active and historical) exposes the appropriate destructive controls. These actions are backend-enforced; hiding a button in the UI is not a cancellation/deletion mechanism.

- **Stop** appears for queued/running jobs. It requests cancellation, stops the worker at the safest supported stage boundary (or terminates it after a bounded grace period), waits until the worker can no longer write, then removes the stopped job and all job-owned partial/transient outputs. It must not leave an apparently running job or orphaned temporary files. The original registered source video is never removed by Stop.
- **Delete** removes a selected job, its job record, run folder, logs/temp files, index rows, and all derived repertoire assets owned only by that job. Before removing any canonical asset, verify its ownership and references; shared/reused assets remain if another project/job references them. The original registered source video is never removed by deleting an analysis job. Deleting multiple jobs requires a confirmation dialog that identifies the scope/count before deletion.
- Stop and Delete are idempotent and safe under retries, stale UI state, concurrent tabs, service restarts, and partially failed filesystem cleanup. The backend validates job IDs and resolves all paths under approved analyzer/repertoire roots; it must reject path traversal and must not accept arbitrary client-supplied deletion paths.
- **Resume is best-effort, not a pause feature or a guarantee.** First determine whether the last completed stage has a validated checkpoint already in the canonical repertoire and whether the pipeline can safely create a fresh job that references it without retaining duplicate run files. If so, offer `Resume from checkpoint`; otherwise Stop cleans the partial job and the user can `Restart` from the original source. Do not retain hidden partial folders merely to claim resumability. A complete Delete always removes the selected job; any retained shared asset must be disclosed as shared/reference-protected.
- The UI must distinguish `Stop & discard this run` from `Delete job/output` in labels and confirmation copy, show progress while cancellation/cleanup is underway, and refresh the active/history lists after the backend confirms the final state. If cleanup fails partially, show which owned paths remain and provide an idempotent retry-cleanup action; never report success while files remain.

## Audio intelligence extension

Audio is a first-class output of Video Summariser analysis. It is not a separate afterthought on Audio Utilities.

The existing Audio Utilities already provides FFmpeg video-to-MP3 extraction, isolated Demucs 2/4/6-stem separation, project-owned audio outputs and manifests, and GPU/CPU selection. Video Summariser will call those utilities through a shared service contract rather than duplicating the implementation or modifying the ComfyUI/Docker environment.

### Default analysis settings

The following settings are enabled by default for a new Video Summariser analysis:

```text
Extract original audio: on
Analysis WAV: on
MP3 preview: on
Run Demucs: AUTO
Detect speech events: on
Detect music events: on
Detect SFX/ambience events: on
Create audio embeddings: on
Create audiovisual embeddings: on
Diarization: on
Same-speaker embeddings: on / ECAPA
Character tracking: Auto when people are detected
Active-speaker association: on
Music analysis: on
Voice feature analysis: on
```

`Run Demucs` is a five-state control: `AUTO`, `off`, `2-stem`, `4-stem`, or `6-stem`. `AUTO` is the default. In AUTO mode, event detection runs first; Demucs runs when music/stem analysis, voice cleanup, or a requested repertoire asset needs it. Every audio control is independent of frame-analysis controls such as frame shaving, scene compaction, extraction FPS, and delete-frames-after-run.

SAM Audio isolation is `ON-DEMAND`, not a default full-video pass. It is invoked only for a selected or high-confidence event such as `footsteps`, `door slam`, `rain`, a speech segment, or a music phrase.

The UI exposes these controls independently:

| Function | Default | UI control | Alternatives |
|---|---|---|---|
| Sound-event detection | On | Toggle | Off |
| Event detector | Auto: HTS-AT → PANNs | Dropdown | HTS-AT / PANNs |
| Semantic audio embeddings | On | Toggle | Off |
| Audio/AV embedding model | Auto: PE-AV → CLAP | Dropdown | PE-AV / CLAP / PE-AV + CLAP |
| Audiovisual embeddings | On | Toggle | Off |
| Speech transcription | On | Toggle | Off |
| Speaker diarization | On | Toggle | Off |
| Diarization backend | NeMo | Dropdown | NeMo / pyannote / Off |
| Same-speaker embeddings | On / ECAPA | Toggle | Off |
| Character tracking | Auto when people detected | Dropdown | Auto / On / Off |
| Active-speaker association | On | Toggle | Off |
| Demucs | Auto | Dropdown | Off / 2 / 4 / 6 stem |
| SAM Audio isolation | On demand | Action/toggle | Selected assets only |
| Music analysis | On | Toggle | Off |
| Voice feature analysis | On | Toggle | Off |

`Auto` means preflight the preferred model and fall back without failing the analysis. The resolved backend and model are written into the analysis manifest.

If an optional audio runtime is unavailable, analysis continues with a clear per-stage status. The system must never claim that a missing audio stage completed.

### Audio artifacts

For each analyzed source video, create a repertoire package:

```text
video_repertoire/audio/<video-id>/
├── source_audio.m4a-or-opus
├── analysis.wav
├── preview.mp3
├── stems/
├── speech/
├── music/
├── sfx/
├── ambience/
└── audio_manifest.json
```

The source bitstream is retained when it can be copied without re-encoding. `analysis.wav` is model-friendly PCM; `preview.mp3` is for browser playback/export. The manifest records the actual stem names for the selected Demucs mode. Stems and event clips are derived artifacts that can be regenerated.

SAM Audio isolation is lazy and Codex-director-controlled (Hermes is an explicitly configured fallback only):

```text
detected event → Codex requests isolation when useful (Hermes only if explicitly configured as fallback)
  → temporary WAV preview
  → quality/provenance check
  → Codex issues save_to_repertoire → persist isolated WAV and provenance
  → otherwise expire/delete temporary WAV
```

The UI may also request a preview, but detection is not isolation and isolation is not permanent storage. It is never run across every detected event automatically. This prevents thousands of derived WAV files from being created for a long video.

### Audio event records

Every detected audio event links to the visual hierarchy:

```json
{
  "event_id": "audio-event-00021",
  "video_id": "video-...",
  "scene_id": "scene_003",
  "clip_id": "scene_003_cut_002",
  "start_time_sec": 32.1,
  "end_time_sec": 34.5,
  "event_type": "sfx",
  "label": "metal door slam",
  "source_stem": "other.wav",
  "confidence": 0.86,
  "embedding_refs": {},
  "provenance": {}
}
```

Initial event types are speech, music, sound effect, ambience/room tone, silence/noise, and uncertain/mixed.

Demucs is a source-separation tool, not a complete SFX classifier. A stem such as `other.wav` must not automatically be labelled as sound effects. Event labels require audio embeddings, a controlled classifier/vocabulary, timestamps, and confidence.

### Detection before separation

The audio branch must not be implemented as `audio → Demucs → semantic labels`.

The required order is:

```text
original mix
  ├── audio event detection (PANNs or HTS-AT)
  ├── PE-AV/CLAP semantic embeddings
  ├── speech pipeline
  ├── music analysis
  └── optional source separation (Demucs)
          └── optional selected-event isolation (SAM Audio)
```

PANNs/HTS-AT supplies a controlled vocabulary and frame-level event scores. PE-AV/CLAP supplies free-language semantic matching. Demucs is retained for music-production stems and voice cleanup; SAM Audio is reserved for isolating an arbitrary selected sound using text, visual, or time-span prompts.

### Recommended audio stack

| Purpose | Preferred component | Fallback/notes |
|---|---|---|
| Source/preview extraction | FFmpeg | Preserve source bitstream when possible |
| Speech transcription/alignment | WhisperX | Existing ASR adapter or Whisper fallback |
| Diarization/overlap | NeMo local diarization | pyannote community-1 is optional; no HF token is required for the default path |
| Optional diarization backend | pyannote community-1 | Requires model access approval/token before download, then can run offline |
| Speaker identity | ECAPA-TDNN/SpeechBrain | Store centroid and per-segment embeddings |
| General sound events | PANNs or HTS-AT | Controlled labels plus timestamps |
| Audio semantics | PE-AV, CLAP fallback | Shared text/audio space |
| Visual-audio semantics | PE-AV | Fused event retrieval |
| Music features | Essentia + librosa | BPM, key, beats, energy, sections |
| Source stems | Demucs | AUTO by default; 2/4/6-stem explicit modes |
| Selected sound isolation | SAM Audio | Lazy preview; persist only when explicitly saved |
| Pitch/prosody | torchcrepe/CREPE + Parselmouth | Measured fields, not invented labels |

Every model has a preflight gate, checkpoint provenance, license record, and graceful fallback. No model in this table may trigger an unapproved Docker or ComfyUI modification.

## Canonical model/repository registry and preflight

The implementation must use these canonical projects and must not silently substitute an arbitrary fork. The registry is versioned with the application and is the source of truth for UI readiness, worker selection, and audit manifests.

| Capability | Canonical repository | Model/checkpoint | Policy |
|---|---|---|---|
| Media decoding | `FFmpeg/FFmpeg` | system FFmpeg | required core capability |
| Direct video understanding and narrative summaries | `OpenGVLab/InternVideo` → `InternVideo3` | `yanziang/InternVideo3-8B-Instruct` | primary clip/video summarizer; complete local snapshot under `video_audio_analyzer/models/internvideo3-8b-instruct/`; direct-video path and isolated runtime must pass benchmark before activation |
| Multimodal retrieval | `facebookresearch/perception_models` | `facebook/pe-av-base` | primary; variable-length Base |
| Audio-text fallback/reranker | `LAION-AI/CLAP` | repository-documented checkpoint | separate vector space; fallback/late reranker |
| Sound-event detection | `RetroCirce/HTS-Audio-Transformer` | repository-documented pretrained HTS-AT checkpoint | primary when preflight succeeds |
| Sound-event fallback | `qiuqiangkong/panns_inference` | repository-documented PANNs checkpoint | fallback tagging/SED |
| ASR/alignment | `m-bain/whisperX` | `Systran/faster-whisper-large-v3` | prefer large-v3 unless benchmark says otherwise |
| Default diarization | `NVIDIA-NeMo/Speech` | local NeMo clustering diarizer | default; benchmark unrestricted speaker counts |
| Optional diarization | `pyannote/pyannote-audio` | `pyannote/speaker-diarization-community-1` | optional only; gated/token-dependent |
| Persistent speaker identity | `speechbrain/speechbrain` | `speechbrain/spkrec-ecapa-voxceleb` | versioned Voice Store centroid model |
| Source separation | `adefossez/demucs` | `htdemucs` / `htdemucs_ft` and supported six-source model | `AUTO` policy; explicit off/2/4/6 modes |
| Arbitrary sound isolation | `facebookresearch/sam-audio` | `facebook/sam-audio-base-tv` | lazy/on-demand; gated; never required |
| Music features | `MTG/essentia`, `librosa/librosa` | package/model versions | BPM, key, beats, loudness, sections |
| Pitch/prosody | `maxrmorrison/torchcrepe`, `YannickJadoul/Parselmouth` | package/model versions | measurable acoustic evidence |
| Face identity | `deepinsight/insightface` | selected checkpoint after license preflight | code and weights licenses recorded separately |
| Geometry tracker | `FoundationVision/ByteTrack` | selected release | tracking only; no ReID claim |
| Appearance/ReID | `mikel-brostrom/boxmot` | BoT-SORT/StrongSORT-compatible backend | optional identity-sensitive tracking |
| Pose evidence | `open-mmlab/mmpose` | selected compatible model | supporting evidence only |
| Active speaker | `luongnguyenminhan/TalkNet` | repository checkpoint | isolated adapter/runtime because of older dependencies |

For each registry entry, preflight records: component and purpose; backend; repository and commit/version; model/checkpoint ID; Python/Torch/CUDA requirements; host/container architecture; GPU availability; checkpoint path; gated/authentication status; code license and checkpoint/model license separately; expected and actual embedding dimensions; smoke-test result; failure reason; and selected fallback. A gated or unavailable optional model is shown explicitly in the UI and cannot block the rest of analysis.

Preflight is read-only: it must not download, modify Docker, modify ComfyUI, or install packages automatically. A later, explicitly approved preparation command may populate a worker image or local model cache.

## Docker/runtime boundaries

The website remains the existing Story Builder application and the Video Summariser remains the existing `/video-summariser` route. Dockerization applies to the analysis workers and supporting services, not to a replacement UI and not to the ComfyUI environment.

Before creating images, inspect the current Docker files, utility-runner abstraction, Python environments, host architecture, CUDA/Torch versions, and existing service ports. Choose the least disruptive boundary: isolated images, isolated virtual environments, or subprocess workers. Do not blindly force three containers if the existing worker abstraction already provides isolation.

The proposed logical boundaries are:

1. `video-caption-worker`: InternVideo3-8B-Instruct direct-video generation and clip/video summary passes; isolate if its Transformers/PyTorch requirements conflict with other workers.
2. `video-perception-worker`: PE-AV embeddings, face/person tracking, optional BoxMOT/ReID, MMPose, and the TalkNet adapter.
3. `audio-analysis-worker`: WhisperX, NeMo, ECAPA/SpeechBrain, HTS-AT/PANNs, Essentia/librosa, CLAP, torchcrepe, and Parselmouth.
4. `audio-separation-worker`: Demucs and SAM Audio.

Workers exchange versioned manifests and timestamped files through the existing project storage. They must not share an uncontrolled site-packages directory. ComfyUI, its Docker image, nodes, wheels, and model paths remain untouched by this upgrade. Each worker has a GPU/CPU preflight and a graceful “unavailable” state, so a missing PE-AV, SAM Audio, TalkNet, or ReID dependency does not disable source import, scene detection, frame selection, subtitles, or basic reports.

## Voice extraction and searchable voice repertoire

The analysis also creates a reusable voice library from speech regions where duration and quality are sufficient.

### Voice extraction flow

```text
video audio
  ↓
speech activity detection + transcript timestamps
  ↓
optional vocal stem from Demucs
  ↓
speaker segmentation and diarization
  ↓
speaker embeddings
  ↓
clean voice examples
  ↓
voice metadata and semantic search index
```

Each anonymous speaker initially receives a stable ID within the source video, for example `video-abc_speaker-01`. The system must not claim that this is a named character or actor unless the identity is supported by labelled subtitles, credits, dialogue/context, prior trusted identity evidence, or a reliable external source. Codex is the director/confirmation authority; Hermes is an explicitly configured Codex fallback only.

### Character association pipeline

MMPose is a pose/keypoint signal, not an identity system. Character association combines:

```text
face detection/embedding (InsightFace/ArcFace)
        +
body tracking/ReID (ByteTrack/StrongSORT-style tracker)
        +
pose/keypoints (MMPose when enabled)
        +
active-speaker detection (TalkNet or compatible adapter)
        +
speaker diarization (NeMo default; pyannote optional)
        +
voice identity (ECAPA centroid)
        ↓
UUID-backed character identity
```

The association result is evidence-weighted. A visible person is not declared the speaker solely because they are in the frame. Active-speaker evidence, face visibility, timing overlap, voice similarity, and tracking continuity are recorded separately.

Each identity has two stable internal IDs:

```text
character_id: char_8F32A91C
voice_identity_id: voice_D91BF21A
```

The friendly display label is mutable:

```text
display_name: Character-K7M2
```

The label may later become `Alice` or another Hermes-confirmed name, but the UUIDs never change and are never used as database keys by display name.

### Voice Store matching

Before creating a new voice identity, query the current project's LanceDB ANN partition for top-K ECAPA centroids, then query the global partition only when no sufficiently supported local identity exists. Metadata filters restrict candidate scope; raw samples are never compared O(N²). Codex receives the bounded candidates plus face/body/voice evidence and confirms, rejects, or retains an anonymous UUID. Hermes may perform that decision only when explicitly configured as the Codex fallback. A similarity threshold alone never merges identities. Every decision stores model/version, score, source project/video, evidence, timestamp, and merge provenance.

### Character naming workflow

The system may propose a name from labelled subtitles, credits, OCR, dialogue/context, or continuity evidence:

```text
Character detected
ID: char_8F32A91C
Suggested name: Alice
Confidence: 0.97

[Confirm Alice] [Rename] [Keep anonymous]
```

These controls are optional non-blocking UI overrides; the unattended pipeline proceeds from the Hermes decision. Renaming updates only the display label and alias metadata. It never rewrites the underlying character or voice identity.

Each voice example stores:

- source video, scene, clip, and timestamps;
- speaker ID and transcript when available;
- language;
- pitch range, speaking rate, energy, and prosody measurements;
- perceived vocal register/presentation only when confidence is sufficient and with uncertainty;
- qualities such as calm, tense, angry, excited, whispering, or authoritative;
- noise and overlap scores;
- speaker embedding and semantic audio/text embedding;
- provenance, licensing, and model versions.

```json
{
  "voice_example_id": "voice-video-abc-speaker-01-004",
  "video_id": "video-abc",
  "speaker_id": "video-abc_speaker-01",
  "scene_id": "scene_004",
  "start_time_sec": 118.4,
  "end_time_sec": 124.2,
  "transcript": "I do not think we should go inside.",
  "tags": ["adult voice", "calm", "cautious", "low energy", "dialogue"],
  "quality": {"noise": 0.08, "overlap": 0.0, "confidence": 0.84},
  "identity": {"label": null, "source": "anonymous_diarization"}
}
```

### Character mapping

1. Diarization finds anonymous speakers.
2. Subtitles and dialogue labels provide possible names.
3. Face/body tracking, active-speaker evidence, voice embeddings, OCR, credits, and dialogue/context are passed to Codex.
4. Codex confirms the mapping, keeps the identity anonymous, or links it to an existing Voice/Character Store identity; Hermes is an explicitly configured fallback only.
5. The mapping and evidence are stored as project/reference metadata with an immutable audit record.

There is no mandatory human-confirmation gate. If subtitles are unlabeled, overlapping, or garbled, the pipeline continues with a collision-safe anonymous alias such as `Character-K7M2`; Codex may rename it later only when supporting evidence exists. Real-world names are never invented from an embedding alone.

### Voice semantic search

Voice searches may include queries such as:

- `deep male voice, calm and authoritative`;
- `frightened and breathless voice`;
- `angry courtroom dialogue`;
- `slow whisper with low energy`;
- `same speaker as this selected clip`.

Retrieval combines speaker identity embeddings, audio/text semantic embeddings, measured pitch/rate/energy filters, transcript/context, and quality constraints that exclude noisy or overlapping samples. Voice examples remain provenance-aware references and are not automatically converted into a cloning model.

### Voice Store matching scope and audit

Voice matching supports both the current project and the global cross-project Voice Store without comparing every raw sample to every other sample. The lookup order is:

1. query the current project's LanceDB voice partition using the versioned ECAPA centroid and ANN top-K retrieval;
2. if no sufficiently supported local identity exists, query the global/cross-project partition with the same top-K limit and metadata filters;
3. send the bounded candidate set and supporting face/body/voice evidence to Codex;
4. let Codex confirm, reject, or retain an anonymous identity; Hermes is an explicitly configured fallback only. Never merge solely because one similarity threshold was crossed.

Each candidate/decision record stores the similarity score, embedding model and version, source project/video, candidate identity, Hermes decision, supporting evidence, timestamp, and merge provenance. A configurable project-only fallback remains available if benchmarks show cross-project matching is harmful. Display names are never keys: `character_id` and `voice_identity_id` are immutable UUIDs, and collision-safe aliases are mutable UI labels.

### Measured versus inferred voice metadata

Store measurable properties separately from model predictions.

Measured fields:

- F0 median and range;
- speaking rate from aligned ASR words per voiced second;
- RMS energy and dynamic range;
- pause ratio;
- spectral centroid;
- harmonic/noise ratio;
- breathiness estimate;
- overlap percentage;
- SNR and clipping rate.

Inferred fields:

- vocal affect, for example tense or calm;
- style, for example whispered or conversational;
- perceived vocal register: low, mid, or high.

Do not store `male` or `female` as an unquestioned factual identity field. If a creative search needs that dimension, use an uncertain perceived-register/presentation field alongside pitch measurements.

## Shared multimodal event identity

Every meaningful interval receives one common `event_id` shared by visual, audio, speech, and reference records:

```json
{
  "event_id": "event-00421",
  "video_id": "video-abc",
  "start_time_sec": 112.32,
  "end_time_sec": 118.71,
  "scene_id": "scene_018",
  "clip_ids": ["scene_018_cut_002"],
  "frame_ids": ["frame_0091", "frame_0094"],
  "visual_embedding_ref": "...",
  "audio_embedding_ref": "...",
  "audiovisual_embedding_ref": "...",
  "transcript_segments": [],
  "speaker_ids": ["video-abc_speaker-01"],
  "audio_events": ["speech", "footsteps", "suspense_music"],
  "source_assets": {
    "original_interval": "...",
    "demucs_stem": "...",
    "isolated_sfx": null
  }
}
```

This event identity is the join key for:

- semantic audiovisual retrieval;
- visual clip references;
- audio/SFX/music references;
- speaker/voice examples;
- timestamp-linked playback;
- Hermes/director context.

## 1. Current Video Summariser functions

The current system has several distinct responsibilities. They must remain separate rather than being replaced by one large model.

### 1.1 Source and library management

Current responsibilities:

- import selected videos from `video_summariser/out_videos`;
- upload local videos;
- download reviewed YouTube sources;
- register source metadata, provenance, checksum, duration, resolution, and codecs;
- play full videos in the browser;
- select one or more videos for analysis;
- stop/cancel analysis jobs and delete selected jobs with their owned outputs;
- restart from source, or resume from a validated retained checkpoint only where safe;
- preserve job state after page refresh.

Upgrade decision: keep this subsystem. Add backend-enforced per-job Stop/Delete semantics, safe cleanup and optional validated checkpoint resume as specified in the authoritative clip-first contract. Preserve source registration and make clear that job cleanup never deletes its source video.

### 1.2 Technical video inspection

Current responsibilities:

- FFmpeg/FFprobe probing;
- duration, resolution, codec, and stream metadata;
- audio extraction;
- frame extraction;
- generated scene and clip media.

Upgrade decision: keep FFmpeg/FFprobe. Add source FPS detection and record both source FPS and analysis sampling FPS in every manifest.

### 1.3 Scene and cut division

Current behavior already produces useful scene divisions and should be preserved.

Upgrade decision:

- keep the existing scene/cut detector as the authoritative temporal partition;
- do not replace it with PE-AV, InternVideo, or a VLM;
- allow a later optional validation pass to flag suspicious boundaries;
- never silently rewrite boundaries after analysis has started;
- if a new detector is tested, save its proposal separately and require explicit acceptance before replacing the existing partition.

### 1.4 Frame sampling and shaving (supporting evidence, not the primary analysis)

Keep the existing frame-sampling/shaving controls for scene detection, selected thumbnails, OCR, and specialist evidence. Do not persist every sample or run the main caption model once per frame. The video processor receives the actual MP4 clip and performs its own bounded temporal sampling; sparse external samples are transient and cleaned unless specifically selected as a thumbnail/evidence artifact.

When a frame-based supporting tool is enabled, its first pass may remain adaptive:

```text
normal dialogue: 2–4 FPS
slow cinematic material: 1–2 FPS
fast action: 8–12 FPS around motion peaks
scene transitions: temporarily increase sampling
```

Decoded/sampled frames remain optional intermediate artifacts. The default durable media is the original video and timestamped audio-video clips under `video_repertoire/`, not a duplicate frame gallery. Preserve selected thumbnails only where needed by the UI and regenerate them from the source clip when safe.

### 1.5 Transcript acquisition

This is the first major correction.

Current failure mode:

- the analyser may use a weak or incorrect transcript source;
- garbled ASR output can be passed to the scene summariser as if it were authoritative;
- YouTube subtitles are not always downloaded even when available.

Required source priority:

1. YouTube manually supplied subtitles/transcript, when available and permitted;
2. YouTube auto-generated subtitles, when available and permitted;
3. embedded subtitle streams in the downloaded file;
4. local ASR such as Whisper/Qwen-ASR;
5. no transcript, explicitly marked as unavailable.

Every transcript must include:

- source type;
- language;
- confidence or source reliability;
- word/segment timestamps when available;
- download/provenance URL or file reference;
- whether it is human, YouTube-generated, embedded, or locally transcribed.

The report generator must never treat a low-confidence or garbled transcript as a reliable description of visible action.

### 1.6 Image Detailer

Current responsibilities:

- analyze selected still frames for optional evidence;
- produce object/subject/camera/lighting/palette/mood evidence;
- optionally use YOLO, Florence, OCR, depth, and related evidence.

Current problem:

- the output is verbose and sometimes schema-shaped rather than scene-useful;
- image evidence and model guesses can be mixed;
- the image detailer may produce facts that do not help temporal understanding;
- frame-level output can overwhelm the scene report.

Upgrade decision:

The Image Detailer remains an optional evidence extractor, not the primary video analyzer or storyteller. InternVideo3 receives the clip directly and is the intended primary video summarizer.

It should output compact, typed evidence:

```json
{
  "frame_id": "frame_0003",
  "timestamp_sec": 9.44,
  "subjects": [],
  "objects": [],
  "actions_visible": [],
  "camera": {},
  "lighting": {},
  "composition": {},
  "text_ocr": [],
  "continuity_facts": [],
  "uncertainties": [],
  "evidence_confidence": 0.0,
  "model_provenance": {}
}
```

It must not generate a long narrative for every frame. Narrative generation moves to the temporal scene-report layer.

### 1.7 Frame-to-frame deltas

Current responsibilities:

- compare selected keyframes;
- describe visible changes between consecutive frames.

Upgrade decision: retain deltas, but normalize them into event signals:

- subject entered/left;
- object appeared/disappeared;
- pose changed;
- camera moved;
- framing changed;
- lighting changed;
- text changed;
- audio event began/ended;
- confidence and evidence references.

Do not pass raw prose deltas directly into the report prompt.

### 1.8 Clip/video-level report generation

Current responsibilities:

- currently receive keyframe descriptions, deltas, and transcript;
- write a chronological scene explanation.

Current problem:

- output contains visible chain-of-thought or “thinking process” text;
- it repeats static descriptions instead of explaining the scene;
- it can mistake garbled transcript text for scene evidence;
- it does not consistently distinguish observation from inference;
- the report is not compact enough for retrieval or director use.

Upgrade decision: replace the legacy frame-prose report path with the bounded InternVideo3 clip → video synthesis → clip-context refinement flow in the authoritative contract above. Keep strict JSON validation, transcript/audio provenance, uncertainty, and no-chain-of-thought rules. Never use a frame-by-frame description list as a substitute for temporal clip understanding.

## 2. Target architecture

```text
Original video ──► existing cut/scene detector ──► timestamped A/V clips
       │                                              │
       │                                              └──► InternVideo3 direct-video
       │                                                   clip draft summaries
       ├──► sparse transient frame sampling (only if needed by supporting tools)
       │
       └──► one audio extraction ──► subtitles/ASR + speaker turns + music/SFX events
                                      (all timestamped, parallel to video analysis)

InternVideo3 clip drafts + timed audio/transcript records
       └──► chronological whole-video synthesis
                └──► one bounded clip-context refinement pass
                         └──► strict per-clip/video text records

PE-AV: clip video/audio/AV vectors + text vectors from refined summaries/transcript/events
       └──► linked semantic index; keyword index remains independently available
```

Video clips are the primary visual analysis units. Frames may be internally sampled by InternVideo3 or temporarily decoded by supporting tools; no persistent frame-by-frame LLM pipeline is in the target.

## 3. Model responsibilities

### 3.1 PE-AV Base

Use PE-AV Base as the retrieval and representation engine only; it does not replace the direct-video narrative model.

It should produce separate, linked vectors for:

- video/clip embedding;
- audio embedding where supported;
- text embedding;
- joint video-text similarity;
- optional audio-video similarity.

It is not responsible for writing the final natural-language summary.

Recommended first deployment:

- use the variable-length Base checkpoint `facebook/pe-av-base`;
- validate throughput, actual embedding dimension, and GPU memory on the target machine;
- use fixed short temporal windows only as a benchmark comparison, not as the default representation;
- preserve the current scene boundaries;
- generate one PE-AV vector per clip and one aggregate vector per scene.

CLAP is a separate fallback/secondary audio-to-text reranker. Store PE-AV and CLAP vectors in separate versioned LanceDB fields/spaces; do not concatenate them. When both are available, normalize their scores and apply weighted late fusion after PE-AV candidate retrieval.

### 3.2 InternVideo3-8B-Instruct — primary video summarizer

Use the official-documented `yanziang/InternVideo3-8B-Instruct` checkpoint, staged at the exact path in the authoritative contract. It is the intended replacement for legacy frame/Image Detailer prose: pass timestamped clip/video paths directly to the model, not one image at a time. Use its video processor's FPS/pixel controls to bound compute. The initial documented example uses 4 FPS; tune against quality and latency rather than equating model sampling FPS with source FPS or persisting those frames.

Default logic is clip-first chronological synthesis followed by one text-context clip refinement pass, as specified above. The short-video full-source-first strategy may be enabled only after a duration/context benchmark. InternVideo3 output is the visual/action narrative source; timed ASR, audio-event, speaker, music/SFX/ambience metadata is fused as explicit parallel evidence. Do not assume the model's video input path consumes or understands the soundtrack unless the selected inference interface has been separately verified. Model absence/failure is explicit and cannot silently claim the old frame pipeline is the new result. A reversible legacy fallback may remain selectable during acceptance.

`InternVideo3` is designated primary but remains gated on isolated runtime preflight and benchmark. Verify current model code, Transformers/PyTorch/CUDA compatibility, memory, supported video decoding and licensing before activating it. Do not install it into the shared website or ComfyUI environment.

### 3.3 Image Detailer

Keep the Image Detailer for compact frame evidence and specialist signals:

- OCR;
- objects and subjects;
- masks/regions;
- camera/framing hints;
- lighting/color measurements;
- depth or geometry cues where enabled;
- continuity facts.

Do not use it as the sole source of scene meaning.

### 3.4 Supporting language-model roles

InternVideo3 is the primary generator for direct-video clip descriptions and the video-level narrative. Ollama Qwen may perform routine text-only normalization or structured fusion where the model-role policy allows, but must not masquerade as direct video understanding. Codex is the director/system steward and is reserved for bounded quality/coherence decisions or requested prompt/product improvements, not called for every clip. Hermes is an explicitly configured Codex fallback only. Every provider/model and prompt version is recorded; provider failure never silently changes the claimed source of video evidence.

## 4. Temporal fusion design

### 4.1 Clip/event evidence fields

Each clip record should contain linked fields (not a requirement to implement a custom all-to-all neural attention model): direct-video InternVideo3 output; optional motion/camera/OCR/frame evidence; transcript segments with source/language/timestamps; speaker IDs; sound/music/ambience events with timestamps/confidence; absolute clip timestamps; scene/clip/video IDs; provenance and uncertainty.

### 4.2 Temporal fusion

Do not plan a new bespoke cross-attention model as a prerequisite. The application performs explicit timestamp joins and supplies compact, provenance-tagged evidence to the video summarization/refinement prompts. The multimodal model's internal attention is not exposed or treated as the database join mechanism. Use bounded hierarchy: clip → scene/video timeline.

### 4.3 Event compression

Many adjacent clips will be near duplicates. Compress them before expensive captioning:

1. keep existing scene/cut clip intervals authoritative;
2. optionally group adjacent clips into higher-level events using PE-AV/audio/text change signals, without changing source clip boundaries;
3. retain original timestamps and parent scene IDs;
4. send each required source clip directly to InternVideo3 once for the first-pass draft;
5. summarize/refine from compact chronological records without re-decoding clips.

The output should be approximately:

```text
1000 sampled windows → 50–100 semantic events → scene report
```

The exact ratio is data-dependent and must be recorded in the manifest.

## 5. Output contracts

### 5.1 Optional transient frame evidence

```json
{
  "frame_id": "frame_0003",
  "timestamp_sec": 9.44,
  "selected_reason": ["scene representative", "camera stable"],
  "subjects": [],
  "objects": [],
  "actions_visible": [],
  "camera": {},
  "lighting": {},
  "composition": {},
  "ocr": [],
  "depth": null,
  "continuity_facts": [],
  "uncertainties": [],
  "confidence": {}
}
```

### 5.2 Clip and linked event record

```json
{
  "event_id": "scene_001_event_003",
  "video_id": "video_abc",
  "scene_id": "scene_001",
  "clip_id": "scene_001_cut_003",
  "start_time_sec": 7.12,
  "end_time_sec": 10.80,
  "source_clip_ref": "video_repertoire/clips/scene_001_cut_003/video.mp4",
  "visual_summary": "...",
  "contextual_summary": "...",
  "action_beats": [],
  "subjects": [],
  "audio_events": [{"event_id": "audio-event-00021", "kind": "music", "label": "...", "start_time_sec": 7.8, "end_time_sec": 10.2, "confidence": 0.0}],
  "transcript_segments": [{"text": "...", "language": "...", "source": "...", "start_time_sec": 7.4, "end_time_sec": 9.1, "confidence": 0.0}],
  "speaker_ids": [],
  "whole_video_context_ref": "video-summary-v1",
  "camera": {},
  "lighting": {},
  "tone": "",
  "emotion": "",
  "evidence_confidence": 0.0,
  "embedding_refs": {}
}
```

### 5.3 Scene/video synthesis report

```json
{
  "scene_id": "scene_001",
  "start_time_sec": 4.8,
  "end_time_sec": 14.08,
  "scene_summary": "A courtroom exchange develops as the standing lawyer addresses the seated lawyer and the attention of the room shifts toward her.",
  "chronology": [],
  "characters": [],
  "actions": [],
  "camera_progression": [],
  "lighting_progression": [],
  "audio_progression": [],
  "dialogue": [],
  "continuity_facts": [],
  "uncertainties": [],
  "unsupported_claims_removed": [],
  "evidence_refs": [],
  "report_confidence": 0.0
}
```

The scene summary must explain what changes over time. It must not merely say that a man is seated, a woman is standing, or that police officers are present in every frame.

### 5.4 Full-video report

The full-video report is InternVideo3's chronology-aware synthesis of ordered clip drafts plus transcript/speaker/audio-event records, not merely an aggregation of static scene descriptions:

- one-sentence overview;
- scene-by-scene chronology;
- major characters/entities;
- recurring actions and themes;
- audio/music/transcript overview;
- camera/lighting/style overview;
- continuity notes;
- source and confidence information.

## 6. Transcript correction plan

Before any report generation:

1. Query the source platform for subtitle tracks.
2. Prefer manually created subtitles over auto-generated ones.
3. Download the selected language track.
4. Preserve the original subtitle file.
5. Convert it to timed internal segments.
6. Align segments to scene boundaries.
7. Use local ASR only for missing intervals or when no subtitle track exists.
8. Mark garbled or low-confidence intervals.

The report prompt must receive transcript provenance such as:

```json
{
  "text": "...",
  "source": "youtube_auto_caption",
  "language": "hi",
  "confidence": 0.61,
  "reliability": "medium"
}
```

If the transcript conflicts with visual evidence, the report must state the conflict instead of inventing a reconciliation.

## 7. Image Detailer replacement map

| Current function | Keep, replace, or modify | New behavior |
|---|---|---|
| Upload/analyze still image | Keep | Remains independently usable in Story Builder |
| YOLO/object detection | Keep optional | Evidence only; missing weights become explicit status |
| Florence captioning | Optional replacement | Run only if compatible and useful; never block analysis |
| OCR | Keep with docTR | Return text plus confidence and frame timestamp |
| Color/palette | Keep | Compact measurable signal |
| Camera/lighting prose | Modify | Return structured fields and confidence |
| Long per-frame narrative | Remove | Replaced with compact evidence JSON |
| Frame-level final summary | Remove | Scene/event layer writes the narrative |
| Raw model text | Retain privately | Store as provenance/debug artifact, not director metadata |

The Image Detailer page should continue to work independently. Video Summariser should call its compact evidence mode rather than the full user-facing narrative mode.

## 8. Video Summariser replacement map

| Existing part | Target implementation |
|---|---|
| Source import/upload/download | Preserve |
| FFprobe metadata | Preserve and add source FPS |
| Scene detector | Preserve as authoritative |
| Frame selector | Preserve; add adaptive second pass |
| Frame shaving | Preserve as an optional deduplication pass |
| Transcript fusion | Replace source priority and provenance handling |
| Image Detailer prose | Remove from primary video-summary path; retain optional compact evidence mode |
| Frame deltas | Optional supporting signals; never substitute for direct clip understanding |
| LLM scene stitching | Replace with InternVideo3 direct-video clip pass, chronological video synthesis, and one bounded context-refinement pass |
| Whole-video summary | InternVideo3 synthesis from timestamped clip/audio/transcript records; optional direct source-video pass only within benchmarked limits |
| Audio extraction | Preserve the source bitstream when possible; create `analysis.wav` for models and `preview.mp3` for UI/export plus a manifest |
| Demucs | Reuse isolated 2/4/6-stem utility; application policy defaults to `AUTO` |
| Audio classification | Add timestamped speech/music/SFX/ambience event layer |
| Voice examples | Add diarized speaker segments, embeddings, metadata, and search |
| Search | PE-AV Base video/audio/AV and summary/transcript/event-text vectors plus keyword search; all records linked by clip/video/time |
| Existing lexical search | Preserve as fallback and explicit keyword mode |
| LanceDB index | Use for fused clip/event vectors |
| Results UI | Add Entire Video, Scenes, Clips, optional selected-frame evidence, and linked Audio/Transcript views; a frame gallery is not required |

## 9. Semantic and keyword search

Both search modes must remain available as independent toggles.

### Semantic search

Uses:

- PE-AV Base text embedding for the query;
- fused clip/event embeddings;
- optional audio-video embedding;
- scene and clip metadata filters;
- diversity by source video and scene.

Example:

```text
Find a tense courtroom confrontation where one person rises and addresses the room.
```

This should match clips even when the exact words “tense courtroom confrontation” are absent from the transcript.

### Keyword search

Uses exact/normalized terms from:

- transcript;
- OCR;
- scene summary;
- action labels;
- subjects;
- camera and lighting labels;
- audio-event labels.

Example:

```text
courtroom lawyer papers
```

### Hybrid search

When both toggles are on:

```text
hybrid_score = semantic_score + keyword_score + metadata/style adjustments
```

The weighting must be recorded with each search result so retrieval is explainable.

### Result controls

Support:

- top N;
- next page without repetition;
- scene/sub-scene/clip grouping;
- recent/oldest ordering for saved analyses;
- relevance ordering for search;
- source-video diversity;
- optional SEO/style weighting;
- save selected clips as project references.

## 10. Entire-video and multi-clip references

Users may select:

- a complete source video;
- one scene;
- one clip;
- multiple clips from one video;
- clips from multiple videos.

For multiple clips, the system stores an ordered reference set:

```json
{
  "reference_set_id": "refs-...",
  "items": [
    {"clip_id": "...", "order": 1},
    {"clip_id": "...", "order": 2}
  ],
  "joined_preview": null,
  "purpose": "motion reference"
}
```

Joining clips is a separate explicit operation. The original clips remain unchanged. A joined preview may be generated with FFmpeg and stored as a derived artifact.

Reference sets can be attached to a Story Builder project and later supplied to Hermes/director automation.

## 11. Results UI changes

The Results area should contain:

1. **Entire video** — player, global summary, transcript overview, metadata.
2. **Scenes** — scene cards ordered by time, each expandable.
3. **Clips** — clip cards with thumbnail, player, timestamp, summary, and selection.
4. **Evidence** — optional selected thumbnails and compact Image Detailer evidence; do not expose every sampled frame by default.
5. **Search** — semantic and keyword toggles, query, top N, sorting, next results.
6. **References** — selected clips/videos and project-save controls.

### 11.1 Audio intelligence controls in the Analyze tab

Add a collapsible **Audio intelligence** panel beside the existing frame-analysis controls; it must not replace or silently change the scene detector, frame selector, extraction FPS, frame shaving, or delete-frames settings. New analyses open with the locked defaults from this plan:

- original audio, analysis WAV, and preview MP3 on;
- speech, music, SFX/ambience events, audio embeddings, audiovisual embeddings, transcription, diarization, ECAPA same-speaker search, active-speaker association, music analysis, and voice-feature analysis on;
- event detector `Auto: HTS-AT → PANNs`;
- semantic model `Auto: PE-AV → CLAP` (PE-AV primary, CLAP separate reranker/fallback);
- diarization `NeMo`;
- character tracking `Auto`;
- Demucs `AUTO`;
- SAM Audio `On demand` only.

Each control has a short explanation, a preflight badge (`ready`, `fallback`, `gated`, `unavailable`), and an explicit resolved backend after the job starts. Audio progress is shown as independent stages—extract, subtitles/ASR, event detection, diarization, embeddings, optional stems, and report/index—so a missing optional stage is visible without making the entire job appear failed.

### 11.2 Audio result views

Add result tabs/panels for **Entire audio**, **Stems**, **Audio events**, **Voices**, and **Audiovisual events**. Every row has a timestamp, confidence, source scene/clip/frame links, provenance, and a playable preview. A timeline scrubber keeps video, transcript, event labels, speaker tracks, and selected frames synchronized. Voice rows show immutable IDs plus mutable anonymous aliases, not invented names.

For an audio event, provide `Preview isolation`, `Save to repertoire`, and `Cancel/Expire` actions. `Save to repertoire` is only enabled after the temporary output and provenance check succeed; Codex-triggered saves (or explicitly configured Hermes fallback decisions) appear in the audit panel. Gated SAM Audio, PE-AV, HTS-AT, NeMo, or optional pyannote states are explained inline and never hide the existing video/scene/frame results.

### 11.3 Search and persistence behavior

The Search panel can search visual, audio, voice, or audiovisual records using semantic and keyword toggles. Results are grouped by source video and scene, with clip/event thumbnails side by side. Audio-only matches can open the corresponding video interval; visual matches can reveal their linked audio events. Search sessions are transient UI state; approved reference assets and manifests are persisted under the existing project storage.

The UI must show:

- analysis progress;
- current stage;
- model availability;
- transcript source;
- evidence confidence;
- unavailable optional models;
- retry and cancel controls;
- per-job Stop and Delete controls with backend-confirmed cancellation/cleanup progress, confirmation, and safe restart/resume messaging;
- no chain-of-thought text.

## 12. Storage and migration

The existing source and analysis artifacts must remain readable.

Add versioned manifests and make `video_repertoire/` the only durable media and shared-index location:

```text
video_repertoire/
├── videos/<video-id>/
├── scenes/<scene-id>/
├── clips/<clip-id>/
├── audio/<audio-event-id>/
├── music/<music-event-id>/
├── sfx/<sfx-event-id>/
├── voices/<voice-example-id>/
├── events/<event-id>/
├── indexes/
└── manifests/

video_audio_analyzer/runs/<run-id>/  # transient/resumable workspace only
├── clips/                           # staged until validated repertoire commit
├── frames/                          # transient decode/thumbnail cache only
├── audio/                           # staged analysis files
├── index/                           # rebuildable run-local cache
└── run_manifest.json
```

Run-local media is staging data, not a second durable library. After a successful validated commit to `video_repertoire/`, remove redundant run copies under the retention policy and keep only compact manifests/logs needed for audit/resume. Do not persist every decoded frame. UI lists and shared semantic search read from the canonical repertoire.

Every upgraded analysis records:

- pipeline version;
- source hash;
- source FPS;
- sampling FPS;
- scene detector version;
- frame selector version;
- transcript source and language;
- Image Detailer model versions;
- PE-AV Base checkpoint and actual embedding dimension;
- InternVideo3 repository/checkpoint revision, processor/config, model-code hash, direct-video sampling FPS/pixel limits, selected summary mode, pass/prompt/schema versions, timings and peak memory;
- clip draft/refined summaries, whole-video summary, exact transcript/audio-event IDs used as context, evidence links and uncertainty;
- report schema version;
- audio extraction and Demucs mode;
- audio-event detector version;
- speaker diarization and voice-embedding model versions;
- timestamps and output paths.

Old analysis outputs must remain viewable. Reprocessing creates a new analysis version rather than overwriting the old result.

## 13. Implementation phases

### Phase 0 — Registry, preflight, and runtime isolation

- add the versioned canonical model/repository registry;
- implement read-only checks for architecture, Python, Torch/CUDA, GPU, FFmpeg, checkpoints, dimensions, licenses, gates, and smoke tests;
- expose resolved backends and fallback reasons to the existing website;
- inspect the current Docker/utility-runner layout before selecting isolated images, environments, or subprocess workers;
- keep ComfyUI and its existing Docker/runtime completely outside this change.

### Phase 1 — Evidence and transcript correctness

- implement subtitle-track acquisition and provenance;
- preserve existing scene and frame outputs;
- add source FPS/sampling FPS metadata;
- normalize frame evidence and deltas;
- integrate default original-audio extraction and MP3 export;
- preserve source audio bitstreams when possible and create model-friendly analysis WAV plus preview MP3;
- persist audio manifests linked to source video, scenes, clips, and timestamps;
- add independent audio toggles to the analysis request;
- remove chain-of-thought from displayed reports;
- add regression fixtures from the courtroom example.

### Phase 2 — Compact Image Detailer mode

- add a video-specific compact evidence schema;
- keep the existing standalone Image Detailer page;
- add confidence and uncertainty fields;
- retain OCR/docTR and optional detectors;
- ensure missing optional models do not fail the job.

### Phase 3 — PE-AV retrieval index

- add model preflight and `facebook/pe-av-base` checkpoint configuration;
- generate clip/event embeddings;
- store vectors and metadata in LanceDB when available;
- retain JSONL fallback;
- implement semantic, keyword, and hybrid scoring;
- keep CLAP in a separate vector field and use it only as fallback/late audio-text reranker;
- add non-repeating next-page retrieval.

### Phase 3A — Audio events and voice repertoire

- reuse the existing isolated Demucs utility without changing Docker or ComfyUI;
- expose `AUTO / off / 2-stem / 4-stem / 6-stem`, with AUTO as the default;
- run event detection on the original mix before deciding whether separation is useful;
- add PANNs/HTS-AT event labels and confidence scores;
- detect and timestamp speech, music, SFX, ambience, silence/noise, and uncertain/mixed events;
- create audio and audiovisual embeddings independently of frame-analysis toggles;
- add Essentia/librosa music measurements and section boundaries;
- add Codex-requested, lazy SAM Audio isolation for selected/high-confidence events (Hermes explicit fallback only), with temporary-output expiry and explicit `save_to_repertoire` persistence;
- add WhisperX-compatible speech alignment;
- add NeMo local diarization as the default backend and pyannote as an optional backend;
- add ECAPA speaker centroids for same-speaker retrieval;
- add face/body/ReID tracking, TalkNet-compatible active-speaker association, and MMPose signals;
- add UUID-backed character and voice identities with current-project-first then global Voice Store ANN matching;
- add Codex confirmation/audit decisions (Hermes explicit fallback only) without changing internal UUIDs;
- diarize speech into stable anonymous speaker IDs;
- extract quality-filtered voice examples;
- store speaker, pitch, rate, energy, prosody, transcript, emotion/style, and provenance metadata;
- create speaker-identity and voice-style indexes;
- link voice examples to scenes, clips, transcripts, and corresponding frames;
- do not invent real character names; generate anonymous aliases automatically and let Hermes rename only with evidence.

### Phase 4 — Temporal event compression

- optionally group adjacent near-duplicate clips as higher-level semantic events for retrieval;
- do not create video descriptions by comparing all extracted frames;
- preserve existing scene/cut intervals and IDs as the source partition;
- call InternVideo3 directly on each source clip for the first-pass summary; any event grouping must retain links to original clips/times;
- add event-level reports and confidence.

### Phase 5 — Direct-video InternVideo3 summarization replacement

- stage the complete canonical InternVideo3-8B-Instruct snapshot at the path in the authoritative contract;
- inspect/pin its model code and license; preflight the isolated worker's architecture, runtime, video decoder, GPU memory, and dependency compatibility;
- benchmark direct MP4-path inference on the supplied short dummy and at least one longer representative video; measure speed and quality and compare against legacy without overwriting either result;
- implement clip-first analysis → chronological whole-video synthesis → one context-refinement pass, with a benchmarked short-video full-source-first option;
- fuse transcript, speaker, music/SFX/ambience, and audio timestamps into each clip text record without claiming native audio understanding unless specifically tested;
- persist strict structured records, provenance, confidence, and uncertainty; strip reasoning traces;
- keep PE-AV indexing as a separate retrieval function, not as the summary generator;
- make direct-video inference active only after benchmark and regression gates; otherwise report `not_ready` explicitly and keep the reversible legacy route.

### Phase 6 — UI and project references

- add Entire Video, Scenes, Clips, Frames, and Evidence views;
- add semantic and keyword toggles;
- add sort/group controls;
- support full-video and multi-clip reference sets;
- add ordered joined-preview generation;
- expose selected references to Media Composer and automation.
- add per-job Stop and Delete actions, backend cancellation/ownership validation, confirmation/cleanup progress, and idempotent cleanup retries;
- expose Resume only if the validator confirms a safe checkpoint survives without duplicate run storage; otherwise offer Restart from the registered source.

### Phase 6A — Audio and voice UI

- add independent audio-analysis controls to the Video Summariser Analyze tab;
- add audio progress stages and per-stage availability/error states;
- add Entire Audio, Stems, Audio Events, and Voice Examples result views;
- add audio players with timestamp-linked video/frame navigation;
- add semantic voice search and same-speaker search;
- show Codex-confirmed mappings (or explicitly configured Hermes fallback) and immutable audit evidence; keep UI rename/override as a non-blocking convenience only;
- expose approved voice examples as references without automatically creating a cloned voice model.

### Phase 7 — Quality/performance hardening after primary-model acceptance

- tune direct-video temporal FPS, pixel bounds, clip batching, model residency, and cache behavior against measured quality/latency;
- evaluate an alternative only if InternVideo3 preflight/benchmark fails agreed acceptance targets; do not silently demote InternVideo3 to an optional frame captioner;
- preserve a reversible fallback and record the actual backend on every run.

## 14. Testing requirements

### Unit tests

- transcript source priority;
- subtitle parsing and timestamps;
- garbled transcript marking;
- frame evidence schema;
- delta normalization;
- event merging;
- vector dimensions/versioning;
- keyword/semantic/hybrid scoring;
- next-page exclusion;
- reference-set ordering;
- manifest migration.
- same-project Voice Store ANN retrieval searches bounded top-K candidates rather than O(N²) raw-sample comparisons;
- cross-project fallback uses LanceDB metadata partitions and preserves source-project provenance;
- one ECAPA similarity threshold alone never merges identities;
- Hermes confirmation decisions and supporting evidence are audit-logged;
- anonymous alias creation is collision-safe and display-name changes never alter UUIDs;
- real-name suggestions require evidence provenance;
- PE-AV and CLAP remain separate vector spaces and CLAP late reranking does not concatenate vectors;
- SAM Audio temporary outputs expire/delete unless Hermes issues `save_to_repertoire`;
- gated-model states expose unavailable/access/authentication/checkpoint details;
- code license and checkpoint/model license are recorded separately;
- ByteTrack geometry tracking is tested separately from BoxMOT/StrongSORT/BoT-SORT appearance ReID.

### Integration tests

- analyze the courtroom fixture;
- verify scene boundaries are unchanged;
- verify existing scene/cut boundaries and source timestamps are unchanged;
- verify InternVideo3 receives clip/video paths directly and no per-frame VLM loop is used;
- verify transient decode/sample frames are cleaned and only requested thumbnails/evidence remain;
- verify clip-first → full-video synthesis → exactly one context-refinement pass preserves chronology and local evidence;
- verify a summary for every clip includes overlapping transcript and timestamped audio events with source/confidence metadata;
- verify the video-level summary and each refined clip summary are PE-AV text-indexed alongside the direct clip video embedding, linked to the same stable IDs;
- compare direct-video and legacy summaries, reporting runtime, peak memory, factuality, chronology, and audio/transcript coverage rather than asserting speed in advance;
- verify YouTube transcript is preferred over fallback ASR;
- verify source bitstream preservation where possible, `analysis.wav`, `preview.mp3`, and the audio manifest;
- verify Demucs AUTO/off/2/4/6-stem modes and AUTO behavior;
- verify event detection runs on the original mix before separation;
- verify speech/music/SFX/ambience event timestamps and confidence;
- verify PANNs/HTS-AT labels are not confused with Demucs stem names;
- verify Essentia music features and section timestamps;
- verify selected-event SAM Audio isolation is optional and provenance-tracked;
- verify WhisperX speech alignment;
- verify NeMo diarization default and pyannote optional fallback behavior;
- verify active-speaker association does not equate frame presence with speech;
- verify face/body/voice evidence fusion and overlap handling;
- verify ECAPA same-speaker matching within a source video;
- verify cross-project Voice Store matching order and bounded top-K ANN behavior;
- verify no full-library O(N²) comparison is performed;
- verify Codex is the confirmation authority and every merge/rejection has provenance (Hermes only as an explicitly configured fallback);
- verify measured voice properties remain separate from inferred affect/style;
- verify UUID-backed identity matching never keys on display names;
- verify anonymous aliases are created without a human gate and real names require supporting evidence;
- verify anonymous speaker IDs remain stable within a video;
- verify voice examples link back to audio, scene, clip, and frame timestamps;
- verify character-name suggestions require explicit supporting evidence or confirmation;
- verify report describes progression rather than repeating static objects;
- verify no chain-of-thought is exposed;
- verify results survive restart;
- verify old reports remain viewable.
- verify source-video and reusable media commit once to `video_repertoire/`, with no duplicate durable copy left in analyzer runs;
- verify stopping a queued/running job stops its worker, removes job-owned partial files/index rows, and preserves the registered source;
- verify deleting an inactive or active job removes its record and only its exclusively owned derived assets; referenced/shared assets and source video are protected;
- verify resume uses only validated checkpoints and never relies on orphaned hidden run folders; restart works from the source when resume is unavailable;
- verify stop/delete are backend-authorized, path-safe, idempotent across retries/restarts, and report partial cleanup failures honestly;

### Playwright tests

- library selection;
- Analyze selected navigation;
- settings toggles;
- progress and refresh recovery;
- active-job Stop, stopping/cleanup progress, and removal from the running list;
- Delete confirmation, owned-output cleanup, shared/source protection, and history refresh;
- validated Resume or source-based Restart state after Stop;
- Entire Video/Scenes/Clips/Frames views;
- semantic and keyword toggles;
- search and next results;
- full-video selection;
- multi-clip selection and ordering;
- save references to a project;
- delete confirmation;
- unavailable optional-model states.
- audio-analysis toggles are independent from frame-analysis toggles;
- audio/stem/event/voice result panels and timestamp-linked playback;
- semantic voice search and speaker confirmation;
- event-detector, semantic-model, diarization-backend, character-tracking, and Demucs controls show locked defaults;
- SAM Audio preview/save/cancel behavior;
- Hermes decision/audit status is visible without exposing chain-of-thought;
- refresh/navigation recovery keeps an active analysis job and its audio stages visible.

## 15. Non-regression rules

- Do not remove the current scene detector.
- Do not remove the current scene detector, clip boundaries, timestamps, or frame-shaving controls; frame processing is optional supporting evidence and must not remain the primary narrative path.
- Do not overwrite existing analysis artifacts.
- Do not make PE-AV, InternVideo, Florence, YOLO, or LanceDB mandatory before preflight succeeds.
- Do not make NeMo, pyannote, HTS-AT, PANNs, SAM Audio, or PE-AV mandatory before their own preflight succeeds; Auto must fall back and record the resolved backend.
- Do not modify Docker or ComfyUI packages for this feature without explicit approval.
- Do not modify ComfyUI images, nodes, wheels, model paths, or the existing Docker environment for this feature.
- Do not install incompatible packages into the frontend/backend environment; worker dependency boundaries must be explicit and preflighted.
- Do not change unrelated Story Builder, Audio Reconstruct, Control-Foley, ACE-Step, or production-runner behavior.
- Do not expose model chain-of-thought in the UI or stored director metadata.
- Do not allow uncertain transcript text to override visual/audio evidence silently.
- Do not delete the original curated source video when deleting derived analysis unless the user explicitly chooses source deletion.

## 16. Definition of done

The upgrade is complete when:

1. Existing scene/cut boundaries, clip timestamps, and frame-shaving controls remain intact; per-frame VLM analysis is no longer the primary report path, and all-frame persistence is not required.
2. YouTube/embedded subtitles are used before fallback ASR.
3. Frame evidence is compact, typed, confidence-aware, and provenance-aware.
4. InternVideo3 directly processes timestamped MP4 clips and produces chronology-grounded per-clip and whole-video summaries with transcript/audio-event context, followed by one bounded clip-refinement pass.
5. PE-AV Base separately embeds each clip's video and its refined text summary/transcript/audio-event semantics for semantic retrieval.
6. Keyword search remains available independently.
7. Hybrid search works when both toggles are enabled.
8. Results support entire-video, scene, clip, optional selected thumbnail/evidence, and multi-clip reference use.
9. Search results can be paged without repetition.
10. Original audio is extracted and persisted by default.
11. Original-mix event detection runs before optional Demucs separation.
12. Demucs supports AUTO/off/2/4/6-stem modes without Docker or ComfyUI changes.
13. Speech, music, SFX, and ambience events are timestamped and confidence-aware.
14. Codex can request selected-event SAM Audio isolation, with temporary-output cleanup and explicit save-to-repertoire provenance; Hermes is fallback-only when explicitly configured.
15. Voice examples are extracted, diarized, semantically tagged, and linked to scenes/clips.
16. Real character names are never invented from anonymous speaker embeddings; anonymous collision-safe aliases are automatic and non-blocking.
17. One shared event ID joins visual, audio, voice, and audiovisual references.
18. Existing Story Builder pages and workflows continue to pass their existing tests.
19. Playwright confirms the complete Video Summariser workflow.
20. UI defaults are explicit: HTS-AT→PANNs, PE-AV→CLAP, NeMo diarization, ECAPA same-speaker matching, Auto character tracking, Auto Demucs, and on-demand SAM Audio.
21. Current-project-first and cross-project Voice Store matching use bounded ANN top-K retrieval and Codex audit decisions (Hermes fallback only) without O(N²) comparison.
22. PE-AV and CLAP vectors remain separately versioned and are combined only through documented late fusion.
23. Registry/preflight reports checkpoint gates, licenses, dimensions, architecture, GPU, smoke tests, and fallbacks.
24. Dockerized workers, if selected after inspection, remain isolated from ComfyUI and the existing website/runtime.
25. InternVideo3's staged checkpoint, exact commit, processor code, isolated runtime, video-path smoke test, speed/memory benchmark, and quality comparison are verified before activating it as the default summary backend.
26. Every clip text record contains the InternVideo3 summary, relevant timed transcript, speaker tags where available, and overlapping music/SFX/ambience records; the whole-video summary is separately indexed as text.
27. Durable source, clip, audio, voice, event, and index assets exist only in `video_repertoire/`; analyzer run directories are transient staging/cache and are cleaned after successful commit.

## 17. Pre-implementation readiness report

This plan is ready for repository inspection and preflight implementation, but not yet an authorization to install or download anything.

### Components expected to run independently

FFmpeg, source registration, subtitle acquisition, existing scene detection, frame selection, clip extraction, analysis WAV/preview MP3 creation, JSONL manifests, LanceDB when present, and the existing Video Repertoire/Story Builder routes must remain usable without any optional model. PE-AV, CLAP, HTS-AT, PANNs, WhisperX, NeMo, ECAPA, Essentia/librosa, Demucs, and the tracking adapters each have their own smoke test and fallback state.

### Gated or manual-access components

SAM Audio (`facebook/sam-audio-base-tv`) and optional pyannote (`pyannote/speaker-diarization-community-1`) may require Hugging Face access acceptance/token and local checkpoint download. Selected InsightFace recognition weights require a separate code-license/checkpoint-license review. The registry must show these as `gated` or `unavailable` rather than silently substituting another model. No manual access is needed for the default NeMo diarization path if its local checkpoint is prepared successfully.

### Likely isolation requirements

TalkNet's older dependency stack, SAM Audio, Demucs, and any model requiring a conflicting Torch/CUDA/native-extension combination are candidates for isolated workers. The actual Docker image/environment split is decided only after inspection of the existing runtime; no Docker or ComfyUI change is made during plan normalization.

### Remaining decisions

No product decision is blocking this plan. The only implementation-time choice is whether the inspected repository is best served by separate Docker images, isolated virtual environments, or subprocess workers. That choice must be justified by preflight results and must preserve the same website and API contracts.

## 18. Isolated analyzer implementation and replacement plan

### 18.0 Persistent implementation safety rules

These rules apply to every implementation phase and every future request to “remember the rule”:

- Treat the existing website/app, legacy `video_summariser`, ComfyUI Docker/runtime, other Docker projects, and existing Conda environments as read-only until the final, explicitly tested website-integration phase.
- Work inside `video_audio_analyzer/` or a dedicated isolated worker only. Do not install packages into another project, shared Conda environment, ComfyUI, or the Story Builder backend without explicit approval.
- Prefer the analyzer's Docker image or a project-local virtual environment. If Docker is unavailable, stop at a clear preflight result rather than silently using a shared environment.
- React or `blender311` Conda environments may receive an additive package only when a dry-run/lock comparison proves that existing installed packages will not be removed, downgraded, or replaced. If the solver proposes any destructive or uncertain change, use the isolated analyzer Docker/worker instead.
- Make every stage verbose: record command, component, selected backend, model/version, input/output paths, timing, warnings, fallback reason, and traceback in the run manifest/log.
- After every phase, run unit/integration tests and the supplied dummy video through the new analyzer; compare scenes, frames, timestamps, transcript, clips, audio, manifests, and summaries against the legacy analyzer without overwriting either output.
- Use Playwright whenever a website or analyzer UI is changed. Do not modify the website merely to test an unintegrated backend.
- Do not switch the website backend until the isolated analyzer, Docker/runtime preflight, dummy comparison, and Playwright acceptance gates all pass. Keep the legacy backend rollback switch available.

The upgraded implementation will be built as a new sibling project:

```text
/home/riki/web_dev/story_builder/video_audio_analyzer/
```

The existing project remains untouched and available as the reference implementation:

```text
/home/riki/web_dev/story_builder/video_summariser/
```

Do not rename, delete, or edit the existing Video Summariser during development. Copy only the required source contracts, fixtures, adapters, and compatible assets into `video_audio_analyzer`; keep the original output and test data readable for comparison.

### 18.1 New project compatibility contract

`video_audio_analyzer` must provide an adapter-compatible tree and API surface for the current website, including:

- source video registration/upload and playback;
- analysis job creation, status, retry, cancel, and restart recovery;
- scene, clip, frame, transcript, audio-event, voice-example, and manifest outputs;
- existing timestamps and identifiers;
- semantic search, keyword search, hybrid search, pagination, and reference-set selection;
- the existing Video Repertoire response shape where practical;
- new audio controls and result panels described in Section 11.

The website must not be switched to the new analyzer until its API contract, persistence layout, failure states, and Playwright flows pass the comparison gate.

### 18.2 Docker and dependency policy

Docker files belong inside `video_audio_analyzer/`. The new project may use separate worker images or isolated environments, but it must not modify the existing ComfyUI image, Docker volumes, node installation, model paths, or the existing Story Builder runtime.

Before installing dependencies:

1. inspect every package's declared Python, Torch, CUDA, system-library, and architecture requirements;
2. build a lock/preflight report showing direct and transitive conflicts;
3. test whether a newer compatible version satisfies the package that requested the older version;
4. prefer the higher compatible version when smoke tests and model outputs remain valid;
5. isolate genuinely incompatible packages behind worker/container boundaries;
6. record the final versions, rationale, wheel/source provenance, and known limitations.

There is no functionality compromise to resolve version conflicts. If a package cannot operate with the shared version, move that package to an isolated worker rather than weakening the analyzer's output contract. No dependency installation is allowed in the existing frontend/backend or ComfyUI environment as part of this project.

### 18.3 Dummy-video comparison gate

After the new analyzer is implemented, run both analyzers against:

```text
/home/riki/web_dev/story_builder/plan/Brother eww what’s that？💀 meme.mp4
```

Comparison must cover:

- duration, source FPS, scene boundaries, cuts, and selected representative frames;
- subtitle/transcript source and timestamp quality;
- clip/event intervals and chronology;
- overall and scene summaries, including unsupported-claim handling;
- extracted source audio, `analysis.wav`, `preview.mp3`, and optional stems;
- speech/music/SFX/ambience event records;
- diarization, ECAPA voice examples, anonymous aliases, and Hermes audit records;
- PE-AV/CLAP vector dimensions, model/version metadata, and semantic/keyword retrieval;
- output manifests, restart recovery, and failure/fallback states;
- storage paths and compatibility with existing Video Repertoire consumers.

The comparison report must distinguish intentional improvements from regressions. The old analyzer's output is never overwritten.

### 18.4 Website replacement gate

Only after the comparison and Playwright gates pass will the website's Video Summariser route be switched from the old service to `video_audio_analyzer`. The route, navigation label, existing library/results behavior, and old saved analyses must remain usable. The additional audio controls, audio/stem/event/voice panels, synchronized timeline, semantic voice search, and Hermes/SAM status must be added without breaking existing video-only workflows.

The integration must support a reversible configuration switch:

```text
VIDEO_ANALYZER_BACKEND=legacy | video_audio_analyzer
```

Legacy remains available during acceptance testing. Once the new backend is proven, the default changes to `video_audio_analyzer`; rollback must require configuration only, not code deletion or data migration.

### 18.5 Acceptance tests before replacement

- isolated analyzer unit, integration, dependency-preflight, and Docker smoke tests pass;
- supplied dummy video completes end-to-end, including audio stages when available;
- existing analyzer remains unchanged and still passes its tests;
- Playwright verifies upload/library/analyze/progress/results/search/audio panels/navigation/restart recovery;
- website build passes with both backend modes;
- no ComfyUI, unrelated Story Builder, Audio Reconstruct, Control-Foley, ACE-Step, or production-runner regression is observed;
- comparison report is stored under `plan/` before the backend switch.

## 19. Implementation ledger

### Phase 2 status — compact frame evidence

Implemented in the isolated `video_audio_analyzer/` project without changing the legacy analyzer or website. The new baseline now emits typed compact evidence per selected frame: dimensions, measurable brightness/contrast/saturation/edge density, dominant colors, lighting measurements, OCR/detector availability, confidence, uncertainty, and model provenance. It uses FFmpeg software-decoding fallback for the supplied AV1 fixture and records unavailable specialist stages rather than inventing semantic claims.

Validated with the supplied dummy video and the isolated test suite. The comparison report is `plan/video_audio_analyzer_dummy_comparison.md`. Phase 2 does not authorize website replacement; PE-AV, sound-event classification, diarization, Voice Store, Hermes, and LanceDB integration remain gated phases.

### Phase 3 status — retrieval index foundation

Implemented in the isolated project: versioned retrieval records for frame/audio events, separate PE-AV and CLAP vector fields, semantic/keyword/hybrid scoring, non-repeating pagination, and an explicit deterministic fallback when `facebook/pe-av-base` and production LanceDB ANN are not preflight-ready. The fallback is marked in every manifest and does not claim model-generated embeddings. Website integration remains deferred until the real PE-AV/CLAP adapters and LanceDB runtime pass preflight.

### Phase 3 isolated-runtime resolution (2026-09-25)

The isolated `video_audio_analyzer/Dockerfile.peav` derives from the existing
ComfyUI image without modifying it. The upstream PE-AV package is installed
with `--no-deps` because its optional `decord==0.6.0` dependency has no
compatible aarch64 wheel. Runtime dependencies are installed only in the new
image; xFormers diagnostics are optional and native PyTorch attention is used
for PE-AV. The canonical `facebook/pe-av-base` checkpoint is stored only under
`video_audio_analyzer/models/pe-av-base/`.

The adapter detects the official Transformers checkpoint format and uses
`PeAudioVideoModel`/`PeAudioVideoProcessor`. It passed text-only and real
audio-video embedding smoke tests on the GPU worker; the verified projection
dimension is 1024. The worker uses Transformers 5.17.0 and timm 1.0.30 because
the base image's older versions did not expose the PE-AV model or vision
architecture; these upgrades exist only in the derived image.

LanceDB 0.30.0 was tested in a disposable derived worker on aarch64: connect,
table creation, and a one-row ANN table write succeeded. The shared React
environment's LanceDB 0.39.0 still hangs during initialization, so the host
path has an 8-second child-process watchdog and retains JSONL fallback on
timeout. The isolated worker can enable LanceDB with
`VIDEO_AUDIO_ANALYZER_ENABLE_LANCEDB=1`; no unbounded native initialization is
permitted.

Validation completed: isolated PE-AV preflight reports GPU/checkpoint/import
ready; text embedding smoke reports `[1, 1024]`; real dummy-video audio-video
embedding reports audio, video, joint, and text projections; the pipeline now
loads PE-AV once per worker run, stores timestamp-linked scene vectors, and
encodes search text with PE-AV; isolated LanceDB table write reports
`media_events`; and the analyzer test suite remains green (12 tests). Website,
legacy analyzer, ComfyUI, and Conda environments were not changed. Website
replacement and Playwright acceptance remain a later gate under Section 18.4.

### Phase 3A status — original-mix sound-event detection (2026-09-25)

The isolated worker now includes the canonical PANNs fallback detector
(`qiuqiangkong/panns_inference`) with its documented Cnn14 decision-level
checkpoint. It runs on the original analysis WAV before any optional Demucs
separation, emits controlled labels/confidences with timestamps, and records
the detector/model provenance in each event. The supplied dummy video produced
Music and Speech events successfully. PANNs dependencies and its checkpoint
exist only in the derived analyzer worker; the shared environments remain
untouched. When the checkpoint or runtime is unavailable, the previous
metadata-only audio activity fallback remains explicit and non-blocking.

The remaining Phase 3A stages are Essentia/librosa music measurements, ASR
alignment, NeMo diarization/ECAPA Voice Store, and optional Demucs/SAM Audio;
they will be added independently rather than making PANNs or PE-AV failures
abort scene/frame analysis.

### Phase 3A status — measured music features (2026-09-25)

The isolated worker now runs a lazy `librosa` measurement pass on the original
analysis WAV when music analysis is enabled. It writes timestamped ten-second
segments containing RMS mean/peak, spectral-centroid mean, onset strength,
beat timestamps/counts, sample rate, duration, and a global tempo estimate.
These are measurements only: the worker does not invent mood, genre, or
instrument labels from them. The stage is independently marked `completed`,
`disabled`, or `unavailable`, and a missing librosa runtime cannot block scene,
frame, PANNs, or PE-AV processing. Essentia remains a later optional music
specialist after its ARM/GPU preflight; it is not silently substituted.

The supplied dummy video completed this stage in the isolated worker with
`music_analysis: completed`, one timestamped segment, and 19 detected beats.
The analyzer suite remains green (12 tests). The AV1 hardware-decoder warning
is expected on this host; FFmpeg software decoding completed the run.

### Phase 3A status — ASR adapter and alignment contract (2026-09-25)

The isolated worker now includes a `faster-whisper==1.2.0` adapter targeting
the canonical `Systran/faster-whisper-large-v3` checkpoint. It supports
timestamped segments and word timestamps, records device/compute settings,
and never downloads a model during an analysis job. The checkpoint path is
preflighted and must be mounted explicitly. The supplied dummy video has no
prepared large-v3 cache, so its manifest correctly reports
`transcription: unavailable` rather than fabricating text; all other stages
complete normally. This is the intended safe fallback until the checkpoint is
prepared in the isolated model cache.

### Phase 3A status — Demucs policy adapter (2026-09-25)

The isolated worker now has an explicit Demucs adapter for `AUTO`, `off`,
`2`, `4`, and `6` modes. It runs only after original-mix event analysis;
AUTO requests stems only when a confident music event warrants them. The
adapter records the selected model, outputs, and failure reason. The current
derived image intentionally does not include Demucs yet, so the dummy run
reports `demucs: unavailable` without failing any other stage. This preserves
the no-conflict runtime boundary; Demucs will be added only as a separately
preflighted separation worker.

### Phase 3A status — transcript source precedence (2026-09-25)

Embedded subtitle streams are now checked and extracted to WebVTT before local
ASR. Parsed cues retain timestamps and source provenance. If no embedded cues
exist, the prepared local faster-whisper adapter is used; if its large-v3
checkpoint is absent, transcription remains explicitly unavailable. The dummy
video had neither an embedded subtitle stream nor a mounted ASR checkpoint,
and completed all non-transcript stages normally.

### Phase 3B status — frame shaving cleanup and repertoire promotion (2026-09-25)

The isolated analyzer now exposes frame-shaving options in `AnalyzerOptions`
and the API contract: sampling FPS, adaptive-sampling flag, scene-change
sensitivity, scene-anchor preservation, and intermediate-sample keep/delete
policy. Software-decoded fallback frames are deleted by default after the
selected scene frames and evidence are persisted; debug runs can retain them.
The manifest records the resolved shaving settings and cleanup result. The
dummy run confirmed `_decoded_frames/` was removed while three scene anchors
remained.

An explicit `promote_run.py` command now copies approved frames and extracted
audio into `/home/riki/web_dev/story_builder/video_repertoire/` and writes a
provenance manifest. It resolves container paths safely and does not move or
delete source run artifacts. The dummy run was promoted under project ID
`dummy-video-project` without changing existing analyzer or website routes.

## 20. Configurable frame-shaving and media-repertoire UI expansion

### 20.1 Frame shaving objective

Frame shaving is an evidence-reduction stage, not a fixed frame counter. Its
goal is to discard visually redundant samples while retaining frames that
represent meaningful story, motion, camera, lighting, composition, or
continuity changes.

The current baseline uses sampled-frame visual difference (`scene_threshold`),
`min_scene_seconds`, and first/middle/last representatives. The upgraded
shaver will preserve that behavior as the safe baseline and add independent,
auditable signals:

- pixel/SSIM or perceptual-hash change between adjacent samples;
- motion magnitude and motion peaks from optical flow;
- camera/shot change indicators from global motion and framing change;
- subject/object appearance or disappearance when evidence is available;
- lighting/exposure change;
- subtitle/text change;
- audio-event onset/ending aligned to the same timestamp;
- a minimum temporal separation to prevent near-duplicate keyframes.

Each retained frame records the reasons and scores that caused retention. A
frame is retained when it crosses the configured change sensitivity, is a
scene boundary, is a motion/camera/audio peak, or is required as a stable
first/middle/last continuity representative. It is never retained solely
because the source video has a high FPS.

### 20.2 Frame-shaving controls

The Video Summariser page will expose these controls, with conservative
defaults matching the current behavior:

| Control | Default | Purpose |
|---|---:|---|
| Analysis sampling FPS | 4 | Initial evidence sampling rate, independent of source FPS |
| Adaptive action sampling | On | Temporarily samples faster around motion/transition peaks |
| Change sensitivity | 0.26 | Visual-change threshold; lower retains more evidence |
| Minimum scene duration | 0.5 s | Prevents unstable micro-scenes |
| Motion/camera awareness | On | Retains meaningful movement and framing changes |
| Audio-event alignment | On | Retains visual evidence around speech/music/SFX changes |
| Keep intermediate samples | Off | Debug option; normally only selected evidence remains |
| Delete intermediate samples after analysis | On | Removes temporary decoded frames after the manifest is written |
| Preserve first/middle/last representatives | On | Maintains continuity anchors in every accepted scene |

The UI must show the resolved settings in the run manifest. The analyzer must
retain temporary samples only until scene boundaries and keyframes are safely
persisted. Cleanup must be resumable and must never delete source videos,
selected keyframes, clips, audio, or manifests.

### 20.3 Video Summariser page additions

The existing library, selection, Analyze navigation, scene/cut detector,
frame selector, results tabs, playback, and search must remain intact. Add an
audio panel whose controls are independent from frame controls:

- extract source audio;
- create `analysis.wav`;
- create `preview.mp3`;
- sound-event detection and detector selection;
- speech/transcription;
- music analysis;
- SFX/ambience analysis;
- semantic audio and audiovisual embeddings;
- diarization and same-speaker matching;
- character/active-speaker association;
- Demucs `AUTO/off/2/4/6`;
- on-demand SAM Audio preview/save;
- voice-feature analysis.

Results must include synchronized, timestamp-linked sections for:

- entire video;
- scenes;
- clips;
- selected frames;
- dialogue and voice examples;
- music regions;
- SFX/ambience regions;
- combined audiovisual events.

The UI must display optional-stage readiness and failure reasons without
making video-only analysis appear failed.

### 20.4 Unified media repertoire storage

Reusable derived media will be stored outside transient run results under:

```text
/home/riki/web_dev/story_builder/video_repertoire/
├── videos/<video-id>/source-and-provenance.json
├── scenes/<scene-id>/
├── clips/<clip-id>/video.*
├── frames/<frame-id>/image.*
├── audio/<audio-event-id>/preview.*
├── music/<music-event-id>/audio.*
├── sfx/<sfx-event-id>/audio.*
├── voices/<voice-example-id>/audio.*
├── events/<event-id>/event.json
├── indexes/
└── manifests/
```

Every stored asset keeps `video_id`, `project_id` when applicable, scene/clip
IDs, timestamps, source checksum, model/runtime provenance, license notes,
embedding references, and whether it is temporary or reusable. Search results
are transient UI state and must not pile up in the interface; approved assets
remain reusable across projects through the shared indexes.

The existing `video_audio_analyzer/runs/` package remains the immutable run
record. A promotion step copies or links approved clips/audio/voices into
`video_repertoire/` without moving or deleting source files.

### 20.5 Safe website replacement and rollback gate

Before changing the Story Builder website or API connections, create a
timestamped compressed backup containing:

- frontend source and package lock;
- backend/API source and configuration;
- current Video Summariser route/components;
- current proxy/API connection settings;
- a manifest listing commit/hash, paths, and restore command.

The backup must be created before the backend switch and kept outside the
working tree. Integration uses a reversible configuration switch:

```text
VIDEO_ANALYZER_BACKEND=legacy | video_audio_analyzer
```

The legacy backend remains selectable until the new analyzer passes the dummy
comparison, API contract, build, and Playwright gates. No existing UI,
workflow, ComfyUI, Docker source image, Conda environment, or saved analysis
may be overwritten. If integration fails, rollback is configuration-only and
the compressed backup remains available.

### 20.6 Manual requirements and open decisions

No manual action is required for frame shaving, storage layout, backup
creation, or API/UI wiring. The following may require user-provided assets or
credentials when those phases are reached:

- gated SAM Audio or optional pyannote checkpoint access;
- a prepared `faster-whisper-large-v3` model cache if local ASR is required;
- Demucs model preparation if the isolated separation worker preflight needs
  it;
- optional HF tokens/license acceptance for gated models;
- final approval to switch the website from legacy to the new analyzer after
  reviewing the comparison report.

No product ambiguity currently blocks plan implementation. Before integration
I will still confirm the backup destination and retention period, and whether
approved media should be copied or hard-linked when the filesystem supports
it. The safe default is a copied, independently deletable repertoire asset.

### 20.7 Hermes/Codex reasoning-provider selection

The director and other LLM reasoning steps must be selectable between the
existing Hermes/OpenCode route and Codex without coupling the media pipeline
to either provider. The provider switch applies to reasoning/decision calls
only; it does not switch ComfyUI workflows, FFmpeg, ASR, embeddings, storage,
or deterministic worker execution.

#### Sequencing decision

Do not build the full application around a hard-coded Hermes call and retrofit
Codex afterward. Also do not expose an untested provider toggle in the UI
before both routes satisfy the same contract. Use this sequence:

1. Define a small provider-neutral structured-reasoning contract and task
   registry first. Keep prompts, JSON schemas, validation, retries, audit
   records, and tool/executor calls in the application layer.
2. Add the Hermes/OpenCode adapter as the initial active adapter and complete
   the director/identity-decision work through that contract. This preserves
   the agreed Hermes-first implementation while avoiding Hermes-specific
   assumptions in every workflow.
3. Add the Codex adapter behind the same contract. Test identical task inputs
   and schemas against Hermes and Codex using dummy projects before enabling
   user selection.
4. Expose the Hermes/Codex selector only after both adapters pass contract,
   safety, and regression tests. Start with a configuration/feature flag;
   then add the UI control in the existing website integration phase.

In short: build the provider seam first, finish and validate the workflows
with Hermes first, then add and validate Codex, and expose the toggle last.
This avoids both a Hermes-only design that is expensive to retrofit and an
early UI toggle that can route production runs to an untested backend.

#### Scope and routing

The website setting is a global default for eligible reasoning tasks, with a
per-run snapshot/override where a workflow needs an explicit choice. It covers
director planning/review, story analysis/refinement and outline, production
planning, and Hermes-confirmation decisions such as speaker/character/Voice
Store matching and SAM Audio save decisions. When `video_audio_analyzer` is
connected to the website, its temporal scene/video prose and continuity
reasoning must use the same selected provider, passed in the job contract and
recorded in its manifest. Keep its Qwen/Ollama visual evidence extraction
separate; do not route image vision through this selector by implication.
Each run records the selected provider, exact model identifier, adapter
version, prompt/schema versions, and fallback/retry history. Paused or resumed
runs continue with their recorded provider unless the user explicitly starts
a new run or accepts a provider-change prompt.

The current Story Builder Ollama calls and the standalone image-vision model
remain separate during rollout. In particular, do not silently replace the
Qwen/Ollama Image Detailer with Codex: vision is a distinct capability and
must only join the selector after its image-input support, cost, output
quality, and tests are explicitly established. Preserve the current Ollama
path as a rollback/compatibility option until the new adapters pass parity
tests.

Hermes/OpenCode and Codex adapters must return validated structured outputs
through the same application-owned schema. Provider failure is explicit; do
not silently switch providers or model families. If a deliberate fallback is
later added, it must be separately configured, visible in the run record, and
covered by tests. Tool execution, permissions, and writes remain governed by
the existing application services and backend authorization—not delegated
implicitly to whichever model provider is selected.

#### Non-regression and acceptance gates

- Keep Hermes as the initial reasoning provider for the newly planned
  director/confirmation path; Codex is an additional selectable adapter, not
  a rewrite of already tested media workers.
- Keep existing Ollama-powered endpoints and Image Detailer behavior intact
  until explicit migration tests pass.
- Do not change ComfyUI, Docker images, worker dependencies, Conda
  environments, media manifests, or API contracts merely to add provider
  selection.
- Keep credentials server-side; the browser stores only a selection, never
  provider tokens or CLI secrets.
- Test structured JSON validity, required fields, unsupported-claim handling,
  retries, provider-unavailable behavior, and audit provenance for both
  adapters.
- Test that provider selection does not alter deterministic executor
  behavior, permissions, or persisted media outputs.
- Before website UI integration, back up the relevant frontend/backend/API
  source and lock/config files as required by Section 20.5; implement behind
  a reversible feature flag and verify both modes with backend tests and
  Playwright.
- The toggle is ready for general use only after representative director and
  story tasks have passed against both adapters and the existing application
  test suite has no regressions.

### 20.8 Provider-selector implementation status (2026-09-26)

The Story Builder website now has a global reasoning-provider selector with
Ollama retained as the compatibility/default path and Hermes/OpenCode and
Codex as explicit alternatives. Story assist, story revisions, story artifact
generation, planning automation, and director planning use one
provider-neutral structured-JSON adapter. Automation runs snapshot their
provider, model, and adapter version at start, so changing the global setting
does not silently switch an active run. A no-save director-test endpoint and
UI action exercise the actual director prompt with synthetic data.

Codex is verified locally with `gpt-6-luna`: the website director test
returned a valid two-shot, two-character plan, and the Story Assist API
returned valid structured refinement under the Codex global selection.
Playwright verified the selector across all 14 website routes, Codex
selection/persistence and restore, no browser exceptions, and no horizontal
overflow at a 390px viewport. The Story Builder backend test suite passed
(53 tests); the frontend test and production build also passed.

Hermes adapter code is present, but Hermes is not currently validated as a
working model route. The local Hermes status reports `qwen3.6:35b` through
OpenCode Zen (not GLM 5.3); its one-shot request returns HTTP 400, `Model is
unavailable`. OpenCode currently has no saved credentials, and the Hermes
status shows GLM is not configured. Until a usable Hermes model/provider is
selected and authenticated, choosing Hermes will produce an explicit error,
not an automatic Codex/Ollama fallback. This requires a user-side Hermes
provider/model setup followed by the same director smoke test.

The pre-change website/API backup was created at
`/tmp/story-builder-provider-switch-backup-20260926.tar.gz`; its SHA-256 and
restore instructions are in `plan/provider-switch-backup-20260926.md`. No
ComfyUI, Docker, or Conda environment was changed. The isolated
`video_audio_analyzer` is not yet the backend behind the website route; its
provider propagation remains part of that later integration gate.

### Phase 3A status — ASR, Demucs, and ECAPA validation (2026-09-26)

The canonical `faster-whisper-large-v3` checkpoint is now prepared in the
isolated model cache. The dummy video produced an English transcript with
word timestamps (`2.93–6.17s`) using CPU int8 fallback because the available
CTranslate2 wheel has no CUDA kernels.

Demucs 4.0.1 is installed only in the derived analyzer image. AUTO mode ran
`htdemucs` after original-mix event detection and produced bass, drums, other,
and vocals WAV stems.

SpeechBrain ECAPA is installed only in the derived worker. Its compatibility
shims are isolated, and the dummy run produced one 192-dimensional
timestamp-linked voice embedding. This is a voice embedding, not a claimed
named character or diarization result.

### 20.9 Provider decision update — Codex default, Hermes excluded (2026-09-26)

This section supersedes the Hermes/Codex selector details in 20.7 and 20.8:

- Codex using the exact model ID `gpt-6-luna` is the default provider for
  eligible Story Builder reasoning tasks.
- Hermes/OpenCode is excluded from the application provider selector and is
  not a supported reasoning route.
- Ollama remains an optional compatibility provider for text reasoning where
  explicitly selected. The Qwen/Ollama Image Detailer vision model remains
  separate and is not replaced by Codex.
- Existing Story Builder reasoning entry points using the shared adapter
  (story assistance, story analysis/revisions, story artifacts, automation
  planning, and director planning) use Codex by default. Automation runs keep
  their provider/model snapshot.
- The independent `video_audio_analyzer` is not yet integrated into the
  website and does not yet consume this selector. Its future text/continuity
  reasoning must use Codex by default; visual evidence extraction remains a
  separate model stage.

Validation for this change must include a real Codex structured-output smoke
test, director dummy test, backend/frontend tests, and Playwright coverage of
the selector on all website routes. No Hermes authentication/setup is
required.

### 20.10 Isolated audio/model validation status (2026-09-26)

This subsection supersedes older Phase 3A statements that HTS-AT, NeMo,
ECAPA, CLAP, PE-AV, and production LanceDB were still preflight-only. It does
not supersede the staged website replacement gate.

Completed and exercised in `video_audio_analyzer` only:

- HTS-AT AudioSet checkpoint inference in the isolated worker. The adapter
  normalizes logits/probabilities correctly, uses the official time-axis
  repeat interpolation, and retains uncertain scores rather than generating
  hundreds of sigmoid-induced false events. The supplied dummy returns broad
  Speech and Music labels over the complete 8.73-second clip; it has no
  confidently detected named SFX.
- NeMo offline clustering diarization with local MarbleNet VAD and TitaNet
  checkpoints; RTTM and three speaker intervals are persisted into the run.
- SpeechBrain ECAPA 192D voice examples, stable UUID-backed anonymous Voice
  Store records, project-first then cross-project LanceDB ANN top-K lookup,
  idempotent same-source retries, and deduplicated ANN candidates. Cross-project
  similarity is never an automatic merge: the identity decision remains
  pending until the Codex director adapter can write its provenance/audit
  decision.
- CLAP text/audio vectors (512D) retained separately from PE-AV Base vectors
  (1024D), batched worker requests, late score fusion, and a real text search
  against the latest dummy index. No vector concatenation is used.
- SAM Audio isolate/save API contract: an event must be explicitly selected;
  preview output is temporary; repertoire save requires the explicit
  `save_to_repertoire` decision. It reports 503/unavailable truthfully while
  the official gated checkpoint and SAM sidecar are absent.
- Final same-video comparison is in `plan/video_audio_analyzer_dummy_comparison.md`.
  The legacy analyzer remains read-only. The new analyzer preserves the single
  scene and timestamps and shaves output to three representative frames; for
  this dummy, the legacy transcript has better word coverage.

Remaining gates and validated capabilities:

- Person/face appearance identity across shots/videos is still incomplete:
  TalkNet/S3FD now produces within-video face tracks and timestamped active
  speaker scores, and the analyzer joins these to NeMo turns as candidates.
  It does not assert stable identity across cuts/projects without a separately
  licensed face-embedding/appearance-ReID model.
- Codex `gpt-6-luna` director confirmation/audit adapter inside the analyzer.
  The Story Builder provider selector does not automatically make Codex
  callable from this isolated worker;
- live SAM Audio inference. The canonical `facebook/sam-audio-base-tv`
  checkpoint is Hugging Face gated and is not locally prepared. No unofficial
  replacement was downloaded, and no sound-isolation success is claimed;
- broader multi-video quality/performance benchmarks before replacing the
  legacy website analyzer.

### 20.11 Active-speaker and final validation update (2026-09-26)

This subsection supersedes the TalkNet-unavailable statements above.

- A dedicated `video-audio-analyzer-talknet:dev` container is built from the
  isolated analyzer audio image. Only this new image receives the two
  TalkNet-specific helper dependencies; neither parent image, other Docker
  services, ComfyUI, nor Conda environments were changed.
- Canonical TalkNet-ASD source is vendored at
  `video_audio_analyzer/vendor/TalkNet-ASD`; the TalkSet and S3FD checkpoints
  are in `video_audio_analyzer/models/talknet/`. A compatibility patch
  replaces removed `numpy.int` with `int`. Checkpoint redistribution/commercial
  license remains unverified and requires review.
- The supplied dummy produced one face track, 216 active-speaker scores, and
  two NeMo-turn-to-face-track candidate associations. Candidates remain
  unmerged until the Codex director makes an auditable decision. TalkNet does
  not provide cross-video character identity or body appearance/ReID.
- PANNs fallback inference was run against the dummy's extracted analysis WAV
  in a disposable analyzer container; it corroborated Speech/Music and found
  no high-confidence named SFX. HTS-AT remains the selected primary detector.
- Final integrated run:
  `video_audio_analyzer/runs/c938423ea483bdc3-rerun-5e8c06b4/`.
- Analyzer regression suite: 24 passed, 1 skipped. The skipped LanceDB test
  was separately verified in the pinned analyzer Docker runtime.

Still requiring external/manual readiness before claiming every capability
complete:

- Live SAM Audio inference requires accepting official gated
  `facebook/sam-audio-base-tv` access terms, preparing/authenticating the
  local checkpoint, and providing the isolated inference worker. The analyzer
  correctly keeps the other stages functional and returns unavailable until
  that is done.
- Automatic Codex director confirmation requires a server-side Codex endpoint
  accessible to the analyzer. The Story Builder Codex selector is not a
  credential bridge into this isolated worker. Until wired, voice/face matches
  remain candidates and are never merged based only on similarity.
- Cross-shot/cross-video visual character matching requires a licensed
  appearance-embedding/ReID model; active-speaker detection only predicts
  which visible face is speaking during a given interval.

These gates do not invalidate the completed audio-analysis and retrieval
outputs. They prevent claiming full character identity, director-confirmed
cross-project merges, SAM isolation, or website replacement. No legacy
summarizer, website/API, ComfyUI environment, or Conda environment was edited
for this validation.

### 20.12 Final analyzer-stage implementation and validation (2026-09-26)

This subsection records the latest isolated-analyzer implementation and
supersedes 20.10/20.11 wherever they describe the SAM worker as absent or
TalkNet as not integrated. It does not claim the external model-access and
director-service gates below have been satisfied.

Completed in `video_audio_analyzer`:

- HTS-AT remains the primary sound-event detector and PANNs remains the
  fallback. Both were run on the supplied dummy: each found broad Speech and
  Music windows, and neither found a confident named sound effect. Detection
  therefore works, but this is not exhaustive sound coverage or a benchmark
  proving recall for every SFX class.
- Offline NeMo clustering diarization, with local MarbleNet VAD and TitaNet,
  completed on the dummy (one speaker, three turns). ECAPA produced
  timestamp-linked voice examples and stable UUID-backed Voice Store records.
- Voice Store lookup is persistent LanceDB ANN, bounded top-K, project-local
  first and global/cross-project second. Idempotent retries and the local to
  global fallback were verified in the pinned analyzer Docker runtime; raw
  audio is not globally compared, and cosine similarity alone never merges
  identities.
- PE-AV and CLAP vectors remain separate (1024D and 512D respectively).
  CLAP text/audio inference and normalized late reranking are live; there is
  no concatenation of independently trained vectors.
- TalkNet-ASD and S3FD run in a dedicated analyzer-only GPU container. The
  dummy generated one within-video face track and 216 timestamped scores;
  the host-side Codex `gpt-6-luna` reviewer confirmed two NeMo speaker-to-face
  links from temporal overlap and active-speaker scores, while leaving the
  low-evidence turn anonymous. Decisions are stored as immutable-run review
  sidecars, with a JSONL audit; the analyzer API overlays them when serving a
  manifest. This does not establish stable identity across cuts/videos.
- `run_peav_worker.sh` invokes the Codex reviewer by default when bounded
  identity candidates exist. Set `VIDEO_AUDIO_ANALYZER_CODEX_DIRECTOR=0` to
  disable it. The Codex CLI runs on the host in read-only/ephemeral mode;
  credentials are never passed into a Docker image. Voice identity links are
  written to a separate Voice Store link journal and are only applied when
  Codex has independent trusted identity evidence. Similarity alone is
  rejected by validation.
- A dedicated SAM Audio worker/image has been built, with local-only model
  loading, temporary preview handling, expiry/cleanup, and explicit
  `save_to_repertoire` persistence. Health, missing-checkpoint and API
  lifecycle behavior were tested. The full SAM inference path is implemented
  but cannot be acceptance-tested until the gated checkpoint is locally
  available.
- The completed same-video run and read-only comparison against the legacy
  summarizer are recorded in
  `plan/video_audio_analyzer_dummy_comparison.md`. Latest run:
  `video_audio_analyzer/runs/c938423ea483bdc3-rerun-009fbcdc/`.

Remaining external gates (not permission to alter other environments):

1. **SAM Audio gated model access:** accept the access terms for
   `facebook/sam-audio-base-tv`, configure authentication only for the
   explicit download/preparation step, and stage the checkpoint at
   `video_audio_analyzer/models/sam-audio-base-tv`. The analyzer does not
   auto-download it. The repository/model is governed by the SAM License;
   review that license for the intended use before commercial use or
   redistribution. After staging, start only the analyzer's `sam-audio`
   Compose profile and validate an actual temporary isolation plus explicit
   repertoire save.
2. **Cross-project voice identity decisions:** bounded local/global ECAPA
   candidates and non-destructive Codex link/audit support are implemented.
   This dummy had no prior matching identity candidate, and the run therefore
   made no cross-project voice merge. The current extraction pipeline does
   not yet attach trusted name/character evidence to voice centroids, so such
   matches remain separate until that independent evidence exists. No
   similarity-only merge is allowed.
3. **Cross-video visual identity:** choose a face/body appearance model only
   after checkpoint licensing is verified. TalkNet/S3FD and its within-video
   track IDs are not a cross-video ReID system.

Final focused analyzer test invocation completed with **22 passed, 1
skipped**. The skipped test requires the pinned LanceDB runtime and its
equivalent ANN behavior was exercised in the analyzer Docker image. A broad
host pytest invocation is invalid because it also collects vendored
upstream/legacy tests without their own import roots; use the focused analyzer
suite. The final integration run returned success and all available model
stages above were represented in its manifest. AV1 hardware decode warnings
fell back to software and did not fail the run. No Story Builder website,
legacy summarizer, ComfyUI image, or Conda environment was changed, so
Playwright is deferred until the separately approved website integration.
The Codex review sidecar is served as an overlay by the analyzer manifest API;
the raw model manifest and original media artifacts are not rewritten.
The actual dummy Codex review confirmed one within-video speaker/face-track
association at 0.90 confidence; a proposed 0.65 association was downgraded to
anonymous by the 0.75 automatic-link floor. It preserved the anonymous alias
and did not claim a real name or merge an external identity. The read-only review completed with
the configured `gpt-6-luna` CLI. The standalone host runner now performs this
review when candidates exist, with `VIDEO_AUDIO_ANALYZER_CODEX_DIRECTOR=0` as
an explicit opt-out. This does not yet provide a browser/API-triggered Codex
job coordinator; that belongs to the later website integration phase.

### 20.13 Director, routine-model, and per-run media-collection policy (2026-09-27)

This section is the current product decision and supersedes earlier provider
wording that makes Hermes the default director, or treats Codex and Ollama as
interchangeable routine generators.

#### Model roles

- **Ollama Qwen** performs ordinary, high-volume generation and analysis using
  application-owned base prompts and strict schemas. It does not own system
  policy or make final director/identity decisions.
- **Codex (`gpt-6-luna`) is the director and system steward.** Within an
  automation run it reviews coherence, selects/approves next actions, and
  adjudicates ambiguous evidence. When the user asks to improve the product,
  Codex may also review and revise base prompts, troubleshoot failures, and
  recommend or implement efficiency/code improvements within the user's
  explicit task scope. It must not silently self-modify production code or
  prompts during an ordinary media-analysis run; changes are versioned,
  tested, and auditable.
- **Hermes is an optional fallback for Codex only.** It is not the routine
  generation engine, primary director, or an always-active parallel worker.
  Fallback must be explicitly configured, recorded in the run audit, and must
  not silently change model/provider. If Hermes is unavailable or has no
  configured model/credentials, the Codex-dependent decision remains pending
  or uses its safe non-blocking fallback (for example, retain an anonymous
  identity); routine Qwen stages continue.
- **Ollama Qwen vision remains its separate image-evidence role.** Do not
  route image pixels to Codex/Hermes unless a later task specifically adds and
  tests that capability.

The analyzer's existing Codex review sidecar is the current director
implementation. The website-wide Qwen/Codex/Hermes routing and prompt
management must be verified and integrated consistently; old labels or
historical Hermes sections elsewhere in this plan are not evidence that an
active Hermes route exists. Provider output is validated by application code,
and model reasoning must never receive unrestricted executor or filesystem
authority.

#### Separate analysis from reusable-asset collection

The Analyze page must present an **Audio & Reusable Assets** settings panel
independent of frame shaving, scene detection, and frame-selection controls.
Keep the existing source-audio/analysis/transcript and event-analysis defaults
unless the user changes them for a particular run. Add separate, explicit
per-run toggles for whether the analyzer should create and persist reusable
media assets. Running analysis must not automatically mean that every voice,
music passage, or SFX is added to a cross-video repertoire.

Use this distinction:

| Control | Recommended new-run default | Effect when on |
|---|---|---|
| Analyze speech/transcript | On (existing default) | Timed transcript for scene/video understanding; does not by itself save voice samples |
| Build voice examples / Voice Store entries | **Off** | Diarize as needed, quality-filter voice excerpts, compute identity/style metadata, and save them to the selected project's voice collection |
| Analyze music events/features | On (existing default) | Detect and describe timed music regions for the report; does not by itself save music excerpts |
| Collect reusable music clips | **Off** | Persist selected, timestamped music excerpts and metadata in the music repertoire |
| Analyze SFX/ambience events | On (existing default) | Detect and describe timed events; does not by itself isolate or persist audio clips |
| Collect reusable SFX/ambience clips | **Off** | Persist selected SFX/ambience excerpts with timestamps and source provenance |
| Run Demucs | AUTO (existing default) | Separate only when policy/settings indicate stems are useful; never treat stems as semantic labels |
| Create semantic audio / AV embeddings | On (existing default) | Index supported event records; honor per-category collection toggles and retention policy |
| Isolate selected sound with SAM Audio | On demand | Create a temporary preview; persist only after the explicit director `save_to_repertoire` decision |

The collection toggles are per analysis job, are saved in its immutable
settings snapshot, and can be changed for the next job without changing
existing projects or artifacts. Provide clear `Analyze only` versus `Analyze
and collect` language, per-category progress, storage estimates when
available, and a visible list of exactly which assets were persisted. Turning
collection off must not remove original audio, transcript, event metadata, or
other evidence required by enabled analysis stages. Turning it on must still
apply duration, quality, overlap, deduplication, provenance, and license
filters. Do not create SAM-isolated files automatically from the collection
switch; SAM remains an explicit/lazy isolation action under its separate
policy.

#### Voice identity scope for the first integrated release

Project-local voice matching and stable anonymous UUIDs are the first-release
requirement. Cross-project identity matching is **deferred and non-blocking**:
do not ask the user to supply matching voice samples, do not block video
analysis on it, and do not let a global similarity result merge identities.
The existing bounded global Voice Store index may be retained as dormant
infrastructure, but the integrated UI defaults to project-only matching until
cross-project evaluation demonstrates value and Codex can make an evidence-
backed decision. Cross-project matching can be enabled later as an explicit
advanced setting; it is not a prerequisite for analyzer completion or website
integration.

#### Updated SAM checkpoint selection and manual-action status

The requested checkpoint is now **`facebook/sam-audio-large-tv`**, not the
previously planned Base TV variant. The user has staged its files under
`video_audio_analyzer/models/sam-audio-large-tv/`; the reported local
checkpoint filename is `sam-audio-large-tv_checkpoint.pt`. The existing SAM
worker/configuration still accepts only Base TV and is not yet compatible with
this Large TV directory. The implementation phase must update the isolated
worker, model registry/preflight, Compose mount, API model validation, and
license/status metadata to select Large TV explicitly, then run a real
isolation, temporary-preview cleanup, and director-approved repertoire-save
test. Do not rename, copy, or load the 14.9 GB checkpoint until the loader's
expected filename/format is verified; avoid making a second full checkpoint
copy. Do not silently fall back to Base TV.

No further manual technical setup is currently requested for voice collection
or cross-project matching. The SAM checkpoint has been staged; the remaining
work is software wiring and inference validation. The only user-side check is
to review the SAM License for the intended use, especially before commercial
use or redistribution. The analyzer developer can use the existing dummy
video and controlled test fixtures for implementation and regression tests;
additional hand-labelled audio clips would improve sound-event quality
benchmarking but are not a prerequisite. Cross-video visual ReID remains an
optional future enhancement pending an explicitly license-compatible
checkpoint; it is not a blocker for project-local voice examples or the first
website integration.

#### Remaining implementation order and acceptance gates

1. Wire and test the staged SAM Audio Large TV checkpoint in its isolated
   worker; confirm temporary cleanup and explicit save behavior.
2. Add the per-job analysis-versus-collection toggles and test all on/off
   combinations without changing the existing video/frame controls or saved
   project results.
3. Validate project-local voice-example creation and project-local identity
   lookup; keep cross-project identity matching deferred.
4. Expand detector tests with available/curated examples and report measured
   class coverage honestly; no claim of exhaustive SFX recognition from the
   current speech/music-only dummy result.
5. Back up the current website/API connections, then integrate the analyzer
   and audio settings/results into the existing Video Summariser page behind
   the reversible backend switch. Run backend/frontend tests and Playwright
   regression/interaction coverage before making it the default.
6. Verify the website model routing: Ollama Qwen for ordinary generation and
   analysis, Codex as director/system steward, Hermes only as an explicitly
   configured Codex fallback, and Qwen/Ollama vision kept separate. Record
   provider/model/prompt versions and any fallback in run/project audit data.

### 20.14 Current implementation and next-phase status (2026-09-27)

This is the newest status record and supersedes older phase-gate statements
above where they say the Large TV SAM worker or the audio UI is not yet wired.
It does not claim that the whole analyzer replacement is complete.

#### Implemented and verified

- The original Video Repertoire source/library/download workflow, scene
  detector, frame selection, frame-shaving controls, timestamps, and legacy
  visual-analysis results remain in place.
- The Analyze tab now includes an independent, per-job audio analyzer panel.
  Speech/transcript, speaker diarization, music-event analysis, SFX/ambience
  detection, audio embeddings, and AV embeddings are enabled by default;
  Demucs defaults to `AUTO`.
- Voice-example, reusable-music, and reusable-SFX collection are separate
  per-job toggles, default OFF. Detection/analysis does not imply persistent
  collection. The settings snapshot is passed to the isolated analyzer.
- Results show audio preview, detected timestamped events, transcript and
  diarization statuses, embedding status, and any collected voice/music/SFX
  assets. The Video Repertoire page now also has an additive **Audio Assets**
  tab that browses explicitly promoted voice/music/SFX/ambience assets and
  Codex-approved SAM isolations from `video_repertoire`, with category filter,
  text filter, timestamps/source provenance, and playback. Source/analysis
  audio is not exposed as a reusable asset by this browser. This is the first
  durable audio-library UI; richer voice identity matching/management and
  semantic audio search remain future UI work.
- The SAM Audio Large TV checkpoint is staged under
  `video_audio_analyzer/models/sam-audio-large-tv/` and the isolated worker is
  configured for `facebook/sam-audio-large-tv`. The Story Builder Results UI
  can request an event-specific temporary isolation, play the WAV, request a
  Codex metadata/provenance review, or discard it. A save happens only when
  Codex returns the explicit `save_to_repertoire` action. Temporary output is
  TTL-cleaned; persisted output is provenance-linked under
  `video_repertoire/audio/isolated/`.
- Live SAM inference against the dummy analyzer run produced a playable
  temporary preview. Codex discarded that particular generic/low-confidence
  event, as intended; it did not claim to listen to the waveform. Unit tests
  cover the explicit save path, discard/expiry, malformed requests, and Codex
  unavailability. An accepted save has therefore been verified by tests, not
  by a separate live director-approved example.
- The responsive Results layout was checked at desktop and narrow viewport;
  the audio panel no longer causes horizontal page overflow.
- Current verification: backend targeted suite `13 passed`; frontend
  `1 passed`; production frontend build succeeds. Existing Vite config and
  bundle-size warnings remain unrelated to this audio integration. Playwright
  against a disposable Story Builder instance verified the Audio Assets tab,
  API list (`200`), audio content (`200`), category filter, no browser
  exceptions, and no horizontal overflow at a 390px viewport. Existing site
  ports were left running and untouched.

#### Non-commercial use and model-license handling

The project owner states the intended use is non-commercial. This is recorded
as project context, not treated as a substitute for a model's actual license
terms. In particular, code-license and pretrained-checkpoint/model-license
must remain distinct fields in preflight. The current SAM Audio Large TV
agreement grants a limited royalty-free right to use/modify SAM Materials and
does not state a blanket non-commercial-only restriction; it still imposes
privacy, trade-control, use, and redistribution conditions. If SAM Materials
or derivatives are made available to third parties, include a copy of the
agreement and comply with its redistribution clause. The project owner says
the repository is intended to remain private; secrecy itself does not waive
any license condition. The proposed cross-video face-recognition/ReID
checkpoint remains deferred: InsightFace's own model-zoo terms limit its
pretrained models to non-commercial research, which is not automatically the
same as any private personal project. Project-local voice identities and
anonymous UUID-backed aliases remain usable without visual ReID.

#### Remaining work and next phases

1. **Voice collection and project-local identity validation — completed for
   the supplied dummy:** an isolated opt-in run completed with
   `collect_voice_examples=true` in a fresh `phase_voice_test` store. It
   produced a timestamped 3.24-second WAV example, a 192-dimensional
   `speechbrain/spkrec-ecapa-voxceleb` identity, immutable character/voice UUIDs,
   and a collision-safe anonymous alias. NeMo clustering diarization completed
   with one speaker, and Codex `gpt-6-luna` wrote two provenance-backed speaker /
   face decisions in the run audit; neither decision authorized an identity
   merge. Voice collection remains OFF by default and opt-in. A separate
   second-project probe using the real ECAPA centroid retrieved the identity
   from the global Voice Store as a bounded top-K candidate (JSONL centroid
   fallback); this was retrieval only and did not merge identities.
   Cross-project matching is enabled. LanceDB ANN is preferred when its
   worker-side preflight succeeds; the portable fallback scans identity
   centroids, never raw utterance pairs.
2. **Sound-event quality coverage:** the latest opt-in run again detected
   speech and music (HTS-AT, with timestamp/confidence) but did not produce a
   named SFX event. This confirms the detector is active, not that general
   sound effects are comprehensively covered. Broaden evaluation with
   representative, labelled SFX material; report per-class evidence and model
   availability and do not imply exhaustive detection. HTS-AT/PANNs preflight
   and graceful fallback must remain truthful.
3. **Analyzer search integration:** the analyzer exposes
   `/api/search/all` for corpus-wide paginated search across run indexes.
   The isolated `peav-search` Compose profile serves real text-query
   embeddings at port 8034; the host/API environment does not install the
   PE-AV Transformers build. Semantic results are withheld unless a real
   PE-AV or CLAP query vector matches a corresponding real index vector.
   Keyword search remains available and deterministic fallback vectors are
   never presented as semantic matches. CLAP remains a separate vector space
   and is only a bounded late reranker/fallback when available. Reindexing
   preserves legacy CLAP vectors only for exact record-ID matches with the
   declared vector dimension; PE-AV query results now exclude CLAP-only
   zero-score rows. Cross-run
   fan-out currently reads run JSONL indexes and globally ranks the records;
   this is adequate for the present corpus but is not cross-run LanceDB ANN.
   Benchmark and add a shared/partitioned ANN index only when corpus size or
   measured latency justifies it. The existing Video Repertoire search still
   uses its prior curated index until parity tests pass and the new endpoint
   is wired into the site.
4. **Audio library UX:** the durable browse/playback tab is implemented for
   collected voice/music/SFX/ambience and SAM-isolated assets, with timestamp
   and source metadata when available. Remaining UX work is richer voice
   identity/alias browsing, stem-library exposure, semantic audio search UI, and
   asset retention/delete controls with safe reference checks. Do not make
   these views required to finish analysis; current per-run results remain
   available.
5. **Scene/video report quality:** replace or improve the current weak legacy
   report only after a factual Qwen prompt/structured-output evaluation. The
   new analyzer's short structural manifest summary is not yet a director-grade
   narrative. Preserve evidence, transcript provenance, and uncertainty; strip
   reasoning traces and never invent unsupported actions.
6. **Replacement gate:** keep the existing visual workflow and UI as the
   fallback. After the above relevant tests, make the new analyzer the default
   behind a reversible backend switch, compare both analyzers on
   `plan/Brother eww what’s that？💀 #meme.mp4`, then run Playwright regression
   checks on source selection, frame controls, audio toggles, job persistence,
   Results playback, search, and SAM preview/save/discard.

No manual model installation is currently required for the already staged
SAM Large TV checkpoint. A curated, representative speech/SFX/music fixture
set would improve the quality benchmark, but it is optional: use the supplied
dummy and existing local media for continued implementation. A user-provided
voice recording is not required for code-level validation; generated or
existing suitable speech may be used while keeping the collection opt-in.

### 20.15 Corpus-wide analyzer retrieval API (2026-09-27)

- Added `POST /api/search/all` to the isolated analyzer API. It fans out across
  persisted per-run indexes, returns globally paginated results, and uses a
  run-qualified result ID so repeated frame/scene IDs from different videos
  never collide.
- PE-AV and CLAP remain distinct embedding fields; CLAP is only an optional
  bounded late reranker. No vector concatenation was introduced.
- Semantic corpus results include only records whose run manifest confirms
  completed PE-AV embeddings and whose vector dimension matches that run's
  index manifest. If the PE-AV text query encoder is unavailable, the endpoint
  returns no semantic results with an explicit reason instead of silently
  ranking deterministic hash vectors as meaning-based matches.
- Keyword and hybrid modes retain non-PE-AV records, with non-semantic vector
  scores set to zero. Deterministic fallback remains clearly marked.
- Scene-level PE-AV vectors are indexed as `scene_clip` records. A scene vector
  is no longer copied onto every frame/audio-event row. Frame and sound-event
  rows carry semantic vectors only if their own pipeline stage created them.
  Sound-event labels over 120 characters are excluded from retrieval text;
  SFX/ambience labels below configurable confidence 0.60 are not indexed as
  searchable sound references. Other speech/music cues use the detector's
  confidence and timestamps. Reanalysis of the supplied fixture confirmed
  HTS-AT's live output as two broad labels (Speech, Music), not hundreds of
  low-confidence SFX labels.
- Corpus search deduplicates repeated analyses by source video and clip ID,
  preferring the newest completed run, so a repository with repeated reruns
  does not fill the first result page with duplicate copies of the same clip.
- Safe reindexing writes to `corpus_index_v2/` and leaves original run
  manifests and `runs/*/index/` files intact. The reindex script skips an
  existing destination unless `--replace` is explicit.
- Tests cover cross-run aggregation, pagination, duplicate record IDs,
  deduplicating repeated analyses of the same source video, scene-only
  embeddings, filtering unreliable/unbounded sound labels,
  filtering non-PE-AV semantic rows, withholding semantic results without a
  real PE-AV query vector, keyword availability in fallback runs, and the API
  handler's run-root/result metadata contract. CLAP preservation is checked
  for exact record/dimension matches, and semantic PE-AV search rejects
  CLAP-only records. `pytest.ini` scopes plain
  `pytest` runs to analyzer-owned tests so test collection does not recurse
  into upstream PE-AV vendor tests.
- Verification in this phase: `PYTHONPATH=src pytest -q` reports 46 passed,
  1 skipped; Python compilation passes. Safe reindexing created 14 new
  corpus-index entries without changing the historical per-run indexes and
  preserved compatible CLAP vectors from 12 legacy indexes. A real PE-AV
  text query through the isolated GPU worker searched 14 analysis runs,
  deduplicated them to one source video/scene, and returned exactly one
  timestamped `scene_clip` result (no zero-score CLAP-only rows). The API/UI is not yet wired into Story
  Builder; website Playwright regression remains part of the next integration
  phase.
- This API is analyzer-ready but is **not yet connected to the Story Builder
  search box**. Website integration remains a separate reversible phase after
  analyzer acceptance and Playwright regression testing.

### 20.16 Latest analyzer validation and SAM Large TV status (2026-09-27)

This section supersedes earlier status notes that described the SAM Audio
checkpoint as absent. The owner has staged `facebook/sam-audio-large-tv` at
`video_audio_analyzer/models/sam-audio-large-tv/`, with the local T5-Base
support files. The isolated SAM worker is already built and running in this
analyzer's Compose project; do not download weights automatically or modify
the ComfyUI/other Docker images.

An opt-in full dummy analysis completed in a fresh validation-only project and
Voice Store. It produced timestamped speech audio, a 192D SpeechBrain ECAPA
embedding, UUID-backed anonymous character/voice IDs, and Codex `gpt-6-luna`
identity/track audit decisions. No identity was merged from similarity alone.
The detector returned broad Speech and Music events; this very short fixture
did not establish named SFX coverage. Cross-project voice retrieval remains
supported by the existing bounded Voice Store ANN path/tests but does not
block this analyzer release; persistent cross-video face identity remains
deferred pending a suitable model/checkpoint license choice.

The isolated PE-AV query service was built without adding FastAPI/Uvicorn or
changing dependencies: it uses a standard-library HTTP server in the existing
PE-AV image. A real query against 14 persisted analysis runs returned the one
deduplicated scene clip for this source video. New indexes are stored in
`video_audio_analyzer/corpus_index_v2/`; all historical run manifests and
`runs/*/index/` artifacts remain untouched. Verification is `44 passed,
1 skipped`, source compilation passed, and the Docker Compose profile was
validated. The PE-AV query worker remains running to serve the analyzer API.

The remaining planned phase is Story Builder integration: replace the
Video Summariser backend behind a reversible switch, add the audio controls /
voice, music, SFX, ambience and stems library UI, connect corpus semantic
search, and perform the full Playwright regression. No website files were
changed in this analyzer phase.

### 20.17 Live SAM, Voice Store, and reindexed-search gate (2026-09-27)

- Verified the already-running `sam-audio-worker` from Docker status/logs;
  did not restart/rebuild it or change any package. Its health response
  identified the staged `facebook/sam-audio-large-tv` checkpoint and local
  T5-Base support files and reported CUDA ready.
- Ran real text-and-time isolation on the supplied dummy's 8.731-second
  `analysis.wav` with the prompt `music`. The worker returned a valid,
  non-empty 48 kHz preview with run/event/time provenance. Explicit
  `save_to_repertoire` copied it to a disposable `/tmp` test repertoire, then
  `expire_preview` removed the temporary preview. The isolated saved output is
  available at `/tmp/vaa-sam-live-check-dsrlfbcd/test-repertoire/audio/isolated/`;
  the copy is retained only as a test artifact and is not in the production
  repertoire. This verifies inference and lifecycle, not subjective separation
  quality; a listener/quality benchmark remains appropriate before production
  use.
- Cross-project voice lookup was exercised against the real 192D ECAPA
  centroid created by the opt-in dummy run, using a different project ID.
  The global Voice Store returned the source identity at cosine similarity
  1.0 as a candidate. No identity link/merge was created. Voice candidate
  selection remains project-first, then global top-K; the JSONL fallback
  scans centroids and avoids pairwise comparison of raw examples. A bounded
  temporary-database smoke test in the pinned analyzer container verified
  both project-local and global LanceDB ANN candidate retrieval. The host
  pytest version of that test remains skipped unless run in that runtime.
- Reindex migration now retains valid legacy 512D CLAP vectors on matching
  frame/audio-event IDs and reports the count/dimension. PE-AV and CLAP remain
  separate. An additional retrieval guard prevents CLAP-only items from
  appearing as zero-score results for a PE-AV semantic query.
- Reindexed all 14 historical runs into the separate `corpus_index_v2/`
  tree; historical run manifests and `runs/*/index/` were not edited. The
  actual GPU-backed PE-AV search now returns exactly one deduplicated
  `scene_clip` for the supplied source video. Analyzer tests: `46 passed,
  1 skipped`; Python compilation and reindex passed.
- Remaining analyzer limitations are explicit: the supplied short dummy
  contains no confidently named SFX, so it cannot establish broad SFX recall;
  cross-video face/body identity remains unimplemented until a suitably
  licensed checkpoint/backend is selected; and the actual Story Builder
  UI/API replacement plus Playwright regression is the next phase. No Story
  Builder website files were modified in this analyzer-only phase.

### 20.18 Story Builder analyzer integration and end-to-end verification (2026-09-27)

This section supersedes the earlier “not yet wired” / “next phase is
integration” statements in 20.14–20.17. The Story Builder integration is now
implemented as an additive, reversible connection; it does not remove or
replace the established library, YouTube download, visual scene/frame
analysis, frame-shaving controls, timestamps, or curated-reference workflow.

- Existing `/video-summariser` and `/video-repertoire` routes remain on the
  same page. The Analyze tab retains its visual-analysis settings and adds the
  independent audio-analysis and opt-in voice/music/SFX collection controls.
  Source-bitstream preservation and MP3 preview extraction are separate ON-by-
  default toggles; the model-processing `analysis.wav` remains available even
  when either export is disabled. Analyzer frame shaving is now connected
  separately from the legacy visual frame-shaving control: sampled frames are
  reduced using a configurable normalized visual-change threshold, optional
  first/last scene anchors, and optional retention of temporary decoded
  samples. Disabling shaving retains all samples at the selected FPS (not every
  source frame). These values are passed through the job worker and recorded
  in the analyzer manifest.
  Results retain the legacy visual report and display analyzer audio preview,
  timestamped events, transcript/diarization/embedding statuses, collected
  media assets, and the temporary SAM isolation → Codex review → save/discard
  workflow. Analyzer-selected frame cards are also shown with their timestamp,
  measured change score, camera/lighting evidence, and uncertainty notes; they
  are additive and do not replace the legacy visual report. The Audio Assets
  tab continues to list only explicitly collected or approved reusable media
  in `video_repertoire`.
- Added `services/video_audio_search.py` and
  `POST /api/video-audio-analyzer/search`, which adapt the analyzer's existing
  corpus-wide `/api/search/all` logic to the Story Builder API. The existing
  “Find reusable clips” card now defaults to the video+audio analyzer corpus;
  the original curated video-reference index remains selectable. Semantic,
  word-similarity, and hybrid modes are retained with a configurable 1–50
  top-hits-per-page control and offset pagination. Analyzer results paginate,
  show run/source/timestamp metadata, play audio-event intervals with source
  context, and play timestamped scene clips or frames. API output strips
  embedding vectors and internal container filesystem paths; artifact URLs
  are validated run-relative paths. If the PE-AV query worker is unavailable,
  keyword retrieval remains usable and semantic retrieval returns the
  analyzer's explicit “no real embedding” result rather than fabricated
  semantic matches.
- Analysis continues through the established persistent Story Builder job
  lifecycle. Audio analysis settings are snapshotted into the job; progress,
  cancellation/retry, result history, and old visual results remain in the
  existing job UI. Analyzer failures are displayed beside successful visual
  output instead of silently failing the whole page.
- Full dummy comparison used the same registered source
  `Brother eww what’s that？💀 #meme.mp4` (8.73 seconds). Both paths reported one
  cut-defined scene. The legacy report included an unwanted “thinking
  process” trace and repetitive narrative; the new analyzer produced a
  concise structural manifest, synchronized transcript/audio, and indexed
  scene/frame/audio evidence. Its event detector reported broad speech/music
  activity, not a confidently named sound effect. This is an honest
  improvement in reusable media indexing, not a claim that the analyzer's
  generated narrative is already director-grade or that sound-event recall is
  comprehensive. The legacy visual report remains visible and unchanged.
- Live search verification: Story Builder called the isolated PE-AV query
  worker with `facebook/pe-av-base` and returned a timestamped
  `scene_clip` hit linked to the registered source video. The running isolated
  workers were inspected, not rebuilt/restarted: PE-AV health reported the
  checkpoint ready and CUDA available; SAM health reported the Large TV
  checkpoint and T5 support files present and CUDA available.
- A timestamped compressed backup of the relevant pre-integration frontend,
  API, service, and launch files is retained outside the repo at
  `/tmp/story-builder-video-analyzer-ui-backup-20260927T170311Z.tar.gz`.
  It includes frontend source, package/lock files, API and video-repertoire
  services, Vite config, and launcher. Restore from the repository root with
  `tar -xzf /tmp/story-builder-video-analyzer-ui-backup-20260927T170311Z.tar.gz`.
  It is a rollback snapshot, not a media/data backup.
- Verification after integration: Story Builder targeted backend tests
  `17 passed`; analyzer tests `50 passed, 1 skipped`; frontend Vitest `1
  passed`; TypeScript `tsc --noEmit` passed; production Vite build passed.
  Playwright verified analyzer keyword search and live PE-AV semantic search,
  audio-event playback and source-video context, scene clip playback, audio
  library, original registered-video library, zero failed requests/browser
  errors, and no horizontal overflow at a 390px viewport. The temporary Story
  Builder test services were stopped afterward; the analyzer PE-AV/SAM/TalkNet/
  audio containers were left running and untouched.
- The checked-in Video Repertoire Playwright regression was refreshed for the
  current tabs and controls and passed `3/3` tests on the disposable test
  instance, including the analyzer-selected frame evidence card's camera,
  lighting, and uncertainty display. It did not start analysis, download
  media, or import library assets.
- Still deferred/limited: no cross-video face/body ReID checkpoint has been
  selected because code and checkpoint licenses must be separately verified;
  voice-based local/global identity matching remains available independently.
  The frame-shaving selector currently uses normalized sampled-frame pixel
  change plus scene anchors; camera-motion compensation and semantic
  action-aware frame scoring remain a later quality upgrade, not something the
  current UI implies is already solved.
  The short supplied dummy cannot validate broad named-SFX recall or subjective
  SAM separation quality. These do not block the integrated analyzer/search
  flow; representative labelled sound-effect material is useful for a future
  quality benchmark. No mandatory manual setup remains for the current
  integrated UI and semantic search path.

### 20.19 Authoritative direct-video summarization correction (2026-09-28)

This is the newest product/implementation decision and supersedes earlier
sections that call InternVideo optional, describe the frame/Image Detailer
report as the intended primary output, or treat the additive legacy visual
report as completion of analyzer replacement.

- **Primary video summarizer:** official-documented
  `yanziang/InternVideo3-8B-Instruct`, from the OpenGVLab InternVideo3 project.
  The complete Hugging Face snapshot was downloaded and verified on
  2026-09-28; inference/runtime integration is still outstanding.
- **Required manual staging location:**
  `/home/riki/web_dev/story_builder/video_audio_analyzer/models/internvideo3-8b-instruct/`.
  Download the entire Hub snapshot, not just one shard and not the whole GitHub
  training repository. The verified local snapshot is 18,740,559,396 bytes
  (91 files; all 7 shards referenced by `model.safetensors.index.json` present;
  no `.incomplete` downloads) at the required path. Hugging Face metadata
  records revision `c4602918b65225650d152db2850fe34e01d21fcd`. Keep this pinned
  revision and model-code provenance; load it only inside the isolated analyzer
  worker.
- **Summary sequence:** direct video-path analysis per existing timestamped
  clip → chronological full-video synthesis from compact clip drafts plus
  transcript/speaker/audio-event timeline → one bounded backward refinement
  pass over clip text using the full-video summary and local/neighbor evidence.
  A short-video full-source-first variant is allowed only after measured
  duration/context limits. This is not a repeated agent loop.
- **Clip text record:** must include clip-level visual/action summary, relevant
  multilingual timed transcript segments, timestamped speaker/voice tags,
  music/SFX/ambience event descriptions and confidence/provenance, and the
  whole-video context reference. Original synced video/audio remains playable.
  Isolated/reusable audio assets remain controlled by their category toggles.
- **Embeddings:** PE-AV remains the vector encoder, never the summary writer.
  For each clip, index linked video and refined-text records (including
  transcript and sound semantics); audio and joint AV vectors are separately
  represented when enabled. Index the full-video summary as its own text
  record. Keep CLAP separate and use documented late fusion; all vectors map
  to stable video/scene/clip/time metadata.
- **Frames:** preserve scene/cut detection, clip extraction, frame-shaving
  controls, and timestamps. Do not persist every sampled frame or run a VLM
  over frames one at a time. InternVideo3 samples from video internally;
  support-tool samples/thumbnails are transient or selectively retained and
  cleaned. No persistent frame gallery is required for the core workflow.
- **Audio/video alignment:** do not assume InternVideo3's documented video
  input path analyzes the soundtrack. ASR, diarization, and audio-event
  analysis run on their own audio worker in parallel, retaining source
  timestamps. The application joins those outputs to clips by interval and
  supplies the compact records to synthesis/refinement. Summaries must not
  claim an event was heard or isolated unless the corresponding audio stage
  provides that evidence.
- **Runtime/acceptance:** the isolated `video-caption-worker` must preflight
  Python, Transformers, PyTorch/CUDA, architecture, video decoding, VRAM/RAM,
  licensing, shipped custom model code, and PE-AV coexistence. Official
  quickstart dependency versions are a starting point, not permission to
  mutate another Docker/Conda environment. Benchmark cold load, throughput per
  video minute, peak memory, factual/chronological quality, audio/transcript
  fusion, and indexing on the supplied 8.73-second meme plus a longer clip.
  Do not promise that it is faster until measured. The current 20.18 website
  connection is additive and still retains the legacy report; actual backend
  replacement, result UI updates, end-to-end comparison, and Playwright
  regression remain outstanding gates.

The checkpoint download is complete. No InternVideo-specific packages were
installed and no Docker/ComfyUI/shared-Conda changes were made for this
download. Remaining before real inference: inspect and pin the custom model
code; build/preflight the isolated caption worker; run a direct-video smoke
test and resource/quality benchmark; then implement the clip-first summaries,
PE-AV linked-vector indexing, result UI, and reversible website cutover. No
manual model download remains.

### 20.20 Job Stop/Delete behavior (2026-09-28)

The Video Summariser/Analyzer UI must expose **Stop** for queued or running
analysis jobs and **Delete** for active or historical jobs. Stop means cancel
the worker, wait until it cannot write, then discard and remove that job and
its job-owned partial outputs; it is not a hidden pause. Delete removes the
selected job record and all exclusively job-owned derived files/assets/index
rows. Both actions preserve the registered source video. Shared/referenced
repertoire assets are not deleted underneath another project; the UI explains
the protection. Backend ownership/path validation and idempotent cleanup are
mandatory, and the UI confirms completion only after the backend reports the
final cleanup state.

Resume is optional: offer it only if a validated completed-stage checkpoint
can be reused without retaining duplicate run outputs. Otherwise stopping
cleans the run and the user restarts from the original registered source.
Playwright and backend tests must cover cancellation races, service restart,
cleanup failures/retry, concurrent tabs, source/shared-asset protection, and
the Resume-or-Restart result. This requirement applies to the analyzer job
surface without removing or altering other Story Builder job workflows.

### 20.21 Stop/Delete implementation update (2026-09-28)

The current website implementation now exposes analysis-job **Stop & delete**
and **Delete** actions in Analyze, plus Delete beside Results history. Stop
sends SIGTERM to the job's process group, waits up to a bounded grace period,
then escalates to SIGKILL if needed; if the worker still cannot be confirmed
stopped, cleanup is withheld and the API reports an error. Job IDs and resolved
paths are validated server-side. Cleanup removes the job folder/logs/copied
inputs, per-job legacy analysis directory, job-prefixed scene clips, and
analyzer run directories that carry the matching job-owner marker. It removes
the job ID from source-manifest bookkeeping while preserving original source
videos and explicitly reusable/shared media. Video Repertoire downloader
controls remain unchanged.

The UI uses confirmation prompts and only removes jobs from its visible list
after the backend succeeds. There is no pause/resume checkpoint: after Stop,
restart means starting a new analysis from the preserved source. Backend tests
and mocked-API Playwright tests cover private-output cleanup, source/shared
asset protection, and both button requests. Broader failure/retry and
multi-tab cancellation-race tests remain in the plan before declaring this
destructive workflow production-complete.

### 20.22 Direct-video implementation and validation update (2026-09-28)

The authoritative direct-video path from 20.19 has now been implemented and
exercised end to end on the supplied 8.73-second dummy video. The Video
Summariser analysis worker now defaults to the isolated InternVideo3 + PE-AV
path; the legacy worker remains an explicit rollback option and is not the
primary path. The Story Builder UI consumes the direct full-video summary,
refined timestamped clip summaries, transcript segments, and time-aligned
audio-event cues. PE-AV video/audio vectors and text-summary vectors remain
separate, versioned fields; full-video text has its own searchable record.

The direct route preserves source video, scene/cut timestamps, and clip
playback, while not persisting sampled JPEGs or invoking per-frame visual
captioning. Timestamp-only frame sampling remains available for scene/change
analysis. Audio stages remain independently controllable. The copied run
artifacts and promoted reusable media are stored under `video_repertoire/`;
the legacy `video_summariser/` code path is not used by default for analysis.

Validation on the supplied dummy produced a coherent direct InternVideo3
full-video summary and clip summary, linked the available timed Whisper
transcript and broad speech/music detections, and created PE-AV Base 1024-D
video/audio and separate text embeddings. The direct route persisted no
selected-frame JPEGs. The short input produced no named sound-effect event;
that is a coverage limitation, not evidence that sound effects are never
detected. Hardware AV1 decoding warnings fell back successfully to software
decoding. This validates functionality, not a speed improvement: measured
model inference and synthesis/refinement took about 10.2 s and 42.2 s
respectively, excluding the substantial cold model-load cost. A persistent
warm worker or later batching is needed before claiming faster throughput.

The corpus currently supports truthful exact JSONL vector scans. The local
LanceDB table writer is not the active corpus retrieval backend, and the PE-AV
text-query service must be running for semantic query vectors; keyword search
continues when it is offline. The UI reports this state instead of claiming
semantic search is ready. Audio diarization/Voice Store matching and SAM Audio
isolation remain optional/unavailable when their separately gated workers or
models are not ready.

Verification on 2026-09-28: analyzer/backend suite passed (56 passed, 2
skipped); frontend production build passed; Video Repertoire Playwright suite
passed (6 passed) on an isolated test server. Only the isolated test server
was stopped; the pre-existing Story Builder listeners were left untouched.
The build emitted existing non-fatal Vite `__dirname` and large-chunk
warnings. Before relying on semantic search in the live UI, start the
analyzer-owned PE-AV query worker and verify its health endpoint on port 8034.
ComfyUI and Ollama are not required by this direct video-analysis path.

### 20.23 Motion-aware shaving and output-path hardening (2026-09-28)

Frame-shaving now estimates coherent global affine camera movement between
low-resolution grayscale samples using OpenCV ECC alignment. It scores the
residual visual change after alignment, while recording a separate normalized
camera-motion score. If alignment confidence or scale bounds fail (including
hard cuts), it safely falls back to raw visual difference and does not label
the pair as camera motion. The existing configurable visual-change threshold,
scene anchors, sampled-FPS semantics, and transient-image cleanup are
preserved. The direct path still stores timestamps/measurements only, not the
sample JPEGs. Results can show timestamp-only support samples and their two
scores without constructing broken image URLs.

The analyzer launcher's preflight report now targets
`video_repertoire/manifests/preflight.json`, and the analyzer container gets a
dedicated writable mount for that shared repertoire location rather than
mounting the analyzer code tree's `manifests/` folder as mutable output. The
SAM gated/unavailable API test now uses a temporary isolated run fixture rather
than depending on the removed legacy `video_audio_analyzer/runs/` dummy
output, so that regression is always exercised after user data cleanup.

Validation after these changes: all project analyzer/backend tests passed
(64 passed, 1 skipped for the documented pinned-runtime LanceDB check); the
frontend build passed; and the six Video Repertoire Playwright tests passed,
including the camera-motion score and timestamp-only card. The supplied dummy
also runs through the pipeline scene-sampling test and software-decoding
fallback. The independent PE-AV/NeMo/SAM/TalkNet workers are currently stopped,
so live semantic-query and optional model-inference gates still require those
project containers to be started and health-checked before they can be called
fully validated in the current session.
The original Story Builder backend on port 3011 was started before the latest
backend edits and does not run with Uvicorn reload; its live capabilities
response is still the older Ollama/legacy shape. Restart Story Builder before
using the updated route. The isolated Playwright server on 3012/8084 was
stopped after the regression suite; the original 3011/8082 services were left
untouched.
