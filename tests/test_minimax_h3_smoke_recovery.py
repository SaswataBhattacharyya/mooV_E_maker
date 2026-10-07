import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import smoke_minimax_h3_dynamic as smoke
from story_builder.services.media_jobs import MediaJobError


def setup_smoke(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, 'ROOT', tmp_path)
    fixture = tmp_path / 'voice.wav'
    fixture.write_bytes(b'fixture')
    monkeypatch.setattr(smoke, 'VOICE_FIXTURE', fixture)
    monkeypatch.setattr(smoke, 'comfyui_root', lambda: tmp_path / 'comfy')
    monkeypatch.setattr('sys.argv', ['smoke', '--preview', '--case', 'voice_only'])
    def request(path):
        if path == '/system_stats':
            return {'devices': [{'vram_free': 100 * 1024**3}], 'system': {}}
        if path == '/queue':
            return {'queue_running': [], 'queue_pending': []}
        return {path.rsplit('/', 1)[-1]: {}}
    monkeypatch.setattr(smoke, 'request_json', request)
    monkeypatch.setattr(smoke, 'validate_comfy_capabilities', lambda _: {})
    monkeypatch.setattr(smoke, 'load_base_graph', lambda: {})
    monkeypatch.setattr(smoke, 'verify_model_files', lambda *_: [])
    monkeypatch.setattr(smoke, 'stage_audio_reference', lambda *a, **k: SimpleNamespace(
        asset_id=k['asset_id'], filename='voice.wav', sha256='hash', duration_seconds=5))
    monkeypatch.setattr(smoke, 'compile_r2v_graph', lambda *_ , **k: SimpleNamespace(
        graph={}, reference_map=SimpleNamespace(as_dict=lambda: {}), width=864, height=480, frame_count=121))
    cleanup = []
    unload = []
    monkeypatch.setattr(smoke, 'cleanup_owned_media', lambda *a, **k: cleanup.append(a[0]) or {'status': 'cleaned'})
    monkeypatch.setattr('story_builder.services.media_jobs.release_comfyui_models_if_idle', lambda **k: unload.append(True) or {'status': 'requested'})
    def manifest():
        return json.loads(next(tmp_path.glob('output/*/runs/*/manifest.json')).read_text())
    return manifest, cleanup, unload


@pytest.mark.parametrize('failure', ['timeout', 'interrupt'])
def test_smoke_reserves_prompt_before_wait_and_retains_live_inputs(monkeypatch, tmp_path, failure):
    manifest, cleanup, unload = setup_smoke(monkeypatch, tmp_path)
    observed = []
    def submit(graph, **kwargs):
        state = manifest()
        observed.append(state)
        assert state.get('comfy_prompt_id'), 'Prompt ID must be durable before submitting or waiting'
        assert kwargs.get('prompt_id') == state['comfy_prompt_id']
        if failure == 'interrupt':
            raise KeyboardInterrupt
        raise MediaJobError('timeout', prompt_id=state['comfy_prompt_id'], remote_state_unknown=True)
    monkeypatch.setattr(smoke, 'submit_and_wait', submit)
    assert smoke.main() == (130 if failure == 'interrupt' else 1)
    assert observed[0].get('comfy_prompt_id')
    assert manifest()['status'] == 'recovery_pending'
    assert cleanup == []
    assert unload == []


def test_smoke_preflight_failure_never_requests_global_unload(monkeypatch, tmp_path):
    manifest, cleanup, unload = setup_smoke(monkeypatch, tmp_path)
    def offline(path):
        raise RuntimeError('sandbox network unavailable')
    monkeypatch.setattr(smoke, 'request_json', offline)
    assert smoke.main() == 1
    assert manifest()['status'] == 'failed'
    assert unload == []


def test_smoke_known_rejection_cleans_only_its_staging(monkeypatch, tmp_path):
    manifest, cleanup, unload = setup_smoke(monkeypatch, tmp_path)
    def reject(*a, **k):
        raise MediaJobError('ComfyUI rejected workflow')
    monkeypatch.setattr(smoke, 'submit_and_wait', reject)
    assert smoke.main() == 1
    assert manifest()['status'] == 'failed'
    assert len(cleanup) == 1
    assert unload == []


def test_smoke_completed_render_keeps_output_and_cleans_owned_inputs(monkeypatch, tmp_path):
    manifest, cleanup, unload = setup_smoke(monkeypatch, tmp_path)
    def complete(graph, **kwargs):
        state = manifest()
        assert state['comfy_prompt_id'] == kwargs['prompt_id']
        return kwargs['prompt_id'], {'outputs': {}}
    def outputs(history, *, destination_dir, comfy_url):
        destination_dir.mkdir(parents=True)
        (destination_dir / 'result.mp4').write_bytes(b'verified output')
        return [{'kind': 'video', 'relative_path': 'result.mp4'}]
    monkeypatch.setattr(smoke, 'submit_and_wait', complete)
    monkeypatch.setattr(smoke, 'collect_outputs', outputs)
    monkeypatch.setattr(smoke, 'probe_media', lambda _: SimpleNamespace(
        duration_seconds=5, width=864, height=480, frame_rate=24, has_audio=True, audio_codec='aac'))
    assert smoke.main() == 0
    state = manifest()
    assert state['status'] == 'completed'
    assert Path(state['outputs'][0]['absolute_path']).read_bytes() == b'verified output'
    assert len(cleanup) == 1
    assert unload == []


def test_recovery_uses_saved_id_after_restart_before_response(monkeypatch, tmp_path):
    from scripts import recover_minimax_h3_smoke as recover
    monkeypatch.setattr(recover, 'ROOT', tmp_path)
    path = tmp_path / 'output' / recover.PROJECT_ID / 'runs' / 'run-1' / 'manifest.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'run_id': 'run-1', 'status': 'submitting', 'comfy_prompt_id': 'reserved-id'}))
    monkeypatch.setattr('sys.argv', ['recover', '--run-id', 'run-1', '--timeout-seconds', '1'])
    # Recovery now samples telemetry on its own clock; provide all loop ticks
    # and keep this test independent from the physical GPU.
    clock = iter([0, 0, 0, 0, 2])
    monkeypatch.setattr(recover.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(recover.time, 'sleep', lambda _: None)
    monkeypatch.setattr(recover, 'inspect_gpu_runtime', lambda **_: {
        'gpu': {'temperature_c': 45, 'graphics_clock_mhz': 300},
        'comfyui': {'free_bytes': 100 * 1024**3}})
    calls = []
    monkeypatch.setattr(recover, 'request_json', lambda url, **k: calls.append(url) or {})
    assert recover.main() == 2
    assert calls == [recover.COMFY_URL + '/history/reserved-id']
    assert json.loads(path.read_text())['status'] == 'recovery_pending'


def test_recovery_refuses_to_replace_saved_prompt_id(monkeypatch, tmp_path):
    from scripts import recover_minimax_h3_smoke as recover
    monkeypatch.setattr(recover, 'ROOT', tmp_path)
    path = tmp_path / 'output' / recover.PROJECT_ID / 'runs' / 'run-1' / 'manifest.json'
    path.parent.mkdir(parents=True)
    original = {'run_id': 'run-1', 'status': 'submitting', 'comfy_prompt_id': 'reserved-id'}
    path.write_text(json.dumps(original))
    monkeypatch.setattr('sys.argv', ['recover', '--run-id', 'run-1', '--prompt-id', 'unrelated-id'])
    with pytest.raises(SystemExit, match='different from the saved run'):
        recover.main()
    assert json.loads(path.read_text()) == original
