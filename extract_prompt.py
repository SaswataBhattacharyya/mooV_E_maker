#!/usr/bin/env python3
"""Extract all STRING widget values and node types from a ComfyUI workflow."""
import json, sys

with open(sys.argv[1]) as f:
    wf = json.load(f)

for node in wf.get('nodes', []):
    nid = node.get('id', '?')
    ntype = node.get('type', '?')
    widgets = node.get('widgets_values', [])
    
    srt_input = None
    for inp in node.get('inputs', []):
        if inp.get('name') in ('srt_content', 'text', 'prompt', 'positive_prompt',
                               'negative_prompt', 'caption', 'input_text', 'string',
                               'input_string'):
            link_id = inp.get('link')
            srt_input = link_id
            break
    
    if widgets:
        for i, w in enumerate(widgets):
            if isinstance(w, str) and len(w) > 2:
                print("NODE %d (%s) widget[%d]: '%s'" % (nid, ntype, i, w[:200]))
    
    if srt_input is not None:
        # Find this link from another node's output
        for other in wf.get('nodes', []):
            for out in other.get('outputs', []):
                if srt_input in out.get('links', []):
                    print("NODE %d (%s) outputs[%d] links to input '%s'" % (other['id'], other['type'], out['link_index'], inp['name']))

