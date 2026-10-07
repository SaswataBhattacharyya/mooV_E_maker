# Story Builder checkout for UI planning and development

This repository contains the real frontend, backend, API routes, services,
workflow definitions, prompts, integration source and planning documents.
Media files, model weights, project data, installed environments, generated
outputs and credentials are excluded. The original source paths are preserved;
machine-specific paths in older documentation describe the operator's Spark.

## Start the backend and frontend

Use Python 3.11 or newer and Node.js 22.12 or newer (Node 22 LTS recommended).
Clone into a directory named `story_builder`, because the Python imports use
that package name:

```bash
git clone https://github.com/SaswataBhattacharyya/mooV_E_maker.git story_builder
cd story_builder
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev-ui.txt
```

Windows users can activate with `.venv\Scripts\Activate.ps1`. The documented
backend setup targets Linux/macOS; some optional GPU process supervision uses
Linux-specific modules.

In the first terminal, from the parent of `story_builder`:

```bash
cd ..
python -m uvicorn story_builder.api.main:app --host 127.0.0.1 --port 3010
```

In a second terminal, from the checkout:

```bash
cd frontend/app
npm ci
cp .env.example .env.local
npm run dev -- --host 127.0.0.1
```

Open `http://localhost:8080`. API documentation is available at
`http://localhost:3010/docs`. Vite proxies `/api` to the backend on port 3010.
Use `VITE_BACKEND_TARGET=http://127.0.0.1:OTHER_PORT npm run dev` if changing
the backend port; put this in the shell environment because the existing Vite
configuration reads `process.env.VITE_BACKEND_TARGET`.

For the frontend build:

```bash
npm run build
```

The original `run_story_builder.sh` is an operator launcher and may start/check
other local services. Use the two commands above for this empty developer copy.

## Expected behavior without models or services

The interface and local project APIs do not require ComfyUI or Ollama to be
installed. A fresh checkout has no existing projects, uploaded media, voices,
installed model weights, library assets or queued jobs. Those lists begin empty. This export was checked with the real backend: projects,
voices and installed audio models each returned an empty list with HTTP 200;
health reported ComfyUI and Ollama unavailable, and the workflow catalog returned
90 definitions.
Workflow and capability menus may still show options from code, with unavailable
status or a reason they cannot run. The UI can display service-offline notices.

Other discovery endpoints can ask Ollama or ComfyUI for live inventories; an
unavailable service can produce an error response rather than an empty list.
The UI may show the corresponding unavailable/error state. Generation, inference,
Docker media tools and provider-backed operations require their real runtimes.
Keep their API contracts when changing the layout. Do not remove a route just
because its list is empty in this checkout.

You can create local projects and edit their local metadata for UI work. New
project state remains ignored by Git. There is no copy of the operator's saved
projects or jobs in this repository. No model download is part of the startup
commands above.

## Where to make UI changes

- `frontend/app/src/App.tsx`: frontend routing.
- `frontend/app/src/pages/`: pages and feature workspaces.
- `frontend/app/src/components/`: shared UI and app shell.
- `frontend/app/src/components/ui/`: reusable UI primitives.
- `frontend/app/src/lib/project-api.ts`, `agent-api.ts`, `tts-api.ts`: API clients.
- `api/main.py`: actual FastAPI routes and request/response contracts.
- `services/`: project storage, feature catalogs and execution logic.
- `workflows/`: JSON graph definitions, with filenames and model references intact.
- `config/`, `prompts/`, `docs/`, `plan/`: configuration and design context.
- `video_audio_analyzer/`, `video_summariser/`, `Image_detailer/`, `audio/`,
  `Art_ist_min/`: companion and optional runtime source, including upstream
  license files. Their datasets, weights and media are excluded.

See `API_ROUTE_MAP.md` for the exported route inventory. The backend's generated
`/docs` page is the authoritative request/response schema after startup.

## Paths and files excluded from Git

The root `.gitignore` excludes media by extension and known local data paths.
Python source folders named `models` are retained where they implement code;
model weight files and runtime weight directories are excluded. Do not use a
blanket `models/` ignore rule that would hide those Python modules.

Empty directories use `.gitkeep` so their expected locations are visible.
Several workflow files contained embedded base64 preview images; the export
removes those previews while retaining the graphs and all path references.
Tokenizer lookup assets and upstream audio test datasets are also excluded.

Before committing, review `git diff --cached --stat` and the staged file list.
Avoid force-adding ignored local data. The original project remains on the Spark;
the GitHub copy is a separate source snapshot.

## Collaborating

Create a branch for layout changes, keep the existing routes/API clients, and
commit the source. A private working branch still belongs to this public
repository; never put keys or personal project data in commits. The repository
owner can review and bring approved changes back into the running installation.

The imported `AGENTS.md` and older operator notes describe live Spark work.
They do not prove that the optional services or GPU acceptance checks exist in
this empty checkout. UI planning does not require running those workloads.
