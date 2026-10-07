# Story Generation, Director, and Style Library Upgrade Plan

**Status:** revised mega-plan, 2026-10-01; implementation and live model/workflow validation are separate later phases  
**Scope:** Story Builder planning automation, production-style selection and authoring, director supervision, character and world reference libraries, dialogue/voice choices, selective scene anchors, and workflow-aware MiniMax H3 shot generation.  
**Compatibility rule:** retain existing Story Builder and Automation entry points, project files, six production-type packs, project continuity graph, media workflows, and working non-story pages. Migrate additively; do not replace unrelated app behavior.

**Decision precedence:** this revision incorporates the user's latest decisions over older wording in `plan/prompt.md`: automation chooses an eligible voice randomly, Manual/Semi users can choose; the Director and worker roles are provider-neutral with Codex as the first configured text provider. Preserve the prompt as historical input, not the final contract. ComfyUI, Conda environments, and the existing website remain unchanged while this is a plan.

**Two independent choices:** a run's **control mode** is Manual, Semi-automated or Fully automated; its **making route** is Direct H3 (fast/text-led), Reference-built (character/world assets first), or Hybrid (Director chooses per shot). These are orthogonal. Default the visible making-route control to **Direct H3** for a new project, with Reference-built as the explicit asset-preparation choice and Hybrid as the per-shot option; preserve any existing project's behavior during migration. The user may change route at a safe shot boundary without duplicating accepted assets. The latest user addendum is preserved verbatim in `plan/prompt.md`.

## 1. Product intent

Build complete, detailed story-production artifacts without forcing a long story or a large scene/dialogue set into one model response. A **single Director orchestrator** owns the project contract, stage order, approvals, and recovery. It delegates bounded writer/reviewer tasks through a provider-neutral text-agent interface; **Codex CLI is the initial configured provider**, not a hard-coded architecture dependency. Ollama is not part of the initial story-production route, and the provider/model is snapshotted per run: changing it requires an explicit new run/fork, never a silent mid-run fallback. The Director prepares each task with relevant canon and creative guidance, then checks outputs at the right depth without blocking healthy progress.

Each run selects one production type, one optional named narrative/story style, and a separate visual-treatment profile. Narrative/story style is derived only from user-provided text documents (`.pdf`, `.md`, `.txt`) and guides story structure, prose, scenes, dialogue, and performance. Visual treatment is selected separately using text presets (for example anime, photorealistic, LEGO-like, or soft-toy) and optional image references. Video references are distinct per-shot/per-generation inputs for motion, camera, composition, or editing structure; they are not ingested to create narrative style packs.

After text planning, the intended production sequence is:

```text
input story
  → complete story/world and character artifacts
  → scenes, sub-scenes, dialogue, and shot/image briefs
  → choose Direct H3, Reference-built, or Hybrid making route
  → optional character/world reference assets for Reference-built shots; Direct H3 retains text canon and voice binding
  → optional first/last/keyframe candidates only for shots whose selected workflow benefits from them
  → deterministic validation plus targeted Director continuity/style review and bounded repair
  → scene-timed dialogue via local TTS, recorded-take voice conversion, or an explicitly configured hosted clone/TTS adapter; plus music/SFX
  → workflow-aware ComfyUI/MiniMax H3 generation using only inputs the selected installed workflow actually accepts
  → scene review, retry of only failed items, and project manifest
```

Planning artifacts and media generation remain distinct stages. Creating scene prompts does not itself generate still images or videos.

**Audio routing correction:** dialogue does **not** automatically move straight into H3. H3 reference generation can accept standalone audio and video, and this machine's `MiniMaxH3ReferenceToVideo` *node* already has those inputs. The website's current `minimax_references` *workflow graph and Manual Director adapter* wire only 1–3 images; `minimax_text` is text-only and `wan_first_last` accepts endpoint images. First add and test a versioned audio/video-capable graph and UI adapter; do not claim it is already runnable. Existing local TTS is the dependable default for exact scripted lines, while the installed local voice changer can transform a recorded performance. MiniMax Speech 2.8 voice cloning is a **separate hosted speech API**, not a free/local H3 video node. If H3 generates its own speech while a pre-generated take is selected, the final mix must explicitly replace/mute it; a prompt's `fully_copy` wording is not proof of sample-exact waveform preservation.

## 2. Current implementation facts and gaps

The plan is grounded in the current repository:

| Existing area | Current behavior | Planned change |
|---|---|---|
| `services/story_pipeline.py` | Story, character, scene, sub-scene, dialogue, and image-job JSON prompts are embedded in Python and each calls one JSON generation request. | Retain schemas and APIs, move reusable prompt contracts to versioned templates, and route large artifacts through a durable chunk coordinator. |
| `services/reasoning_provider.py` | One global selected provider is captured for a planning run. | Add a role/task adapter with Codex as the first story provider; preserve other pages' behavior. Record provider/model and generator/reviewer task separately in the run audit. |
| `services/ollama_client.py` | Existing Ollama support may serve other app tasks. | Do not call it from story-production automation; do not remove or alter its unrelated uses. |
| `services/director_pipeline.py` | Generates one shot plan after the six planning artifacts. | Make one Director policy layer guide and review stages using the selected text-provider adapter only when needed, not only write a final plan. |
| `services/prompt_styles.py`, `prompts/styles/*.json` | Six validated flat JSON packs represent production types; style selector is a flat `<select>`. | Preserve these as production-type base packs and add nested versioned style variants and a shared hierarchical picker. |
| `services/project_graph.py` | A project-local JSON graph records artifact/entity mentions after automation stages; manual artifact edits do not reliably update it. | Treat it as a derived lookup view, not approved canon. Rebuild/update on both generated and manual revisions; add a separate style evidence graph. |
| `services/project_store.py` | Project root is `storage/projects/<project_id>` with artifacts and `project.json`; generated media uses project output paths. | Keep state, approved canon, manifests, and run checkpoints under project storage; generated media has one canonical home under `output/<project_id>`, referenced by IDs. |
| `frontend/app/src/pages/StoryBuilder.tsx` | Draft, Start planning, Start full production, six artifact textareas, one flat style picker, and progress polling. Artifact content is not rehydrated after every stage. | Keep the entry point; use shared style picker and stage/chunk-aware project refresh so artifacts appear as they complete. |
| `frontend/app/src/pages/AutomationStudio.tsx` | Separate automation entry with another flat style selector and story-file upload. | Keep the entry point and use the same shared style picker, provider/mode snapshot, style version, and run contract. Audio automation remains unchanged. |
| `services/production_runner.py` | Current tested demo production path is limited: it uses the same `plan/image.png` as three references, has a fixture fallback for music, creates a Foley cue, then runs a fixed MiniMax H3 reference workflow. | Replace fixture references with approved per-character/per-scene assets; route by the Director's scene contract and the inspected ComfyUI workflow manifest. Preserve a safe fixture path only for explicit tests. Keep separately generated dialogue/music/SFX on the same shot timeline. |
| `services/audio_catalog.py` | Discovers example voices under ComfyUI; only voice files with an adjacent non-empty `.reference.txt`/`.txt` are discoverable by the current TTS suite. | Add read-only metadata overlay from this project's voice catalog and eligibility preflight; never copy or alter the ComfyUI source voices merely to create descriptions. |
| `services/manual_director.py` and `workflows/api/` | Installed text, image-reference, and WAN first/last workflows have different actual slots; the current image-reference graph does not take audio/video files. | Preserve installed graphs; build versioned, separately tested workflow adapters before claiming H3 audio/video-reference routing. |
| Installed ComfyUI core `nodes_minimax_h3.py` | The local `MiniMaxH3ReferenceToVideo` node supports autogrowing image, video, paired video-soundtrack, and standalone-audio inputs, but the app graph connects images only. The installed core does **not** contain `MiniMaxH3AddGuide`; Fun ControlNet model patch and pose models were not found in local model folders. | First wire/test existing R2V node capabilities in a **new app workflow**. Treat Multiframe/Add Guide and Fun ControlNet as later version/model compatibility gates; do not update ComfyUI or install checkpoints as part of planning. |
| `services/audio_effects.py` / `services/audio_automation.py` | Audio Studio has local `voice_changer` with a discoverable target reference voice, and `rvc` with installed model/index options; Audio Reconstruct stores raw/accepted takes. | Offer recorded-performance conversion as a distinct dialogue source, preserving the exact words/timing where validated; do not equate voice conversion, reference cloning, and persistent hosted voice IDs. |
| `workflows/ricky/vid_minmax_h3_r2v.json` and `...r2v_crazy.json` | These are editable ComfyUI UI graphs. The first contains two `LoadImage` inputs; the crazy variant contains three image links, one video-frame link, one paired-video-audio link, and two standalone audio links. Its video frame and soundtrack links currently come from **different** `VHS_LoadVideo` nodes; its Resolution Selector is `0.4`, overriding the H3 node's displayed width/height. | Treat them as inspected templates, not a safe API contract. Compile a fresh validated API graph from a stable base and requested asset roles; pair image/audio outputs from the same video loader and set the final selector explicitly. Do not overwrite Ricky's graphs. |
| `workflows/ricky/gsl_starter_1_1.json`, `qwen_image_edit_2511.json`, and `workflows/api/` | `gsl_starter_1_1` is **Z-Image Turbo**, not Qwen 2512. The existing Qwen 2512 text-to-image API graph exists, but the current `qwen_edit_api.json` selects Qwen Image Edit **2509**, while Ricky's UI graph names **2511**. The Ricky I2V graph contains subgraph nodes rather than being a ready API graph. | Add distinct versioned image-generator/edit adapters only after live model/node preflight and a UI-to-API export/validation for 2511. Keep the tested 2509 adapter untouched until 2511 is proven. |

The existing Story Builder project artifacts remain the public compatibility contract. New chunk records and provenance must be additive; callers that only read the current `content` field must continue working.

## 3. Design invariants

1. Never compress or omit story beats, scenes, dialogue beats, characters, or required metadata merely to fit a provider's response limit.
2. Bound each model call below its model/context/output budget. Split work by meaningful narrative units, not arbitrary character counts where a scene/beat boundary is available.
3. Save every completed chunk atomically. A retry resumes at the failed/incomplete unit and does not duplicate accepted units.
4. Keep immutable source story and approved upstream artifacts. Repairs create new revisions with parent IDs and diffs; they do not silently overwrite approved material.
5. Keep writer and director providers, models, prompt versions, style IDs/versions, chunk IDs, retries, and reviewer decisions in the run audit.
6. The configured Director/writer agents may repair current-run artifacts and produce versioned prompt-pack improvement proposals. They must not silently modify executable Python code during a user run.
7. The text-agent interface is provider-neutral. Codex is the first configured provider. Preflight failure is visible and actionable; there is no silent switch to another provider or mid-run generator change.
8. Style is guidance, not story content. Source-derived style rules must cite evidence and must not copy source plots, dialogue, characters, or scene text into unrelated projects.
9. Character continuity uses reusable image references and stable character IDs, not a requirement to train a LoRA per character.
10. Use existing ComfyUI workflows and Video Repertoire/analyzer outputs when possible. Do not modify ComfyUI's environment or introduce a new vector database without a demonstrated requirement.
11. Narrative-style source ingestion is limited to `.pdf`, `.md`, and `.txt`. Image references and video references use separate visual/generation workflows and must not silently become plot/story sources.
12. No code/schema change may break manual editing of artifacts, current project loading, the two existing automation entry points, or audio automation.
13. Approved facts live in a versioned project bible (source story plus accepted artifacts and explicit overrides). The project graph is rebuildable indexing, never a second conflicting authority.
14. Generated images/audio/video live once in `output/<project_id>`; Video Repertoire remains the source/reference analyzer library. Manifests point to asset IDs, not copied payloads.
15. A run is durably recoverable: stages and tasks are idempotent, a process restart reconciles unfinished work, and a completed media result cannot be submitted twice merely because a UI/API retry occurred.

## 4. Long-output generation and token-limit handling

### 4.1 Generation coordinator

Add `services/generation_coordinator.py` (name may be adjusted after implementation inspection) between API orchestration and provider adapters. It owns:

- provider-specific input/output budgets and safety margin;
- semantic work-unit planning for each artifact type;
- chunk numbering, dependency IDs, idempotency keys, and retry state;
- structured response validation and assembly;
- checkpoints, resumability, run progress, and cost/latency/token metadata where available;
- repair requests for truncated or schema-invalid chunks.

Back this with a small durable run ledger (prefer SQLite in the existing project runtime, after migration tests), rather than relying on FastAPI `BackgroundTasks` and process-local pause flags. In plain language: each stage is a checked-off job with inputs, output ID, status, and attempt history. If the server stops after finishing scene 2, it restarts at the next incomplete scene, not at scene 1. Use a single canonical run record, transactional state transitions, leases/heartbeat for active workers, startup reconciliation for abandoned leases, idempotency keys for external media submissions, and a durable cancel/retry cursor. Keep existing JSON artifacts as readable content; the ledger tracks work and does not become a second copy of large media. Do not promise true pause in the middle of a GPU request; pause at safe boundaries and show an explicit stopping/waiting state.

Do not infer that a response is complete just because it parses as JSON. The coordinator validates expected coverage and required IDs/counts against the chunk plan.

### 4.2 Chunking by artifact

The stage plan should use units appropriate to each output:

| Artifact | Proposed bounded generation units |
|---|---|
| Story/world | First create a beat/act/chapter outline with stable beat IDs. Expand each beat/sequence separately into complete prose; assemble in canonical order. Preserve the submitted story verbatim as the immutable source. |
| Character bible | Generate the cast index, then complete character records in small batches. Assign stable IDs before image work. Do not truncate appearance, motivation, wardrobe baseline, relationships, or voice/performance notes. |
| Scenes | Produce a scene index from the approved outline, then expand each scene/sequence as complete records. Store scene count/order and transitions, not just a short generic scene list. |
| Sub-scenes/shots | Work scene-by-scene and beat-by-beat. Every shot gets its own stable ID, duration intent, continuity handoff, camera, lighting, blocking, emotion, and frame/audio needs. |
| Dialogue | Work per scene/sub-scene, then per dialogue beat where needed. Preserve every line, speaker, delivery, pause, and time intent. A final coverage pass checks that each planned beat has dialogue or an explicit no-dialogue reason. |
| Image jobs | Work per character reference, then per scene/shot frame. Each job points to the exact upstream character/scene/style revisions it uses. |
| Director contract/review | Review one scene or a bounded set of scenes at a time; merge decisions and run a final whole-project continuity check using compact graph facts plus exact relevant source artifacts. |

The shared base generation contract must explicitly tell the writer: “Do not shorten the assigned material to fit a response. Complete only the assigned unit, mark its stable ID and coverage, and request/continue with the next planned unit. Never claim completion while planned units remain.” This instruction supplements chunking; it does not replace it.

### 4.3 Truncation, validation, retry, and resume

- Set provider output limits explicitly when supported (`num_predict`/equivalent); keep a configurable safety margin under the provider context window.
- Treat provider stop reason, empty/incomplete content, invalid JSON, missing IDs, absent required fields, and incomplete coverage as distinct recoverable errors.
- Repair only the malformed/missing unit. A bounded retry policy records attempt number, reason, and output revision; repeated failure pauses/fails with an actionable message instead of silently returning a partial artifact.
- Persist `planned_units`, `completed_units`, `failed_units`, per-unit status, and cursor before/after each call. Resume starts from the first incomplete dependency-safe unit.
- Assemble stable ordered artifacts into the existing `artifacts/<type>.json` and `project.json` content fields after validation. Retain chunk files and assembly manifest for audit/debugging.
- Add configurable quality floors and output-size metrics, but do not require exact token counts from providers that do not expose them.

### 4.4 Proposed storage and one-copy asset ownership

```text
storage/projects/<project_id>/
  input/                              # existing uploaded/pasted source story
  artifacts/                          # existing assembled story/characters/scenes/etc JSON
  canon/approved.json                  # versioned accepted world/character/scene facts and provenance
  references/                         # only project-owned uploads not already stored elsewhere
  assets/characters.json               # canonical character sheet/voice bindings and accepted revisions
  assets/world.json                    # canonical locations/props/state variants, reference IDs and revisions
  assets/shots.json                    # shot contracts, reference mappings, audio ownership and output IDs
  generation/<run_id>/
    run.json                          # providers, style snapshot, prompts, stage status
    chunks/<artifact>/<unit_id>.json  # atomic completed outputs and validation
    reviews/<artifact>/<unit_id>.json # Director review, fixes, provenance, audit
    prompt_improvements/              # run-scoped proposals; never auto-edit source code
  graph/continuity.json               # derived lookup index, rebuildable from approved revisions
output/<project_id>/                  # ONE canonical home for this project's generated media
  characters/<character_id>/...       # generated/accepted multi-angle images
  world/<world_id>/...                 # generated/accepted environment/prop sheets and variants
  voices/<character_id>/...           # approved recorded/converted/synthesized dialogue, not copied bundled masters
  scenes/<scene_id>/...               # requested frames, voice/music/SFX mixes, video takes
video_repertoire/                     # external/downloaded/analyzed reference media only
```

Project manifests store stable IDs, canonical paths, hashes, and origin (`project_upload`, `generated_output`, or `video_repertoire_reference`). Selecting a repertoire clip links its ID/path and never copies it into the project. On deletion, resolve owned paths precisely: removing a project deletes only its owned state/output after confirmation; shared/repertoire references remain. An imported file is copied once only if the project must own that upload; any staging temp is deleted after promotion. Existing `project.json` stays compatible. The SQLite ledger lives under the project's storage area or a compatible existing shared data location with project IDs, and must never contain media bytes.

## 5. Provider-neutral text workers + one Director orchestrator

### 5.1 Role-specific provider contract

All story text roles use one typed task/result interface. The first adapter invokes Codex CLI for writer and model-backed Director tasks; future LLM adapters must satisfy the same schemas, timeout/cancel behavior, structured-output validation, and audit contract. Deterministic scheduling, dependency checks, schema validation, and asset/workflow preflight are ordinary code, not a second LLM “director.” One Director policy layer chooses assignments, approves/revises outputs, and owns the final stage decision. Do not route initial story tasks through Ollama; unrelated Ollama features remain untouched. Record explicit fields:

```json
{
  "text_provider": "codex",
  "writer_model": "configured model ID",
  "director_agent": "story_director",
  "director_provider": "codex",
  "director_model": "configured model ID",
  "review_policy": "deterministic_every_unit__model_review_on_risk_or_milestone",
  "run_mode": "manual | semi_automated | fully_automated",
  "semi_controls": {"image_selection": true, "voice_selection": true, "video_generation": true},
  "style_id": "production-type or type.variant",
  "style_version": 1,
  "prompt_contract_version": 1
}
```

The configured adapter is preflighted before a run. Each task receives only the source story/relevant excerpt, accepted upstream artifacts, style snapshots, continuity facts, requested schema/unit, and a completeness rubric. Use schema-constrained output where the provider supports it (the Codex adapter can use CLI output-schema support), then validate independently. On failure, retry only that unit with bounded repair instructions; preserve original and repaired revisions. A different provider can be selected for a *new* run/fork, but not injected silently into a running one.

### 5.2 Director behavior

For each generation stage, the Director builds a bounded task packet for the selected worker provider containing:

- immutable source story or relevant excerpt;
- accepted upstream artifact and approved canon facts (the graph only locates them);
- the current chunk's exact requirements and completeness checklist;
- the selected production type/style **Director behavior profile** and only the rules relevant to this stage, with citations;
- previous decisions/continuity constraints and any known uncertainties.

The Director produces a structured `director_brief` before every generation task: purpose, must-preserve facts, stage-specific creative targets, style constraints, required coverage, prohibited shortcuts, workflow constraints, and review rubric. The worker is instructed to complete the requested unit and explicitly signal continuation rather than compressing required detail to fit one response.

After each unit, deterministic checks verify schema, coverage, references, and unchanged approved facts. The Director then uses a model review only for failures, ambiguous style/continuity choices, high-risk changes, and stage milestones; other clean units receive a logged fast-path approval. A bounded review/repair task is followed by re-validation. This should not serialize unrelated ready work unnecessarily. Every decision records evidence and artifact/chunk IDs. All providers must distinguish fact from preference and must not invent unsupported source facts. Manual edits create approved or pending revisions and invalidate only downstream tasks whose input hashes changed; regenerate the derived graph after each accepted edit.

### 5.3 Learning from review without prompt drift

When the Director finds a recurring failure, it emits a structured prompt/code improvement proposal:

- observed defect and affected stage;
- supporting run/chunk examples;
- proposed prompt-pack change or code-level issue;
- expected behavior and regression test;
- before/after evaluation results.

Prompt changes are written as a new version in `prompts/` or the style library, evaluated against a small fixed regression suite, and promoted only if they improve target metrics without breaking existing fixtures. The active prompt version is recorded per run. Code-change proposals become a testable patch for normal engineering review; the runtime Director never executes arbitrary source edits while a story is running. Keep rollback to the previous prompt version straightforward.

## 6. Production-type taxonomy and nested style picker

### 6.1 Data model and compatibility

Treat the current six JSON files as **production-type base packs**:

- story/film;
- advertisement;
- informative/educational;
- news/reporting;
- social/profile;
- corporate pitch/meeting.

Add optional named variants under a production type. A category with no variants selects its base pack directly. A category with variants opens a nested panel/side submenu.

Suggested code-managed layout (preserve current flat files while migrating):

```text
prompts/styles/
  story_film.json                     # existing base pack, versioned
  advertisement.json                  # existing base pack, versioned
  ...
  story_film/<style_slug>.json        # optional checked-in/default variants
prompts/director_profiles/
  story_film.json                     # base Director vision for that production type
  advertisement.json
  corporate_pitch.json
  informative.json
  news_report.json
  social_profile.json
  <production_type>/<style_slug>.json # variant overrides, never a second director system
```

Suggested user-generated style library:

```text
storage/style_library/
  catalog.json
  <production_type>/<style_id>/
    v<version>/style.json
    v<version>/style_graph.json
    v<version>/evidence.jsonl
    v<version>/source_manifest.json
    v<version>/evaluation.json
    sources/<text-source-id>.<pdf|md|txt> # optional retained upload; otherwise keep provenance/hash only
```

Only text documents are accepted as narrative-style sources. Do not accept video/analyzer output as a source for the story-style builder. Visual references have their own project/library asset records (see §7) and are not copied into `storage/style_library`. Do not store credentials or private system prompts in style packs.

IDs are stable and names are editable. Use an unambiguous style key such as `story_film.neo_noir`; continue accepting old flat IDs such as `story_film`.

**Director vision is distinct for every production type and named variant.** A versioned JSON behavior profile accompanies each base pack and may have variant overrides. It defines: primary goal/audience, narrative shape, pacing and scene density, dialogue/performance expectations, camera/shot tendencies, audio priorities, allowed creative latitude, factual/evidence guardrails, stage-specific brief templates, review rubric, retake priorities, and workflow preferences that are *conditional on the installed capability manifest*. For example, a news report emphasizes source attribution and no fabricated facts; an advertisement emphasizes product claim discipline and a short call to action; a story/film variant can prioritize cinematic escalation and character arcs. These are different Director decisions, not merely different adjective lists. Resolve base profile → variant override → explicit project override; snapshot the resolved profile and its component versions in every run. Validate inheritance/conflicts and require every production type to have a tested base behavior profile before enabling the new route. Keep profile text concise enough to retrieve only its relevant stage slice.

### 6.2 Narrative-style profile schema

Each style profile should contain:

- identity: style ID/name, production type, parent/base style, version, status, created/updated timestamps;
- intended use and audience;
- narrative grammar: story shape, scene/beat patterns, point of view, pacing/rhythm;
- character/performance guidance: behavior, emotional range, dialogue rhythm/delivery;
- stage applicability limited to story, scene, sub-scene, dialogue, and performance;
- positive rules, negative rules, stage-specific instructions, exceptions, and uncertainty;
- source evidence references and confidence scores;
- a style graph/retrieval pack and evaluation prompts/results;
- prompt/schema version and any Director/reviewer-provider provenance.

Do not use a single opaque prose field as the only style representation. Keep structured machine-readable fields plus concise prose instructions so the Director can retrieve exactly the rules relevant to the current artifact.

Visual appearance, cinematography, music, and sound rules belong in separate visual-treatment/audio profiles or project assets unless the uploaded text explicitly provides such direction and the user elects to map those passages into a separate profile. Never let narrative prose style implicitly override the selected image/video treatment.

### 6.3 How a text document becomes a narrative style

1. **Choose a production type and text source.** Style Library accepts `.pdf`, `.md`, or `.txt` only. A plain story submitted to Story Builder remains the project's story input; it is not automatically treated as a reusable style source.
2. **Extract source text with provenance.** Markdown/text retain section/line ranges; PDFs retain page numbers and headings. Normalize layout artifacts without silently rewriting the source. Store a hash and optionally retain one uploaded copy under the style library; never create duplicate copies.
3. **Build evidence cards.** Break the text into compact records such as `{source_id, page_or_line_range, excerpt, candidate_trait, confidence}`. Separate explicit source rules from inferred observations.
4. **Distill narrative-only rules.** The selected text provider drafts a structured candidate under Director guidance and checks it against cited evidence. Extract story grammar, pacing, point of view, scene structure, dialogue cadence, emotional progression, and performance direction. Do not extract/reuse source plot, characters, dialogue, proper names, or factual claims as new-project content. The draft also proposes a *variant Director behavior override* (what the Director briefs/checks differently), not just writer-facing style prose.
5. **Construct a style graph/retrieval pack.** Link each rule to evidence and applicable stages (`story`, `scene`, `dialogue`, `performance`) using edges such as `supported_by`, `applies_to_stage`, `compatible_with`, and `conflicts_with`. Rules without direct evidence must be marked as a creative interpretation.
6. **Validate with a neutral sample.** The selected provider generates/reviews a small unrelated sample (for example, one scene and dialogue exchange) and checks whether the style is expressed without source-plot leakage or copying. Validate schemas, base/variant inheritance, and contradictions.
7. **Save and publish a version.** Save as a draft; the user previews and publishes it as an immutable version. Starting a run snapshots the selected version; later edits create a new version and never rewrite old project provenance.
8. **Apply stage-specific slices.** The Director retrieves only the relevant narrative rules for story, scene, or dialogue work. It does not pass an entire source document into every worker task.

### 6.4 Separate visual treatment and reference inputs

Narrative style and visual style must not be conflated. Add a visual-treatment selector to both Story Builder and Automation Studio. It starts with named text presets (`anime`, `photorealistic`, `LEGO-like`, `soft-toy`, etc.) and permits a user-authored visual profile. A visual profile contains medium/rendering, shape/material cues, palette, lighting, lens/composition, motion/camera language, continuity constraints, positive/negative rules, and stage applicability. These are instructions for character/background image prompts and video prompts; they do not alter the source-story text style.

Optional visual reference images can be attached to a character, environment, or scene/project. They guide appearance, palette, material, composition, or concrete frame anchors depending on the selected workflow. Save references once in the existing project/media asset area, with IDs and provenance; project artifacts store IDs/paths rather than embedding copies. A reference image is not automatically an editable layer or a guaranteed exact style transfer.

Store user-supplied visual references **once** under project-owned references only if no canonical repertoire asset already exists, for example `storage/projects/<project_id>/references/images/<asset_id>.<ext>` and `.../references/videos/<asset_id>.<ext>` (or the equivalent existing project media path discovered during implementation). Character and scene manifests store asset IDs, role, source, and hash. Generated character sheets and scene keyframes go under `output/<project_id>/`; do not create a duplicate project media tree.

Optional reference videos are generation inputs, not style-library sources. Only expose them when the selected provider/workflow supports them, and require the user/director to specify what to borrow: motion/action, camera movement, cut rhythm/temporal structure, visual subject, or direct edit/continuation. A reference video must not be described as a deterministic “replace the characters/background” operation. Reference generation can be instructed to transfer motion/camera/style while changing subject/environment, but the generated result is model interpretation and may retain or alter source elements unpredictably. If exact source preservation with replacement is required, classify that as a video-editing task and verify that the chosen model/workflow explicitly supports it; do not promise identity/background replacement from a generic reference-generation call.

For MiniMax H3, the plan must represent three distinct modes:

| Mode | Inputs | Intended role |
|---|---|---|
| Text-to-video | text prompt | Generate from scratch. |
| Image-to-video / first-last-frame | text + first frame and optionally last frame | Anchor the beginning/end and generate the transition. |
| Reference-to-video | text + reference images/videos/audio | Use visual/audio references for character, motion, camera, style, voice, or editing rhythm. |

Important API constraint: MiniMax H3 treats first/last-frame image mode and reference-to-video mode as mutually exclusive in a single request. The workflow picker must prevent combining them in one request; if both kinds of guidance are needed, the Director must choose a supported staged workflow (e.g. derive an approved still/reference first, then call the appropriate video mode) or report the limitation. The current official API documents up to 9 reference images, 3 reference videos (2–15 seconds each, combined ≤15 seconds), and 3 audio references (2–15 seconds each, combined ≤15 seconds), with file/dimension/request limits; validate against current provider limits at runtime rather than hardcoding unverified assumptions.

Provider-contract references to verify at implementation time: [MiniMax H3 Video Generation guide](https://platform.minimax.io/docs/guides/video-generation), the actual [Video Generation V2 task API](https://platform.minimax.io/docs/api-reference/video-generation-v2-create), and the [official MiniMax H3 full-reference prompt guide](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md). The [Context-IR API](https://platform.minimax.io/docs/api-reference/video-generation-v2-h3-context-ir) produces an enhanced prompt only and is not a generation endpoint. These documents distinguish reference generation from editing/continuation and define reference labels; they do not promise deterministic background preservation or subject replacement.

### 6.5 Style graph retrieval

The first implementation should use JSON graph/evidence retrieval and metadata filtering. Do not add vector embeddings or a new vector database for styles until evaluation shows that the style library is large enough to require semantic retrieval. If embeddings are later justified, store them separately from continuity facts and retain the source citations.

### 6.6 Narrative-style picker and library UI

Add a shared `ProductionStylePicker` used from both Story Builder and Automation Studio:

- first panel lists the production types;
- rows with variants show a chevron and open an adjacent/submenu list;
- selecting a base type with no variant selects that type's default pack;
- selected label clearly shows `Production type / Style variant` and version/draft status where appropriate;
- supports mouse, keyboard, focus management, touch/mobile, and accessible `aria-expanded`/`aria-controls` behavior;
- current active run locks the snapshotted style; changing style requires starting a new run or using the existing paused-run style-change/fork flow if implemented;
- a “Manage/Create style” action opens the Style Library workflow;
- no style choice silently changes the production type or alters completed project artifacts.

Add `frontend/app/src/pages/StyleLibrary.tsx` as a dedicated narrative-style author/manage page linked from the style picker and AppShell. It supports `.pdf`/`.md`/`.txt` upload, extraction progress, page/line evidence review, candidate narrative-style preview, version history, and publish/archive. Visual-treatment presets and image/video reference attachment are separate UI controls, not source-ingestion options in this page.

## 7. Persistent character/world assets and selective shot anchors

### 7.0 Two making routes (plus shot-level Hybrid)

| Making route | Preparation | Typical H3 shot | Trade-off |
|---|---|---|---|
| **Direct H3 — fast/text-led** | Approved story, stable character/world *text* bible, short descriptive character/location briefs, scene/shot beats, and bound voice samples. Do **not** run an image-generation stage just to satisfy this route. | New scene: R2V text + only needed voice references, with no prior-video continuity input. Subsequent cut in the same scene: use a short approved tail of the previous generated shot as `ref_video_N` and, where useful and clean, its *paired* soundtrack. Add the relevant current-character voice samples if a new speaker appears or voice identity needs reinforcement. | Faster and less storage/compute, but text-only characters/rooms can drift or be recast across fresh scenes. The Director compares results with the text bible and prior accepted shots; it may recommend or create a minimal still anchor after explicit route/policy approval, but it must not pretend text alone locks visual identity. |
| **Reference-built — controlled/asset-first** | Generate base designs with **Qwen Image 2512** or the separately identified **Z-Image Turbo** workflow; use a *verified* Qwen Image Edit 2511 adapter for accepted character multi-view sheets and world/location/prop boards. Selectively make first/last frames for FL2VA shots; use image/world/voice/video references in the dynamic R2V graph for other shots. | Director selects only the accepted character/world/action/voice assets relevant to this shot. A following cut may additionally use a short previous-shot tail and optional paired audio. | More consistent and controllable, but requires image review, more GPU time and more project assets. It is not a requirement to put all possible references in every shot. |
| **Hybrid — recommended for longer stories** | Start Direct H3 for exploratory or low-risk shots; create reference masters only for recurring characters, signature places, or shots that fail continuity checks. | Route each shot to T2V, FL2VA, or dynamic R2V according to its actual needs and tested graph capability. | Saves preparation while giving the recurring elements a stable visual anchor. Track when an accepted master supersedes an earlier text-only depiction and invalidate only dependent future shots. |

The UI offers a **Making route** selector independently of Manual/Semi/Full control mode, with a per-shot override and a clear estimated preparation/render cost. A route switch never overwrites an accepted take. The Direct H3 route still needs a *detailed H3 shot prompt*; it merely skips separate image-generation prompts and visual-master creation unless a later shot requires them. Stable text descriptions, speaker IDs and world-state facts remain mandatory for the Director. A fresh scene starts a new local continuity chain; it does not ingest the prior scene's MP4 merely because that file exists. If an established character crosses into the fresh scene, the Director may reuse an approved character still/master when available, but the pure text-only route openly accepts weaker visual identity.

### 7.1 Character reference stage

For Reference-built shots, and the specific characters that Hybrid elevates to masters, create image jobs per stable `character_id` using a preflighted ComfyUI image workflow catalog after characters are approved as structured text:

- generate a canonical neutral design/reference first;
- derive additional angles/expressions using that accepted image and the character bible, not a fresh text-only reinvention;
- save accepted and rejected outputs with workflow/model/seed/prompt/style provenance;
- the Director checks identity, wardrobe, age cues, distinctive features, and forbidden drift across angles using image comparison and targeted model review where needed; retry only a failed view a bounded number of times;
- no per-character LoRA is required or silently trained.

Generated project assets live under `output/<project_id>/characters/<character_id>/`. A manifest under project storage holds stable reference IDs, canonical paths, and accepted status. These references are passed to scene image jobs without copying them.

### 7.2 World/location reference stage — the missing global visual memory

Build a project-scoped **text world bible** from approved story/scenes for **all** routes. Give every recurring location, prop, vehicle, costume state, and lighting/time-of-day state a stable ID, description, relationships, and rules: floorplan/geography, entrances and screen direction, palette/materials, persistent damage/weather, and what is allowed to change over time. This is approved project canon; the graph indexes it but is not its authority. In the Reference-built route, or selectively in Hybrid, create one accepted establishing image or reference board for each recurring environment, then optional relevant interior/exterior angles and lighting variants. Use a verified Qwen image/edit adapter as a candidate; edit from the approved master rather than asking text-to-image to reinvent the same room. A Qwen edit is generative and does **not** prove geometry is identical: validate doors, windows, layout, props and perspective before accepting it. A multi-panel sheet may conserve H3 reference slots, but a targeted crop/single view may outperform a dense unreadable sheet; benchmark both. In Direct H3, retain the same world-state IDs and descriptive canon but do not make the board a prerequisite to rendering.

The project manifest stores asset role, canonical path/hash, workflow/model/prompt/seed, accepted revision, and dependencies. Generated world assets live once under `output/<project_id>/world/<world_id>/`; an external Video Repertoire reference stays in the repertoire and is linked by ID. Scene records refer to world IDs plus current state (e.g. stormy night, broken window). A rejected/updated world asset invalidates only dependent frames/shots, not unrelated scenes. UI: add a **World & props** stage/gallery alongside Character references, with approve/replace, state variants, and a per-scene reference shortlist. This creates global visual memory without putting the entire image library into every H3 request.

### 7.3 Selective scene-frame stage

Do **not** generate first and last frames for every shot. The Director first selects the shot's likely workflow. Create endpoint frames for FL2VA shots, a first/transition frame when a prior shot's last frame provides useful continuity, or timeline keyframes only for a verified Add Guide workflow. R2V shots receive only the relevant images/video/audio selected by their making route; Direct H3 may have voice audio without any character/world images. T2V needs no reference asset. Keep optional thumbnails for browsing distinct from conditioning frames. For each requested frame, include character IDs, world state/props, camera/lens, lighting, palette, emotion, and intended transition. Add intermediate frames only when a verified timeline-guide workflow benefits from them.

The Director reviews frame candidates against the style pack, character and world masters, previous/next approved scenes, geography, wardrobe, props, camera, and emotion. A failed frame triggers only that frame's bounded regeneration. Store prompts, image hashes, workflow IDs, candidates, accepted image IDs, and review reasons in the project.

## 8. Downstream audio/video handoff

The authoritative scene contract becomes the source for dialogue, music, Foley, frame prompts, and MiniMax H3 prompts. Store durations and all dialogue/music/SFX events on a common scene timeline. Clip duration must derive from the planned shot/audio timing and be validated against the selected workflow limits.

The Director chooses **shot duration and quality target**, rather than applying one duration preset to every scene. It first budgets spoken words, pauses, action beats and transition time; then splits a scene into adjacent shot units whenever it exceeds the selected workflow's tested duration. It records target duration, resolution/quality tier, aspect ratio, seed policy, reference roles and an estimated GPU/time cost before submission. The user may override these in Manual/Semi within real workflow limits. In Fully automated, start at the highest preflighted quality tier allowed by the project's run policy and available GPU, with a bounded lower-cost preview/retake strategy only when explicitly selected. A duration or quality setting is never displayed unless the active workflow actually exposes it.

The selected workflow receives only the supported subset: (a) text; (b) text plus first/last frames; (c) text plus supported reference images/video/audio; or (d) locally, a separately proven R2V + timeline-guide/control combination. The Director chooses among valid modes according to the shot goal; it never assumes the hosted API permits the same combinations as newer local ComfyUI nodes. Separately generated TTS/music/SFX are timed production assets even when the video workflow does not accept them as conditioning inputs. The final clip audio policy explicitly records generated H3 audio vs TTS/converted/clone-synthesized take vs soundtrack mix, including replacement/mute decisions. Scene duration comes from the approved timeline and the active workflow's limits; longer scenes are split into stable shot units.

Do not claim a workflow consumes reference audio if its API graph does not accept it. Workflow capability manifests determine required/optional slots; validate missing references before submission. Record exact workflow, inputs, seeds, run IDs, outputs, timing, and retry/failure reason.

### 8.1 Director-led, workflow-aware MiniMax H3 routing

The Director must know the selected ComfyUI workflow/API contract before writing the final generation prompt. Maintain a workflow registry populated from the actual installed workflow/API JSON, with each input's type, role, cardinality, limits, required/optional status, and meaning. A provider/model label alone is not sufficient evidence that a workflow accepts a given combination.

| Scene need | Preferred conditioning | Director prompt responsibility |
|---|---|---|
| Unconstrained establishing/montage shot | T2V, with approved world/character facts in text | Allow invention within canon; avoid spending reference slots without a reason. |
| Slow/simple shot needing controlled opening/ending | FL2VA text + first/last frame in a verified local graph | Describe the continuous action/camera between anchors; do not assume endpoint frames control choreography or persistent voice. |
| Character/world consistency or dialogue-heavy shot | R2V with relevant character/world image shortlist and, once a new versioned graph is validated, up to the needed voice/dialogue references | Map `<Picture N>` and `<Audio N>` to stable character/speaker IDs. Keep only references useful to this shot; do not fill every slot. |
| Action/fight/dance with no chosen action clip | Text or R2V with identity/world images, with explicit action beats | No external video is silently chosen in full automation; a Director-created control asset is allowed only after a tested route exists. |
| Choreography/camera from a chosen clip | R2V with user-selected reference video and character/world images; optional Pose ControlNet only after its separate checkpoint/runtime gate | State what transfers and what must change; ordinary R2V is approximate motion transfer, while pose/depth/canny impose stronger constraints but still are not frame-perfect actor replacement. |
| Next cut directly continues previous approved shot | Current route: prior last frame in FL2VA, or prior video as R2V reference after the new graph test. Future route: Add Guide previous tail frames plus matching audio once installed | Preserve state, direction and master identity/world references; this is input chaining, not final film stitching. |
| Exact spoken performance | Local TTS, accepted recorded take, local voice-converted take, or explicitly configured hosted clone/TTS; feed to H3 only after a tested audio-capable graph, and keep external mix as fidelity fallback | Distinguish `reference` timbre from intended `fully_copy`/`partially_copy` reuse. Do not treat those prompt markers as a guaranteed audio-copy API switch. |

For H3, use its documented task distinctions: T2VA (text), I2VA/FL2VA (first/last image anchors), and Ref2VA (reference images/video/audio). The **hosted API** says frame-anchor mode and reference-role mode cannot be mixed in one request. Local ComfyUI may combine R2V with `MiniMaxH3AddGuide` (guide image/clip/audio on its timeline) but only after that node and the exact workflow are installed and tested; this is not a claim that hosted API constraints disappeared. Reference-video generation is guidance/transfer, not guaranteed pixel-preserving actor replacement. Direct video editing/inpainting is distinct. Limits come from the *active backend*: hosted H3 permits up to 9 reference images, 3 videos (each 2–15 seconds, total ≤15 seconds), and 3 standalone audios (each 2–15 seconds, total ≤15 seconds), but the local workflow/model may have additional frame-grid, VRAM and performance limits.

**Current installation versus public H3 capability (read-only audit, 2026-10-01):** `services/manual_director.py` exposes `minimax_text` (text), `minimax_references` (1–3 images), and `wan_first_last` (two frames); `workflows/api/minimax_h3_i2v_api.json` exists but is not mapped there. Yet local ComfyUI `comfy_extras/nodes_minimax_h3.py` exposes `MiniMaxH3ReferenceToVideo` autogrow slots for up to 9 images, 3 video-frame batches, 3 paired video soundtracks and 3 standalone audio clips. The graph simply does not connect them. The FL2VA and Ref2VA diffusion models, H3 text encoder, and AV VAEs are present. `MiniMaxH3AddGuide` is **not** in the installed H3 node file; the Fun ControlNet patch and pose/detector models were **not found** in the inspected model folders. Therefore **R2V with audio/video should be the first new versioned graph**, while Add Guide and ControlNet are optional later capability gates involving possible ComfyUI/model changes. Before enabling each, inspect live `object_info`, wire precise slots and media preprocessors, validate runtime/VRAM/quality, and run a real shot; do not mutate tested graphs or ComfyUI in place. H3 Context-IR returns an enhanced prompt, **not video**, and is hosted/optional.

Local H3 uses a 24-fps `17k+5` frame grid and about a 768-pixel short-edge native canvas in the documented ComfyUI templates. Documented standard graphs use about 20 sampling steps; turbo lowers steps and can reduce audio/motion fidelity. Start with a cheap composition preview **only when the user/run policy permits it**, then a full-step final for identity/dialogue-critical shots, rather than promising hosted 2K detail from local 768p generation. Measure local max concurrent model footprint; serialize incompatible GPU stages and unload idle models where supported. None of these quality settings are universal—read the selected graph manifest.

#### Dynamic R2V API graph: Director chooses roles, compiler connects nodes

Do **not** let the Director/Codex freely edit ComfyUI JSON. The Director emits a typed, versioned `reference_plan` for the shot: ordered image assets (0–9), video assets (0–3), a Boolean `include_paired_soundtrack` per video, standalone audio assets (0–3), each asset's role/subject/speaker, prompt intent, duration, resolution preset, `ref_image_size`, steps and seed. A deterministic **graph compiler** validates that plan and builds a temporary API graph from an immutable, checksum-pinned R2V base. It may clone only approved loader/preprocessor nodes and add their typed links to `MiniMaxH3ReferenceToVideo`; it never edits `workflows/ricky/*.json` or a tested API graph in place. Preserve the sampling, video/audio VAE decode, `CreateVideo`, and `SaveVideo` chain. Save the compiled graph, asset hashes, node version, reference map, and ComfyUI prompt ID in the shot audit so any output is reproducible.

For each requested image, add one `LoadImage` and connect sequential `ref_images.ref_image_0..8`. For each requested video, stage the canonical project/repertoire asset into the ComfyUI input mechanism **without creating a second permanent project copy**, then add one validated video loader/resampler, connect its IMAGE/frame-batch output to `ref_videos.ref_video_0..2`, and—**only when the soundtrack is deliberately used**—connect the **same loader's** AUDIO output to matching `ref_video_audios.ref_video_audio_N`. This fixes the two-loader mismatch in `vid_minmax_h3_r2v_crazy.json`. Convert/sample to the H3 node's expected 24-fps timeline, trim to a Director-chosen short interval, and verify frame/audio duration and sync before submission. For each standalone voice/performance input, add a validated audio loader and connect sequential `ref_audios.ref_audio_0..2`. Do not connect separate BGM/SFX tracks as voice references merely to fill slots. An absent optional reference means **no node/link**, not a blank `LoadAudio` widget.

The compiler must calculate tags from the **actual connected references** after graph construction, never from a hard-coded template. H3 sees pictures first, then for each video its paired audio immediately before that video, then standalone audios. Thus one video with soundtrack plus two independent voice files yields `<Video 1>`, `<Audio 1>` = its soundtrack, `<Audio 2>` = first voice, `<Audio 3>` = second voice. If the video soundtrack is disconnected, the first voice becomes `<Audio 1>`. Store this mapping explicitly and insert it into the Director's prompt brief; validate that every connected reference has a purpose and every prompt tag resolves to the intended asset. Stable `(S1)`/`(S2)` speaker identities are a **separate** mapping to characters/voices, not inferred from `<Subject N>` or a loader index.

Preflight local `object_info` and the ComfyUI API-export schema for autogrow input names, loader types, file staging, installed node versions and model IDs. Refuse an unsupported combination with a precise message. Enforce local slot maximums (9 image, 3 video, up to 3 matching video soundtracks, 3 standalone audio) and separately enforce the selected backend's total-duration/file limits; **do not assume local node slots automatically prove hosted API constraints or GPU feasibility**. Benchmark the combined reference-token/VRAM cost and trim/reduce references when necessary; never silently discard one. Keep a small collection of golden compiled graphs and a test that compares their endpoint wiring to the existing working R2V core.

The requested `0.98` is the **Resolution Selector megapixel preset**, not a general quality score. In Ricky's selector note it maps to 1344×768 at 16:9; `0.4` maps to 864×480 and currently overrides the H3 node's displayed 1344×768 default in the crazy graph. Use `0.98` as the **final-render default** only after the exact exported API graph and live GPU preflight confirm it; allow a clearly labelled lower-resolution preview. Quality is separately affected by steps/scheduler, reference clarity, `ref_image_size` (`match` preview versus tested `max` hero identity), and acceptance review. Preserve manual parameter overrides within the selected graph's tested limits.

#### Versioned H3 prompting corpus and continuity rule

Create project-readable, versioned H3 rules under `prompts/minimax_h3/` (e.g. `reference_roles.md`, `shot_prompt_contract.md`, `examples.json`, and `workflow_capabilities.json`). Distill the official MiniMax/ComfyUI guides into **original concise rules**, not copied long passages: define every `<Picture N>`, `<Video N>`, `<Audio N>` and subject; state what each contributes versus what must *not* transfer; keep `(S#)` stable per voice; place spoken text inside `<d>[language] ...</d>`; describe shot-by-shot action, camera, lighting, world, timing, native sound and omissions; specify `reference`, `partially_copy`, or `fully_copy` as intent while acknowledging none alone guarantees exact waveform reuse. Examples cover text-only new scene, one-character dialogue, two-speaker dialogue, previous-shot continuation with/without paired audio, reference choreography, and FL2VA endpoint composition. The Director reads the **resolved rule/version and actual reference map before writing a shot prompt**, and the prompt compiler checks missing/incorrect tags, conflicting voice roles, impossible shot duration, and unsupported workflow roles. Save the rule version with the run; test improvements against fixed shots before promoting them.

For **same-scene cut 2 onward**, the recommended continuity candidate is a short **approved tail** of the immediately previous shot as one R2V video reference, optionally with its own synchronized audio if that audio is relevant and clean. This is not an automatic entire-clip dump: the node interprets reference frames at 24 fps and truncates frames beyond the requested output length. The Director chooses the excerpt (often a few seconds), role (state, motion, camera, or sound continuity), and whether to include its soundtrack; a prior soundtrack containing obsolete dialogue or music may contaminate the new cut, so omit it when inappropriate. Keep approved master images/voices in Reference-built/Hybrid shots; in Direct H3, keep the approved text bible and voice bindings, while disclosing greater drift risk. A **new scene** starts without a previous-scene video continuity input unless the Director explicitly plans a narrative match cut; it still carries global canon/style and any accepted character/world anchors relevant to that scene. Ref video guidance is not the same as an Add Guide continuation anchor and does not promise a seamless cut.

H3's native soundtrack is always captured with its shot video. Its generated dialogue, Foley and music are **provisional shot audio**, not assumed final stems. Prepare separate dialogue performances when exact words/voice matter. Generate separate background-music and SFX candidates **only when requested by the production contract or Director** and save them as independent timestamped project assets for the future Hyperframes edit; do not feed BGM/SFX into `ref_audios` by default and do not silently add them to the H3 shot. Record whether a shot uses H3-native sound, a selected voice reference, a prior-video paired soundtrack, or an approved exact take. Hyperframes assembly/stitching is deferred, but manifests must keep these assets aligned and avoid irreversible destructive mixing.

### 8.2 Voice catalog, random automation, and dialogue policy

The current read-only source is `/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/custom_nodes/TTS-Audio-Suite/voices_examples/`. Its 26 audio files were inventoried on 2026-10-01. `services/audio_catalog.py` additionally searches ComfyUI `models/voices` and `models/TTS/voices`, but the inspected local examples are the confirmed assets. Only an adjacent non-empty reference transcript makes a file discoverable to the current TTS suite. The nine `vibevoice` files and `crestfallen_original.mp3` lack such companions; the long MP3 is not a clean short voice example. Two `vibevoice` filenames indicate background music; exclude them from a clean-speech voice pool until audition/preparation. Descriptions supplied in this project's [`plan/voice_catalog`](voice_catalog/README.md) are filename/README/FFprobe-derived and **not** claims that we listened, measured emotion, verified identity, or proved license/consent. The catalog has one JSON file per audio file, stores its original absolute path without copying audio, and marks unknown traits explicitly.

- At character-building time the Director writes a voice *brief* and assigns a stable character/speaker ID. The initial Fully automated policy is **seeded random selection**, once per character/run, from voices that pass technical eligibility (file exists, correct backend, usable transcript, language if required, quality/consent flags); it does **not** use semantic mood/age similarity to rank them. Store seed, eligible pool IDs/version, selected voice ID, and binding. Never reroll on each line or retry. If the pool is empty, surface an actionable missing-voice state; do not silently use a bundled celebrity-named sample or change backend.
- In Semi/Manual, the user can audition/filter and explicitly choose any *eligible* voice; if they choose a currently ineligible file, show why and what transcript/preparation is required. Manual selection overrides random binding for later dialogue, with provenance. Descriptors such as presentation, age impression, texture, emotion, accent and speaking rate remain editable, confidence-marked metadata; no gender/real-person assertion is inferred from a filename alone.
- Exact new dialogue remains text plus language, speaker ID, delivery, pauses, and timing in the approved scene contract. The existing TTS workflow can generate line/turn audio and bind it to the chosen voice; save each accepted audio once under the project output. Preserve approved TTS and separate optional music/SFX with timestamps for a later Hyperframes final mix; the H3 shot's native soundtrack remains independently available. When an H3 audio-reference workflow is verified, expose a per-shot option for `timbre_reference`, `reuse_exact_audio`, or `generated_voice`; require an explicit future-mix rule and prevent double dialogue in any preview/render that combines tracks. H3 public 2–15-second reference-audio limits do **not** mean a 30-second Voice Store example can be passed directly; prepare a compliant excerpt only when that route exists.
- Source-file provenance, terms/consent, and possible impersonation risk are separate from technical eligibility. Celebrity-like filenames are only labels; do not claim they are authorized real voices. The user can replace the initial catalog metadata after listening. No audio files or ComfyUI packages are changed by this plan.

#### Three different ways to make a character speak

| Path | Input and result | What is available now / gate |
|---|---|---|
| **Local TTS (default)** | Approved line text + selected local reference voice + timing → generated spoken line | Existing `services/audio_tts.py` and timed multi-character TTS workflow; live voice availability and language must be preflighted. |
| **Recorded performance → local voice conversion** | User records the exact words, pauses, and acting → `services/audio_effects.py` `voice_changer` targets a discoverable reference voice, or `rvc` uses a *specific installed RVC model/index* | Already exposed in Audio Studio/Audio Automation, with raw/accepted takes in Audio Reconstruct. Preserve original take; verify transcript, timing, intelligibility and identity after conversion. RVC is not arbitrary sample-based cloning without a suitable model. |
| **MiniMax Speech 2.8 hosted clone → TTS** | Upload authorized clean 10-second–5-minute source (MP3/M4A/WAV, ≤20 MB), optionally a separate <8-second example, create hosted `voice_id`, then synthesize exact script through the Speech API | **Not currently an app/local ComfyUI integration.** Requires explicit external-upload opt-in, account/API key, cost/usage approval, rights/consent check, and a separately tested service adapter. Never upload a bundled or repertoire voice automatically. Store opaque hosted ID and service/provenance metadata, not the API secret. Keep local TTS/voice-conversion path working if hosted service is not configured. |

The project's **master voice identity** is an app-level stable ID with clean source/accepted examples and optional links to a local TTS voice, local RVC model, or hosted MiniMax `voice_id`; these are different backends and are not interchangeable tokens. A canonical character may also retain recorded takes and generated dialogue lines. A 10–300-second hosted-clone source and a 2–15-second H3 reference clip have different purposes/limits; generate a clean short excerpt for H3 if needed, not a second full master copy. For Manual/Semi the user chooses backend and voice/performance per character or line. Fully automated stays **seeded-random among eligible local voices** by default (latest user decision); it does not silently clone/upload, and it can reuse a previously user-approved hosted voice ID only if that backend was explicitly enabled for the run.

If exact dialogue is pre-generated, prepare a **shot-level dialogue track** from accepted per-speaker takes with fixed timecodes, room tone and deliberate gaps; keep music and Foley separate for mixing. A verified R2V graph may receive that track as an audio reference/guide, with `<Audio N>`/`(S1)` mapping and a `fully_copy`/`partially_copy` intent in its prompt. **Do not assume that instruction preserves the waveform or perfect lip sync.** Compare output against the input, then choose the accepted final-audio policy: (1) keep H3 audio if it matches, (2) mux the exact original dialogue track and retain only wanted H3 ambience, or (3) replace H3 audio entirely and mix the approved dialogue/music/SFX. Align video to audio where possible; final mux is the fidelity guarantee. For two or more speakers, keep stable `(S1)`, `(S2)` IDs, minimize voice references per shot, and flag wrong-speaker/lip-sync results for retake or external mix; H3's own prompt guide warns that reference voices can attach to the wrong speaker.

### 8.3 Automation mode and staged production UI

Add a **control-mode** selector with three modes: **Manual**, **Semi-automated**, and **Fully automated**; independently add a **Making route** selector: **Direct H3 (fast)**, **Reference-built (controlled)**, or **Hybrid (per-shot)**. Text planning remains Director-guided generation through the selected text-provider adapter (Codex initially) in all modes/routes; “Manual” means manually controlled **media decisions**, not that the user must write every artifact. Show an estimated preparation/storage/GPU difference and a per-shot route override. Present a persistent, resumable workspace with stages rather than a single long form:

1. **Text & direction:** story/world canon, characters, locations/props, scenes, cut/shot plan, dialogue, emotion, camera, lighting, audio timing, per-scene image/video prompts, and Director reviews. Long outputs use the chunk/checkpoint system. Save and show each artifact as soon as approved.
2. **Character, world and selective shot images:** In Reference-built and selected Hybrid shots, prompts are prepared by the configured text worker under Director guidance and dispatched through the chosen, preflighted ComfyUI image API workflow. Build/accept reusable character and world masters first; then make frames only for shots requiring anchors. Qwen 2512, Z-Image Turbo, and Qwen Edit 2511 are distinct choices with distinct verified adapters, not aliases. Manual/semi mode makes four candidates per requested image and asks the user to select; automated mode makes one candidate, with a bounded Director-requested retake using a new seed/adjusted parameters when needed. Do not let the Director silently choose among user-requested manual candidates. **Direct H3 skips this generation stage** while still displaying text-only character/world canon and any previously accepted assets.
3. **Voices and audio:** at character-building time, the selected text provider creates a concise voice brief for each character. Populate auditionable voice samples from the project-side metadata overlay and available TTS assets, with uncertain descriptors marked as such. Semi/manual mode lets the user audition/select and binds the stable voice ID to the character; full automation makes one reproducible random choice from the eligible voice pool and records seed/pool/selection. The brief guides performance but does not silently change that random policy. Generate exact dialogue with the tested TTS route, plus music and SFX through configured audio workflows, all with scene timestamps and voice identity binding.
4. **Shot-by-shot video generation and review:** show the Director-prepared H3 prompt and resolved `<Picture>/<Video>/<Audio>` mapping, selected making route, shot duration, workflow recommendation/selector, workflow-specific controls (H3 frame-grid duration, `0.98` final resolution preset, reference-image sizing, steps/scheduler/seed where exposed), required/optional slots, shortlists of approved character/world/shot assets, semantic Video Repertoire results, and upload/browse controls. For a same-scene follow-up cut show the previous-tail video and **separate include-paired-soundtrack** decision. Display limits and missing required inputs before Run; do not silently substitute assets. Show reference-audio/video slots only for a preflighted compiled graph. Save one canonical output per accepted take plus lightweight run metadata; the Director checks action, identity, world continuity, speaker/audio ownership and ending state before moving to the next dependent shot. Prior-shot **input** continuity is in scope via supported routes; final-film attachment/stitching/Hyperframes editing is deferred.

When Semi-automated is selected, expand a collapsible section with three independent controls: image candidate selection, voice selection, and video generation/reference selection. For each enabled control, prompt the user at that stage; disabled controls follow the full-automation policy. Manual mode means user-operated asset/workflow actions while the configured text worker still prepares text/prompt artifacts under Director guidance. Fully automated mode performs selection and generation under explicit policy, except external action-reference video selection remains off unless a user supplies/approves it.

Persist page position, run mode, enabled semi controls, approvals, chosen asset IDs, workflow, parameters, generated outputs, and pending actions so navigating away does not lose state. A manual choice is project-scoped and becomes an auditable input to subsequent Director/worker tasks.

### 8.4 Explicit Manual, Semi, and Fully automated paths

All modes share one approved canon, asset registry, shot contract and durable run ledger. Switching mode at a safe boundary changes **who decides**; it does not create a different media pipeline or duplicate outputs. Every shot gets a signed `shot_plan` containing: beat/scene IDs, cast and world-state IDs, text prompt, spoken lines with `(S#)` IDs and timing, requested voice backend, reference shortlist and roles, selected workflow/version, frame/audio/video slot mapping, duration/frame count, output quality/steps/seed, soundtrack policy, previous-shot dependency, acceptance rubric, and fallback if a capability is unavailable. Freeze input hashes before submission.

| Decision | Manual | Semi-automated | Fully automated |
|---|---|---|---|
| Story/canon/shot text | Director drafts and checks; user may edit/approve | Same, optional review points | Director approves after checks; no mandatory user gate |
| Character/world visual masters | In Reference-built or chosen Hybrid shots, user can upload, edit, choose one of four candidates and lock it; Direct H3 keeps text canon only | User chooses only when the image-choice toggle is on and an image is requested; otherwise Director selects/retries | Director creates/locks only assets called for by the selected making route, with Direct H3 generating none by default |
| Voice and dialogue source | User auditions/chooses local voice or eligible recorded-take/hosted option; can replace exact lines | User chooses if voice toggle is on; otherwise one saved seeded-random local voice per character | One saved seeded-random eligible local voice per character; TTS exact dialogue by default, no automatic hosted clone/upload |
| Video workflow/references | User sees Director recommendation, can pick valid T2V/FL2VA/R2V, refs, params and run/retake | User picks workflow/refs/Run if video toggle is on; otherwise Director submits valid planned shot | Director routes each shot, uses approved project assets/previous shot only; never picks an external action video without prior explicit approval |
| Output approval | User chooses/accepts take; can edit plan and rerun only the shot | User approves enabled-gate outputs; Director fast-paths others | Director checks and accepts or bounded-retakes; uncertain/unsupported cases surface as actionable paused work |

**Manual walkthrough:** choose/edit the story and production/style profile, then the making route → inspect text canon/world; approve character/location sheets **only if Reference-built or a Hybrid shot calls for them** → audition/bind voices or record a line and convert it locally → inspect shot board and resolved H3 reference tags → choose a valid workflow and slot mapping for Shot 1 → preview/final render and review native audio against any exact dialogue take → approve, then repeat for Shot 2 using an approved previous-shot tail only if same-scene continuity and the supported graph call for it. The system never silently changes the user's chosen workflow, voice, references or quality. It can recommend alternatives and explain missing inputs.

**Semi walkthrough:** user chooses any subset of the three existing gates. Example: choose Direct H3, choose both voices personally, and control the R2V video reference for action shots; the image gate is skipped because this route requests no image assets. The Director completes text/world preparation, pauses durably at the Voice gate, resumes after the user binds voices, then pauses at each Video gate with prepared prompt and candidate references. A Reference-built choice instead activates image candidate selection as configured. Untoggled stages follow exactly the full-auto policy. A user-selected action video is treated as a reference asset, not as a narrative-style source.

**Full-auto walkthrough:** Director builds text/canon → follows the selected Direct H3, Reference-built or Hybrid preparation policy → selects stable random eligible local voices and generates timed TTS when exact lines are required → plans each 4–15-ish-second shot under *local tested* duration/frame-grid limits → chooses T2V for unconstrained shots, FL2VA for composition-led shots, or compiled R2V for text/identity/world/dialogue references once graph-tested → submits/validates Shot 1 → for a same-scene Shot 2, may use a short accepted tail with optional *relevant* paired audio via supported R2V, while keeping text canon and any accepted masters/voice bindings → makes bounded targeted retakes → saves prompts, outputs and decisions. A fresh scene does not inherit a previous-scene MP4 by default. No automatic voice cloning of unapproved material, no hidden download/repertoire action-video choice, and no unsupported Add Guide/ControlNet selection. If dialogue audio cannot be conditioned in H3, retain the exact take as a timestamped project asset for later mixing rather than dropping the line.

### 8.5 Workflow toolbox and rollout order

1. **Now: tested T2V, current image-only R2V, current H3 I2V graph (after app adapter), and WAN first/last.** Preserve their known behavior and do not claim cross-mode combinations.
2. **First extension: new versioned H3 R2V audio/video graph.** Reuse existing installed H3 node/model files, adding `LoadVideo`/audio-loading and preprocessing connections that deliver a 24-fps frame batch plus optional paired soundtrack and standalone audio. Verify ordering of `<Picture N>`, `<Video N>`, `<Audio N>`, limit enforcement, prompt binding, GPU cost and actual results. The exact loaders must be chosen from local `object_info`, not guessed. This route can be added without changing ComfyUI's Python packages if local loader/node preflight succeeds.
3. **Later/optional: Multiframe/Add Guide.** It can place still/clip and audio anchors at chosen 24-fps frame indices and can help continuation, but `MiniMaxH3AddGuide` is absent locally. First inspect the required upstream ComfyUI change and dependencies; seek separate approval before touching that environment. Version a new workflow, validate crop/frame-grid behavior and compare continuity against simpler R2V/last-frame methods.
4. **Later/optional: Fun ControlNet Union.** Pose/Depth/Canny/HED/MLSD are stronger action/geometry controls, but the patch, pose estimator and detector checkpoints were not found locally. Keep it unavailable until license, architecture/VRAM, model and live smoke preflight pass. Do not install into ComfyUI merely because the documentation lists it.
5. **Optional hosted H3/Context-IR adapters:** hosted API is a different cost/privacy/credential path and maintains first/last-versus-reference exclusivity; Context-IR outputs a better prompt, not video. Neither is an implicit fallback to local failures. The user must explicitly opt in and set budget/upload policy.

Order the tests around **one full scene**, not a giant film: two characters, one recurring room, two adjacent dialogue/action shots, distinct voices, one exact recorded/converted line, one R2V shot with real audio/video inputs after graph extension, and one continuity handoff. Capture prompts, input slot mapping, audio pre/post waveforms, resulting video, known limitations, peak GPU and elapsed time. Promote each toolbox entry only after it beats or materially expands the known-good route on this fixture.

## 9. Planned code, API, and UI changes

### Backend

| File/new file | Planned responsibility |
|---|---|
| `services/generation_coordinator.py` (new) | Chunk plan, bounded provider requests, validation, retries, atomic checkpoints, assembly, resume. |
| `services/production_run_store.py` (new) | SQLite run/task/event ledger, transactional transitions, leases, idempotency, safe pause/cancel and restart reconciliation; JSON artifacts remain readable outputs. |
| `services/project_canon.py` (new) | Versioned approved project bible and dependency hashes; manual/generator updates have the same acceptance/invalidation path. |
| `services/text_agent_adapter.py` (new) | Typed provider-neutral writer/reviewer task/result interface; initial Codex CLI adapter with structured-output/timeout/cancel support. |
| `services/generation_contracts.py` (new) | Shared completeness rules, per-artifact schemas/coverage validators, stable IDs, prompt contract version. |
| `services/prompt_templates.py` or `prompts/generation/*.md` (new) | Versioned provider-neutral task contracts, stage instructions, Director briefs, completeness/continuation instructions. |
| `services/reasoning_provider.py` | Initial story role routing to the Codex adapter; preserve the existing shared provider behavior for unrelated pages. |
| `services/workflow_registry.py` (new) | Read/validate installed ComfyUI API workflow manifests and expose their actual input roles, settings, limits, and requirements to UI and Director. |
| `services/minimax_h3_graph_compiler.py` (new) | Turn a typed Director `reference_plan` into a versioned H3 R2V API graph; add only approved loaders/preprocessors and sequential autogrow slots, pair each reference-video soundtrack with its *own* loader, derive prompt tags from final connections, validate model/node/VRAM constraints, and archive the compiled graph. Never let model text mutate executable graph JSON directly. |
| `prompts/minimax_h3/*.md` and `examples.json` (new) | Versioned, source-attributed H3 shot-writing rules and original test examples for subjects, references, dialogue IDs, shot timeline, camera/light/sound, preservation/transfer, continuity and negative constraints. Director briefs include the exact rule version and compiler-produced reference map. |
| `services/production_run_modes.py` (new) | Validate Manual/Semi/Fully mode behavior, checkpoints, approvals, and policy-driven asset selection. |
| `services/making_route_policy.py` (new or run-modes extension) | Resolve Direct H3, Reference-built, or Hybrid preparation independently from Manual/Semi/Full control; permit audited shot-level route changes without invalidating unrelated accepted media. |
| `services/voice_catalog.py` (new or `audio_catalog.py` extension) | Read-only overlay for one-JSON-per-voice metadata, eligibility checks, deterministic random binding, audition/manual binding and provenance. No ComfyUI package/file edits. |
| `services/world_asset_store.py` (new) | Canonical location/prop/state manifests, shot-level world reference shortlist, accepted revisions and dependency invalidation; generated media uses project output. |
| `services/dialogue_source_router.py` (new or audio adapter extension) | Route exact text to local timed TTS, accepted recording through existing voice changer/RVC, or an explicitly configured hosted clone/TTS adapter; bind every output to speaker/timeline provenance. |
| `services/minimax_speech_adapter.py` (optional, new) | Opt-in hosted Speech 2.8 clone/TTS with upload/credential/budget/rights preflight; never import it into local ComfyUI by assumption or upload bundled voices automatically. |
| `services/scene_audio_policy.py` (new or existing audio adapter extension) | Bind TTS/converted/hosted dialogue, music/SFX and chosen H3 audio track to one shot timeline; explicitly replace/mute/mix and verify against source to avoid doubled/wrong-speaker speech. |
| `services/shot_router.py` (new) | Select only preflighted T2V/FL2VA/R2V/advanced workflow capability according to the approved shot contract; generate reference order/labels, frame count, quality settings, idempotency key and retake scope. |
| `services/story_pipeline.py` | Convert existing prompt functions to bounded unit functions and consume style/Director brief; preserve current artifact JSON shapes at final assembly. |
| `services/director_pipeline.py` | One policy authority for stage pre-brief, targeted model review, structured corrections, final global continuity/style review and conditional workflow selection. |
| `services/prompt_styles.py` | Backward-compatible recursive catalog, base/variant resolution, validation, version snapshot, no silent fallback to another style. |
| `services/director_profiles.py` (new) and `prompts/director_profiles/*.json` (new) | Resolve per-production-type and per-variant Director behavior, validate overrides and snapshot the exact vision/rubric version per run. |
| `services/style_ingestion.py` (new) | `.pdf`/`.md`/`.txt` extraction with page/line evidence, narrative-style distillation/validation; rejects video as a narrative-style source. |
| `services/visual_profiles.py` (new or registry extension) | Visual-treatment presets and project-level image/video/voice reference manifests, separate from narrative styles. |
| `services/style_store.py` (new) | Versioned style CRUD, source/evidence manifests, graph retrieval, publish/archive and integrity validation. |
| `services/project_graph.py` | Rebuildable links from approved canon/artifact revisions to style snapshot, assets and Director decisions; update on manual edits too. Preserve current graph schema compatibility. |
| `services/project_store.py` | Add project-local run/checkpoint/manifest paths and artifact revision helpers; generated media points to `output/<project_id>`, with safe defaults for existing projects. |
| `api/main.py` | Extend story-start payload with writer mode/style variant; expose generation progress/checkpoints; add style-library endpoints; retain existing routes and response fields. |
| `tests/` | Provider, chunk, style, evidence, project migration, and director audit regression coverage. |

### API routing (proposed)

Keep current routes working. Add versioned/catalog routes as needed:

- `GET /api/automation/styles` — return production types and their base/variant tree (maintain a compatibility flattened form or add `/catalog`).
- `GET /api/automation/styles/{style_id}` — resolve base or variant plus immutable version.
- `POST /api/style-library/sources` — register `.pdf`/`.md`/`.txt` narrative-style input only; reject video/media types with a clear validation message.
- `POST /api/style-library/sources/{source_id}/analyze` — create extraction/evidence/style draft job.
- `GET /api/style-library/jobs/{job_id}` — progress/errors/evidence preview.
- `POST /api/style-library/styles` — save a draft style version; `POST .../{style_id}/publish` publishes validated version; version history remains immutable.
- `POST /api/projects/{project_id}/automation/start` — extend payload with run mode, provider/model snapshot and selected narrative/visual styles; keep old `style_id` payload valid.
- `GET /api/projects/{project_id}/automation/run` — add active unit/chunk and provider/reviewer metadata while retaining current status fields.
- `GET /api/projects/{project_id}/generation/{run_id}` — optional detailed checkpoint/review view if keeping that information out of the compact project response.
- `GET /api/projects/{project_id}/graph` — expose style snapshot and asset relations through the existing project graph surface.
- `GET /api/visual-profiles` — return visual-treatment presets; `POST /api/projects/{project_id}/references` registers image/video reference assets separately from narrative-style sources.
- `GET /api/production/workflows` — return available ComfyUI workflow contracts, parameter controls, accepted reference roles, and limits.
- `POST /api/projects/{project_id}/production/{run_id}/shots/{shot_id}/reference-plan/validate` — return the compiled graph's slot/tag map, soundtrack pairing, staged inputs, limits, estimated resource cost and precise errors before Run; submission uses the validated plan version, not a newly hallucinated graph.
- `GET /api/projects/{project_id}/world` and scoped asset actions — list accepted location/prop sheets, state variants and dependencies; generating/accepting variants updates canon and only affected shots.
- `PATCH /api/projects/{project_id}/production/{run_id}/mode` — save manual/semi/fully mode and semi-mode controls at safe boundaries.
- `POST /api/projects/{project_id}/production/{run_id}/assets/select` — record selected image/voice/audio/video/frame asset IDs and provenance; no duplicate copies.
- `POST /api/projects/{project_id}/production/{run_id}/generate/{stage}` — start or resume the selected image/audio/video workflow stage with validated inputs.
- `GET /api/projects/{project_id}/production/{run_id}/shots/{shot_id}` — shot contract, allowed workflows, reference shortlist, dialogue/audio-source and mix policy, costs, previews and take history; `POST .../takes` submits an idempotent chosen workflow and `POST .../takes/{take_id}/accept` records the accepted output. Keep compatibility routes intact.
- `GET /api/production/voices` — read-only catalog plus live eligibility/preflight status; `POST /api/projects/{project_id}/production/{run_id}/voices/bind` persists a deliberate Semi/Manual choice. Automatic seeded choice is internal to the run and must be auditable.
- `GET /api/production/speech/backends` — local TTS, local voice conversion, and optional hosted clone/TTS readiness separately. Hosted clone/upload requires an explicit opt-in route and never runs as an automatic fallback.
- `POST /api/projects/{project_id}/production/{run_id}/pause|resume|cancel` — durable safe-boundary controls; do not claim to pause an in-flight GPU job instantly.

### Frontend

- `frontend/app/src/components/ProductionStylePicker.tsx` (new shared nested picker).
- `frontend/app/src/pages/StyleLibrary.tsx` (new style ingestion/library view).
- `frontend/app/src/pages/StoryBuilder.tsx` — use shared narrative picker and visual-treatment picker, show configured writer/director provider and no-silent-fallback policy, show live stage/unit progress, refresh project artifacts after each completed stage, surface Director review status and artifact revisions.
- `frontend/app/src/pages/AutomationStudio.tsx` — same narrative/visual selectors and run contract; preserve the independent audio-pipeline editor.
- `frontend/app/src/pages/ProductionRunWorkspace.tsx` (new or composed from existing pages) — persistent four-step text → images → voices/audio → video run workspace, mode selector, per-stage progress and approval state. Route e.g. `/production/:runId` from existing `/story` and `/automation` without replacing `/manual-director` or `/generate`.
- `frontend/app/src/components/WorldAssetBoard.tsx` (new) — approved locations/props, multi-view/state variants, per-shot world reference shortlist and affected-shot warning when an accepted master changes.
- `frontend/app/src/components/ShotBoard.tsx` (new) — one-shot contracts, timeline/dialogue lane, chosen/alternative workflows, reference role mapping, previews, quality/VRAM estimate, take history, acceptance/targeted retake and continuity handoff.
- `frontend/app/src/components/DialogueSourcePicker.tsx` (new) — local TTS vs upload/record + local voice changer/RVC vs opt-in hosted clone/TTS; displays exact line, source/target voice and transcript, preflight/consent, audition and audio ownership policy.
- `frontend/app/src/lib/project-api.ts` — typed catalog tree, style-library APIs, provider-role fields, chunk progress, artifact revision and frame-reference types.
- `frontend/app/src/components/VisualTreatmentPicker.tsx` (new) — independent visual preset picker and image/video reference slots with role, limit, and workflow validation.
- `frontend/app/src/components/ProductionModeSelector.tsx` (new) — Manual/Semi-automated/Fully automated selector; semi mode reveals three stage controls.
- `frontend/app/src/components/MakingRouteSelector.tsx` (new) — Direct H3/Reference-built/Hybrid choice independent from control mode, with optional per-shot override and preparation/cost/drift trade-offs.
- `frontend/app/src/components/WorkflowReferenceSlots.tsx` (new) — drag/drop, browse, project assets, semantic Video Repertoire results, role labels, and workflow-derived validation.
- `frontend/app/src/components/VoiceAuditionPicker.tsx` (new) — playable voice candidates, clearly sourced/uncertain descriptive tags, transcript/quality warnings, and explicit Semi/Manual character-voice binding; automated random binding is shown but not presented as semantic matching.
- `frontend/app/src/pages/ManualDirector.tsx` — retain its current standalone job contract; later add any proven H3 R2V audio/video workflow to its picker through the same capability registry. Do not expose unsupported upload slots as accepted reference inputs.
- `frontend/app/src/components/AppShell.tsx` and route registry — add Style Library navigation without renaming/removing existing routes.
- Shared UI states: loading extraction, generation progress, per-unit retries, failure with resumable cursor, completed style preview, provider unavailable, Director correction/review, and empty style-variant state.

## 10. Phased implementation and gates

### Phase 0 — Baseline, backups, and contract

- Inspect active project schemas, current style packs, model IDs, provider settings, and existing tests.
- Make a compressed backup of the affected website source/config and style packs before code edits; do not include multi-GB model/video artifacts.
- Freeze response compatibility and define artifact/chunk schemas, approved-canon revision format, voice catalog overlay, one-copy asset ownership, and run provenance fields.
- Inventory exact ComfyUI workflow node inputs and voice/TTS capabilities read-only; no Docker/Conda/ComfyUI package changes in this phase.
- Export/compare Ricky UI workflows with API graphs. Record that `gsl_starter_1_1` is Z-Image Turbo, the current Qwen Edit API graph is 2509 rather than Ricky's 2511, the Ricky I2V workflow uses subgraphs, and the crazy R2V graph pairs video frames and audio from separate loaders. Resolve each through a **new versioned adapter/export** before exposing it; do not overwrite existing working graphs.
- Test with existing fixture projects before touching UI.

**Gate:** migration tests show old projects/styles still load unchanged.

### Phase 1 — Durable run and continuity foundation

- Add SQLite run/task/event ledger behind existing API state, safe stage boundaries, lease/heartbeat reconciliation, idempotency keys and cancellation semantics.
- Add versioned approved project bible; every generated acceptance and manual edit updates dependencies and rebuilds the project graph as a derived view. Keep old project JSON and routes compatible.
- Verify `output/<project_id>` owns generated media, while Video Repertoire owns downloaded/analyzed references; no duplicate generated files.

**Gate:** restart mid-run does not lose accepted artifacts or duplicate media submissions; a manual artifact edit invalidates only affected downstream work; old projects still load.

### Phase 2 — Chunk-safe text artifacts

- Add coordinator, per-artifact unit planners/validators, checkpoints, retries, deterministic assembly.
- Add completion contract and explicit provider output budgeting.
- First use mocked providers and oversized fixtures to prove no omissions/duplicates; then run a long multi-scene sample.

**Gate:** intentionally truncated/invalid responses recover only the failed unit; assembled artifacts cover every planned ID in source order.

### Phase 3 — Provider-neutral text workers / Director orchestration

- Implement typed provider-neutral writer/reviewer adapters and route initial story text/prompt generation through Codex CLI; do not use Ollama in this initial production path.
- Add Director task briefs, per-unit checks, safe patch revisions, workflow constraints, and audit logs. Leave unrelated provider integrations unchanged.
- Add project modes (Manual/Semi-automated/Fully automated) and stage checkpoints; keep Director-guided text/prompt preparation active in every mode.
- Add prompt-improvement proposals plus evaluation/promotion flow; never allow runtime arbitrary code modification.

**Gate:** tests prove all text stages invoke the selected adapter (Codex initially) with Director guidance, no Ollama call occurs in the initial route, deterministic checks run for every unit, model review occurs at configured risk/milestones, and each mode resumes correctly. A mock second adapter proves provider neutrality without configuring a production fallback.

### Phase 4 — Hierarchical styles and production-specific Director vision

- Upgrade registry to base production type + optional named variants, retain old IDs and six existing packs.
- Add one tested Director behavior profile for each of the six base types, plus variant overrides and immutable per-run resolved snapshots.
- Build one accessible shared nested picker and use it on both Story Builder and Automation Studio.
- Record immutable style/version snapshots per run.

**Gate:** all six current base styles load with distinct Director briefs/review rubrics; type-only and variant selection resolve correctly; keyboard/mobile behavior passes Playwright.

### Phase 5 — Text-only Narrative Style Library and source-to-style distillation

- Add `.pdf`, `.md`, and `.txt` narrative-style source adapters only; reject video and analyzer sources.
- Generate evidence cards, structured style profile and Director behavior override, style graph, provider-backed review, sample prompt, draft/publish versioning.
- Add visual-treatment presets and separate project reference-asset manifest support for images/videos.

**Gate:** PDF page and Markdown/text line citations resolve; video is rejected as a narrative-style source; each active narrative-style rule has evidence or is marked as a creative inference; source plot/character/dialogue leakage tests pass; visual references remain distinct from narrative style.

### Phase 6 — Making-route selection, optional visual masters, selective anchors, and voice binding

- Add the independent Direct H3 / Reference-built / Hybrid selector and per-shot policy. All routes receive stable character/world *text* canon. Only Reference-built and selected Hybrid shots generate project-local multi-angle character/location masters; Direct H3 generates no mandatory image masters.
- Preflight and version the Qwen 2512 text-to-image, Z-Image Turbo, and Ricky Qwen Edit 2511 UI-to-API paths separately. Keep the current Qwen Edit 2509 API workflow untouched. For generated visual masters, use four candidates for Manual/Semi selection and one candidate plus bounded Director retakes in Full; validate identity/geography and record exact model/workflow versions.
- Generate/review first/last frames **only** for selected FL2VA shots and keyframes only for a verified guide workflow; do not create unused images for every scene.
- Add character voice briefs and a read-only metadata overlay for the 26 inventoried ComfyUI voice examples; live-preflight TTS discoverability, transcript, backend/language, cleanliness, and rights/consent flags. Implement audition/manual selection in Semi/Manual and seeded random selection once per character in Fully automated, persisting seed/pool/binding. Do not add audio files to ComfyUI or infer verified voice traits from names.

**Gate:** a Direct H3 fixture renders without generating image assets; a Reference-built fixture with two characters, two scenes and one recurring room shows accepted identity/geography/wardrobe masters and provenance; Hybrid adds only the assets it chooses. Unused first/last frames are not generated. Qwen 2511 is labelled unavailable until a real API export and smoke pass.

### Phase 7 — Local H3 reference inputs and dialogue source routing

- Build a capability manifest from installed workflow JSON and live ComfyUI node definitions. Keep tested graphs untouched. First build a **versioned R2V graph compiler** over the already-installed H3 node: zero-to-nine images, zero-to-three videos, matching optional paired soundtracks, and zero-to-three standalone audios, subject to actual runtime/VRAM limits. Use one video loader's IMAGE and AUDIO outputs for each pair; derive tags from the resolved graph; add an H3 I2V adapter only if its existing graph preflight passes.
- Adopt `0.98` as the tested final 16:9 Resolution Selector preset, not a generic quality slider; preserve a separate preview setting. Normalize video references to the node's 24-fps interpretation and align short prior-shot tails with their paired audio when selected.
- Add a versioned H3 prompt-rule corpus and Director/shot contract for subject definitions, reference role maps, stable speaker IDs, detailed action/camera/light/audio beats, and distinction between voice reference, source-soundtrack continuity and exact dialogue asset. Test rules against original prompts and outputs before promotion.
- Keep local TTS exact scripted dialogue as default. Add accepted recorded take → existing local `voice_changer`/RVC branch, preserving raw take and validating spoken words/timing. Optional MiniMax Speech hosted cloning is a *separate* opt-in adapter only after credential, budget, upload and permission preflight; no hosted path is required for the local gate.
- Define soundtrack replacement/mix behavior for H3-generated audio; test one- and two-speaker shots, reference versus exact line input, waveform comparison, wrong-speaker detection and no double speech. Treat `fully_copy` as prompt intent, not a proven exact-copy guarantee.
- Validate 24-fps frame grid, duration, resolution/steps/turbo/seed, reference order and `<Picture>/<Video>/<Audio>` labels, media limits, optional audio/video soundtrack binding, VRAM/runtime, and GPU model release. If local reference-video/audio fails, retain known-good text/image-only/first-last routes with honest UI limitations.

**Gate:** real short R2V shots cover voice-only Direct H3; image+video+audio Reference-built; two voices with and without a paired soundtrack; and a same-scene previous-tail continuation. Inspect resulting video/audio, graph connections, tag numbering, 24-fps sync, 0.98 final resolution, GPU/time and wrong-speaker risk. Both local TTS and recorded-take conversion are tested on exact dialogue; prompts, slot mapping, audio policy and outputs are traceable. Existing workflows remain unchanged. A failing capability stays unavailable instead of breaking known-good paths.

### Phase 8 — Production workspace, shot router, and end-to-end validation

- Add the persistent text → optional character/world images → voices/audio → shot video workspace and workflow-derived parameters/asset slots. Manual, Semi and Full use the **same** shot contract/runner with different approval gates; each works with Direct H3, Reference-built or Hybrid.
- Consume selected character/world/frame/voice assets and Director timing. For same-scene follow-up cuts, use a short approved previous-shot tail and optionally its *paired relevant* audio only via a supported graph; for a new scene omit previous-scene MP4 by default while keeping global text canon and any approved masters/voices. A longer scene is a sequence of accepted short shots, not one overlength H3 request.
- Keep H3-native soundtrack with every shot; generate separate optional BGM/SFX candidates as timestamped project assets for later Hyperframes editing, without feeding them as voice-reference audios or prematurely stitching a final film.
- Validate H3/ComfyUI input roles and limits; external action-reference videos require explicit user selection, while text-only action and keyframe workflows remain available to automation.
- Run a complete small two-scene/two-character story with a recurring location from pasted/uploaded source through accepted shot videos. Exercise Manual, Semi and Full decision paths on disposable projects; capture prompts, reference mappings, dialogue-source choices, audio mix, output clips and manifest.

**Gate:** exercise each making route with Manual, Semi and Full decision paths, plus a two-cut same-scene chain and a fresh-scene reset. End-to-end outputs match the Director contract, no fixture image is silently used, a failed shot retake does not regenerate approved unrelated shots, no voice mismatch/double speech is silently accepted, generated media is stored once under project output, repertoire references remain untouched, and artifacts are navigable. Use Playwright for changed Story Builder/Automation/production pages and regression-check touched Manual Director, Audio Studio, and project controls.

### Phase 9 — Optional advanced control workflows, strictly gated

- Assess a **separate** ComfyUI update/model-install proposal for Add Guide/Multiframe and Fun ControlNet Union after the basic local R2V path works. Include exact new node/checkpoint IDs, package/version/wheel conflicts, rollback strategy, GPU peak, storage and licensing. Never patch the user's working ComfyUI merely to satisfy this plan.
- If approved and preflight passes, version new graphs and benchmark previous-shot tail+audio guides against simple last-frame/R2V continuity, then Pose ControlNet against ordinary action reference. Keep each advanced feature separately disableable and never the only path to finish a run.
- Consider hosted H3/Context-IR or MiniMax Speech adapters only with explicit API key/upload/cost policy; compare them against local outcomes rather than silently adding cloud dependency.

**Gate:** every optional route has independent live smoke, quality comparison, GPU/cost report, disable switch and Playwright visibility. Failure leaves Phase 8 workflows fully functional. Final movie stitching/editor attachment remains a separate plan.

## 11. Test and Playwright matrix

### Backend tests

- Long story exceeds one response: beat/chapter chunks preserve all source facts and order.
- Oversized scenes, sub-scenes, and dialogue: all expected IDs/lines exist after assembly; no silent compression.
- Truncated JSON, missing IDs, malformed chunk, duplicate chunk, provider timeout, and retry exhaustion.
- Restart/recovery after process interruption continues at the next incomplete unit and does not repeat accepted work or duplicate external ComfyUI submissions; pause/cancel at safe boundaries is durable.
- The configured text worker always receives Director guidance; deterministic per-unit checks, targeted model review/repair calls, and provenance are observable.
- No initial story-production stage calls Ollama; unrelated Ollama-backed pages remain regression-tested and unchanged; a mock alternative adapter passes the same role contract without a runtime provider switch.
- Repair preserves source/approved revisions and logs its diff/rationale; manual edits update approved canon, trigger only dependent regeneration, and rebuild the derived graph.
- Prompt proposal creates a new version and regression result; no runtime source-code edit occurs.
- Current six production base packs and old flat IDs remain valid; each base has a distinct Director behavior profile; variant hierarchy, override conflicts, duplicate IDs, invalid parent/stage, and version changes are validated.
- PDF page and Markdown/text line citations remain traceable; style graph retrieval returns only relevant narrative-stage rules.
- Video is rejected as a narrative-style source; project video references remain separate generation assets and obey selected workflow limits.
- H3 request validation prevents illegal mixing of first/last-frame mode with reference-to-video roles and distinguishes reference generation from direct editing/continuation.
- Installed H3 image-reference graph rejects audio/video refs; any new versioned adapter must pass actual node-capability preflight and a live smoke run before its UI slot appears. The H3 Context-IR prompt endpoint must never be mistaken for video generation.
- Capability manifest distinguishes the installed local R2V node's optional inputs from the app graph's connected inputs, the absent Add Guide node, absent Fun ControlNet models, and the hosted API's different input rules. A missing advanced capability disables only that route, not the entire production run.
- Graph-compiler unit tests cover 0/1/9 images, 0/1/3 videos, each video with and without its own paired soundtrack, 0/1/3 standalone audios, mixed reference plans, sparse/invalid slot attempts, exact loader-to-input links, immutability of Ricky and tested API JSON, and deterministic graph serialization. A soundtrack from a different loader must fail validation.
- Prompt-index tests compare connected graph slots with generated `<Picture N>`, `<Video N>`, `<Audio N>` tags. One paired-video soundtrack plus two voices must map to Audio 1/2/3; without the soundtrack the same two voices must map to Audio 1/2. Reject undefined/unassigned tags, wrong speaker bindings, and connected references without a declared role.
- Preflight catches a 30/60-fps video treated as 24 fps without explicit resampling, a reference longer than the requested shot, source audio/video drift, no-audio MP4 when paired sound is requested, unloaded/missing model or custom loader, excessive combined reference budget, and insufficient GPU headroom. `0.98` is checked as a resolution selector mapping, not interpreted as a quality scalar; preview/final resolution, steps and `ref_image_size` are independently tested.
- Direct H3 tests create no character/world *image* assets but retain stable text descriptions, speaker IDs, scene state and prompt corpus version. Reference-built tests use an accepted Qwen/Z-Image base and a separately proven 2511 edit adapter, never silently falling back to the current 2509 API graph. Hybrid creates only requested masters and can switch at a shot boundary without rewriting accepted takes.
- Workflow registry/UI rejects unsupported reference combinations, over-limit clips/files, missing required inputs, and incorrect voice-to-character bindings before ComfyUI submission.
- World/canon tests check recurring-location geography, prop/wardrobe/weather state, accepted-master revision, shot-level reference shortlist, and invalidation of only shots dependent on a changed master. A Qwen-edited alternate view is a candidate, not automatically accepted as the same architecture.
- Shot-router tests choose T2V, FL2VA, or versioned R2V from actual tested capabilities and shot needs; first/last images are generated only when selected, and no unrequested external action video is attached automatically. Duration, frame count, resolution, step count, reference count, and GPU policy are validated against the selected local graph rather than a generic MiniMax limit.
- Voice catalog tests count/source-check the 26 metadata files, detect missing source/transcript, mark filename traits unverified, and exclude BGM/no-transcript/long/non-consented voices from the automatic pool until preflight permits them. Seeded random auto choice is stable per character/run and changes only on explicit rebinding; Semi/Manual binding wins. Test empty eligible pool and exact transcript/language mismatch behavior.
- TTS/audio tests verify exact scripted lines use the selected voice, timestamps remain aligned, and H3/TTS speech is not doubled. Local recorded-performance conversion is tested separately from local TTS and hosted MiniMax Speech cloning; each retains the original performance, target-voice/source consent, backend, transcript, output hash, and failed-conversion reason. Hosted clone/TTS cannot upload or spend without explicit project opt-in, credentials, and budget; its `voice_id` is not treated as a local model ID.
- Versioned R2V audio/video-reference graph tests submit real WAV/MP3 and MP4 references, verify actual node connections, prompt-role mapping, S1/S2 consistency, output sound/video, and wrong-speaker failure handling. Until the live test passes, those slots remain unavailable in the website even though the local node defines them.
- Dialogue-mix tests compare generated H3 speech with pre-generated exact dialogue: reject accidental double speech, wrong line, wrong speaker, clipped start/end, missing silence, and A/V drift. A prompt word such as `fully_copy` is not accepted as proof of waveform preservation; use and test the exact approved take in the final mix where required.
- Manual/Semi/Fully mode tests: four image candidates and human choice in semi/manual; one candidate and bounded Director retake in full; audition/voice binding; prompt-prepared video page; no lost state on navigation.
- Manual tests accept an uploaded world/character sheet, recorded voice performance, chosen workflow and references without silent substitutions. Semi tests cover all eight combinations of its three independent choice gates, durable pause/resume, and untouched automatic stages. Full-auto tests reject unavailable advanced routes and use bounded fallback/retakes without a human gate.
- Consecutive scene continuity tests distinguish previous project clip input from external action reference and from deferred final-film stitching; use previous approved video only with a supported reference-video route, otherwise a valid last-frame route or no chaining, always retaining canonical identity and world references. Add Guide tail-frame-plus-audio and Pose ControlNet are separate future-gated tests, never presumed available from the current install.
- Same-scene cut 2 can reference a short approved prior-shot tail, with paired audio only when explicitly relevant; the next fresh scene does not inherit that MP4 by default. Tests cover stale dialogue/music contamination when prior audio is attached, visual drift in text-only Direct H3, and truthful Director escalation to a still/master or retake instead of a false continuity guarantee.
- Separate BGM/SFX project assets retain source/timestamps for future Hyperframes editing; they are not automatically plugged into H3 standalone *voice* slots, muxed over the native H3 soundtrack, or duplicated in Video Repertoire. No test asserts final film stitching is already available.
- Character image and scene-frame IDs remain stable across retries and project reload.
- Old project JSON loads with defaulted new fields without destructive migration.
- One-copy storage tests prove project output owns generated media, Video Repertoire owns analyzed/downloaded references, manifests do not copy assets, and project deletion never removes a referenced repertoire asset.

### Playwright tests

- Story Builder and Automation Studio both display the same production-type/variant tree.
- Expand/collapse/keyboard/selection behavior, current selection label, and disabled-while-running behavior.
- Style Library source upload/selection, evidence preview, draft/save/publish, version history, and failure states.
- Per-stage artifact content becomes visible as chunks complete without page reload; progress shows unit N of M and bounded retries.
- Director review status and output revision are visible and distinguish original from corrected content.
- Character reference gallery shows angle/status/provenance; scene frames show first/last label and linked character references.
- World/props board shows recurring locations, approved master/variants, current story-state and dependent-shot warnings. The shot board explains why a frame, action video, prior clip, or audio reference was selected, and shows a truthful unavailable reason for Add Guide/ControlNet/hosted voice clone.
- Navigation during generation preserves the run and reloads current artifacts/checkpoints.
- Fully automated voice page shows the selected random voice and stable character binding; Semi/Manual lets the user audition/change it; missing transcript/ineligible voices show a truthful reason.
- Production workspace displays only workflow-supported audio/video/frame slots, explicit soundtrack policy, and the prior-clip-versus-last-frame continuity choice; invalid combinations are blocked before Run. Manual upload/drag-drop and repertoire selection point to one canonical asset, not copied media. Semi-automatic gates reopen at their exact pending stage after reload.
- Making-route selector is independent of Manual/Semi/Full control mode; Direct H3 skips image generation, Reference-built shows image approval, Hybrid reveals per-shot routing. R2V slot UI displays the **compiled** tags and one synchronized video/soundtrack pair, not arbitrary file fields. Final render shows `0.98` as a resolution preset and clearly differentiates it from steps and preview quality.
- No console errors/layout overflow at desktop and mobile widths; existing audio automation and project controls remain functional.

### Live acceptance run

Use a newly created disposable project and a deliberately long two-scene/two-character story. Capture:

1. source story and exact immutable revision;
2. per-stage prompts/director briefs, chunk requests/responses and assembled artifacts;
3. Director reviews, corrections, and any prompt improvement proposals;
4. narrative-style text evidence and version snapshot, plus separate visual-treatment/reference-asset IDs;
5. selected making route and shot-level overrides; in Reference-built/Hybrid, accepted character sheets and recurring world/location masters/state variants, plus only frames called for by selected shots; in Direct H3, the text-only character/world bible and no mandatory generated stills;
6. per-character random/manual voice binding, one local recorded-performance conversion fixture, dialogue/music/SFX timing, TTS output, versioned MiniMax requests, generated outputs, audio mix policy, retries and final manifest;
7. one-copy canonical media paths, run ledger restart/recovery trace, and unchanged Video Repertoire references.

Do not use a real existing project as the destructive test fixture. Do not claim complete media production based on planning artifacts alone.

## 12. Non-goals for this plan

- Training one LoRA per character.
- Replacing video/audio analyzer, Video Repertoire, Ollama, or Codex CLI; modifying tested ComfyUI graphs in place. Any additional H3 input mode uses a separate versioned adapter/workflow and a live capability gate.
- Forcing every generated style to use vector embeddings or a hosted graph database.
- Rewriting other Story Builder pages or changing existing project deletion semantics beyond precisely including newly owned project outputs; shared repertoire assets remain intact.
- Letting the LLM omit detail to satisfy a single response limit.
- Allowing Codex to run arbitrary shell commands or silently modify application source at runtime.
- Automatically attaching generated video outputs into a separate editing/composition system; generated files remain saved and visible in this project, but the later attachment feature is deferred.

## 13. Locked decisions and remaining validation gates

Locked direction and remaining clarification:

1. Narrative styles come only from `.pdf`, `.md`, and `.txt`; visual treatments and image/video/voice references are independent controls.
2. A provider-neutral Director/worker contract orchestrates story text and prompt generation; Codex CLI is the initial configured worker/reviewer provider. No Ollama fallback in the initial story pipeline and no silent provider switch mid-run; other Ollama functionality is out of scope.
3. Style sources produce a **draft**; the configured text provider and Director validate evidence/profile, and the user publishes. Published style and Director-profile versions are immutable. Every one of the six production types has a distinct Director behavior base profile; variants can override it.
4. Style knowledge is structured JSON + evidence graph initially; semantic style embeddings are optional future work.
5. Run mode is selected per run: Manual, Semi-automated, or Fully automated. Semi mode has independent image-choice, voice-choice, and video-generation/reference controls; text and prompt preparation remains Director-guided through the configured provider in every mode.
6. Manual/semi image requests produce four candidates for user selection; fully automatic produces one candidate and may do bounded Director-requested retakes.
7. Voice samples are auditionable in Manual/Semi; full automation selects randomly *once per character* from a preflight-eligible pool using a saved seed. The preliminary 26-file JSON catalog is not acoustic/identity verification. Store presentation/register as confidence-marked descriptors, not an asserted real-world gender.
8. Generated visual/audio/video assets live once under `output/<project_id>` and are referenced by stable IDs from project storage; source/analyzed reference media stays in Video Repertoire. Do not duplicate media across these locations.
9. Character/keyframe validation can auto-retry bounded failures; unattended progress does not block indefinitely on human confirmation.
10. Previous-output-to-next-input **continuity chaining is in scope** for adjacent cuts **within a scene** when the selected workflow supports it: a short approved previous-shot tail as a reference-video input, optionally with relevant paired audio, or its last frame as a valid first-frame input otherwise. A fresh scene has no previous-scene MP4 input by default; keep global text canon/voice IDs and, where available, accepted character/world masters. Final-film output attachment/stitching is a separate deferred feature. Do not claim the current installed website graph takes a previous video file.
11. **Workflow constraint:** MiniMax public API currently documents first/last-frame inputs and Ref2VA reference inputs as mutually exclusive modes. A hybrid is available only if the exact selected ComfyUI workflow/API manifest supports it; otherwise use a valid alternative/staged flow. Do not promise pixel-exact actor/background replacement.
12. **Exact dialogue is pre-generated where needed, not simply entrusted to H3.** The default route is local TTS; a user may record the lines and use the already available local voice-changing/RVC route, and hosted MiniMax Speech voice cloning/TTS is optional only after consent, credentials, upload/privacy and cost approval. The installed H3 R2V *node* accepts audio/video, but the website's current graph does not connect those inputs. Build and smoke-test a separate versioned graph before exposing the slots. Prompt-only `fully_copy` is not an exact-audio guarantee: retain and mix the approved dialogue take when exact performance is required, preventing doubled speech.
13. Before implementation, verify whether the local TTS backend actually accepts each catalog voice/transcript and which source samples may be used under the user's intended consent/rights policy. The user may correct subjective voice descriptions after audition; missing adjectives do not block planning. If the eligible automatic pool is empty, pause with a clear action rather than picking an unsafe/incompatible file.
14. Stage-level Director model-review frequency and a minimum quality rubric can be tuned from the two-scene acceptance run; the invariant is deterministic validation on every unit and auditable deeper review for ambiguity/risk/milestones, not a wasteful model call for every clean token.
15. Character identity, location geography and voice identity come from immutable accepted **text canon and voice bindings** in every route; Reference-built/selected Hybrid shots additionally use accepted visual masters. The immediately prior approved shot provides short-term state only. A world **text/state** manifest is required before dependent shot generation, but a generated world image board is not mandatory in Direct H3. Reference sheets are selected per shot, not all uploaded to every H3 request.
16. Local ComfyUI Add Guide/Multiframe and Fun ControlNet are documented possibilities, **not locally installed capabilities** in the audited runtime. Their models/nodes, license, GPU peak and live output must be preflighted before any UI promise or ComfyUI change. Current T2V/FL2VA/R2V routes remain usable if these later options never pass the gate.
17. Manual, Semi and Full use one versioned shot contract and runner. The Director prepares text, shot rationale, timing, references, prompt and validation for every mode; mode changes only asset-choice and approval gates. Generated project assets remain in project output, not duplicated into Video Repertoire.
18. The **making route** is independent: Direct H3 (fast text-led), Reference-built (asset-first), or Hybrid (shot-by-shot). Direct H3 does not require separate character/world/scene image prompts, but it still requires a structured H3 shot prompt, text canon and stable voice identity. Its weaker visual continuity is an explicit trade-off, not something a Director can guarantee away.
19. The Director plans references and writes prompts according to a versioned H3 rule corpus; a deterministic compiler, not free-form agent JSON edits, constructs the dynamic R2V API graph. The compiler owns loader staging, same-file video/audio pairing, 24-fps alignment, slot limits, tag numbering, and validation. Never overwrite Ricky UI graphs or tested API workflows.
20. For a follow-up cut **inside the same scene**, a short prior approved video tail and its relevant synchronized audio may be attached to R2V. A fresh scene has no previous-scene MP4 by default. The same physical clip's IMAGE and AUDIO outputs must feed the matching video/audio slots; the Director may omit the paired soundtrack to avoid obsolete dialogue/music conditioning. Ordinary R2V remains a reference, not a guaranteed seamless continuation.
21. Use Ricky's `0.98` Resolution Selector preset as the proposed **final 16:9 resolution** (mapped there to 1344×768), subject to API-export and live GPU validation. It is not a quality score. Keep lower-resolution preview optional and steps, scheduler, `ref_image_size`, reference count and acceptance tests separately controlled.
22. H3 creates a native audio-video shot. Exact voice performances, and optional separately generated BGM/SFX, are retained as aligned project assets for later Hyperframes editing; separate music/SFX are not filled into H3 voice-reference slots by default. No final-film assembly is implied by this plan.

## 14. Primary capability references (recheck during implementation)

- MiniMax H3 input modes and limits: https://platform.minimax.io/docs/guides/video-generation and https://platform.minimax.io/docs/api-reference/video-generation-v2-create
- Local H3 T2V/I2V/R2V and workflow behavior: https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native
- R2V node's local slot ordering, paired-video soundtracks and 24-fps reference-frame behavior: https://github.com/Comfy-Org/embedded-docs/blob/main/comfyui_embedded_docs/docs/MiniMaxH3ReferenceToVideo/en.md (cross-check against the installed source; this page identifies itself as AI-generated)
- MiniMax's full-reference prompt structure and role terminology: https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md
- H3 reference roles and dialogue/audio prompt syntax: https://docs.comfy.org/tutorials/video/minimax/minimax-h3-prompt-guide
- Later-gated Multiframe/Add Guide: https://docs.comfy.org/tutorials/video/minimax/minimax-h3-multiframe
- Later-gated Fun ControlNet Union: https://docs.comfy.org/tutorials/video/minimax/minimax-h3-fun-controlnet
- Hosted Speech voice cloning, upload and `voice_id` constraints: https://platform.minimax.io/docs/guides/speech-voice-clone
- Hosted H3 Context-IR (prompt enhancement, not video generation): https://platform.minimax.io/docs/api-reference/video-generation-v2-h3-context-ir

These pages describe potential capabilities, not proof that the currently installed ComfyUI graph or website accepts those inputs. The local workflow manifest and a real smoke output are the final capability gate.
