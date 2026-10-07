"""Recover and collect an already-submitted dynamic H3 smoke without resubmission."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from story_builder.services.audio_catalog import comfyui_root
from story_builder.services.media_jobs import collect_outputs, comfy_submission_guard, release_comfyui_models_if_idle
from story_builder.services.gpu_runtime import GPUAdmissionError, inspect_gpu_runtime, record_gpu_telemetry
from story_builder.services.minimax_h3_media import cleanup_owned_media, probe_media, sha256_file
from story_builder.scripts.smoke_minimax_h3_dynamic import (
    COMFY_URL, PROJECT_ID, remove_hash_verified_comfy_outputs, write_manifest as atomic_write_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


def request_json(url: str, timeout_seconds: int = 10) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_manifest(path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--prompt-id", help="Defaults to the prompt ID saved in the run manifest.")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    run_dir = ROOT / "output" / PROJECT_ID / "runs" / args.run_id
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Cannot recover: manifest not found at {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("run_id") != args.run_id or manifest.get("status") not in {"submitting", "running", "recovery_pending"}:
        raise SystemExit(f"Refusing recovery because manifest state is {manifest.get('status')!r} for run {manifest.get('run_id')!r}")
    saved_prompt_id = manifest.get("comfy_prompt_id")
    if args.prompt_id and saved_prompt_id and args.prompt_id != saved_prompt_id:
        raise SystemExit("Refusing recovery with a prompt ID different from the saved run.")
    args.prompt_id = args.prompt_id or saved_prompt_id
    if not args.prompt_id:
        raise SystemExit("No saved prompt ID; provide the exact ID from the original submission logs.")
    manifest.update({"status": "recovery_pending", "comfy_prompt_id": args.prompt_id,
                     "recovery_started_at": datetime.now(timezone.utc).isoformat()})
    write_manifest(manifest_path, manifest)
    deadline = time.monotonic() + max(1, args.timeout_seconds)
    consecutive_connection_errors = 0
    last_note = ""
    next_telemetry = 0.0
    while time.monotonic() < deadline:
        if time.monotonic() >= next_telemetry:
            try:
                sample = inspect_gpu_runtime(comfy_url=COMFY_URL, expected_prompt_id=args.prompt_id,
                                             workload_started_at=manifest.get("started_at"))
            except GPUAdmissionError as exc:
                note = f"GPU state is no longer verifiable; render reconciliation is paused: {exc}"
                manifest["recovery_last_note"] = note
                write_manifest(manifest_path, manifest)
                print(json.dumps({"status": "recovery_pending", "manifest": str(manifest_path),
                                  "prompt_id": args.prompt_id, "last_note": note}, indent=2))
                return 2
            record_gpu_telemetry(run_dir / "gpu_telemetry.jsonl", sample,
                                 workload_id=args.run_id, phase="recovery")
            next_telemetry = time.monotonic() + 10
        try:
            history = request_json(f"{COMFY_URL}/history/{args.prompt_id}", timeout_seconds=20)
            consecutive_connection_errors = 0
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            consecutive_connection_errors += 1
            last_note = f"ComfyUI history temporarily unavailable ({type(exc).__name__}); consecutive={consecutive_connection_errors}"
            manifest["recovery_last_note"] = last_note
            if consecutive_connection_errors >= 5:
                manifest.update({"status": "recovery_pending", "failure": {"code": "comfyui_unreachable", "message": last_note}})
                write_manifest(manifest_path, manifest)
                print(json.dumps({"status": "recovery_pending", "manifest": str(manifest_path), "failure": last_note}, indent=2))
                return 1
            time.sleep(5)
            continue
        prompt_state = history.get(args.prompt_id)
        if prompt_state:
            status = prompt_state.get("status", {})
            if status.get("status_str") == "error":
                manifest.update({"status": "failed", "failure": {"code": "comfy_prompt_failed", "details": status.get("messages", [])}})
                write_manifest(manifest_path, manifest)
                print(json.dumps({"status": "failed", "manifest": str(manifest_path), "failure": manifest["failure"]}, indent=2))
                return 1
            if status.get("completed"):
                collected = collect_outputs(prompt_state, destination_dir=run_dir / "media", comfy_url=COMFY_URL)
                output_rows: list[dict[str, Any]] = []
                for row in collected:
                    path = run_dir / "media" / row["relative_path"]
                    item: dict[str, Any] = {**row, "absolute_path": str(path.resolve()), "sha256": sha256_file(path) if path.is_file() else None}
                    if item.get("kind") == "video" and path.is_file():
                        probed = probe_media(path)
                        item["probe"] = {"duration_seconds": probed.duration_seconds, "width": probed.width,
                                         "height": probed.height, "fps": probed.frame_rate,
                                         "has_audio": probed.has_audio, "audio_codec": probed.audio_codec}
                    output_rows.append(item)
                if not any(row.get("kind") == "video" and row.get("probe", {}).get("has_audio") for row in output_rows):
                    manifest.update({"status": "failed", "failure": {"code": "output_missing_native_audio", "outputs": output_rows}})
                    write_manifest(manifest_path, manifest)
                    print(json.dumps({"status": "failed", "manifest": str(manifest_path), "failure": manifest["failure"]}, indent=2))
                    return 1
                comfy_output_root = Path(os.environ.get("COMFYUI_OUTPUT_DIR", str(comfyui_root() / "output"))).resolve()
                output_cleanup = remove_hash_verified_comfy_outputs(
                    prompt_state, comfy_output_root=comfy_output_root,
                    run_id=args.run_id, copied_outputs=output_rows)
                manifest.update({"status": "completed", "outputs": output_rows,
                                 "removed_comfy_output_duplicates": output_cleanup["removed"],
                                 "retained_comfy_output_duplicates": output_cleanup["retained"],
                                 "completed_at": datetime.now(timezone.utc).isoformat()})
                try:
                    manifest["cleanup"] = cleanup_owned_media(
                        args.run_id,
                        comfy_input_dir=Path(os.environ.get("COMFYUI_INPUT_DIR", str(comfyui_root() / "input"))),
                        owner_root=ROOT / "storage" / "projects" / PROJECT_ID / "comfy_staging")
                except Exception as exc:
                    manifest["cleanup"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
                with comfy_submission_guard():
                    manifest["model_release"] = release_comfyui_models_if_idle(comfy_url=COMFY_URL)
                write_manifest(manifest_path, manifest)
                print(json.dumps({"status": "completed", "manifest": str(manifest_path),
                                  "outputs": output_rows,
                                  "removed_comfy_output_duplicates": output_cleanup["removed"],
                                  "retained_comfy_output_duplicates": output_cleanup["retained"],
                                  "model_release": manifest["model_release"]}, indent=2))
                return 0
        time.sleep(5)
    manifest.update({"status": "recovery_pending", "failure": {"code": "recovery_timeout", "message": last_note or "ComfyUI has not completed this prompt yet."}})
    write_manifest(manifest_path, manifest)
    print(json.dumps({"status": "recovery_pending", "manifest": str(manifest_path),
                      "prompt_id": args.prompt_id, "last_note": last_note}, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
