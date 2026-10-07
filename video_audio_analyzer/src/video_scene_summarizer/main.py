from __future__ import annotations

from pathlib import Path

from video_scene_summarizer.cli.interactive import run_interactive


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    run_interactive(project_root)


if __name__ == "__main__":
    main()
