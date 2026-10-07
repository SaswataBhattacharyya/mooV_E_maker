#!/usr/bin/env python3
import json, time, urllib.request, os
from pathlib import Path

COMFY_URL = "http://127.0.0.1:3008"
WF_PATH = "/home/riki/web_dev/story_builder/workflows/ricky/TTS_audio_multichar_timed_wf.json"

# Step 1: Load + modify workflow
with open(WF_PATH) as f:
    wf = json.load(f)

intro_srt = r"""1
00:00:02,500 --> 00:00:07,000
[Qwen3:Alice] Hello! I'm Hermes — your AI voice assistant running inside ComfyUI.

2
00:00:08,500 --> 00:00:14,500
[F5TTS:Bob] I use powerful TTS engines like Qwen3-TTS and CosyVoice to generate natural-sounding speech for stories.

3
00:00:16,000 --> 00:00:22,000
[Qwen3:Alice] With your TTS-Audio-Suite workflow skills, I can produce multilingual dialogue with precise timing and character voices.

4
00:00:24,000 --> 00:00:31,500
[F5TTS:Bob] These skills let me build rich audio narratives — chapter narration, character switching, emotion control, and sound effects.

5
00:00:33,500 --> 00:00:40,000
[Qwen3:Alice] Ready when you are! Just say the word and I'll generate your next audio scene.
"""

replaced = False
for node in wf["nodes"]:
    if "Primitive" in str(node.get("type", "")):
        widgets = node.get("widgets_values", [])
        if widgets and isinstance(widgets[0], str) and "-->" in str(widgets[0]):
            node["widgets_values"][0] = intro_srt
            print(f"Replaced SRT content from {node['type']} widget[0]")
            replaced = True
            break

if not replaced:
    for idx, node in enumerate(wf["nodes"]):
        widgets = node.get("widgets_values", [])
        if widgets and isinstance(widgets[0], str) and "-->" in str(widgets[0]):
            wf["nodes"][idx]["widgets_values"][0] = intro_srt
            replaced = True
            break

if not replaced:
    print("ERROR: No SRT content found!")
    sys.exit(1)

# Also update the UnifiedTTSSRTNode to use the same engine
for node in wf["nodes"]:
    if "UnifiedTTS" in str(node.get("type", "")):
        # Find which linked node provides the TTS engine via link
        for inp in node.get("inputs", []):
            if inp.get("name") == "TTS_engine" and inp.get("link"):
                print(f"\nUnifiedTTSSRTNode found at node {node['id']}")
                # Look up what provides the TTS engine (the linked node)
                for other in wf["nodes"]:
                    if other["type"] not in ("Reroute","PrimitiveFloat",):
                        has_srt_widget = any(w == intro_srt[:20] for w in (other.get("widgets_values") or []))

# Step 2: Queue to ComfyUI via prompt endpoint
payload = json.dumps({"prompt": wf}).encode()
req = urllib.request.Request(
    f"{COMFY_URL}/queue",
    data=payload,
    headers={"Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req, timeout=30)
result_data = json.loads(resp.read())
prompt_id = result_data.get("prompt_id") or list(result_data.keys())[0]
print(f"Queued workflow (prompt_id={prompt_id})")

# Step 3: Poll for completion
status_url = f"{COMFY_URL}/history/{prompt_id}"
max_wait = 600
start = time.time()
while True:
    if time.time() - start > max_wait:
        print("TIMEOUT waiting for TTS to complete")
        sys.exit(1)
    
    treq = urllib.request.Request(status_url)
    resp2 = urllib.request.urlopen(treq, timeout=30)
    hist = json.loads(resp2.read())
    
    # If our prompt_id is a key in history with completed status
    if prompt_id in hist and hist[prompt_id].get("status", {}).get("status_str") == "completed":
        print("Workflow COMPLETED!")
        break
    if prompt_id in hist and any(node.get("outputs") for node_id, output_dict in hist.items() for nodename in ["outputs"]) if isinstance(hist.get(prompt_id), dict) else None:
        outputs = hist[prompt_id].get("outputs", {})
        print(f"Progress check - outputs found at {list(outputs.keys())}")
    
    time.sleep(2)

# Step 4: Get the result files
hist = json.loads(urllib.request.urlopen(status_url).read())[prompt_id]
print(f"\nNode outputs in history for prompt {prompt_id}:")
for node_id_str, node_data in hist.get("outputs", {}).items():
    print(f"  Node {node_id_str}: {list(node_data.keys())[:5]}")

# Look at PreviewAudio node (should be node 9 based on the workflow)
preview_outputs = hist["outputs"].get(9, {})
print(f"\nPreviewAudio output keys: {list(preview_outputs.keys())}")
if "images" in preview_outputs:
    for img in preview_outputs["images"]:
        print(f"  Image: {img}")

# Step 5: Check temp/comfyui output directory
comfy_input_dir = Path("/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/input")
comfy_temp_dir = Path("/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/temp")

print(f"\nChecking ComfyUI temp dir: {comfy_temp_dir}")
if comfy_temp_dir.exists():
    for f in sorted(comfy_temp_dir.iterdir()):
        print(f"  {f.name} ({f.stat().st_size} bytes, modified {time.ctime(f.stat().st_mtime)})")

# Check recent files (last 30 seconds)
import glob
recent_audio_files = []
for fpath in glob.glob(str(comfy_temp_dir / "*.wav")) + glob.glob(str(comfy_temp_dir / ".mp3")):
    if time.time() - os.path.getmtime(fpath) < 180:
        recent_audio_files.append(Path(fpath))

if recent_audio_files:
    print(f"\nFound {len(recent_audio_files)} recent audio files in temp!")
else:
    print(f"\nNo new audio files in temp yet. Checking workflow outputs directory...")
    
    # Check the actual ComfyUI output/queue directories 
    import os
    for d in [Path("/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/output"),
              Path("/home/riki/web_dev/setup_comfy_and-stuff/comfyui-output"),
              Path("/tmp"):
        if d.exists():
            audio_files = list(d.glob("*.{wav,mp3,wma,ogg}"))
            recent_audio = [f for f in audio_files 
                           if time.time() - os.path.getmtime(f) < 180 and f.stat().st_size > 100]
            if recent_audio:
                print(f"\nFound {len(recent_audio)} recent audio files in {d}")

# Save modified workflow for reference
output_dir = Path("/home/riki/web_dev/story_builder/output")
output_dir.mkdir(parents=True, exist_ok=True)

with open(output_dir / "TTS_workflow_with_self_intro.json", "w") as f:
    json.dump(wf, f, indent=2)
print(f"\nModified workflow saved to {output_dir}/TTS_workflow_with_self_intro.json")

