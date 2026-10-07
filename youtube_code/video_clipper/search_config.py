#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path

# -------- Defaults (edit if you like) --------
DEFAULT_VIDEO_DIR = "/home/saswata/web_dev/youtube_song/out_videos"
DEFAULT_OUT_DIR = "/home/saswata/web_dev/youtube_song/search_clip_out"
DEFAULT_QUERY = "person singing on stage"
DEFAULT_USE_LLM_REFINEMENT = False
DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"
DEFAULT_CLIP_LEN_SEC = 8.0
DEFAULT_OVERLAP_SEC = 2.0
DEFAULT_SCORE_THRESHOLD = 0.35
DEFAULT_TOP_K = 5
DEFAULT_EXTRACT_CLIPS = True

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
FRAME_SAMPLE_COUNT = 4
MOCK_SCORER_SEED = 1337
JSON_INDENT = 2

THIS_DIR = Path(__file__).resolve().parent
# ---------------------------------------------
