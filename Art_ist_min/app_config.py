"""Shared runtime configuration for the simplified launcher."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _get_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    return int(value)


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    comfyui_path: Path
    comfyui_host: str
    comfyui_port: int
    website_host: str
    website_port: int
    start_comfyui: bool
    start_website: bool
    frontend_dir: Path
    workflows_dir: Path
    venv_dir: Path
    requirements_file: Path

    @property
    def venv_python(self) -> Path:
        if sys.platform == "win32":
            return self.venv_dir / "Scripts" / "python.exe"
        return self.venv_dir / "bin" / "python"

    @property
    def base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "COMFYUI_PATH": str(self.comfyui_path),
                "COMFYUI_HOST": self.comfyui_host,
                "COMFYUI_PORT": str(self.comfyui_port),
                "WEBSITE_HOST": self.website_host,
                "WEBSITE_PORT": str(self.website_port),
                "START_COMFYUI": "true" if self.start_comfyui else "false",
                "START_WEBSITE": "true" if self.start_website else "false",
            }
        )
        return env


def _prompt_for_port(label: str, default: int) -> int:
    try:
        value = input(f"{label} [{default}]: ").strip()
    except EOFError:
        return default
    if not value:
        return default
    return int(value)


def load_config(project_root: Path, *, prompt_for_ports: bool = False) -> AppConfig:
    comfyui_port = _get_int("COMFYUI_PORT", 3008)
    website_port = _get_int("WEBSITE_PORT", _get_int("WEBSITE_FRONTEND_PORT", 3010))
    if prompt_for_ports:
        comfyui_port = _prompt_for_port("ComfyUI port", comfyui_port)
        website_port = _prompt_for_port("Website port", website_port)
    if comfyui_port == website_port:
        raise ValueError("ComfyUI port and website port must be different.")

    return AppConfig(
        project_root=project_root,
        comfyui_path=Path(os.environ.get("COMFYUI_PATH", project_root / "ComfyUI")).resolve(),
        comfyui_host=os.environ.get("COMFYUI_HOST", "127.0.0.1"),
        comfyui_port=comfyui_port,
        website_host=os.environ.get("WEBSITE_HOST", "127.0.0.1"),
        website_port=website_port,
        start_comfyui=_get_bool("START_COMFYUI", True),
        start_website=_get_bool("START_WEBSITE", True),
        frontend_dir=(project_root / "ai-art-generator-hub").resolve(),
        workflows_dir=(project_root / "workflows").resolve(),
        venv_dir=(project_root / "venv").resolve(),
        requirements_file=(project_root / "requirements.txt").resolve(),
    )
