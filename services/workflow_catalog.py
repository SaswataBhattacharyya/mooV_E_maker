"""Workflow discovery and UI-friendly input inference for the media composer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WORKFLOW_ROOT = Path(__file__).resolve().parent.parent / "workflows"
SUPPORTED_SUFFIXES = {".json"}
TEXT_NODE_TYPES = {"CLIPTextEncode", "TextEncodeQwenImageEditPlus", "Text Multiline", "PromptInput", "Note"}
IMAGE_NODE_TYPES = {"LoadImage"}
VIDEO_OUTPUT_NODE_TYPES = {"SaveVideo", "VHS_VideoCombine", "CreateVideo"}
IMAGE_OUTPUT_NODE_TYPES = {"SaveImage"}
AUDIO_HINTS = ("audio", "tts", "foley", "srt", "voice", "music")
VIDEO_HINTS = ("video", "ltx", "wan", "animate", "film", "vfx")
IMAGE_HINTS = ("image", "qwen", "ipadapter", "controlnet")


@dataclass(frozen=True)
class WorkflowField:
    key: str
    label: str
    kind: str
    required: bool
    multiple: bool = False
    description: str = ""
    default: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "required": self.required,
            "multiple": self.multiple,
            "description": self.description,
            "default": self.default,
        }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative_id(path: Path) -> str:
    return str(path.relative_to(WORKFLOW_ROOT)).replace("\\", "/")


def _normalise_nodes(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return a common node map for API and ComfyUI UI workflow exports.

    UI exports contain top-level metadata and a ``nodes`` list, while API
    exports are already keyed by node id.  Catalog discovery must understand
    both without treating metadata strings as nodes.
    """
    if isinstance(data.get("nodes"), list):
        result: dict[str, dict[str, Any]] = {}
        for index, node in enumerate(data["nodes"]):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", index))
            widgets = node.get("widgets_values", [])
            inputs: dict[str, Any] = {}
            if isinstance(widgets, list):
                inputs["widgets_values"] = widgets
            result[node_id] = {
                "class_type": str(node.get("type", "")),
                "inputs": inputs,
            }
        return result
    return {
        str(node_id): node
        for node_id, node in data.items()
        if isinstance(node, dict) and ("class_type" in node or "inputs" in node)
    }


def _guess_category(workflow_id: str, data: dict[str, Any]) -> str:
    nodes = _normalise_nodes(data)
    joined = f"{workflow_id} {' '.join(str(node.get('class_type', '')) for node in nodes.values())}".lower()
    if any(token in joined for token in AUDIO_HINTS):
        return "audio"
    if any(token in joined for token in VIDEO_HINTS):
        return "video"
    if any(token in joined for token in IMAGE_HINTS):
        return "image"
    return "utility"


def _output_type(data: dict[str, Any], category: str) -> str:
    classes = {node.get("class_type", "") for node in _normalise_nodes(data).values()}
    if classes & VIDEO_OUTPUT_NODE_TYPES:
        return "video"
    if classes & IMAGE_OUTPUT_NODE_TYPES:
        return "image"
    if category == "audio":
        return "audio"
    return category


def _infer_text_fields(data: dict[str, Any]) -> list[WorkflowField]:
    fields: list[WorkflowField] = []
    positive_added = False
    negative_added = False
    for node in _normalise_nodes(data).values():
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if class_type not in TEXT_NODE_TYPES:
            continue
        text_value = inputs.get("text")
        prompt_value = inputs.get("prompt")
        if isinstance(text_value, str):
            is_negative = any(token in text_value.lower() for token in ("low quality", "deformed", "bad", "ugly"))
            if is_negative and not negative_added:
                fields.append(
                    WorkflowField(
                        key="negative_prompt",
                        label="Negative Prompt",
                        kind="text",
                        required=False,
                        description="Used for exclusions and quality constraints.",
                        default=text_value,
                    )
                )
                negative_added = True
            elif not positive_added:
                fields.append(
                    WorkflowField(
                        key="prompt",
                        label="Prompt",
                        kind="text",
                        required=True,
                        description="Primary generation prompt.",
                        default=text_value,
                    )
                )
                positive_added = True
        if isinstance(prompt_value, str) and not positive_added:
            fields.append(
                WorkflowField(
                    key="prompt",
                    label="Prompt",
                    kind="text",
                    required=True,
                    description="Primary generation prompt.",
                    default=prompt_value,
                )
            )
            positive_added = True
    return fields


def _infer_asset_fields(data: dict[str, Any], category: str) -> list[WorkflowField]:
    fields: list[WorkflowField] = []
    load_images = sum(1 for node in _normalise_nodes(data).values() if node.get("class_type") in IMAGE_NODE_TYPES)
    if load_images == 1:
        kind = "image"
        label = "Reference Image"
        description = "Single image input."
        if category == "video":
            label = "Source Image"
            description = "Single frame used to drive the video workflow."
        fields.append(WorkflowField(key="images", label=label, kind=kind, required=True, multiple=False, description=description))
    elif load_images > 1:
        label = "Image Inputs"
        description = "Provide the images in workflow order."
        if category == "video":
            label = "Video Frame Inputs"
            description = "Usually start/end frames or multiple conditioning images."
        fields.append(WorkflowField(key="images", label=label, kind="image", required=True, multiple=True, description=description))
    if category == "audio":
        fields.append(
            WorkflowField(
                key="audio_notes",
                label="Audio Notes",
                kind="text",
                required=False,
                description="Speaker, timing, or style guidance for audio flows.",
            )
        )
    return fields


def _infer_parameter_fields(data: dict[str, Any], category: str) -> list[WorkflowField]:
    defaults: dict[str, Any] = {}
    for node in _normalise_nodes(data).values():
        inputs = node.get("inputs", {})
        for key in ("width", "height", "steps", "cfg", "seed", "length", "frame_rate"):
            if key in inputs and key not in defaults:
                defaults[key] = inputs[key]
    fields: list[WorkflowField] = []
    for key, label in (
        ("width", "Width"),
        ("height", "Height"),
        ("steps", "Steps"),
        ("cfg", "CFG"),
        ("seed", "Seed"),
        ("length", "Length"),
        ("frame_rate", "Frame Rate"),
    ):
        if key not in defaults:
            continue
        fields.append(
            WorkflowField(
                key=key,
                label=label,
                kind="number",
                required=False,
                default=defaults[key],
                description=f"Override the workflow's default {label.lower()}." if category else "",
            )
        )
    return fields


def _recommended_use_case(category: str, fields: list[WorkflowField]) -> str:
    if category == "video":
        if any(field.multiple for field in fields):
            return "Sequence or start/end-frame video generation."
        return "Text or single-image driven video generation."
    if category == "audio":
        return "Speech, subtitle timing, foley, or music generation."
    if any(field.kind == "image" for field in fields):
        return "Image editing or reference-guided generation."
    return "Text-first image generation."


def analyze_workflow(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    workflow_id = _relative_id(path)
    category = _guess_category(workflow_id, data)
    fields = _infer_text_fields(data) + _infer_asset_fields(data, category) + _infer_parameter_fields(data, category)
    api_format = path.parts[-2] == "api" or "/api/" in f"/{workflow_id}"
    ui_format = isinstance(data.get("nodes"), list)
    return {
        "id": workflow_id,
        "label": path.stem,
        "category": category,
        "source_path": str(path),
        "output_type": _output_type(data, category),
        "fields": [field.as_dict() for field in fields],
        "recommended_use_case": _recommended_use_case(category, fields),
        "supports_api_submission": api_format and not ui_format,
        "format": "ui" if ui_format else "api",
        "node_count": len(_normalise_nodes(data)),
    }


def load_workflow_catalog() -> list[dict[str, Any]]:
    workflows: list[dict[str, Any]] = []
    for path in sorted(WORKFLOW_ROOT.rglob("*")):
        if path.suffix.lower() not in SUPPORTED_SUFFIXES or not path.is_file():
            continue
        try:
            workflows.append(analyze_workflow(path))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return workflows


def get_workflow_definition(workflow_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    workflow_path = WORKFLOW_ROOT / workflow_id
    if not workflow_path.exists():
        raise FileNotFoundError(workflow_id)
    return analyze_workflow(workflow_path), _read_json(workflow_path)
