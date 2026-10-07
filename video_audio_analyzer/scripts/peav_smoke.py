from __future__ import annotations

import json
import os
from pathlib import Path

from video_audio_analyzer.peav_adapter import PEAVAdapter


def main() -> None:
    checkpoint = os.environ.get("PE_AV_MODEL_DIR", "/models/pe-av-base")
    adapter = PEAVAdapter(checkpoint)
    # Text-only is a cheap deterministic checkpoint smoke test; media encoding
    # is invoked by the analyzer only when the user enables PE-AV processing.
    output = adapter.embed(text="a short cinematic scene with dialogue and music")
    vector = output.get("visual_text_embeds") or output.get("text_video_embeds") or []
    print(json.dumps({"status": "ready", "device": str(adapter.device), "dimension": adapter.dimension, "text_shape": [len(vector), len(vector[0]) if vector else 0]}))


if __name__ == "__main__":
    main()
