#!/usr/bin/env python3
"""Load workflow, modify SRT intro, send to ComfyUI, download result."""
import json, sys
from pathlib import Path

WF_PATH = "/home/riki/web_dev/story_builder/workflows/ricky/TTS_audio_multichar_timed_wf.json"
with open(WF_PATH) as f:
    wf = json.load(f)

print("=== Workflow Nodes ===")
for n in wf.get('nodes', []):
    print(f"  ID {n['id']}: {n['type']}")

# Find nodes with SRT text (PrimitiveStringMultiline and/or UnifiedTTSSRTNode widgets)
for n in wf.get('nodes', []):
    widgets_vals = n.get('widgets_values', [])
    if widgets_vals:
        for wv in widgets_vals:
            if isinstance(wv, str) and '-->' in wv:
                print(f"\n  Text node {n['id']} ({n['type']}):")
                first_line = wv.strip().split('\n')[0][:80]
                print(f"    Starts: {first_line}...")
