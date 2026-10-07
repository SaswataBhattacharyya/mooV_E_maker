from __future__ import annotations

import json
import subprocess
import pytest
from pathlib import Path

from story_builder.services.production_job_worker import ProductionJobWorker
from story_builder.services.production_ledger import LedgerConflict, ProductionLedger
from story_builder.services.production_video_director import review_video_take


def _completed_director_take(path: Path, images=None):
    ledger = ProductionLedger(path)
    run = ledger.create_run(project_id="p1", idempotency_key="run",
        config={"control_mode": "fully_automated", "provider": "codex",
            "director_profile": {"profile_version": "test", "review_priorities": []}})
    take = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
        idempotency_key="take", input_snapshot={"validation_request": {"prompt": "A river at dawn.", "images": images or []}})
    ledger.transition_take(project_id="p1", take_id="t1", status="submitting")
    prompt = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]
    ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=prompt)
    ledger.transition_take(project_id="p1", take_id="t1", status="collecting")
    ledger.set_take_outputs(project_id="p1", take_id="t1", outputs=[{
        "asset_id": "pa-0123456789abcdef", "kind": "video", "sha256": "a" * 64}])
    ledger.transition_take(project_id="p1", take_id="t1", status="needs_review")
    return ledger, run, take


def test_director_video_review_claim_persists_immutable_decision_and_survives_reopen(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger, run, take = _completed_director_take(path)
    manual = ledger.create_run(project_id="p1", idempotency_key="manual", config={"control_mode": "manual"})
    ledger.queue_take(project_id="p1", run_id=manual["run_id"], shot_id="s2", take_id="manual-take",
        idempotency_key="manual-take", input_snapshot={})
    owner = "review-worker-1"
    claimed = ledger.claim_next_director_video_review(owner_token=owner)
    assert claimed["job_id"] == take["job_id"]
    decision = {"schema_version": 1, "action": "accept", "confidence": .9,
        "reason": "All requirements are visible.", "criteria": [{"name": "requested scene", "passed": True,
            "evidence": "The river is visible in all sampled frames."}], "prompt_delta": ""}
    saved = ledger.record_director_video_review(take=claimed, decision=decision, owner_token=owner)
    ledger.release_director_video_review_claim(job_id=take["job_id"], owner_token=owner)

    reopened = ProductionLedger(path)
    pending = reopened.unresolved_director_video_reviews()
    assert pending[0]["decision"] == decision
    assert pending[0]["review_id"] == saved["review_id"]
    assert reopened.claim_next_director_video_review(owner_token="other") is None
    with __import__("pytest").raises(LedgerConflict, match="immutable"):
        reopened.record_director_video_review(take=claimed,
            decision={**decision, "reason": "changed"})
    resolver = reopened.claim_pending_director_video_review(job_id=take["job_id"], owner_token="resolver-1")
    assert resolver is not None
    assert reopened.claim_pending_director_video_review(job_id=take["job_id"], owner_token="resolver-2") is None
    assert reopened.get_run(project_id="p1", run_id=run["run_id"])["takes"][0]["director_review"]["resolution_status"] == "reviewing"
    reopened.release_director_video_review_claim(job_id=take["job_id"], owner_token="resolver-1")
    assert reopened.get_run(project_id="p1", run_id=run["run_id"])["takes"][0]["director_review"]["resolution_status"] == "review_recovery_pending"


def test_worker_replays_saved_video_decision_without_second_inference(tmp_path):
    ledger, run, take = _completed_director_take(tmp_path / "ledger.sqlite3")
    claimed = ledger.claim_next_director_video_review(owner_token="first")
    decision = {"schema_version": 1, "action": "accept", "confidence": .9,
        "reason": "Looks right.", "criteria": [{"name": "scene", "passed": True, "evidence": "River."}],
        "prompt_delta": ""}
    ledger.record_director_video_review(take=claimed, decision=decision, owner_token="first")
    ledger.release_director_video_review_claim(job_id=take["job_id"], owner_token="first")
    calls = []
    worker = ProductionJobWorker(ledger, comfy_url="http://unused", prepare=lambda _: None,
        collect=lambda *_: [], cleanup=lambda _: None, resolve_video_output=lambda _: Path("unused"),
        director_video_review=lambda *_: calls.append("inference"), enqueue_director_retake=lambda *_: {})

    result = worker.review_next_take()

    assert result["status"] == "accepted"
    assert calls == []
    state = ledger.get_run(project_id="p1", run_id=run["run_id"])
    assert state["takes"][0]["status"] == "accepted"
    assert state["takes"][0]["director_review"]["resolution_status"] == "accepted"
    assert any(event["payload"].get("actor") == "director_review" for event in state["events"])


def test_worker_keeps_saved_retake_decision_pending_until_fresh_preparation_completes(tmp_path):
    ledger, run, take = _completed_director_take(tmp_path / "ledger.sqlite3")
    inference_calls = []
    retake_calls = []

    def review(*_args):
        inference_calls.append(True)
        return {"schema_version": 1, "action": "retake", "confidence": .9,
            "reason": "Adjust framing.", "criteria": [{"name": "framing", "passed": False,
            "evidence": "The subject is too far left."}], "prompt_delta": "Keep the subject centered."}

    def enqueue(take_row, _decision):
        retake_calls.append(True)
        if len(retake_calls) == 1:
            return {"status": "preparing", "take_id": "retake-child",
                "prompt_preparation_task_id": "retake-prompt-task"}
        child = ledger.queue_take(project_id=take_row["project_id"], run_id=take_row["run_id"],
            shot_id=take_row["shot_id"], take_id="retake-child", idempotency_key="retake-key",
            input_snapshot={"prompt_preparation_task_id": "retake-prompt-task"})
        return child

    worker = ProductionJobWorker(ledger, comfy_url="http://unused", prepare=lambda _: None,
        collect=lambda *_: [], cleanup=lambda _: None, resolve_video_output=lambda _: Path("unused"),
        director_video_review=review, enqueue_director_retake=enqueue)
    first = worker.review_next_take()
    state = ledger.get_run(project_id="p1", run_id=run["run_id"])
    assert first["status"] == "preparing"
    assert state["takes"][0]["director_review"]["resolution_status"] == "review_recovery_pending"
    assert inference_calls == [True]

    restarted_ledger = ProductionLedger(ledger.path)
    restarted_worker = ProductionJobWorker(restarted_ledger, comfy_url="http://unused",
        prepare=lambda _: None, collect=lambda *_: [], cleanup=lambda _: None,
        resolve_video_output=lambda _: Path("unused"), director_video_review=review,
        enqueue_director_retake=enqueue)
    second = restarted_worker.review_next_take()
    state = restarted_ledger.get_run(project_id="p1", run_id=run["run_id"])
    assert second["status"] == "retake_queued"
    assert second["retake"]["take_id"] == "retake-child"
    assert state["takes"][0]["director_review"]["resolution_status"] == "retake_queued"
    assert state["takes"][0]["director_review"]["retake_take_id"] == "retake-child"
    assert inference_calls == [True]
    assert retake_calls == [True, True]


def test_video_review_extracts_three_frames_and_rejects_weak_acceptance(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake video bytes")
    analyzed = []
    vision_options = []

    def runner(args, **kwargs):
        if args[0] == "ffprobe":
            return subprocess.CompletedProcess(args, 0, stdout="10.0\n", stderr="")
        Path(args[-1]).write_bytes(b"png")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    def vision(path, **kwargs):
        analyzed.append(path.name)
        vision_options.append(kwargs)
        return {"analysis_valid": True, "frame_card": {"summary": "A river at sunrise.",
            "evidence_valid": True, "confidence": .75}}

    take = {"shot_id": "s1", "input_snapshot": {"validation_request": {"prompt": "River at dawn"}}}
    config = {"provider": "codex", "director_profile": {"review_priorities": []}}
    def director(**kwargs):
        evidence = json.loads(kwargs["prompt"])
        assert len(evidence["frames"]) == 3
        assert any("criteria must be a JSON array of 1 to 20 objects" in row
            for row in evidence["instructions"])
        assert any("For accept, confidence must be at least 0.75" in row for row in evidence["instructions"])
        return {"action": "accept", "confidence": .6, "reason": "Seems right.",
            "criteria": [{"name": "setting", "passed": True, "evidence": "River."}]}

    with pytest.raises(ValueError, match="confidence"):
        review_video_take(video_path=clip, take=take, run_config=config,
            runner=runner, vision_review=vision, director=director,
            audio_review=lambda **_: {"text": "", "segments": [], "dialogue_match": True})
    assert analyzed == ["frame-1.png", "frame-2.png", "frame-3.png"]
    assert all(option["inference_timeout_seconds"] == 180 for option in vision_options)


@pytest.mark.parametrize("bad_evidence", [
    {},
    {"analysis_valid": False, "frame_card": {"summary": "A river.", "evidence_valid": True, "confidence": .8}},
    {"analysis_valid": True, "frame_card": {"summary": "A river.", "confidence": .8}},
    {"analysis_valid": True, "frame_card": {"summary": "A river.", "evidence_valid": False, "confidence": .8}},
    {"analysis_valid": True, "frame_card": {"summary": "A river.", "evidence_valid": True}},
    {"analysis_valid": True, "frame_card": {"summary": "A river.", "evidence_valid": True, "confidence": float("nan")}},
    {"analysis_valid": True, "frame_card": {"summary": "A river.", "evidence_valid": True, "confidence": float("inf")}},
    {"analysis_valid": True, "frame_card": {"summary": "A river.", "evidence_valid": True, "confidence": 1.01}},
    {"analysis_valid": True, "frame_card": {"summary": "A river.", "evidence_valid": True, "confidence": True}},
])
def test_video_review_blocks_untrusted_or_invalid_frame_evidence(tmp_path, bad_evidence):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake video bytes")
    def runner(args, **kwargs):
        if args[0] == "ffprobe":
            return subprocess.CompletedProcess(args, 0, stdout="10.0\n", stderr="")
        Path(args[-1]).write_bytes(b"png")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    called = []
    def director(**_kwargs):
        called.append(True)
        return {"action": "accept", "confidence": .9, "reason": "Looks good.",
            "criteria": [{"name": "setting", "passed": True, "evidence": "River."}]}
    with pytest.raises(ValueError, match="Trusted visual evidence"):
        review_video_take(video_path=clip,
            take={"shot_id": "s1", "input_snapshot": {"validation_request": {"prompt": "River"}}},
            run_config={"provider": "codex", "director_profile": {"review_priorities": []}},
            runner=runner, vision_review=lambda *_args, **_kwargs: bad_evidence, director=director)
    assert called == []


def test_saved_video_acceptance_holds_changed_bytes_after_reopen(tmp_path):
    import hashlib
    ledger, run, take = _completed_director_take(tmp_path / "ledger.sqlite3")
    video = tmp_path / "candidate.mp4"
    original = b"original reviewed video bytes"
    video.write_bytes(original)
    decision = {"schema_version": 1, "action": "accept", "confidence": .9,
        "reason": "Looks right.", "criteria": [{"name": "scene", "passed": True, "evidence": "River."}],
        "prompt_delta": "", "video_sha256": hashlib.sha256(original).hexdigest()}
    claimed = ledger.claim_next_director_video_review(owner_token="first")
    ledger.record_director_video_review(take=claimed, decision=decision, owner_token="first")
    ledger.release_director_video_review_claim(job_id=take["job_id"], owner_token="first")
    reopened = ProductionLedger(ledger.path)
    worker = ProductionJobWorker(reopened, comfy_url="http://unused", prepare=lambda _: None,
        collect=lambda *_: [], cleanup=lambda _: None, resolve_video_output=lambda _: video,
        director_video_review=lambda *_: pytest.fail("Saved review must not be regenerated."))
    video.write_bytes(b"replaced bytes")
    assert worker.review_next_take()["status"] == "held"
    assert reopened.get_run(project_id="p1", run_id=run["run_id"])["takes"][0]["status"] == "needs_review"
    video.write_bytes(original)
    assert worker.review_next_take()["status"] == "accepted"
    assert reopened.get_run(project_id="p1", run_id=run["run_id"])["takes"][0]["status"] == "accepted"


@pytest.mark.parametrize("matched,action", [(True, "accept"), (False, "accept"), (False, "retake")])
def test_native_audio_evidence_reaches_director_and_cannot_be_overridden(tmp_path, matched, action):
    clip = tmp_path / "clip.mp4"; clip.write_bytes(b"actual registered bytes")
    def runner(args, **kwargs):
        if args[0] == "ffprobe": return subprocess.CompletedProcess(args, 0, stdout="5.0", stderr="")
        Path(args[-1]).write_bytes(b"png")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    def temporal(**kwargs):
        return {"video_sha256": kwargs["expected_sha256"], "device": "cpu", "frame_count": 16,
            "timestamps_seconds": [round(5 * i / 16, 6) for i in range(16)], "grid_sha256": "b" * 64,
            "observations": {"summary": "The left person changes mouth position.", "evidence_valid": True, "confidence": .9}}
    audio = {"text": "Ready?" if matched else "Extra words. Ready?", "segments": [], "dialogue_match": matched}
    def director(**kwargs):
        payload = json.loads(kwargs["prompt"])
        assert payload["native_audio"] == audio
        assert payload["temporal_speaker_evidence"]["frame_count"] == 16
        return {"action": action, "confidence": .95, "reason": "Audio and frames reviewed.",
            "criteria": [{"name": "speech", "passed": matched, "evidence": audio["text"]}],
            "prompt_delta": "Speak only the exact requested line." if action == "retake" else ""}
    kwargs = {"video_path": clip, "take": {"input_snapshot": {"validation_request": {"prompt": "(S1) <d>Ready?</d>"}}},
        "run_config": {"provider": "codex", "director_profile": {}}, "runner": runner,
        "vision_review": lambda *a, **k: {"analysis_valid": True, "frame_card": {
            "summary": "Two people.", "evidence_valid": True, "confidence": .9}},
        "audio_review": lambda **k: audio, "director": director, "temporal_review": temporal}
    if not matched and action == "accept":
        with pytest.raises(ValueError, match="Native audio differs"): review_video_take(**kwargs)
    else:
        decision = review_video_take(**kwargs)
        assert decision["native_audio"] == audio and decision["action"] == action


def test_saved_name_only_asr_retake_is_held_without_render_or_acceptance(tmp_path):
    ledger, run, take = _completed_director_take(tmp_path/'l.db')
    claimed = ledger.claim_next_director_video_review(owner_token='first')
    decision = {'action':'retake', 'reason':'Name spelling differs', 'confidence':.9,
        'criteria':[{'name':'Required dialogue','passed':False,'evidence':'Arun/Aaron'}],
        'prompt_delta':'Pronounce Arun clearly',
        'native_audio':{'text':"Aaron, the neighbors are here, with mom's dog.",
            'expected_lines':["Arun, the neighbors are here—with Mom's dog."]}}
    ledger.record_director_video_review(take=claimed, decision=decision, owner_token='first')
    ledger.release_director_video_review_claim(job_id=take['job_id'], owner_token='first')
    worker = ProductionJobWorker(ledger, comfy_url='http://unused', prepare=lambda _: None,
        collect=lambda *_: [], cleanup=lambda _: None,
        enqueue_director_retake=lambda *_: pytest.fail('ASR spelling uncertainty must not dispatch a retake'))
    result = worker.review_next_take()
    assert result['status']=='blocked' and result['error']['code']=='native_audio_name_uncertain'
    current=ledger.get_run(project_id='p1',run_id=run['run_id'])
    assert len(current['takes'])==1 and current['takes'][0]['status']=='needs_review'
    assert current['takes'][0]['director_review']['decision']==decision


@pytest.mark.parametrize('heard,failed_visual,uncertain', [
    ("Aaron, the neighbors are here.",False,True),
    ("Aaron, the neighbors are here, then go.",False,False),
    ("Arjun, the neighbors are here.",False,False),
    ("Aaron, the neighbors are here.",True,False),
])
def test_name_spelling_guard_does_not_hide_extra_speech_wrong_names_or_visual_defects(heard,failed_visual,uncertain):
    from story_builder.services.production_video_director import name_spelling_is_only_audio_issue
    criteria=[{'name':'Required dialogue','passed':False}]
    if failed_visual: criteria.append({'name':'Character appearance','passed':False})
    assert name_spelling_is_only_audio_issue({'text':heard,'expected_lines':['Arun, the neighbors are here.']},criteria) is uncertain


@pytest.mark.parametrize('invalid', [None, 'hash', 'extra_words', 'confirmation', 'visual_defect'])
def test_hashed_human_name_verification_reuses_evidence_but_cannot_hide_other_defects(tmp_path, invalid):
    import hashlib
    from story_builder.services.production_video_director import VideoDirectorReviewError
    clip=tmp_path/'clip.mp4';clip.write_bytes(b'unchanged native bytes');sha=hashlib.sha256(clip.read_bytes()).hexdigest()
    audio={'text':'Aaron, the neighbors are here.', 'expected_lines':['Arun, the neighbors are here.'],
        'segments':[], 'dialogue_match':False}
    criteria=[{'name':'Required dialogue','passed':False,'evidence':'ASR name uncertainty'}]
    prior={'video_sha256':sha,'native_audio':audio,'criteria':criteria,
        'evidence':[{'time_seconds':t,'summary':'A group in a stairwell.'} for t in (.75,2.5,4.25)]}
    verification={'source':'human_native_audio_review','video_sha256':sha,'confirmed':True,'statement':'The intended line is clear; no unwanted speech'}
    if invalid=='hash': verification['video_sha256']='b'*64
    if invalid=='extra_words': audio['text']='Aaron, the neighbors are here. Extra words.'
    if invalid=='confirmation': verification['confirmed']=False
    if invalid=='visual_defect': criteria.append({'name':'Missing character','passed':False})
    def director(**kwargs):
        payload=json.loads(kwargs['prompt']);assert payload['verified_native_audio']==verification
        assert payload['native_audio']['dialogue_match'] is False
        return {'action':'accept','confidence':.95,'reason':'Visuals pass and exact native audio verified by user.',
            'criteria':[{'name':'Required dialogue','passed':True,'evidence':'Exact-hash human confirmation'}]}
    kwargs={'video_path':clip,'take':{'input_snapshot':{'validation_request':{'prompt':'<d>Arun, the neighbors are here.</d>'}}},
        'run_config':{'provider':'codex','director_profile':{}},'prior_review':prior,'audio_verification':verification,
        'runner':lambda *_a,**_k: subprocess.CompletedProcess([],0,stdout='5.0'),
        'vision_review':lambda *_a,**_k: pytest.fail('Validated hashed frames must not be reanalyzed'),
        'audio_review':lambda **_k: pytest.fail('Unchanged hashed ASR must not be replayed'), 'director':director}
    if invalid is not None:
        with pytest.raises(VideoDirectorReviewError):review_video_take(**kwargs)
    else:
        decision=review_video_take(**kwargs)
        assert decision['action']=='accept' and decision['audio_verification']==verification
        assert decision['native_audio']['dialogue_match'] is False

def test_video_review_supplies_reference_features_and_targeted_frame_requirements(tmp_path):
    clip = tmp_path / 'clip.mp4'; clip.write_bytes(b'video')
    references = [{'tag': '<Picture 1>', 'asset_id': 'master', 'observed_features': {'summary': 'Olive jacket'}}]
    def runner(args, **kwargs):
        if args[0] == 'ffprobe':
            return subprocess.CompletedProcess(args, 0, stdout='8.0\n', stderr='')
        Path(args[-1]).write_bytes(b'png')
        return subprocess.CompletedProcess(args, 0, stdout='', stderr='')
    def vision(path, **kwargs):
        assert kwargs['review_requirements']['approved_references'] == references
        return {'analysis_valid': True, 'frame_card': {'summary': 'Man in olive jacket.', 'confidence': .9, 'evidence_valid': True}}
    def director(**kwargs):
        payload = json.loads(kwargs['prompt'])
        assert payload['approved_reference_evidence'] == references
        assert 'not pixel-verifiable' in payload['reference_instruction']
        return {'action': 'accept', 'confidence': .9, 'reason': 'Appearance matches.',
                'criteria': [{'name': 'appearance', 'passed': True, 'evidence': 'Olive jacket.'}]}
    result = review_video_take(video_path=clip, take={'input_snapshot': {'validation_request': {'prompt': 'Man'}}},
        run_config={'provider': 'codex', 'director_profile': {}}, reference_evidence=references,
        director=director, vision_review=vision, runner=runner,
        audio_review=lambda **_: {'text': '', 'segments': [], 'dialogue_match': True})
    assert result['reference_evidence'] == references

@pytest.mark.parametrize('mutation', ['none', 'hash', 'reference', 'lease', 'retake'])
def test_reference_evidence_reassessment_is_scoped_archived_and_spent_once(tmp_path, mutation):
    ledger, run, take = _completed_director_take(tmp_path / 'ledger.sqlite3', images=[{'asset_id': 'master'}])
    for i in range(3):
        claimed = ledger.claim_next_director_video_review(owner_token=f'owner-{i}')
        if mutation != 'lease' or i != 2:
            ledger.release_director_video_review_claim(job_id=take['job_id'], owner_token=f'owner-{i}')
    decision = {'action': 'blocked' if mutation != 'retake' else 'retake', 'video_sha256': 'a' * 64,
        'reason': 'Reference appearance evidence is insufficient.', 'reference_evidence': []}
    review = ledger.record_director_video_review(take=claimed, decision=decision)
    ledger.resolve_director_video_review(job_id=take['job_id'], status='blocked')
    references = [{'asset_id': 'master', 'sha256': 'b' * 64,
        'observed_features': {'evidence_valid': True, 'summary': 'Olive jacket.'}}]
    if mutation == 'reference': references[0]['asset_id'] = 'other'
    args = dict(project_id='p1', run_id=run['run_id'], take_id='t1', review_id=review['review_id'],
        video_sha256='0' * 64 if mutation == 'hash' else 'a' * 64, reference_evidence=references)
    if mutation != 'none':
        with pytest.raises(LedgerConflict): ledger.reopen_incomplete_reference_review(**args)
        return
    before = ledger.get_run(project_id='p1', run_id=run['run_id'])['takes'][0]
    ledger.reopen_incomplete_reference_review(**args)
    state = ledger.get_run(project_id='p1', run_id=run['run_id'])
    assert state['takes'][0]['prompt_id'] == before['prompt_id']
    assert state['takes'][0]['output_hashes'] == before['output_hashes']
    archive = next(e['payload'] for e in state['events'] if e['event_type'] == 'director_video_reference_evidence_reassessment')
    assert archive['archived_review']['review_id'] == review['review_id']
    assert archive['render_resubmitted'] is False
    final = ledger.claim_next_director_video_review(owner_token='final')
    assert final['review_attempt_count'] == 4
    ledger.release_director_video_review_claim(job_id=take['job_id'], owner_token='final')
    saved = ledger.record_director_video_review(take=final, decision=decision)
    ledger.resolve_director_video_review(job_id=take['job_id'], status='blocked')
    with pytest.raises(LedgerConflict, match='already spent'):
        ledger.reopen_incomplete_reference_review(**{**args, 'review_id': saved['review_id']})

@pytest.mark.parametrize('invalid', [None, 'visual', 'mismatch', 'scope', 'hash'])
def test_exact_dialogue_sound_confirmation_remains_scoped(tmp_path, invalid):
    import hashlib
    from story_builder.services.production_video_director import VideoDirectorReviewError
    clip = tmp_path/'clip.mp4'; clip.write_bytes(b'unchanged'); sha=hashlib.sha256(clip.read_bytes()).hexdigest()
    audio={'text':'The storm is coming.','expected_lines':['The storm is coming.'],'segments':[], 'dialogue_match': invalid != 'mismatch'}
    prior={'action':'blocked','video_sha256':sha,'native_audio':audio,
        'criteria':[{'name':'Speaker confirmed','passed':False}],
        'evidence':[{'time_seconds':t,'summary':'Woman turns to listening man.'} for t in (1.2,4.0,6.8)]}
    if invalid == 'visual': prior['criteria'].append({'name':'Wrong clothing','passed':False})
    verification={'source':'human_native_audio_review','confirmed':True,'video_sha256':'b'*64 if invalid=='hash' else sha,
        'statement':'Maya’s line is clear; no unwanted speech', 'scope':'other' if invalid=='scope' else 'matching_dialogue_audio_uncertainty'}
    def director(**kwargs):
        payload=json.loads(kwargs['prompt']);assert payload['verified_native_audio']==verification
        assert payload['native_audio']==audio
        return {'action':'accept','confidence':.9,'reason':'Visual staging and exact native dialogue pass.',
            'criteria':[{'name':'Dialogue','passed':True,'evidence':'Exact-hash user verification'}]}
    args=dict(video_path=clip,take={'input_snapshot':{'validation_request':{'prompt':'<d>The storm is coming.</d>'}}},
        run_config={'provider':'codex','director_profile':{}},prior_review=prior,audio_verification=verification,
        runner=lambda *_a,**_k:subprocess.CompletedProcess([],0,stdout='8.0'),director=director,
        vision_review=lambda *_a,**_k:pytest.fail('Do not repeat hashed visual inference'),
        audio_review=lambda **_k:pytest.fail('Do not repeat hashed ASR'))
    if invalid:
        with pytest.raises(VideoDirectorReviewError):review_video_take(**args)
    else: assert review_video_take(**args)['action']=='accept'


def _contradictory_group_decision():
    return {'action':'retake','video_sha256':'a'*64,'reason':'Descriptions conflict','confidence':.9,
        'prompt_delta':'Keep the group visible',
        'evidence':[{'summary':'Five people and a dog.'},{'summary':'Four characters and a dog.'}],
        'native_audio':{'text':'Aaron, the neighbors are here.','expected_lines':['Arun, the neighbors are here.'],'dialogue_match':False,'segments':[]},
        'criteria':[{'name':'Required group visible','passed':False,'evidence':'Frame descriptions conflict and do not establish a continuous count.'},
                    {'name':'Native dialogue','passed':False,'evidence':'Arun/Aaron'}]}


@pytest.mark.parametrize('defect',[None,'clothing','extra_speech','concrete_missing_person','no_contradiction'])
def test_saved_conflicting_count_review_never_rerenders_uncertainty(tmp_path,defect):
    from story_builder.services.production_video_director import contradictory_group_evidence_only
    decision=_contradictory_group_decision()
    if defect=='clothing':decision['criteria'].append({'name':'Wrong clothing','passed':False,'evidence':'Puffer instead of rain jacket.'})
    if defect=='extra_speech':decision['native_audio']['text']='Aaron, the neighbors are here, leave now.'
    if defect=='concrete_missing_person':decision['criteria'][0]['evidence']='One neighbor visibly vanishes.'
    if defect=='no_contradiction':decision['evidence'][0]['summary']='Four people and a dog.'
    assert contradictory_group_evidence_only(decision) is (defect is None)
    if defect:return
    ledger,run,take=_completed_director_take(tmp_path/'count.db')
    claimed=ledger.claim_next_director_video_review(owner_token='first')
    ledger.record_director_video_review(take=claimed,decision=decision,owner_token='first')
    ledger.release_director_video_review_claim(job_id=take['job_id'],owner_token='first')
    worker=ProductionJobWorker(ledger,comfy_url='http://unused',prepare=lambda _:None,collect=lambda *_:[],cleanup=lambda _:None,
        enqueue_director_retake=lambda *_:pytest.fail('Contradictory descriptions must not dispatch a retake'))
    result=worker.review_next_take()
    assert result['status']=='blocked' and result['error']['code']=='native_video_evidence_uncertain'
    state=ledger.get_run(project_id='p1',run_id=run['run_id'])
    assert len(state['takes'])==1 and state['takes'][0]['director_review']['decision']==decision


def _subject_gap_decision():
    return {'action':'retake','video_sha256':'a'*64,
        'native_audio':{'text':'Aaron, the neighbors are here.','expected_lines':['Arun, the neighbors are here.'],'dialogue_match':False,'segments':[]},
        'criteria':[{'name':'Five subjects visible','passed':False,'evidence':'Neighbors and dog are not individually described.'},
                    {'name':'Native dialogue','passed':False,'evidence':'Arun/Aaron'}],
        'evidence':[{'time_seconds':t,'summary':'Four people and a dog.','subjects':[{'name':'Person1'},{'name':'Person2'}]} for t in (1.2,4.,6.8)]}


def test_subject_limited_review_refreshes_frames_not_hashed_audio(tmp_path):
    import hashlib
    clip=tmp_path/'clip.mp4';clip.write_bytes(b'actual');prior=_subject_gap_decision();sha=hashlib.sha256(clip.read_bytes()).hexdigest();prior['video_sha256']=sha
    calls=[]
    verification={'source':'human_native_audio_review','confirmed':True,'video_sha256':sha,'statement':'Intended name and line clear','scope':'name_spelling_only'}
    def runner(args,**kwargs):
        if args[0]=='ffprobe':return subprocess.CompletedProcess(args,0,stdout='8.0')
        Path(args[-1]).write_bytes(b'frame');return subprocess.CompletedProcess(args,0)
    def vision(path,**kwargs):
        assert kwargs['max_visible_subjects']==12;calls.append(path.name)
        return {'analysis_valid':True,'frame_card':{'summary':'Four distinct people plus dog, each located.','subjects':[{'name':str(i)} for i in range(5)],'evidence_valid':True,'confidence':.9}}
    def director(**kwargs):
        payload=json.loads(kwargs['prompt']);assert len(payload['frames'][0]['subjects'])==5 and payload['verified_native_audio']==verification
        return {'action':'accept','confidence':.9,'reason':'Fresh visual and verified audio pass','criteria':[{'name':'Group','passed':True,'evidence':'Five subjects located'}]}
    result=review_video_take(video_path=clip,take={'input_snapshot':{'validation_request':{'prompt':'<d>Arun, the neighbors are here.</d>'}}},
        run_config={'provider':'codex','director_profile':{}},prior_review=prior,audio_verification=verification,refresh_visual_evidence=True,
        runner=runner,vision_review=vision,director=director,audio_review=lambda **k:pytest.fail('Do not repeat hashed audio'))
    assert len(calls)==3 and result['action']=='accept' and result['frame_analysis_subject_limit']==12


@pytest.mark.parametrize('mutation',[None,'clothing','extra_speech','complete_budget'])
def test_subject_gap_does_not_hide_concrete_defects(mutation):
    from story_builder.services.production_video_director import subject_limit_evidence_gap
    d=_subject_gap_decision()
    if mutation=='clothing':d['criteria'].append({'name':'Clothing','passed':False,'evidence':'Wrong puffer jacket.'})
    if mutation=='extra_speech':d['native_audio']['text']='Aaron, the neighbors are here, run away.'
    if mutation=='complete_budget':d['frame_analysis_subject_limit']=12
    assert subject_limit_evidence_gap(d) is (mutation is None)


def _speaker_only_after_name_acceptance(sha='a'*64):
    return {'action':'blocked','video_sha256':sha,
        'native_audio':{'text':'Aaron, the neighbors are here.','expected_lines':['Arun, the neighbors are here.'],
            'segments':[],'dialogue_match':False},
        'audio_verification':{'source':'human_native_audio_review','confirmed':True,'video_sha256':sha,
            'scope':'name_spelling_only','statement':'Aaron is fine'},
        'criteria':[{'name':'Appearance','passed':True,'evidence':'Approved clothing'},
            {'name':'Mira is the audible speaker','passed':False,'evidence':'Still frames cannot establish speaker identity'}],
        'evidence':[{'time_seconds':t,'summary':'Mira and Arun in the stairwell.'} for t in (.75,2.5,4.25)]}


@pytest.mark.parametrize('mutation',[None,'extra_words','clothing','name_hash','unconfirmed','wrong_scope'])
def test_human_speaker_confirmation_cannot_hide_concrete_defects(mutation):
    from story_builder.services.production_video_director import speaker_uncertainty_with_accepted_pronunciation
    d=_speaker_only_after_name_acceptance()
    if mutation=='extra_words':d['native_audio']['text']+=' Run away.'
    if mutation=='clothing':d['criteria'].append({'name':'Clothing','passed':False,'evidence':'Wrong jacket'})
    if mutation=='name_hash':d['audio_verification']['video_sha256']='b'*64
    if mutation=='unconfirmed':d['audio_verification']['confirmed']=False
    if mutation=='wrong_scope':d['audio_verification']['scope']='speaker'
    assert speaker_uncertainty_with_accepted_pronunciation(d) is (mutation is None)


@pytest.mark.parametrize('invalid',[None,'hash','active','unauthorized','changed_review','defect'])
def test_human_speaker_reassessment_preserves_claims_and_is_single_use(tmp_path,invalid):
    path=tmp_path/'speaker.db';ledger,run,take=_completed_director_take(path)
    for index in range(3):
        claimed=ledger.claim_next_director_video_review(owner_token=f'owner{index}')
        if index==2:
            d=_speaker_only_after_name_acceptance()
            if invalid=='defect':d['criteria'].append({'name':'Clothing','passed':False,'evidence':'Wrong jacket'})
            review=ledger.record_director_video_review(take=claimed,decision=d,owner_token=f'owner{index}')
            ledger.resolve_director_video_review(job_id=take['job_id'],
                status='blocked',error={'code':'director_video_review_blocked'})
        if invalid!='active' or index!=2:
            ledger.release_director_video_review_claim(job_id=take['job_id'],owner_token=f'owner{index}')
    options=dict(project_id='p1',run_id=run['run_id'],take_id=take['take_id'],review_id=review['review_id'],
        video_sha256='b'*64 if invalid=='hash' else 'a'*64,statement='The girl was speaking, not Aaron',
        authorize_one_extra_attempt=invalid!='unauthorized')
    if invalid=='changed_review':options['review_id']='different'
    if invalid:
        with pytest.raises((LedgerConflict,ValueError)):
            ledger.reopen_speaker_uncertain_review_with_human_verification(**options)
        assert ledger.get_run(project_id='p1',run_id=run['run_id'])['takes'][0]['director_review']['review_id']==review['review_id']
        return
    verification=ledger.reopen_speaker_uncertain_review_with_human_verification(**options)
    reopened=ProductionLedger(path)
    for i in range(505):reopened.record_run_event(project_id='p1',run_id=run['run_id'],event_type='later',payload={})
    saved=reopened.human_audio_review_evidence(project_id='p1',run_id=run['run_id'],job_id=take['job_id'])
    assert saved['verification']==verification and saved['archived_review']['decision']==d
    assert reopened.claim_next_director_video_review(owner_token='final')['review_attempt_count']==4
    reopened.release_director_video_review_claim(job_id=take['job_id'],owner_token='final')
    assert reopened.claim_next_director_video_review(owner_token='fifth')['review_attempts_exhausted'] is True
    with pytest.raises(LedgerConflict):reopened.reopen_speaker_uncertain_review_with_human_verification(**options)
    assert len(reopened.get_run(project_id='p1',run_id=run['run_id'])['takes'])==1


@pytest.mark.parametrize('changed',[False,True])
def test_final_speaker_review_uses_same_hashed_evidence_and_keeps_pronunciation(tmp_path,changed):
    import hashlib
    from story_builder.services.production_video_director import VideoDirectorReviewError
    clip=tmp_path/'clip.mp4';clip.write_bytes(b'native video bytes');sha=hashlib.sha256(clip.read_bytes()).hexdigest()
    prior=_speaker_only_after_name_acceptance(sha)
    verification={'source':'human_native_audio_review','confirmed':True,'video_sha256':sha,
        'statement':'The girl was speaking not Aaron','scope':'speaker_with_accepted_pronunciation',
        'prior_pronunciation_verification':prior['audio_verification']}
    if changed:clip.write_bytes(b'changed')
    def director(**kwargs):
        payload=json.loads(kwargs['prompt'])
        assert payload['verified_native_audio']==verification and payload['native_audio']==prior['native_audio']
        return {'action':'accept','confidence':.9,'reason':'Same-clip human speaker confirmation and visuals pass',
            'criteria':[{'name':'Speaker','passed':True,'evidence':'Human confirmed the girl speaks'}]}
    options=dict(video_path=clip,take={'input_snapshot':{'validation_request':{'prompt':'<d>Arun, the neighbors are here.</d>'}}},
        run_config={'provider':'codex','director_profile':{}},prior_review=prior,audio_verification=verification,
        runner=lambda *_a,**_k:subprocess.CompletedProcess([],0,stdout='5.0'),director=director,
        vision_review=lambda *_a,**_k:pytest.fail('Do not repeat trusted vision'),
        audio_review=lambda **_k:pytest.fail('Do not repeat same-hash ASR'),
        temporal_review=lambda **_k:pytest.fail('No unrequested new temporal analysis'))
    if changed:
        with pytest.raises(VideoDirectorReviewError):review_video_take(**options)
    else:
        result=review_video_take(**options)
        assert result['action']=='accept' and result['audio_verification']==verification
