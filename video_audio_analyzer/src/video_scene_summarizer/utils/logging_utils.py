from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_dir: Path, log_name: str = "video_scene_summarizer.log") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_name
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
