import os
from pathlib import Path
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent
_CONFIG_DIR = _PROJECT_ROOT / "config"
_LOCAL_ENV_FILE = _CONFIG_DIR / "movie_builder.local.env"

if _LOCAL_ENV_FILE.exists():
    load_dotenv(_LOCAL_ENV_FILE)

PROJECT_ROOT: str = str(_PROJECT_ROOT)
PROJECT_STATE_DIR: str = str(_PROJECT_ROOT / "project_state")
EXPORTS_DIR: str = str(_PROJECT_ROOT / "exports")
CONFIG_DIR: str = str(_CONFIG_DIR)
LOCAL_ENV_FILE: str = str(_LOCAL_ENV_FILE)

OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_STORY_MODEL: str = os.getenv("OLLAMA_STORY_MODEL", "qwen3.6:35b")
OLLAMA_CODER_MODEL: str = os.getenv("OLLAMA_CODER_MODEL", "qwen3-coder:30b")
MOVIE_BUILDER_HOST: str = os.getenv("MOVIE_BUILDER_HOST", "0.0.0.0")
MOVIE_BUILDER_PORT: str = os.getenv("MOVIE_BUILDER_PORT", "8501")
