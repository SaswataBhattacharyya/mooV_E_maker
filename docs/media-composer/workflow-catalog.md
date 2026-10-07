# Media Composer Workflow Catalog

This file maps generation intents to current workflow candidates inside `story_builder/workflows/`.

Use this together with:

- `workflow-io-matrix.md`
- `tts-audio-integration.md`

## Phase 1: Image First

### Text -> Image

- Workflow: `story_builder/workflows/image/image_qwen_Image_2512.json`
- Use for:
  - character assets
  - backgrounds
  - scene stills
  - prompt candidate batches
- Notes:
  - good default path for story_builder prompt packs
  - should support multi-candidate generation plus image review

### Text + Image -> Image Edit

- Workflow: `story_builder/workflows/image/02_qwen_Image_edit_subgraphed.json`
- Use for:
  - refining a generated still
  - adapting composition from a reference image
  - carrying character identity or layout into a new frame

### API Template Bridge

- Workflow: `story_builder/workflows/templates/gsl_starter_1_1_api.json`
- Use for:
  - stable template-driven API submission
  - known-node-id prompt injection patterns
- Notes:
  - inherited from `Art_ist_min`
  - useful when app code wants a production-known template instead of a dynamic builder

## Phase 2: Video

### First/Last Frame -> Video

- Workflow: `story_builder/workflows/video/video_ltx2_3_flf2v.json`
- Use for:
  - two approved keyframes
  - generating motion between established start and end frames

### Image + Text -> Video

- Workflow: `story_builder/workflows/video/video_ltx2_3_ia2v.json`
- Use for:
  - a reference still plus motion/prompt intent
  - continuity-driven scene expansion

### Wan Image -> Video

- Workflow: `story_builder/workflows/video/video_wan2_2_14B_i2v.json`
- Use for:
  - image-conditioned video generation
  - experiments where Wan performs better than LTX for motion or style

### Wan Text -> Video

- Workflow: `story_builder/workflows/video/video_wan2_2_14B_t2v.json`
- Use for:
  - direct text-to-video generation
  - situations where no approved keyframe exists

## Phase 3: Audio

### Multi-character Timed TTS

- Workflow: `story_builder/workflows/audio/TTS_audio_multichar_timed_wf.json`
- Use for:
  - dialogue tracks
  - character voice timing
  - multi-speaker narration

### Audio SRT Timing

- Workflow: `story_builder/workflows/audio/audio_SRT_timing.json`
- Use for:
  - subtitle/timing alignment
  - speech timing support for downstream sync

## Selection Rules

- Prefer Qwen image workflows for phase-1 story-to-image work.
- Use LTX first for start/end-frame or image-assisted video experiments.
- Keep Wan available as an alternate video family, not the only path.
- Audio workflows are downstream of approved story/dialogue assets, not upstream.

## Future Catalog Entries

Later add:

- video sequence analysis inputs
- video-reference search and selection assets
- lip sync workflows
- VFX or compositing workflows
- PPT/slideshow assembly workflows
