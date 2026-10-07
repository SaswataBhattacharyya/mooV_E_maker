# video_scene_summarizer

Local-first video analysis pipeline with:

1. YouTube search and download
2. Cut-based scene detection
3. Keyframe-first visual analysis
4. Frame-to-frame delta narration
5. Transcript fusion
6. Final whole-video summarization
7. Adjacent-scene continuity analysis
8. Streamlit inspection UI

The current pipeline is no longer the old “send a batch of scene frames to the VLM and append the response” flow.

The implemented visual-analysis path is now:

1. detect cut-defined scenes
2. extract scene frames
3. keep only selected keyframes
4. fully analyze important keyframes
5. compare adjacent kept frames and describe only the delta
6. stitch keyframe text + deltas into one scene story
7. compare adjacent scene stories for continuity
8. stitch all scene stories into one video story
9. combine scene transitions + video story + transcript + metadata into the final summary

## Setup

Bootstrap the repo with:

```bash
chmod +x *.sh
./install_and_setup.sh
```

`install_and_setup.sh` now delegates to `./bootstrap_vm.sh`.

The analysis runtime requires Ollama and the configured `qwen3.6:35b` model. It uses direct Ollama calls. Hermes/OpenClaw supervisor paths are not part of this application.

## Main Entry Points

### Combined flow

```bash
./run_video_scene_summarizer.sh
```

This does:

1. YouTube search
2. download
3. analysis

### Analysis-only flow

```bash
./run_video_analysis.sh
```

This analyzes already-downloaded videos from a local folder such as `out_videos/`.

### Download-only flow

```bash
./run_video_download.sh
```

### Streamlit UI

```bash
./run_streamlit_app.sh
```

Default Streamlit port:

- `3020`

The launcher matches the `image_analyzer` behavior:

1. host defaults to `0.0.0.0`
2. port defaults to `3020`
3. it prompts for a different port only in interactive mode

## Models

Current model roles:

1. `qwen3.6:35b`
   - full keyframe and pairwise frame-delta analysis
   - scene-story stitching and optional compaction
   - adjacent-scene continuity and final whole-video summary
2. Whisper `small`
   - audio transcription

## What A “Scene” Means

In this repo, a scene means:

- the frames between two adjacent visual cuts

This repo does not currently try to detect higher-level coherence-based scenes.

So:

- one cut-defined segment = one scene

## Analysis Flow

When a video enters the analysis stage, the pipeline does this:

1. extract audio to MP3
2. transcribe with Whisper
3. detect cut-defined scenes with `ffmpeg`
4. extract frames for each scene
5. select keyframes within each scene
6. fully analyze selected keyframes with:
   - VLM
   - YOLO
   - Florence-2
   - OCR
   - dominant color extraction
7. compare each adjacent kept keyframe pair and describe only the differences
8. stitch those full-frame analyses and deltas into one scene explanation
9. optionally compact the scene explanation
10. concatenate all scene explanations into `video_scene.txt`
11. stitch all scenes into `video_story.txt`
12. summarize from:
   - metadata
   - scene text
   - video story text
   - transcript

## How Frame Comparison Works

The current repo uses two different frame-comparison ideas.

### 1. Scene boundary detection

This decides where one cut-defined scene ends and the next begins.

Mechanism:

1. `ffmpeg` scene-change score
2. threshold from `configs/settings.yaml`
3. minimum-scene-length merge rule

### 2. Keyframe change scoring inside a scene

This decides which frames are different enough to keep.

Mechanism:

1. grayscale load
2. resize to `160x90`
3. absolute pixel difference
4. normalized change score

Selected frames always try to include:

1. first
2. midpoint
3. last

Additional frames are kept when the change threshold is crossed.

## Per-Scene Visual Pipeline

Inside each cut-defined scene:

1. pick kept keyframes
2. run full analysis on checkpoint frames
3. compare adjacent kept frames
4. emit:
   - full frame JSON/text
   - delta JSON/text
5. stitch them into:
   - `scene_<n>_raw.txt`
   - `scene_<n>.txt`
   - `scene_story.json`

The key design rule is:

- first kept frame gets a full description
- later kept frames get delta descriptions relative to the previous kept frame

## Output Layout

For each processed video:

```text
outputs/<video_name>/
  metadata.json
  audio.txt
  video_scene.txt
  video_story.txt
  video_story.json
  summary_video.txt
  summary_video.json
  scenes/
    scene_1/
      frame_000001.jpg
      ...
      analysis/
        frame_0001_full.json
        frame_0001_full.txt
        frame_0001_to_frame_0002_delta.json
        frame_0001_to_frame_0002_delta.txt
        scene_story.json
        scene_story.txt
      scene_1_raw.txt
      scene_1.txt
```

Important files:

1. `metadata.json`
   - video metadata
   - scene timing
   - scene output paths
2. `audio.txt`
   - full transcript
   - timestamped transcript segments
3. `video_scene.txt`
   - final per-scene text threaded in order
4. `video_story.txt`
   - stitched whole-video narrative trail
5. `video_story.json`
   - structured video story bundle
6. `summary_video.txt`
   - final whole-video summary
7. `scene_<n>/analysis/*.json`
   - full keyframe analysis and frame-delta records

## Streamlit UI

The Streamlit app exposes:

1. input/output paths
2. transcript fusion toggle
3. cache reuse toggle
4. frame extraction FPS
5. scene compaction toggle
6. live event log
7. final per-video summary
8. per-scene scene text
9. keyframe images and full descriptions
10. frame-pair delta JSON/text
11. transcript slice per scene

## Runtime boundary

This repository is intentionally a standalone direct-Ollama application. It does not install, start, or configure an agent supervisor. An external agent may invoke the documented launcher scripts, but the summarizer itself owns the analysis request and uses only `qwen3.6:35b`.

## Notes

1. The repo runtime expects `PYTHONPATH=src`; all launcher scripts already set it.
2. The repo no longer depends on the sibling `image_analyzer` folder at runtime.
3. The copied image-analysis capability now lives under `src/video_scene_summarizer/providers/` and `src/video_scene_summarizer/processing/frame_detail.py`.
