from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json

import pytest

from story_builder.services.production_ledger import (
    LedgerConflict, LedgerNotFound, ProductionLedger,
)


def test_run_creation_is_durable_idempotent_and_project_scoped(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    first = ProductionLedger(path)
    config = {"story": "A short story", "mode": "manual", "provider": "codex"}
    created = first.create_run(project_id="p1", idempotency_key="start-1", config=config)
    again = ProductionLedger(path).create_run(project_id="p1", idempotency_key="start-1", config=config)

    assert created["run_id"] == again["run_id"]
    assert again["config"] == config
    assert ProductionLedger(path).get_run(project_id="p1", run_id=created["run_id"])["events"][0]["event_type"] == "run_created"
    with pytest.raises(LedgerConflict):
        first.create_run(project_id="p1", idempotency_key="start-1", config={"story": "different"})
    with pytest.raises(LedgerNotFound):
        first.get_run(project_id="p2", run_id=created["run_id"])


def test_run_event_history_is_bounded_and_returns_latest_events_in_order(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "test"})
    for index in range(20):
        ledger.record_run_event(project_id="p1", run_id=run["run_id"],
            event_type="fixture_event", payload={"index": index})

    recent = ledger.get_run(project_id="p1", run_id=run["run_id"], event_limit=10)
    complete = ledger.get_run(project_id="p1", run_id=run["run_id"], event_limit=100)

    assert recent["event_history_truncated"] is True
    assert [event["payload"].get("index") for event in recent["events"]] == list(range(10, 20))
    assert complete["event_history_truncated"] is False
    assert len(complete["events"]) == 21


def test_run_listing_is_project_scoped_and_returns_summaries(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    older = ledger.create_run(project_id="p1", idempotency_key="older", config={"story": "old"})
    newer = ledger.create_run(project_id="p1", idempotency_key="newer", config={"story": "new"})
    ledger.create_run(project_id="p2", idempotency_key="other", config={"story": "other"})
    ledger.queue_take(project_id="p1", run_id=older["run_id"], shot_id="shot", take_id="take",
                      idempotency_key="take", input_snapshot={"prompt": "test"})

    rows = ledger.list_runs(project_id="p1")
    assert {row["run_id"] for row in rows} == {older["run_id"], newer["run_id"]}
    assert all("takes" not in row and "events" not in row for row in rows)
    assert ledger.list_runs(project_id="p1", limit=1)[0]["run_id"] == rows[0]["run_id"]


def test_run_event_deduplication_survives_concurrent_replay_and_is_run_scoped(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "ledger.sqlite3"
    ledger = ProductionLedger(path)
    runs = [ledger.create_run(project_id="p1", idempotency_key=key, config={}) for key in ("first", "second")]

    def record(_index):
        ProductionLedger(path).record_run_event(project_id="p1", run_id=runs[0]["run_id"],
            event_type="binding_blocked", dedupe_key="revision-1", payload={"reason": "invalid"})

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(record, range(12)))
    ledger.record_run_event(project_id="p1", run_id=runs[1]["run_id"],
        event_type="binding_blocked", dedupe_key="revision-1", payload={"reason": "invalid"})
    ledger.record_run_event(project_id="p1", run_id=runs[0]["run_id"],
        event_type="binding_blocked", dedupe_key="revision-2", payload={"reason": "invalid"})
    with ledger._connect() as db:
        rows = db.execute("SELECT run_id,COUNT(*) AS count FROM production_events "
            "WHERE event_type='binding_blocked' GROUP BY run_id").fetchall()
    assert {row["run_id"]: row["count"] for row in rows} == {runs[0]["run_id"]: 2, runs[1]["run_id"]: 1}


def test_reconciling_unchanged_remote_state_does_not_append_duplicate_events(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "test"})
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
        idempotency_key="take", input_snapshot={"validation_hash": "a" * 64})
    ledger.transition_take(project_id="p1", take_id="t1", status="submitting")
    ledger.reserve_prompt_id(project_id="p1", take_id="t1")

    first = ledger.reconcile_remote_state(project_id="p1", take_id="t1", observed="absent",
        details={"code": "comfy_prompt_not_in_history"})
    event_count_after_transition = len(ledger.get_run(project_id="p1", run_id=run["run_id"])["events"])
    second = ledger.reconcile_remote_state(project_id="p1", take_id="t1", observed="absent",
        details={"code": "comfy_prompt_not_in_history"})

    assert first["status"] == second["status"] == "recovery_required"
    assert second["updated_at"] == first["updated_at"]
    assert len(ledger.get_run(project_id="p1", run_id=run["run_id"])["events"]) == event_count_after_transition


def test_concurrent_run_double_click_creates_one_run(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"

    def create() -> str:
        return ProductionLedger(path).create_run(
            project_id="p1", idempotency_key="same-click", config={"story": "fixed"}
        )["run_id"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        run_ids = list(pool.map(lambda _: create(), range(12)))
    assert len(set(run_ids)) == 1


def test_take_double_click_and_frozen_snapshot_conflict(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "x"})
    kwargs = dict(project_id="p1", run_id=run["run_id"], shot_id="shot-1", take_id="take-1",
                  idempotency_key="generate-shot-1", input_snapshot={"prompt": "same", "seed": 10})
    first = ledger.queue_take(**kwargs)
    again = ProductionLedger(ledger.path).queue_take(**kwargs)

    assert first["job_id"] == again["job_id"]
    assert first["status"] == "queued"
    with pytest.raises(LedgerConflict):
        ledger.queue_take(**{**kwargs, "input_snapshot": {"prompt": "changed", "seed": 10}})
    parent = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="shot-parent",
        take_id="parent", idempotency_key="parent-key", input_snapshot={"prompt": "parent"})
    child_kwargs = {**kwargs, "take_id": "child", "idempotency_key": "child-key",
        "input_snapshot": {"prompt": "child"},
        "parent_take_id": parent["take_id"]}
    child = ledger.queue_take(**child_kwargs)
    replayed = ledger.queue_take(**child_kwargs)
    assert replayed["job_id"] == child["job_id"]
    other_parent = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="other-parent",
        take_id="other-parent", idempotency_key="other-parent-key", input_snapshot={"prompt": "other"})
    with pytest.raises(LedgerConflict):
        ledger.queue_take(**{**child_kwargs, "parent_take_id": other_parent["take_id"]})


def test_child_waits_for_accepted_parent_then_becomes_queued(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "x"})
    parent = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
                              idempotency_key="k1", input_snapshot={"prompt": "first"})
    child = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s2", take_id="t2",
                              idempotency_key="k2", input_snapshot={"prompt": "second", "uses": "t1"},
                              parent_take_id="t1")
    assert child["status"] == "waiting_for_predecessor"

    ledger.transition_take(project_id="p1", take_id="t1", status="submitting")
    prompt = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]
    bound = ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=prompt)
    assert bound["status"] == "running"
    ledger.transition_take(project_id="p1", take_id="t1", status="collecting")
    ledger.transition_take(project_id="p1", take_id="t1", status="needs_review")
    ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="t1")

    full = ledger.get_run(project_id="p1", run_id=run["run_id"])
    by_take = {take["take_id"]: take for take in full["takes"]}
    assert by_take["t1"]["prompt_id"] == prompt
    assert by_take["t1"]["status"] == "accepted"
    assert by_take["t2"]["status"] == "queued"
    assert any(event["event_type"] == "predecessor_accepted" for event in full["events"])


def test_parent_take_must_belong_to_same_run_and_acceptance_cannot_release_legacy_cross_run_child(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run_a = ledger.create_run(project_id="p1", idempotency_key="run-a", config={"story": "a"})
    run_b = ledger.create_run(project_id="p1", idempotency_key="run-b", config={"story": "b"})
    parent = ledger.queue_take(project_id="p1", run_id=run_a["run_id"], shot_id="s1", take_id="parent-a",
        idempotency_key="parent-a", input_snapshot={})

    with pytest.raises(LedgerNotFound, match="project/run"):
        ledger.queue_take(project_id="p1", run_id=run_b["run_id"], shot_id="s2", take_id="child-b",
            idempotency_key="child-b", input_snapshot={}, parent_take_id=parent["take_id"])

    # Simulate a row written by the pre-fix ledger. Acceptance must remain run-scoped
    # even if a legacy or manually repaired database contains this invalid edge.
    now = "2026-10-05T00:00:00+00:00"
    with ledger._connect() as db:
        db.execute("INSERT INTO production_takes(job_id, project_id, run_id, shot_id, take_id, idempotency_key, "
            "input_hash, input_snapshot_json, status, parent_take_id, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("legacy-cross-run-job", "p1", run_b["run_id"], "s2", "legacy-cross-run-child",
             "legacy-cross-run-child", "hash", "{}", "waiting_for_predecessor", parent["take_id"], now, now))

    _put_take_in_review(ledger, "p1", parent["take_id"])
    ledger.accept_take(project_id="p1", run_id=run_a["run_id"], take_id=parent["take_id"])
    other_run = ledger.get_run(project_id="p1", run_id=run_b["run_id"])
    assert other_run["takes"][0]["status"] == "waiting_for_predecessor"
    with ledger._connect() as db:
        db.execute("UPDATE production_takes SET status='queued' WHERE job_id='legacy-cross-run-job'")
    assert ProductionLedger(ledger.path).claim_next_queued_take(lease_owner="restart-worker") is None
    assert ledger.get_run(project_id="p1", run_id=run_b["run_id"])["takes"][0]["status"] == "waiting_for_predecessor"


@pytest.mark.parametrize(("control_mode", "edit_after_queue", "expected_status"), [
    ("manual", False, "queued"),
    ("manual", True, "waiting_for_user"),
    ("semi", False, "waiting_for_user"),
    ("fully_automated", False, "waiting_for_user"),
])
def test_accepting_parent_only_auto_releases_unchanged_manual_child(
        tmp_path: Path, control_mode: str, edit_after_queue: bool, expected_status: str) -> None:
    ledger = ProductionLedger(tmp_path / f"{control_mode}-{edit_after_queue}.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run",
        config={"story": "x", "control_mode": control_mode})
    parent = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="parent",
        idempotency_key="parent", input_snapshot={"prompt": "first"})
    _put_take_in_review(ledger, "p1", "parent")
    request = {"shot_plan_revision_id": "shot-plan-r1", "prompt": "child prompt", "steps": 20,
        "images": [], "videos": [], "standalone_audios": []}
    ledger.record_run_event(project_id="p1", run_id=run["run_id"], event_type="shot_composer_draft_saved",
        payload={"shot_id": "s2", "revision": 1, "shot_plan_revision_id": "shot-plan-r1", "draft": request})
    child = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s2", take_id="child",
        idempotency_key="child", input_snapshot={"validation_request": request,
            "shot_plan_revision_id": "shot-plan-r1"}, parent_take_id=parent["take_id"])
    assert child["status"] == "waiting_for_predecessor"
    if edit_after_queue:
        edited = {**request, "prompt": "edited after queue"}
        ledger.record_run_event(project_id="p1", run_id=run["run_id"], event_type="shot_composer_draft_saved",
            payload={"shot_id": "s2", "revision": 2, "shot_plan_revision_id": "shot-plan-r1", "draft": edited})

    accepted = ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="parent")
    state = {row["take_id"]: row for row in ledger.get_run(project_id="p1", run_id=run["run_id"])["takes"]}
    assert accepted["accepted"] is True
    assert state["child"]["status"] == expected_status
    assert ("child" in accepted["released_child_take_ids"]) == (expected_status == "queued")
    assert ("child" in accepted["held_child_take_ids"]) == (expected_status == "waiting_for_user")
    claim = ledger.claim_next_queued_take(lease_owner="worker")
    assert (claim is None) == (expected_status == "waiting_for_user")


def test_prompt_id_cannot_be_rebound_and_illegal_transitions_fail(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "x"})
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
                      idempotency_key="k1", input_snapshot={})
    ledger.transition_take(project_id="p1", take_id="t1", status="submitting")
    reserved = ledger.reserve_prompt_id(project_id="p1", take_id="t1")
    ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=reserved["prompt_id"])
    with pytest.raises(LedgerConflict):
        ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id="prompt-2")
    with pytest.raises(LedgerConflict):
        ledger.transition_take(project_id="p1", take_id="t1", status="accepted")


def test_comfy_prompt_id_is_reserved_before_submit_and_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = ProductionLedger(path)
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "x"})
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
                      idempotency_key="k1", input_snapshot={"compiled_graph_hash": "abc"})
    ledger.transition_take(project_id="p1", take_id="t1", status="submitting")
    reserved = ledger.reserve_prompt_id(project_id="p1", take_id="t1")
    again = ProductionLedger(path).reserve_prompt_id(project_id="p1", take_id="t1")

    assert reserved["prompt_id"] == again["prompt_id"]
    assert reserved["status"] == "submitting"
    candidate = ProductionLedger(path).reconciliation_candidates(project_id="p1")[0]
    assert candidate["input_snapshot"] == {"compiled_graph_hash": "abc"}

    recovered = ProductionLedger(path).reconcile_remote_state(
        project_id="p1", take_id="t1", observed="running", details={"recovered_after_restart": True}
    )
    assert recovered["status"] == "running"
    assert recovered["prompt_id"] == reserved["prompt_id"]
    assert recovered["attempt"] == 1


def test_missing_reserved_comfy_prompt_requires_recovery_decision_not_resubmit(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "x"})
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
                      idempotency_key="k1", input_snapshot={})
    ledger.transition_take(project_id="p1", take_id="t1", status="submitting")
    prompt_id = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]

    recovered = ledger.reconcile_remote_state(project_id="p1", take_id="t1", observed="absent")

    assert recovered["status"] == "recovery_required"
    assert recovered["prompt_id"] == prompt_id
    assert "retry" not in recovered


def test_queued_cancel_is_local_and_retry_uses_new_attempt_prompt_id(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "x"})
    take = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
                             idempotency_key="k1", input_snapshot={"graph_hash": "g1"})
    cancelled = ledger.transition_take(project_id="p1", take_id="t1", status="cancelled")
    assert cancelled["status"] == "cancelled"
    assert cancelled["prompt_id"] is None  # queued cancellation never reached ComfyUI

    retry_take = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s2", take_id="t2",
                                  idempotency_key="k2", input_snapshot={"graph_hash": "g2"})
    ledger.transition_take(project_id="p1", take_id="t2", status="submitting")
    initial_prompt = ledger.reserve_prompt_id(project_id="p1", take_id="t2")["prompt_id"]
    ledger.reconcile_remote_state(project_id="p1", take_id="t2", observed="error", details={"code": "smoke"})
    ledger.transition_take(project_id="p1", take_id="t2", status="retrying")
    queued_again = ledger.transition_take(project_id="p1", take_id="t2", status="queued")
    assert queued_again["status"] == "queued"
    assert queued_again["attempt"] == 2
    assert queued_again["prompt_id"] is None
    ledger.transition_take(project_id="p1", take_id="t2", status="submitting")
    next_prompt = ledger.reserve_prompt_id(project_id="p1", take_id="t2")["prompt_id"]
    assert next_prompt != initial_prompt
    assert retry_take["take_id"] == "t2"


def test_single_global_gpu_claim_and_durable_output_records(tmp_path: Path):
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "x"})
    first = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
        idempotency_key="k1", input_snapshot={"validation_hash": "a" * 64})
    ledger.queue_take(project_id="p2", run_id=ledger.create_run(project_id="p2", idempotency_key="run2",
        config={"story": "y"})["run_id"], shot_id="s2", take_id="t2", idempotency_key="k2",
        input_snapshot={"validation_hash": "b" * 64})
    claimed = ledger.claim_next_queued_take(lease_owner="worker-a")
    assert claimed["take_id"] == first["take_id"] and claimed["status"] == "submitting"
    assert claimed["lease_owner"] == "worker-a"
    assert ledger.claim_next_queued_take(lease_owner="worker-b") is None
    prompt_id = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]
    ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=prompt_id)
    ledger.transition_take(project_id="p1", take_id="t1", status="collecting")
    outputs = [{"asset_id": "pa-0123456789abcdef", "kind": "video", "sha256": "f" * 64}]
    updated = ledger.set_take_outputs(project_id="p1", take_id="t1", outputs=outputs)
    assert updated["output_hashes"] == outputs
    ledger.transition_take(project_id="p1", take_id="t1", status="needs_review")
    ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="t1")
    next_claim = ledger.claim_next_queued_take(lease_owner="worker-b")
    assert next_claim["take_id"] == "t2"


def test_concurrent_workers_cannot_claim_two_gpu_takes(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = ProductionLedger(path)
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "x"})
    for index in range(2):
        ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id=f"s{index}",
            take_id=f"t{index}", idempotency_key=f"k{index}", input_snapshot={"shot": index})

    def claim(worker: str):
        # Each worker has its own ledger object/SQLite connection, as separate
        # API worker processes would, while sharing only the durable database.
        return ProductionLedger(path).claim_next_queued_take(lease_owner=worker)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ("worker-a", "worker-b")))

    claimed = [take for take in claims if take is not None]
    assert len(claimed) == 1
    assert claimed[0]["status"] == "submitting"
    assert claimed[0]["lease_owner"] in {"worker-a", "worker-b"}
    run_state = ProductionLedger(path).get_run(project_id="p1", run_id=run["run_id"])
    assert sum(take["status"] == "submitting" for take in run_state["takes"]) == 1
    assert sum(take["status"] == "queued" for take in run_state["takes"]) == 1


def _put_take_in_review(ledger: ProductionLedger, project_id: str, take_id: str) -> None:
    ledger.transition_take(project_id=project_id, take_id=take_id, status="submitting")
    prompt_id = ledger.reserve_prompt_id(project_id=project_id, take_id=take_id)["prompt_id"]
    ledger.bind_prompt_id(project_id=project_id, take_id=take_id, prompt_id=prompt_id)
    ledger.transition_take(project_id=project_id, take_id=take_id, status="collecting")
    ledger.transition_take(project_id=project_id, take_id=take_id, status="needs_review")


def test_parent_retake_previews_and_stales_only_confirmed_queued_children(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "x"})
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="parent-v1",
        idempotency_key="parent-v1", input_snapshot={"prompt": "first"})
    _put_take_in_review(ledger, "p1", "parent-v1")
    ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="parent-v1")
    queued_child = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s2",
        take_id="child-queued", idempotency_key="child-queued", input_snapshot={"uses": "parent-v1"},
        parent_take_id="parent-v1")
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s3",
        take_id="child-accepted", idempotency_key="child-accepted", input_snapshot={"uses": "parent-v1"},
        parent_take_id="parent-v1")
    _put_take_in_review(ledger, "p1", "child-accepted")
    ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="child-accepted")
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="parent-v2",
        idempotency_key="parent-v2", input_snapshot={"prompt": "retake"})
    _put_take_in_review(ledger, "p1", "parent-v2")
    waiting_on_retake = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s4",
        take_id="child-new-parent", idempotency_key="child-new-parent",
        input_snapshot={"uses": "parent-v2"}, parent_take_id="parent-v2")
    assert waiting_on_retake["status"] == "waiting_for_predecessor"

    preview = ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="parent-v2")
    assert preview["accepted"] is False and preview["requires_confirmation"] is True
    assert [row["take_id"] for row in preview["queued_children_to_stale"]] == [queued_child["take_id"]]
    preview_state = {row["take_id"]: row for row in ledger.get_run(project_id="p1", run_id=run["run_id"])["takes"]}
    assert preview_state["parent-v2"]["status"] == "needs_review"

    confirmed = ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="parent-v2",
        confirm_stale_child_ids=[queued_child["take_id"]])
    assert confirmed["accepted"] is True
    final = {row["take_id"]: row for row in ledger.get_run(project_id="p1", run_id=run["run_id"])["takes"]}
    assert final["child-queued"]["status"] == "stale"
    assert final["child-accepted"]["status"] == "accepted"
    assert final["parent-v1"]["status"] == "accepted"
    assert final["parent-v2"]["status"] == "accepted"
    assert final["child-new-parent"]["status"] == "queued"


def test_parent_retake_confirmation_is_recomputed_and_active_child_blocks(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "x"})
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="parent-v1",
        idempotency_key="parent-v1", input_snapshot={})
    _put_take_in_review(ledger, "p1", "parent-v1")
    ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="parent-v1")
    first_child = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s2",
        take_id="child-first", idempotency_key="child-first", input_snapshot={}, parent_take_id="parent-v1")
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="parent-v2",
        idempotency_key="parent-v2", input_snapshot={"retake": 1})
    _put_take_in_review(ledger, "p1", "parent-v2")
    preview = ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="parent-v2")
    assert [row["take_id"] for row in preview["queued_children_to_stale"]] == [first_child["take_id"]]

    # A child added after the first preview is not silently invalidated by an
    # old/empty confirmation token; the caller receives a fresh preview.
    new_child = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s2",
        take_id="child-new", idempotency_key="child-new", input_snapshot={}, parent_take_id="parent-v1")
    changed = ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="parent-v2",
        confirm_stale_child_ids=[first_child["take_id"]])
    assert changed["accepted"] is False
    assert {row["take_id"] for row in changed["queued_children_to_stale"]} == {
        first_child["take_id"], new_child["take_id"]}

    accepted = ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="parent-v2",
        confirm_stale_child_ids=[first_child["take_id"], new_child["take_id"]])
    assert accepted["accepted"] is True
    state = {row["take_id"]: row for row in ledger.get_run(project_id="p1", run_id=run["run_id"])["takes"]}
    assert state["child-first"]["status"] == state["child-new"]["status"] == "stale"


def test_active_child_blocks_parent_retake_acceptance(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "x"})
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="parent-v1",
        idempotency_key="parent-v1", input_snapshot={})
    _put_take_in_review(ledger, "p1", "parent-v1")
    ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="parent-v1")
    child = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s2",
        take_id="child-active", idempotency_key="child-active", input_snapshot={}, parent_take_id="parent-v1")
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="parent-v2",
        idempotency_key="parent-v2", input_snapshot={"retake": 1})
    _put_take_in_review(ledger, "p1", "parent-v2")
    ledger.transition_take(project_id="p1", take_id=child["take_id"], status="submitting")

    blocked = ledger.accept_take(project_id="p1", run_id=run["run_id"], take_id="parent-v2")
    assert blocked["blocked_by_active_children"] is True
    state = {row["take_id"]: row for row in ledger.get_run(project_id="p1", run_id=run["run_id"])["takes"]}
    assert state["parent-v2"]["status"] == "needs_review"
    assert state["child-active"]["status"] == "submitting"


def test_successful_third_attempt_clears_current_error_but_keeps_failure_events(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "retry"})
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
        idempotency_key="take", input_snapshot={"prompt": "test"})

    for attempt in (1, 2):
        ledger.transition_take(project_id="p1", take_id="t1", status="submitting")
        failed = ledger.transition_take(project_id="p1", take_id="t1", status="failed", payload={
            "code": "production_prepare_failed", "attempt": attempt})
        assert failed["error"]["code"] == "production_prepare_failed"
        ledger.transition_take(project_id="p1", take_id="t1", status="retrying")
        queued = ledger.transition_take(project_id="p1", take_id="t1", status="queued")
        assert queued["attempt"] == attempt + 1
        assert queued["error"] is None

    ledger.transition_take(project_id="p1", take_id="t1", status="submitting")
    prompt_id = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]
    ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=prompt_id)
    collecting = ledger.reconcile_remote_state(project_id="p1", take_id="t1", observed="success")
    assert collecting["status"] == "collecting"
    completed = ledger.transition_take(project_id="p1", take_id="t1", status="needs_review")

    assert completed["attempt"] == 3
    assert completed["status"] == "needs_review"
    assert completed["error"] is None
    persisted = ProductionLedger(ledger.path).get_run(project_id="p1", run_id=run["run_id"])
    failures = [event for event in persisted["events"]
        if event["event_type"] == "take_transition"
        and event["payload"].get("code") == "production_prepare_failed"]
    assert [event["payload"]["attempt"] for event in failures] == [1, 2]
    assert next(row for row in persisted["takes"] if row["take_id"] == "t1")["error"] is None


def test_successful_take_projection_hides_legacy_stored_error_but_keeps_failure_history(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "legacy"})
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
        idempotency_key="take", input_snapshot={"prompt": "test"})
    ledger.transition_take(project_id="p1", take_id="t1", status="submitting")
    ledger.transition_take(project_id="p1", take_id="t1", status="failed", payload={
        "code": "production_prepare_failed", "message": "old attempt failed"})
    ledger.transition_take(project_id="p1", take_id="t1", status="retrying")
    ledger.transition_take(project_id="p1", take_id="t1", status="queued")
    ledger.transition_take(project_id="p1", take_id="t1", status="submitting")
    prompt_id = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]
    ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=prompt_id)
    ledger.reconcile_remote_state(project_id="p1", take_id="t1", observed="success")
    ledger.transition_take(project_id="p1", take_id="t1", status="needs_review")

    # Simulate a successful row written by the old implementation, where
    # transition settlement left a prior attempt's error_json behind.
    with ledger._connect() as db:
        db.execute("UPDATE production_takes SET error_json=? WHERE project_id=? AND take_id=?",
            ('{"code":"production_prepare_failed","message":"old attempt failed"}', "p1", "t1"))

    reopened = ProductionLedger(ledger.path).get_run(project_id="p1", run_id=run["run_id"])
    take = next(row for row in reopened["takes"] if row["take_id"] == "t1")
    assert take["status"] == "needs_review"
    assert take["error"] is None
    with ledger._connect() as db:
        stored_error = db.execute("SELECT error_json FROM production_takes WHERE project_id=? AND take_id=?",
            ("p1", "t1")).fetchone()["error_json"]
    assert json.loads(stored_error)["code"] == "production_prepare_failed"
    failures = [event for event in reopened["events"]
        if event["event_type"] == "take_transition"
        and event["payload"].get("code") == "production_prepare_failed"]
    assert len(failures) == 1


def _unavailable_video_review(ledger):
    run = ledger.create_run(project_id='p', idempotency_key='r', config={'control_mode': 'fully_automated'})
    ledger.queue_take(project_id='p', run_id=run['run_id'], shot_id='s', take_id='t', idempotency_key='t', input_snapshot={})
    ledger.transition_take(project_id='p', take_id='t', status='submitting')
    prompt = ledger.reserve_prompt_id(project_id='p', take_id='t')
    ledger.transition_take(project_id='p', take_id='t', status='collecting')
    ledger.set_take_outputs(project_id='p', take_id='t', outputs=[{'sha256': 'a'*64}])
    ledger.transition_take(project_id='p', take_id='t', status='needs_review')
    take = ledger.claim_next_director_video_review(owner_token='owner')
    review = ledger.record_director_video_review(take=take, owner_token='owner', decision={
        'action': 'blocked', 'reason': 'Director video review unavailable: ReasoningProviderError: usage limit'})
    ledger.resolve_director_video_review(job_id=take['job_id'], status='blocked')
    ledger.release_director_video_review_claim(job_id=take['job_id'], owner_token='owner')
    return run, take, review


def test_provider_review_retry_preserves_prompt_outputs_and_archives_failure(tmp_path):
    ledger = ProductionLedger(tmp_path/'l.db')
    run, take, review = _unavailable_video_review(ledger)
    before = ledger.get_run(project_id='p', run_id=run['run_id'])['takes'][0]
    ledger.retry_unavailable_director_video_review(project_id='p', run_id=run['run_id'], take_id='t', review_id=review['review_id'])
    reopened = ProductionLedger(ledger.path).get_run(project_id='p', run_id=run['run_id'])
    after = reopened['takes'][0]
    assert (after['prompt_id'], after['attempt'], after['output_hashes'], after['status']) == (before['prompt_id'], before['attempt'], before['output_hashes'], 'needs_review')
    archived = [e for e in reopened['events'] if e['event_type']=='director_video_unavailable_review_retried']
    assert len(archived)==1 and archived[0]['payload']['archived_review']['review_id']==review['review_id']
    with pytest.raises(LedgerConflict):
        ledger.retry_unavailable_director_video_review(project_id='p', run_id=run['run_id'], take_id='t', review_id=review['review_id'])
    claimed = ledger.claim_next_director_video_review(owner_token='next')
    assert claimed['review_attempt_count']==2 and claimed['take_id']=='t'
    assert ledger.claim_next_director_video_review(owner_token='foreign') is None


@pytest.mark.parametrize('rejection', ['quality', 'lease', 'budget', 'wrong_project'])
def test_provider_review_retry_rejects_quality_active_owner_exhaustion_and_wrong_scope(tmp_path, rejection):
    ledger = ProductionLedger(tmp_path/'l.db')
    run, take, review = _unavailable_video_review(ledger)
    with ledger._connect() as db:
        if rejection=='quality':
            db.execute('UPDATE production_video_director_reviews SET decision_json=?', (json.dumps({'action':'blocked','reason':'Uncertain speech'}),))
        elif rejection=='lease':
            db.execute("UPDATE production_video_director_review_claims SET lease_until='2999-01-01T00:00:00+00:00'")
        elif rejection=='budget':
            db.execute('UPDATE production_video_director_review_claims SET attempt_count=3')
    with pytest.raises((LedgerConflict, LedgerNotFound)):
        ledger.retry_unavailable_director_video_review(project_id='other' if rejection=='wrong_project' else 'p', run_id=run['run_id'], take_id='t', review_id=review['review_id'])
    assert ledger.get_run(project_id='p', run_id=run['run_id'])['takes'][0]['director_review'] is not None


@pytest.mark.parametrize('invalid',[None,'hash','quality','lease','budget'])
def test_human_name_verification_reopens_only_exact_scoped_hold_and_preserves_audit(tmp_path,invalid):
    ledger=ProductionLedger(tmp_path/'l.db');run,take,old=_unavailable_video_review(ledger)
    decision={'action':'retake','video_sha256':'a'*64,
        'native_audio':{'text':'Aaron, the neighbors are here.','expected_lines':['Arun, the neighbors are here.']},
        'criteria':[{'name':'Required dialogue','passed':False}]}
    with ledger._connect() as db:
        db.execute('UPDATE production_video_director_reviews SET decision_json=?,error_json=?',
            (json.dumps(decision),json.dumps({'code':'other_quality_hold' if invalid=='quality' else 'native_audio_name_uncertain'})))
        if invalid=='lease':db.execute("UPDATE production_video_director_review_claims SET lease_until='2999-01-01T00:00:00+00:00'")
        if invalid=='budget':db.execute('UPDATE production_video_director_review_claims SET attempt_count=3')
    args={'project_id':'p','run_id':run['run_id'],'take_id':'t','review_id':old['review_id'],
        'video_sha256':'b'*64 if invalid=='hash' else 'a'*64,'statement':'The intended line is clear; no unwanted speech'}
    if invalid:
        with pytest.raises(LedgerConflict):ledger.reopen_name_uncertain_review_with_human_verification(**args)
    else:
        evidence=ledger.reopen_name_uncertain_review_with_human_verification(**args)
        reopened=ProductionLedger(ledger.path).get_run(project_id='p',run_id=run['run_id'])
        assert reopened['takes'][0]['status']=='needs_review'
        assert reopened['takes'][0]['prompt_id']==take['prompt_id']
        archived=[e for e in reopened['events'] if e['event_type']=='director_video_human_audio_verification_recorded']
        assert len(archived)==1 and archived[0]['payload']['archived_review']['decision']==decision
        assert archived[0]['payload']['verification']==evidence
        with pytest.raises(LedgerConflict):ledger.reopen_name_uncertain_review_with_human_verification(**args)

@pytest.mark.parametrize('invalid', [None, 'visual', 'mismatch', 'hash', 'lease', 'budget', 'retake'])
def test_matching_audio_confirmation_preserves_exact_hold_and_survives_event_window(tmp_path, invalid):
    ledger = ProductionLedger(tmp_path/'audio.db'); run, take, old = _unavailable_video_review(ledger)
    decision = {'action': 'retake' if invalid == 'retake' else 'blocked', 'video_sha256': 'a'*64,
        'native_audio': {'text': 'The storm is coming.', 'dialogue_match': invalid != 'mismatch'},
        'criteria': [{'name': 'Speaker confirmed', 'passed': False}]}
    if invalid == 'visual': decision['criteria'].append({'name': 'Wrong clothing', 'passed': False})
    with ledger._connect() as db:
        db.execute('UPDATE production_video_director_reviews SET decision_json=?,error_json=?',
            (json.dumps(decision), json.dumps({'code':'director_video_review_blocked'})))
        if invalid == 'lease': db.execute("UPDATE production_video_director_review_claims SET lease_until='2999-01-01T00:00:00+00:00'")
        if invalid == 'budget': db.execute('UPDATE production_video_director_review_claims SET attempt_count=3')
    args = dict(project_id='p', run_id=run['run_id'], take_id='t', review_id=old['review_id'],
        video_sha256='b'*64 if invalid == 'hash' else 'a'*64,
        statement='Maya’s line is clear; no unwanted speech', verification_scope='matching_dialogue_audio_uncertainty')
    if invalid:
        with pytest.raises(LedgerConflict): ledger.reopen_name_uncertain_review_with_human_verification(**args)
        return
    before = ledger.get_run(project_id='p', run_id=run['run_id'])['takes'][0]
    verification = ledger.reopen_name_uncertain_review_with_human_verification(**args)
    for i in range(505): ledger.record_run_event(project_id='p', run_id=run['run_id'], event_type='later_event', payload={'n':i})
    reopened = ProductionLedger(ledger.path)
    evidence = reopened.human_audio_review_evidence(project_id='p', run_id=run['run_id'], job_id=take['job_id'])
    assert evidence['verification'] == verification and evidence['archived_review']['decision'] == decision
    assert reopened.human_audio_review_evidence(project_id='other', run_id=run['run_id'], job_id=take['job_id']) is None
    after = reopened.get_run(project_id='p', run_id=run['run_id'])['takes'][0]
    assert (after['prompt_id'],after['attempt'],after['output_hashes']) == (before['prompt_id'],before['attempt'],before['output_hashes'])
    assert reopened.claim_next_director_video_review(owner_token='final')['review_attempt_count'] == 2
    with pytest.raises(LedgerConflict): reopened.reopen_name_uncertain_review_with_human_verification(**args)


@pytest.mark.parametrize('invalid',[None,'hash','lease','budget','quality','already_child'])
def test_count_reassessment_is_exact_bounded_and_preserves_original_decision(tmp_path,invalid):
    ledger=ProductionLedger(tmp_path/'count.db');run,take,old=_unavailable_video_review(ledger)
    decision={'action':'retake','video_sha256':'a'*64,
        'evidence':[{'summary':'Five people and a dog.'},{'summary':'Four characters and a dog.'}],
        'native_audio':{'dialogue_match':True},
        'criteria':[{'name':'Required group visible','passed':False,'evidence':'Frame descriptions conflict.'}]}
    with ledger._connect() as db:
        db.execute('UPDATE production_video_director_reviews SET decision_json=?,error_json=?',
            (json.dumps(decision),json.dumps({'code':'other' if invalid=='quality' else 'native_video_evidence_uncertain'})))
        if invalid=='lease':db.execute("UPDATE production_video_director_review_claims SET lease_until='2999-01-01T00:00:00+00:00'")
        if invalid=='budget':db.execute('UPDATE production_video_director_review_claims SET attempt_count=3')
        if invalid=='already_child':db.execute("UPDATE production_video_director_reviews SET retake_take_id='child'")
    args=dict(project_id='p',run_id=run['run_id'],take_id='t',review_id=old['review_id'],video_sha256='b'*64 if invalid=='hash' else 'a'*64,
        observation='Exact clip inspection shows four people plus a dog; model count descriptions conflict.')
    if invalid:
        with pytest.raises(LedgerConflict):ledger.reopen_contradictory_count_review(**args)
        return
    ledger.reopen_contradictory_count_review(**args)
    state=ProductionLedger(ledger.path).get_run(project_id='p',run_id=run['run_id'])
    assert state['takes'][0]['director_review'] is None and state['takes'][0]['status']=='needs_review'
    archived=[e for e in state['events'] if e['event_type']=='director_video_count_evidence_reassessment']
    assert len(archived)==1 and archived[0]['payload']['archived_review']['decision']==decision
    claimed=ledger.claim_next_director_video_review(owner_token='recheck')
    assert claimed['review_attempt_count']==2
    with pytest.raises(LedgerConflict):ledger.reopen_contradictory_count_review(**args)


@pytest.mark.parametrize('invalid',[None,'budget','hash','complete_evidence','clothing'])
def test_audio_confirmation_can_refresh_only_old_incomplete_subject_cards(tmp_path,invalid):
    ledger=ProductionLedger(tmp_path/'subjects.db');run,take,old=_unavailable_video_review(ledger)
    d={'action':'retake','video_sha256':'a'*64,'native_audio':{'text':'Aaron, the neighbors are here.','expected_lines':['Arun, the neighbors are here.']},
       'criteria':[{'name':'Five subjects visible','passed':False,'evidence':'Neighbors are not individually described.'},{'name':'Native dialogue','passed':False,'evidence':'Arun/Aaron'}],
       'evidence':[{'summary':'Four people and a dog.','subjects':[{'name':'P1'},{'name':'P2'}]}]}
    if invalid=='complete_evidence':d['frame_analysis_subject_limit']=12
    if invalid=='clothing':d['criteria'].append({'name':'Wrong clothing','passed':False,'evidence':'Puffer instead of rain jacket.'})
    with ledger._connect() as db:
        db.execute('UPDATE production_video_director_reviews SET decision_json=?,error_json=?',(json.dumps(d),json.dumps({'code':'native_video_evidence_incomplete'})))
        if invalid=='budget':db.execute('UPDATE production_video_director_review_claims SET attempt_count=3')
    args=dict(project_id='p',run_id=run['run_id'],take_id='t',review_id=old['review_id'],video_sha256='b'*64 if invalid=='hash' else 'a'*64,
        statement='Intended name and line clear',refresh_visual_evidence=True)
    if invalid:
        with pytest.raises(LedgerConflict):ledger.reopen_name_uncertain_review_with_human_verification(**args)
        return
    ledger.reopen_name_uncertain_review_with_human_verification(**args)
    saved=ProductionLedger(ledger.path).human_audio_review_evidence(project_id='p',run_id=run['run_id'],job_id=take['job_id'])
    assert saved['refresh_visual_evidence'] is True and saved['archived_review']['decision']==d
    assert ledger.claim_next_director_video_review(owner_token='final')['review_attempt_count']==2
