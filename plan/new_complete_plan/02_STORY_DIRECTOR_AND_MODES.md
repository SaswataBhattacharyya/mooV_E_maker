# Story, Director, styles, prompt rules, and the two mode axes

Phase 1 dynamic H3 proves the media capability. This document defines the later **project production** behavior that drives it. Reuse the existing `/api/projects`, artifact editors and style packs; do not create an unrelated story database or route around project identity.

## Story is always present

`POST /api/projects` already requires `story_input`; preserve that invariant. A project can begin with one paragraph, but **not a blank shot**. The Director first distinguishes (a) explicit user facts, (b) approved previous artifacts, and (c) creative details it proposes to fill missing story structure. A sparse-story elaboration must retain all given facts, character names and ordering, state what it inferred, and offer review/editing before those facts become canon in Manual/Semi. In Full, apply deterministic checks and bounded Director review/repair without an indefinite human gate. Manual can author/edit story, scenes and prompts itself or click **Generate draft** at any stage; “optional generation” does not mean “optional story.”

Existing artifact compatibility: `story`, `characters`, `scenes`, `subscenes`, `dialogue`, `image_jobs` in `services/project_store.py` remain readable/editable. Add new shot, canon, style and asset revisions **alongside** them; retain current `content`, status and route shapes for old clients. `services/story_pipeline.py` currently makes one JSON request per artifact and `services/director_pipeline.py` currently makes one shot-plan request; these are starting points, not the complete Director. The new path must handle long output in chunks with stable IDs and a completeness check so entire stories/dialogue sets are not silently compressed into a single token-limited response.

Suggested hierarchy and identifiers:

```text
story source revision → approved story canon
  → character IDs / voice bindings / location+world-state IDs
  → ordered scene IDs → ordered cut/shot IDs
  → dialogue beats with speaker, language, exact words, target timing
  → one versioned ShotPlan per shot → reference plan → compiled graph → takes
```

Every generated or manual revision records author/provider, prompt/rule version, parent revision, evidence from source story, timestamp, and affected downstream IDs. Changing a character costume or scene geography invalidates only dependent future shot plans and renders. Keep `services/project_graph.py` as rebuildable index of approved canon, not a conflicting second source of truth.

## Director and workers

The **Director is one orchestration/policy authority**. It gives a bounded writing task to a provider-neutral text worker, receives structured output, validates it, requests a targeted repair if needed, and advances the run. Codex CLI (`gpt-6-luna` as currently configured) is the initial story text/review provider; do not hard-wire the architecture to that model or silently switch providers mid-run. Do not remove Ollama from other pages. A run snapshots provider/model, production type, narrative style/version, visual treatment, rule corpus version, making route, control mode and consent/cost policy.

Director duties at **each** stage: preserve source facts; resolve approved character/world state; plan shot duration/cuts; choose the tested H3 workflow and asset roles; decide whether a prior-shot video/soundtrack is relevant; write useful prompts; check model output at an appropriate depth; request bounded retakes; record confidence and reason. It is not merely a last-page reviewer. Deterministic schema/coverage checks run for every text unit; expensive provider review is targeted at ambiguity, continuity risks, style conflicts and milestone assemblies. Prompt improvements are **versioned proposals evaluated on fixtures**, not live edits to executable source files.

Keep production type and style separate from image/video references. Preserve the six existing base packs in `prompts/styles/*.json` and the current `services/prompt_styles.py` contract, then add nested named style variants and distinct Director behavior profiles for each production type. A narrative style can be drafted from `.pdf`, `.md` or `.txt` with page/line evidence; do not ingest a video into narrative style. Visual treatment (anime, realistic, etc.) is a separate selectable policy and can use image references. Do not copy a source document's plot or dialogue into another project's style.

## Two independent axes

| Axis | Options | What it changes |
|---|---|---|
| **Control mode** | Manual / Semi / Fully automated | Who selects/approves text, images, voices, references, parameters and takes; not the underlying media model. |
| **Making route** | Direct H3 (default for new projects) / Reference-built / Hybrid | Whether visual masters are made first, skipped, or chosen per shot. A saved existing project is never silently migrated to a new default. |

**Manual:** story required, but generating story expansion/scenes/dialogue is a user-triggered option; edits are first-class. In Direct H3, advance from approved story/scene text straight to voice selection and H3 prompt composition. Offer **Generate character image** as an optional, same-contract branch with prepared prompt and model/ref controls. In Reference-built, the required character/world image tasks and approvals appear before their dependent shots. User approves each shot draft and may click Generate & Next to authorize a queued render. No silent substitution of voice, ref or workflow.

**Semi:** present *four independent human-decision gates*: (1) story/scene/detail review, (2) image creation/candidate selection, (3) voice selection, (4) shot reference/workflow/render approval. The Director prepares drafts for every gate. Disabled gates follow full-auto policy. Turning all on resembles Manual but never removes the Director's drafting/checking; Direct H3 still skips an image gate when no image is requested. Persist gates per run and show precisely where it is waiting.

**Fully automated:** Director elaborates story, plans and validates text, binds one eligible local voice per character using a saved random seed/pool version, chooses tested H3 modes/assets, renders and reviews within bounded retries. It cannot silently fetch an external action clip, clone/upload a voice, select an unapproved reference across projects or pretend a new model is available. If an essential asset or model fails, pause with an actionable reason; do not generate an empty/incorrect substitute.

For any route, maintain a global **text character/world bible**. Reference-built/selected Hybrid shots additionally use approved visual masters. Direct H3 may keep a visual still from an accepted prior shot as an explicitly chosen identity aid; doing so does not make the entire route Reference-built. Fresh scenes do not inherit a previous-scene MP4 merely because one exists. If the same characters appear, the Director can use text, stable voice files, and any *approved* still/master; disclose visual drift risk when no such anchor exists.

## Versioned H3 prompt corpus

Add original, concise rules under `prompts/minimax_h3/`, for example `reference_roles.md`, `shot_prompt_contract.md`, `examples.json`, `validation.json`, `corpus_manifest.json`. Read official MiniMax and ComfyUI primary guides at implementation time and cite their versions. Do not paste their entire copyrighted guides into the repository. The Director loads the active corpus version **before** planning shots; every shot stores it.

The corpus must teach these distinctions:

- H3 T2V versus FL2VA first/last anchors versus R2V images/videos/audio; only expose a combination the **selected local graph** actually supports. The hosted API's first/last-vs-reference rules are not interchangeable with local ComfyUI behavior.
- `<Picture N>` means a particular selected image; `<Video N>` a particular frame batch; `<Audio N>` either a deliberately paired video soundtrack or standalone audio, in the resolved graph order. `(S1)` is a stable *speaker* and `<Subject 1>` a visual subject; declare their mapping explicitly.
- For each reference, state what transfers: identity, costume, world geography, camera, action rhythm, audio timbre, existing performance, ambience, etc.; also state what must **not** transfer. Unused refs should be removed.
- A prompt should give scene setting, relevant character/world descriptions, per-cut time budget, subject action/blocking, camera/framing/motion, lighting, dialogue with language and `<d>...</d>` tags, native soundscape, music intent, and continuity/end state. It should be short enough for the selected model yet complete; use small, validated shot units instead of a huge single prompt.
- `reference`, `partially_copy` and `fully_copy` are **prompt intents**, not a guarantee of exact waveform preservation. Two voices can map incorrectly in H3; the Director must inspect and can choose exact external dialogue preservation for later editing.
- A prior video is either motion/camera/style reference or same-scene short-term continuity; do not label ordinary R2V as exact video editing or Add Guide continuation.

The Director creates a structured `ShotPromptDraft` with `scene_id`, `shot_id`, `story_facts_used`, `character_ids`, `world_state_ids`, spoken lines/timing, H3 workflow family, main prompt, reference intents, expected end state and review rubric. The graph compiler's **resolved reference map** is injected before final wording/validation. Prompt lint catches missing/extra tags, wrong speaker-to-voice mapping, conflicting instructions (“keep old dialogue” versus “new line”), overlong spoken text for duration, and unsupported output roles.

## Refine button semantics

Each selected asset has **two different text concepts**:

1. **Asset-creation prompt** — used by Qwen/Z-Image/Edit/TTS to create that asset; has its own model-specific style and revision history.
2. **Asset-use intent** — the user's note under that asset in the shot composer, such as “Picture 2 is the costume reference; ignore its background.” This is not sent verbatim as a second MiniMax prompt. It informs the main H3 prompt.

**Refine** takes the current main prompt, story/shot facts, visual/voice canon, all selected assets and their use intents, actual resolved `<Picture>/<Video>/<Audio>` tags, active H3 rules, and user free-text instruction. It returns a proposed revised prompt **plus a concise change rationale and validation warnings**. Show a line/word diff with Accept, Edit and Discard; never overwrite the user's prompt automatically. Do not change asset selection or slot order during Refine. If a ref changes afterward, mark the prompt stale and require revalidation/refinement before Run. Retain old revisions for rollback.

For image generation/editing, use a **different prompt contract**: one principal image prompt plus per-input-image role/intents. Qwen Edit's asset inputs are not MiniMax `<Picture N>` tags. The image Refine button produces a proposed *image-model prompt* and shows a diff; it must not silently change a character's approved identity or the H3 video prompt. Keep these separate in the UI and audit.

## Long text and stage handoff

Chunk story expansion by acts/beats, scene plan by scene, dialogue by scene/shot and visual briefs by asset. Save each accepted unit atomically. Validate all planned IDs exist after assembly, preserve the source story and manual edits, and reconcile across stage boundaries. Back navigation and prompt edits update a revision, not delete accepted upstream work. A run restart resumes at the first incomplete unit; no repeated ComfyUI submission due to retry.

**Acceptance gate for this area:** a sparse but mandatory two-scene story expands without losing source facts; both Director-generated and user-authored Manual scene paths work; every control/making-route combination produces a valid shot contract and H3 prompt; Refine honors asset-intent changes and exposes a diff; the old artifact editors and style IDs still work.
