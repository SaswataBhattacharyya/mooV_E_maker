#!/usr/bin/env python3
"""Streamlit frontend for Story Builder - Agentic Art Pipeline."""

import json, os, sys, time, urllib.request as _urllib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

# Allow imports from sibling modules within the project root
sys.path.insert(0, str(Path(__file__).resolve().parent))


# ======================================================================[ Config ]======
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:3008")
OLLAMA_API  = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434/api")
OUT_DIR     = Path(os.environ.get("OUTPUT_DIR", str(Path.home()) + "/web_dev/story_projects/"))

STAGE_NAMES = [
    "Story Understanding",
    "Character Design",
    "Scene Mapping",
    "Subscene Breakdown",
    "Dialogue Generation",
    "Visual Continuity Plan",
    "Asset Plan",
    "Keyframe Planning",
    "Generation Queue",
]

# ======================================================================[ Session State ]=======
BS = dict(
    pipeline_results=dict(),
    images_generated=[],
    stages_completed=0,
    current_stage=None,
    is_running=False,
    comfyui_url=COMFYUI_URL,
    ollama_api=OLLAMA_API,
    seed=-1,
    steps=30,
    cfg=8.0,
    img_width=1024,
    img_height=1024,
)
for _k, _v in BS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ======================================================================[ Helpers ]======

def health_comfy(url):
    """Return (ok, info_or_error_string)."""
    try:
        raw = _urllib.urlopen(str(url + "/system_stats"), timeout=5).read()
        data = json.loads(raw)
        devs = data.get("devices", [])
        vf = sum(d.get("vram_free", 0) for d in devs)
        name = devs[0].get("name", "?") if devs else "?"
        ver  = data.get("system", dict()).get("comfyui_version", "")
        info = "GPU: " + name + "\nVRAM free: " + str(round(vf / 1e9, 1)) + " GB\nVersion: " + ver
        return True, info
    except Exception as e:
        return False, str(e)


def health_ollama():
    """Return list of model names or empty list on failure."""
    api = st.session_state.get("ollama_api", OLLAMA_API)
    try:
        raw = _urllib.urlopen(str(api + "/tags"), timeout=5).read()
        models = json.loads(raw).get("models", [])
        return [m.get("name", "?") for m in models]
    except Exception:
        return []


def health_ollama_api():
    """Return list of model names or empty list."""
    api = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434/api")
    try:
        raw = _urllib.urlopen(str(api + "/tags"), timeout=5).read()
        models = json.loads(raw).get("models", [])
        return [m.get("name", "?") for m in models]
    except Exception:
        return []


def parse_json(text):
    """Extract first JSON object from *text*, ignoring surrounding Markdown/code fences."""
    if not text:
        return None
    s = text.strip()
    oi = s.find("{")
    if oi < 0:
        return None
    depth, end = 0, -1
    for ci in range(oi, len(s)):
        ch = s[ci]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = ci + 1
                break
    if end < 0:
        return None
    try:
        return json.loads(s[oi:end])
    except json.JSONDecodeError:
        return None


def get_json_from_llm(messages, model=None, temperature=0.3):
    """Send to Ollama and return parsed JSON (or dict-error on failure)."""
    api = st.session_state.get("ollama_api", os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434/api"))
    mdl = model or os.environ.get("OLLAMA_MODEL", "qwen3.6:35b")
    body = dict(model=mdl, messages=messages, stream=False)
    body["options"] = dict(temperature=float(temperature))
    payload = json.dumps(body).encode("utf-8")
    req = _urllib.Request(api + "/chat", data=payload, headers={"Content-Type":"application/json"})
    try:
        with _urllib.urlopen(req, timeout=300) as resp:
            msg_content = json.loads(resp.read()).get("message", "")
        if isinstance(msg_content, dict):
            msg_content = ""
        p = parse_json(msg_content) if msg_content else None
        return p or {"status": "error"}, str(msg_content[:200])
    except Exception as e:
        return {"status": "error"}, str(e)


def run_single_stage(stage_idx, data):
    """Run one pipeline stage. Returns (result_dict, raw_text_or_error)."""
    story = data.get("raw_story", "")
    s1 = data.get("s1_data")      # stage 1 output
    s2 = data.get("s2_data")      # stage 2 output
    s3 = data.get("s3_data")      # stage 3 output
    s4 = data.get("s4_data")      # stage 4 output
    s5 = data.get("s5_data")      # stage 5 output
    s6 = data.get("s6_data")      # stage 6 output
    s7 = data.get("s7_data")      # stage 7 output
    s8 = data.get("s8_data")      # stage 8 output

    if stage_idx == 1:
        prompt = ("You are a story analysis engine.\n"
                  "Analyse the following story and output ONLY valid JSON (no markdown, no extra text).\n\n"
                  "Story:\n---\n" + story + "\n---\n\n"
                  "JSON keys: title (string), logline (string), genre (string), tone (string),\n"
                  "  themes (array of strings), setting (object with location, time_period, atmosphere),\n"
                  "  word_count (int), complexity_score (1-10)")

    elif stage_idx == 2:
        tone = s1.get("tone", "neutral") if s1 else "neutral"
        loc = ""
        if s1 and s1.get("setting"):
            setting_obj = s1["setting"]
            if isinstance(setting_obj, dict):
                loc = str(setting_obj.get("location", "unknown"))
            else:
                loc = "unknown"
        prompt = ("You are a character designer for a story with tone '" + str(tone)
                  + "' set in '" + str(loc) + "'.\n"
                  "Extract all named characters and give each visual description for consistent image generation.\n"
                  "Rules: one reusable identity portrait per character, no pose/emotion/lighting variants,\n"
                  "include face/hair/eyes/skin/body/clothing/traits/colors.\n\nStory:\n---\n" + story
                  + "\n---\n\nJSON: characters array with name(role+physical_description+"
                  "wardrobe{top+bottom}+color_palette{primary+accent}"
                  "+unique_traits(array)+visual_prompt_for_asset_gen), character_count (int), design_notes (string)")

    elif stage_idx == 3:
        ll = s1.get("logline", "") if s1 else ""
        tone = s1.get("tone", "neutral") if s1 else "neutral"
        prompt = ("You are a scene mapping engine. Logline: '" + str(ll)
                  + "'. Tone: '" + str(tone) + "'.\n"
                  "Break the story into scenes with reusable locations (no visible people in background plates).\n\nStory:\n---\n"
                  + story + "\n---\n\nJSON: scenes array with scene_id(int)+location+time_of_day+"
                  "atmosphere+visual_description+camera_direction+characters_present(array of strings)+"
                  "key_actions(object with description+emotional_tone)+visual_prompt_for_background_gen,"
                  "total_scenes (int), location_count (int)")

    elif stage_idx == 4:
        s3 = data.get("s3_data") or dict()
        sc_list = s3.get("scenes", [])[:3] if isinstance(s3, dict) else []
        prompt = ("You are a subscene-breaking engine. Scenes:\n" + json.dumps(sc_list, indent=2) + "\n\n"
                  "Break each into 1-4 subscenes with clear visual moments.\n\nJSON: subscenes array with "
                  "parent_scene_id(int)+subscene_id(int)+location+visual_description+"
                  "characters_in_shot(array of name+position)+camera_direction, total_subscenes (int)")

    elif stage_idx == 5:
        s4 = data.get("s4_data") or dict()
        sbs = s4.get("subscenes", [])[:3] if isinstance(s4, dict) else []
        prompt = ("You are a dialogue writer. Subscenes:\n" + json.dumps(sbs, indent=2) + "\n\n"
                  "Write vivid in-character dialogue with inline stage directions.\n\nJSON: dialogues array "
                  "with parent_scene_id(int)+subscene_id(int)+location+dialogue_exchanges(array of speaker+line+"
                  "action)+narration")

    elif stage_idx == 6:
        s2 = data.get("s2_data") or dict()
        s3 = data.get("s3_data") or dict()
        cn = [c.get("name", "") for c in (s2.get("characters", []) if isinstance(s2, dict) else [])]
        lg = [s.get("location", "") for s in (s3.get("scenes", []) if isinstance(s3, dict) else [])]
        prompt = ("You are a visual continuity planner. Characters: " + str(cn[:6]) + "\nLocations: " + str(lg[:5])
                  + "\n\nCreate consistency rules. JSON: continuity_rules with characters(array of name+"
                  "must_consistently_show+should_not_change)+locations(array of location+"
                  "consistent_elements+lighting_style), reference_assets(array)")

    elif stage_idx == 7:
        s3 = data.get("s3_data") or dict()
        sc_list2 = s3.get("scenes", [])[:3] if isinstance(s3, dict) else []
        prompt = ("You are an asset planning engine. Scenes:\n" + str(sc_list2) + "\n\n"
                  "List reusable character portraits and background plates (no people in backgrounds).\n\nJSON: "
                  "character_assets(array of asset_id+type+for_character+prompt)+background_assets(array of "
                  "asset_id+type=background_plate+for_location+prompt)+"
                  "dependency_order(array)+total_characters(int)+total_backgrounds(int)")

    elif stage_idx == 8:
        s7 = data.get("s7_data") or dict()
        ca_arr = s7.get("character_assets", []) if isinstance(s7, dict) else []
        ba_arr = s7.get("background_assets", [])[:5] if isinstance(s7, dict) else []
        all_assets = str(ca_arr)[:1000] + "..." + str(ba_arr)[:500] if ca_arr else str(ba_arr)
        prompt = ("You are a keyframe-planning engine. Assets:\n" + str(all_assets) + "\n\n"
                  "Plan composed shots combining characters and backgrounds.\n\nJSON: keyframes(array of "
                  "keyframe_id+requires_background{asset_id}+"
                  "characters_in_frame(array of asset_id+position)+composition_notes)+total_keyframes (int)")

    elif stage_idx == 9:
        s8 = data.get("s8_data") or dict()
        kf_list = s8.get("keyframes", [])[:5] if isinstance(s8, dict) else []
        prompt = ("You are a generation queue builder. Keyframes:\n" + str(kf_list)[:1000]
                  + "\n\nOrder by dependency: character/background assets FIRST, then keyframes.\n"
                  "Use qwen_2512_t2i for standalone assets, qwen_edit for composed frames.\n\nJSON: queue(array of "
                  "job_id+type+prompt+width+height+steps+cfg_scale)+total_jobs(int)+"
                  "estimated_total_steps(int)")

    else:
        return {"status": "error", "message": "UNKNOWN_STAGE"}, "n/a"

    result, raw = get_json_from_llm([dict(role="user", content=prompt)],
                                     temperature=0.3 if stage_idx <= 5 else 0.2)
    result["stage"] = stage_idx
    return result, raw


# ======================================================================[ ComfyUI Generation ]======

def comfyui_submit_workflow(callback):
    """Submit a workflow to ComfyUI and wait for completion."""
    url = st.session_state.get("comfyui_url", COMFYUI_URL)
    try:
        seed_val = int(st.session_state.seed) if isinstance(st.session_state.seed, (int, float)) else -1
        steps_val = int(st.session_state.steps)
        cfg_val = float(st.session_state.cfg)
        w = int(st.session_state.img_width)
        h = int(st.session_state.img_height)

        prompt_text = callback()
        wf = build_qwen_workflow(prompt_text, seed=seed_val, steps=steps_val, cfg=cfg_val, width=w, height=h)

        payload = json.dumps({"prompt": wf}).encode("utf-8")
        req = _urllib.Request(str(url + "/prompt"), data=payload, headers={"Content-Type":"application/json"})
        raw_resp = _urllib.urlopen(req, timeout=10).read()
        resp_data = json.loads(raw_resp)
        prompt_id = resp_data.get("prompt_id", "")
    except Exception as e:
        return dict(status="error", message=str(e))

    # Poll for completion
    start_time = time.time()
    timeout_secs = 180
    while (time.time() - start_time) < timeout_secs:
        try:
            hist_resp = _urllib.urlopen(str(url + "/history/" + str(prompt_id)), timeout=5).read()
            history = json.loads(hist_resp)
            if prompt_id in history and "outputs" in history[prompt_id]:
                imgs = []
                for node_out in history[prompt_id]["outputs"].values():
                    for img_info in node_out.get("images", []):
                        fname = str(img_info.get("filename", ""))
                        sf    = str(img_info.get("subfolder", ""))
                        url   = str(url + "/view?filename=" + fname + "&type=output")
                        imgs.append(dict(filename=fname, url=url))
                if imgs:
                    return dict(status="done", elapsed=round(time.time() - start_time), images=imgs)
        except Exception:
            pass
        time.sleep(2)

    return dict(status="timeout", message="Timed out after " + str(timeout_secs) + "s")


def build_qwen_workflow(prompt_text, seed=-1, steps=30, cfg=8.0, width=1024, height=1024):
    """Build a QwenImage workflow dict compatible with our ComfyUI setup."""
    # Load checkpoint
    nodeloader = dict(class_type="CheckpointLoaderSimple", inputs=dict(ckpt_name="qwen_image_2512_bf16.safetensors"))

    encode_pos = dict(class_type="CLIPTextEncode",
                     inputs=dict(text=prompt_text, clip=["nodeloader", 1]))

    neg_text = "ugly, deformed, blurry, low quality, bad anatomy"
    encode_neg = dict(class_type="CLIPTextEncode",
                     inputs=dict(text=neg_text, clip=["nodeloader", 1]))

    empty_latent = dict(class_type="EmptyLatentImage",
                       inputs=dict(width=width, height=height, batch_size=1))

    sampler = dict(class_type="KSampler",
                  inputs=dict(seed=seed if seed > 0 else int(time.time()),
                              steps=steps, cfg=cfg,
                              sampler_name="euler_ancestral",
                              scheduler="normal", denoise=1.0,
                              model=["nodeloader", 0],
                              positive=["encode_pos", 0],
                              negative=["encode_neg", 0],
                              latent_image=["empty_latent", 0]))

    vae_dec = dict(class_type="VAEDecode", inputs=dict(samples=["sampler", 0], vae=["nodeloader", 2]))

    save_img = dict(class_type="SaveImage", inputs=dict(images=["vae_dec", 0],
             filename_prefix="story_builder_" + time.strftime("%Y%m%d_%H%M%S")))

    return dict(
        nodeloader=nodeloader,
        encode_pos=encode_pos,
        encode_neg=encode_neg,
        empty_latent=empty_latent,
        sampler=sampler,
        vae_dec=vae_dec,
        save_img=save_img,
    )


# ======================================================================[ Save pipeline outputs ]======

def save_all_results(story_text, results):
    """Persist everything to the configured output directory."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(str(OUT_DIR) + "story_" + str(ts))
    out_dir.mkdir(parents=True, exist_ok=True)

    files_saved = []
    fp1 = str(out_dir / "00_story_raw.txt")
    open(fp1, "w").write(story_text)
    files_saved.append("00_story_raw.txt")

    stage_names = dict(
        stage_1="01_story_structure",
        stage_2="02_character_design",
        stage_3="03_scene_mapping",
        stage_4="04_subscene_breakdown",
        stage_5="05_dialogue_generation",
        stage_6="06_visual_continuity_plan",
        stage_7="07_asset_plan",
        stage_8="08_keyframe_plan",
        stage_9="09_generation_queue",
    )

    for sid, bname in stage_names.items():
        if sid in results:
            fp2 = str(out_dir / (str(bname) + ".json"))
            open(fp2, "w").write(json.dumps(results[sid], indent=2))
            files_saved.append(bname + ".json")

    return dict(output_dir=str(out_dir), file_paths=files_saved, count=len(files_saved))


# ======================================================================[ Streamlit UI ]======

def sidebar():
    with st.sidebar:
        st.header("Settings")

        # ComfyUI config
        url_in = st.text_input("ComfyUI URL", value=st.session_state.get("comfyui_url", COMFYUI_URL))
        if st.button("Test ComfyUI"):
            ok, msg = health_comfy(url_in)
            if ok:
                st.success("Connected!")
                st.info(msg)
            else:
                st.error(msg)

        # Ollama config
        api_in = st.text_area("Ollama API URL", value=st.session_state.get("ollama_api", OLLAMA_API), height=60)
        if st.button("Test Ollama"):
            models = health_ollama_api()
            if models:
                st.success("Connected! Models: " + str(models))
            else:
                st.warning("No models found.")

        # Image settings
        st.header("Image Gen")
        st.slider("Width", 256, 2048, int(st.session_state.img_width), 64)
        st.slider("Height", 256, 2048, int(st.session_state.img_height), 64)
        st.number_input("Seed", value=int(st.session_state.seed), step=1)
        st.slider("Steps", 5, 100, 30, 1)
        st.number_input("CFG", value=float(st.session_state.cfg), step=0.5)

        # Output dir
        out_dir_in = st.text_area("Output Dir", str(OUT_DIR), height=80)
        if os.path.exists(out_dir_in):
            dirs_found = [d for d in os.listdir(str(out_dir_in)) if os.path.isdir(os.path.join(out_dir_in, d))]
            if dirs_found:
                st.info(dirs_found[-1])  # show latest


def progress_bar():
    """Show the artifact chain progress."""
    stages_completed = (int)(st.session_state.stages_completed) if isinstance(st.session_state.stages_completed, int) else 0

    for i in range(9):
        done = "<" + str(i + 1) + ">" < str(stages_completed)
        icon = "<done>" if done else "<pending>"
        name = STAGE_NAMES[i]
        st.markdown((str(icon) + " **Step " + str(i+1) + ":** ") + str(name))


def render_progress_table():
    """Table showing each stage result (preview)."""
    results = st.session_state.pipeline_results if isinstance(st.session_state.pipeline_results, dict) else dict()

    col_names = ["Stage", "Status", "Preview"]
    table_data = []

    stage_labels = dict(
        stage_1=("Story Understanding", "analysis"),
        stage_2=("Character Design", "characters"),
        stage_3=("Scene Mapping", "scenes"),
        stage_4=("Subscene Breakdown", "subscenes"),
        stage_5=("Dialogue Generation", "dialogues"),
        stage_6=("Visual Continuity Plan", "rules"),
        stage_7=("Asset Plan", "assets"),
        stage_8=("Keyframe Planning", "keyframes"),
        stage_9=("Generation Queue", "queue")
    )

    for sid, (label, key) in sorted(stage_labels.items()):
        res = results.get(sid, None) or dict(status="pending")
        status = str(res.get("status", "error"))
        preview = ""
        if isinstance(res, dict):
            for k2, v2 in res.items():
                preview = str(v2)[:100]
                break
        table_data.append((label, status, preview))

    col_stages = st.columns(3)
    col_stages[0].header("Stage")
    col_stages[1].header("Status")
    col_stages[2].header("Preview")
    
    for label, status, preview in table_data:
        badge = "OK" if status == "ok" else "FAIL" if "error" in str(status).lower() else "PENDING"
        col_names2 = st.columns([4, 1, 5])
        col_names2[0].write(label)
        col_names2[1].badge(badge, color="success" if status == "ok" else "warning" if "pending" in str(status).lower() else "error")
        col_names2[2].text(preview[:80])


def render_images_panel():
    """Display generated images from all stages."""
    imgs = st.session_state.images_generated if "images_generated" in st.session_state else []
    if not imgs:
        st.info("No images generated yet. Start a pipeline to generate your story assets.")

    rows = [(idx, img_data) for idx, img_data in enumerate(imgs)]

    cols_layout = st.columns(min(3, len(rows))) if rows else st.columns(1)
    for col2, (idx2, imgd) in zip(cols_layout, rows):
        url_img = str(imgd.get("url", ""))
        fname   = str(imgd.get("filename", "unknown"))
        col2.image(url_img, caption="Generated: " + fname, use_column_width=True)


# ======================================================================[ Pipeline execution ]======

@st.dialog("Generating your story assets...")
def execute_pipeline(story_text):
    """Execute all 9 stages sequentially with progress reporting."""
    results = dict(raw_story=story_text)

    for sidx in range(1, 10):
        stage_name = STAGE_NAMES[sidx-1]
        st.write("### Stage " + str(sidx) + ": " + str(stage_name))
        
        result_dict2, raw_or_err = run_single_stage(sidx, results)

        if "error" in str(result_dict2.get("status", "")).lower():
            st.error(str(raw_or_err)[:300])
            st.stop()
        
        key_out = ("stage_" + str(sidx))
        results[key_out] = result_dict2
        
        # Update session state so UI reflects progress
        updated_key = "stage_" + str(sidx)
        
        status_str = "completed" if result_dict2.get("status") != "error" else "failed"
        st.session_state.stages_completed = sidx

        # Preview the stage output
        preview_data = dict(stages=results.get(str(key_out), {}))


# ======================================================================[ Image generation for current stage ]======

def generate_current_image(stage_num=1):
    """Generate an image for the current pipeline step using ComfyUI."""
    results_dict = st.session_state.pipeline_results if "pipeline_results" in st.session_state else dict()
