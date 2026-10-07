# 6. Architecture, storage, integrations, and runtime

## Architecture at a glance

```text
Browser (React/Vite)
       │ HTTP / JSON / media upload
       ▼
FastAPI backend (`api/main.py`)
       ├─ filesystem-backed Story Builder projects/artifacts
       ├─ job coordinators/workers and status manifests
       ├─ ComfyUI HTTP/WebSocket adapter for media workflows
       ├─ local reasoning adapter: Codex CLI or Ollama
       ├─ Video Repertoire storage/search/analyzer launchers
       └─ optional isolated Docker services for analyzer models
```

Frontend route definitions are in `frontend/app/src/App.tsx`; Vite proxies to the backend URL configured by `run_story_builder.sh`.

## Startup behavior

`run_story_builder.sh` health-checks Ollama and ComfyUI first. If either local service is already reachable, it leaves it running; otherwise it tries to start Ollama and invokes the configured ComfyUI startup script. It then starts FastAPI and Vite. This means the launcher can start or depend on GPU-backed services; closing the shell's backend/frontend processes does not necessarily stop detached Ollama or independently managed ComfyUI. Use each service's own stop procedure if you need GPU memory released.

The script defaults to backend port 3010 and frontend port 8080, overridable by `STORY_BUILDER_BACKEND_PORT` and `STORY_BUILDER_FRONTEND_PORT`.

## Reasoning versus media execution

- Codex/Ollama produce structured reasoning/JSON via `services/reasoning_provider.py`.
- ComfyUI executes image/audio/video workflow graphs via media adapters.
- FFmpeg and other local tools perform extraction, muxing, conversion, and deterministic transforms.
- The video analyzer can run through project-local Docker workers; it should not modify ComfyUI's environment.

An LLM request being successful does not mean a ComfyUI graph ran. A ComfyUI job being successful does not mean the story prompt was coherent.

## Storage domains

| Data | Main location / ownership |
|---|---|
| Story project state | `projects/` (through `ProjectStore`; exact root configured in API/services) |
| Story JSON artifacts | Project `artifacts/` directory plus materialized project state |
| Project media and outputs | Project media/output subfolders and job manifests |
| Uploaded/downloaded source videos | `video_repertoire/downloads/` or registered source path, indexed by `video_repertoire/manifests/` |
| Video analysis, scenes/cuts, derived clips/audio | `video_repertoire/` folders and manifests; analyzer working run outputs are promoted into the shared repertoire according to its promotion code |
| Manual Director uploads/inputs/outputs | `video_repertoire/manual/assets`, `manual/inputs`, `manual/outputs`, `manual/jobs` |
| Audio library assets | Audio catalog's configured storage root; separate from Video Repertoire reusable clips |
| Provider selection | `storage/reasoning_provider.json` |
| Analyzer model files and Docker config | `video_audio_analyzer/models/` and `video_audio_analyzer/docker-compose.yml` |

Storage roots may be overridden by environment variables; consult `services/video_repertoire.py`, project-store initialization, and audio catalog configuration before manual cleanup. Job deletion is destructive for generated derivatives; source downloads and shared assets should have separate safeguards.

## Docker and GPU boundaries

`video_audio_analyzer/docker-compose.yml` defines optional profiles/workers (core, PE-AV/query, audio analysis, SAM Audio, TalkNet). Model workers are isolated to avoid forcing specialized/legacy dependencies into ComfyUI or shared Conda environments. Not all profiles are required for basic analysis. Model files, gated access, checkpoint compatibility and available VRAM determine readiness. GPU use from concurrent ComfyUI/Ollama/analyzer workers adds together; job sampling is best-effort and not perfect per-container attribution.

## Security and operational concerns to review

- File-serving endpoints should remain rooted in allow-listed project/repertoire paths and reject traversal.
- Uploaded reference size/type limits are enforced in Manual Director.
- Codex is invoked read-only/ephemeral for reasoning and should not receive media-worker credentials.
- Model checkpoint license and gated-access terms should be recorded independently of code repository license.
- Job cancellation/stop/delete semantics must be understood separately; a queued-job cancel response is not evidence that an already-finished job was stopped.
- External services can remain resident after website shutdown; launcher and service lifecycle documentation must be clear.

