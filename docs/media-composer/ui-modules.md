# UI Modules

This file describes the recommended UI split for the first two modules.

## Preferred Shape

Use one frontend application with multiple routes, not separate unrelated websites.

Recommended routes:

- `/story`
- `/story/projects/:id`
- `/media`
- `/media/projects/:id`
- `/media/workflows`
- `/media/review`

This keeps:

- shared auth/session/project context in one app
- separate interfaces for drafting and media generation
- future automation pages in the same product shell

## Story Builder Route

Main goals:

- editable writing canvas
- side recommendation panel
- stage cards for story, characters, scenes, sub-scenes, dialogue, prompt jobs
- save, refine, compare, approve, and export controls

Key widgets:

- large story canvas
- "refine", "connect", "expand", "compress", "clarify" actions
- recommendation sidebar
- stage timeline
- editable JSON/text artifact drawers

## Media Composer Route

Main goals:

- choose workflow family
- choose generation mode
- fill the inputs required by that workflow
- run candidate batches
- review images/videos/audio outputs

Suggested top-level panels:

1. Workflow selector
2. Input builder
3. Prompt fields
4. Batch controls
5. Run status
6. Output review

## Input Builder Behavior

Because workflows have varying inputs, the UI should not hardcode a single form.

Minimum behavior:

- support text fields for positive and negative prompts
- support 0..N image/file inputs
- support add/remove input rows with `+` and `-`
- support workflow-specific parameter sections
- display which inputs are required vs optional

## Human and Hermes Checkpoints

The system should allow:

- Hermes-only auto selection
- human review and selection
- mixed mode where Hermes proposes and human confirms

Examples:

- choose best image out of 4
- choose best video sequence candidate
- choose external reference clip for a prompt

## Future Routes

Later add:

- `/media/video-library`
- `/automation`
- `/automation/flows/:id`
