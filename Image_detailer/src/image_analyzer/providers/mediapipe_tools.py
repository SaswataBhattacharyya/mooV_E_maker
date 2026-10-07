from __future__ import annotations

from pathlib import Path

from image_analyzer.providers.base import OptionalProvider, ProviderArtifact


class MediaPipePeopleProvider(OptionalProvider):
    name = "mediapipe"

    def analyze(self, image_path: Path, context: dict[str, object]) -> ProviderArtifact:
        try:
            import mediapipe as mp  # type: ignore
            from mediapipe.tasks import python  # type: ignore
            from mediapipe.tasks.python import vision  # type: ignore
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"MediaPipe unavailable: {exc}"])

        warnings: list[str] = []
        data: dict[str, object] = {}
        try:
            base_options = python.BaseOptions()
            image = mp.Image.create_from_file(str(image_path))
        except Exception as exc:
            return ProviderArtifact(provider=self.name, warnings=[f"MediaPipe image load failed: {exc}"])

        for task_name, options_builder in {
            "pose": lambda: vision.PoseLandmarkerOptions(base_options=base_options, output_segmentation_masks=False),
            "face": lambda: vision.FaceLandmarkerOptions(base_options=base_options, output_face_blendshapes=True),
            "segmenter": lambda: vision.ImageSegmenterOptions(base_options=base_options, output_category_mask=True),
        }.items():
            try:
                with _build_task(task_name, options_builder()) as task:
                    result = task.detect(image)
                data[task_name] = _flatten_result(result)
            except Exception as exc:
                warnings.append(f"MediaPipe {task_name} failed: {exc}")
        return ProviderArtifact(provider=self.name, data=data, warnings=warnings)


def _build_task(task_name: str, options: object):
    from mediapipe.tasks.python import vision  # type: ignore

    if task_name == "pose":
        return vision.PoseLandmarker.create_from_options(options)
    if task_name == "face":
        return vision.FaceLandmarker.create_from_options(options)
    return vision.ImageSegmenter.create_from_options(options)


def _flatten_result(result: object) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key in dir(result):
        if key.startswith("_"):
            continue
        value = getattr(result, key)
        if callable(value):
            continue
        if isinstance(value, (str, int, float, bool, list, dict, tuple)) or value is None:
            payload[key] = value
        else:
            payload[key] = str(value)
    return payload

