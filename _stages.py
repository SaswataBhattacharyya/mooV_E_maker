# Story pipeline stages - pure functions for all 9 agentic art steps
import json, os, sys, time, urllib.request as _urllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def ollama_chat(messages, model=None, temperature=0.3):
    api = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434/api")
    mdl = model or os.environ.get("OLLAMA_MODEL", "qwen3.6:35b")
    body = {"model": mdl, "messages": messages, "stream": False}
    body["options"] = dict(temperature=temperature)
    req = _urllib.Request(str(api + "/chat"),
                        data=json.dumps(body).encode("utf-8"),
                        headers={"Content-Type":"application/json"})
    try:
        with _urllib.urlopen(req, timeout=300) as resp:
            content = json.loads(resp.read()).get("message","")
        return content if isinstance(content, dict) else ""
    except Exception:
        return None


def parse_json(text):
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


def health_ollama():
    api = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434/api")
    try:
        with _urllib.urlopen(str(api + "/tags"), timeout=5) as resp:
            return json.loads(resp.read()).get("models", [])
    except Exception:
        return []


def check_comfy_url(url):
    try:
        with _urllib.urlopen(str(url + "/system_stats"), timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ============================ Stage prompts & executors ====================

def stage_story(story_text):
    # Stage 1 - Story Understanding
    prompt = ("You are a story analysis engine.\n"
              "Analyse the following story and output ONLY valid JSON.\n\n"
              "Story:\n---\n" + story_text + "\n---\n\n"
              "JSON keys: title (string), logline (string), genre (string), tone (string),\n"
              "  themes (array of strings), setting (object with location/time_period/atmosphere),\n"
              "  word_count (int), complexity_score (1-10)")
    t = ollama_chat([dict(role="user", content=prompt)], temperature=0.3)
    p = parse_json(t) if t else None
    return p or {"status": "error"}


def stage_characters(story_text, story_data):
    # Stage 2 - Character Design
    tone = story_data.get("tone", "neutral")
    loc = story_data.get("setting", dict()).get("location", "unknown")
    prompt = ("You are a character designer for a story with tone \"{}\" set in \"{}\".\n"
              "Extract all named characters and give each visual description for consistent image generation.\n"
              "Rules: one reusable identity portrait per character, no pose/emotion/lighting variants,\n"
              "include face/hair/eyes/skin/body/clothing/traits/colors.\n\nStory:\n---\n{}\n---\n\n"
              "JSON: characters array with name(role+physical_description+wardrobe{top+bottom+shoes}+"
              "color_palette{primary+accent}+unique_traits+visual_prompt_for_asset_gen),\n"
              "  character_count (int), design_notes (string)")
    t = ollama_chat([dict(role="user", content=prompt.format(tone, loc, story_text))], temperature=0.2)
    p = parse_json(t) if t else None
    return p or {"status": "error"}


def stage_scenes(story_text, story_data):
    # Stage 3 - Scene Mapping
    ll = story_data.get("logline", "")
    tone = story_data.get("tone", "neutral")
    prompt = ("You are a scene mapping engine. Logline: \"{}\". Tone: \"{}\".\n"
              "Break the story into scenes with reusable locations (no visible people in background plates).\n\nStory:\n---\n{}\n---\n\n"
              "JSON: scenes array with scene_id(int)+location+time_of_day+atmosphere+visual_description+"
              "camera_direction+characters_present(array of strings)+key_actions(object with description+emotional_tone)+"
              "visual_prompt_for_background_gen,\n"
              "  total_scenes (int), location_count (int)")
    t = ollama_chat([dict(role="user", content=prompt.format(ll, tone, story_text))], temperature=0.3)
    p = parse_json(t) if t else None
    return p or {"status": "error"}


def stage_subscenes(scenes_data):
    # Stage 4 - Subscene Breakdown
    sc = scenes_data.get("scenes", [])[:3]
    prompt = ("You are a subscene-breaking engine. Scenes:\n" + json.dumps(sc, indent=2) + "\n\n"
              "Break each into 1-4 subscenes with clear visual moments.\n\n"
              "JSON: subscenes array with parent_scene_id(int)+subscene_id(int)+"
              "location+visual_description+characters_in_shot( array of{name+position})+"
              "camera_direction, total_subscenes (int)")
    t = ollama_chat([dict(role="user", content=prompt)], temperature=0.3)
    p = parse_json(t) if t else None
    return p or {"status": "error"}


def stage_dialogue(subscenes_data):
    # Stage 5 - Dialogue Generation
    sbs = subscenes_data.get("subscenes", [])[:3]
    prompt = ("You are a dialogue writer. Subscenes:\n" + json.dumps(sbs, indent=2) + "\n\n"
              "Write vivid in-character dialogue with inline stage directions.\n\n"
              "JSON: dialogues array with parent_scene_id(int)+subscene_id(int)+"
              "location+dialogue_exchanges(array of speaker+line+action)+narration")
    t = ollama_chat([dict(role="user", content=prompt)], temperature=0.3)
    p = parse_json(t) if t else None
    return p or {"status": "error"}


def stage_continuity(chars_data, scenes_data):
    # Stage 6 - Visual Continuity Plan
    cn = [c.get("name","") for c in chars_data.get("characters", [])]
    lg = [s.get("location","") for s in scenes_data.get("scenes", [])]
    prompt = ("You are a visual continuity planner. Characters: {}\nLocations: {}\n\n"
              "Create consistency rules. JSON: continuity_rules with characters(array of name+"
              "must_consistently_show+should_not_change)+locations(array of location+"
              "consistent_elements+lighting_style), reference_assets(array)")
    t = ollama_chat([dict(role="user", content=prompt.format(json.dumps(cn[:6]), json.dumps(lg[:5])))], temperature=0.2)
    p = parse_json(t) if t else None
    return p or {"status": "error"}


def stage_assets(scenes_data):
    # Stage 7 - Asset Plan
    sc = scenes_data.get("scenes", [])[:3]
    prompt = ("You are an asset planning engine. Scenes:\n" + json.dumps(sc, indent=2) + "\n\n"
              "List reusable character portraits and background plates (no people in backgrounds).\n\n"
              "JSON: character_assets(array of asset_id+type=character_identity+for_character+prompt)+"
              "background_assets(array of asset_id+type=background_plate+for_location+prompt)+"
              "dependency_order(array)+total_characters(int)+total_backgrounds(int)")
    t = ollama_chat([dict(role="user", content=prompt)], temperature=0.2)
    p = parse_json(t) if t else None
    return p or {"status": "error"}


def stage_keyframes(assets_data):
    # Stage 8 - Keyframe Planning
    ca = assets_data.get("character_assets", []) + assets_data.get("background_assets", [])[:5]
    prompt = ("You are a keyframe-planning engine. Assets:\n" + json.dumps(ca) + "\n\n"
              "Plan composed shots combining characters and backgrounds.\n\n"
              "JSON: keyframes(array of keyframe_id+requires_background{asset_id}+"
              "characters_in_frame(array of asset_id+position)+composition_notes)+"
              "  total_keyframes (int)")
    t = ollama_chat([dict(role="user", content=prompt)], temperature=0.3)
    p = parse_json(t) if t else None
    return p or {"status": "error"}


def stage_queue(kf_plan):
    # Stage 9 - Generation Queue
    kfs = kf_plan.get("keyframes", [])[:5]
    prompt = ("You are a generation queue builder. Keyframes:\n" + json.dumps(kfs, indent=2) + "\n\n"
              "Order by dependency: character/background assets FIRST, then keyframes.\n"
              "Use qwen_2512_t2i for standalone assets, qwen_edit for composed frames.\n\n"
              "JSON: queue(array of job_id+type+prompt+width+height+steps+cfg_scale)+"
              "total_jobs(int)+estimated_total_steps(int)")
    t = ollama_chat([dict(role="user", content=prompt)], temperature=0.3)
    p = parse_json(t) if t else None
    return p or {"status": "error"}


# Save all pipeline outputs to disk
def save_results(story_text, results):
    project_name = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(os.environ.get("OUTPUT_DIR", str(Path.home()) + "/web_dev/story_projects/") +
                    "story_" + project_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    files_saved = ["00_story_raw.txt"]
    (out_dir / "00_story_raw.txt").write_text(story_text)

    stage_names = {
        "stage_1": "01_story_structure",
        "stage_2": "02_character_design",
        "stage_3": "03_scene_mapping",
        "stage_4": "04_subscene_breakdown",
        "stage_5": "05_dialogue_generation",
        "stage_6": "06_visual_continuity_plan",
        "stage_7": "07_asset_plan",
        "stage_8": "08_keyframe_plan",
        "stage_9": "09_generation_queue",
    }

    for stage_id, basename in stage_names.items():
        if stage_id in results:
            fp = out_dir / (basename + ".json")
            fp.write_text(json.dumps(results[stage_id], indent=2))
            files_saved.append(basename + ".json")

    return {
        "output_dir": str(out_dir),
        "files_saved": files_saved,
    }
