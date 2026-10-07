# Plan: Backend Audio Split -> Edit -> Reassemble Pipeline

This file records the current understanding of the required automation pipeline.

## Implementation Status

The following pieces have now been built in the repo:

- shared splitter core:
  - `utils/audio/scene_splitter.py`
- shared Step Audio EditX edit driver:
  - `utils/audio/scene_edit_driver.py`
- shared concat core:
  - `utils/audio/scene_concat.py`

- ComfyUI nodes:
  - `nodes/audio/scene_splitter_node.py`
  - `nodes/audio/scene_edit_driver_node.py`
  - `nodes/audio/scene_concat_node.py`

- CLI scripts:
  - `scripts/split_scene_audio.py`
  - `scripts/edit_scene_clips.py`
  - `scripts/concat_scene_audio.py`

- node registration:
  - `nodes.py` now registers:
    - `✂️ Scene Splitter`
    - `🎛️ Scene Edit Driver`
    - `🧩 Scene Concat`

### Current Verification State

- Splitter CLI: smoke-tested
- Concat CLI: smoke-tested
- Enriched JSON generation: smoke-tested
- ComfyUI node registration: implemented in code, not runtime-verified in a live ComfyUI session here
- Step Audio EditX batch edit driver:
  - implemented
  - requires a valid ComfyUI root for standalone CLI mode because the Step Audio EditX node imports `folder_paths`
  - standalone script supports this via `--comfyui-root` or `COMFYUI_ROOT`

## What The User Wants

The current `TTS SRT` workflow already does:

- timed audio generation
- multi-character generation
- scene-level output audio

What is missing is:

- post-generation emotion editing for selected regions
- post-generation style/speed editing for selected regions
- possible voice replacement for selected regions
- automatic split and reassembly around those selected regions

The user does **not** want to rely only on ComfyUI graph logic for this part.
The user is open to using the repo's Python code, models, and node logic directly in a backend script.


## Core Idea

The final architecture should be:

1. Generate full scene audio using the existing timed multi-character TTS workflow
2. Use timing instructions to split the scene audio into multiple numbered clips
3. Edit only the clips that need changes
4. Reassemble the full scene by clip order

The timing instructions can come from:

- SRT-like timing text
- JSON timing file
- any structured file containing:
  - `start`
  - `end`
  - optional text
  - optional edit instructions


## Important Clarification About Audio Wave Analyzer

Current behavior of `🌊 Audio Wave Analyzer`:

- It accepts manual regions
- It can extract multiple regions
- But when multiple regions are selected, it concatenates them into a **single** `segmented_audio` output

So the current analyzer is **not** enough for the required backend split pipeline.

It is useful for:

- timing verification
- region discovery
- extracting one region at a time

It is not sufficient for:

- automatic multi-file splitting
- creating one output per region
- preserving untouched left/right spans as separate clips

### How regions are currently specified in AWA

Currently, the Audio Wave Analyzer does **not** accept a JSON input port for split instructions.

It currently supports:

- manual region entry through the `manual_regions` text field
- optional labels via `region_labels`
- export formatting via `export_format`

The current `manual_regions` format is plain text like:

```text
1.5,3.2
4.0,6.8
8.1,10.5
```

So:

- region input is currently **text**
- not a structured JSON input socket
- not a dedicated split-manifest input

This is why using AWA directly for the new backend automation is not the preferred approach.


## What The User Wants The Splitter To Do

The user wants a splitting tool that takes:

- one input scene audio
- one timing instruction file

And produces **multiple independent audio files**, not one concatenated output.

### Example input edit ranges

- `5.00 - 10.00`
- `18.00 - 25.00`
- `30.00 - 40.00`

### Required split output

The splitter must produce **all required adjacent clips**, including untouched regions:

- `0.00 - 5.00`
- `5.00 - 10.00`
- `10.00 - 18.00`
- `18.00 - 25.00`
- `25.00 - 30.00`
- `30.00 - 40.00`
- `40.00 - end`

This is the key requirement.

The split logic must:

- sort ranges
- fill untouched gaps automatically
- include leading and trailing untouched parts
- emit all clips in scene order


## Meaning Of The Timing / Edit File

The input timing/edit file will only list the regions that need processing.

It will contain:

- `start`
- `end`
- `text`
- parameters for Step Audio EditX editing

It does **not** need to explicitly list untouched regions.

The splitter still needs to infer untouched regions automatically from:

- scene start to first edit range
- gaps between edit ranges
- last edit range to scene end

### Required JSON shape

The JSON should be the working format for the backend flow.

Example:

```json
[
  {
    "start": 5.0,
    "end": 10.0,
    "text": "I can't believe this happened.",
    "edit_type": "emotion",
    "emotion": "sad"
  },
  {
    "start": 18.0,
    "end": 25.0,
    "text": "Keep your voice down.",
    "edit_type": "style",
    "style": "whisper"
  }
]
```

### Required post-split JSON enrichment

After splitting, the tool should append the generated split clip filename into the JSON entry itself.

That means each target edit item should become something like:

```json
[
  {
    "file_name": "scene_02.wav",
    "start": 5.0,
    "end": 10.0,
    "text": "I can't believe this happened.",
    "edit_type": "emotion",
    "emotion": "sad"
  }
]
```

This `file_name` field is critical because it becomes the bridge between:

- split stage
- edit stage
- reassembly stage

### Optional text-file compatibility

If text format is still supported, the parser must convert it into the same internal JSON structure.

But JSON should be treated as the canonical automation format.


## Required Output Naming Convention

The split output files should be named in scene order.

### Split files

Naming format:

- `name_01.wav`
- `name_02.wav`
- `name_03.wav`

or similar zero-padded index naming.

The important part is:

- stable scene order
- numeric suffix
- predictable sorting

### Edited files

If a clip is edited, the edited version should be saved with:

- `edited_name_02.wav`

That means:

- original split file stays available
- edited version is clearly marked
- reassembly can choose edited version if present, otherwise original version

### Naming requirements summary

Split stage:

- `scene_01.wav`
- `scene_02.wav`
- `scene_03.wav`

Edit stage:

- `edited_scene_02.wav`
- `edited_scene_05.wav`

The numeric suffix is the clip order authority.


## Required Metadata Per Split Clip

There should be:

- one scene-level manifest for all clips
- and the edit JSON should be enriched with `file_name` for target clips

Minimum metadata for the scene manifest:

- clip index
- start time
- end time
- duration
- kind: `edited_target` or `untouched`
- original filename
- split filename
- edited filename if it exists

Example:

```json
{
  "clip_index": 2,
  "start": 5.0,
  "end": 10.0,
  "duration": 5.0,
  "kind": "edited_target",
  "text": "I can't believe this happened.",
  "source_file": "scene.wav",
  "split_file": "scene_02.wav",
  "edited_file": "edited_scene_02.wav"
}
```


## Editing Stage Requirements

After splitting, a backend script should inspect the enriched JSON / manifest and only send target clips for editing.

### For Step Audio EditX

It should receive:

- the split audio file
- the text for that clip
- edit type and parameters

Typical Step edit modes:

- emotion
- style
- speed
- paralinguistic

Examples:

- emotion = sad
- style = whisper
- speed = slower

### Iterative edit execution model

The backend should process one clip at a time:

1. read JSON item
2. load `file_name`
3. map JSON fields to Step Audio EditX parameters
4. run edit
5. save output as `edited_<file_name>`
6. continue to next JSON item

This is intentionally iterative, not batch-all-at-once.

### Relation To `audio_emotion.json`

There is a desired per-audio edit instruction file:

- [audio_emotion.json](/home/saswata/web_dev/website_design/TTS-Audio-Suite/example_workflows/ricky/audio_emotion.json)

The backend tool should be able to:

- read JSON entries
- map them to the proper Step Audio EditX parameters
- send the corresponding split audio to the edit stage

So the effective backend contract becomes:

- split stage enriches JSON with `file_name`
- edit stage consumes enriched JSON
- edit stage writes `edited_*.wav`

### For Voice Change

Step Audio EditX is not the correct tool for true voice replacement.

Voice replacement should be handled separately through:

- re-generation of that line with a target voice
- or a voice conversion pipeline

So the backend should support at least two edit paths:

1. `step_edit`
2. `voice_regen_or_vc`


## Reassembly Requirements

After all target clips are edited, the system must rebuild the scene in numeric order.

Rule:

- if `edited_name_XX.wav` exists, use it
- otherwise use `name_XX.wav`

Then concatenate in ascending clip index.

This is a sequential append operation, not a mix operation.

So the required primitive is `concat`, not `overlay`.

### Multi-concat requirement

If existing `AudioConcat` only handles two inputs at a time, the system needs either:

1. a backend multi-concat utility, or
2. a new `AudioConcatMulti` node / helper

This multi-concat tool should:

- collect all numbered clips
- sort by numeric suffix
- substitute edited clips when present
- concatenate all clips into one final scene audio


## Relation To Existing Repo Nodes

Existing repo pieces that are relevant:

- `🌊 Audio Wave Analyzer`
  - useful as reference implementation for region extraction
  - already has JSON export mode
  - not sufficient as-is for multi-file split output

- `🎨 Step Audio EditX - Audio Editor`
  - useful for editing the extracted clips

- `AudioConcat`
  - already exists and is used in example workflows
  - currently oriented toward pairwise concatenation inside ComfyUI graphs

- `🥪 Merge Audio`
  - exists as a node
  - is more for merging/mixing than simple ordered reattachment

For backend automation, it may be simpler to implement direct Python audio concatenation rather than chaining many `AudioConcat` calls in ComfyUI.


## Proposed Engineering Direction

### Preferred Direction: Separate Backend Tools

The preferred architecture is **not** to modify the Audio Wave Analyzer first.

Instead, build separate backend tools that reuse the same extraction logic where useful.

Reason:

- AWA is currently a waveform analysis / visualization tool
- it does not currently accept JSON edit instructions as a proper input
- it does not natively output one file per region
- forcing save-path, JSON enrichment, and multi-file orchestration into AWA would overload the node

So the cleaner design is:

1. keep AWA as analysis / visualization / one-region extraction reference
2. build a separate backend splitter tool
3. build a separate backend edit driver
4. build a separate backend concat tool

## Delivery Format Decision

These new capabilities should be built in two forms:

1. ComfyUI node version
2. Standalone script / CLI version

This is now a requirement.

Reason:

- the node version keeps the tools usable inside ComfyUI workflows
- the script version makes them callable by bash, agents, or backend automation
- both should reuse the same underlying implementation

So the architecture should be:

- shared reusable logic in utility modules
- thin node wrappers for ComfyUI
- thin script wrappers for command-line use

## Where To Place The New Tools

### Shared core logic

Place the actual reusable implementation under:

- `utils/audio/`

Suggested shared files:

- `utils/audio/scene_splitter.py`
- `utils/audio/scene_edit_driver.py`
- `utils/audio/scene_concat.py`

These should contain the real logic.

### ComfyUI node wrappers

Place the node wrappers under:

- `nodes/audio/`

Suggested node files:

- `nodes/audio/scene_splitter_node.py`
- `nodes/audio/scene_edit_driver_node.py`
- `nodes/audio/scene_concat_node.py`

These should expose the shared logic to ComfyUI.

### Standalone script wrappers

Place the bash / CLI tools under:

- `scripts/`

Suggested script files:

- `scripts/split_scene_audio.py`
- `scripts/edit_scene_clips.py`
- `scripts/concat_scene_audio.py`

These should expose the same shared logic for direct execution.

### If AWA were ever tweaked

If the project later decides to enhance AWA, the necessary additions would be:

- optional JSON input connection for split instructions
- output directory parameter
- automatic multi-file writing
- automatic JSON enrichment with `file_name`
- scene manifest writing

But this is **not** the preferred first implementation.

### Backend Tool 1: Splitter Utility

This separate tool should:

- ask for input audio path
- ask for JSON path
- optionally ask for full transcript text path
- ask for output folder path

Then it should:

- parse the JSON
- split the audio into full ordered clip sequence
- save split clips to the output folder
- enrich target JSON items with `file_name`
- save the enriched JSON to the same folder
- save a full scene manifest to the same folder

This tool should reuse the core time-to-sample extraction logic already present in AWA.

### ComfyUI node version of the splitter

The node version should:

- accept audio input or file path
- accept timing/edit JSON path
- optionally accept transcript text path
- accept output folder path
- save split clips to disk
- save enriched JSON to disk
- save manifest to disk

This should be a file-writing utility node, not just an in-memory tensor output node.

### Backend Tool 2: Edit Driver

This tool should:

- ask for split-audio folder path
- ask for enriched JSON path
- ask for output folder path

Then it should:

- iterate through JSON items one by one
- load the corresponding audio clip by `file_name`
- map JSON fields to Step Audio EditX parameters
- run the edit stage
- save the edited result as `edited_<file_name>`

This tool should use:

- the same folder as output by default, if desired
- [audio_emotion.json](/home/saswata/web_dev/website_design/TTS-Audio-Suite/example_workflows/ricky/audio_emotion.json) semantics as the editing contract

### ComfyUI node version of the edit driver

The node version should:

- accept clips folder path
- accept enriched JSON path
- accept output folder path
- iterate through JSON items one by one
- save edited clips to disk

This is primarily an orchestration / batch node.

### Backend Tool 3: Cleanup Rule

After editing is complete, the tool should remove the unedited counterparts of clips that now have edited replacements.

Rule:

- if `edited_scene_02.wav` exists, delete `scene_02.wav`

Reason:

- no duplicate clip numbers should remain
- later concat stage should see only one file per clip number
- this avoids ambiguity and confusion

### Backend Tool 4: Multi-Concat Utility

This tool should:

- ask for the folder path containing the final clip set
- sort clips by their numeric suffix
- concatenate them in numeric order
- write one final scene output

This is preferable to relying on pairwise `AudioConcat` node chaining for backend automation.

### ComfyUI node version of the concat tool

The node version should:

- accept a folder path
- discover all numbered clips
- sort them by numeric suffix
- concatenate in order
- optionally save final output to disk
- optionally expose the final audio as a normal ComfyUI audio output

This should behave as a true scene rebuild node.


## Recommended Pipeline

### Stage 1: Generate scene

Input:

- SRT-style timed scene script

Output:

- `scene.wav`
- timing report
- adjusted SRT

### Stage 2: Prepare edit instructions

Input:

- second JSON describing only clips that need edits

Output:

- normalized edit instruction JSON

### Stage 3: Split scene

Input:

- `scene.wav`
- edit instruction JSON
- optional transcript text file

Output:

- `scene_01.wav`
- `scene_02.wav`
- `scene_03.wav`
- ...
- enriched edit JSON with `file_name`
- scene manifest JSON

### Stage 4: Edit target clips

Input:

- split clips folder
- enriched edit JSON
- output folder

Output:

- `edited_scene_02.wav`
- `edited_scene_05.wav`
- ...

Cleanup after stage:

- delete `scene_02.wav` if `edited_scene_02.wav` exists
- delete `scene_05.wav` if `edited_scene_05.wav` exists

### Stage 5: Reassemble

Input:

- final clip folder

Output:

- `scene_final.wav`


## What Was Understood From The User

The user wants:

- one main workflow that creates the scene audio
- one second-stage process that edits only selected regions
- timing-driven splitting
- file-based intermediate artifacts
- deterministic naming
- no dependence on manual one-region-at-a-time UI work
- JSON-driven per-clip editing
- automatic file-name insertion into the edit JSON
- iterative one-audio-at-a-time editing
- final sequential multi-concat
- deletion of original unedited target clips once edited versions exist
- prompt-based backend tools for path inputs
- both node and script versions of the new tools

The user is explicitly asking for:

- automatic splitting from timing instructions
- preserved untouched regions
- per-clip editing
- edited file naming with `edited_` prefix
- ordered reassembly
- JSON enriched with `file_name`
- backend mapping from JSON fields to Step Audio EditX parameters
- multi-audio concat according to numeric clip suffix
- split tool separate from AWA, unless a later reason appears to integrate them
- clear repo placement for nodes vs scripts vs shared logic

This is understood correctly.


## Immediate Implementation Target

The next concrete build target should be:

1. shared splitter core in `utils/audio/scene_splitter.py`
2. standalone splitter script in `scripts/split_scene_audio.py`
3. ComfyUI splitter node in `nodes/audio/scene_splitter_node.py`
4. enriched edit JSON format with `file_name`
5. scene manifest format
6. shared Step Audio EditX edit driver in `utils/audio/scene_edit_driver.py`
7. standalone edit script in `scripts/edit_scene_clips.py`
8. ComfyUI edit-driver node in `nodes/audio/scene_edit_driver_node.py`
9. deletion of original target clips when edited replacements exist
10. shared concat core in `utils/audio/scene_concat.py`
11. standalone concat script in `scripts/concat_scene_audio.py`
12. ComfyUI concat node in `nodes/audio/scene_concat_node.py`

This is the correct next step for the automation system.


## New Edits

These are additional requirements discovered after the first implementation pass.

### 1. Clarify Current Scene Edit Driver Behavior

The current implementation in:

- `utils/audio/scene_edit_driver.py`
- `nodes/audio/scene_edit_driver_node.py`

does **not** send clips into a saved ComfyUI workflow JSON file.

It currently works by:

- reading the enriched edit JSON
- iterating over each target clip one at a time
- loading the clip directly from disk
- importing the `🎨 Step Audio EditX - Audio Editor` node code directly
- calling that node's Python method for editing
- saving the result as `edited_<file_name>`

So the current scene edit driver is:

- JSON-driven
- iterative
- direct-Python
- not a workflow runner
- not using a `Load Audio` node
- not dispatching into `example_workflows/ricky/audio_emotion.json`

This behavior should be kept unless a later workflow-runner abstraction is added on purpose.


### 2. Step Audio EditX Emotion / Style Limitations

Step Audio EditX currently supports:

- predefined emotion options
- predefined style options
- predefined speed options
- paralinguistic tags

It does **not** currently expose an audio-guided style or emotion reference input in the same way that IndexTTS-2 does for `emotion_control`.

So for existing audio clip editing:

- Step Audio EditX = preset-driven edit categories
- not reference-audio-guided emotion/style cloning

If custom presets are desired later, the implementation work would likely require:

- extending the Step Audio EditX node option lists
- tracing how those options are converted into Step model prompts / control instructions
- possibly adding a custom mapping layer from user-facing preset names to internal Step edit tokens

This is a separate enhancement from the current split-edit-concat pipeline.


### 3. Add Voice Edit Routing To The JSON-Driven Edit Stage

The enriched edit JSON should support a voice-conversion edit item such as:

```json
{
  "file_name": "scene_02.wav",
  "start": 5.0,
  "end": 10.0,
  "text": "I can't believe this happened.",
  "edit_type": "voice",
  "voice": "Alice.wav"
}
```

Meaning:

- the clip is not sent to Step Audio EditX
- instead it is routed to a voice-change path
- the target voice file is looked up from the voice examples folder
- the result is saved as `edited_scene_02.wav`


### 4. New Voice Change Workflow Contract

The user plans to add a new workflow file:

- `example_workflows/ricky/voice_change.json`

The design intent is:

- input clip from the split stage = source audio
- target voice reference from `"voice"` field in JSON
- perform one-shot voice change
- save `edited_<file_name>`

The `"voice"` field should be resolved by searching the repo voice folders, especially:

- `voices_examples/`

If `"voice": "Alice.wav"` is specified, the system should locate that reference audio file automatically.


### 5. Required Edit Driver Routing Logic

The scene edit driver must be extended so that it becomes a small router:

- if `edit_type` is `emotion`, `style`, `speed`, `paralinguistic`, `denoise`, or `vad`
  - use the existing Step Audio EditX path

- if `edit_type` is `voice`
  - use the voice-change path instead

This means the edit driver should no longer be treated as Step-only.


### 6. Voice Change Path Should Prefer Existing Voice Conversion Capability

For `edit_type = "voice"`, the preferred implementation direction is:

- use the existing voice conversion infrastructure in the repo
- avoid pretending Higgs is a voice changer unless the code proves it is the best option

Current likely candidates:

- `🔄 Voice Changer`
- RVC-based path
- other true VC-capable routes already present in the repo

This should be verified during implementation.

The current assumption for the next implementation pass is:

- use the repo's real voice conversion path
- not Step Audio EditX
- not plain TTS regeneration unless VC is unsuitable


### 7. Voice Change Workflow / Tool Integration Requirement

The next implementation pass should treat node mode and script mode differently.

#### Node mode

The node should stay independent and graph-native.

It should **not** directly import and call another node's Python method the way the current first-pass implementation does.

Instead, the node version should behave like a routing / dispatch helper based on:

- the enriched JSON
- which downstream edit nodes are actually connected

Required node-mode behavior:

- if the scene edit driver node is connected to `🎨 Step Audio EditX - Audio Editor`
  - send only clips whose `edit_type` is:
    - `emotion`
    - `style`
    - `speed`
    - `paralinguistic`
    - `denoise`
    - `vad`

- if the scene edit driver node is connected to a voice-change path
  - send only clips whose `edit_type` is:
    - `voice`

The goal is:

- the scene edit driver node remains independent
- downstream nodes remain explicit in the graph
- routing happens by JSON type + connection presence

This means the node-mode design should move away from the current direct-Python Step-only implementation and become a proper graph router.

#### Script mode

The script version can stay backend-driven and use direct Python integration.

In script mode, one driver can:

- read the enriched JSON
- route Step-style edits into Step Audio EditX backend code
- route voice edits into the voice-change backend code
- save all outputs as `edited_<file_name>`

So script mode can keep internal dispatching without requiring the user to manually wire graph nodes.

This is acceptable because the script version is intended for agent/bash automation rather than graph purity.


### 8. New Build Target For Next Chat

In the next implementation pass, the system should be extended to:

1. add `voice` edit-type support to the enriched JSON contract
2. resolve target voice file names from `voices_examples/`
3. route `voice` edits to a dedicated voice conversion backend path
4. keep Step Audio EditX for style/emotion/speed-type edits
5. save all voice-converted results as `edited_<file_name>`
6. preserve the same concat stage after mixed edit types are complete
7. do **not** require a separate `voice_change.json` workflow
8. assume the user will extend:
   - `example_workflows/ricky/audio_emotion.json`
   with both Step edit and voice change branches if desired for manual node-mode use

This new routing layer should be treated as the next planned extension.


### 9. Updated Manual Workflow Assumption

The user does **not** want a separate dedicated voice-change workflow file anymore.

Instead:

- `example_workflows/ricky/audio_emotion.json`
  should conceptually become the combined manual editing workflow

It may eventually contain:

- Step Audio EditX branch
- voice change branch
- a scene edit driver node that routes clips according to JSON edit type

For manual node-mode use:

- one graph may contain both edit branches
- the scene edit driver node should decide which clip goes to which branch
- clips with Step edit types should not go to the voice branch
- clips with `edit_type = voice` should not go to the Step branch


### 10. Current Caveat To Resolve In The Next Implementation Pass

The current first-pass `scene_edit_driver` implementation is not yet aligned with the desired node behavior.

Current behavior:

- direct Python call into Step Audio EditX
- no graph-based routing
- Step-only

Desired next behavior:

- node version:
  - graph-connected routing behavior
  - separate handling based on downstream node connections

- script version:
  - direct backend dispatch is acceptable
  - route by JSON type internally

This mismatch should be resolved in the next implementation pass.
