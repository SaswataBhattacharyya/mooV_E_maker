"""PE-AV-only phase run after InternVideo3 has exited and released GPU memory."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .internvideo3_stage import attach_peav_text_embeddings


def embed_manifest_text(manifest_path: Path) -> dict:
    return attach_peav_text_embeddings(manifest_path)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m video_audio_analyzer.peav_text_stage MANIFEST.json")
    print(json.dumps(embed_manifest_text(Path(sys.argv[1])), indent=2))


if __name__ == "__main__":
    main()
