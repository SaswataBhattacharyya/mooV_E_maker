from __future__ import annotations

import base64
import json
import logging
import socket
import os
from pathlib import Path
from typing import Iterable
from urllib import error, request


LOGGER = logging.getLogger(__name__)


class OllamaInferenceError(RuntimeError):
    pass


class OllamaVisionAnalyzer:
    def __init__(self, base_url: str, model_name: str, max_new_tokens: int = 512, timeout_sec: int = 1800, keep_alive: str = "30m", num_gpu: int | None = None, structured_output: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        self.timeout_sec = timeout_sec
        self.keep_alive = keep_alive
        self.num_gpu = num_gpu
        self.structured_output = structured_output

    def describe(
        self,
        prompt: str,
        frame_paths: Iterable[str],
        transcript_text: str = "",
        structured_context: str = "",
    ) -> str:
        frame_list = [frame_path for frame_path in frame_paths if Path(frame_path).exists()]
        images = [_encode_image(frame_path) for frame_path in frame_list]
        LOGGER.info(
            "Starting Ollama vision inference | model=%s | frames=%s | transcript_chars=%s | timeout_sec=%s",
            self.model_name,
            len(frame_list),
            len(transcript_text),
            self.timeout_sec,
        )
        options = {"num_predict": self.max_new_tokens}
        if self.num_gpu is not None:
            # Ollama accepts num_gpu as a request-scoped runner option. Zero
            # keeps this call off CUDA without changing the daemon globally.
            options["num_gpu"] = self.num_gpu
        payload = {
            "model": self.model_name,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": f"{prompt}\n\nTranscript:\n{transcript_text}\n\nContext:\n{structured_context}",
                    "images": images,
                }
            ],
            "options": options,
            "keep_alive": self.keep_alive,
            "_timeout_sec": self.timeout_sec,
        }
        if self.structured_output:
            # Budget the final evidence JSON rather than reasoning tokens.
            # Opt-in keeps existing unstructured video analysis unchanged.
            payload["format"] = "json"
            payload["think"] = False
        try:
            response = _post_json(f"{self.base_url}/api/chat", payload)
            message = response.get("message", {})
            content = str(message.get("content", "")).strip()
            if not content and not self.structured_output:
                content = str(message.get("thinking", "")).strip()
            LOGGER.info(
                "Completed Ollama vision inference | model=%s | frames=%s | output_chars=%s",
                self.model_name,
                len(frame_list),
                len(content),
            )
            if not content:
                raise OllamaInferenceError(f"Ollama model {self.model_name} returned an empty vision response")
            return content
        except (TimeoutError, socket.timeout) as exc:
            raise OllamaInferenceError(f"Ollama vision inference timed out after {self.timeout_sec}s") from exc
        except error.HTTPError as exc:
            raise OllamaInferenceError(f"Ollama vision request failed with HTTP {exc.code}: {exc.reason}") from exc
        except error.URLError as exc:
            raise OllamaInferenceError(f"Ollama is unreachable: {exc.reason}") from exc
        except OllamaInferenceError:
            raise
        except Exception as exc:
            raise OllamaInferenceError(f"Ollama vision inference failed: {exc}") from exc


class OllamaTextGenerator:
    def __init__(self, base_url: str, model_name: str, max_new_tokens: int = 512, timeout_sec: int = 1800, keep_alive: str = "30m") -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        self.timeout_sec = timeout_sec
        self.keep_alive = keep_alive

    def generate(self, prompt: str, transcript_text: str = "", structured_context: str = "") -> str:
        LOGGER.info(
            "Starting Ollama text generation | model=%s | transcript_chars=%s | context_chars=%s | timeout_sec=%s",
            self.model_name,
            len(transcript_text),
            len(structured_context),
            self.timeout_sec,
        )
        payload = {
            "model": self.model_name,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": f"{prompt}\n\nTranscript:\n{transcript_text}\n\nContext:\n{structured_context}",
                }
            ],
            "options": {"num_predict": self.max_new_tokens},
            "keep_alive": self.keep_alive,
            "_timeout_sec": self.timeout_sec,
        }
        try:
            response = _post_json(f"{self.base_url}/api/chat", payload)
            message = response.get("message", {})
            content = str(message.get("content", "")).strip() or str(message.get("thinking", "")).strip()
            LOGGER.info("Completed Ollama text generation | model=%s | output_chars=%s", self.model_name, len(content))
            if not content:
                raise OllamaInferenceError(f"Ollama model {self.model_name} returned an empty text response")
            return content
        except (TimeoutError, socket.timeout) as exc:
            raise OllamaInferenceError(f"Ollama text generation timed out after {self.timeout_sec}s") from exc
        except error.HTTPError as exc:
            raise OllamaInferenceError(f"Ollama text request failed with HTTP {exc.code}: {exc.reason}") from exc
        except error.URLError as exc:
            raise OllamaInferenceError(f"Ollama is unreachable: {exc.reason}") from exc
        except OllamaInferenceError:
            raise
        except Exception as exc:
            raise OllamaInferenceError(f"Ollama text inference failed: {exc}") from exc


def _encode_image(frame_path: str) -> str:
    return base64.b64encode(Path(frame_path).read_bytes()).decode("ascii")


def _post_json(url: str, payload: dict) -> dict:
    timeout_sec = int(payload.pop("_timeout_sec", 1800)) if "_timeout_sec" in payload else 1800
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def configure_ollama_runtime(max_loaded_models: int, num_parallel: int, keep_alive: str = "30m") -> None:
    os.environ.setdefault("OLLAMA_MAX_LOADED_MODELS", str(max_loaded_models))
    os.environ.setdefault("OLLAMA_NUM_PARALLEL", str(num_parallel))
    os.environ.setdefault("VIDEO_SUMMARIZER_OLLAMA_KEEP_ALIVE", keep_alive)


def probe_ollama_model(base_url: str, model_name: str, timeout_sec: int = 30) -> dict[str, object]:
    try:
        tags = _get_json(f"{base_url.rstrip('/')}/api/tags", timeout_sec)
        installed = {str(row.get("name", "")) for row in tags.get("models", []) if isinstance(row, dict)}
        if model_name not in installed:
            return {"ready": False, "model": model_name, "installed": sorted(installed), "error": f"Ollama model {model_name} is not installed"}
        details = _post_json(f"{base_url.rstrip('/')}/api/show", {"model": model_name, "_timeout_sec": timeout_sec})
        capabilities = [str(value).lower() for value in details.get("capabilities", [])]
        if capabilities and "vision" not in capabilities:
            return {"ready": False, "model": model_name, "capabilities": capabilities, "error": f"Ollama model {model_name} does not advertise vision capability"}
        response = _post_json(f"{base_url.rstrip('/')}/api/chat", {
            "model": model_name, "stream": False,
            "messages": [{"role": "user", "content": "Reply with READY only."}],
            "options": {"num_predict": 8}, "keep_alive": os.environ.get("VIDEO_SUMMARIZER_OLLAMA_KEEP_ALIVE", "30m"),
            "_timeout_sec": timeout_sec,
        })
        message = response.get("message", {})
        content = str(message.get("content", "")).strip()
        # Qwen reasoning builds can emit the short answer in ``thinking``
        # while leaving message.content empty.  That still proves the model
        # is responsive and should not fail preflight.
        if not content:
            content = str(message.get("thinking", "")).strip()
        if not content:
            return {"ready": False, "model": model_name, "error": "Ollama returned an empty model probe response"}
        return {"ready": True, "model": model_name, "capabilities": capabilities, "error": None}
    except Exception as exc:
        return {"ready": False, "model": model_name, "error": f"Ollama model probe failed: {exc}"}


def _get_json(url: str, timeout_sec: int) -> dict:
    with request.urlopen(url, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))
