"""Review must consume real selected reference provenance, not prompt assertions."""
import hashlib
from types import SimpleNamespace
import pytest
from story_builder.api import main as api

@pytest.mark.parametrize('mutation', ['none', 'bytes', 'task_hash', 'review_hash', 'review_asset', 'unreviewed'])
def test_selected_reference_evidence_checks_all_provenance(tmp_path, monkeypatch, mutation):
    image = tmp_path / 'master.png'; image.write_bytes(b'original pixels')
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    asset = {'sha256': digest, 'metadata': {'production_image_job': {'job_id': 'image-job',
        'settings': {'review_identity': {'display_name': 'Arun'}}}}}
    review = {'asset_id': 'master', 'resolution_status': 'accepted', 'decision': {'action': 'accept',
        'image_sha256': digest, 'evidence': {'evidence_valid': True, 'summary': 'Olive jacket.'}}}
    fingerprints = {'master': digest}
    if mutation == 'bytes': image.write_bytes(b'changed pixels')
    if mutation == 'task_hash': fingerprints['master'] = '0' * 64
    if mutation == 'review_hash': review['decision']['image_sha256'] = '0' * 64
    if mutation == 'review_asset': review['asset_id'] = 'other'
    if mutation == 'unreviewed': review = None
    monkeypatch.setattr(api, 'get_production_asset_record', lambda *args: asset)
    monkeypatch.setattr(api, 'resolve_production_asset_content', lambda *args: (image, 'image/png', 'master.png'))
    monkeypatch.setattr(api, 'ProductionImageJobStore', lambda *args: SimpleNamespace(get_director_review=lambda **kwargs: review))
    monkeypatch.setattr(api, '_production_stage_task_store', lambda: SimpleNamespace(get=lambda **kwargs: {'request': {'asset_fingerprints': fingerprints}}))
    take = {'project_id': 'p', 'run_id': 'r', 'input_snapshot': {'prompt_preparation_task_id': 'task',
        'validation_request': {'images': [{'asset_id': 'master', 'role': 'character_master', 'intent': 'appearance'}]}}}
    if mutation in {'bytes', 'task_hash', 'review_hash', 'review_asset'}:
        with pytest.raises(ValueError, match='(bytes|review)'):
            api._production_v2_reference_review_evidence(take)
    else:
        result = api._production_v2_reference_review_evidence(take)
        assert result[0]['sha256'] == digest
        assert result[0]['observed_features'] == (review['decision']['evidence'] if review else None)

@pytest.mark.parametrize('refresh', [False, True])
def test_normal_worker_consumes_durable_human_audio_evidence(monkeypatch, refresh):
    prior = {'video_sha256':'a'*64}; confirmation = {'statement':'Maya’s line is clear'}
    monkeypatch.setattr(api, '_production_v2_ledger', lambda: SimpleNamespace(
        human_audio_review_evidence=lambda **kwargs: {'archived_review':{'decision':prior},'verification':confirmation,'refresh_visual_evidence':refresh}))
    monkeypatch.setattr(api, '_production_v2_reference_review_evidence', lambda take: [])
    seen = {}
    monkeypatch.setattr(api, 'review_video_take', lambda **kwargs: seen.update(kwargs) or {'action':'blocked'})
    api._review_production_v2_take({'project_id':'p','run_id':'r','job_id':'j'}, {'video_path':'/tmp/real.mp4','config':{}})
    assert seen['prior_review'] == prior and seen['audio_verification'] == confirmation

    assert seen.get('refresh_visual_evidence', False) is refresh
