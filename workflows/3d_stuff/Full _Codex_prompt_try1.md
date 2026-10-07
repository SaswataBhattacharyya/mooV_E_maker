Build a Local Image-to-Game-Asset WebUI Pipeline

## Standalone repository boundary

Implement the application entirely under the repository-root directory:

```text
3d_stuff/
```

This directory is the standalone app boundary. It must contain its own frontend,
backend, workflow adapters/templates, configuration, tests, setup instructions,
and output handling. Do not import Python/JavaScript modules, routes, styles,
storage helpers, or runtime code from the existing Story Builder WebUI. Existing
files may be copied into `3d_stuff/` when needed, but the copied version must be
self-contained and use relative paths or environment variables.

The current `workflows/3d_stuff/` directory is source/reference material during
development. Preserve those originals; copy required workflow templates and
documentation into the standalone `3d_stuff/` directory. The finished directory
must be movable to another repository without breaking imports or paths.

## Standalone data layout and stage hand-offs

The app owns its input/output folders inside `3d_stuff/`; it must not write to
the parent Story Builder folders:

```text
3d_stuff/
├── input/
├── output/game_assets/<job_id>/
│   ├── input/
│   ├── stage01_concepts/
│   ├── stage02_multiview/
│   ├── stage03_reconstruction/
│   ├── stage04_meshripple/
│   ├── stage05_preview/
│   ├── stage06_blender/
│   ├── stage07_rigged/
│   └── job_manifest.json
└── workflows/
```

The hand-off is explicit: selected image → optional multiview images → one
engine mesh → GLB preview → optional MeshRipple mesh → optional Blender exports
→ optional rigged asset. Every stage reads the previous persisted path and
writes a new immutable artifact.

## Parameter-tuning page

Provide an Advanced Parameters page/drawer whose controls are generated from
the live `/object_info` schemas. Show friendly labels, tooltips, recommended
defaults, reset-to-default, and an expandable raw-values view. Only controls
for the selected engine are shown, and invalid values are rejected before a
job is queued.

Recommended starting values (editable):

* Pixal3D: resolution `1024`, pipeline `1024_cascade`, steps `20`, guidance
  `3.0`, texture guidance `3.0`, background `auto_remove`, camera `moge`, mesh
  scale `1.0`, camera resolution `512`, force offload enabled.
* UltraShape: discovered checkpoint, dtype `bfloat16`, low VRAM enabled,
  refinement steps `20`, guidance `3.0`, octree resolution `384`, chunks
  `8000`, remove background enabled.
* Hunyuan3D: expose only controls reported by its live installed schema. If no
  image-to-3D node is discoverable, disable the engine with an explanation.
* GLB export: decimation target `100000`, texture size `2048`, remesh off.
* Blender: seed plus portable blend/config paths; default `MeshCleanUp.blend`.
* SkinTokenRig: device `auto`, GLB output, transfer/postprocess enabled,
  skeleton `Keep model names`, smooth angle `60`, discovered checkpoint.

You are working inside an existing local WebUI project. First inspect the existing project thoroughly: framework, routing, component patterns, styling system, API utilities, job handling, file upload patterns, and folder structure. Reuse the architecture and engineering patterns where sensible, but create a visually distinct interface for this 3D asset tool.

Goal

Build a new local WebUI where the user uploads either:

one image, or

multiple independent images as a batch.

Each image becomes one separate 3D asset job. A text prompt first uses the configured
text-to-image workflow and then follows the same image-to-3D path.

The pipeline must run locally and automatically pass the output of each stage into the next stage:

Optional Qwen multi-angle preprocessing -> exactly one selected reconstruction
engine (Pixal3D, UltraShape, or Hunyuan3D) -> browser GLB preview -> optional
MeshRipple -> optional Blender 4.2 cleanup/export -> optional SkinToken rigging.

Qwen multi-angle is disabled by default. Direct image input must work without it.
MeshRipple is disabled until its isolated worker exists; it must never block the
main reconstruction path.

# Cinematic GSAP interaction and UI specification

The supplied `MiniMax_H3_00009_.mp4` is the visual foundation of the landing page.
Do not replace it with a static hero or make the interface appear immediately.

## Scroll sequence

Use GSAP `ScrollTrigger` with a pinned hero section and a scrubbed video timeline.
The video should advance continuously and smoothly, but scrolling must not be
quantized to one video frame per wheel event. Use a five-frame keyframe/scroll
quantum as the minimum visual unit (approximately 5 frames at the source frame
rate), with interpolation and easing between keyframes. Trackpad, touch, keyboard,
and large wheel movements must remain usable and must not skip the final UI state.

The hero remains pinned while the user scrolls through the sequence. Near the
end, slow the scrub slightly so the final robot-leaning-on-the-box composition is
clearly readable. The final video frame is held after the scroll timeline ends.

## End-frame prompt interface

The robot's box is the visual location for the prompt interface. Do not place a
second obvious card on top of it. Preserve the last video frame as the background
and place a transparent/texture-matched HTML overlay precisely inside the visible
front face of the box. The overlay should match the box perspective, edge color,
lighting, and shadow. This is preferable to baking text into the video because
the prompt must remain editable, accessible, responsive, and keyboard-operable.

The overlay contains, in this order:

1. a compact prompt textarea with placeholder `Describe your 3D game asset...`;
2. an image-upload icon/button with tooltip `Upload reference image`;
3. a `Refine for game asset` icon button;
4. a primary `Generate concepts` button.

The textarea is the main interaction and is centered on the box face. Upload and
refine controls sit along its lower edge; the primary action sits at the lower
right. On narrow screens the controls stack below the textarea while remaining
inside the box-aligned overlay. Dragging an image onto the box must also trigger
the upload flow.

After the scroll reaches the held final frame, reveal the overlay controls with a
short, gentle GSAP sequence: box highlight first, textarea fade/slide second,
then upload/refine icons, then the primary button. Keep motion restrained and
respect `prefers-reduced-motion`.

## Landing controls retained outside the box

Below the hero/box interaction, reveal the workbench configuration panel. It
contains the input mode (single image or batch), asset name, Static/Animated
mode, reconstruction engine selector (Pixal3D, UltraShape, or Hunyuan3D),
optional Qwen multi-angle toggle, optional MeshRipple toggle, optional Blender
cleanup toggle, texture/output settings, and `Run 3D pipeline`.

The Qwen multi-angle control is off by default. Direct image-to-3D remains the
shortest path. MeshRipple is visibly marked optional/unavailable until its
worker is installed.

## Hover-only navigation

Keep the navbar hidden or reduced to a small unobtrusive affordance during the
cinematic sequence. Reveal it on pointer hover (and on keyboard focus) with a
subtle opacity/slide transition. Retain these destinations:

* Home / cinematic landing
* Create / workbench
* Generated Results / stage outputs
* Jobs / history and retryable runs
* Settings / ComfyUI connection and model discovery

The navbar must not cover the robot or box. On touch devices, provide a visible
menu button because hover is unavailable.

## Generated Results progression

Each completed stage opens or updates a Generated Results view containing the
stage output and Three.js GLB viewer. In automated mode, the next stage starts
after the current result is persisted and acknowledged. In manual mode, the
result remains visible and a clearly labeled `Next` button starts the next stage.
The user can return to earlier results without losing artifacts.

## Processing/loading experience

Long-running ComfyUI and worker jobs must never leave the user staring at a
blank page. While a stage is running, show a dedicated cinematic loading state
inside the workbench/results shell. Use a lightweight looping visual (the
provided loading artwork/video or a CSS/GSAP animation) with a clear label for
the active stage. Loading animation is presentation-only and must not pretend a
stage succeeded.

Show a real progress bar whenever ComfyUI websocket progress or worker progress
is available. Display stage name, percentage when known, elapsed time, queue
position when available, and an indeterminate animated bar when the backend does
not expose a trustworthy percentage. The UI must distinguish queued, running,
completed, failed, skipped, and unavailable-optional states.

As soon as an intermediate artifact is persisted, expose it in an inspectable
Generated Results entry without waiting for the entire pipeline. Image outputs
use an image viewer; GLB outputs use the Three.js viewer; meshes and packages
also show metadata and download controls. A `Continue`/`Next` action is shown in
manual mode, while automated mode proceeds after persistence and validation.
Never show a placeholder artifact as a completed result. Errors must include the
backend stage/node and a retry-from-stage action.

All progress and intermediate-result updates must come from the ComfyUI `/ws`
events or `/history/<prompt_id>` polling and the isolated worker status API;
GSAP only animates presentation of those real state changes.

## Visual language

Use the dark graphite 3D-workbench aesthetic with restrained electric violet and
teal accents, technical typography, large drag/drop surfaces, and three animated
themes: Light, Dark, and Fire. Use GSAP for route/stage transitions, progress
reveals, and micro-interactions—not for distracting perpetual motion.

Do NOT require multi-angle images by default. Pixal3D, UltraShape, and
Hunyuan3D must each accept the direct image path. The Qwen multi-angle graph is
an optional preprocessor only. Its required LoRA is installed at
`ComfyUI/models/loras/lenovo_z.safetensors`; the UI may enable this stage after
the adapter verifies the live model list.

Supplied files

The supplied files are UI-exported ComfyUI graphs, not API-format graphs. Generate
runtime /prompt adapters from the live /object_info schemas. Do not refer to
nonexistent API template files.

Critical rule: never invent installed node schemas

At application startup, call ComfyUI /object_info and verify every required class_type and its input schema.

Existing public nodes expected:

LoadImage

RunningHubPixal3DModelLoader

RunningHubPixal3DImageTo3D

RunningHubPixal3DSaveGLB

UltraShapeLoadModel

UltraShapeLoadCoarseMesh

UltraShapeRefine

UltraShapeSaveGLB

SkinTokenRigTrimesh

BlenderGenericNode

If an installed node's schema differs from the template, adapt the runtime workflow to the schema reported by /object_info; do not silently guess.

Custom ComfyUI node package to create

Create:
ComfyUI/custom_nodes/comfyui_game_asset_pipeline/

Do not fabricate replacement nodes for functionality already provided by the
installed packages. Use BlenderGenericNode and SkinTokenRigTrimesh. Implement
MeshRipple only as a separately guarded worker/node after its runtime is ready.

A. MeshRippleArtistMesh (future optional worker)

class_type = "MeshRippleArtistMesh"

Inputs:

source_mesh_path: STRING

model_variant: enum 10k_full | 20k_nsa

checkpoint_path: STRING

sample_points: INT default 40960

condition_points: INT default 16384

target_faces: INT default 20000

seed: INT

top_k: INT

top_p: FLOAT

temperature: FLOAT

output_dir: STRING

filename_prefix: STRING

Outputs:

output_path: STRING

status: STRING

model_3d: FILE_3D_GLB when supported

Behavior:

Load the source GLB/OBJ with trimesh.

Normalize it exactly once and save transform metadata.

Uniformly sample sample_points surface points.

Select/resample exactly condition_points points for the Michelangelo point-cloud conditioning expected by MeshRipple.

Adapt the official MeshRipple inference code into a reusable inference class. Do NOT shell out to main.py for every job if a persistent worker can keep the model loaded.

Use official checkpoints:

10k: meshRipple_10k.pth

20k: meshRipple_nsa.pth

Run point-cloud-conditioned generation and write a clean GLB/OBJ.

Restore original scale/orientation.

Preserve logs and return the output path.

Important: MeshRipple is NOT a normal mesh decimator. It is point-cloud-conditioned artist-mesh generation. The wrapper must derive the point cloud from the Pixal3D/UltraShape geometry, mirroring the paper's two-stage image-conditioned approach.

Because MeshRipple's published environment differs from ComfyUI, prefer an isolated worker environment/process with a small localhost IPC API rather than contaminating the main ComfyUI Python environment. Keep the worker persistent between jobs.

B. Blender cleanup/export integration

Use the installed BlenderGenericNode. Do not invent a BlenderGameReadyBake node.
The default asset is MeshCleanUp.blend; SimpleRig.blend is only for animation.

Run the installed Blender executable in background/headless mode with a generated Python script.

Inputs have three roles:

textured_source_mesh: Pixal3D GLB, used as material/PBR source.

highpoly_geometry_mesh: UltraShape refined GLB if enabled; otherwise Pixal3D GLB. Used for normal/AO high-to-low bake.

artist_lowpoly_mesh: MeshRipple result when MeshRipple is enabled. If it is
disabled, use the selected reconstruction mesh as the cleanup/export input and
skip high-to-low baking that depends on a separate artist mesh.

Required output processing:

Import all source meshes.

Clean low-poly mesh: merge-by-distance, recalc normals, remove degenerate geometry where safe.

UV unwrap the active cleanup/export mesh.

Bake/transfer to the low-poly UVs:

Base Color from the reconstruction material source

Roughness from Pixal3D

Metallic from Pixal3D

Tangent-space Normal from high-poly geometry

Ambient Occlusion from high-poly geometry

Use Cycles baking with configurable ray/cage distance and safe defaults. If a map fails, mark that map failed but do not delete successful outputs.

Build a PBR material on LOD0.

Generate:

LOD0 = 100%

LOD1 = 50%

LOD2 = 25%

LOD3 = 10%
Keep UVs/materials.

Generate a separate collision mesh using a convex hull by default. Name it clearly, e.g. <asset>_COLLISION.

Export:

<asset>_LOD0.glb

<asset>_LOD1.glb

<asset>_LOD2.glb

<asset>_LOD3.glb

<asset>_COLLISION.glb

<asset>.fbx when possible

PBR textures

asset_manifest.json

ZIP containing the complete package.

Return primary LOD0 path, manifest path, zip path and status.

Do not apply a destructive decimation to the archived master Pixal3D/UltraShape meshes.

TokenRig

Use the installed SkinTokenRigTrimesh node for animated assets only.

Patch:

mesh_path = final LOD0 GLB

use_transfer = true

use_postprocess = true

export_format = glb by default

Keep the unrigged LOD package as well as the rigged asset.

ComfyUI API integration

Default base URL from env:
COMFYUI_URL=http://127.0.0.1:3008

Implement:

upload image to ComfyUI input

clone workflow JSON per job

patch runtime placeholders

POST API graph to /prompt

track prompt ID

listen to /ws if available for execution progress; fall back to /history/<prompt_id> polling

capture errors per node

resolve the exact produced files

persist a job manifest containing every stage input/output path

Never confuse normal ComfyUI browser workflow JSON with API-format workflow JSON.

Pipeline behavior

For each uploaded image create a job with these stages:

queued -> input(text-to-image or upload) -> qwen_multiangle(optional) ->
reconstruction(pixal3d OR ultrashape OR hunyuan3d) -> preview ->
meshripple(optional/unavailable until worker exists) -> blender(optional) ->
skintoken(optional) -> complete

Rules:

The reconstruction engine is selected explicitly; engines are alternatives and
must not be silently chained.

asset_mode=static: skip TokenRig.

asset_mode=animated: run TokenRig.

If UltraShape is skipped, use the selected reconstruction mesh as the high-poly
source. If MeshRipple is disabled, do not require an artist-lowpoly input or
artist-mesh bake; the Blender cleanup/export stage must still work.

Batch uploads run as separate jobs. GPU-heavy stages should be serialized by default; make concurrency configurable.

A failed job must not corrupt other jobs.

Support retry from the failed stage without rerunning earlier successful stages.

Save every stage artifact, never overwrite it.

Model/checkpoint discovery

Do not hardcode the UltraShape checkpoint filename.

At startup:

query /object_info

inspect ComfyUI/models/UltraShape/

select the installed UltraShape checkpoint if exactly one valid checkpoint exists

otherwise expose a settings dropdown.

For MeshRipple paths use environment/config:

MESHRIPPLE_ROOT

MESHRIPPLE_10K_CHECKPOINT

MESHRIPPLE_20K_CHECKPOINT

For Blender:

BLENDER_EXECUTABLE=/home/riki/web_dev/setup_comfy_and-stuff/env_setup/blender-4.2/blender
BLENDER_BLEND_FILE=/home/riki/web_dev/setup_comfy_and-stuff/env_setup/sources/comfyUI-blender-wrapper/exampleBlendFiles/MeshCleanUp.blend
BLENDER_CONFIG_FILE=/home/riki/web_dev/setup_comfy_and-stuff/env_setup/sources/comfyUI-blender-wrapper/exampleBlendFiles/meshCleanUpExampleConfig.config

Do not assume the desktop `blender` command is Blender 4.2. Resolve and validate
the explicit executable path. Keep the `blender311` environment because the
host-built Blender binary depends on its Python 3.11 runtime library.

WebUI

Use the existing WebUI project as the structural reference, but create a new theme:

dark graphite 3D-workbench aesthetic

restrained electric violet + teal accents

large drag/drop area

clean technical typography

no copying the old project's theme

Main screen:

Single / Batch upload

Asset name

Asset mode: Static | Animated

Quality: Standard | Hero

MeshRipple target: 10K | 20K

Texture: 2K | 4K

Engine preset: Generic | Unity | Unreal

Generate button

Job view:

original image

horizontal/vertical pipeline stage tracker

one card per stage

live status and elapsed time

GLB preview for every mesh-producing stage

file metadata: faces/verts, texture size, file size

download button for every completed stage

final "Game Ready Package" card

final rigged preview if Animated

Use Three.js or <model-viewer> for GLB preview depending on what fits the existing stack best.

Output layout

Use a deterministic job folder:

output/game_assets/<job_id>/

with:

input/

stage01_pixal3d/

stage02_ultrashape/

stage03_meshripple/

stage04_game_ready/

stage05_rigged/

job_manifest.json

Quality safeguards

Before declaring a job complete, validate:

output GLB loads successfully

LOD0 has vertices/faces

UV layer exists

normal map exists

base-color map exists

material references resolve

LOD triangle counts decrease monotonically

collision mesh exists

for animated mode: skeleton and skin weights exist

Surface warnings in the UI instead of hiding them.

Deliverables

Implement the complete feature, not just mock screens.

Include:

working frontend

backend/API integration

workflow loader/patcher

MeshRipple custom ComfyUI worker/node

Blender game-ready custom ComfyUI node + Blender Python script

TokenRig integration

job persistence/retry

batch processing

.env.example

setup instructions

a smoke-test command

unit tests for workflow patching and stage transitions

Do not alter unrelated behavior in the existing WebUI.

Implementation order and definition of done

Phase 1 is the usable MVP: direct image upload, one selected reconstruction
engine, ComfyUI /prompt adapter, job progress, GLB output, and browser preview.
Text input may call the existing text-to-image workflow before entering this
same path.

Phase 2 adds optional BlenderGenericNode cleanup/export using Blender 4.2 and
the portable paths above, then optional SkinTokenRigTrimesh for animated jobs.

Phase 3 adds Qwen multi-angle after its adapter verifies all referenced models,
including `lenovo_z.safetensors`. It remains optional/off by default, while
direct image-to-3D remains unaffected.

Phase 4 adds the isolated MeshRipple worker. Its absence must produce a clear
optional-stage status, never a failed reconstruction job.

Before each phase is declared complete, verify only the relevant live
`/object_info` schemas, model paths, output files, and UI state. Do not invent
node names, API graphs, model files, or successful stages. Preserve all source
artifacts and make failed stages retryable.
