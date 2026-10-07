from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
import json
import threading
import time
import uuid
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image
import pytest

from story_builder.services import production_assets as assets
from story_builder.services import gpu_watchdog, music_sound, control_foley, audio_tts
from story_builder.services.media_jobs import MediaJobError
from story_builder.services.production_route_assets import enforce_route_assets, RouteAssetError
from story_builder.services.production_audio_sidecars import AudioSidecarStore, SidecarConflict
from story_builder.services.production_authority import director_controls


def png(color):
    stream = BytesIO()
    Image.new("RGB", (7, 5), color=color).save(stream, format="PNG")
    return stream.getvalue()


def test_real_candidate_acceptance_satisfies_route(tmp_path):
    path = tmp_path / "output" / "p" / "a.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(png("red"))
    record = assets.register_output(tmp_path / "projects", tmp_path / "output", "p",
        relative_path="a.png", role="image_candidate",
        metadata={"production_image_job": {"status": "completed", "job_id": "j"}})
    accepted = assets.accept_image_candidate(tmp_path / "projects", "p", record["asset_id"], role="character_master")
    assert accepted["metadata"]["approval_status"] == "accepted"
    assets.assign_master_identity(tmp_path / "projects", "p", record["asset_id"], role="character_master", entity_id="c")
    assert enforce_route_assets(route="reference_built", shot_content={"characters": ["c"]},
        selected_images=[{"asset_id": record["asset_id"], "role": "character_master"}],
        get_asset=lambda aid: assets.get_asset_record(tmp_path / "projects", "p", aid))["satisfied"]


def test_registry_concurrent_writes_preserve_all_assets(tmp_path):
    barrier = threading.Barrier(8)
    def register(index):
        barrier.wait(timeout=5)
        return assets.register_upload(tmp_path, "p", filename=f"{index}.png", content=png((index, 0, 0)), role="character_master")
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(register, range(8)))
    assert assets.list_assets(tmp_path, "p")["total"] == 8
    assert len({row["asset_id"] for row in records}) == 8


def test_identical_output_bytes_keep_independent_attempt_provenance(tmp_path):
    output = tmp_path / "output" / "p"
    output.mkdir(parents=True)
    (output / "one.png").write_bytes(png("blue"))
    (output / "two.png").write_bytes(png("blue"))
    one = assets.register_output(tmp_path / "projects", output.parent, "p", relative_path="one.png", role="image_candidate", metadata={"job_id": "one"})
    two = assets.register_output(tmp_path / "projects", output.parent, "p", relative_path="two.png", role="image_candidate", metadata={"job_id": "two"})
    assert one["asset_id"] != two["asset_id"]
    assert two["metadata"] == {"job_id": "two"} and two["deduplicated"]
    assert assets.resolve_content(tmp_path / "projects", output.parent, "p", one["asset_id"])[0] == assets.resolve_content(tmp_path / "projects", output.parent, "p", two["asset_id"])[0]


@pytest.mark.parametrize("refs,record,code", [
    ([{"asset_id": "a", "role": "character_master"}]*2, {"kind": "image", "roles": ["character_master"]}, "duplicate_master_asset"),
    ([{"asset_id": "a", "role": "character_master"}], {"kind": "video", "roles": ["world_master"]}, "asset_role_mismatch"),
    ([{"asset_id": "a", "role": "character_master"}], {"kind": "image", "roles": ["character_master"], "metadata": {"character_id": "other"}}, "master_identity_mismatch"),
])
def test_route_does_not_trust_client_role_counts(refs, record, code):
    with pytest.raises(RouteAssetError) as error:
        enforce_route_assets(route="hybrid", shot_content={"characters": ["c", "d"], "asset_requirements": [{"role": "character_master", "count": 2}]}, selected_images=refs, get_asset=lambda _: record)
    assert error.value.code == code


@pytest.mark.parametrize("gate", ["story_review", "voice_selection", "image_candidate_selection", "shot_workflow_render_approval"])
def test_semi_authority_is_independent_per_gate(gate):
    assert not director_controls({"control_mode": "semi"}, gate)
    assert director_controls({"control_mode": "semi", "semi_gates": {gate: False}}, gate)
    assert not director_controls({"control_mode": "manual", "semi_gates": {gate: False}}, gate)
    assert director_controls({"control_mode": "fully_automated"}, gate)


def test_watchdog_samples_while_history_http_is_blocked(tmp_path):
    stopped = threading.Event()
    blocked = threading.Event()
    release = threading.Event()
    reads = []
    def request(url, **kwargs):
        blocked.set()
        release.wait(2)
        return {}
    def reader():
        reads.append(time.monotonic())
        if len(reads) >= 4:
            stopped.set()
        return {"temperature_c": 84, "graphics_clock_mhz": 2100}
    thread = threading.Thread(target=gpu_watchdog.supervise, args=("http://comfy", "owned", tmp_path / "state.json"), kwargs={"reader": reader, "request": request, "stop": stopped, "interval": .02})
    thread.start()
    assert blocked.wait(1)
    assert stopped.wait(1), "A blocked HTTP request prevented independent thermal sampling"
    release.set()
    thread.join(2)
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["tripped"] and len(reads) >= 4


@pytest.mark.parametrize("module", [music_sound, control_foley])
def test_audio_reserves_prompt_and_preserves_unknown_outcome(module, tmp_path, monkeypatch):
    snapshots = []
    job = {"job_id": "audio-job", "settings": {}, "outputs": [], "status": "queued"}
    builder = "build_ace_workflow" if module is music_sound else "build_workflow"
    monkeypatch.setattr(module, builder, lambda _: {})
    def submit(*args, **kwargs):
        assert snapshots[-1]["prompt_id"] == kwargs["prompt_id"]
        raise MediaJobError("response lost", prompt_id=kwargs["prompt_id"], remote_state_unknown=True)
    monkeypatch.setattr(module, "submit_and_wait", submit)
    run = module.run_music_job if module is music_sound else module.run_job
    result = run(job, project_dir=tmp_path / "p", output_root=tmp_path / "output", comfy_url="http://comfy", progress=lambda row: snapshots.append(deepcopy(row)))
    assert result["status"] == "recovery_required" and uuid.UUID(result["prompt_id"])
    monkeypatch.setattr(module, "submit_and_wait", lambda *a, **k: pytest.fail("Known prompt was resubmitted"))
    run(result, project_dir=tmp_path / "p", output_root=tmp_path / "output", comfy_url="http://comfy", progress=lambda _: None)


def test_audio_queue_idempotency_and_restart_preserve_exact_prompt(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    store = AudioSidecarStore(path)
    job = {"job_id": "j", "status": "queued"}
    one = store.enqueue("p", "r", "key", {"prompt": "wind"}, job)
    assert store.enqueue("p", "r", "key", {"prompt": "wind"}, {**job, "job_id": "duplicate"}) == one
    with pytest.raises(SidecarConflict):
        store.enqueue("p", "r", "key", {"prompt": "rain"}, job)
    one.update(status="submitting", prompt_id="reserved")
    store.save(one)
    assert AudioSidecarStore(path).unsettled()[0]["prompt_id"] == "reserved"
    with store.own("j") as owned:
        assert owned
        with AudioSidecarStore(path).own("j") as second:
            assert not second


def test_detached_watchdog_survives_spawner_exit_and_interrupts_owned_prompt(tmp_path):
    """Real process/HTTP lifecycle using a fake NVIDIA executable, never a GPU."""
    interrupted = threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            payload = {"queue_running": [[0, "owned"]], "queue_pending": []} if self.path == "/queue" else {}
            body = json.dumps(payload).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            if self.path == "/interrupt":
                interrupted.set()
            self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    values = tmp_path / "values"
    values.write_text("45, 300\n")
    executable = fake_bin / "nvidia-smi"
    executable.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nprint(Path({str(values)!r}).read_text(), end='')\n")
    executable.chmod(0o755)
    url = f"http://127.0.0.1:{server.server_port}"
    package_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    environment = {**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
                   "TMPDIR": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTHONPATH": package_root + os.pathsep + os.environ.get("PYTHONPATH", "")}
    code = "from story_builder.services.gpu_watchdog import ensure_prompt_watchdog; print(ensure_prompt_watchdog(comfy_url=" + repr(url) + ", prompt_id='owned').path)"
    state_path = None
    try:
        parent = subprocess.run([sys.executable, "-c", code], env=environment, text=True, capture_output=True, timeout=8, check=True)
        from pathlib import Path
        state_path = Path(parent.stdout.strip())
        next_values = values.with_suffix(".tmp")
        next_values.write_text("84, 2100\n")
        next_values.replace(values)
        assert interrupted.wait(6), "Detached supervision stopped when the spawning process exited"
        state = json.loads(state_path.read_text())
        assert state["tripped"] and state["gpu"]["temperature_c"] == 84
    finally:
        if state_path:
            state_path.with_suffix(".done").touch()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if json.loads(state_path.read_text()).get("remote_terminal"):
                    break
                time.sleep(.05)
        server.shutdown(); server.server_close()


@pytest.mark.parametrize("module", [music_sound, control_foley])
def test_production_sidecar_audio_has_one_permanent_home(module, tmp_path, monkeypatch):
    job = {"job_id": "sidecar", "settings": {}, "production_sidecar": True, "outputs": [], "status": "queued"}
    monkeypatch.setattr(module, "build_ace_workflow" if module is music_sound else "build_workflow", lambda _: {})
    monkeypatch.setattr(module, "submit_and_wait", lambda *args, **kwargs: (kwargs["prompt_id"], {}))
    def collect(history, *, destination_dir, **kwargs):
        destination_dir.mkdir(parents=True, exist_ok=True)
        (destination_dir / "sound.wav").write_bytes(b"audio bytes")
        return [{"kind": "audio", "filename": "sound.wav", "relative_path": "sound.wav"}]
    monkeypatch.setattr(module, "collect_outputs", collect)
    runner = module.run_music_job if module is music_sound else module.run_job
    result = runner(job, project_dir=tmp_path / "projects" / "p", output_root=tmp_path / "output", comfy_url="http://comfy", progress=lambda _: None)
    assert result["status"] == "completed"
    assert len(list(tmp_path.rglob("*.wav"))) == 1
    assert str(tmp_path / "output" / "p") in result["export_path"]


def test_timed_tts_preserves_ambiguous_prompt_identity(tmp_path, monkeypatch):
    snapshots = []
    monkeypatch.setattr(audio_tts, "validate_live_nodes", lambda *args: None)
    def submit(*args, **kwargs):
        assert snapshots[-1]["prompt_id"] == kwargs["prompt_id"]
        raise MediaJobError("lost reply", prompt_id=kwargs["prompt_id"], remote_state_unknown=True)
    monkeypatch.setattr(audio_tts, "submit_and_wait", submit)
    audio_tts.run_timed_job(project_id="p", project_dir=tmp_path / "p", output_root=tmp_path / "output",
        job={"job_id": "tts", "original_srt": "", "rewritten_srt": ""}, workflow={}, comfy_url="http://comfy",
        update=lambda changes: snapshots.append(changes))
    assert snapshots[-1]["status"] == "recovery_required" and snapshots[-1]["prompt_id"]


def test_reference_built_requires_explicit_identity_and_assignment_is_stable(tmp_path):
    record = assets.register_upload(tmp_path, "p", filename="master.png", content=png("red"), role="character_master")
    refs = [{"asset_id": record["asset_id"], "role": "character_master"}]
    resolve = lambda aid: assets.get_asset_record(tmp_path, "p", aid)
    with pytest.raises(RouteAssetError) as missing:
        enforce_route_assets(route="reference_built", shot_content={"characters": ["c"]}, selected_images=refs, get_asset=resolve)
    assert missing.value.code == "master_identity_required"
    assets.assign_master_identity(tmp_path, "p", record["asset_id"], role="character_master", entity_id="c")
    assert enforce_route_assets(route="reference_built", shot_content={"characters": ["c"]}, selected_images=refs, get_asset=resolve)["satisfied"]
    with pytest.raises(assets.ProductionAssetError) as changed:
        assets.assign_master_identity(tmp_path, "p", record["asset_id"], role="character_master", entity_id="other")
    assert changed.value.code == "master_identity_conflict"


@pytest.mark.parametrize("reading", ["nan, 2100", "45, inf", "-1, 2100"])
def test_gpu_operating_point_rejects_nonfinite_or_negative_readings(monkeypatch, reading):
    from story_builder.services import gpu_runtime
    monkeypatch.setattr(gpu_runtime, "_run", lambda *args, **kwargs: reading)
    with pytest.raises(gpu_runtime.GPUAdmissionError):
        gpu_runtime.read_gpu_operating_point()


def test_gpu_memory_reserve_is_admission_only_and_owned_render_remains_monitored(monkeypatch):
    from story_builder.services import gpu_runtime
    monkeypatch.setattr(gpu_runtime, "read_gpu_operating_point", lambda: {
        "temperature_c": 58.0, "graphics_clock_mhz": 2080.0})
    monkeypatch.setattr(gpu_runtime, "_run", lambda *_args, **_kwargs:
        "NVIDIA GB10, 58, 96, Not Active, Not Active")
    monkeypatch.setattr(gpu_runtime, "_json_url", lambda url: (
        {"devices": [{"name": "cuda:0 NVIDIA GB10", "vram_free": 6 * 1024**3}]}
        if url.endswith("/system_stats") else {"queue_running": [[0, "owned-prompt"]], "queue_pending": []}))
    monkeypatch.setattr(gpu_runtime, "_comfy_processes", lambda _url: {123: "python main.py"})
    monkeypatch.setattr(gpu_runtime, "_compute_processes", lambda: [{"pid": 123, "process_name": "python"}])
    monkeypatch.setattr(gpu_runtime, "_kernel_errors", lambda _since: [])

    with pytest.raises(gpu_runtime.GPUAdmissionError, match="20 GiB is required"):
        gpu_runtime.inspect_gpu_runtime(comfy_url="http://comfy")
    sample = gpu_runtime.inspect_gpu_runtime(comfy_url="http://comfy", expected_prompt_id="owned-prompt")
    assert sample["comfyui"]["running_prompt_ids"] == ["owned-prompt"]
    assert sample["comfyui"]["free_gib"] == 6.0


@pytest.mark.parametrize("point,expected", [
    ({"temperature_c": 83, "graphics_clock_mhz": 2100}, "cutoff"),
    ({"temperature_c": 45, "graphics_clock_mhz": 2101}, "clock exceeded"),
    (None, "telemetry unavailable"),
])
def test_watchdog_trips_on_each_operator_limit_and_missing_telemetry(tmp_path, point, expected):
    stopped = threading.Event()
    readings = []
    def reader():
        readings.append(True)
        if len(readings) == 3:
            stopped.set()
        if point is None:
            raise RuntimeError("offline")
        return point
    path = tmp_path / "watch.json"
    gpu_watchdog.supervise("http://comfy", "owned", path, reader=reader,
        request=lambda *a, **k: {}, stop=stopped, interval=.01)
    state = json.loads(path.read_text())
    assert state["tripped"] and expected in state["reason"]


@pytest.mark.parametrize("queue", [
    {"queue_running": [[0, "foreign"]], "queue_pending": []},
    {"queue_running": [[0, "owned"]], "queue_pending": [[1, "foreign"]]},
])
def test_watchdog_never_interrupts_foreign_or_pending_work(queue):
    calls = []
    def request(url, **kwargs):
        calls.append(url)
        return queue
    interrupted, detail = gpu_watchdog.interrupt_if_owned_prompt(comfy_url="http://comfy", prompt_id="owned", request_json=request)
    assert not interrupted and "Refused" in detail
    assert calls == ["http://comfy/queue"]
