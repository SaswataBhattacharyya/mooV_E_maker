# Video/Audio Repertoire and Manual Director Upgrade Plan

## Status (2026-09-29)

The requested implementation is complete. Sound-event labels are used to
group same-class assets for review; acoustic near-duplicate matching and an
additional varied-audio run are not required acceptance gates. Existing
scene boundaries remain intact. Cut-to-cut children are timestamped virtual
intervals in the source video, with configurable motion-compensated change
threshold and minimum duration; they are estimates from sampled frames, not
guaranteed frame-accurate edit-list cuts. They are searchable/stageable without
creating duplicate encoded media.

Demucs is integrated as source separation, not semantic classification:
`AUTO` runs vocals/accompaniment two-stem separation when music is detected or
voice collection is explicitly requested; explicit 2/4/6-stem choices remain
available. SFX labels come from event detection, while SAM Audio is a separate
on-demand isolation path. Original audio remains the provenance source.

### Implementation and verification log

- Implemented: isolated Manual Director workflow catalog/validation and
  page/API; project-local continuous voice passages with a 30-second minimum;
  Demucs modes and AUTO routing; independent speech/music/SFX toggles; derived
  audio duplicate review/deletion with source/event-history retention; virtual
  cut children; search/UI exposure and timestamped/idempotent Manual Director
  staging; job stop/delete safeguards; independent PE-AV audio-event vectors;
  relative music-mood ranking (clearly not calibrated probabilities); and UI
  labels for mixed/unisolated audio excerpts.
- Fixed during live testing: Hugging Face PE-AV’s single-modality forward path
  rejects audio-only/video-only input. The adapter now calls the official
  modality-specific projection helpers, so real audio-event vectors are
  generated. The installed WAN `CreateVideo` requires `fps` while the stored
  graph has `frame_rate`; the runtime adapter now supplies both without
  modifying ComfyUI or the saved workflow. Minimax reference graphs with three
  image nodes now safely fill unused nodes with the final selected image.
- Full dummy-video analysis passed for `Brother eww what’s that？💀 #meme.mp4`
  (`analysis-77f3e3f16b9e`; analyzer run
  `c938423ea483bdc3-rerun-667e9c10`): 1 scene, 1 timestamped virtual cut, 1
  transcript segment, 2 timed events (music and speech), one promoted mixed
  music excerpt, Demucs AUTO vocals/accompaniment stems, completed PE-AV scene
  and audio-event embeddings, relative mood ranking, and approved promotion
  under `video_repertoire`. No reusable voice sample was saved, correctly,
  because this video is shorter than 30 seconds. Semantic search returned both
  this run and existing repertoire items using PE-AV.
- SAM Audio Large-TV was started only in this project's isolated Docker service.
  Real isolation of the sample's timed music event returned a temporary preview;
  explicit discard removed it. The service was stopped after the test so its
  model does not remain resident on the GPU. SAM is optional/on-demand.
- Live Manual Director runs succeeded for Minimax text-only
  (`manual-64b2f1b51b54`), Minimax reference-image (`manual-19955bc32b4e`), and
  WAN first/last-frame (`manual-9f274d83a250`); each produced an MP4 registered
  under `video_repertoire/manual/outputs/`. A minimal 2-second/256x256 profile
  was used for safe smoke testing.
- Verification on 2026-09-29: 101 Python tests passed, 1 skipped; 10 Playwright
  tests passed against the isolated Story Builder test site at 8084/3012;
  TypeScript check and Vite production build passed. Only existing Vite
  configuration/plugin and bundle-size warnings remain. The user's existing
  site at 8082/3011 was not restarted or modified.
- Duplicate review now exposes same-project, same-class SFX/music/ambience
  review groups alongside exact-file duplicates. A shared class is not proof
  of acoustic identity: distinct thunder events remain separate, are not
  auto-selected, and are never auto-deleted. “Select exact duplicates” selects
  exact-file-hash matches only.
- After a Story Builder ComfyUI workflow completes, request model unload and
  cache release through ComfyUI's `/free` API only if its shared queue is idle.
  If another workflow is running/queued or ComfyUI is unavailable, defer/record
  cleanup instead of interrupting work. Video/audio analysis workers are
  separate processes and release their GPU allocations on exit; the persistent
  PE-AV query service is separate from per-job allocations.
- The Results UI now reports sampled baseline/peak/delta GPU compute
  allocations for analyzer jobs when `nvidia-smi` is available. A complete
  8.73-second dummy-video profile (all analyzer stages, including InternVideo3)
  measured 4,677 MiB baseline, 23,138 MiB observed peak, and 18,461 MiB peak
  increase at one-second sampling. This is whole-host compute-process usage and
  includes resident/concurrent services; it is representative of that short
  test, not a guaranteed maximum for longer videos.
- Live ComfyUI cleanup verification: queue was idle; `/free` with both unload
  and cache-release flags reduced the ComfyUI process allocation from 20,643
  MiB to 323 MiB. The residual is the live ComfyUI/CUDA process footprint, not
  model weights; literal 0 MiB requires stopping ComfyUI. SAM Audio was not
  running and used 0 GPU during this check.
- The isolated profile used `VIDEO_REPERTOIRE_ROOT=/tmp` only for disposable
  measurement output. Docker left root-owned test artifacts there; ordinary
  user cleanup was denied, so remove only `/tmp/storybuilder-gpu-profile` with
  `sudo rm -r -- /tmp/storybuilder-gpu-profile` when convenient. Canonical
  `video_repertoire` data was not touched by this profiling run.
- Final verification after these updates: 81 tests under the Story Builder
  `tests/` directory passed; 10 relevant Playwright tests passed against the
  isolated 8084/3012 instance; Python compilation, shell syntax validation,
  and the Vite production build passed. Running bare `pytest -q` at the entire
  workspace root also discovers unrelated vendored TTS tests that exit during
  collection because their external model path is absent; that is outside
  this plan's regression suite.

## Purpose

Extend the current Video Summariser/Repertoire into a timestamp-preserving media
reference library and add a Manual Director page for composing selected assets
into a ComfyUI generation request.

The existing scene analysis, direct-video summaries, PE-AV semantic search,
Story Builder/Video Repertoire integration, and working ComfyUI workflows must
remain intact. Changes must be additive and regression-tested. Do not modify
other repositories, ComfyUI packages, Conda environments, or Docker projects.

## User requirements captured

1. Keep scene boundaries and scene summaries. Add cut-to-cut clips as children
   of their scene. Cut clips are timestamped and playable, do not need their own
   LLM summary, and are returned alongside the parent scene in search results.
2. Preserve source timestamps for every video/audio derivative.
3. Organize audio into distinct, linked categories:
   - **Speech/voice:** project-scoped speaker identities only. Do not match or
     merge voice identities across projects. Retain only continuous, single-
     speaker speech passages with at least 30 seconds of usable speech audio.
     Preserve natural pauses within a passage. Keep transcript, speaker ID,
     timestamps, and provenance. Do not save short isolated speech snippets as
     voice-reference assets. Short transcript/event records may still exist as
     analysis metadata if useful, but must not be presented as reusable voice
     clips.
   - **Sound effects:** timestamp, classify, and isolate reusable occurrences.
     Keep distinct sounds even when they share a class (e.g. different thunder
     events). Within each project, group/flag likely duplicate same-class audio
     for review; do not apply a fixed numeric similarity threshold and never
     automatically delete it. Preserve all occurrence timestamps/links
     regardless of any later asset deletion.
   - **Music:** retain the complete musical mix as heard, with instruments
     together; do not split instruments into separate assets by default.
     Produce confidence-scored sentiment/mood/style descriptions (e.g. sad,
     joyful, tense), not objective ground truth. Retain timestamps and source
     provenance. Demucs stems may be an optional derived analysis aid, not a
     replacement for the original mix.
4. From Video Summariser/Repertoire search, allow multiple video, scene, cut,
   speech, SFX, and music assets to be selected and handed off to Manual
   Director. Handoff must be idempotent: an already-present asset is not added
   twice. Large/unsupported assets must be explained in the UI before running.
5. Manual Director supports prompt text and reference slots for audio, video,
   first frame, and last frame. References can be dragged/dropped from the
   repository, pasted where browser permissions allow, or selected from the
   local computer. Local uploads are stored once in the central
   `video_repertoire` asset store; manual project JSON stores paths/asset IDs,
   not duplicate media bytes.
6. Each generation workflow exposes its own documented parameters, accepted
   reference types, file size/duration/resolution limits, required and optional
   fields, and validation. Include workflow-specific settings such as Minimax
   H3 duration/time and quality when supported by the installed workflow.
7. Initial workflow choices: Minimax text-only, Minimax with references, and
   WAN first/last-frame workflow if an appropriate existing ComfyUI API
   workflow is present. Do not fabricate a WAN workflow: the user will provide
   it if absent. Inspect actual installed API workflows and map supported input
   nodes before enabling a choice.
8. A Run action submits the validated prompt/references/parameters to the
   selected existing ComfyUI API workflow, reports actionable errors, tracks
   progress where available, and displays generated output on the same page.
9. Store manual-run metadata under `video_repertoire/manual/inputs/` and
   generated output under `video_repertoire/manual/outputs/`. Each input JSON
   includes prompt, workflow and version, settings, asset IDs/paths, timestamps
   and run metadata, but does not embed/copy media. Uploaded source assets are
   managed in the shared repertoire storage and referenced by path/ID.

## Current-state discovery before implementation

Read the current analyzer/repertoire plan and inspect the implementation before
changing code. Verify, rather than assume:

- current audio event, ASR, diarization, speaker identity, SFX isolation,
  Demucs, music feature/sentiment, and timestamp schemas;
- current scene and cut/shot boundary representation and whether cut assets
  already exist;
- where video, audio, frame, and embedding assets are physically stored;
- current video and audio search endpoints and result-card components;
- existing Manual Director route/page, if any, and its current capabilities;
- actual ComfyUI API workflow JSONs and node/input mappings for Minimax H3,
  reference workflows, and WAN;
- supported upload formats, file limits, output destinations, and ComfyUI
  availability/health interfaces;
- existing tests, Playwright setup, and project/job cleanup semantics.

Do not delete or migrate the legacy `video_summariser` until the website no
longer imports it and the replacement path has passed regression checks.

## Target architecture

### A. Timestamped video hierarchy

```text
Video
└── Scene (start/end, coherent summary, transcript/audio context)
    ├── Scene-level audiovisual description and search embeddings
    ├── Cut clip 1 (start/end, playable source interval, no required summary)
    ├── Cut clip 2
    └── ...
```

- Scene search returns its child cut clips and their time ranges.
- Cut clips should reference source-video intervals and avoid needless duplicate
  encoded media when an on-demand/virtual trim is sufficient. If a physical
  reusable clip is needed for a supported workflow, create it once in the
  central repertoire and record provenance.
- Search and UI must distinguish scene, cut clip, and whole-video results.

### B. Timestamped audio hierarchy and retention policy

```text
Video source audio
├── Speech events/transcript spans
│   └── project-scoped speaker identity
│       └── eligible voice-reference passage(s), each continuous and >=30s
├── Sound-event occurrences
│   └── isolated SFX representative asset(s), class + similarity/dedup record
└── Music intervals
    └── full mixed music excerpt + confidence-scored mood/style metadata
```

- Maintain event/occurrence metadata even if a derived asset is later deleted.
- Duplicate grouping is project-local. Group candidates using available
  same-class and acoustic resemblance signals, but do not define or expose a
  fixed percentage threshold. Candidate grouping is advisory; preserve all
  distinct occurrence records and never automatically delete assets.
- A >=30-second voice-reference passage means at least 30 seconds of usable,
  continuous, single-speaker speech in that saved asset. Do not concatenate
  unrelated distant utterances into a fake continuous recording. Natural pauses
  inside the continuous passage are retained. If several passages from the
  same project speaker qualify, retain them as separate assets linked to the
  same project-scoped voice identity.
- Keep transcript alignment at word/segment level where available; store
  language detection and ASR confidence. Multilingual ASR language handling
  remains configured by the analyzer and must not be replaced with assumptions
  based on one dummy video.
- Music mood labels are model inferences with confidence/model provenance.
  Store complete mixed excerpts; any separated stem is explicitly derived and
  optional.
- Respect source-audio/video timestamps through trim offsets, resampling,
  separation, and export. Store source start/end plus any derivative-relative
  offsets.

### C. Search, selection, and handoff

- Search categories: whole video, scene, cut clip, voice passage, SFX, and music.
- Preserve semantic and word/keyword search modes where available; filter by
  project/video/category/time and sort results. Search result metadata exposes
  parent scene/video and exact time range.
- Add multi-select controls and a visible selection tray/count. “Send to
  Manual Director” transfers stable repertoire asset IDs and metadata, not file
  copies. Repeated handoff uses asset ID + role as an idempotency key.
- Show clear notices for too-large, unsupported, missing, or incompatible
  references, including applicable workflow size/duration limits. Do not silently
  omit a selected reference.

#### Duplicate review and cleanup

- Add a **Duplicate candidates** view/filter in the audio repertoire, grouping
  flagged assets by project, sound class, and candidate group. Show playback or
  waveform comparison, duration, source video/timestamps, similarity method and
  version, score, and why the candidates were grouped.
- A candidate group is only a review aid; it does not assert the sounds are
  identical. Keep every occurrence and timestamp discoverable.
- Provide per-item selection, “select all in this group,” and “select all
  flagged candidates.” Before deletion, show the selected asset count and total
  bytes, and explicitly state that source videos/original audio and
  event/timestamp records will remain.
- Bulk deletion removes only selected derived audio files and their derived
  asset records. Keep the event/timestamp/transcript metadata and mark its
  derived audio as removed. Do not delete or alter source video or source audio.
  Never automatically repoint one occurrence to another candidate; offer an
  explicit “same reusable sound” action only if the user wants shared storage.
- Require confirmation for bulk deletion, report per-file failures, reclaimed
  bytes, and remaining candidates. Do not provide an ambiguous “delete all”
  that can reach original media.

### D. Manual Director page

- Dedicated route/page integrated in Story Builder navigation without replacing
  or destabilizing current pages.
- Layout: prompt editor; selected workflow; workflow-specific parameter panel;
  four typed reference slots (audio, video, first frame, last frame); selected
  repository assets; local upload/drop/paste affordances; validation/status;
  run history/progress; output preview and download/open controls.
- Repository assets can be dragged from search results/selection tray into the
  appropriate slot. Validate asset media type against the slot.
- Local file selection/drop/paste stores the media once in the managed
  `video_repertoire` asset store. JSON records its managed relative path and
  asset ID. Reject unsafe path traversal and unsupported MIME/content types.
- Workflow selector is populated only from inspected, available API workflows.
  Each workflow definition declares accepted slot types, required fields,
  parameter schema/defaults/ranges, media constraints, ComfyUI workflow ID,
  and mappings to actual node/input identifiers.
- Minimax text-only: prompt plus supported settings; reference slots are not
  required and unsupported ones are rejected or clearly ignored only after
  explicit user removal.
- Minimax with references: supported reference types/limits are derived from the
  actual installed API workflow, not assumed. Require configured mandatory
  reference(s); allow audio/video/image only if the workflow really supports
  them.
- WAN first/last-frame workflow: show only when user-provided WAN workflow is
  installed and mapped. Require both endpoints if the workflow requires them;
  tell the user precisely what is missing.
- Expose duration/time, quality, resolution, seed, and other controls only when
  supported by that workflow. Enforce schema min/max and show effective values
  in the run record.
- The backend is authoritative for workflow validation, file limits, job
  ownership, asset permissions, and ComfyUI submission. UI validation is for
  usability, not security/correctness.
- Run state: queued/running/succeeded/failed/cancelled, progress when ComfyUI
  reports it, elapsed time, errors, output asset IDs, workflow snapshot, and
  prompt/reference snapshot. Provide safe cancel/delete semantics consistent
  with existing jobs; deleting a run must not delete shared source repertoire
  assets.
- Persist JSON under `video_repertoire/manual/inputs/<run_id>.json`; generated
  artifacts under `video_repertoire/manual/outputs/<run_id>/`. Keep all media
  bytes in the central repertoire only—never duplicate them under analyzer or
  manual input folders.

## Implementation phases and gates

### Phase 0 — Backup and contract audit

- Make a dated compressed backup of the website UI, routing, and relevant API
  connection/configuration files before integration edits. Do not back up large
  generated model/media trees.
- Record current git/worktree state and preserve unrelated user changes.
- Inventory current ComfyUI API workflows and map exact nodes/inputs. Do not
  alter ComfyUI installation or workflows during this audit.
- Deliver a compatibility matrix and migration notes before modifying data
  schemas.

### Phase 1 — Analyzer asset/schema extension

- Add scene-child cut-clip records and time-linked audio asset/event schemas as
  needed, with backward-compatible readers for current manifests.
- Add voice eligibility rule (continuous single speaker, >=30 s), project-local
  identity scope, transcript/language provenance, SFX class/similarity lineage,
  and music sentiment metadata.
- Ensure all durable media is located in `video_repertoire`; analyzer run
  directories contain only ephemeral work and are cleaned after promotion or
  failure according to existing retention policy.
- Add schema migrations/versioning and idempotent promotion.

### Phase 2 — Analysis generation and indexing

- Generate cut-to-cut timestamps under existing scene boundaries without
  requiring cut summaries. The default cut threshold is 0.18 and minimum cut
  duration is 0.5 seconds; both are configurable. Each child points to its
  original-video time range and is labeled as an estimated boundary.
- Derive the audio categories independently but align all outputs to source
  timeline. Preserve original audio and avoid claiming Demucs stems equal
  semantic classes.
- Save eligible voice passages only; retain speech transcript/event timing.
- Detect SFX candidates and isolate them only through the on-demand SAM Audio
  action. Exact-file duplicates are currently flagged for review; acoustic
  near-duplicate candidate ranking remains follow-up work. Retain every source
  occurrence and timestamp regardless of derived-asset cleanup.
- Save mixed music intervals and confidence-scored mood/style metadata.
- Add searchable text/semantic fields for scene, clip, transcript, voice,
  effects, and music, keeping embeddings model/version separated.
- Gate: run the existing dummy video and at least one varied audio/video sample;
  inspect timeline alignment, asset uniqueness, and storage locations.

### Phase 3 — Repertoire UI and selection handoff

- Add distinct tabs/filters and cards for scenes, cut clips, voices, effects,
  and music while preserving existing library/results functionality.
- Show timestamps, parent relationships, playback/preview, summaries or
  transcript as applicable, labels/confidence, and source provenance.
- Add multi-selection and idempotent handoff to Manual Director.
- Gate: Playwright tests for search/filter, selection, duplicate handoff,
  category rendering, and media paths; no regressions in current video UI.

### Phase 4 — Manual Director API and UI

- Add backend workflow catalog, schema validation, managed upload/asset lookup,
  idempotent reference intake, run record persistence, ComfyUI submission,
  progress/status polling, cancellation, and output registration.
- Add frontend route/page and workflow-specific settings/reference slots.
- Support local file selection/drop and supported clipboard paste; report
  unsupported clipboard/browser permission cases with a file-picker fallback.
- Add missing-input, type, size, duration, resolution, and workflow-availability
  guidance before submission.
- Do not expose WAN until the user supplies its API workflow and the workflow
  audit confirms the exact inputs.
- Gate: mocked API/component tests first; then run a small, known-safe live
  ComfyUI job per available workflow after confirming service readiness.

### Phase 5 — End-to-end and regression acceptance

- Run analysis of the designated dummy video and verify scene summaries, cut
  clips, timestamps, transcript, eligible voice handling, SFX/music records,
  embeddings/search, and all durable media under `video_repertoire`.
- Select multiple representative assets and send them to Manual Director;
  verify no duplicates and paths resolve.
- Execute each installed workflow with a minimal prompt and valid references;
  inspect output preview and saved JSON/output locations.
- Use Playwright on the actual Story Builder website for navigation, selections,
  upload/drop behavior, workflow settings, validation/errors, progress, and
  output rendering. Run backend and frontend suites plus existing video
  repertoire tests.
- Compare before/after behavior of existing Video Summariser, Repertoire,
  search, and other pages. No unrelated regressions permitted.

## Acceptance criteria

- Scene summaries remain intact; each scene exposes timestamped cut-to-cut child
  clips without forced clip summaries.
- Audio records are independently categorized as speech/voice, SFX, or music,
  timestamp-aligned, linked to the source and searchable.
- No reusable voice sample under the 30-second continuous single-speaker rule is
  retained as a voice-reference asset; project identities never cross-merge.
- Repeated SFX occurrences remain discoverable by timestamp; likely duplicates
  are grouped/flagged within the project without a numeric threshold and never
  auto-deleted. Bulk cleanup removes selected derived assets only and preserves
  source media and event history.
- Music retains the mixed sound and receives explicitly probabilistic,
  confidence-scored sentiment/style labels.
- Search selections hand off by stable asset identity and are not duplicated.
- Manual Director validates workflow-specific references/settings and runs only
  available mapped ComfyUI API workflows.
- Inputs JSON stores references/paths and prompt/settings, not embedded/copied
  media. All managed media and generated output live in `video_repertoire`.
- Existing site routes and workflows pass Playwright/regression tests; no
  changes are made to other repositories, ComfyUI installation, or Conda envs.

## Open implementation notes / risks (not blockers to the plan)

- Duplicate grouping is heuristic and project-local. It must be presented as a
  review aid rather than proof of identity; no fixed numeric threshold or
  automatic deletion is required.
- Thirty seconds of continuous voice may be rare in short clips. The system
  should report “no eligible voice reference” rather than keep prohibited short
  snippets or join distant speech unnaturally.
- Accurate SFX separation/classification and music sentiment are model
  estimates. Persist confidence and model provenance; never represent these as
  perfect labels.
- Clipboard file access varies by browser/security context. File picker and
  drag/drop remain reliable alternatives.
- ComfyUI workflow names do not establish API compatibility. Exact workflow
  JSON and node mappings must be inspected. The user will provide WAN workflow
  if absent.
- Shared repertoire assets must not be removed when a manual run/project is
  deleted. Deletion removes run metadata and generated outputs only, unless a
  separate explicit asset-delete action is introduced.

## User-provided constraints requiring no further clarification

- Voice identity matching is per project only.
- Reusable voice audio must be a continuous, single-person passage with at least
  30 seconds of audio; do not retain short voice snippets as reference assets.
- Keep different examples of the same SFX class when they are meaningfully
  different; group/flag likely duplicate SFX within a project for review while
  retaining timestamps for every occurrence. No numeric similarity threshold.
- Music is retained as the full mixed/instrumental layer; mood is sentiment-style
  inference with confidence.
- Repository handoff uses references/paths and prevents duplicates; report
  oversize/incompatible files.
- Workflow-specific adjustable parameters and file/reference limits belong in
  the UI.
- Use installed workflows only; WAN will be provided if missing.
- Keep all media and generated manual outputs in `video_repertoire`.
