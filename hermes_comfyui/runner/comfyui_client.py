"""Small stdlib-only ComfyUI client derived from Art_ist_min's proven bridge."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class ComfyUIError(RuntimeError):
    pass


class ComfyUIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:3008") -> None:
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict[str, Any]:
        return self._get_json("/system_stats", timeout=10)

    def upload_image(self, path: Path) -> str:
        boundary = f"----hermes{time.time_ns()}"
        body = _multipart(boundary, path)
        request = urllib.request.Request(
            f"{self.base_url}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ComfyUIError(f"Failed to upload input image {path.name}: {exc}") from exc
        return str(data.get("name") or path.name)

    def submit(self, workflow: dict[str, Any]) -> str:
        request = urllib.request.Request(
            f"{self.base_url}/prompt",
            data=json.dumps({"prompt": workflow}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ComfyUIError(f"ComfyUI rejected workflow (HTTP {exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise ComfyUIError(f"Could not reach ComfyUI at {self.base_url}") from exc
        if not data.get("prompt_id"):
            raise ComfyUIError(f"ComfyUI did not return prompt_id: {data}")
        return str(data["prompt_id"])

    def wait(self, prompt_id: str, timeout_seconds: int = 900) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            history = self._get_json(f"/history/{prompt_id}", timeout=30)
            state = history.get(prompt_id)
            if state:
                status = state.get("status", {})
                if status.get("status_str") == "error":
                    raise ComfyUIError(f"ComfyUI execution failed: {status.get('messages', [])}")
                if status.get("completed"):
                    return state
            time.sleep(2)
        raise ComfyUIError(f"Timed out waiting for prompt {prompt_id}")

    def download_outputs(self, history: dict[str, Any], destination: Path) -> list[dict[str, str]]:
        destination.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, str]] = []
        keys = (("images", "image"), ("videos", "video"), ("gifs", "video"), ("audio", "audio"))
        for node in history.get("outputs", {}).values():
            for key, kind in keys:
                for item in node.get(key, []):
                    filename = str(item.get("filename", ""))
                    if not filename:
                        continue
                    params = urllib.parse.urlencode({"filename": filename, "subfolder": item.get("subfolder", ""), "type": item.get("type", "output")})
                    target = destination / Path(filename).name
                    with urllib.request.urlopen(f"{self.base_url}/view?{params}", timeout=180) as response:
                        target.write_bytes(response.read())
                    results.append({"kind": kind, "path": str(target.resolve())})
        return results

    def _get_json(self, path: str, timeout: int) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(f"{self.base_url}{path}", timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ComfyUIError(f"ComfyUI request failed for {path}: {exc}") from exc


def _multipart(boundary: str, path: Path) -> bytes:
    prefix = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{path.name}\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    return prefix + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
