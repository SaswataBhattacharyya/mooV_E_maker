"""Minimal Ollama client for structured OpenClaw planning steps."""

from __future__ import annotations

import json
import os
import base64
import subprocess
import urllib.error
import urllib.request
from typing import Any

from story_builder.services.media_jobs import MediaJobError, gpu_workload_guard



DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_OLLAMA_MODEL = os.environ.get(
    "OLLAMA_REASONING_MODEL",
    os.environ.get("OPENCLAW_LLM_MODEL", "qwen3.6:35b"),
)
DEFAULT_OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "0m")
DEFAULT_REASONING_KEEP_ALIVE = os.environ.get(
    "OLLAMA_REASONING_KEEP_ALIVE",
    DEFAULT_OLLAMA_KEEP_ALIVE,
)
DEFAULT_VISION_KEEP_ALIVE = os.environ.get(
    "OLLAMA_VISION_KEEP_ALIVE",
    DEFAULT_OLLAMA_KEEP_ALIVE,
)


class OllamaError(RuntimeError):
    """Raised when the local Ollama service cannot satisfy a request."""


def _run_ollama_cli(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["ollama", *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise OllamaError("The ollama CLI is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise OllamaError(f"ollama {' '.join(arguments)} timed out") from exc

    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        raise OllamaError(output or f"ollama {' '.join(arguments)} failed")
    return output


def list_running_models() -> list[dict[str, Any]]:
    output = _run_ollama_cli(["ps"])
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if len(lines) <= 1:
        return []

    models: list[dict[str, Any]] = []
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        model: dict[str, Any] = {"name": name, "raw": line}
        if len(parts) >= 2:
            model["id"] = parts[1]
        if len(parts) >= 3:
            model["size"] = parts[2]
        if len(parts) >= 4:
            model["processor"] = parts[3]
        if len(parts) >= 5:
            model["until"] = " ".join(parts[4:])
        models.append(model)
    return models


def stop_model(model: str) -> str:
    if not model.strip():
        raise OllamaError("Model name is required for ollama stop")
    return _run_ollama_cli(["stop", model.strip()])


def _clean_json_text(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    return text


def _generate(
    *,
    prompt: str,
    model: str,
    temperature: float,
    response_format: str | None = None,
    images: list[str] | None = None,
    keep_alive: str | None = None,
    cpu_only: bool = False,
    gpu_admission_timeout_seconds: int = 24 * 3600,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }
    if cpu_only:
        # Request-scoped runner setting: keeps this reasoning job off the GPU
        # without mutating global Ollama configuration for other workloads.
        payload["options"]["num_gpu"] = 0
    if response_format is not None:
        payload["format"] = response_format
    if images:
        payload["images"] = images
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    request = urllib.request.Request(
        f"{DEFAULT_OLLAMA_HOST}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        # Ollama may execute on the same unified-memory GPU used by ComfyUI.
        # Hold the Story Builder lease for the full inference and wait until
        # visible ComfyUI work is idle before asking it to load a model.
        with gpu_workload_guard(comfy_url=os.environ.get("COMFYUI_URL", "http://127.0.0.1:3008"),
                                timeout_seconds=gpu_admission_timeout_seconds):
            with urllib.request.urlopen(request, timeout=300) as response:
                raw = json.loads(response.read().decode("utf-8"))
    except MediaJobError as exc:
        raise OllamaError(f"GPU admission blocked: {exc}") from exc
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body = ""
        detail = f"Ollama returned HTTP {exc.code}"
        if body:
            detail = f"{detail}: {body}"
        raise OllamaError(detail) from exc
    except urllib.error.URLError as exc:
        raise OllamaError(f"Could not reach Ollama at {DEFAULT_OLLAMA_HOST}") from exc
    # Reasoning-capable Qwen variants may place the structured answer in the
    # ``thinking`` field when ``format=json`` is requested and leave
    # ``response`` empty.  Treat that field as the answer so callers do not
    # fail despite Ollama having completed successfully.
    response = str(raw.get("response", "")).strip()
    if response:
        return response
    thinking = str(raw.get("thinking", "")).strip()
    return thinking


def generate_text(*, prompt: str, model: str = DEFAULT_OLLAMA_MODEL, temperature: float = 0.3) -> str:
    return _generate(
        prompt=prompt,
        model=model,
        temperature=temperature,
        keep_alive=DEFAULT_REASONING_KEEP_ALIVE,
    )


def generate_json(*, prompt: str, model: str = DEFAULT_OLLAMA_MODEL, temperature: float = 0.4,
                  cpu_only: bool = False, gpu_admission_timeout_seconds: int = 24 * 3600) -> dict[str, Any]:
    response_text = _clean_json_text(
        _generate(
            prompt=prompt,
            model=model,
            temperature=temperature,
            response_format="json",
            keep_alive=DEFAULT_REASONING_KEEP_ALIVE,
            cpu_only=cpu_only,
            gpu_admission_timeout_seconds=gpu_admission_timeout_seconds,
        )
    )
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        # Some reasoning models wrap the JSON with a short explanation or
        # think tags even when ``format=json`` is requested.  Recover the
        # first complete JSON object/array without accepting arbitrary text.
        decoder = json.JSONDecoder()
        for index, char in enumerate(response_text):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(response_text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        raise OllamaError("Ollama did not return valid JSON")


def _encode_image(path: str) -> str:
    return base64.b64encode(open(path, "rb").read()).decode("ascii")


def generate_vision_json(
    *,
    prompt: str,
    image_paths: list[str],
    model: str,
    temperature: float = 0.2,
) -> dict[str, Any]:
    encoded_images = [_encode_image(path) for path in image_paths]
    response_text = _clean_json_text(
        _generate(
            prompt=prompt,
            model=model,
            temperature=temperature,
            response_format="json",
            images=encoded_images,
            keep_alive=DEFAULT_VISION_KEEP_ALIVE,
        )
    )
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise OllamaError("Vision model did not return valid JSON") from exc
