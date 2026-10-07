from story_builder.services import gpu_runtime


def test_runtime_sample_persists_the_graphics_clock_used_by_admission(monkeypatch):
    monkeypatch.setattr(gpu_runtime, "read_gpu_operating_point", lambda: {
        "temperature_c": 51.0, "graphics_clock_mhz": 2075.0})
    monkeypatch.setattr(gpu_runtime, "_run", lambda *_a, **_k: "NVIDIA GB10, 51, 8, Not Active, Not Active\n")
    monkeypatch.setattr(gpu_runtime, "_json_url", lambda url: {
        "devices": [{"name": "cuda:0 NVIDIA GB10", "type": "cuda", "vram_free": 64 * 1024**3}]
    } if url.endswith("/system_stats") else {"queue_running": [], "queue_pending": []})
    monkeypatch.setattr(gpu_runtime, "_comfy_processes", lambda _url: {42: "python main.py --port 3008"})
    monkeypatch.setattr(gpu_runtime, "_compute_processes", lambda: [{"pid": 42, "process_name": "python", "used_memory_mib": 100}])
    monkeypatch.setattr(gpu_runtime, "_kernel_errors", lambda _since: [])

    result = gpu_runtime.inspect_gpu_runtime(comfy_url="http://comfy:3008")

    assert result["gpu"]["graphics_clock_mhz"] == 2075.0
