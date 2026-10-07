"""Compatibility shim for Facebook denoiser on modern torchaudio.

Torchaudio 2.9+ removed ``torchaudio.info``.  The vendored denoiser only uses
its basic stream metadata, which SoundFile can provide without changing the
vendored source tree.
"""

from types import SimpleNamespace

import soundfile
import torch
import torchaudio


if not hasattr(torchaudio, "info"):
    def _info(path):
        data = soundfile.info(str(path))
        return SimpleNamespace(
            sample_rate=data.samplerate,
            num_frames=data.frames,
            num_channels=data.channels,
            bits_per_sample=0,
            encoding=data.subtype,
        )

    torchaudio.info = _info

if not hasattr(torchaudio, "get_audio_backend"):
    torchaudio.get_audio_backend = lambda: "soundfile"


def _load(path, frame_offset=0, num_frames=-1, **_kwargs):
    data, sample_rate = soundfile.read(
        str(path), start=frame_offset,
        frames=num_frames if num_frames and num_frames > 0 else -1,
        dtype="float32", always_2d=True,
    )
    return torch.from_numpy(data.T.copy()), sample_rate


def _save(path, waveform, sample_rate, **_kwargs):
    data = waveform.detach().cpu().numpy()
    soundfile.write(str(path), data.T, sample_rate)


torchaudio.load = _load
torchaudio.save = _save
