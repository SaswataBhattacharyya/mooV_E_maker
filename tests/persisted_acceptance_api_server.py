"""Isolated API subprocess for the persisted browser acceptance harness."""
from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()

    from story_builder.services.project_store import ProjectStore
    import story_builder.api.main as api

    storage = Path(args.storage)
    api.STORAGE_ROOT = storage
    api.PROJECT_STORE = ProjectStore(storage / "projects")
    api.UPLOADS_ROOT = storage / "uploads"
    api.OUTPUT_ROOT = Path(args.output)
    api.AUDIO_LIBRARY_ROOT = storage / "audio_library"
    api.COMFYUI_URL = "http://127.0.0.1:1"  # inert; lifespan and consumers are disabled
    uvicorn.run(api.app, host="127.0.0.1", port=args.port, log_level="warning", lifespan="off")


if __name__ == "__main__":
    main()
