from __future__ import annotations

import json
import os
import platform
from pathlib import Path


def main() -> None:
    model_dir = Path(os.environ.get("PE_AV_MODEL_DIR", "/models/pe-av-base"))
    result = {
        "architecture": platform.machine(),
        "model_dir": str(model_dir),
        "model_present": (model_dir / "config.json").exists() and (model_dir / "model.safetensors").exists(),
        "model_id": "facebook/pe-av-base",
        "status": "ready" if (model_dir / "config.json").exists() else "missing_checkpoint",
    }
    try:
        import torch
        result["torch"] = torch.__version__
        result["cuda_available"] = bool(torch.cuda.is_available())
        from core.audio_visual_encoder import PEAudioVisual, PEAudioVisualTransform  # noqa: F401
        result["perception_models_import"] = "ready"
    except Exception as exc:
        result["perception_models_import"] = "error"
        result["error"] = str(exc)
    panns_path = Path(os.environ.get("PANNs_CHECKPOINT", "/models/panns/Cnn14_DecisionLevelMax_mAP=0.385.pth"))
    result["panns"] = {"checkpoint": str(panns_path), "present": panns_path.exists() and panns_path.stat().st_size >= 300_000_000}
    try:
        import panns_inference  # noqa: F401
        result["panns"]["import"] = "ready"
    except Exception as exc:
        result["panns"]["import"] = "unavailable"
        result["panns"]["error"] = str(exc)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
