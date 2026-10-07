# Production workspace UX and visual interaction contract

Use the current React/Vite website and component system (`frontend/app/src/pages`, `components/ui`, Tailwind, Sonner). **Do not create a second website.** Preserve `/story`, `/automation`, `/manual-director`, `/video-repertoire`, `/audio-studio` and the existing navigation. Add `/production/:runId` (or a route consistent with `App.tsx`) from Story Builder/Automation after a valid project story exists. Build reusable components, not a single thousand-line JSX page. Back/forward/browser reload must hydrate from backend run state rather than only `localStorage`.

## Workspace navigation

Top bar: project title, production type/style, control mode, making route, current scene/cut, save state, provider/ComfyUI readiness, run state, and **View outputs**. A compact horizontal stage navigator shows **Story & direction → Optional asset studio → Voices & audio → Shot composer → Review**. Each stage displays `not started`, `ready`, `waiting for you`, `queued`, `running`, `failed`, or `accepted`; progress is based on completed units, not an animated guess. A persistent bottom/side queue rail lists active and dependent jobs with elapsed time, blocker, cancel where safe, and links to their shots. Existing story automation progress remains visible and compatible.

**Control mode** selector: Manual / Semi / Fully automated. **Making route** selector: Direct H3 (new-project default) / Reference-built / Hybrid. Explain the difference in one sentence under each selection. Semi expands four independent human-decision switches: Story/scene review; Images; Voices; Video/refs/render. Route and gate choices persist per run. Changing a route on a started project shows dependent-shot consequences before accepting. All media-generating actions show estimated time/storage/GPU class as estimates, not guarantees.

## Page A — mandatory Story & direction

Story text is mandatory even in Manual. If it is brief, show **Detail this story** (Director expansion) and compare proposed new detail with the source; source facts are pinned. Manual users may write/edit story, scenes, cuts and dialogues or click Generate draft for each. Fully automatic can move through validated text units without a human click. Show approved canon, scene order, characters, locations and dialogue in editable cards with version history and Director review status. Do not make user review six empty legacy artifact textareas before seeing a usable shot plan; retain those existing editors in an Advanced/artifacts drawer for compatibility. Every Next step validates story presence and writes a saved revision.

## Page B — Asset studio (conditional)

Direct H3 shows a lightweight **optional character/world image** area: each character card has Director-prepared visual description, editable image-model prompt, Choose model (Qwen 2512 / Z-Image Turbo / Qwen Edit 2511 only when ready), source-image `+` slots and per-source **use intent**, Refine image prompt, Generate candidates, preview, Accept. The separate scene/world cards work similarly. The user may skip every card. In Reference-built the necessary master cards are required before shots that depend on them; Hybrid marks only selected assets required. Do not offer Qwen Edit 2511 if its actual new API graph/model has not passed preflight. The current 2509 API path may remain separately labelled if it already works.

For a requested Manual/Semi image, show four candidates with zoom, reject, regenerate, Accept and provenance. Fully automatic starts with one and allows a bounded Director retake. A multi-panel character sheet and individual face/body crops can coexist as distinct **roles** without duplicating files. First/last frame cards appear only for FL2VA-designated shots, not as a compulsory asset stage. If an accepted master changes, show which unrendered/accepted shots are affected and ask whether to fork/replan those shots.

## Page C — Voices & audio

Character rows show voice brief, bound speaker ID (S1 etc.), selected backend/voice, playable clean samples, editable descriptive tags, transcript/consent/technical warnings, and Bind/Change. Manual/Semi voice gate requires a choice or explicit mute/no-dialogue condition for a speaking character; Full uses the saved seeded-random eligible local binding. The voice stage supports exact-transcript original-take upload and an installed-local-RVC conversion control with job status and separate output lineage. It explicitly warns that the selected RVC model is not the character's bound voice master; conversion must not imply identity transfer or exact dialogue generation. Hosted MiniMax clone is a separate opt-in path with consent, upload and cost dialog, not a default choice.

Separate collapsible sections list generated dialogue takes, native H3 audio from accepted shots, optional music and SFX candidates, each with waveform/player, time range, source and project asset ID. Mark optional music/SFX as **for later Hyperframes editing**; do not imply they have already been mixed into an H3 render. A character's voice binding remains stable across cuts unless changed deliberately.

## Page D — Shot composer (the primary work surface)

Use one shot at a time on desktop, with scene/cut selector and previous/next navigation. Suggested desktop layout:

```text
┌ Shot header: Scene 2 / Cut 3 · duration · workflow · route · queue state ┐
│ Director's editable H3 main prompt                         │ Asset shelf  │
│ [story facts] [shot beats] [camera/audio] [Refine] [diff]    │ tabs/search  │
├ Images  [card 1] [card 2] [card 3] [+ image, up to 9] ─────┤ Characters │
├ Videos  [card 1: paired-audio switch] [+ video, up to 3] ──┤ Worlds     │
├ Audios  [voice/S1] [+ standalone audio, up to 3] ───────────┤ Dialogue   │
│ Compiled tags, reference roles, size/duration/steps/seed      │ Video Rep. │
└ [Back] [Save draft] [Preview validation] [Generate & Next] ──┴────────────┘
```

On smaller screens the asset shelf becomes a full-height sheet/drawer and cards stack vertically. The initial view can show three empty image positions and one video/audio card affordance as requested, but **empty cards are UI placeholders, not connected graph nodes**. For each selected asset card show preview/play, source/project ownership, its actual compiled tag (`<Picture 1>`, `<Video 1>`, `<Audio 2>`), a **Use this for…** note, remove/reorder, and provenance. Video cards each have a separate **Include this video's audio** switch and soundtrack waveform: there are at most **three videos total**, not three silent plus three audio videos. Put a short explanation next to the switch when its audio is obsolete dialogue/music. Standalone audio cards separately show S1/S2 binding and audition. If a paired video soundtrack is present, its Audio label appears before standalone voices; update labels visibly when a card is added/removed/reordered.

The right asset shelf is project-scoped by default: Generated characters; world/scene images; accepted frames; dialogue/voices; previous approved cuts; music; SFX; external Video Repertoire search; Upload from computer. Collapsible groups remember state; large lists are virtualized/paginated. Drag/drop, click-to-add and upload all resolve to a safe asset ID. The UI must not silently copy an external asset into project output. If semantic Video Repertoire search is offline, display keyword search with a clear limitation, not a fake semantic result.

**Prompt Refine:** editable main text is Director-generated from the actual shot plan and role map. Under each selected asset, the user writes an *intent note*, not a second H3 prompt. Clicking Refine sends current main prompt + shot canon + asset IDs/intent notes + compiled tags + free-form user instruction to the text worker; return a proposed diff/rationale/validation list. Accept/Edit/Discard. Preserve the user's original prompt revision. A subsequent asset reorder marks the accepted prompt stale and offers to re-refine/revalidate. Image-generation Refine is a **separate** action on Page B with model-specific prompt rules and source-image roles.

Workflow controls come from capability manifest: T2V, local R2V dynamic, tested FL2VA, and optional future advanced modes. Show exact required slots, reference count/duration, 24-fps treatment, output frame count, the `0.98` final resolution preset, `ref_image_size`, steps, seed and estimated cost. Disable unsupported combinations *before* submission with field-level reasons. Do not offer Add Guide/Fun ControlNet until separately installed and smoke-tested.

For a same-scene second/later cut, the Director can propose a short tail of the immediately previous **accepted** take; the card states whether it carries paired audio. A fresh scene does not automatically inherit that previous scene's MP4. The user can override in Manual/Semi; Full follows recorded policy and audits the choice. “Use previous shot for identity” and “use external action video for choreography” are visibly different roles.

## Navigation and queue behavior

- **Save draft** persists prompt, intents, selected IDs, slot order and parameters without ComfyUI submission.
- **Preview validation** calls the backend reference-plan validator and shows resolved tags, missing inputs and resource limits; it does not consume GPU.
- **Generate & Next** is the primary button when the draft is approved. It creates an idempotent queued shot, gives immediate confirmation with job ID, and moves to the next shot draft. If the predecessor is still running, mark the new job `waiting_for_predecessor`; let the user edit/cancel it until submission. When predecessor is accepted, auto-submit **only if** the queued draft, inputs and compiled plan revision are unchanged. Otherwise show `Needs review` and do not run.
- **Back** returns without losing the current draft. Editing an accepted earlier shot creates a new take/plan revision; show affected dependent queued/accepted shots and ask for explicit replan scope. Do not silently overwrite or delete accepted media.
- **Review** shows playable video **with native audio**, separate optional dialogue/music/SFX assets, actual compiled graph/reference map, generation logs summary, Director rubric, Accept/Retake/Compare. Retake only the selected shot; dependent same-scene queue waits for the accepted choice.
- Show a queued shot's actual dependency and whether it is awaiting human input, ComfyUI, previous-shot acceptance, or GPU capacity. A browser reload must restore it exactly.

## Interaction polish and accessibility

Use existing Radix/shadcn primitives for cards, sheets, dialogs, tabs, tooltips, toast and progress. Buttons get subtle pressed/spinner feedback and do not double-submit. Long actions show determinate progress where measurable (story units, queue position, completed shots) and honest indeterminate state during model sampling. Toasts announce success/failure; persistent inline errors show the **specific asset, node, stage, retry action and log/correlation ID**. For example “Video 1 audio is missing” or “ComfyUI rejected `VHS_LoadVideo`,” not merely “HTTP 500.”

Required states: loading skeleton, empty project, no eligible voices, model unavailable, offline ComfyUI, upload failure, invalid ref count/duration, stale prompt, queued/running/waiting/failed/cancelled/accepted shot, no native audio, and previous-shot retake invalidation. Dialogs confirm destructive operations with exact scope; deletion of a shot/take must never delete its shared Video Repertoire source or another shot's accepted asset. Provide focus restoration, labels/ARIA descriptions, keyboard card reorder or buttons as an alternative to drag/drop, visible focus/disabled state, reduced-motion support and touch-sized actions. Test narrow/mobile and desktop widths; avoid horizontal overflow in prompt/reference cards.

## Frontend file plan

- `frontend/app/src/App.tsx`: additive production route; retain all existing routes.
- `frontend/app/src/pages/ProductionRunWorkspace.tsx`: page-level state/router composition, not all logic in one file.
- `frontend/app/src/components/production/`: `ModeRouteSelector`, `StageRail`, `StoryDirectionPanel`, `AssetStudio`, `VoiceBindingPanel`, `ShotComposer`, `ReferenceCard`, `ProjectAssetBrowser`, `ResolvedTagMap`, `PromptDiff`, `JobQueueRail`, `ShotReview`.
- `frontend/app/src/lib/project-api.ts` or a dedicated typed `production-api.ts`: strict DTOs for production run, stage, asset, reference plan, validation, job, output and error codes. Existing methods stay compatible.
- Reuse `frontend/app/src/components/AppShell.tsx` navigation; add a contextual Production link rather than a duplicate top-level app.

**UI gate:** Playwright covers first-run story requirement, both making routes and Hybrid override, Manual/Semi/Full gates, card count and paired-audio numbering, model unavailability, Refine diff, reload persistence, Generate & Next queueing, Back invalidation, a real or test-server output player, errors/pop-ups, keyboard/mobile states and unchanged legacy pages.
