# OpenClaw Pipeline

This file describes the intended workflow through the website and up to image generation.

## Product Entry Point

The user starts in the website.

The user should not need to manually drive OpenClaw.

Normal startup:

```bash
./bootstrap_vm.sh
```

Then open:

```text
http://<vm-ip>:3010
```

Optional supervisor setup:

```bash
./setup_openclaw_supervisor.sh
```

Optional supervisor daily start:

```bash
./run_openclaw_supervisor.sh
```

Then open:

```text
http://<vm-ip>:3009
```

The supervisor is separate from the main website for now. It watches the same project state and logs.

## Website Flow

### 1. Draft Intake

The user provides:

- project title
- initial story idea
- automation preference

The first action should save a draft.

The draft must survive:

- page navigation
- refresh
- moving to status and back

### 2. Story Generation

After the draft exists, the user generates the `story` artifact.

The system should:

- improve and expand the user’s idea
- keep it coherent
- preserve the user’s core intent
- prepare a production-useful story blueprint

The user may then edit or approve it.

### 3. Character Building

After story approval, generate `characters`.

Character output should include:

- name
- role
- appearance
- wardrobe baseline
- personality
- visual prompt direction
- suggested voice alias

The user may then edit or approve it.

### 4. Scene Building

After character approval, generate `scenes`.

Scene output should include:

- ordered scenes
- location
- time of day
- visible characters
- summary
- background direction
- continuity notes

The user may then edit or approve it.

### 5. Sub-Scene Building

After scene approval, generate `subscenes`.

Sub-scene output should include:

- shot number
- camera
- blocking
- action
- mood
- start-frame intent
- end-frame intent
- visual prompt basis

The user may then edit or approve it.

### 6. Dialogue Building

After sub-scene approval, generate `dialogue`.

Dialogue output should include:

- beat-level dialogue
- speaker
- line text
- delivery notes
- timing intent
- narration notes
- SFX notes
- BGM notes
- whether the speaker is on-screen or off-screen

The user may then edit or approve it.

### 7. Image Job Generation

After dialogue approval, generate `image_jobs`.

These jobs should be ordered roughly as:

1. character assets
2. scene backgrounds
3. scene compositions
4. later scene-image variations

Each job should include:

- title
- kind
- prompt
- width
- height
- scene or subscene linkage

## Character Asset Flow

Character image generation should begin before full scene composition.

Expected image asset types:

- front full body
- back full body
- left side full body
- right side full body
- close-up

Default review behavior:

- generate 4 candidates
- user chooses one
- or user asks for 4 more

## Scene Visual Flow

After characters are approved:

1. generate scene backgrounds
2. approve backgrounds
3. generate composed scene images using character and scene context
4. approve image batches

This is the current target up to images.

## Later Video Flow

After enough approved images exist, later phases should support:

- first/last scene image planning
- intermediate image planning
- scene-to-scene visual progression
- video interpolation
- inpainting
- lip-sync-related localized repair

That later video path is not the current stopping point, but the pipeline should already be designed so it leads there naturally.

## Audio Preparation Flow

Audio comes after visual intent is well-defined.

The audio path should follow:

1. approved sub-scenes
2. approved dialogue plan
3. approved visual timing intent
4. dialogue generation in parts
5. localized edit path when needed
6. SFX plan
7. BGM plan
8. assembly/mix

### Audio Rules

- narrator may be untagged in plain narration
- default female lead is `Alice`
- default male lead is `Bob`
- alias map is the source of truth for added characters
- pause tags should be rare and internal to a line
- local corrections should use split/edit/concat where possible

## Full Automation

Automation mode does not remove the pipeline.

It changes who chooses during review.

### Manual Mode

The user:

- reviews artifacts
- reviews image candidates
- triggers next steps

### Full Automation Mode

The app may continue stage by stage automatically, but:

- decisions should still be visible in the website
- artifacts should still be stored
- the system should still be stoppable and resumable
- OpenClaw supervision later should still remain bounded

In this mode, OpenClaw should:

- supervise every generated text/JSON stage
- revise weak artifacts in place when a small correction is enough
- request regeneration when the result is too weak or incoherent
- judge image batches with VLM + reasoning
- accept one candidate or request a redo batch

## OpenClaw’s Place In This Pipeline

OpenClaw does not replace the pipeline.

OpenClaw watches the pipeline and helps by:

- diagnosing problems
- checking if the right stage failed
- checking whether the prompt/artifact/workflow is weak
- suggesting the smallest useful correction
- later comparing prompt/result variants

The pipeline remains website-first and backend-controlled.
