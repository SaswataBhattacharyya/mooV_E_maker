from __future__ import annotations

from pathlib import Path

from video_scene_summarizer.config.settings import load_settings
from video_scene_summarizer.graph.workflow import run_download_stage
from video_scene_summarizer.utils.logging_utils import configure_logging


def run_download_only_interactive(project_root: Path) -> None:
    config = load_settings(project_root)
    configure_logging(config.log_dir, "download_stage.log")
    query = input("Text query for YouTube search: ").strip()
    count = int(input("Number of videos to download: ").strip())
    download_root = input(f"Video download folder [{config.downloads_dir}]: ").strip() or str(config.downloads_dir)

    result = run_download_stage(
        config=config,
        source_query=query,
        requested_video_count=count,
        download_root=Path(download_root),
    )

    downloaded = [
        record
        for record in result.get("queued_videos", [])
        if getattr(record, "video_path", None) is not None and not getattr(record, "error", None)
    ]

    print("\nDownload stage complete.")
    print(f"Downloaded videos: {len(downloaded)}")
    if result.get("errors"):
        print("Errors:")
        for err in result["errors"]:
            print(f"- {err}")
