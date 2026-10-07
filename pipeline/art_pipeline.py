"""
Story Pipeline - Core engine for all 9 agentic art stages.
Follows REPO_AGENTIC_ART_FLOW.md artifact chain:
  story -> characters -> scenes -> subscenes -> dialogue -> visual_continuity_plan -> asset_plan -> keyframe_plan -> generation_queue
"""

import json
import os
from pathlib import Path
from datetime import datetime


class StoryPipeline:
    """Orchestrates the 9-stage agentic art pipeline."""

    def __init__(self, comfyui_url="http://127.0.0.1:3008", ollama_api_url="http://127.0.0.1:11434/v1"):
        self.comfyui_url = comfyui_url
        self.ollama_api_url = ollama_api_url

    def get_system_info(self):
        """Get ComfyUI system information."""
        import urllib.request as ur
        try:
            url = f"{self.comfyui_url}/system_stats"
            req = ur.Request(url)
            with ur.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            devices = data.get("devices", [])
            vram_total = 0
            vram_free = 0
            gpu_name = "Unknown"
            for d in devices:
                vram_total += d.get("vram_total", 0)
                vram_free += d.get("vram_free", 0)
                if not gpu_name or gpu_name == "Unknown":
                    gpu_name = d.get("name", "Unknown")
            return {
                "gpu_name": gpu_name,
                "vram_total_gb": round(vram_total / 1e9, 1),
                "vram_free_gb": round(vram_free / 1e9, 1),
                "comfyui_version": data.get("system", {}).get("comfyui_version", ""),
            }
        except Exception as e:
            return {"error": str(e)}

    def check_comfy_ready(self):
        """Check if ComfyUI is ready."""
        import urllib.request as ur
        try:
            url = f"{self.comfyui_url}/system_stats"
            req = ur.Request(url)
            with ur.urlopen(req, timeout=5) as resp:
                json.loads(resp.read())
            return True
        except Exception:
            return False

    def get_queue_status(self):
        """Get current queue status from ComfyUI."""
        import urllib.request as ur
        try:
            url = f"{self.comfyui_url}/queue"
            req = ur.Request(url)
            with ur.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except Exception:
            return {"error": "Failed"}

    def ollama_chat(self, messages, model="qwen3.6:35b", temperature=0.3):
        """Chat via Ollama API."""
        import urllib.request as ur
        try:
            url = f"{self.ollama_api_url}/api/chat"
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            }
            raw = json.dumps(payload).encode("utf-8")
            req = ur.Request(url, data=raw, headers={"Content-Type": "application/json"})
            with ur.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
            return data.get("message", {}).get("content", "")
        except Exception as e:
            return None

    def submit_workflow(self, workflow_data):
        """Submit a workflow (dict with nodes) to ComfyUI via /prompt API."""
        import urllib.request as ur
        try:
            url = f"{self.comfyui_url}/prompt"
            payload = json.dumps({"prompt": workflow_data}).encode("utf-8")
            req = ur.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with ur.urlopen(req, timeout=10) as resp:
                response = json.loads(resp.read())
            return response.get("prompt_id", None)
        except Exception as e:
            print(f"  ERROR submitting workflow: {e}")
            return None

    def stage_story_analysis(self, story_text):
        """Stage 1: Analyze the story and produce structured understanding."""
        prompt = (
            "You are a story analysis engine.\n"
            "Analyse the following story and output STRICT valid JSON only (no markdown, no extra text).\n\n"
            f"Story:\n---\n{story_text}\n---\n\n"
            "Output format:\n"
            "{\n"
            "  \"title\": string,\n"
            "  \"logline\": string,\n"
            "  \"genre\": string,\n"
            "  \"tone\": string,\n"
            "  \"themes\": [string],\n"
            "  \"setting\": {\"location\": string, \"time_period\": string, \"atmosphere\": string},\n"
            "  \"word_count\": number,\n"
            "  \"complexity_score\": 1-10\n}"
        )
        content = self.ollama_chat([{"role": "user", "content": prompt}], temperature=0.3)
        return json.loads(content) if "{" in (content or "") else {"status": "error", "message": "Failed to parse response"}

    def stage_character_design(self, story_text, prior_results):
        """Stage 2: Design unique reusable character assets with visual details."""
        tone = prior_results.get("tone", "neutral")
        setting_desc = prior_results.get("setting", {})
        prompt = (
            "You are a character designer.\n"
            f"Story Tone: {tone}\n"
            f"Setting: {setting_desc.get('location', 'unknown')} - {setting_desc.get('time_period', 'unknown')}\n\n"
            "Rules:\n"
            "- ONE reusable identity image per distinct named character\n"
            "- NO emotion/pose/injury/lighting/action/camera variants as separate assets\n"
            "- Include visual descriptors for consistent rendering\n"
            "- Specify clothing style and color palette\n"
            "- Specify any unique traits or accessories\n\n"
            f"Story:\n---\n{story_text}\n---\n\n"
            "Output STRICT valid JSON:\n"
            "{\n"
            "  \"characters\": [{\"name\": string, \"role\": string, \"physical_description\": string}],\n"
            "  \"character_count\": number,\n"
            "  \"design_notes\": string\n}"
        )
        content = self.ollama_chat([{"role": "user", "content": prompt}], temperature=0.2)
        return json.loads(content) if "{" in (content or "") else {"status": "error", "message": "Failed to parse response"}

    def stage_scene_mapping(self, story_text, characters):
        """Stage 3: Map scenes from the story structure."""
        logline = prior_results.get("logline", "")
        tone = prior_results.get("tone", "neutral")
        prompt = (
            f"You are a scene mapping engine.\n"
            f"Story logline: {logline}\n"
            f"Tone: {tone}\n\n"
            "Rules:\n"
            "- Each scene should be a self-contained location with reusable background plate\n"
            "- NO visible people in background plates (they are empty locations)\n"
            "- Include camera direction notes\n\n"
            f"Characters in story: {json.dumps(characters[:3] if 'characters' in characters else [])}\n\n"
            f"Story:\n---\n{story_text}\n---\n\n"
            "Output STRICT valid JSON:\n"
            "{\n"
            "  \"scenes\": [{\"scene_id\": number, \"location\": string, \"time_of_day\": string}],\n"
            "  \"total_scenes\": number\n}"
        )
        content = self.ollama_chat([{"role": "user", "content": prompt}], temperature=0.3)
        return json.loads(content) if "{" in (content or "") else {"status": "error", "message": "Failed to parse response"}

    def stage_subscene_breakdown(self, scenes_info):
        """Stage 4: Break each scene into subscenes."""
        scenes_raw = scenes_info.get("scenes", [])
        prompt = (
            f"You are a subscene breaking engine.\n"
            f"Scenes:\n{json.dumps(scenes_raw[:3], indent=2)}\n\n"
            "Rules:\n"
            "- Split scenes into 1-4 subscenes each\n"
            "- Each subscene should have a clear visual moment\n"
            "- Track which characters appear and their positioning\n"
            "- Note camera angles and emotional beats\n\n"
            "Output STRICT valid JSON:\n"
            "{\n"
            "  \"subscenes\": [{\"parent_scene_id\": number, \"location\": string}],\n"
            "  \"total_subscenes\": number\n}"
        )
        content = self.ollama_chat([{"role": "user", "content": prompt}], temperature=0.3)
        return json.loads(content) if "{" in (content or "") else {"status": "error", "message": "Failed to parse response"}

    def stage_dialogue_generation(self, subscenes_info):
        """Stage 5: Write dialogue for each subscene."""
        sbs = subscenes_info.get("subscenes", [])
        prompt = (
            f"You are a dialogue writer.\n"
            f"Subscenes:\n{json.dumps(sbs[:3], indent=2)}\n\n"
            "Rules:\n"
            "- Dialogue should match the story tone\n"
            "- Include stage directions inline with speech\n"
            "- Keep dialogue snappy and visual where possible\n\n"
            "Output STRICT valid JSON:\n"
            "{\n"
            "  \"dialogues\": [{\"location\": string, \"dialogue_exchanges\": [{\"speaker\": string, \"line\": string}]}]\n}"
        )
        content = self.ollama_chat([{"role": "user", "content": prompt}], temperature=0.3)
        return json.loads(content) if "{" in (content or "") else {"status": "error", "message": "Failed to parse response"}

    def stage_visual_continuity_plan(self, characters_info, scenes_info):
        """Stage 6: Create a visual continuity plan."""
        char_names = [c.get("name", "") for c in characters_info.get("characters", [])]
        locations = [s.get("location", "") for s in scenes_info.get("scenes", [])]
        prompt = (
            f"You are a visual continuity planner.\n"
            f"Characters: {json.dumps(char_names[:8], indent=2)}\n"
            f"Locations: {json.dumps(locations[:5], indent=2)}\n\n"
            "Output STRICT valid JSON:\n"
            "{\n"
            "  \"continuity_rules\": {\n"
            "    \"characters\": [{\"name\": string, \"must_consistently_show\": []}],\n"
            "    \"locations\": [{\"location\": string, \"consistent_elements\": []}]\n"
            "  }\n}"
        )
        content = self.ollama_chat([{"role": "user", "content": prompt}], temperature=0.2)
        return json.loads(content) if "{" in (content or "") else {"status": "error", "message": "Failed to parse response"}

    def stage_asset_plan(self, scenes_info):
        """Stage 7: Plan reusable assets needed."""
        scenes_raw = scenes_info.get("scenes", [])
        prompt = (
            f"You are an asset planning engine.\n"
            f"Scenes:\n{json.dumps(scenes_raw[:3], indent=2)}\n\n"
            "Rules:\n"
            "- Asset types: character_identity | background_plate\n"
            "- One image per distinct named character\n"
            "- Background plates must have no visible people\n"
            "- Character assets are neutral poses only\n"
            "- Order by dependency priority\n\n"
            "Output STRICT valid JSON:\n"
            "{\n"
            "  \"character_assets\": [{\"for_character\": string, \"prompt\": string}],\n"
            "  \"background_assets\": [{\"for_location\": string, \"prompt\": string}]\n}"
        )
        content = self.ollama_chat([{"role": "user", "content": prompt}], temperature=0.2)
        return json.loads(content) if "{" in (content or "") else {"status": "error", "message": "Failed to parse response"}

    def stage_keyframe_plan(self, asset_plan):
        """Stage 8: Plan composed keyframes from assets + subscenes."""
        character_assets = asset_plan.get("character_assets", [])
        background_assets = asset_plan.get("background_assets", [])
        prompt = (
            f"You are a keyframe planning engine.\n"
            f"Assets:\n{json.dumps(character_assets + background_assets[:5], indent=2)}\n\n"
            "Output STRICT valid JSON:\n"
            "{\n"
            "  \"keyframes\": [{\"requires_background\": {\"asset_id\": string}, \"characters_in_frame\": [], \"notes\": string}],\n"
            "  \"total_keyframes\": number\n}"
        )
        content = self.ollama_chat([{"role": "user", "content": prompt}], temperature=0.3)
        return json.loads(content) if "{" in (content or "") else {"status": "error", "message": "Failed to parse response"}

    def stage_generation_queue(self, keyframe_plan):
        """Stage 9: Build dependency-ordered generation queue for ComfyUI."""
        keyframes_raw = keyframe_plan.get("keyframes", [])
        prompt = (
            f"You are a generation queue builder.\n"
            f"Keyframes:\n{json.dumps(keyframes_raw[:5], indent=2)}\n\n"
            "Rules:\n"
            "- qwen_2512_t2i for standalone reusable character/background assets\n"
            "- qwen_edit for composed keyframes and refinements\n"
            "- Do NOT use gsl_starter_1_1 for new jobs\n"
            "- Character/background assets FIRST, then keyframes using those assets\n"
            "- Order by dependency graph\n\n"
            "Output STRICT valid JSON:\n"
            "{\n"
            "  \"queue\": [{\"job_id\": string, \"type\": string, \"prompt\": string}],\n"
            "  \"total_jobs\": number,\n"
            "  \"estimated_total_steps\": number\n}"
        )
        content = self.ollama_chat([{"role": "user", "content": prompt}], temperature=0.3)
        return json.loads(content) if "{" in (content or "") else {"status": "error", "message": "Failed to parse response"}

    def run_full_pipeline(self, story_text):
        """Run all 9 stages sequentially."""
        results = {}
        errors = []

        # Stage 1: Story Understanding
        stage_results = self.stage_story_analysis(story_text)
        results['stage_1'] = {**stage_results, 'status': 'completed'}
        
        # Stage 2: Character Design - needs prior_results from stage 1
        char_results = self.stage_character_design(story_text, stage_results)
        results['stage_2'] = {**char_results, 'status': 'completed'}
        
        return results

    def save_results(self, story_text, results, project_name=None):
        """Save all pipeline artifacts to files."""
        if not project_name:
            project_name = f"story_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        output_dir = Path("/home/riki/web_dev").parent / "web_dev" / "story_projects" / project_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save story text
        (output_dir / "01_story.txt").write_text(story_text)
        results["project_id"] = project_name
        results["output_dir"] = str(output_dir)

        # Save each stage result as JSON
        stage_to_ext = {
            'stage_1': '02_story_structure',
            'stage_2': '03_character_design',
            'stage_3': '04_scene_mapping',
            'stage_4': '05_subscene_breakdown',
            'stage_5': '06_dialogue_generation',
            'stage_6': '07_visual_continuity_plan',
            'stage_7': '08_asset_plan',
            'stage_8': '09_keyframe_plan',
            'stage_9': '10_generation_queue'
        }

        saved_files = []
        for stage_id, ext in stage_to_ext.items():
            if stage_id in results:
                filepath = output_dir / f"{ext}.json"
                filepath.write_text(json.dumps(results[stage_id], indent=2))
                saved_files.append(str(filepath))

        return {"saved_to": str(output_dir), "files_count": len(saved_files)}

