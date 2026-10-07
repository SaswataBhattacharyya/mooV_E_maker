from pathlib import Path

from story_builder.services.production_ledger import ProductionLedger
from story_builder.services.production_reconciliation import reconcile_comfyui_takes


def _submitted_take(ledger: ProductionLedger, suffix: str = "1") -> dict:
    run = ledger.create_run(project_id="p1", idempotency_key=f"r-{suffix}", config={"story": suffix})
    ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id=f"shot-{suffix}", take_id=f"take-{suffix}",
                      idempotency_key=f"k-{suffix}", input_snapshot={"graph_hash": f"abc-{suffix}"})
    ledger.transition_take(project_id="p1", take_id=f"take-{suffix}", status="submitting")
    return ledger.reserve_prompt_id(project_id="p1", take_id=f"take-{suffix}")


def test_reconciles_prompt_still_running_without_resubmission(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    take = _submitted_take(ledger)
    requested: list[str] = []

    def get_json(url: str, **_kwargs):
        requested.append(url)
        return {"queue_pending": [], "queue_running": [[1, take["prompt_id"], {}, {}, []]]}

    report = reconcile_comfyui_takes(ledger, comfy_url="http://comfy.test", get_json=get_json)

    assert report["status"] == "completed"
    assert report["updated"][0]["status"] == "running"
    assert len(requested) == 1  # queue inspection only; never POST /prompt
    assert ledger.reconciliation_candidates(project_id="p1")[0]["prompt_id"] == take["prompt_id"]


def test_reconciles_completed_and_failed_history(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    first = _submitted_take(ledger, "1")
    report = reconcile_comfyui_takes(
        ledger, comfy_url="http://comfy.test",
        get_json=lambda url, **_: {first["prompt_id"]: {"status": {"status_str": "success", "completed": True}}},
    )
    assert report["updated"][0]["status"] == "collecting"

    second = _submitted_take(ledger, "2")
    history_rows = {
        first["prompt_id"]: {"status": {"status_str": "success", "completed": True}},
        second["prompt_id"]: {"status": {"status_str": "error", "messages": [["execution_error", {}]]}},
    }

    def get_history(url: str, **_kwargs):
        if url.endswith("/queue"):
            return {"queue_pending": [], "queue_running": []}
        prompt_id = url.rsplit("/", 1)[-1]
        return {prompt_id: history_rows[prompt_id]}

    report = reconcile_comfyui_takes(
        ledger, comfy_url="http://comfy.test",
        get_json=get_history,
    )
    assert next(row for row in report["updated"] if row["take_id"] == "take-2")["status"] == "failed"
    assert ledger.get_run(project_id="p1", run_id=first["run_id"])["events"]


def test_absent_prompt_becomes_recovery_required_not_requeued(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    take = _submitted_take(ledger, "3")
    report = reconcile_comfyui_takes(ledger, comfy_url="http://comfy.test", get_json=lambda *_args, **_kwargs: {})

    assert report["updated"][0]["status"] == "recovery_required"
    assert ledger.get_run(project_id="p1", run_id=take["run_id"])["takes"][0]["status"] == "recovery_required"


def test_comfy_unavailable_defers_without_changing_take(tmp_path: Path) -> None:
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    take = _submitted_take(ledger, "4")

    def unavailable(*_args, **_kwargs):
        raise OSError("ComfyUI not reachable")

    report = reconcile_comfyui_takes(ledger, comfy_url="http://comfy.test", get_json=unavailable)
    assert report["status"] == "deferred"
    assert ledger.reconciliation_candidates(project_id="p1")[0]["status"] == "submitting"
    assert take["prompt_id"]
