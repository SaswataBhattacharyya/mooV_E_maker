"""ComfyUI Engine - Submit workflows, poll status, retrieve images."""
import json
import urllib.request
import time
from pathlib import Path


class ComfyUIEngine:
    """Handles all ComfyUI API interactions for story generation."""

    def __init__(self, comfy_url="http://127.0.0.1:3008"):
        self.comfy_url = comfy_url

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def is_running(self):
        """Return True if ComfyUI responds on /system_stats."""
        try:
            urllib.request.urlopen(f"{self.comfy_url}/system_stats", timeout=5)
            return True
        except Exception:
            return False

    def get_system_info(self):
        """Return GPU name, VRAM totals and ComfyUI version or error dict."""
        try:
            data = json.loads(urllib.request.urlopen(f"{self.comfy_url}/system_stats", timeout=5).read())
            devices = data.get("devices", [])
            vram_total = sum(d.get("vram_total", 0) for d in devices)
            vram_free = sum(d.get("vram_free", 0) for d in devices)
            gpu_name = devices[0].get("name", "Unknown") if devices else "Unknown"
            return {
                "gpu_name": gpu_name,
                "vram_total_gb": round(vram_total / 1e9, 1),
                "vram_free_gb": round(vram_free / 1e9, 1),
                "comfyui_version": data.get("system", {}).get("comfyui_version", ""),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_queue_status(self):
        """Return queue dict from /queue."""
        try:
            return json.loads(urllib.request.urlopen(f"{self.comfy_url}/queue", timeout=5).read())
        except Exception:
            return {"error": "Failed"}

    def get_available_models(self):
        """List checkpoint models in the local ComfyUI diffusion_models directory."""
        model_dir = Path("ComfyUI/models/diffusion_models")
        if not model_dir.exists():
            return []
        return [str(f) for f in model_dir.iterdir()
                if f.is_file() and f.suffix in ('.safetensors', '.pt', '.ckpt')]

    # ------------------------------------------------------------------
    # Submit & Poll
    # ------------------------------------------------------------------
    def submit_workflow(self, workflow: dict):
        """Submit a workflow to ``/prompt``.  Returns *prompt_id* or *None*."""
        try:
            payload = json.dumps({"prompt": workflow}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.comfy_url}/prompt",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp_data = json.loads(urllib.request.urlopen(req, timeout=10).read())
            return resp_data.get("prompt_id")
        except Exception as e:
            print(f"[ComfyUIEngine submit error] {e}")
            return None

    def wait_for_completion(self, prompt_id: str, timeout: int = 120):
        """Poll ``/history/<id>`` until job finishes or timeout."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                history = json.loads(
                    urllib.request.urlopen(f"{self.comfy_url}/history/{prompt_id}", timeout=5).read()
                )
                if prompt_id in history and "outputs" in history[prompt_id]:
                    outputs = history[prompt_id]["outputs"]
                    for nod, val in outputs.items():
                        imgs = val.get("images", [])
                        if imgs:
                            return {"status": "done", "elapsed": round(time.time() - start, 1),
                                    "outputs": imgs}
            except Exception:
                pass
            time.sleep(2)
        return {"status": "timeout", "message": "Timed out waiting for completion"}

    def get_output_images(self, prompt_id: str):
        """Return list of dicts ``{filename, url}`` per generated image."""
        try:
            history = json.loads(
                urllib.request.urlopen(f"{self.comfy_url}/history/{prompt_id}", timeout=5).read()
            )
            images = []
            for node_out in history.get(prompt_id, {}).get("outputs", {}).values():
                for info in node_out.get("images", []):
                    fname = info.get("filename", "")
                    subfolder = info.get("subfolder", "")
                    otype = info.get("type", "output")
                    images.append({
                        "filename": fname,
                        "url": f"{self.comfy_url}/view?filename={fname}&subfolder={subfolder}&type={otype}",
                    })
            return images
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Workflow builders
    # ------------------------------------------------------------------
    @staticmethod
    def build_qwen_image_workflow(prompt, negative_prompt="", width=1024, height=1024,
                                  steps=30, cfg=8.0, seed=-1,
                                  ckpt="qwen_image_2512_bf16.safetensors"):
        """Build a **Qwen Image** (t2i) workflow targeting the standard *CheckpointLoaderSimple / KSampler* chain."""
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": ckpt},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["1", 1]},
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative_prompt or "ugly, deformed, blurry, low quality, bad anatomy",
                           "clip": ["1", 1]},
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed if seed > 0 else int(time.time()),
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "euler_ancestral",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                },
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {"images": ["6", 0], "filename_prefix": "story_builder"},
            },
        }

    @staticmethod
    def build_qwen_edit_workflow(image_path, prompt, negative_prompt="", width=1024, height=1024,
                                 steps=30, cfg=8.0, seed=-1):
        """Build a **Qwen Image Edit** (img2img) workflow for composed keyframes."""
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "qwen_image_edit_2511_bf16.safetensors"},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["1", 1]},
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative_prompt or "blurry, deformed", "clip": ["1", 1]},
            },
            "4": {
                "class_type": "LoadImage",
                "inputs": {"image": image_path, "upload": "image"},
            },
            "5": {
                "class_type": "CLIPVisionEncode",
                "inputs": {"clip": ["1", 3], "images": ["4", 0]},
            },
            "6": {
                "class_type": "ConditioningZeroOut",
                "inputs": {"conditioning": [5, 0]},
            },
            "7": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed if seed > 0 else int(time.time()),
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "euler_ancestral",
                    "scheduler": "normal",
                    "model": ["1", 0],
                    "positive": [6, 0],
                    "negative": [3, 0],
                    "latent_image": [7, 0],
                },
            },
            "9": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["8", 0], "vae": ["1", 2]},
            },
            "10": {
                "class_type": "SaveImage",
                "inputs": {"images": [9, 0], "filename_prefix": "story_builder_edit"},
            },
        }
