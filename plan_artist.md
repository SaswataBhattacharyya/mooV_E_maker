# Master Plan: story_builder + ComfyUI Media Composer + Automation

## 1. Project Intent

This project is not just "migrate Art_ist_min into story_builder".

It is a larger system with three connected layers:

1. `story_builder`
   - An editable writing and planning surface for stories, characters, scenes, and prompts.
   - The user writes rough thoughts in a canvas, gets clarification help, and refines iteratively.
   - The result is structured story data and prompt-ready assets, not just a one-shot generated story.
   - It is one example of an upstream builder that produces text-heavy inputs for downstream media work.

2. `other upstream builders`
   - Examples: PPT builder, music builder, audio builder, logo maker, ad maker, or future prompt-producing tools.
   - These tools may output text, images, audio, video, or mixed structured metadata.
   - Their outputs should not talk to ComfyUI directly unless the mapping is trivial and already known.
   - Each upstream builder should have a Hermes skill that explains how to normalize its outputs before they enter the media manager.

3. `media manager`
   - The media manager is Hermes with a UI.
   - It is a ComfyUI-driven generation surface for image, video, audio, and later lip sync or combined outputs.
   - It consumes prompts, characters, scene plans, reference images, timelines, audio, video, or external upstream-builder outputs.
   - Hermes decides which workflow family to use, rewrites or restructures prompts to match workflow contracts, queues jobs, drives ComfyUI through API at `http://127.0.0.1:3008`, and returns results to the UI.
   - It must cover the full local workflow library under `/home/riki/web_dev/setup_comfy_and-stuff/workflows` plus connected TTS-Audio-Suite helpers.
   - The UI must be able to display all supported outputs cleanly:
     - image
     - image sequence
     - video
     - audio
     - audio + video
     - later lip-synced or post-processed composites

4. `automation runner`
   - A later n8n-like orchestration layer for defining reusable generation flows.
   - Automation links the upstream builders and the media manager.
   - It chains upstream inputs into downstream Hermes/media-manager jobs and post-processing steps.
   - This is for repeatable pipelines such as "story -> shots -> images -> video -> audio" or "PPT text/images -> slideshow video".

The immediate phase is:

- make `story_builder` editable and collaborative
- make ComfyUI control a separate but pluggable capability
- keep Hermes as the orchestrator and workflow-aware media manager

## 2. Clarified Decisions

### 2.1 No RUFLO in phase 1

RUFLO is removed from this plan.

Reason:

- Hermes already provides orchestration, routing, and delegation patterns.
- The real missing piece is not process spawning but decision quality:
  - which agent to use
  - which skill to use
  - which tool or MCP to use
  - what context to pass to each stage
- The current pipeline is sequential, not true swarm execution.

Decision:

- Hermes is the base orchestrator.
- Do not install or design around RUFLO for phase 1.
- Revisit only if true parallel worker execution becomes necessary later.

### 2.2 Port policy

Use these ports consistently:

- ComfyUI API: `3008`
- story_builder backend: `3010`
- story_builder frontend dev server: `5173` or another dev-only port chosen by Vite

Rules:

- In development:
  - React/Vite runs separately on its own dev port
  - FastAPI runs on `3010`
  - Frontend talks to backend over HTTP API
- In production or local integrated mode:
  - FastAPI may serve the built frontend
  - In that case the user-facing app can live on `3010`

The old plan mixed backend and website port descriptions because it copied assumptions from `Art_ist_min`. This plan separates dev and integrated modes explicitly.

### 2.3 ComfyUI integration model

Do not treat the old `Art_ist_min` template workflow and the current `story_builder` dynamic builders as equivalent.

There are two valid control models:

1. Template-driven workflow execution
   - Example: `Art_ist_min/api_server/services/comfyui_bridge.py`
   - Best when a workflow JSON with known node ids is stable and production-proven.

2. Dynamic workflow building
   - Example: `story_builder/engine/comfyui_engine.py`
   - Best when Hermes should compose or vary simpler workflows programmatically.

Decision:

- Support both, but do not mix them blindly.
- Phase 1 image generation should allow:
  - stable template workflows under `story_builder/workflows/`
  - dynamic builders for simple text-to-image or edit operations
- The media composer must choose one execution path per task:
  - use a known template workflow
  - or use a dynamic builder

### 2.4 Hermes execution boundary

Hermes should not be a vague idea inside the backend.

Decision:

- `story_builder` application code owns state, persistence, APIs, and ComfyUI/Ollama integration.
- Hermes is the reasoning layer and orchestration policy layer.
- Hermes is also the workflow-aware media execution coordinator.
- In phase 1, backend routes should call local Python services that encode the Hermes rules and stage logic.
- If a later CLI-driven Hermes runtime is needed, it can be added, but the core app must not depend on a fragile shell-out loop.

This means:

- Python services implement the actual stage transitions and API calls.
- Hermes docs, skills, and agents define how decisions are made.
- Hermes skills must define:
  - how to interpret each upstream builder's outputs
  - how to normalize those outputs into media-manager inputs
  - how to rewrite prompts to fit workflow-specific input contracts
  - how to decide when audio, image, and video assets can be passed through directly without prompt rewriting
  - how to queue, retry, and review jobs
- The website reflects those decisions and logs.

### 2.5 Media input policy

Not all upstream outputs need the same amount of Hermes transformation.

Decision:

- text-heavy outputs usually need workflow-aware prompt refinement before ComfyUI execution
- image, audio, and video inputs often map more directly into workflow input slots
- Hermes must still validate those direct inputs against the target workflow contract
- each upstream builder should emit a normalized handoff package, not arbitrary loose text

The standard handoff package should aim to contain:

- `source_type`
- `goal`
- `prompt_bundle`
- `assets`
- `constraints`
- `desired_outputs`
- `review_policy`

### 2.6 Queueing policy

The media manager must assume that many prompts or jobs may arrive from multiple upstream builders.

Decision:

- Hermes owns the intake queue and execution ordering policy
- the backend owns durable job state and persistence
- the UI must show queued, running, completed, failed, and review-needed jobs
- queueing must support both single interactive runs and batched upstream submissions
- automation flows should be able to enqueue multiple jobs without bypassing Hermes policy

## 3. Product Split

## 3.1 story_builder

Primary purpose:

- help the user develop a story through back-and-forth editing
- improve rough thoughts without flattening intent
- ask clarifying questions when connections are weak
- preserve editability at every stage

Key UX requirement:

- the initial writing surface is a canvas/editor, not a single "generate and lock" form
- the AI should help connect ideas, refine structure, and suggest alternatives
- it should not always balloon the story unless asked

Core outputs:

- story draft
- refined story
- characters
- scenes
- sub-scenes
- dialogue beats
- image prompt jobs

All outputs must remain editable before moving to media generation.

## 3.2 Media Manager

Primary purpose:

- operate ComfyUI properly from a friendlier interface
- expose generation choices that are currently too manual in raw ComfyUI
- act as the Hermes-run execution layer for all upstream builders
- support multiple media entry points, not only story text

Inputs may include:

- text prompt only
- story_builder prompt packs
- normalized payloads from PPT builder
- normalized payloads from music builder
- normalized payloads from audio builder
- normalized payloads from logo maker
- text + reference image
- text + multiple images
- start image + end image
- scene plan + character sheets
- external PPT-like content
- future audio/timeline inputs

Outputs may include:

- still image
- edited image
- intermediate image sequence
- video
- audio
- audio-enhanced video
- audio + video bundle
- later lip-synced video

This should be a separate page or route inside the same frontend application because the control surface is fundamentally different from story drafting.

The media manager is not just a raw workflow form.

It should do all of the following:

- receive upstream-builder handoff packages
- let Hermes classify the request
- select a workflow family
- decide whether the path is:
  - direct asset-to-workflow mapping
  - text prompt rewriting
  - mixed prompt + asset conditioning
- prepare the final workflow payload
- submit the job
- track queue state
- show outputs and review status
- support retries or alternates when the result is weak

## 3.3 Automation Runner

Primary purpose:

- define reusable chains of generation steps
- connect upstream tools to the media manager
- support semi-manual and fully automated flows

Examples:

- story -> scene prompts -> images -> video -> audio
- PPT text/images -> slideshow prompts -> video assembly
- text + assets -> batch character pack generation
- logo brief -> candidate logos -> selected variants
- audio brief -> TTS/music/effects workflows -> review outputs

This is phase 3 or later, not phase 1.

## 4. Hermes Role

Hermes is the orchestrator and the brain of the media manager.

Hermes should:

- understand the user's intent
- decide whether the user is drafting, refining, editing, generating, or debugging
- route to the correct specialist agent or skill
- keep context boundaries clean
- use Playwright when building or verifying UI
- use ComfyUI-specific knowledge when media generation is involved
- interpret upstream-builder output packages
- decide which parts need prompt refinement and which assets can pass through directly
- choose the workflow family
- transform prompts to the workflow's contract
- queue jobs and decide execution order
- decide when human review is required versus when automation may continue
- explain what it did in UI-visible logs

Hermes should not:

- force every task through a heavy agent ritual
- treat Graphify as mandatory for direct local questions
- generate locked artifacts that the user cannot revise
- bypass workflow constraints with generic prompting
- let upstream builders submit directly to ComfyUI without a defined handoff contract

Base orchestration roles:

- `orchestrator`: default router and final decision owner
- `story-editor`: story refinement and clarification helper
- `source-normalizer`: converts upstream-builder outputs into a standard handoff package
- `character-designer`
- `scene-mapper`
- `image-analyzer`
- `comfyui-expert`
- `workflow-router`
- `media-queue-manager`
- `output-reviewer`
- `frontend`
- `browser`
- `debugger`
- `quality-gate`

### 4.1 Source-specific Hermes skills

Each upstream builder should have a Hermes skill that explains exactly how to prepare its outputs before handoff to the media manager.

Examples:

- `story-builder-handoff`
- `ppt-builder-handoff`
- `music-builder-handoff`
- `audio-builder-handoff`
- `logo-maker-handoff`

Each source skill should define:

- what the upstream tool emits
- which fields are required
- how loose text becomes a structured prompt bundle
- which assets may pass through directly
- common cleanup or normalization rules
- when to ask the user for clarification
- which downstream workflow families are usually valid

### 4.2 Media-manager Hermes skills

The media manager also needs repo-specific Hermes skills for:

- workflow routing
- prompt transformation by workflow family
- direct asset mapping for audio/image/video inputs
- queueing and retry policy
- output review and candidate selection
- TTS-Audio-Suite and helper-tool integration

## 5. Where ComfyUI Knowledge Should Live

There are two separate storage locations for this capability.

### 5.1 Repo data and workflow assets

Put repo-specific generation assets inside `story_builder`:

```text
story_builder/
  workflows/
    image/
    video/
    audio/
    templates/
  docs/
    media-composer/
      workflow-catalog.md
      workflow-io-matrix.md
      tts-audio-integration.md
      ui-modules.md
      node-notes.md
      input-output-map.md
```

This is the source of truth for:

- actual workflow JSON files
- repo-specific node conventions
- required models and custom nodes
- workflow family descriptions
- TTS-Audio-Suite integration notes and helper-tool surfaces

### 5.2 Hermes skills and agents

Put Hermes capability definitions under `opencode`:

```text
opencode/.opencode/agents/
opencode/.opencode/skills/
opencode/hermes_agent/
```

Reason:

- the workflows belong to the app repo
- the Hermes behavior layer belongs to the `opencode` instruction system

Pattern:

- `story_builder/workflows/` stores the actual workflows
- `opencode/.opencode/skills/...` teaches Hermes how to use them
- `opencode/.opencode/agents/...` routes work to the right specialist
- source-specific skills teach Hermes how to consume upstream builder outputs before media-manager routing

## 6. Current ComfyUI Roadmap

The media roadmap should be phased by increasing complexity:

### Phase 1

- story -> image
- text-to-image
- text + image to image edit
- batch candidate generation
- image review and selection

### Phase 2

- image sequence planning
- start image + end image interpolation workflows
- text + image to video
- scene-level video generation

### Phase 3

- video + audio
- speech, soundtrack, and effects integration
- lip sync
- reusable automated flows

The key principle is:

- get coherence in story -> images first
- only then invest heavily in story -> video

## 7. Free/Open Model Direction

As of August 5, 2026, the best fit for the later video roadmap appears to be:

- LTX-Video 2.3 for later synchronized audio/video and richer multimodal control
- Wan 2.2 family for open text-to-video and image-to-video workflows

Practical planning decision:

- phase 1 should target image generation first
- phase 2 should keep both LTX and Wan workflow families in the catalog
- lip sync and audio-synchronized video should be treated as later capability layers, not assumed complete on day one

## 8. Target Architecture

```text
setup_comfy_and-stuff/
  opencode/
    .opencode/
      agents/
      skills/
    hermes_agent/
      ...

  story_builder/
    plan_artist.md

    api/
      backend.py

    services/
      project_store.py
      prompt_builders.py
      supervisor.py
      comfyui_bridge.py
      vision_recovery.py
      media_job_router.py

    pipeline/
      art_pipeline.py

    engine/
      comfyui_engine.py

    workflows/
      image/
      video/
      audio/
      templates/

    docs/
      media-composer/
        workflow-catalog.md
        workflow-notes.md
        model-requirements.md

    frontend/
      story-builder-app/
      media-composer-app/
```

## 9. story_builder Scope

The `story_builder` page should do all of the following:

### 9.1 Writing canvas

- large editable story canvas
- user can write rough English, fragments, notes, scene ideas
- AI suggests:
  - structure
  - questions
  - missing links
  - cleaner wording
  - optional expansion

### 9.2 Side recommendations

- suggestions panel beside the canvas
- "connect these two ideas"
- "clarify motivation"
- "expand this section"
- "make this tighter"
- "turn into scene list"

### 9.3 Staged editable outputs

After story refinement:

- characters
- scenes
- sub-scenes
- dialogue
- prompts

Each stage must remain editable.

Do not force a locked pipeline where generation makes artifacts uneditable.

### 9.4 Transition to media generation

Once the user is satisfied:

- export approved story assets into the media manager handoff package
- let the user choose what to generate next:
  - image
  - image edit
  - image sequence
  - video
  - audio/video composite

## 10. Media Manager Scope

The media manager should be a separate route or section inside the same frontend app.

It should expose the choices the user actually needs:

- generation mode
- workflow family
- input type
- reference assets
- output type
- candidate count
- review and redo controls
- whether the chosen route is pure workflow execution or helper-tool-assisted
- queue status and Hermes job decisions

Suggested top-level tabs:

1. `Text -> Image`
2. `Text + Image -> Image`
3. `Start + End -> Sequence`
4. `Text/Image -> Video`
5. `Audio/Voice/Sync`
6. `Workflow Debug`
7. `VFX / Preprocess`

Internally it should:

- accept normalized handoff packages from upstream builders
- choose the workflow
- validate required models/custom nodes
- let Hermes decide whether prompt refinement is needed
- submit to ComfyUI
- poll history
- collect outputs
- display output types appropriately
- expose retries and redos

The input builder must be workflow-aware:

- some workflows take only text
- some take text plus one image
- some take start and end images
- some later take audio, subtitles, or timing tracks

So the UI should support:

- positive and negative prompt fields
- dynamic file input rows
- `+` to add more optional inputs
- `-` to remove optional inputs
- workflow-specific parameter groups
- upload and picker controls for image, audio, and video inputs
- advanced sections for preprocess, pose, controlnet, or VFX-heavy workflows
- output viewers for image, video, audio, and mixed media results
- queue panels for queued, running, completed, failed, and review-needed jobs

## 10.1 Video Reference Selection

Later, add a semi-manual video reference module.

Purpose:

- user or Hermes can search/select short video sequences that match a prompt
- a video analyzer can strip a source video into frames, clips, and text descriptions
- Hermes can compare story prompts with those descriptions and shortlist usable sequences

Flow:

1. story prompt or scene brief is prepared
2. video-reference descriptions are searched or filtered
3. Hermes or the user chooses a candidate clip/sequence
4. the chosen clip becomes an input for downstream image/video workflows

This is not phase 1, but the architecture should leave room for it.

## 11. Implementation Phases

### Phase A: Rewrite the master plan and repo boundaries

- remove RUFLO from all planning
- define clear module boundaries
- define ports and environments properly
- define where workflows and Hermes skills live

### Phase B: Editable story_builder UX

- replace one-shot generation flow with canvas-based refinement
- add side recommendations
- keep structured story stages editable
- add project save/load
- add manual promotion from editable artifacts to approved generation inputs

### Phase C: Media manager foundation

- create `workflows/` structure in `story_builder`
- add workflow catalog docs
- copy the full local workflow library from `/home/riki/web_dev/setup_comfy_and-stuff/workflows`
- document workflow input/output shapes and special-case requirements
- document connected TTS-Audio-Suite workflows and Python helper surfaces
- build `media_job_router.py`
- build a normalized upstream handoff schema
- support template-driven and dynamic ComfyUI execution
- build image-first workflows and review loop
- add dynamic workflow-aware input forms
- add Hermes-or-human image candidate selection
- add queue state and job review state in backend and UI

### Phase D: Hermes capability pack for media

- add or refine `comfyui-expert` agent
- add source-normalizer and workflow-router roles
- add source-specific skills for each upstream builder
- add repo-specific ComfyUI workflow skill that references `story_builder/workflows/`
- add guidance for:
  - choosing workflow family
  - translating upstream builder outputs into media-manager payloads
  - mapping inputs/outputs
  - rewriting prompts per workflow contract
  - retrying failed runs
  - analyzing generated outputs
  - queueing many jobs safely

### Phase E: Video and audio expansion

- add sequence and video workflows
- add output review logic for motion and continuity
- add audio and lip sync planning
- add video reference analysis and selection support
- add TTS-Audio-Suite helper-tool integration for subtitle timing, voice processing, and scene-level audio assembly
- add mixed output rendering in UI for audio, video, and audio + video bundles

### Phase F: Automation runner

- define reusable flow schema
- build manual flow editor first
- let automation enqueue jobs into Hermes/media-manager intake instead of bypassing it
- later add n8n-like execution UI and reusable pipeline templates

## 12. Immediate Next Build Order

The next practical steps should be:

1. clean up this master plan
2. create `story_builder/workflows/` and `story_builder/docs/media-composer/`
3. copy the full local workflow library into those folders
4. document workflow IO shapes and TTS-Audio-Suite integration points
5. define the normalized upstream handoff package used by story builder and future builders
6. create repo-specific Hermes agents and skills that read those workflow docs
7. create source-specific Hermes skills for story builder and the other initial builders
8. implement editable story canvas UX before rebuilding the whole old Art_ist_min flow
9. implement image-first media manager using ComfyUI on `3008`
10. add backend queueing and UI-visible job states before large-scale automation

## 13. Success Criteria

Phase 1 is successful when:

- user can draft and refine stories interactively
- characters and scene plans are editable
- prompts can be exported into media-manager handoff packages
- media manager can generate image candidates via ComfyUI API
- Hermes can explain, choose, and operate workflows with clear instructions
- source-specific Hermes skills can normalize upstream-builder outputs
- queue state is visible to the user
- the system does not depend on RUFLO

Phase 2 is successful when:

- story assets can drive image-to-video or text-to-video workflows
- outputs are reviewable and redoable
- workflow choice is visible and understandable to the user
- audio, video, and combined outputs can be displayed cleanly in the media-manager UI

Phase 3 is successful when:

- automation flows can chain upstream content sources into media pipelines
- audio and lip sync can be attached as reusable modules
- multiple upstream builders can enqueue jobs safely through Hermes policy

## 14. Final Position

`story_builder` should be one important part of the larger project, not the whole project.

It is the creative planning and refinement layer.

The media manager should be its own reusable Hermes-driven generation layer.

Hermes should sit above the upstream builders and inside the media manager as the orchestrator, specialist router, prompt transformer, and queue owner.

Automation should link the parts, not replace Hermes.
