from story_builder.services.video_repertoire_worker import _GpuMemorySampler


def test_gpu_memory_report_separates_baseline_from_peak():
    sampler = _GpuMemorySampler(interval_seconds=1)
    sampler.samples[:] = [4200, 8700, 7600]
    report = sampler.report()
    assert report["available"] is True
    assert report["baseline_mib"] == 4200
    assert report["peak_mib"] == 8700
    assert report["peak_delta_mib"] == 4500
    assert report["sample_count"] == 3


def test_gpu_memory_report_explains_unavailable_telemetry():
    report = _GpuMemorySampler().report()
    assert report["available"] is False
    assert "nvidia-smi" in report["reason"]
