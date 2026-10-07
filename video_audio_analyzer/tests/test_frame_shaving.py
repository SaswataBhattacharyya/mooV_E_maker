from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from video_audio_analyzer import pipeline
from video_audio_analyzer.pipeline import AnalyzerOptions, _frame_pair_change, _select_scene_frames


def test_adaptive_frame_shaving_keeps_scene_anchors_and_change_points():
    samples = [(index * 0.25, object(), 0.0) for index in range(20)]
    samples[7] = (samples[7][0], samples[7][1], 0.32)
    samples[14] = (samples[14][0], samples[14][1], 0.24)
    kept = _select_scene_frames(samples, AnalyzerOptions(adaptive_sampling=True, frame_change_threshold=0.2))
    assert kept[0][0] == samples[0][0]
    assert kept[-1][0] == samples[-1][0]
    assert samples[7] in kept and samples[14] in kept
    assert len(kept) < len(samples)


def test_disabling_frame_shaving_retains_all_sampled_frames():
    samples = [(index * 0.25, object(), 0.0) for index in range(12)]
    kept = _select_scene_frames(samples, AnalyzerOptions(adaptive_sampling=False))
    assert len(kept) == len(samples)


def test_frame_shaving_threshold_and_anchor_toggle_are_respected():
    samples = [(index * 0.5, object(), 0.0) for index in range(8)]
    samples[3] = (samples[3][0], samples[3][1], 0.3)
    kept = _select_scene_frames(samples, AnalyzerOptions(
        adaptive_sampling=True, frame_change_threshold=0.4, preserve_scene_anchors=False))
    assert len(kept) == 1
    assert kept[0][0] == samples[4][0]  # stable midpoint fallback when no sample clears threshold


def test_motion_compensation_reduces_global_pan_noise_and_reports_camera_motion():
    previous = np.zeros((90, 160), dtype=np.uint8)
    cv2.rectangle(previous, (20, 20), (70, 60), 180, -1)
    cv2.circle(previous, (110, 40), 12, 255, -1)
    warp = np.asarray([[1.0, 0.0, 7.0], [0.0, 1.0, 3.0]], dtype=np.float32)
    current = cv2.warpAffine(previous, warp, (160, 90), borderMode=cv2.BORDER_REPLICATE)
    raw_change = float(cv2.absdiff(previous, current).mean() / 255.0)
    compensated_change, camera_motion = _frame_pair_change(previous, current)
    assert camera_motion > 0.0
    assert compensated_change < raw_change


def test_hard_cut_falls_back_to_visual_change_not_camera_motion():
    previous = np.zeros((90, 160), dtype=np.uint8)
    current = np.full((90, 160), 255, dtype=np.uint8)
    change, camera_motion = _frame_pair_change(previous, current)
    assert change > 0.9
    assert camera_motion == 0.0


def test_audio_output_toggles_do_not_disable_model_analysis_wav(tmp_path):
    commands = []

    def fake_run(command):
        commands.append(command)
        Path(command[-1]).write_bytes(b"fixture")

    with patch.object(pipeline, "_run", side_effect=fake_run):
        result = pipeline._extract_audio(Path("dummy.mp4"), tmp_path / "audio", AnalyzerOptions(
            extract_source_audio=False, extract_preview_mp3=False))
    assert result["analysis_wav"].endswith("analysis.wav")
    assert result["source_audio"] is None
    assert result["preview_mp3"] is None
    assert len(commands) == 1
