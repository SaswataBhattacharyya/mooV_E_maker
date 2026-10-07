from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI


app = FastAPI(title="image-analyzer-supervisor")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
def config() -> dict[str, object]:
    return {
        "project_root": str(PROJECT_ROOT),
        "ollama_host": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        "ollama_reasoning_model": os.environ.get("OLLAMA_REASONING_MODEL"),
        "ollama_coder_model": os.environ.get("OLLAMA_CODER_MODEL"),
        "ollama_synthesis_model": os.environ.get("OLLAMA_SYNTHESIS_MODEL"),
    }


@app.get("/")
def index() -> dict[str, object]:
    return {
        "name": "image-analyzer supervisor",
        "docs": [
            "openclaw/DUTY.md",
            "openclaw/KNOWLEDGE.md",
            "openclaw/PIPELINE.md",
            "openclaw/SOUL.md",
            "openclaw/STYLE.md",
            "openclaw/RUNTIME.md",
        ],
    }

