#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
export VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_URL="${VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_URL:-http://127.0.0.1:8034}"
export VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL="${VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL:-http://127.0.0.1:8031}"
exec uvicorn video_audio_analyzer.api:app --host "${VIDEO_AUDIO_ANALYZER_HOST:-127.0.0.1}" --port "${VIDEO_AUDIO_ANALYZER_PORT:-3021}"
