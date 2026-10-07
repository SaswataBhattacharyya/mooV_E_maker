from __future__ import annotations

import uuid

import pytest

from story_builder.services.production_voice_binding import VoiceBindingError, bind_voice, eligible_voice_pool


def _voice(asset_id: str, *, seconds: float = 35.0, status: str = "accepted", source: str = "project_upload"):
    return {"asset_id": asset_id, "kind": "audio", "roles": ["voice_master"], "source": source,
        "sha256": asset_id[3:].ljust(64, "0")[:64], "media": {"duration_seconds": seconds},
        "metadata": {"approval_status": status}}


def test_semi_delegated_voice_uses_saved_random_policy(tmp_path):
    voice = _voice("pa-voice0000000000")
    options = dict(run_id=str(uuid.uuid4()), character_id=str(uuid.uuid4()),
        control_mode="semi", semi_gates={"voice_selection": False}, strategy="seeded_random",
        asset_id=None, assets=[voice], get_asset=lambda _: voice)
    first = bind_voice(tmp_path, "p", **options)
    second = bind_voice(tmp_path, "p", **options)
    assert first["seed"] == second["seed"] and second["reused"]
    with pytest.raises(VoiceBindingError):
        bind_voice(tmp_path, "p", **{**options, "strategy": "manual", "asset_id": voice["asset_id"]})


def test_voice_eligibility_explains_short_unapproved_and_external_exclusions():
    eligible, excluded = eligible_voice_pool([
        _voice("pa-valid"), _voice("pa-short", seconds=12),
        _voice("pa-pending", status="candidate"), _voice("pa-external", source="external_video_repertoire_audio")])
    assert [row["asset_id"] for row in eligible] == ["pa-valid"]
    assert {row["asset_id"]: row["reason"] for row in excluded} == {
        "pa-short": "voice_master_too_short_or_unprobed",
        "pa-pending": "not_accepted",
        "pa-external": "external_voice_not_eligible_for_automatic_binding",
    }


def test_manual_voice_binding_is_project_scoped_stable_and_path_free(tmp_path):
    run_id, character_id = str(uuid.uuid4()), str(uuid.uuid4())
    voice = _voice("pa-voice0000000000")
    result = bind_voice(tmp_path / "projects", "film", run_id=run_id, character_id=character_id,
        control_mode="manual", strategy="manual", asset_id=voice["asset_id"], assets=[voice],
        get_asset=lambda asset_id: voice if asset_id == voice["asset_id"] else {})
    assert result["speaker_id"] == "S1"
    assert result["voice_asset_id"] == voice["asset_id"]
    assert result["seed"] is None and result["h3_reference_excerpt_required"] is True
    assert "relative_path" not in result and "path" not in result
    repeated = bind_voice(tmp_path / "projects", "film", run_id=run_id, character_id=character_id,
        control_mode="manual", strategy="manual", asset_id=voice["asset_id"], assets=[voice],
        get_asset=lambda _asset_id: voice)
    assert repeated["reused"] is True and repeated["binding_id"] == result["binding_id"]
    with pytest.raises(VoiceBindingError) as changed:
        bind_voice(tmp_path / "projects", "film", run_id=run_id, character_id=character_id,
            control_mode="manual", strategy="manual", asset_id="pa-other", assets=[voice],
            get_asset=lambda _asset_id: voice)
    assert changed.value.code == "voice_asset_ineligible"


def test_two_character_bindings_keep_distinct_stable_speaker_ids(tmp_path):
    run_id, character_a, character_b = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    voices = [_voice("pa-voice0000000011"), _voice("pa-voice0000000012")]
    get_asset = lambda asset_id: next(row for row in voices if row["asset_id"] == asset_id)
    first = bind_voice(tmp_path / "projects", "film", run_id=run_id, character_id=character_a,
        control_mode="manual", strategy="manual", asset_id=voices[0]["asset_id"], assets=voices,
        get_asset=get_asset)
    second = bind_voice(tmp_path / "projects", "film", run_id=run_id, character_id=character_b,
        control_mode="manual", strategy="manual", asset_id=voices[1]["asset_id"], assets=voices,
        get_asset=get_asset)
    assert (first["speaker_id"], second["speaker_id"]) == ("S1", "S2")
    assert first["voice_asset_id"] != second["voice_asset_id"]
    repeated = bind_voice(tmp_path / "projects", "film", run_id=run_id, character_id=character_a,
        control_mode="manual", strategy="manual", asset_id=voices[0]["asset_id"], assets=voices,
        get_asset=get_asset)
    assert repeated["speaker_id"] == "S1" and repeated["reused"] is True


def test_full_voice_choice_is_reproducible_and_cannot_be_user_rerolled(tmp_path):
    run_id, character_id = str(uuid.uuid4()), str(uuid.uuid4())
    voices = [_voice("pa-voice0000000001"), _voice("pa-voice0000000002")]
    kwargs = dict(run_id=run_id, character_id=character_id, control_mode="fully_automated",
        strategy="seeded_random", asset_id=None, assets=voices,
        get_asset=lambda asset_id: next(row for row in voices if row["asset_id"] == asset_id))
    first = bind_voice(tmp_path / "projects", "film", **kwargs)
    assert first["seed"] is not None and first["eligible_pool_hash"]
    repeated = bind_voice(tmp_path / "projects", "film", **kwargs)
    assert repeated["reused"] is True and repeated["voice_asset_id"] == first["voice_asset_id"]
    assert repeated["seed"] == first["seed"]


@pytest.mark.parametrize("mode,strategy", [("manual", "seeded_random"), ("semi", "seeded_random"),
                                             ("fully_automated", "manual")])
def test_voice_strategy_must_match_control_mode(tmp_path, mode, strategy):
    voice = _voice("pa-voice0000000000")
    with pytest.raises(VoiceBindingError) as error:
        bind_voice(tmp_path, "film", run_id=str(uuid.uuid4()), character_id=str(uuid.uuid4()),
            control_mode=mode, strategy=strategy, asset_id=voice["asset_id"], assets=[voice],
            get_asset=lambda _asset_id: voice)
    assert error.value.code == "voice_strategy_forbidden"
