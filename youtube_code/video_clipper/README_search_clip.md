# search_clip

`search_clip` is a prompt-based batch video search utility. It scans every video in a folder, scores sliding windows against a text query, saves JSON results, and can optionally extract merged clips.

## Files

- `search_clip.py` - main CLI
- `search_config.py` - editable defaults and constants
- `search_video_utils.py` - ffmpeg/ffprobe helpers and clip extraction
- `search_query_utils.py` - query refinement helpers and CLI prompt helpers
- `search_json_utils.py` - JSON saving and match merging
- `search_model_internvideo.py` - InternVideo2 wrapper with mock scorer fallback
- `requirements_search_clip.txt` - light dependency file

## Setup

1. Install Python 3.10+.
2. Install `ffmpeg` and make sure both `ffmpeg` and `ffprobe` are in `PATH`.
3. Optional: create a virtual environment.
4. Install Python requirements:

```bash
pip install -r requirements_search_clip.txt
```

5. Optional for query refinement: install Ollama and pull the model:

```bash
ollama pull qwen2.5:3b
```

## Run

Run the script directly:

```bash
python search_clip.py
```

You will be prompted for:

- input video folder
- output folder
- text query
- LLM refinement on/off
- Ollama model name when refinement is enabled
- clip length
- overlap
- score threshold
- top-k clips per video
- extract clips or JSON only
- mock scorer on/off

## Without Ollama

Leave `LLM query refinement` set to `n`. The pipeline will use the original query only.

## With Ollama

Turn `LLM query refinement` on. The script will call local `ollama` and ask `qwen2.5:3b` for one refined query plus three alternatives. If Ollama fails, the script falls back to the original query automatically.

## Output Layout

The script writes outputs like this:

```text
output_root/
  query_slug/
    json/
      video1_matches.json
      video2_matches.json
    clips/
      video1_000123_000131.mp4
      video1_000500_000510.mp4
```

## InternVideo2 Integration

The pipeline is fully wired except for the exact InternVideo2 repository-specific loading code.

Edit:

- `search_model_internvideo.py`

Look for:

```python
# TODO: adapt model loading to exact InternVideo2 repo layout
```

You need to replace the placeholder loader and scorer with the exact imports, checkpoint loading, preprocessing, and similarity call required by your InternVideo2-CLIP 1B setup.

Until then, keep `Use mock scorer mode` enabled to test the full pipeline flow end-to-end.
