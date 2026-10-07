# 2. Story creation, artifacts, prompts, and reasoning providers

## Story project lifecycle

The primary project data model is filesystem-backed. A project gets a generated ID and a project directory; state is materialized from `project.json`, with artifacts saved as JSON under `artifacts/`. The primary artifact chain is:

1. **Story Blueprint** (`story`)
2. **Character Sheet** (`characters`)
3. **Scene Plan** (`scenes`)
4. **Sub-scene Plan** (`subscenes`)
5. **Dialogue Plan** (`dialogue`)
6. **Image Queue** (`image_jobs`)

These are individually editable and saveable. Upstream artifact content is passed into downstream generation prompts to preserve continuity. There is also a project graph/status representation and a separate production runner; do not assume the six artifacts automatically generate a finished film without those later execution paths.

Relevant implementation: `services/project_store.py`, `services/story_pipeline.py`, `api/main.py` artifact and automation routes, `frontend/app/src/pages/StoryBuilder.tsx`.

## What each generation prompt asks for

Every stage uses JSON-only output requirements and shared guardrails: improve only the current artifact, preserve approved facts and continuity, and do not invent stages. A selected production-style contract is serialized into each applicable prompt.

| Stage | Main output |
|---|---|
| Story | Title, original input, expanded prose story, story goal, tone, continuity rules, visual style notes. |
| Characters | Stable slug-like ID, name, role, gender presentation, age band, appearance, baseline wardrobe, personality, visual prompt, voice-alias suggestion. |
| Scenes | Ordered scene IDs/numbers, summaries, location/time, continuity notes, visible character IDs, background prompts. |
| Sub-scenes | Cut/shot-level camera, blocking, action, mood, dialogue sketch, image prompt, start/end-frame brief. |
| Dialogue | Per-subscene beats, speaker, line, delivery, timing intent, onscreen/offscreen/cutaway, narration, SFX and music notes. |
| Image jobs | Ordered character assets, backgrounds, and scene-frame jobs with prompt, size, and optional scene/subscene IDs. |

Prompt builders live in `services/story_pipeline.py`. Style text comes from `prompts/styles/*.json` through the style loader, rather than being a model weight or image/video reference. The current style catalog includes advertisement, corporate pitch, informative, news report, social profile, and story film.

## Base prompt policy in the current implementation

The current story prompts are concise, stage-specific templates. They specify schemas and continuity rules, then embed upstream artifact JSON. They do **not** currently implement a general multi-round continuation protocol for arbitrarily long outputs in `story_pipeline.py`; each artifact generation is one `generate_json()` request. If the selected provider truncates output or returns incomplete JSON, parsing/validation can fail rather than transparently continuing section by section.

The desired robust long-form strategy (chunked generation, stable IDs, completeness checks, bounded continuation, and a final reconciliation pass) is discussed in `plan/story_generation_director_and_style_system_plan.md`; treat it as a plan until the implementation is found and tested.

## Director: current behavior versus the broader desired role

Current code has a Director shot-plan generator in `services/director_pipeline.py`. It consumes story, character, scene, subscene, and dialogue artifacts and requests a coherent JSON shot list covering camera/framing, lighting, tone/emotion, blocking, dialogue beats, music/foley, start/end-frame briefs, duration, and continuity checks. A review policy is requested in the output.

That is not yet equivalent to an autonomous director agent that independently guides and audits every artifact stage, decides when to regenerate, improves the base prompts, and orchestrates the whole workflow. The Story Builder has supervisor/run state and an automation coordinator, but the desired continuously supervising director described in the plan is broader than this single shot-plan call.

## Reasoning-provider behavior

The backend adapter supports two providers:

- **Codex CLI**, default model `gpt-6-luna`; launched as an ephemeral, read-only CLI call. It is used for JSON reasoning, not to execute media jobs or directly write project outputs.
- **Ollama**, model name from the local client configuration; it remains a selectable compatibility option.

The global selector in `AppShell` says it applies to story and director reasoning. Provider choice is persisted in `storage/reasoning_provider.json`, and a context variable pins a provider for a running background run. Media execution is separate and normally goes through ComfyUI adapters.

Code: `services/reasoning_provider.py`, `services/ollama_client.py`, `/api/reasoning/provider*`, `frontend/app/src/components/AppShell.tsx`.

## Human checkpoints

The UI exposes artifact editors and save buttons, so the user can review/edit at each stage. The Director prompt currently asks for `human_approval_required: true`; this is an output policy field and should not be confused with evidence that all automation stages have an implemented approval gate. Review the actual automation state transitions and UI before assuming a stop-and-approve gate exists everywhere.

