#!/usr/bin/env python3
"""Parse TTS workflow to find text input nodes and engine config."""
import json, sys

wf_path = "/home/riki/web_dev/story_builder/workflows/ricky/TTS_audio_multichar_timed_wf.json"

with open(wf_path) as f:
    wf = json.load(f)

for node in wf.get('nodes', []):
    nid = node.get('id')
    ntype = node.get('type', '?')
    widgets = node.get('widgets_values', [])
    
    # Look for text/string related nodes
    if any(kw in ntype.lower() for kw in ['string', 'text', 'srt', 'tts', 'unified']):
        print("NODE %d (%s)" % (nid, ntype))
        if widgets:
            for i, w in enumerate(widgets):
                print("  widget[%d]: %r" % (i, str(w)[:300]))
        
        for inp in node.get('inputs', []):
            link_id = inp.get('link')
            input_name = inp['name']
            print("  INPUT: %s -> link #%s" % (input_name, link_id))
        if not node.get('inputs'):
            print("  (no inputs)")
