"""Small, lazy PE-AV adapter for the isolated analyzer worker.

The dependency is intentionally imported only when a checkpoint is configured;
the normal scene/frame pipeline remains usable without the several-GB model.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class PEAVUnavailable(RuntimeError):
    pass


class PEAVAdapter:
    def __init__(self, checkpoint_dir: str | Path, device: str | None = None):
        self.checkpoint_dir = Path(checkpoint_dir)
        if not (self.checkpoint_dir / "config.json").exists() or not (self.checkpoint_dir / "model.safetensors").exists():
            raise PEAVUnavailable(f"PE-AV checkpoint is incomplete: {self.checkpoint_dir}")
        try:
            import torch
        except Exception as exc:  # pragma: no cover - depends on isolated image
            raise PEAVUnavailable(f"PE-AV runtime import failed: {exc}") from exc
        self.torch = torch
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        # `facebook/pe-av-base` is published in the Transformers checkpoint
        # format (architecture PeAudioVideoModel).  The upstream repository
        # also ships an older custom-loader format for some checkpoints; keep
        # that path as a compatibility fallback, but prefer the canonical HF
        # model format used by the selected Base checkpoint.
        import json
        architecture = json.loads((self.checkpoint_dir / "config.json").read_text(encoding="utf-8")).get("architectures", [])
        if "PeAudioVideoModel" in architecture:
            from transformers import PeAudioVideoModel, PeAudioVideoProcessor
            self.model = PeAudioVideoModel.from_pretrained(str(self.checkpoint_dir), local_files_only=True).to(self.device).eval()
            self.transform = PeAudioVideoProcessor.from_pretrained(str(self.checkpoint_dir), local_files_only=True)
            self._hf_format = True
        else:
            from core.audio_visual_encoder import PEAudioVisual, PEAudioVisualTransform
            self.model = PEAudioVisual.from_config(str(self.checkpoint_dir), pretrained=True).to(self.device).eval()
            self.transform = PEAudioVisualTransform.from_config(str(self.checkpoint_dir))
            self._hf_format = False

    @property
    def dimension(self) -> int:
        value = getattr(self.model.config, "output_dim", None)
        if value is None:
            value = getattr(getattr(self.model.config, "audio_video_config", None), "output_dim", 1024)
        return int(value)

    def embed(self, *, video: str | None = None, audio: str | None = None, text: str | None = None) -> dict[str, list[list[float]] | None]:
        if not any((video, audio, text)):
            raise ValueError("at least one of video, audio or text is required")
        inputs = self.transform(videos=video, audio=audio, text=text, return_tensors="pt", padding=True) if self._hf_format else self.transform(videos=video, audio=audio, text=text)
        inputs = inputs.to(self.device)
        autocast_device = "cuda" if self.device.type == "cuda" else "cpu"
        with self.torch.inference_mode(), self.torch.autocast(autocast_device, dtype=self.torch.bfloat16, enabled=self.device.type == "cuda"):
            if self._hf_format and text is not None and video is None and audio is None:
                # Transformers exposes text-only projections through the
                # modality-specific helpers; forward() intentionally requires
                # at least two modalities.
                value = self.model.get_text_audio_video_embeds(inputs["input_ids"], inputs.get("attention_mask"))
                return {"audio_embeds": None, "video_embeds": None, "visual_embeds": None, "audio_visual_embeds": None, "audio_video_embeds": None, "audio_text_embeds": None, "text_audio_embeds": None, "visual_text_embeds": value.detach().float().cpu().tolist(), "text_video_embeds": value.detach().float().cpu().tolist(), "audio_visual_text_embeds": None, "text_audio_video_embeds": value.detach().float().cpu().tolist()}
            if self._hf_format and audio is not None and video is None and text is None:
                # The HF PE-AV forward pass is cross-modal and deliberately
                # rejects a single modality. Audio-only indexing must use the
                # modality projection helper, just like text-only queries.
                value = self.model.get_audio_embeds(inputs["input_values"], inputs.get("padding_mask"))
                return {"audio_embeds": value.detach().float().cpu().tolist(), "video_embeds": None,
                    "visual_embeds": None, "audio_video_embeds": None, "audio_visual_embeds": None,
                    "audio_text_embeds": None, "text_audio_embeds": None, "visual_text_embeds": None,
                    "text_video_embeds": None, "audio_visual_text_embeds": None, "text_audio_video_embeds": None}
            if self._hf_format and video is not None and audio is None and text is None:
                value = self.model.get_video_embeds(inputs["pixel_values_videos"], inputs.get("padding_mask_videos"))
                return {"audio_embeds": None, "video_embeds": value.detach().float().cpu().tolist(),
                    "visual_embeds": value.detach().float().cpu().tolist(), "audio_video_embeds": None,
                    "audio_visual_embeds": None, "audio_text_embeds": None, "text_audio_embeds": None,
                    "visual_text_embeds": None, "text_video_embeds": None,
                    "audio_visual_text_embeds": None, "text_audio_video_embeds": None}
            output = self.model(**inputs)
        result: dict[str, list[list[float]] | None] = {}
        names = ("audio_embeds", "video_embeds", "visual_embeds", "audio_video_embeds", "audio_visual_embeds", "audio_text_embeds", "text_audio_embeds", "visual_text_embeds", "text_video_embeds", "audio_visual_text_embeds", "audio_visual_text_embeds")
        for name in names:
            value = getattr(output, name, None)
            result[name] = value.detach().float().cpu().tolist() if value is not None else None
        return result


def configured_adapter() -> PEAVAdapter:
    path = os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_PATH")
    if not path:
        raise PEAVUnavailable("VIDEO_AUDIO_ANALYZER_PE_AV_PATH is not set")
    return PEAVAdapter(path)
