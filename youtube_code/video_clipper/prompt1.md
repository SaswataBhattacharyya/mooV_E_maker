I want you to build a Python pipeline called `search_clip` for batch video search and clip extraction.

IMPORTANT: Match the coding style of my existing utility scripts:
- simple prompt-based CLI
- editable defaults at top of file
- use pathlib.Path
- use subprocess for ffmpeg/ffprobe calls
- helper functions + clear main()
- batch process all videos in a folder
- minimal unnecessary abstraction
- robust but readable code
- no web UI, no FastAPI, no classes unless truly needed

Goal of this pipeline:
1. Prompt user for:
   - input video folder
   - output folder
   - text query to search for
   - whether LLM query refinement is ON/OFF (default OFF)
   - if ON, use local Ollama model `qwen2.5:3b`
   - clip length in seconds
   - overlap in seconds
   - score threshold
   - top-k clips to keep per video
   - whether to actually extract clips or only save JSON

2. For every video in the input folder:
   - get duration using ffprobe
   - generate sliding windows over the video
   - each window should be represented by start_sec and end_sec
   - sample a small set of frames from each window using ffmpeg
   - run a video-text retrieval model on that window against the query
   - save raw results to JSON
   - merge overlapping positive windows
   - extract final merged clips with ffmpeg into output folder

3. Output structure should be:
   output_root/
      query_slug/
         json/
            video1_matches.json
            video2_matches.json
         clips/
            video1_000123_000131.mp4
            video1_000500_000510.mp4

4. The code should be split into these files:
   - search_clip.py                 # main CLI
   - search_config.py               # defaults and constants
   - search_video_utils.py          # ffmpeg/ffprobe helpers, window generation, clip extraction
   - search_query_utils.py          # query refinement via Ollama, slugify, prompt helpers
   - search_json_utils.py           # saving/loading/merging JSON
   - search_model_internvideo.py    # retrieval model wrapper
   - requirements_search_clip.txt

5. For model wrapper:
   - create a clean stub/integration layer for InternVideo2-CLIP 1B
   - do NOT hardcode broken repo-specific imports if uncertain
   - make the wrapper modular so I can later adjust loading code
   - include a placeholder section clearly marked:
     `# TODO: adapt model loading to exact InternVideo2 repo layout`
   - but implement the rest of the pipeline fully
   - include a fallback mock scorer mode for testing pipeline flow without the heavy model

6. LLM refinement mode:
   - default OFF
   - if ON, call local Ollama using subprocess or requests to `ollama`
   - model name: `qwen2.5:3b`
   - input = original user query
   - output = short refined search query + 3 alternative phrasings
   - return a small list of candidate queries
   - final retrieval score for a clip should be the max score over all refined query variants
   - if Ollama fails, fall back to original query only

7. JSON format:
   for each video save:
   {
     "video": "...",
     "query_original": "...",
     "query_variants": [...],
     "clip_len_sec": ...,
     "overlap_sec": ...,
     "threshold": ...,
     "raw_matches": [
       {
         "start_sec": ...,
         "end_sec": ...,
         "score": ...,
         "matched_query": "..."
       }
     ],
     "merged_matches": [
       {
         "start_sec": ...,
         "end_sec": ...,
         "score_max": ...,
         "score_mean": ...
       }
     ]
   }

8. Code requirements:
   - use only Python scripts
   - no notebooks
   - include clear comments
   - catch subprocess errors cleanly
   - skip failed videos but continue batch
   - support common video extensions: .mp4 .mkv .mov .avi .webm
   - create folders automatically
   - keep naming and flow similar to my frame extraction script style

9. Also create:
   - a `README_search_clip.md`
   - include exact setup steps
   - include how to run with and without Ollama refinement
   - include where I need to edit model-loading code for InternVideo2

10. In the final response:
   - show the full code for all files
   - do not omit any file
   - ensure imports are correct
   - ensure main script is runnable