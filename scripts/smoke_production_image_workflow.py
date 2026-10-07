"""One-at-a-time disposable live smoke for a production image adapter.

Examples (repository root):
  PYTHONPATH=/home/riki/web_dev python3 scripts/smoke_production_image_workflow.py qwen_image_2512
  PYTHONPATH=/home/riki/web_dev python3 scripts/smoke_production_image_workflow.py z_image_turbo
  PYTHONPATH=/home/riki/web_dev python3 scripts/smoke_production_image_workflow.py qwen_image_edit_2511

This is an opt-in ComfyUI model execution. It refuses a busy queue or less
than 20 GiB of reported free VRAM. It never edits ComfyUI, Docker, or Conda.
After submission, if remote state becomes uncertain, it preserves staged input
and writes a recovery_pending manifest rather than deleting media in use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from story_builder.services.audio_catalog import comfyui_root
from story_builder.services.media_jobs import (
    comfy_submission_guard,
    collect_outputs,
    release_comfyui_models_if_idle,
)
from story_builder.services.gpu_runtime import inspect_gpu_runtime, record_gpu_telemetry
from story_builder.services.minimax_h3_media import cleanup_owned_media, sha256_file, stage_image_reference
from story_builder.services.production_image_workflows import (
    ImageWorkflowError, SPECS, compile_image_candidates, image_output_provenance,
)
try:  # Direct script execution places this directory on sys.path.
    from smoke_minimax_h3_dynamic import remove_hash_verified_comfy_outputs
except ModuleNotFoundError:  # Test/module import from the repository root.
    from scripts.smoke_minimax_h3_dynamic import remove_hash_verified_comfy_outputs


ROOT = Path(__file__).resolve().parents[1]
COMFY_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:3008").rstrip("/")
PROJECT_ID = "disposable-production-image-smoke"
FIXTURE_IMAGE = ROOT / "plan" / "image.png"
MIN_FREE_VRAM = 20 * 1024**3
PROMPT = (
    "A clear, original cinematic concept image of a small red umbrella on a "
    "wooden bench after rain, soft overcast daylight, realistic materials, "
    "single subject, balanced composition, no text or watermark."
)


def request_json(path: str, *, timeout: int = 15, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{COMFY_URL}{path}",
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers={} if payload is None else {"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        raise RuntimeError(f"ComfyUI returned HTTP {exc.code} for {path}: {detail[:4000]}") from exc


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def queue_is_idle() -> bool:
    queue = request_json("/queue")
    running, pending = queue.get("queue_running"), queue.get("queue_pending")
    if not isinstance(running, list) or not isinstance(pending, list):
        raise RuntimeError("ComfyUI /queue response is malformed; withholding submission.")
    return not running and not pending


def may_release_models(*, submitted: bool, status: str) -> bool:
    """Only unload after this runner owned a render and it is terminal."""
    return submitted and status in {"completed", "failed"}


def _main_locked() -> int:
    parser = argparse.ArgumentParser(description="Run exactly one disposable production image workflow smoke.")
    parser.add_argument("workflow_id", choices=sorted(SPECS))
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    args = parser.parse_args()
    if not 60 <= args.timeout_seconds <= 14400:
        parser.error("--timeout-seconds must be between 60 and 14400")

    comfy_root = comfyui_root()
    comfy_input = Path(os.environ.get("COMFYUI_INPUT_DIR", str(comfy_root / "input"))).resolve()
    staging_root = ROOT / "storage" / "production" / "image_smoke_staging"
    run_id = f"image-{args.workflow_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = ROOT / "output" / PROJECT_ID / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": 1, "status": "preflight", "project_id": PROJECT_ID,
        "run_id": run_id, "workflow_id": args.workflow_id,
        "workflow_version": SPECS[args.workflow_id]["version"], "comfyui_url": COMFY_URL,
        "started_at": datetime.now(timezone.utc).isoformat(), "outputs": [], "staged_assets": [],
    }
    staged_owner = run_id
    submitted = False
    prompt_id: str | None = None
    started = time.monotonic()
    try:
        if args.workflow_id == "qwen_image_edit_2511" and not FIXTURE_IMAGE.is_file():
            raise RuntimeError(f"Edit workflow fixture is missing: {FIXTURE_IMAGE}")
        stats = request_json("/system_stats")
        devices = stats.get("devices", [])
        if not devices:
            raise RuntimeError("ComfyUI reports no compute device; refusing image smoke.")
        device = devices[0]
        free_vram = int(device.get("vram_free", 0))
        if free_vram < MIN_FREE_VRAM:
            raise RuntimeError(f"Only {free_vram / 1024**3:.1f} GiB free VRAM; minimum is 20 GiB.")
        if not queue_is_idle():
            raise RuntimeError("ComfyUI queue is busy; no image workflow was submitted.")
        object_info = request_json("/object_info")
        spec = SPECS[args.workflow_id]
        missing_nodes = sorted(set(spec["required_nodes"]) - set(object_info))
        missing_models = [
            f"{folder}/{filename}" for folder, filename in spec["models"].values()
            if not (comfy_root / "models" / folder / filename).is_file()
        ]
        graph_path = ROOT / "workflows" / "api" / spec["graph"]
        if missing_nodes or missing_models or not graph_path.is_file():
            raise RuntimeError(f"Workflow preflight failed: missing_nodes={missing_nodes}; "
                               f"missing_models={missing_models}; graph_exists={graph_path.is_file()}")
        manifest["comfyui"] = {
            "version": stats.get("system", {}).get("comfyui_version"),
            "python": stats.get("system", {}).get("python_version"),
            "torch": stats.get("system", {}).get("pytorch_version"),
            "device": device.get("name"), "vram_free_before_bytes": free_vram,
        }
        manifest["preflight"] = {"status": "ready", "missing_nodes": [], "missing_models": [],
                                 "graph": f"workflows/api/{spec['graph']}"}
        source_images: list[str] = []
        if args.workflow_id == "qwen_image_edit_2511":
            staged = stage_image_reference(FIXTURE_IMAGE, asset_id="fixture-source",
                owner_id=staged_owner, comfy_input_dir=comfy_input, owner_root=staging_root)
            source_images = [staged.filename]
            manifest["staged_assets"] = [{"kind": "image", "filename": staged.filename,
                                           "sha256": staged.sha256, "source_sha256": staged.source_sha256}]
        compiled = compile_image_candidates(
            workflow_id=args.workflow_id, prompt=PROMPT, control_mode="fully_automated",
            seed=20261002, output_prefix=f"story_builder/{run_id}", source_images=source_images)
        candidate = compiled["candidates"][0]
        manifest.update({"status": "compiled", "workflow_version": compiled["workflow_version"],
            "control_mode": "fully_automated", "initial_candidate_count": compiled["initial_candidate_count"],
            "settings": compiled["settings"], "seed": candidate["seed"],
            "graph_sha256": hashlib.sha256(json.dumps(candidate["graph"], sort_keys=True).encode()).hexdigest()})
        (run_dir / "compiled_graph.json").write_text(json.dumps(candidate["graph"], indent=2), encoding="utf-8")
        write_manifest(manifest_path, manifest)
        if not queue_is_idle():
            raise RuntimeError("ComfyUI queue became busy after preflight; no image workflow was submitted.")
        sample = inspect_gpu_runtime(comfy_url=COMFY_URL,
                                     workload_started_at=manifest["started_at"])
        record_gpu_telemetry(run_dir / "gpu_telemetry.jsonl", sample,
                             workload_id=run_id, phase="admission")
        response = request_json("/prompt", payload={"prompt": candidate["graph"]}, timeout=60)
        prompt_id = str(response.get("prompt_id") or "")
        if not prompt_id:
            raise RuntimeError("ComfyUI accepted no prompt ID; remote submission state is unknown.")
        submitted = True
        manifest.update({"status": "running", "comfy_prompt_id": prompt_id,
                         "submitted_at": datetime.now(timezone.utc).isoformat()})
        write_manifest(manifest_path, manifest)
        deadline = time.monotonic() + args.timeout_seconds
        prompt_state = None
        next_telemetry = 0.0
        while time.monotonic() < deadline:
            if time.monotonic() >= next_telemetry:
                sample = inspect_gpu_runtime(comfy_url=COMFY_URL, expected_prompt_id=prompt_id,
                                             workload_started_at=manifest["started_at"])
                record_gpu_telemetry(run_dir / "gpu_telemetry.jsonl", sample,
                                     workload_id=run_id, phase="render")
                next_telemetry = time.monotonic() + 10
            history = request_json(f"/history/{urllib.parse.quote(prompt_id, safe='')}", timeout=30)
            prompt_state = history.get(prompt_id)
            if prompt_state:
                status = prompt_state.get("status", {})
                if status.get("status_str") == "error":
                    manifest.update({"status": "failed", "failure": {"code": "comfy_prompt_failed",
                        "details": status.get("messages", [])}, "comfy_status": status})
                    write_manifest(manifest_path, manifest)
                    return 1
                if status.get("completed"):
                    break
            time.sleep(5)
        if not prompt_state or not prompt_state.get("status", {}).get("completed"):
            manifest.update({"status": "recovery_pending", "failure": {"code": "render_timeout_or_state_unknown",
                "message": "The render may still be active. Staged image inputs were intentionally retained."}})
            write_manifest(manifest_path, manifest)
            print(json.dumps({"status": manifest["status"], "manifest": str(manifest_path),
                              "prompt_id": prompt_id}, indent=2))
            return 2
        collected = collect_outputs(prompt_state, destination_dir=run_dir / "media", comfy_url=COMFY_URL)
        output_rows = []
        for row in collected:
            path = run_dir / "media" / row["relative_path"]
            if row.get("kind") != "image" or not path.is_file():
                continue
            try:
                from PIL import Image
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    dimensions = list(image.size)
            except Exception as exc:
                raise RuntimeError(f"Collected image failed decode verification: {path.name}: {exc}") from exc
            output_rows.append({**row, "absolute_path": str(path.resolve()), "sha256": sha256_file(path),
                                "width": dimensions[0], "height": dimensions[1],
                                "provenance": image_output_provenance(project_id=PROJECT_ID, run_id=run_id,
                                    asset_role="disposable_smoke", workflow_id=args.workflow_id,
                                    prompt=PROMPT, seed=candidate["seed"], settings=compiled["settings"],
                                    candidate_index=1)})
        if not output_rows:
            raise RuntimeError("ComfyUI completed but no decodable image output was collected.")
        cleanup_report = remove_hash_verified_comfy_outputs(prompt_state, comfy_output_root=comfy_root / "output",
            run_id=run_id, copied_outputs=output_rows)
        manifest.update({"status": "completed", "outputs": output_rows,
            "removed_comfy_output_duplicates": cleanup_report["removed"],
            "retained_comfy_output_duplicates": cleanup_report["retained"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 2)})
        try:
            manifest["cleanup"] = cleanup_owned_media(
                staged_owner, comfy_input_dir=comfy_input, owner_root=staging_root)
        except Exception as exc:
            manifest["cleanup"] = {"status": "warning", "reason": f"{type(exc).__name__}: {exc}"}
        try:
            manifest["model_release"] = release_comfyui_models_if_idle(comfy_url=COMFY_URL)
        except Exception as exc:
            manifest["model_release"] = {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
        smoke_record = {"schema_version": 1, "status": "passed", "workflow_id": args.workflow_id,
            "workflow_version": compiled["workflow_version"], "run_id": run_id,
            "manifest": str(manifest_path), "output": output_rows[0],
            "verified_at": datetime.now(timezone.utc).isoformat()}
        evidence = ROOT / "storage" / "production" / "image_workflow_smokes" / f"{args.workflow_id}.json"
        try:
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text(json.dumps(smoke_record, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            # Output truth is stronger than catalog evidence. Keep the completed
            # artifact valid, but don't claim the catalog can enable this adapter.
            manifest["smoke_evidence_write_warning"] = f"{type(exc).__name__}: {exc}"
        write_manifest(manifest_path, manifest)
        print(json.dumps({"status": "completed", "manifest": str(manifest_path),
                          "output": output_rows[0], "model_release": manifest["model_release"]}, indent=2))
        return 0
    except KeyboardInterrupt:
        manifest.update({"status": "recovery_pending" if submitted else "interrupted",
            "failure": {"code": "operator_interrupt", "message": "Remote render state must be checked before any retry."}})
        if prompt_id:
            manifest["comfy_prompt_id"] = prompt_id
        write_manifest(manifest_path, manifest)
        print(json.dumps({"status": manifest["status"], "manifest": str(manifest_path),
                          "prompt_id": prompt_id}, indent=2))
        return 130
    except Exception as exc:
        manifest.update({"status": "recovery_pending" if submitted else "failed",
            "failure": {"type": type(exc).__name__, "message": str(exc)}})
        if prompt_id:
            manifest["comfy_prompt_id"] = prompt_id
        write_manifest(manifest_path, manifest)
        print(json.dumps({"status": manifest["status"], "manifest": str(manifest_path),
                          "failure": manifest["failure"], "prompt_id": prompt_id}, indent=2))
        return 1
    finally:
        # Only pre-submit failures or already-terminal outcomes are safe to clean.
        if not submitted or manifest.get("status") in {"completed", "failed"}:
            try:
                if "cleanup" not in manifest:
                    manifest["cleanup"] = cleanup_owned_media(
                        staged_owner, comfy_input_dir=comfy_input, owner_root=staging_root)
            except Exception as exc:
                manifest["cleanup"] = {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
            if may_release_models(submitted=submitted, status=str(manifest.get("status", ""))):
                try:
                    if "model_release" not in manifest:
                        manifest["model_release"] = release_comfyui_models_if_idle(comfy_url=COMFY_URL)
                except Exception as exc:
                    manifest["model_release"] = {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
            write_manifest(manifest_path, manifest)


def main() -> int:
    """Run one disposable image job under Story Builder's shared GPU lock.

    Hold the same cross-process admission lock used by website jobs from before
    preflight through render completion. This prevents two Story Builder
    checkouts/processes from both observing an idle ComfyUI queue and submitting
    concurrently. Direct ComfyUI UI clients remain external to this lock.
    """
    with comfy_submission_guard():
        return _main_locked()


if __name__ == "__main__":
    raise SystemExit(main())
