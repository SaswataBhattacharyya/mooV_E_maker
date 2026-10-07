from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
import wave

from fastapi import BackgroundTasks, HTTPException
import pytest

from story_builder.api import main as api
from story_builder.services import production_dialogue_tts
from story_builder.services.production_world_state import create_anonymous_character


def _wav(seconds: float) -> bytes:
    content = BytesIO()
    with wave.open(content, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(32000)
        output.writeframes(b"\0\0" * int(32000 * seconds))
    return content.getvalue()


def _project(tmp_path, monkeypatch):
    store = api.ProjectStore(tmp_path / "projects")
    project = store.create_project(title="Dialogue TTS", story_input="Two people speak.", automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", store)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    run = asyncio.run(api.create_production_v2_run(project["id"],
        api.ProductionV2RunRequest(idempotency_key="run")))
    characters = [create_anonymous_character("Maya"), create_anonymous_character("Ari")]
    api.save_project_canon(store.root_dir, project["id"], expected_revision=0,
        characters=characters, worlds=[], actor="test")
    masters = []
    excerpts = []
    for index, character in enumerate(characters):
        master = api.register_production_asset_upload(store.root_dir, project["id"],
            filename=f"voice-{index}.wav", content=_wav(32), role="voice_master")
        masters.append(master)
        asyncio.run(api.create_production_voice_binding(project["id"], run["run_id"],
            api.ProductionVoiceBindingRequest(character_id=character["character_id"],
                strategy="manual", voice_asset_id=master["asset_id"])))
        excerpts.append(asyncio.run(api.create_production_h3_voice_excerpt(project["id"],
            run["run_id"], character["character_id"],
            api.ProductionVoiceExcerptRequest(voice_asset_id=master["asset_id"],
                start_sec=0, duration_seconds=5))))
    return project["id"], run["run_id"], characters, masters, excerpts


def _payload(characters, excerpts, text="Wait—listen."):
    return api.ProductionDialogueTTSRequest(idempotency_key="dialogue-click",
        speakers=[{"character_id": row["character_id"], "voice_excerpt_asset_id": excerpts[index]["asset_id"]}
            for index, row in enumerate(characters)],
        lines=[{"character_id": characters[0]["character_id"], "text": text,
                 "start_seconds": 0, "end_seconds": 2},
               {"character_id": characters[1]["character_id"], "text": "I hear rain.",
                 "start_seconds": 2, "end_seconds": 4}],
        seed=99)


def test_run_bound_dialogue_tts_durable_worker_and_asset_round_trip(tmp_path, monkeypatch):
    project, run, characters, _masters, excerpts = _project(tmp_path, monkeypatch)
    payload = _payload(characters, excerpts)
    first = asyncio.run(api.create_production_dialogue_tts(project, run, payload, BackgroundTasks()))
    replay = asyncio.run(api.create_production_dialogue_tts(project, run, payload, BackgroundTasks()))
    assert first["job_id"] == replay["job_id"]
    assert first["prompt_id"] == replay["prompt_id"]
    assert "Speaker 1: Wait—listen." in first["submitted_srt"]
    assert "Speaker 2: I hear rain." in first["submitted_srt"]
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(api.create_production_dialogue_tts(project, run,
            payload.model_copy(update={"lines": [payload.lines[0].model_copy(update={"text": "Different words."}), payload.lines[1]]}),
            BackgroundTasks()))
    assert conflict.value.status_code == 409

    registered_output = {}

    def fake_run_job(**kwargs):
        output = Path(kwargs["output_root"]) / project / "audio" / "dialogue" / first["job_id"] / "speech.wav"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_wav(4))
        kwargs["update"]({"status": "completed", "export_path": str(output),
                          "srt_path": str(tmp_path / "submitted.srt")})
        registered_output["path"] = output

    monkeypatch.setattr(production_dialogue_tts, "run_job", fake_run_job)
    api._execute_production_audio_sidecar(project, run, first)
    completed = api._production_audio_store().get(project, run, first["job_id"])
    assert completed["status"] == "completed"
    asset = api.get_production_asset_record(api.PROJECT_STORE.root_dir, project, completed["production_asset_id"])
    assert asset["roles"] == ["dialogue_take"]
    lineage = asset["metadata"]["dialogue_take"]
    assert lineage["recording_status"] == "generated_tts"
    assert lineage["transcript"][0]["text"] == "Wait—listen."
    assert [row["speaker_id"] for row in lineage["speakers"]] == ["S1", "S2"]
    assert Path(api.resolve_production_asset_content(api.PROJECT_STORE.root_dir, api.OUTPUT_ROOT,
        project, asset["asset_id"])[0]).resolve() == registered_output["path"].resolve()
    api._execute_production_audio_sidecar(project, run, first)
    assert api._production_audio_store().get(project, run, first["job_id"])["production_asset_id"] == asset["asset_id"]


def test_dialogue_tts_rejects_excerpt_from_wrong_run_character_or_master(tmp_path, monkeypatch):
    project, run, characters, _masters, excerpts = _project(tmp_path, monkeypatch)
    wrong = _payload(characters, [excerpts[1], excerpts[0]])
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(api.create_production_dialogue_tts(project, run, wrong, BackgroundTasks()))
    assert rejected.value.status_code == 422
    assert rejected.value.detail["code"] == "dialogue_voice_excerpt_mismatch"
