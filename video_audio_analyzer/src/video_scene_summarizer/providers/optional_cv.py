from __future__ import annotations

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

from video_scene_summarizer.models.schemas import BoundingBox
from video_scene_summarizer.providers.base import OptionalProvider, ProviderArtifact

_VIDEO_ROOT = Path(__file__).resolve().parents[3]
_DEPTH_MODEL = None
_DINO_MODEL = None


class DepthAnythingProvider(OptionalProvider):
    """Relative-depth evidence using the locally cloned Depth Anything V2."""

    name = "depth_anything_v2"

    def analyze(self, image_path: Path, context: dict[str, object]) -> ProviderArtifact:
        del context
        model_path = Path(os.environ.get("VIDEO_SUMMARIZER_DEPTH_MODEL", str(_VIDEO_ROOT / "models" / "depth_anything_v2_vits.pth")))
        repo = Path(os.environ.get("VIDEO_SUMMARIZER_DEPTH_REPO", str(_VIDEO_ROOT / "vendor" / "Depth-Anything-V2")))
        if not model_path.is_file() or not repo.is_dir():
            return ProviderArtifact(provider=self.name, warnings=[f"Depth Anything V2 weights/repository unavailable: {model_path}"])
        try:
            import cv2
            import numpy as np
            import torch
            if str(repo) not in sys.path:
                sys.path.insert(0, str(repo))
            from depth_anything_v2.dpt import DepthAnythingV2  # type: ignore
            global _DEPTH_MODEL
            if _DEPTH_MODEL is None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                _DEPTH_MODEL = DepthAnythingV2(encoder="vits", features=64, out_channels=[48, 96, 192, 384])
                _DEPTH_MODEL.load_state_dict(torch.load(model_path, map_location="cpu"))
                _DEPTH_MODEL = _DEPTH_MODEL.to(device).eval()
            image = cv2.imread(str(image_path))
            if image is None:
                raise ValueError("unable to read image")
            depth = _DEPTH_MODEL.infer_image(image)
            depth = np.asarray(depth, dtype=np.float32)
            finite = depth[np.isfinite(depth)]
            if finite.size == 0:
                raise ValueError("depth output is empty")
            artifact_root = Path(os.environ.get("VIDEO_SUMMARIZER_VISION_ARTIFACT_DIR", str(image_path.parent / "vision_artifacts")))
            artifact_root.mkdir(parents=True, exist_ok=True)
            depth_path = artifact_root / f"{image_path.stem}_depth.png"
            normalized = ((depth - finite.min()) / max(float(finite.max() - finite.min()), 1e-6) * 255).clip(0, 255).astype("uint8")
            cv2.imwrite(str(depth_path), normalized)
            return ProviderArtifact(provider=self.name, data={"depth_path": str(depth_path), "min": float(finite.min()), "max": float(finite.max()), "mean": float(finite.mean()), "near_is_bright": True})
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"Depth Anything V2 failed: {exc}"])


class DINOEmbeddingProvider(OptionalProvider):
    """Optional DINO embedding evidence for continuity/reference similarity."""

    name = "dinov3"

    def analyze(self, image_path: Path, context: dict[str, object]) -> ProviderArtifact:
        del context
        model_ref = Path(os.environ.get("VIDEO_SUMMARIZER_DINO_MODEL_DIR", "/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/models/Pixal3D/camenduru_dinov3-vitl16-pretrain-lvd1689m"))
        if not (model_ref / "model.safetensors").is_file():
            return ProviderArtifact(provider=self.name, warnings=[f"DINOv3 weights not found: {model_ref}"])
        try:
            import torch
            from PIL import Image
            from transformers import AutoImageProcessor, AutoModel  # type: ignore
            global _DINO_MODEL
            if _DINO_MODEL is None:
                processor = AutoImageProcessor.from_pretrained(str(model_ref), local_files_only=True)
                model = AutoModel.from_pretrained(str(model_ref), local_files_only=True)
                _DINO_MODEL = (processor, model.eval())
            processor, model = _DINO_MODEL
            with torch.no_grad():
                output = model(**processor(images=Image.open(image_path).convert("RGB"), return_tensors="pt"))
                vector = output.last_hidden_state[:, 0, :].float()
                vector = torch.nn.functional.normalize(vector, dim=-1)[0].cpu().tolist()
            return ProviderArtifact(provider=self.name, data={"embedding": vector, "dimension": len(vector), "model_path": str(model_ref)})
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"DINOv3 embedding unavailable: {exc}"])


class ComfySam3Provider(OptionalProvider):
    """Capability evidence for the installed ComfyUI SAM3.1 nodes.

    Actual segmentation remains a ComfyUI graph operation; this provider never
    fabricates masks when the API is offline or the node schema changes.
    """

    name = "comfyui_sam3"

    def analyze(self, image_path: Path, context: dict[str, object]) -> ProviderArtifact:
        del image_path, context
        base_url = os.environ.get("COMFYUI_URL", "http://127.0.0.1:3008").rstrip("/")
        try:
            with urllib.request.urlopen(f"{base_url}/object_info", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            available = [name for name in ("SAM3_Detect", "SAM3_VideoTrack") if name in payload]
            if not available:
                return ProviderArtifact(provider=self.name, warnings=["ComfyUI is reachable but SAM3 nodes are not exposed in /object_info"])
            return ProviderArtifact(provider=self.name, data={"available": True, "nodes": available, "checkpoint": os.environ.get("COMFYUI_SAM3_CHECKPOINT", "sam3.1_multiplex_fp16.safetensors"), "execution": "comfyui_api"})
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"ComfyUI SAM3 unavailable: {exc}"])


class ViTPoseProvider(OptionalProvider):
    """Whole-body pose evidence from the locally installed ViTPose ONNX model."""

    name = "vitpose"

    def analyze(self, image_path: Path, context: dict[str, object]) -> ProviderArtifact:
        del context
        model_path = Path(os.environ.get("VIDEO_SUMMARIZER_VITPOSE_MODEL", "/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI/models/detection/vitpose-l-wholebody.onnx"))
        if not model_path.is_file():
            return ProviderArtifact(provider=self.name, warnings=[f"ViTPose model not found: {model_path}"])
        try:
            import cv2
            import numpy as np
            import onnxruntime as ort
            image = cv2.imread(str(image_path))
            if image is None:
                raise ValueError("unable to read image")
            height, width = image.shape[:2]
            resized = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), (192, 256)).astype("float32") / 255.0
            resized = (resized - np.array([0.485, 0.456, 0.406], dtype="float32")) / np.array([0.229, 0.224, 0.225], dtype="float32")
            output = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"]).run(None, {"input_0": resized.transpose(2, 0, 1)[None]})[0]
            heatmaps = np.asarray(output)[0]
            points = []
            for heatmap in heatmaps:
                y, x = np.unravel_index(int(np.argmax(heatmap)), heatmap.shape)
                confidence = float(heatmap[y, x])
                points.append({"x": round(float(x / max(heatmap.shape[1] - 1, 1) * width), 2), "y": round(float(y / max(heatmap.shape[0] - 1, 1) * height), 2), "confidence": round(confidence, 4)})
            return ProviderArtifact(provider=self.name, data={"keypoints": points, "count": len(points), "model_path": str(model_path), "coordinate_space": "full_image"})
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"ViTPose failed: {exc}"])


class YoloDetectionProvider(OptionalProvider):
    name = "yolo"

    def analyze(self, image_path: Path, context: dict[str, object]) -> ProviderArtifact:
        del context
        try:
            from ultralytics import YOLO  # type: ignore
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"YOLO unavailable: {exc}"])

        model_path = os.environ.get("VIDEO_SUMMARIZER_YOLO_MODEL", str(_VIDEO_ROOT / "models" / "yolov8m.pt"))
        allow_downloads = os.environ.get("VIDEO_SUMMARIZER_ALLOW_MODEL_DOWNLOADS", "").lower() in {"1", "true", "yes"}
        if not allow_downloads and not Path(model_path).exists():
            return ProviderArtifact(
                provider=self.name,
                warnings=[f"YOLO model not found locally: {model_path}. Set VIDEO_SUMMARIZER_ALLOW_MODEL_DOWNLOADS=1 to permit auto-downloads."],
            )

        try:
            model = YOLO(model_path)
            results = model.predict(source=str(image_path), verbose=False)
            detections: list[dict[str, object]] = []
            for result in results:
                boxes = getattr(result, "boxes", None)
                if boxes is None:
                    continue
                for box in boxes:
                    coords = box.xyxy[0].tolist()
                    cls_id = int(box.cls[0].item())
                    label = result.names.get(cls_id, str(cls_id))
                    detections.append(
                        {
                            "label": label,
                            "bbox_px": BoundingBox(
                                x1=int(coords[0]),
                                y1=int(coords[1]),
                                x2=int(coords[2]),
                                y2=int(coords[3]),
                            ).to_dict(),
                            "confidence": float(box.conf[0].item()),
                            "provenance": self.name,
                        }
                    )
            return ProviderArtifact(provider=self.name, data={"detections": detections})
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"YOLO failed: {exc}"])


class FlorenceRegionProvider(OptionalProvider):
    name = "florence2"

    def analyze(self, image_path: Path, context: dict[str, object]) -> ProviderArtifact:
        del context
        try:
            from transformers import AutoModelForCausalLM, AutoProcessor  # type: ignore
            from PIL import Image
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"Florence-2 unavailable: {exc}"])

        allow_downloads = os.environ.get("VIDEO_SUMMARIZER_ALLOW_MODEL_DOWNLOADS", "").lower() in {"1", "true", "yes"}
        model_ref = os.environ.get("VIDEO_SUMMARIZER_FLORENCE_MODEL_DIR", str(_VIDEO_ROOT / "models" / "florence-2-large"))
        local_only = Path(model_ref).exists() and Path(model_ref).is_dir()
        # Never let an optional provider attempt an implicit Hugging Face
        # download.  In offline/default mode a model identifier is not enough
        # evidence that weights exist locally.
        if not local_only and not allow_downloads:
            return ProviderArtifact(
                provider=self.name,
                warnings=[f"Florence-2 weights not found locally: {model_ref}. Set VIDEO_SUMMARIZER_FLORENCE_MODEL_DIR to a local directory or explicitly enable downloads."],
            )
        try:
            processor = AutoProcessor.from_pretrained(
                model_ref,
                trust_remote_code=True,
                local_files_only=local_only or not allow_downloads,
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_ref,
                trust_remote_code=True,
                local_files_only=local_only or not allow_downloads,
                # Florence-2's custom class predates Transformers' SDPA
                # capability probe. Eager attention avoids the missing
                # `_supports_sdpa` attribute while preserving correctness.
                attn_implementation="eager",
            )
            image = Image.open(image_path).convert("RGB")
            prompt = "<MORE_DETAILED_CAPTION>"
            generated = _run_florence_caption(model, processor, image, prompt)
            text = processor.batch_decode(generated, skip_special_tokens=False)[0]
            parsed = processor.post_process_generation(
                text,
                task=prompt,
                image_size=(image.width, image.height),
            )
            caption = parsed.get(prompt, parsed) if isinstance(parsed, dict) else parsed
            return ProviderArtifact(provider=self.name, data={"caption": caption})
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"Florence-2 failed: {exc}"])


def _run_florence_caption(model: object, processor: object, image: object, prompt: str) -> object:
    inputs = processor(text=prompt, images=image, return_tensors="pt")
    # Florence-2 model revisions do not all expose forced_bos_token_id on
    # their language config.  Let the model's own generation config supply it.
    # The legacy Florence generation helper assumes a populated KV cache;
    # Transformers 4.57+/5.x can pass an empty cache on the first beam step.
    # Disabling cache is slightly slower but reliable for this optional pass.
    return model.generate(input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"], max_new_tokens=64, num_beams=1, use_cache=False)


class DocTROcrProvider(OptionalProvider):
    """Optional deep-learning OCR provider with word regions and confidence."""

    name = "doctr"

    def analyze(self, image_path: Path, context: dict[str, object]) -> ProviderArtifact:
        del context
        try:
            from doctr.io import DocumentFile  # type: ignore
            from doctr.models import ocr_predictor  # type: ignore
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"docTR unavailable: {exc}"])

        try:
            allow_downloads = os.environ.get("VIDEO_SUMMARIZER_ALLOW_MODEL_DOWNLOADS", "").lower() in {"1", "true", "yes"}
            # docTR downloads detector/recognizer weights on first use. Keep
            # that explicit, matching the other optional providers.
            cache_dir = Path(os.environ.get("DOCTR_CACHE_DIR", str(Path.home() / ".cache" / "doctr" / "models")))
            # Resolve architecture names before checking the cache.
            det_arch = os.environ.get("VIDEO_SUMMARIZER_DOCTR_DET_ARCH", "db_resnet50")
            reco_arch = os.environ.get("VIDEO_SUMMARIZER_DOCTR_RECO_ARCH", "crnn_vgg16_bn")
            cached_weights = list(cache_dir.glob(f"{det_arch}-*.pt"))
            cached_recognizer = list(cache_dir.glob(f"{reco_arch}-*.pt"))
            weights_ready = bool(cached_weights and cached_recognizer)
            if not allow_downloads and not weights_ready and not os.environ.get("DOCTR_WEIGHTS_READY", "").lower() in {"1", "true", "yes"}:
                return ProviderArtifact(provider=self.name, warnings=["docTR weights are not marked ready. Set VIDEO_SUMMARIZER_ALLOW_MODEL_DOWNLOADS=1 for the first run, then set DOCTR_WEIGHTS_READY=1."])
            predictor = ocr_predictor(det_arch=det_arch, reco_arch=reco_arch, pretrained=True, assume_straight_pages=True)
            document = DocumentFile.from_images(str(image_path))
            exported = predictor(document).export()
            pages = exported.get("pages", []) if isinstance(exported, dict) else []
            words: list[dict[str, object]] = []
            lines: list[str] = []
            for page in pages:
                for block in page.get("blocks", []):
                    for line in block.get("lines", []):
                        line_words = line.get("words", [])
                        line_text = " ".join(str(word.get("value", "")).strip() for word in line_words).strip()
                        if line_text:
                            lines.append(line_text)
                        for word in line_words:
                            words.append({"value": word.get("value", ""), "confidence": word.get("confidence", 0.0), "geometry": word.get("geometry")})
            return ProviderArtifact(provider=self.name, data={"ocr_text": "\n".join(lines), "words": words, "detector": det_arch, "recognizer": reco_arch})
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"docTR failed: {exc}"])
