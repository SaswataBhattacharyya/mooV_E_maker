# 9. Grouped backend API map

The FastAPI app is defined in `api/main.py`. This is a navigation aid, not a substitute for the endpoint's Pydantic/request validation or authorization/path checks.

## Health, provider, project, and story

- Health: `/api/health`
- Reasoning provider catalog/change/tests: `/api/reasoning/provider`, `PUT /api/reasoning/provider`, provider/director test endpoints
- Projects: `/api/projects`, `/api/projects/{id}`, draft update
- Story automation: start, upload input, inspect run, pause/resume/reset actions, status
- Project graph and production runner: `/api/projects/{id}/graph`, `/production/start`, `/production/run`
- Artifacts: generate/save under `/api/projects/{id}/artifacts/{artifact_type}`
- Story assist: `/api/story/assist`
- Style catalog/details: `/api/automation/styles`

## Workflow and generated media

- Workflow discovery/details: `/api/workflows`, `/api/workflows/{workflow_id:path}`
- Generic project media upload/jobs/files/output finalization/composition/manifest
- Audio capability and workflow catalogs: `/api/audio/capabilities`, `/api/audio/voices`, `/api/audio/models`, `/api/music/capabilities`, Control-Foley and ACE preflight/capabilities

## Audio

- Audio library CRUD/content: `/api/audio-library/assets*`
- Utilities: capability endpoint and project job creation/list/detail
- Voice upload/refresh, character map, timed TTS jobs
- F5 fine-tuning preflight/prepare/status
- Audio effect jobs, scene split/stitch jobs
- Music and Control-Foley jobs/status
- Audio automation blocks/schemas, project pipelines, validation, run status and step retry
- Audio reconstruction: project session, calibration, parts, takes, accept take

## Video Repertoire and analyzer

- Capability status and video-reference index/search/SEO/selection
- YouTube resolve/download jobs/cancel/retry
- Asset list/import/upload/delete/content
- Analysis jobs/list/status/cancel/stop/delete/retry
- Word/semantic search; optional vision job and references
- Audio asset list/delete/content
- Repertoire artifact serving
- Analyzer run artifacts/search, SAM isolate preview/review/delete
- Manual Director workflow/assets/jobs/output files

## Vision / Canvas

- Image analysis and project vision runs/events/cancel/artifacts/generation brief
- Canvas revisions, analysis, and outline generation

## Useful inspection method

For a route, trace four things in order: React page/client function → API endpoint and request model → service/worker function → persisted manifest/output path. A route returning HTTP 200 or a page rendering is not sufficient evidence that an external model/workflow completed correctly.

