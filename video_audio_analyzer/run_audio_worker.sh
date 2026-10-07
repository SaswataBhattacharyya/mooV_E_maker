#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec docker run --rm --gpus all --network host \
  --entrypoint python3 \
  -e PYTHONPATH=/app/src:/opt/perception_models \
  -e PE_AV_MODEL_DIR=/models/pe-av-base \
  -e VIDEO_AUDIO_ANALYZER_NEMO_VAD_MODEL=/models/nemo/vad_multilingual_marblenet.nemo \
  -e VIDEO_AUDIO_ANALYZER_NEMO_SPEAKER_MODEL=/models/nemo/titanet_large.nemo \
  -e VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT=/models/clap/630k-audioset-best.pt \
  -e VIDEO_AUDIO_ANALYZER_CLAP_DEVICE=cuda \
  -e VIDEO_AUDIO_ANALYZER_SAM_AUDIO_PATH=/models/sam-audio-large-tv \
  -e VIDEO_AUDIO_ANALYZER_SAM_T5_PATH=/models/sam-audio-t5-base \
  -v "$ROOT_DIR/models:/models:ro" \
  -v "$ROOT_DIR/src:/app/src:ro" \
  video-audio-analyzer-audio:dev \
  -m uvicorn video_audio_analyzer.audio_worker:app --host 0.0.0.0 --port 8031
