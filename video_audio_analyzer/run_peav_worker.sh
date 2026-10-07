#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VIDEO_PATH="${1:?usage: $0 /absolute/or/relative/video.mp4}"
shift || true
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
if [[ "$VIDEO_PATH" = /* ]]; then VIDEO_REAL="$(realpath "$VIDEO_PATH")"; else VIDEO_REAL="$(realpath "$REPO_ROOT/$VIDEO_PATH")"; fi
case "$VIDEO_REAL" in
  "$REPO_ROOT"/*) CONTAINER_VIDEO="/app/project/${VIDEO_REAL#"$REPO_ROOT"/}" ;;
  *) echo "Input video must be inside the mounted Story Builder workspace: $VIDEO_REAL" >&2; exit 2 ;;
esac
VOICE_STORE_NAME="${VIDEO_AUDIO_ANALYZER_VOICE_STORE_NAME:-voice_store}"
PROJECT_ID="${VIDEO_AUDIO_ANALYZER_PROJECT_ID:-default_project}"
REPERTOIRE_ROOT="${VIDEO_REPERTOIRE_ROOT:-$REPO_ROOT/video_repertoire}"
RUNS_ROOT="$REPERTOIRE_ROOT/analyses/video_audio_analyzer"
VOICE_STORE_ROOT="$REPERTOIRE_ROOT/indexes/$VOICE_STORE_NAME"
DIRECTOR_REVIEW_ROOT="$REPERTOIRE_ROOT/indexes/director_reviews"
mkdir -p "$RUNS_ROOT" "$VOICE_STORE_ROOT" "$DIRECTOR_REVIEW_ROOT" "$REPERTOIRE_ROOT/manifests/analyzer-runs"
AUDIO_WORKER_ARGS=()
ANALYSIS_JOB_ID="${VIDEO_AUDIO_ANALYZER_JOB_ID:-manual-$$}"
if [[ -n "${VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL:-}" ]]; then
  AUDIO_WORKER_URL="$VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL"
else
  AUDIO_WORKER_URL="http://127.0.0.1:8031"
fi
if curl -fsS --max-time 2 "$AUDIO_WORKER_URL/health" >/dev/null 2>&1; then
  AUDIO_WORKER_ARGS=(-e "VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL=$AUDIO_WORKER_URL")
fi
TALKNET_WORKER_URL="${VIDEO_AUDIO_ANALYZER_TALKNET_URL:-http://127.0.0.1:8032}"
if curl -fsS --max-time 2 "$TALKNET_WORKER_URL/health" >/dev/null 2>&1; then
  AUDIO_WORKER_ARGS+=( -e "VIDEO_AUDIO_ANALYZER_TALKNET_URL=$TALKNET_WORKER_URL" )
fi
SAM_AUDIO_WORKER_URL="${VIDEO_AUDIO_ANALYZER_SAM_AUDIO_URL:-http://127.0.0.1:8033}"
if curl -fsS --max-time 2 "$SAM_AUDIO_WORKER_URL/health" >/dev/null 2>&1; then
  AUDIO_WORKER_ARGS+=( -e "VIDEO_AUDIO_ANALYZER_SAM_AUDIO_URL=$SAM_AUDIO_WORKER_URL" )
fi
docker run --rm --label "story-builder.analysis-job=$ANALYSIS_JOB_ID" --gpus all --network host \
  --user "$(id -u):$(id -g)" \
  --entrypoint python \
  -e HOME=/tmp/video-audio-analyzer-home \
  -e PYTHONPATH=/app/src \
  -e PE_AV_MODEL_DIR=/models/pe-av-base \
  -e VIDEO_AUDIO_ANALYZER_PE_AV_PATH=/models/pe-av-base \
  -e VIDEO_AUDIO_ANALYZER_PANNS_CHECKPOINT=/models/panns/Cnn14_DecisionLevelMax_mAP=0.385.pth \
  -e VIDEO_AUDIO_ANALYZER_HTSAT_CHECKPOINT=/models/HTSAT_AudioSet_Saved_1.ckpt \
  -e VIDEO_AUDIO_ANALYZER_HTSAT_REPO=/app/project/video_audio_analyzer/vendor/HTS-Audio-Transformer \
  -e VIDEO_AUDIO_ANALYZER_ASR_MODEL=/models/faster-whisper-large-v3 \
  -e VIDEO_AUDIO_ANALYZER_ECAPA_MODEL=/models/spkrec-ecapa-voxceleb \
  -e VIDEO_AUDIO_ANALYZER_VOICE_STORE_PATH="/app/voice_store" \
  -e "VIDEO_AUDIO_ANALYZER_PROJECT_ID=$PROJECT_ID" \
  -e VIDEO_AUDIO_ANALYZER_ENABLE_LANCEDB=1 \
  -e VIDEO_AUDIO_ANALYZER_VOICE_STORE_ENABLE_LANCEDB=1 \
  -e VIDEO_AUDIO_ANALYZER_PREFLIGHT_PATH=/app/repertoire/manifests/preflight.json \
  "${AUDIO_WORKER_ARGS[@]}" \
  -v "$ROOT_DIR/models:/models:ro" \
  -v "$ROOT_DIR/src:/app/src:ro" \
  -v "$RUNS_ROOT:/app/runs" \
  -v "$VOICE_STORE_ROOT:/app/voice_store" \
  -v "$REPERTOIRE_ROOT:/app/repertoire" \
  -v "$REPO_ROOT:/app/project:ro" \
  video-audio-analyzer-peav:dev \
  -m video_audio_analyzer.cli --root /app --video "$CONTAINER_VIDEO" "$@"

# The clip-first summary is the primary report. It is deliberately a second
# isolated one-shot so the PE-AV/Transformers environment and InternVideo3's
# pinned Transformers environment never need to coexist.
if [[ "${VIDEO_AUDIO_ANALYZER_INTERNVIDEO3_ENABLED:-1}" != "0" ]]; then
  VIDEO_ID="$(sha256sum "$VIDEO_REAL" | cut -c1-16)"
  MANIFEST_PATH=""
  for candidate in "$RUNS_ROOT/$VIDEO_ID/manifest.json" "$RUNS_ROOT"/"$VIDEO_ID"-rerun-*/manifest.json; do
    [[ -f "$candidate" ]] || continue
    if [[ -z "$MANIFEST_PATH" || "$candidate" -nt "$MANIFEST_PATH" ]]; then MANIFEST_PATH="$candidate"; fi
  done
  if [[ -z "$MANIFEST_PATH" ]]; then
    echo "[internvideo3] Analyzer did not produce a manifest for video $VIDEO_ID; cannot summarize clips." >&2
    exit 5
  fi
  echo "[internvideo3] Creating direct-video clip and full-video summaries from $MANIFEST_PATH"
  bash "$ROOT_DIR/run_internvideo3_stage.sh" "$VIDEO_REAL" "$MANIFEST_PATH"
  RUN_ID="$(basename "$(dirname "$MANIFEST_PATH")")"
  docker run --rm --label "story-builder.analysis-job=$ANALYSIS_JOB_ID" --gpus all --network host --ipc=host \
    --user "$(id -u):$(id -g)" \
    --entrypoint python \
    -e HOME=/tmp/video-audio-analyzer-home \
    -e PYTHONPATH=/app/src \
    -e VIDEO_AUDIO_ANALYZER_PE_AV_PATH=/models/pe-av-base \
    -e VIDEO_AUDIO_ANALYZER_ENABLE_LANCEDB=1 \
    -v "$ROOT_DIR/models:/models:ro" \
    -v "$ROOT_DIR/src:/app/src:ro" \
    -v "$RUNS_ROOT:/app/runs:rw" \
    -v "$REPO_ROOT:/app/project:ro" \
    video-audio-analyzer-peav:dev \
    -m video_audio_analyzer.peav_text_stage "/app/runs/$RUN_ID/manifest.json"
  docker run --rm --label "story-builder.analysis-job=$ANALYSIS_JOB_ID" --gpus all --network host --ipc=host \
    --user "$(id -u):$(id -g)" \
    --entrypoint python \
    -e HOME=/tmp/video-audio-analyzer-home \
    -e PYTHONPATH=/app/src \
    -e VIDEO_AUDIO_ANALYZER_PE_AV_PATH=/models/pe-av-base \
    -e VIDEO_AUDIO_ANALYZER_ENABLE_LANCEDB=1 \
    -v "$ROOT_DIR/models:/models:ro" \
    -v "$ROOT_DIR/src:/app/src:ro" \
    -v "$RUNS_ROOT:/app/runs:rw" \
    -v "$REPO_ROOT:/app/project:ro" \
    video-audio-analyzer-peav:dev \
    -m video_audio_analyzer.index_manifest_stage "/app/runs/$RUN_ID/manifest.json"
fi

# Codex runs on the host, never inside a model worker, so ~/.codex credentials
# are not mounted into Docker. It reviews only the bounded candidate metadata
# from this run and cannot write arbitrary files or call other tools.
if [[ "${VIDEO_AUDIO_ANALYZER_CODEX_DIRECTOR:-1}" != "0" ]] && command -v codex >/dev/null 2>&1; then
  VIDEO_ID="$(sha256sum "$VIDEO_REAL" | cut -c1-16)"
  echo "[director] Reviewing identity candidates with Codex ${VIDEO_AUDIO_ANALYZER_CODEX_MODEL:-gpt-6-luna}"
  if ! PYTHONPATH="$ROOT_DIR/src" VIDEO_AUDIO_ANALYZER_CODEX_MODEL="${VIDEO_AUDIO_ANALYZER_CODEX_MODEL:-gpt-6-luna}" \
    python3 -m video_audio_analyzer.codex_director_review \
    --runs-root "$RUNS_ROOT" --video-id "$VIDEO_ID" \
      --voice-store "$VOICE_STORE_ROOT" --review-root "$DIRECTOR_REVIEW_ROOT"; then
    echo "[director] Review unavailable or invalid; the run remains usable and identity merges stay unconfirmed." >&2
  fi
elif [[ "${VIDEO_AUDIO_ANALYZER_CODEX_DIRECTOR:-1}" != "0" ]]; then
  echo "[director] Codex CLI unavailable; identity candidates remain unconfirmed." >&2
fi
