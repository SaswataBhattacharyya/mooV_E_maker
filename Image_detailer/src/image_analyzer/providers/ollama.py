from __future__ import annotations

import base64
import os
import json
import subprocess
from pathlib import Path
from typing import Any

import requests

from image_analyzer.providers.base import OptionalProvider, ProviderArtifact


class OllamaSynthesisProvider(OptionalProvider):
    name = "ollama"

    def __init__(self, base_url: str, model_name: str, timeout_sec: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_sec = timeout_sec

    def synthesize(self, image_path: Path, context: dict[str, object]) -> ProviderArtifact:
        try:
            content = self._chat(
                messages=[
                    {
                        "role": "user",
                        "content": _build_prompt(context),
                    }
                ],
                image_path=None,
                num_predict=700,
            )
            if content:
                return ProviderArtifact(provider=self.name, data={"description": content})
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"Ollama synthesis unavailable: {exc}"])
        return ProviderArtifact(provider=self.name, warnings=["Ollama synthesis returned no content"])

    def analyze_visual_pass(self, image_path: Path, prompt: str, *, num_predict: int = 900) -> ProviderArtifact:
        try:
            content = self._chat(
                messages=[{"role": "user", "content": prompt}],
                image_path=image_path,
                num_predict=num_predict,
            )
            return ProviderArtifact(provider=self.name, data={"content": content})
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"Ollama visual analysis unavailable: {exc}"])

    def generate_json(self, prompt: str, *, image_path: Path | None = None, num_predict: int = 1200) -> ProviderArtifact:
        try:
            content = self._chat(
                messages=[{"role": "user", "content": prompt}],
                image_path=image_path,
                num_predict=num_predict,
                format_mode="json",
            )
            parsed = _safe_parse_json(content)
            if parsed is not None:
                return ProviderArtifact(provider=self.name, data={"json": parsed, "content": content})
            return ProviderArtifact(
                provider=self.name,
                data={"content": content},
                warnings=["Ollama JSON response could not be parsed cleanly."],
            )
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"Ollama JSON generation unavailable: {exc}"])

    def compare_images(self, reference_path: Path, generated_path: Path, prompt: str) -> ProviderArtifact:
        content_prompt = (
            f"{prompt}\n\nReference image is attached first. Generated image is attached second. "
            "Produce strict JSON if possible."
        )
        try:
            content = self._chat(
                messages=[
                    {
                        "role": "user",
                        "content": content_prompt,
                        "images": [_encode_image(reference_path), _encode_image(generated_path)],
                    }
                ],
                image_path=None,
                num_predict=1200,
                format_mode="json",
            )
            parsed = _safe_parse_json(content)
            if parsed is not None:
                return ProviderArtifact(provider=self.name, data={"json": parsed, "content": content})
            return ProviderArtifact(provider=self.name, data={"content": content}, warnings=["Comparison JSON was not parseable."])
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"Ollama image comparison unavailable: {exc}"])

    def _chat(
        self,
        *,
        messages: list[dict[str, Any]],
        image_path: Path | None,
        num_predict: int,
        format_mode: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "stream": False,
            "messages": [dict(message) for message in messages],
            "options": {"num_predict": num_predict},
            "keep_alive": os.environ.get("IMAGE_ANALYZER_OLLAMA_KEEP_ALIVE", "45s"),
        }
        if format_mode == "json":
            payload["format"] = "json"
        if image_path is not None and payload["messages"]:
            payload["messages"][0]["images"] = [_encode_image(image_path)]
        if os.environ.get("IMAGE_ANALYZER_ENFORCE_SINGLE_OLLAMA_MODEL", "1") == "1":
            _ensure_single_active_model(self.model_name)
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout_sec,
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "").strip()
        except requests.HTTPError as exc:
            if _looks_like_model_load_failure(exc):
                _ensure_single_active_model(self.model_name, force_unload_target=False)
                retry_response = requests.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout_sec,
                )
                retry_response.raise_for_status()
                return retry_response.json().get("message", {}).get("content", "").strip()
            raise


def configure_ollama_runtime(max_loaded_models: int, num_parallel: int) -> None:
    os.environ.setdefault("OLLAMA_MAX_LOADED_MODELS", str(max_loaded_models))
    os.environ.setdefault("OLLAMA_NUM_PARALLEL", str(num_parallel))
    os.environ.setdefault("IMAGE_ANALYZER_ENFORCE_SINGLE_OLLAMA_MODEL", "1")
    os.environ.setdefault("IMAGE_ANALYZER_OLLAMA_KEEP_ALIVE", "45s")


def _build_prompt(context: dict[str, object]) -> str:
    return (
        "Write a precise, richly detailed image description from the structured analysis below. "
        "Prefer measured findings. Call out uncertainty explicitly. "
        f"Structured analysis: {context}"
    )


def _encode_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _safe_parse_json(content: str) -> dict[str, Any] | list[Any] | None:
    if not content.strip():
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = min(
            (index for index in (content.find("{"), content.find("[")) if index != -1),
            default=-1,
        )
        end = max(content.rfind("}"), content.rfind("]"))
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None


def _ensure_single_active_model(target_model: str, *, force_unload_target: bool = False) -> None:
    for model in _running_models():
        if model == target_model and not force_unload_target:
            continue
        _stop_model(model)


def _running_models() -> list[str]:
    try:
        completed = subprocess.run(["ollama", "ps"], capture_output=True, text=True, check=True)
    except Exception:
        return []
    models: list[str] = []
    for line in completed.stdout.splitlines()[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        models.append(stripped.split()[0])
    return models


def _stop_model(model_name: str) -> None:
    try:
        subprocess.run(["ollama", "stop", model_name], capture_output=True, text=True, check=False)
    except Exception:
        return


def _looks_like_model_load_failure(exc: requests.HTTPError) -> bool:
    response = exc.response
    if response is None:
        return False
    try:
        payload = response.json()
        message = str(payload.get("error", ""))
    except Exception:
        message = response.text
    lowered = message.lower()
    return "model failed to load" in lowered or "resource limitations" in lowered
