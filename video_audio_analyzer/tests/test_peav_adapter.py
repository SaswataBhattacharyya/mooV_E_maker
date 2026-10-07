from contextlib import nullcontext
from types import SimpleNamespace

from video_audio_analyzer.peav_adapter import PEAVAdapter


class _Tensor:
    def detach(self):
        return self

    def float(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return [[0.25, 0.75]]


class _Torch:
    bfloat16 = object()

    @staticmethod
    def inference_mode():
        return nullcontext()

    @staticmethod
    def autocast(*_args, **_kwargs):
        return nullcontext()


class _Processor:
    def __call__(self, **kwargs):
        if kwargs.get("audio"):
            return _Batch(input_values="audio-values", padding_mask="audio-mask")
        return _Batch(pixel_values_videos="video-values", padding_mask_videos="video-mask")


class _Batch(dict):
    def to(self, _device):
        return self


class _Model:
    def get_audio_embeds(self, values, mask):
        assert (values, mask) == ("audio-values", "audio-mask")
        return _Tensor()

    def get_video_embeds(self, values, mask):
        assert (values, mask) == ("video-values", "video-mask")
        return _Tensor()

    def __call__(self, **_kwargs):  # pragma: no cover - single-modal paths must bypass forward
        raise AssertionError("single-modality PE-AV encoding must call its modality projection")


def _adapter():
    adapter = object.__new__(PEAVAdapter)
    adapter.torch = _Torch
    adapter.device = SimpleNamespace(type="cpu")
    adapter._hf_format = True
    adapter.model = _Model()
    adapter.transform = _Processor()
    return adapter


def test_hf_audio_only_uses_audio_projection_helper():
    output = _adapter().embed(audio="event.wav")
    assert output["audio_embeds"] == [[0.25, 0.75]]
    assert output["video_embeds"] is None


def test_hf_video_only_uses_video_projection_helper():
    output = _adapter().embed(video="scene.mp4")
    assert output["video_embeds"] == [[0.25, 0.75]]
    assert output["audio_embeds"] is None
