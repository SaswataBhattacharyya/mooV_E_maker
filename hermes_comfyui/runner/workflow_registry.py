"""Allowlisted workflows and their stable input contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from request_schema import MediaRequest, RequestError


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class WorkflowSpec:
    workflow_id: str
    relative_path: str
    output_kind: str
    min_images: int = 0
    max_images: int = 0

    @property
    def path(self) -> Path:
        return REPO_ROOT / self.relative_path

    def validate(self, request: MediaRequest) -> None:
        image_count = len(request.input_images)
        if not self.min_images <= image_count <= self.max_images:
            expected = str(self.min_images) if self.min_images == self.max_images else f"{self.min_images}..{self.max_images}"
            raise RequestError(f"{self.workflow_id} requires {expected} input image(s); received {image_count}")
        if request.input_videos or request.input_audio:
            raise RequestError(f"{self.workflow_id} does not yet accept standalone video/audio references")


WORKFLOWS = {
    "z-image-turbo": WorkflowSpec("z-image-turbo", "workflows/api/gsl_starter_1_1_api.json", "image"),
    "qwen-image-2512": WorkflowSpec("qwen-image-2512", "workflows/api/qwen_2512_t2i_api.json", "image"),
    "qwen-image-edit-2511": WorkflowSpec("qwen-image-edit-2511", "workflows/api/qwen_edit_api.json", "image", 1, 3),
    "qwen-image-refine-2512": WorkflowSpec("qwen-image-refine-2512", "workflows/api/qwen_2512_t2i_refine_api.json", "image", 1, 2),
    "minimax-h3-t2v": WorkflowSpec("minimax-h3-t2v", "workflows/api/minimax_h3_t2v_api.json", "video"),
    "minimax-h3-i2v": WorkflowSpec("minimax-h3-i2v", "workflows/api/minimax_h3_i2v_api.json", "video", 1, 2),
    "minimax-h3-r2v": WorkflowSpec("minimax-h3-r2v", "workflows/api/minimax_h3_r2v_api.json", "video", 1, 3),
}


def get_spec(workflow_id: str) -> WorkflowSpec:
    try:
        return WORKFLOWS[workflow_id]
    except KeyError as exc:
        raise RequestError(f"Unknown workflow '{workflow_id}'. Allowed: {', '.join(sorted(WORKFLOWS))}") from exc
