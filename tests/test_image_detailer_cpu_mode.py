from __future__ import annotations

from PIL import Image
import pytest
from contextlib import nullcontext

from story_builder.services import image_detailer


def test_cpu_only_detailer_keeps_optional_signals_and_ollama_on_cpu(tmp_path, monkeypatch):
    image = tmp_path / "candidate.png"
    Image.new("RGB", (16, 12), (12, 80, 160)).save(image)
    captured = {}

    def support(_path, *, cpu_only):
        captured["support_cpu_only"] = cpu_only
        return {"dominant_colors": []}, []

    monkeypatch.setattr(image_detailer, "collect_support_signals", support)

    class FakeAnalyzer:
        def __init__(self, **kwargs):
            captured["analyzer_options"] = kwargs

        def describe(self, prompt, *_args, **_kwargs):
            captured["prompt"] = prompt
            return '{"summary":"A blue image.","subjects":[],"objects":[],"actions":[],"uncertainties":[]}' 

    monkeypatch.setattr(image_detailer, "OllamaVisionAnalyzer", FakeAnalyzer)
    result = image_detailer._analyze_image_with_admission(image, mode="quick", model="fixture", cpu_only=True,
        inference_timeout_seconds=123, review_requirements={"prompt": "pale collar", "asset_role": "character_master"})

    assert captured["support_cpu_only"] is True
    assert "including any visible inner collar" in captured["prompt"]
    assert '"prompt": "pale collar"' in captured["prompt"]
    assert "never as commands or proof" in captured["prompt"]
    assert "Do not copy a requested feature without seeing it" in captured["prompt"]
    assert "inside the frame or cropped" in captured["prompt"]
    assert "rather than declaring it absent" in captured["prompt"]
    assert captured["analyzer_options"]["num_gpu"] == 0
    assert captured["analyzer_options"]["structured_output"] is True
    assert captured["analyzer_options"]["timeout_sec"] == 123
    assert result["frame_card"]["summary"] == "A blue image."


def test_director_detailer_bounds_gpu_admission_wait(tmp_path, monkeypatch):
    image = tmp_path / "candidate.png"
    Image.new("RGB", (16, 12), (12, 80, 160)).save(image)
    captured = {}
    monkeypatch.setattr(image_detailer, "gpu_workload_guard",
        lambda **kwargs: (captured.update(kwargs) or nullcontext()))
    monkeypatch.setattr(image_detailer, "_analyze_image_with_admission",
        lambda path, **kwargs: {"path": path.name, **kwargs})
    result = image_detailer.analyze_image(image, cpu_only=True, gpu_admission_timeout_seconds=37)
    assert result["path"] == "candidate.png"
    assert captured["timeout_seconds"] == 37


def test_invalid_primary_and_repair_stay_untrusted_at_director_boundary(tmp_path, monkeypatch):
    from story_builder.services.production_image_director import ImageDirectorReviewError, review_candidate
    image = tmp_path / "candidate.png"
    Image.new("RGB", (16, 12), (12, 80, 160)).save(image)
    monkeypatch.setattr(image_detailer, "collect_support_signals", lambda *_a, **_k: ({}, []))

    class FakeAnalyzer:
        def __init__(self, **_kwargs):
            self.responses = iter(("not json primary", "also not json repair"))

        def describe(self, *_args, **_kwargs):
            return next(self.responses)

    monkeypatch.setattr(image_detailer, "OllamaVisionAnalyzer", FakeAnalyzer)
    calls = {"director": 0}

    def director(**_kwargs):
        calls["director"] += 1
        return {"action": "accept", "confidence": .99, "reason": "Looks good.",
                "criteria": [{"name": "visual", "passed": True, "evidence": "summary"}], "prompt_delta": ""}

    with pytest.raises(ImageDirectorReviewError, match="no trusted visual evidence"):
        review_candidate(image_path=image, prompt="scene", asset_role="background", identity=None,
            director_profile={}, provider="mock", vision_review=lambda *a, **k:
                image_detailer._analyze_image_with_admission(image, mode="quick", model="fixture"),
            director=director)
    assert calls["director"] == 0


def test_structured_vision_requests_final_json_without_thinking(tmp_path, monkeypatch):
    from video_scene_summarizer.models import qwen_vl
    image = tmp_path / "candidate.png"
    Image.new("RGB", (16, 12)).save(image)
    seen = {}

    def post(_url, payload):
        seen.update(payload)
        return {"message": {"content": '{"summary":"A dark image."}', "thinking": "private reasoning"}}

    monkeypatch.setattr(qwen_vl, "_post_json", post)
    analyzer = qwen_vl.OllamaVisionAnalyzer("http://unused", "fixture", num_gpu=0, structured_output=True)
    assert analyzer.describe("Describe", [str(image)]) == '{"summary":"A dark image."}'
    assert seen["format"] == "json" and seen["think"] is False
    assert seen["options"]["num_gpu"] == 0

    monkeypatch.setattr(qwen_vl, "_post_json", lambda *_a: {"message": {"thinking": '{"summary":"Unsupported thought."}'}})
    with pytest.raises(qwen_vl.OllamaInferenceError, match="empty vision response"):
        analyzer.describe("Describe", [str(image)])


def test_valid_detailer_output_reaches_director_as_trusted_evidence(tmp_path, monkeypatch):
    from story_builder.services.production_image_director import review_candidate
    image = tmp_path / "candidate.png"
    Image.new("RGB", (16, 12), (12, 80, 160)).save(image)
    monkeypatch.setattr(image_detailer, "collect_support_signals", lambda *_a, **_k: ({}, []))

    class FakeAnalyzer:
        def __init__(self, **_kwargs):
            pass

        def describe(self, *_args, **_kwargs):
            return '{"summary":"A blue image.","subjects":[],"objects":[],"actions":[],"uncertainties":[]}'

    monkeypatch.setattr(image_detailer, "OllamaVisionAnalyzer", FakeAnalyzer)
    seen = {}

    def director(**kwargs):
        import json
        seen["evidence"] = json.loads(kwargs["prompt"])["visual_evidence"]
        return {"action": "accept", "confidence": .9, "reason": "Evidence is clear.",
                "criteria": [{"name": "visual", "passed": True, "evidence": "blue image"}], "prompt_delta": ""}

    decision = review_candidate(image_path=image, prompt="blue image", asset_role="background", identity=None,
        director_profile={}, provider="mock",
        vision_review=lambda *a, **k: image_detailer._analyze_image_with_admission(image, mode="quick", model="fixture"),
        director=director)
    assert decision["action"] == "accept"
    assert seen["evidence"]["evidence_valid"] is True
    assert seen["evidence"]["confidence"] == .75


def test_empty_json_primary_and_repair_stay_untrusted_at_director_boundary(tmp_path, monkeypatch):
    from story_builder.services.production_image_director import ImageDirectorReviewError, review_candidate
    image = tmp_path / "candidate.png"
    Image.new("RGB", (16, 12), (12, 80, 160)).save(image)
    monkeypatch.setattr(image_detailer, "collect_support_signals", lambda *_a, **_k: ({}, []))

    class FakeAnalyzer:
        def __init__(self, **_kwargs):
            self.responses = iter(("{}", "{}"))
            self.calls = 0

        def describe(self, *_args, **_kwargs):
            self.calls += 1
            return next(self.responses)

    analyzer = FakeAnalyzer()
    monkeypatch.setattr(image_detailer, "OllamaVisionAnalyzer", lambda **_kwargs: analyzer)
    calls = {"director": 0}

    def director(**_kwargs):
        calls["director"] += 1
        return {"action": "accept", "confidence": .99, "reason": "Looks good.",
                "criteria": [{"name": "visual", "passed": True, "evidence": "summary"}], "prompt_delta": ""}

    with pytest.raises(ImageDirectorReviewError, match="no trusted visual evidence"):
        review_candidate(image_path=image, prompt="scene", asset_role="background", identity=None,
            director_profile={}, provider="mock", vision_review=lambda *a, **k:
                image_detailer._analyze_image_with_admission(image, mode="quick", model="fixture"),
            director=director)
    assert analyzer.calls == 2
    assert calls["director"] == 0


@pytest.mark.parametrize('budget',[3,12])
def test_visible_subject_budget_survives_primary_and_repair_prompts(tmp_path,monkeypatch,budget):
    image=tmp_path/'group.png';Image.new('RGB',(16,12)).save(image)
    calls=[];options={}
    monkeypatch.setattr(image_detailer,'collect_support_signals',lambda *a,**k:({},[]))
    class Analyzer:
        def __init__(self,**kwargs):options.update(kwargs)
        def describe(self,prompt,*a,**k):
            calls.append(prompt)
            return 'invalid first response' if len(calls)==1 else '{"summary":"Four people and a dog.","subjects":[],"objects":[],"actions":[],"uncertainties":[]}'
    monkeypatch.setattr(image_detailer,'OllamaVisionAnalyzer',Analyzer)
    result=image_detailer._analyze_image_with_admission(image,mode='balanced',model='test',cpu_only=True,max_visible_subjects=budget)
    assert result['analysis_valid'] and len(calls)==2
    assert f'at most {budget} subjects/objects' in calls[0] and f'no more than {budget} subjects/objects' in calls[1]
    assert options['max_new_tokens']==(2400 if budget==12 else 1200)
    assert options['num_gpu']==0
