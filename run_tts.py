#!/usr/bin/env python3
"""Load, modify, and execute TTS workflow on ComfyUI."""
import json, time, urllib.request, os, sys
from pathlib import Path

COMFY_URL = "http://127.0.0.1:3008"
WF_PATH = "/home/riki/web_dev/story_builder/workflows/ricky/TTS_audio_multichar_timed_wf.json"

# 1) Load workflow
with open(WF_PATH, 'r') as f:
    wf = json.load(f)

print("Workflow nodes:")
for n in wf.get('nodes', []):
    print(f"  ID {n['id']}: {n['type']}")
