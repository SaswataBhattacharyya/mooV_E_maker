from __future__ import annotations

import json

import pytest

from story_builder.services.director_contract import (
    DirectorContractError,
    build_director_task,
    lint_h3_prompt,
    load_prompt_corpus,
    refine_h3_prompt,
    refine_proposal_is_current,
    review_story_revision,
    review_text_stage_revision,
)


def _reference_map():
    return {
        "pictures": [{"tag": "<Picture 1>", "intent": "character identity"}],
        "videos": [{"tag": "<Video 1>", "role": "previous_cut_state", "intent": "prior cut continuity"}],
        "audios": [{"tag": "<Audio 1>", "speaker_id": "S1", "intent": "voice timbre"}],
        "speaker_audio_tags": {"S1": "<Audio 1>"},
    }


def test_corpus_manifest_is_versioned_hashed_and_contains_only_declared_files():
    corpus = load_prompt_corpus()
    assert corpus["version"] == "h3_prompt_rules_v1"
    assert len(corpus["content_hash"]) == 64
    assert {"reference_roles.md", "shot_prompt_contract.md", "examples.json", "validation.json"} == set(corpus["rules"])
    assert len(corpus["examples"]) >= 2


def test_director_task_is_provider_neutral_and_snapshots_corpus_and_context():
    corpus = load_prompt_corpus()
    task = build_director_task(stage="shot_prompt", source={"story": "Asha leaves."},
                               context={"shot_id": "cut-01"}, corpus=corpus)
    assert task["corpus_version"] == corpus["version"]
    assert task["corpus_hash"] == corpus["content_hash"]
    assert task["context"]["shot_id"] == "cut-01"
    assert any("stable IDs" in item for item in task["constraints"])
    assert "provider" not in task
    assert "tools" not in task


def test_prompt_lint_accepts_exact_references_speaker_binding_and_continuity():
    prompt = ("<Picture 1> defines Maya's identity. <Video 1> is the preceding cut; continue from its final moment. "
              "<Audio 1> is Maya's voice reference for Subject 1 (S1). Maya (S1) says <d>[English] We should go.</d>")
    lint = lint_h3_prompt(prompt, _reference_map(), duration_seconds=5,
                          dialogue_lines=[{"text": "We should go."}])
    assert lint["ok"] is True
    assert lint["errors"] == []
    assert lint["warnings"] == []


def test_prompt_lint_reports_unknown_unused_refs_speaker_binding_and_copy_conflict():
    prompt = "Use <Picture 9> and fully_copy the original audio exactly, then add new dialogue."
    lint = lint_h3_prompt(prompt, _reference_map())
    codes = {issue["code"] for issue in lint["errors"]}
    assert {"prompt_reference_tags_mismatch", "speaker_reference_unbound", "audio_copy_conflict"} <= codes


def test_prompt_lint_warns_for_dense_dialogue_and_undeclared_prior_video():
    lint = lint_h3_prompt("<Picture 1> <Video 1> <Audio 1> for Maya (S1).", _reference_map(),
                          duration_seconds=2, dialogue_lines=[{"text": "one two three four five six seven"}])
    assert {issue["code"] for issue in lint["warnings"]} == {"dialogue_density_high", "continuity_role_undeclared"}


def test_prompt_corpus_fails_closed_on_manifest_drift(tmp_path):
    (tmp_path / "corpus_manifest.json").write_text(json.dumps({"status": "active", "version": "v"}))
    with pytest.raises(DirectorContractError, match="file list"):
        load_prompt_corpus(tmp_path)


def test_refine_returns_non_mutating_diff_proposal_bound_to_inputs_and_tags():
    reference_map = _reference_map()
    original = "<Picture 1> defines Maya. <Video 1> is the preceding cut. <Audio 1> is voice for S1."
    result = refine_h3_prompt(
        current_prompt=original, user_instruction="Make the camera movement slower.",
        shot_facts={"scene_id": "scene-1"}, asset_intents=[{"asset_id": "img-1", "intent": "Maya identity"}],
        reference_map=reference_map, shot_plan_revision="shot-rev-3", provider="codex",
        generator=lambda **kwargs: {"proposed_prompt": "<Picture 1> defines Maya. <Video 1> is the preceding cut; continue from it. <Audio 1> is Maya's voice reference for Subject 1 (S1). Slow the camera movement.",
                                   "change_summary": ["Slowed camera movement."], "warnings": []})
    assert result["lint"]["ok"] is True
    assert result["assets_unchanged"] is True
    assert result["applied"] is False
    assert result["shot_plan_revision"] == "shot-rev-3"
    assert "--- current-prompt" in result["diff"]
    assert "+++ proposed-prompt" in result["diff"]
    assert "+<Picture 1>" in result["diff"]
    assert "Slow the camera movement." in result["diff"]
    assert "asset_ids" not in result
    assert refine_proposal_is_current(result, result["base_input_hash"]) is True
    assert refine_proposal_is_current(result, "changed-input-hash") is False


def test_refine_proposal_can_be_returned_but_lint_blocks_changed_reference_tags():
    result = refine_h3_prompt(
        current_prompt="<Picture 1> is a character reference.", user_instruction="Add a camera push-in.",
        shot_facts={}, asset_intents=[], reference_map=_reference_map(), shot_plan_revision="rev-1",
        generator=lambda **_kwargs: {"proposed_prompt": "Use <Picture 1> and also <Video 99>.",
                                    "change_summary": [], "warnings": []})
    assert result["lint"]["ok"] is False
    assert result["applied"] is False


def test_director_reviews_long_story_one_chunk_at_a_time_and_requires_confidence():
    calls = []
    revision = {"revision_id": "story-canon-123456789abc", "story_goal": "Escape",
                "chunks": [{"chunk_id": f"story_chunk_{index:04d}", "source_excerpt": f"Source {index}",
                            "expanded_text": f"Expanded {index}", "source_facts": [], "inferred_details": []}
                           for index in range(1, 4)]}

    def generator(*, prompt, **_kwargs):
        calls.append(prompt)
        return {"decision": "approve", "confidence": 0.9, "issues": [], "repair_instruction": ""}

    result = review_story_revision(revision=revision, provider="codex", generator=generator)
    assert result["accepted"] is True
    assert len(calls) == 3
    assert [item["chunk_id"] for item in result["reviews"]] == ["story_chunk_0001", "story_chunk_0002", "story_chunk_0003"]
    assert "Source 1" in calls[0] and "Source 2" not in calls[0]
    assert "Source 2" in calls[1] and "Source 1" not in calls[1]
    assert "Source 3" in calls[2] and "Source 2" not in calls[2]
    assert 'labelled "Inferred:" and recorded in inferred_details' in calls[0]
    assert "changes a\nrelationship, event order or outcome" in calls[0]


def test_director_review_repair_or_low_confidence_never_auto_accepts():
    revision = {"story_goal": "Find truth", "chunks": [
        {"chunk_id": "story_chunk_0001", "source_excerpt": "The clue is lost.", "expanded_text": "The clue is lost."}]}
    def provider_response(*, prompt, **_kwargs):
        if prompt.startswith("You are the story-development writer"):
            import json
            source = json.loads(prompt.split("Exact source text as a JSON string (decode it; preserve every character):\n", 1)[1].split("\n\n", 1)[0])
            return {"chunk_id": "story_chunk_0001", "source_excerpt": source,
                    "source_facts": [{"quote": "The", "start": 0, "end": 3, "category": "other"}],
                    "expanded_text": "Revised with consequence.", "inferred_details": [],
                    "continuity_summary": "The clue is lost.", "story_goal": "Find truth.",
                    "tone": [], "continuity_rules": [], "visual_style_notes": []}
        return {"decision": "repair", "confidence": 0.98, "issues": ["Consequence missing."],
                "repair_instruction": "Add the consequence."}
    result = review_story_revision(revision=revision, generator=provider_response)
    assert result["accepted"] is False
    assert result["decision"] == "repair"
    assert result["repair_instructions"] == ["Add the consequence."]
    assert result["reviews"][0]["repair_attempted"] is True

    def low_confidence_provider(*, prompt, **kwargs):
        if prompt.startswith("You are the story-development writer"):
            return provider_response(prompt=prompt, **kwargs)
        return {"decision": "approve", "confidence": 0.4, "issues": [], "repair_instruction": ""}
    uncertain = review_story_revision(revision=revision, generator=low_confidence_provider)
    assert uncertain["accepted"] is False


def test_story_director_performs_one_targeted_chunk_repair_and_rechecks_it():
    calls = []
    source = "Asha discovers the key."

    def generator(*, prompt, **_kwargs):
        calls.append(prompt)
        if prompt.startswith("You are the story-development writer"):
            marker = "Exact source text as a JSON string (decode it; preserve every character):\n"
            exact_source = json.loads(prompt.split(marker, 1)[1].split("\n\n", 1)[0])
            return {"chunk_id": "story_chunk_0001", "source_excerpt": exact_source,
                    "source_facts": [{"quote": "Asha", "start": 0, "end": 4, "category": "character"}],
                    "expanded_text": "Asha discovers the brass key and understands its importance.",
                    "inferred_details": ["Inference: the key is brass."],
                    "continuity_summary": "Asha now has the key.", "story_goal": "Find the vault.",
                    "tone": ["mystery"], "continuity_rules": ["Keep the key with Asha."],
                    "visual_style_notes": ["Low-key light."]}
        if len([call for call in calls if call.startswith("You are the supervising Director")]) == 1:
            return {"decision": "repair", "confidence": 0.9, "issues": ["Key consequence needs clarity."],
                    "repair_instruction": "Clarify why the key matters, without changing source facts."}
        return {"decision": "approve", "confidence": 0.94, "issues": [], "repair_instruction": ""}

    revision = {"title": "The Vault", "story_goal": "Find the vault.", "continuity_rules": [],
                "tone": ["mystery"], "chunks": [{"chunk_id": "story_chunk_0001", "index": 4,
                    "source_start": 100, "source_end": 100 + len(source), "source_excerpt": source,
                    "source_facts": [], "expanded_text": "Asha finds a key.", "inferred_details": []}]}
    result = review_story_revision(revision=revision, provider="codex", generator=generator)
    assert result["accepted"] is True
    assert result["repaired_chunks"]["story_chunk_0001"]["index"] == 4
    fact = result["repaired_chunks"]["story_chunk_0001"]["source_facts"][0]
    assert fact["source_start"] == 100 and fact["text"] == "Asha"
    assert result["reviews"][0]["repair_attempted"] is True
    assert len(calls) == 3  # initial review, one bounded repair, one verification review


def test_text_stage_director_reviews_each_stable_unit_and_repairs_content_only_once():
    calls = []
    revision = {"stage": "scenes", "complete": True,
        "expected_unit_ids": ["scene-01", "scene-02"],
        "completed_unit_ids": ["scene-01", "scene-02"],
        "items": [{"unit_id": "scene-01", "source_chunk_ids": ["chunk-1"],
                   "content": {"description": "Mira enters."}},
                  {"unit_id": "scene-02", "source_chunk_ids": ["chunk-2"],
                   "content": {"description": "Mira leaves."}}]}

    def generator(*, prompt, **_kwargs):
        calls.append(prompt)
        if "Repair only the content" in prompt:
            return {"content": {"description": "Mira sees the signal and leaves."}}
        if '"description": "Mira enters."' in prompt:
            return {"decision": "repair", "confidence": 0.9, "issues": ["Motivation absent."],
                    "repair_instruction": "Connect her exit to the signal."}
        return {"decision": "approve", "confidence": 0.93, "issues": [], "repair_instruction": ""}

    result = review_text_stage_revision(revision=revision, provider="codex", generator=generator)
    assert result["accepted"] is True
    assert result["repair_attempts"] == 1
    assert result["items"][0]["unit_id"] == "scene-01"
    assert result["items"][0]["source_chunk_ids"] == ["chunk-1"]
    assert result["items"][0]["content"]["description"] == "Mira sees the signal and leaves."
    assert result["items"][1]["unit_id"] == "scene-02"
    assert len(calls) == 4  # review/repair/review for unit 1, review for unit 2


def test_text_stage_director_holds_unresolved_and_rejects_missing_unit_ids():
    revision = {"stage": "dialogue", "complete": True,
        "expected_unit_ids": ["line-1"], "completed_unit_ids": ["line-1"],
        "items": [{"unit_id": "line-1", "content": {"line": "Go."}}]}
    unresolved = review_text_stage_revision(revision=revision, generator=lambda **_kwargs: {
        "decision": "repair", "confidence": 0.95, "issues": ["Speaker unclear."],
        "repair_instruction": "Clarify the speaker."} if "Repair only" not in _kwargs["prompt"] else {"content": {"line": "Go."}})
    assert unresolved["accepted"] is False
    broken = {**revision, "completed_unit_ids": []}
    with pytest.raises(DirectorContractError, match="stable unit IDs"):
        review_text_stage_revision(revision=broken, generator=lambda **_kwargs: {})


def test_dialogue_reviewer_receives_canonical_speaker_identity_map():
    prompts = []
    revision = {"stage": "dialogue", "complete": True,
        "expected_unit_ids": ["shot-01"], "completed_unit_ids": ["shot-01"],
        "items": [{"unit_id": "shot-01", "character_ids": ["char-mira"],
            "scene_context": {"characters": ["Mira"]},
            "content": {"dialogue": [{"speaker_id": "char-mira", "text": "We should go."}]}}]}

    def generator(*, prompt, **_kwargs):
        prompts.append(prompt)
        return {"decision": "approve", "confidence": 0.95, "issues": [], "repair_instruction": ""}

    result = review_text_stage_revision(revision=revision, generator=generator,
        review_context={"character_identity_map": {"char-mira": "Mira"}})

    assert result["accepted"] is True
    assert len(prompts) == 1
    assert '"char-mira": "Mira"' in prompts[0]
    assert "map each speaker_id to the named character" in prompts[0]


def test_shot_plan_director_review_receives_active_h3_rules_and_reference_context():
    prompts = []
    context = {"active_h3_prompt_rules": {"version": "h3_prompt_rules_v1",
        "content_hash": "a" * 64, "reference_roles": "Use refs by declared role.",
        "shot_prompt_contract": "Bind tags exactly."},
        "caller_context": {"reference_map": {"pictures": [{"tag": "<Picture 1>"}]}}}
    revision = {"stage": "shot_plans", "complete": True,
        "expected_unit_ids": ["shot-001"], "completed_unit_ids": ["shot-001"],
        "items": [{"unit_id": "shot-001", "content": {"prompt": "Mira enters."}}]}

    def generator(*, prompt, **_kwargs):
        prompts.append(prompt)
        return {"decision": "approve", "confidence": 0.95, "issues": [], "repair_instruction": ""}

    result = review_text_stage_revision(revision=revision, generator=generator, review_context=context)
    assert result["accepted"] is True
    assert len(prompts) == 1
    assert "Use refs by declared role." in prompts[0]
    assert "Bind tags exactly." in prompts[0]
    assert '"<Picture 1>"' in prompts[0]


def test_scene_review_receives_neighboring_transition_context_during_review_and_repair():
    prompts = []
    revision = {"stage": "scenes", "complete": True,
        "expected_unit_ids": ["scene-01", "scene-02"],
        "completed_unit_ids": ["scene-01", "scene-02"],
        "items": [
            {"unit_id": "scene-01", "source_chunk_ids": ["chunk-1"],
             "content": {"scene_index": 1, "title": "The lighthouse", "location": "the lighthouse",
                         "characters": ["Arun"], "summary": "Arun finds a key and leaves for the cafe.",
                         "shots": [{"beat": "Arun leaves with the key.", "continuity": "He carries the key."}]}},
            {"unit_id": "scene-02", "source_chunk_ids": ["chunk-1"],
             "content": {"scene_index": 2, "title": "Mira's cafe", "location": "Mira's cafe",
                         "characters": ["Arun", "Mira"], "summary": "Arun arrives with the key.",
                         "shots": [{"beat": "Arun enters carrying the key."}]}},
        ]}

    scene_one_reviews = 0

    def generator(*, prompt, **_kwargs):
        prompts.append(prompt)
        if "Repair only the content" in prompt:
            return {"content": revision["items"][0]["content"]}
        if ('Unit: {"unit_id": "scene-01"' in prompt
                and "Adjacent scene context" in prompt):
            nonlocal scene_one_reviews
            scene_one_reviews += 1
            if scene_one_reviews == 1:
                return {"decision": "repair", "confidence": 0.9, "issues": ["Clarify the transition."],
                        "repair_instruction": "Keep the established departure and arrival coherent."}
        return {"decision": "approve", "confidence": 0.95, "issues": [], "repair_instruction": ""}

    result = review_text_stage_revision(revision=revision, generator=generator)
    assert result["accepted"] is True
    assert result["items"][0]["unit_id"] == "scene-01"
    assert result["items"][0]["source_chunk_ids"] == ["chunk-1"]
    assert result["items"][1]["unit_id"] == "scene-02"
    scene_one_prompts = [prompt for prompt in prompts
        if 'Unit: {"unit_id": "scene-01"' in prompt
        or 'Current unit: {"unit_id": "scene-01"' in prompt]
    assert len(scene_one_prompts) == 3  # review, content-only repair, review
    assert all("Mira's cafe" in prompt and "Arun enters carrying the key." in prompt
               for prompt in scene_one_prompts)
    assert all("do not call that missing continuity" in prompt for prompt in scene_one_prompts)


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_visual_fixed_design_reaches_review_and_bounded_repair(repair_succeeds):
    import copy
    design = "Small brown dog with a pale chest, wearing a red collar and leash."
    content = {"visual_brief": "The dog waits.", "continuity": {"visible_characters_and_animal": [
        {"id": "dog", "proposed_design_choice": "A black dog."}]}}
    revision = {"stage": "visual_briefs", "complete": True, "expected_unit_ids": ["visual-1"],
        "completed_unit_ids": ["visual-1"], "items": [{"unit_id": "visual-1", "content": content}]}
    calls = []
    def generate(*, prompt, **kwargs):
        calls.append(prompt)
        assert design in prompt
        if "Repair only the content" in prompt:
            repaired = copy.deepcopy(content)
            if repair_succeeds:
                repaired["continuity"]["visible_characters_and_animal"][0]["proposed_design_choice"] = design
            return {"content": repaired}
        return {"decision": "approve", "confidence": 0.99, "issues": [], "repair_instruction": ""}
    result = review_text_stage_revision(revision=revision, generator=generate,
        review_context={"caller_context": {"fixed_master_designs": {"dog": design}}})
    assert result["accepted"] is repair_succeeds
    assert result["repair_attempts"] == 1
    assert len(calls) == 3
    assert revision["items"][0]["content"] == content
