"""Local-only direct-video caption adapter for the pinned InternVideo3 snapshot.

This module is imported only inside the dedicated caption worker. It does not
download model files and intentionally exposes one video-path operation rather
than a frame-captioning API.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any


MODEL_ID = "yanziang/InternVideo3-8B-Instruct"
MODEL_REVISION = "c4602918b65225650d152db2850fe34e01d21fcd"


class InternVideo3Unavailable(RuntimeError):
    pass


def _clean_generated_text(text: str) -> str:
    # The model can emit internal <think> blocks despite a no-reasoning prompt.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"^\s*(assistant|analysis)\s*[:：]\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


class InternVideo3Captioner:
    def __init__(self, model_dir: str | Path | None = None, *, sample_fps: float = 1.0):
        load_started = time.monotonic()
        self.model_dir = Path(model_dir or os.environ.get(
            "VIDEO_AUDIO_ANALYZER_INTERNVIDEO3_PATH", "/models/internvideo3-8b-instruct"
        )).resolve()
        if not (self.model_dir / "config.json").is_file() or not (self.model_dir / "model.safetensors.index.json").is_file():
            raise InternVideo3Unavailable(f"InternVideo3 snapshot is incomplete: {self.model_dir}")
        shard_names = __import__("json").loads((self.model_dir / "model.safetensors.index.json").read_text(encoding="utf-8")).get("weight_map", {}).values()
        missing = sorted({name for name in shard_names if not (self.model_dir / name).is_file()})
        if missing:
            raise InternVideo3Unavailable(f"InternVideo3 snapshot is missing weight shard(s): {', '.join(missing)}")
        import torch
        if not torch.cuda.is_available():
            raise InternVideo3Unavailable("InternVideo3 8B worker requires CUDA; CPU loading is disabled")
        self.torch = torch
        self.sample_fps = max(0.25, min(float(sample_fps), 2.0))
        try:
            from transformers import AutoModelForCausalLM, AutoProcessor
            self.processor = AutoProcessor.from_pretrained(
                str(self.model_dir), trust_remote_code=True, local_files_only=True,
                fix_mistral_regex=True,
            )
            self.model = AutoModelForCausalLM.from_pretrained(
                str(self.model_dir), dtype=torch.bfloat16, attn_implementation="sdpa",
                device_map="cuda:0", trust_remote_code=True, local_files_only=True,
            ).eval()
            self.model.generation_config.temperature = None
            self.model.generation_config.top_p = None
            self.model.generation_config.top_k = None
        except Exception as exc:
            raise InternVideo3Unavailable(
                f"Failed to load pinned InternVideo3 snapshot in isolated worker: {type(exc).__name__}: {exc}"
            ) from exc
        self.model_load_seconds = round(time.monotonic() - load_started, 3)

    def _generate(self, messages: list[dict[str, Any]], *, max_new_tokens: int, fps: float | None = None) -> tuple[str, float]:
        started = time.monotonic()
        try:
            inputs = self.processor.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True, return_dict=True,
                fps=fps or self.sample_fps, return_tensors="pt",
            )
        except TypeError:
            # This model snapshot's documented video path is present in some
            # Transformers builds without the enable_thinking kwarg.
            inputs = self.processor.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True, return_dict=True,
                fps=fps or self.sample_fps, return_tensors="pt",
            )
        inputs = inputs.to(self.model.device)
        with self.torch.inference_mode():
            generated = self.model.generate(
                **inputs, max_new_tokens=max_new_tokens, use_cache=True,
                do_sample=False,
            )
        suffix = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated)]
        text = self.processor.batch_decode(
            suffix, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        result = _clean_generated_text(text)
        if not result:
            raise RuntimeError("InternVideo3 generated an empty response")
        return result, time.monotonic() - started

    def summarize_video(self, video_path: str | Path, prompt: str, *, max_new_tokens: int = 300) -> dict[str, Any]:
        path = Path(video_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        text, elapsed = self._generate([{"role": "user", "content": [
            {"type": "video", "video": str(path), "fps": self.sample_fps},
            {"type": "text", "text": prompt},
        ]}], max_new_tokens=max_new_tokens, fps=self.sample_fps)
        return {"text": text, "seconds": round(elapsed, 3), "input_mode": "direct_video_path", "sample_fps": self.sample_fps}

    def synthesize_text(self, prompt: str, *, max_new_tokens: int = 400) -> dict[str, Any]:
        text, elapsed = self._generate([{"role": "user", "content": [{"type": "text", "text": prompt}]}], max_new_tokens=max_new_tokens)
        return {"text": text, "seconds": round(elapsed, 3), "input_mode": "text_context"}


def decode_video_preflight(video_path: str | Path, *, model_dir: str | Path | None = None, sample_fps: float = 1.0) -> dict[str, Any]:
    """Exercise the pinned processor's direct path decoder without loading 8B weights."""
    import time
    import torch
    from transformers import AutoProcessor

    model_path = Path(model_dir or os.environ.get(
        "VIDEO_AUDIO_ANALYZER_INTERNVIDEO3_PATH", "/models/internvideo3-8b-instruct"
    )).resolve()
    video = Path(video_path).resolve()
    if not video.is_file():
        raise FileNotFoundError(video)
    start = time.monotonic()
    processor = AutoProcessor.from_pretrained(str(model_path), trust_remote_code=True,
        local_files_only=True, fix_mistral_regex=True)
    messages = [{"role": "user", "content": [
        {"type": "video", "video": str(video), "fps": sample_fps},
        {"type": "text", "text": "Describe the visible action in this clip."},
    ]}]
    try:
        inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
            return_dict=True, fps=sample_fps, return_tensors="pt")
    except Exception as exc:
        raise RuntimeError(f"Transformers failed to decode the direct video path {video}: {type(exc).__name__}: {exc}") from exc
    grid = inputs.get("video_grid_thw")
    shape = list(inputs["pixel_values_videos"].shape) if "pixel_values_videos" in inputs else None
    return {"status": "decoded", "model": MODEL_ID, "input_mode": "direct_video_path",
        "video": str(video), "sample_fps": sample_fps,
        "sampled_temporal_patches": grid.tolist() if grid is not None else None,
        "pixel_values_videos_shape": shape, "tensor_device": "cpu_before_model_transfer",
        "torch": torch.__version__, "seconds": round(time.monotonic() - start, 3),
        "persisted_frames": False}
