# 3. Images, video, media generation, and Director workflows

## Media Composer

Media Composer discovers workflow JSON files and infers a UI schema from graph nodes: category, prompt fields, image fields, numeric parameters, and output type. It supports browsing workflows, supplying prompt/reference assets, submitting a ComfyUI job, then polling job history and collecting output files.

The discovered workflow catalog is not a guarantee of runtime readiness. A workflow may reference missing custom nodes, checkpoints, or models. A successful API submission also does not imply that the output is the intended quality; each workflow should be validated with its actual ComfyUI installation.

Implementation pointers: `frontend/app/src/pages/MediaComposer.tsx`, `services/workflow_catalog.py`, `services/media_jobs.py`, `workflows/`.

## Manual Director

Manual Director is a workflow-aware generation surface backed by `services/manual_director.py`. It currently maps three explicit workflow IDs:

| Workflow | Current contract |
|---|---|
| `minimax_text` | Text-to-video; no media references required. |
| `minimax_references` | Reference-image mode, accepts 1–3 images. The mapped local graph does not accept reference audio or video. |
| `wan_first_last` | WAN first/last frame mode; both endpoint images are required. The mapped graph does not accept reference audio or video. |

The page can add media from the repository or upload it into the shared repertoire; references can be drag-and-drop/pasted. The workflow catalog exposes only parameters inferred/mapped for that workflow (e.g., duration, quality steps, seed), validates required slots, then submits to ComfyUI. Inputs are recorded as JSON; outputs are kept under `video_repertoire/manual/outputs/`; job files are stored under the same manual subtree.

Important current limitation: UI slot types include audio/video, but the currently mapped workflow contracts do not accept those slots. Do not assume H3 full-reference audio/video conditioning is available merely because an audio/video reference can be uploaded or the model itself supports it. The workflow graph and adapter must support the slot.

Code: `services/manual_director.py`, `frontend/app/src/pages/ManualDirector.tsx`, `/api/video-repertoire/manual/*`, `workflows/api/`.

## Generate and the production runner

The Generate page is primarily an entry point to the component workflows and output finalization. The backend production runner is a narrower demonstration/production path, not the entire desired story-to-film product. It currently:

1. Creates a production run and working folder in the project.
2. Uses the supplied `plan/image.png` fixture as three image references.
3. Attempts an ACE-Step music job, falling back to a supplied MP3 fixture if needed.
4. Creates one Control-Foley cue.
5. Selects up to two shot records (one per scene where possible), with fallback shots if the director shot list is inadequate.
6. Builds a fixed MiniMax H3 reference-to-video API graph, submits it to ComfyUI, retries once on failure, and muxes generated video with music/foley.
7. Writes a production manifest and project output.

This runner is useful as an integration smoke path, but its fixed fixture/reference selection and fixed workflow do not equal the future workflow-aware, per-character/per-scene production system. Read `services/production_runner.py` before treating the two-scene demo as a general creative workflow.

## Video workflow model

There are several distinct concepts:

- **Text-to-video**: model invents the visual trajectory based on text.
- **Image/reference-to-video**: images condition appearance/composition; actual accepted count/meaning depends on graph.
- **First/last frame**: workflow anchors endpoints and synthesizes between them.
- **Reference-video motion/style conditioning**: only available if the specific model/API graph and local ComfyUI node support it. It is not implied by ordinary image-reference workflows.
- **Audio reference/reuse**: also requires explicit workflow nodes/API support; the current Manual Director mapped graphs do not expose such input slots.

## UI / runtime signals to teach reviewers

On every generation page, distinguish:

- workflow listed vs workflow available/mapped;
- ComfyUI reachable vs its required node/checkpoint loaded;
- job accepted vs job completed;
- output file produced vs output semantically/visually correct;
- reference file present vs graph actually consumes that reference slot.

