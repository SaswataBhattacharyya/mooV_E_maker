from __future__ import annotations

import argparse
import json
from pathlib import Path

from video_audio_analyzer.repertoire import promote_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote approved analyzer artifacts into video_repertoire")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--repertoire", type=Path, default=Path(__file__).resolve().parents[2] / "video_repertoire")
    parser.add_argument("--project-id", default="unassigned")
    args = parser.parse_args()
    print(json.dumps(promote_run(args.run_dir, args.repertoire, args.project_id), indent=2))


if __name__ == "__main__":
    main()
