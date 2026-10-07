# Scene Surgery Contract

## Input edit manifest

JSON may be a list or `{ "edits": [...] }`. Every item needs numeric `start`, numeric `end`, and usually exact `text`.

```json
[
  {
    "start": 5.0,
    "end": 10.0,
    "text": "I cannot believe this happened.",
    "edit_type": "emotion",
    "emotion": "sad",
    "n_edit_iterations": 1
  }
]
```

Ranges must be positive, within source duration, and non-overlapping. The splitter sorts them, creates untouched gap clips, and adds `file_name` to an enriched JSON file. Do not invent `file_name` before splitting.

The edit driver writes `edited_<original-name>` and routes Step edits or `edit_type: voice`. Voice edits need `voice` resolvable as an audio path or discovered voice key.

## Commands

Run with the ComfyUI Python environment when model-backed editing is involved.

```bash
python TTS-Audio-Suite/scripts/split_scene_audio.py \
  --audio scene.wav --instructions scene_edits.json --output-dir scene_parts

python TTS-Audio-Suite/scripts/partition_scene_edits.py \
  --instructions scene_parts/scene_edits_enriched.json --output-dir scene_parts/routes

python TTS-Audio-Suite/scripts/edit_scene_clips.py \
  --clips-dir scene_parts --instructions scene_parts/scene_edits_enriched.json \
  --output-dir scene_parts/edited --comfyui-root ComfyUI --keep-originals

python TTS-Audio-Suite/scripts/concat_scene_audio.py \
  --clips-dir scene_parts/final --output final_scene.wav
```

Use timed concat when explicit gaps are needed:

```json
[{"file":"scene_01.wav","gap_after_seconds":0.5}]
```

Never delete originals until the final duration, order, timing, and audible transitions are verified.
