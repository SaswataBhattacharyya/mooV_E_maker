# Story Builder — full product and process review

This review is a reader's guide to the current Story Builder website, its workflows, prompts, model/runtime boundaries, and known gaps. It is intended to help someone who did not build the app understand what it does and give useful product or engineering feedback.

## How to read this review

The documents distinguish three states:

- **Implemented in the current code**: a UI/API/service path exists. This does not by itself mean every model, workflow, or external service is installed and healthy on every machine.
- **Conditional / environment-dependent**: the path exists but depends on local models, ComfyUI workflows, CLI tools, checkpoints, GPU memory, or credentials.
- **Planned / not represented as current behavior**: described in a plan, discussion, README, or UI aspiration but not verified as an implemented end-to-end path.

The review is source-based, not a live acceptance test. It does not launch or mutate the website, ComfyUI, Ollama, Docker, or any model. References point to the source files that should be checked when behavior changes.

## Reading order

1. [Product map and page-by-page guide](01_product_and_routes.md)
2. [Story creation, artifacts, prompts, and reasoning providers](02_story_pipeline_and_prompts.md)
3. [Images, video, media generation, and Director workflows](03_media_and_generation.md)
4. [Video Repertoire and Video/Audio Analyzer](04_video_repertoire_and_analyzer.md)
5. [Audio workflows](05_audio_workflows.md)
6. [Architecture, storage, integrations, and runtime](06_architecture_storage_runtime.md)
7. [Prompts, models, and workflow contracts](07_prompt_model_workflow_inventory.md)
8. [Current gaps and questions for reviewers](08_review_questions_and_gaps.md)
9. [Grouped API map](09_api_map.md)

## One-paragraph mental model

Story Builder is a local-first web workspace. A React frontend talks to a FastAPI backend. Story projects hold editable JSON artifacts and generation state; media execution is delegated to known ComfyUI API workflows and local services. Video Repertoire is a separate shared library for source videos, analysis results, clips, and selected reusable audio. The reasoning provider can be selected between Codex CLI and Ollama, while media generation itself is performed by workflow/runtime adapters rather than by the reasoning model. Several advanced integrations are optional or conditional, so “the feature exists” and “the selected checkpoint/workflow is ready” are distinct states.

## Source-of-truth pointers

- Frontend routes: `frontend/app/src/App.tsx`
- Shared navigation/provider/run monitor: `frontend/app/src/components/AppShell.tsx`
- API surface: `api/main.py`
- Project/artifact storage: `services/project_store.py`
- Reasoning provider adapter: `services/reasoning_provider.py`
- Story-stage prompts: `services/story_pipeline.py`
- Director shot-plan prompt: `services/director_pipeline.py`
- ComfyUI job execution and workflow discovery: `services/media_jobs.py`, `services/workflow_catalog.py`
- Video Repertoire API/storage/worker: `services/video_repertoire.py`, `services/video_repertoire_worker.py`
- Isolated analyzer: `video_audio_analyzer/README.md`, `video_audio_analyzer/src/video_audio_analyzer/`
- Tests: `tests/`
- Future story/director/style proposal: `plan/story_generation_director_and_style_system_plan.md` (proposal, not proof of implementation)

