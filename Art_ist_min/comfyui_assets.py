"""ComfyUI workflow asset discovery and downloading."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app_config import AppConfig


def _log(message: str) -> None:
    print(message, flush=True)


def _iter_workflow_model_entries(data: Any) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if isinstance(data, dict):
        models = data.get("models")
        if isinstance(models, list):
            for item in models:
                if not isinstance(item, dict):
                    continue
                url = item.get("url")
                directory = item.get("directory")
                if isinstance(url, str) and isinstance(directory, str):
                    found.append({"url": url, "directory": directory})
        for value in data.values():
            found.extend(_iter_workflow_model_entries(value))
    elif isinstance(data, list):
        for item in data:
            found.extend(_iter_workflow_model_entries(item))
    return found


def _discover_workflow_assets(workflows_dir: Path) -> list[dict[str, str]]:
    assets: dict[tuple[str, str], dict[str, str]] = {}
    if not workflows_dir.exists():
        return []

    for workflow_file in workflows_dir.rglob("*.json"):
        try:
            payload = json.loads(workflow_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for asset in _iter_workflow_model_entries(payload):
            assets[(asset["directory"], asset["url"])] = asset
    return sorted(assets.values(), key=lambda item: (item["directory"], item["url"]))


def _load_manifest(manifest_file: Path) -> list[dict[str, str]]:
    if not manifest_file.exists():
        return []
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a list in {manifest_file}")
    manifest_assets: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        directory = item.get("directory")
        if isinstance(url, str) and isinstance(directory, str):
            manifest_assets.append({"url": url, "directory": directory})
    return manifest_assets


def _download(url: str, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url) as response:
            destination.write_bytes(response.read())
        return True
    except urllib.error.URLError as exc:
        _log(f"[ASSET] failed {url} -> {destination}: {exc}")
        return False


def sync_comfyui_assets(config: AppConfig) -> dict[str, int]:
    workflow_assets = _discover_workflow_assets(config.workflows_dir)
    manifest_assets = _load_manifest(config.asset_manifest_file)

    unique_assets: dict[tuple[str, str], dict[str, str]] = {}
    for asset in workflow_assets + manifest_assets:
        unique_assets[(asset["directory"], asset["url"])] = asset

    downloaded = 0
    skipped = 0
    failed = 0

    for asset in unique_assets.values():
        filename = asset["url"].rstrip("/").split("/")[-1]
        destination = config.models_root / asset["directory"] / filename
        if destination.exists():
            skipped += 1
            _log(f"[ASSET] skip {destination}")
            continue
        _log(f"[ASSET] download {asset['url']} -> {destination}")
        if _download(asset["url"], destination):
            downloaded += 1
        else:
            failed += 1

    return {"downloaded": downloaded, "skipped": skipped, "failed": failed}
