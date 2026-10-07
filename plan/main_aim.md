# Story Builder — Main Aim and Automation Blueprint

**Date:** 2026-09-17  
**Target engine:** local ComfyUI on `127.0.0.1:3008` (Minimax H3 for video)  
**Director/orchestrator:** Hermes Director with its GLM 5.3 model  
**Escalation/review model:** Codex GPT‑5.6 Luna when Hermes requests deeper planning, debugging, or adjudication  
**Local vision worker:** Ollama Qwen 3.6B (the configured Ollama model ID remains environment-controlled; the current host exposes `qwen3.6:35b`)

## The end goal

Story Builder should turn an approved story into a coherent, timed scene package:

```text
story
  → story analysis and refinement
  → screenplay outline and scene breakdown
  → characters, dialogue, and character voice map
  → timed dialogue, music, ambience, and effects
  → character reference sheets and multi-angle references
  → background and scene-frame candidates
  → director continuity checks and approvals
  → first/last frames + timed audio + motion prompt
  → Minimax H3 video clips
  → scene-level audio/video composition
  → accepted per-scene outputs and final manifest
```

The important distinction is that this is not one unconstrained prompt. Every stage
creates a versioned artifact that becomes the input to the next stage. A later stage
must never silently overwrite an approved earlier artifact.

## Production styles and prompt packs

The production style is selected before an automated run begins. It changes both
direction and analysis; it is not merely a visual theme. Each style is stored as a
versioned, self-contained JSON prompt pack under `prompts/styles/`, including common
stage prompts plus style-specific overrides for story treatment, scene direction,
camera, lighting, image generation, dialogue delivery, music, foley, video motion,
continuity review and final reporting.

Initial style packs:

- `story_film.json` — cinematic narrative, character continuity and dramatic beats.
- `advertisement.json` — product value proposition, brand safety, hook, CTA and short-form pacing.
- `informative.json` — clear explanation, evidence, diagrams, definitions and teaching order.
- `news_report.json` — attribution, chronology, uncertainty, source separation and neutral tone.
- `social_profile.json` — vertical/social pacing, hook, captions, retention beats and platform-safe framing.
- `corporate_pitch.json` — business objective, audience, proof points, executive clarity and presentation polish.

Every pack must declare the same allow-listed stage keys so the backend can validate
it. A style can provide text instructions, image-generation instructions and video
direction instructions. Optional reference images or videos may be attached to a
style run, but references never override explicit story facts or safety constraints.
The selected `style_id` and prompt-pack version are recorded with every artifact and
director decision. Users may create a new style pack later; it must be versioned
rather than mutating an existing run.

## Director coherence contract

Before downstream generation, the director produces one authoritative scene contract.
Hermes may improve or edit the story, scene and dialogue text, but every edit creates
a new revision and must preserve approved facts. The contract controls all outputs:

- story beat and scene-to-scene handoff;
- character intent and emotion;
- camera angle, shot size, lens/framing and movement;
- lighting, palette, atmosphere and tone;
- dialogue wording, delivery, pauses and exact timing;
- music, ambience and sound-effect cues;
- first-frame and last-frame requirements;
- shot duration, derived from the locked audio timeline;
- Minimax motion prompt and allowed changes.

Dialogue, music, foley, frames and video prompts are generated from this same
contract. A downstream stage must report a conflict instead of silently changing it.
Minimax clips should normally be 2–10 seconds; longer scenes are split into linked
shots. Post-generation analysis compares the video against the contract and can
regenerate only the failed shot.

## Automation entry points and run ownership

Automation can start from either of two places:

1. **Story Builder page:** paste a story, choose the production style and options,
   optionally request story detailing, then press **Start automation**.
2. **Automation page:** upload a story/project folder, choose the same style and
   options, optionally request detailing, then press **Start automation**.

The initial story is always the first automation input. Detailing is optional and is
the only difference between the two entry modes; the pipeline after the initial
artifact is identical. Starting a run from one page disables the start action on the
other page for that run. Both pages can pause, resume or cancel the same run. A run
has one durable `run_id`, owner page, style-pack version, input revision and stage
states; navigation must never cancel or reset it.

## Persistent process monitor

The application shell owns one global run monitor rather than individual page-local
job state. It remains mounted while routes change and shows every active process in a
minimizable bottom overlay:

- run/stage name, source page and project;
- progress bar, current step, elapsed time and status;
- pause/resume/cancel controls where supported;
- errors, attention-needed questions and retry actions;
- live GPU/CPU/memory telemetry when available from the local services.

The overlay must not hide page content or the footer. The document layout reserves
bottom space and extends scrolling below the footer while the monitor is expanded.
State is restored from the backend by `run_id` when a page is revisited or the browser
refreshes. WebSocket/SSE updates are preferred, with polling as a fallback. A job
started on Image Detailer, Video Repertoire or any automation page therefore remains
visible and resumable until it finishes, is paused, cancelled or fails.

## Automation projects, resume and style changes

Every automation run is a project with a durable `project_id` and `run_id`. The
canonical project workspace is:

```text
storage/projects/<project_id>/
  input/          # original .txt/.md/.json story and uploaded project files
  revisions/      # immutable story and director revisions
  artifacts/      # generated structured artifacts and reports
  images/ audio/ video/ references/
  graph/          # project-scoped Graphify/Graphiti data, when enabled
  output/         # accepted final scene packages and final manifest
```

Existing legacy output locations must remain readable during migration, but new
automation outputs should be registered in the project workspace and exposed through
the project manifest. A run can be:

- **resumed** from the last completed valid stage with its context, artifacts and
  project graph intact;
- **paused** at a safe stage boundary;
- **reset/stopped**, which preserves the project and artifacts but ends the active run;
- **deleted**, which requires explicit confirmation and removes the selected project
  from input, output, artifacts, media, revisions and graph storage.

The project list shows progress, current stage, start style, current style, status,
created/updated time and last error. Automation provides a multi-select project list,
filters for start style, ending/current style, recent/earliest ordering, **Load**,
**Reset**, **Resume** and confirmed **Delete** actions. Only one project may be loaded
into the active automation workspace at a time; multiple projects may be selected for
deletion. Deletion is a backend transaction with a confirmation token and never runs
from a client-only checkbox.

Each run starts with exactly one style. If the style is changed while a paused or
stopped run is being continued, the user must first press **Continue**; only then is a
dialog shown:

> Continue this project with the new style while preserving its existing context, or
> create a separate project?

Continuing creates a new style revision while retaining the original context and
records both the starting and ending styles. Choosing a separate project forks the
approved input/context into a new project and never mutates the original run. The
dialog must not appear merely because a dropdown changed; it appears on Continue.

## Project-scoped knowledge graph

When enabled, each project receives its own Graphify/Graphiti-compatible graph under
`graph/`. It is never shared blindly between projects. After every successful Ollama
artifact step, the graph is updated with the new artifact version, entities,
relationships, scene timing and provenance. Subsequent Ollama prompts may receive a
compact graph context for continuity, while the project files remain the source of
truth. Graph updates are versioned and resumable; disabling the graph must not block
the normal pipeline.

## GPU telemetry and monitor updates

The global monitor receives GPU/CPU/memory samples from the backend. Approximate host
GPU usage is acceptable when process-level attribution is unavailable. Samples are
emitted after each detected usage change (and periodically while a job is active),
not only when a stage completes. Telemetry is informational and must never be used as
the sole indication that a job succeeded.

## What is already present

| Area | Current reality |
|---|---|
| Project and story persistence | Working project store and project-scoped revisions exist. |
| Story analysis and outline | FastAPI routes call Ollama directly; live analysis and outline have been verified. Hermes will own production-level approval and orchestration. |
| Artifact generation | Story, character, scene, sub-scene, dialogue, and image-job artifact services exist, but are not yet one dependency-aware production run. |
| Workflow catalog | API-format ComfyUI workflows are catalogued and selected through the backend gateway. |
| Qwen image generation | Live text-to-image execution, model validation, polling, and output collection work. |
| Minimax H3 video | Live image-to-video execution and output collection work. |
| Mixed TTS | Character map, timed SRT processing, ComfyUI TTS execution, and output persistence work. |
| Music | ACE-Step generation works. ACE fine-tuning is intentionally outside this aim for now. |
| Audio utilities | Noise cleanup and Demucs runtimes are live; voice repair, voice changer, RVC, emotion, and style jobs have completed live tests. |
| Video Repertoire | Upload, download infrastructure, frame/scene analysis, Ollama summary, clips, and searchable records exist. |
| Output handling | FFmpeg scene muxing and a project output manifest endpoint exist. |
| UI | Story Canvas, Generate, Media, Audio, Music/Sound, Audio Utilities, Video Repertoire, Automation, and Audio Reconstruct pages exist. |
| Tests | Backend regression tests and Playwright route tests pass. |

## What is not yet the complete aim

These are implementation gaps, not user mistakes:

1. **The production coordinator now covers the tested two-scene media path.** It executes the dependency-ordered planning/director chain, Control-Foley, stable reference staging, two Minimax reference-to-video shots with retry metadata, audio timing records, FFmpeg scene muxing, and a durable production manifest. Larger projects and richer audio/approval policies remain follow-up work.
2. **Director artifacts now have a validated structured contract.** The coordinator writes per-shot camera, framing, lighting, palette, tone, emotion, continuity, dialogue, music, foley, first/end-frame, duration, and retry-policy fields; scene execution and review still remain.
3. **Character consistency needs a first-class reference stage.** Character image generation and multi-angle reference selection are not yet connected to every scene prompt.
4. **Scene-frame generation and review need a dedicated stage.** Candidate frames should be generated, compared with the director brief and previous scenes, then accepted or regenerated.
5. **Audio-to-frame timing needs a timeline model.** Dialogue, music, ambience, and effects need absolute start/end times and scene markers before H3 is called.
6. **The director retry loop is not complete.** A failed continuity check must be able to regenerate only the affected prompt/frame/audio/video stage while retaining the approved inputs.
7. **Repertoire references need semantic matching.** Video Repertoire can produce frames/clips/audio, but those references are not yet automatically ranked and attached to a scene brief.
8. **Final composition is implemented for the production runner's scene package.** It muxes each scene video with music and Control-Foley, writes per-scene outputs and a production manifest; dialogue/subtitle/loudness expansion remains.
9. **Human approval surfaces need expansion.** The existing UI has pages and job states, but the production run needs explicit review cards and “approve / regenerate / edit / ask me” actions.
10. **Style prompt packs are implemented for the initial release.** The six initial JSON packs, schema validation, style selector and per-run style/version provenance are now wired.
11. **The shared automation-run coordinator is implemented through the tested two-scene production path.** Story Builder now exposes separate planning and full-production controls; the production API runs stable references, Control-Foley, two distinct Minimax scene shots, timing, mux/export, and manifest generation.
12. **The global process monitor is partially implemented.** The shell now hydrates automation runs across routes with persistent progress and pause/resume controls; broader GPU telemetry and all non-story jobs still need to be unified.
13. **Project lifecycle controls are partially implemented.** Project listing, style filtering, recent/earliest sorting, multi-select confirmed deletion and input/output cleanup are wired; resume/fork-on-style-change UI remains.
14. **The project-scoped continuity graph foundation is implemented.** Each completed planning/director stage now updates `storage/projects/<project-id>/graph/continuity.json`, exposed through the project graph API. External Graphiti ingestion and richer relationship extraction remain optional follow-up work.
15. **The canonical project workspace needs migration.** New runs should use project-local `input/` and `output/` folders while retaining compatibility with the current legacy output directory.

## Proposed automated production run

Each scene is a durable state machine. Independent scenes may run in parallel, but
steps inside one scene respect dependencies.

### Stage A — Story room

1. Save the story as an immutable revision.
2. Offer optional Ollama actions: analyze, refine a selected range, or outline.
3. Require the user to approve the novel/screenplay revision before production.
4. Generate structured characters, scenes, sub-scenes, dialogue, and image-job artifacts.

### Stage B — Audio lock

1. Build or edit the character map (one voice per character).
2. Compile dialogue into timed SRT with stable scene/line IDs.
3. Run mixed multi-character TTS.
4. Generate or select music, ambience, and foley; place each on the same timeline.
5. Run optional noise cleanup, voice repair, voice change, RVC, emotion, and style stages.
6. Store every intermediate audio file and a timing manifest. Audio Reconstruction/ASR remains a separate manual-input path.

### Stage C — Visual bible

1. Generate a character reference image for each character.
2. Generate requested angles/expressions and let the user accept or reject candidates.
3. Generate or import background/location references.
4. Attach accepted reference IDs to every scene and sub-scene prompt.

### Stage D — Director scene plan

For each scene, Hermes Director receives the approved story, scene summary, character bible,
audio timing, prior-scene continuity facts, and optional Repertoire references. It
returns strict JSON containing:

```json
{
  "scene_id": "scene_001",
  "story_beat": "...",
  "shots": [
    {
      "shot_id": "scene_001_shot_001",
      "start_sec": 0,
      "end_sec": 2.4,
      "camera": "wide / dolly in",
      "lighting": "cool moonlight with warm rim",
      "tone": "quiet suspense",
      "emotion": "cautious wonder",
      "first_frame_prompt": "...",
      "last_frame_prompt": "...",
      "motion_prompt": "...",
      "character_reference_ids": [],
      "background_reference_ids": [],
      "audio_markers": []
    }
  ],
  "continuity_constraints": [],
  "confidence": 0.0,
  "questions_for_user": []
}
```

Hermes is the decision-maker. The JSON is validated by the backend. Hermes cannot
invent workflow node names or rewrite a ComfyUI graph; it can only fill allow-listed
semantic fields. Hermes delegates frame comparison to the local Qwen 3.6B vision
worker and may escalate difficult decisions to Codex GPT‑5.6 Luna.

### Stage E — Frame candidates

For each shot, generate first/last frame candidates through the selected Qwen image
workflow, using the visual bible and references. The director compares candidates
against:

* character identity and clothing;
* location and prop continuity;
* camera/framing and lighting brief;
* story beat and emotion;
* the previous and next shot;
* audio markers that must be visible or motivated.

If the score is below the configured threshold, only that shot is regenerated. The
user sees the candidates and can accept one, edit the brief, or ask the director a
question.

### Stage F — Minimax H3 motion

Once first and last frames are accepted, submit H3 with:

* first frame;
* last frame;
* motion prompt;
* selected duration and frame rate;
* scene audio as background input where supported.

The output is stored as a shot/scene artifact, then checked for duration, file
integrity, and continuity metadata.

### Stage G — Scene package and final export

1. Mux scene video with dialogue, music, ambience, and foley using the timing manifest.
2. Run loudness, duration, missing-track, and frame-rate checks.
3. Ask the director for a final continuity report.
4. If accepted, copy the scene package to the project output directory and update the manifest.
5. Keep all rejected or superseded files in `artifacts/`, `images/`, `audio/`, `video/`, and `revisions/`.

## How the director/overseer should work

### Model connection contract

Hermes Director is the single owner of orchestration decisions. Its GLM 5.3 model
receives structured project context and calls Story Builder director tools for
artifact creation, ComfyUI jobs, Repertoire searches, retries, and user questions.
For visual evidence, Hermes sends selected frames to Ollama Qwen 3.6B through a
vision-tool adapter and receives JSON observations (identity, composition,
lighting, continuity risks, and confidence). For unusually complex planning or a
deadlocked review, Hermes packages the evidence and asks Codex GPT‑5.6 Luna for an
escalated recommendation; that recommendation is advisory until Hermes accepts it.
Every call records provider, model, prompt version, input artifact IDs, output, and
decision status in the project run log.

The overseer should be fast and selective, not repeatedly re-analyze everything.

* **Before a stage:** validate required inputs and model/workflow availability.
* **During a stage:** monitor job progress, errors, durations, and output existence.
* **After a stage:** run a cheap deterministic check first (schema, dimensions,
  duration, filenames, timing), then ask Hermes for semantic continuity. Hermes may
  delegate visual comparison to Qwen 3.6B or escalate a difficult case to Codex
  GPT‑5.6 Luna.
* **On a low-confidence result:** regenerate the smallest affected unit, not the
  whole project.
* **On ambiguity:** pause that scene and create a user question with the exact
  artifact, options, and recommended choice.
* **On repeated failure:** stop retrying, preserve logs and outputs, and request help.

Hermes is the director and supervisor. The Story Builder backend remains the
authority for project state, prompt provenance, ComfyUI submission, filesystem
safety, and output acceptance. Hermes communicates through director tools/API and
does not write project files directly.

## What can run simultaneously

| Parallel work | Constraint |
|---|---|
| Ollama story analysis and deterministic file validation | Do not run competing large vision requests when GPU memory is constrained. |
| Independent scene audio preparation | Character-map changes invalidate downstream TTS for affected scenes. |
| Independent character angle generation | Shared character bible must be locked before scene frames are accepted. |
| Independent scene background/reference searches | Repertoire downloads and analysis use separate worker jobs. |
| First-frame and last-frame candidate generation | Limit concurrency to the available ComfyUI/GPU scheduler. |
| Scene-level H3 jobs | Each scene must have approved frames and a locked timing manifest. |
| Final mux checks for completed scenes | Export only after all required tracks exist. |

The queue needs one visible concurrency policy: CPU-heavy preparation can overlap,
but GPU-heavy ComfyUI jobs are scheduled and progress is shown per scene.

## How the UI asks you for help

The production page should contain a persistent run timeline and an **Attention
needed** panel. A question card must show:

* scene/shot and artifact version;
* what the director detected;
* the relevant preview (frame, waveform, transcript, or clip);
* a recommended option;
* buttons: **Approve**, **Regenerate**, **Edit brief**, **Choose reference**, or **Ask me later**.

Examples of legitimate questions:

* “Two accepted character references disagree about the coat. Which one is canonical?”
* “The dialogue is 1.2 seconds longer than the planned shot. Stretch audio, extend the shot, or split it?”
* “No Repertoire clip clearly matches this ambience. Use the closest reference or continue without one?”
* “The last frame does not preserve the prop from the previous shot. Regenerate the last frame only?”

The run must continue automatically for scenes with no unresolved question. A user
decision should unblock only the affected scene/stage.

## Prompt strategy

There are three prompt classes:

1. **Fixed system/workflow prompts:** kept versioned in the repository and never
   generated dynamically.
2. **Structured variable prompts:** generated by Hermes GLM 5.3 from approved
   context and a strict schema; saved with director model, prompt-template version,
   and source artifact IDs. Qwen 3.6B supplies visual observations, not final
   directing decisions. Codex GPT‑5.6 Luna may produce an explicitly marked
   escalation result.
3. **User-authored overrides:** visible, editable, and preserved as a new revision.

Hermes generates scene descriptions, camera language, lighting, tone, emotion,
motion, and reference-selection decisions. Qwen 3.6B reports visual evidence for
those decisions. No model may choose arbitrary ComfyUI nodes, filenames, model
paths, or unsafe filesystem locations.

## Completion definition

The main aim is complete when a new project can:

1. move from a saved story to approved structured scene artifacts;
2. lock mixed timed audio and a character map;
3. create and approve reusable character/location references;
4. produce a director-validated first/last frame pair per shot;
5. generate Minimax H3 clips with correct timing;
6. regenerate only failed shots without losing accepted work;
7. compose and validate per-scene audio/video packages;
8. show progress, previews, questions, retries, and provenance in one UI;
9. export a final manifest while retaining all prior versions.

## Explicitly out of scope for the current automated build

* Audio Reconstruction/ASR still needs your microphone and spoken calibration/dialogue recordings.
* ACE-Step fine-tuning still needs optional training checkpoints and a separate training workflow.
* Control-Foley remains an optional sound stage until its external ComfyUI source/import issue is resolved.
