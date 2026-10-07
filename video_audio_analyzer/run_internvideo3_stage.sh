#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
IMAGE="${VIDEO_AUDIO_ANALYZER_INTERNVIDEO3_IMAGE:-video-audio-analyzer-internvideo3:dev}"
FPS="${VIDEO_AUDIO_ANALYZER_INTERNVIDEO3_FPS:-1.0}"
ANALYSIS_JOB_ID="${VIDEO_AUDIO_ANALYZER_JOB_ID:-manual-$$}"

usage() {
  echo "usage: $0 /path/to/video.mp4 /path/to/manifest.json [--preflight]" >&2
  echo "The manifest must belong to an analyzer run under video_repertoire/analyses/video_audio_analyzer." >&2
}

if [[ $# -lt 2 || $# -gt 3 ]]; then usage; exit 2; fi
VIDEO_REAL="$(realpath "$1")"
MANIFEST_REAL="$(realpath "$2")"
if [[ "${3:-}" == "--preflight" ]]; then PREFLIGHT=1; elif [[ $# -eq 3 ]]; then usage; exit 2; else PREFLIGHT=0; fi
case "$VIDEO_REAL" in "$REPO_ROOT"/*) VIDEO_CONTAINER="/app/project/${VIDEO_REAL#"$REPO_ROOT"/}";; *) echo "Source video must be in the Story Builder workspace: $VIDEO_REAL" >&2; exit 2;; esac
REPERTOIRE_ROOT="${VIDEO_REPERTOIRE_ROOT:-$REPO_ROOT/video_repertoire}"
RUNS_ROOT="$REPERTOIRE_ROOT/analyses/video_audio_analyzer"
case "$MANIFEST_REAL" in "$RUNS_ROOT"/*/manifest.json) ;; *) echo "Manifest must be an analyzer run manifest under: $RUNS_ROOT" >&2; exit 2;; esac
RUN_ID="$(basename "$(dirname "$MANIFEST_REAL")")"
MODEL_DIR="$ROOT_DIR/models/internvideo3-8b-instruct"
if [[ ! -s "$MODEL_DIR/model.safetensors.index.json" ]]; then echo "InternVideo3 checkpoint index is missing: $MODEL_DIR" >&2; exit 3; fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Required isolated image '$IMAGE' is not built. Build it explicitly with:" >&2
  echo "  docker build -f '$ROOT_DIR/Dockerfile.internvideo3' -t '$IMAGE' '$ROOT_DIR'" >&2
  exit 4
fi
ARGS=(--manifest "/app/runs/$RUN_ID/manifest.json" --source "$VIDEO_CONTAINER" --fps "$FPS")
if [[ "$PREFLIGHT" == 1 ]]; then ARGS+=(--preflight-only); fi
docker run --rm --label "story-builder.analysis-job=$ANALYSIS_JOB_ID" --gpus all --ipc=host \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp/video-audio-analyzer-home \
  -e PYTHONPATH=/app/src:/opt/perception_models \
  -e VIDEO_AUDIO_ANALYZER_INTERNVIDEO3_PATH=/models/internvideo3-8b-instruct \
  -e VIDEO_AUDIO_ANALYZER_INTERNVIDEO3_REVISION=c4602918b65225650d152db2850fe34e01d21fcd \
  -v "$MODEL_DIR:/models/internvideo3-8b-instruct:ro" \
  -v "$RUNS_ROOT:/app/runs:rw" \
  -v "$REPO_ROOT:/app/project:ro" \
  --entrypoint python "$IMAGE" -m video_audio_analyzer.internvideo3_stage "${ARGS[@]}"
