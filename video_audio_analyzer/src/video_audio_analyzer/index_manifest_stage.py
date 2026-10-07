"""Rebuild a run-local search index after all model embeddings are attached."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .retrieval import build_index


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m video_audio_analyzer.index_manifest_stage MANIFEST.json")
    manifest_path = Path(sys.argv[1]).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = build_index(manifest, manifest_path.parent, index_name="index_v2",
        preserve_clap_from=manifest_path.parent / "index")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
