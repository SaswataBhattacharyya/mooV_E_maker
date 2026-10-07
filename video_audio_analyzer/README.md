# Video Audio Analyzer

Isolated successor to `video_summariser`. It preserves the existing scene/frame
timeline contract while adding a versioned audio branch. The old analyzer is
never modified by this project.

## Quick smoke test

```bash
./run_analyzer.sh --preflight
./run_analyzer.sh --video "/home/riki/web_dev/story_builder/plan/Brother eww what’s that？💀 #meme.mp4"
```

Outputs are written to `runs/<video-id>/`:

- `manifest.json`: source metadata, scenes, selected frames, audio events, model/runtime statuses;
- `scenes/`: representative frame JPEGs with timestamps;
- `audio/source_audio.mka`: source bitstream copy when possible;
- `audio/analysis.wav`: model-friendly PCM;
- `audio/preview.mp3`: browser/export preview;
- `summary.txt`: deterministic baseline summary.

Optional models are intentionally reported as `preflight_only`, `unavailable`,
or `on_demand` until their isolated worker is prepared. The analyzer does not
silently invent transcript, diarization, PE-AV, HTS-AT, or SAM Audio results.

## Docker boundary

`Dockerfile` and `docker-compose.yml` belong only to this folder. They do not
alter ComfyUI or the Story Builder runtime. Build/run them only after the
dependency preflight and architecture checks pass.

## Optional PE-AV worker

The canonical `facebook/pe-av-base` checkpoint is kept under
`models/pe-av-base/` and is loaded only by the derived PE-AV image. On this
ARM host the upstream `decord==0.6.0` wheel is unavailable, so the image
installs the PE-AV package without optional evaluation/video-reader extras and
uses native PyTorch attention instead of requiring xFormers. The existing
ComfyUI image is used as a read-only base; it is never modified.

```bash
docker build -f Dockerfile.peav -t video-audio-analyzer-peav:dev .
docker run --rm --gpus all \
  -v "$PWD/models:/models" \
  video-audio-analyzer-peav:dev /app/scripts/peav_preflight.py
```

Set `VIDEO_AUDIO_ANALYZER_PE_AV_PATH=/models/pe-av-base` only for runs that
explicitly enable PE-AV. `VIDEO_AUDIO_ANALYZER_ENABLE_LANCEDB=1` enables the
isolated LanceDB 0.30 probe/table writer; if initialization exceeds the
watchdog, JSONL retrieval remains the safe fallback.

The same worker contains the optional PANNs event detector. Set
`VIDEO_AUDIO_ANALYZER_PANNS_CHECKPOINT=/models/panns/Cnn14_DecisionLevelMax_mAP=0.385.pth`
to enable original-mix sound-event labels; events are timestamped and retain
their detector confidence. Demucs is still independent and remains `AUTO`.

When music analysis is enabled (the default), the worker also writes
`music_features` to the manifest using isolated `librosa`. These are measured,
timestamped values—RMS energy, spectral centroid, onset strength, beat times,
and tempo estimate—not invented mood or genre labels. A missing librosa
runtime is reported as `unavailable` without blocking the rest of the run.

The worker also includes `faster-whisper==1.2.0` for local ASR. Mount a
prepared `Systran/faster-whisper-large-v3` directory and set
`VIDEO_AUDIO_ANALYZER_ASR_MODEL`; weights are never downloaded during a job.
Without that cache, transcription is explicitly marked unavailable while the
remaining analysis stages continue.

The isolated worker also contains Demucs 4.0.1 and SpeechBrain ECAPA. In the
latest dummy validation, Demucs AUTO produced four stems and ECAPA produced a
192-dimensional embedding for the ASR-aligned speech segment. These outputs
remain anonymous and provenance-linked; diarization and character naming are
separate stages.

## Optional active-speaker worker

TalkNet-ASD runs in a separate analyzer-only image because its legacy helper
dependencies should not be added to the PE-AV/NeMo worker or shared Conda
environments. The TalkSet checkpoint and S3FD weights are prepared under
`models/talknet/`. Start only this optional service when active-speaker
evidence is desired:

```bash
docker compose --profile active-speaker up -d talknet-worker
curl http://127.0.0.1:8032/health
```

`run_peav_worker.sh` detects the service and submits the original video. Each
request runs in a unique temporary directory and returns timestamped face
tracks and active-speaker scores; temporary crops/frames are removed at the
end. A score creates only a diarized-speaker/face-track candidate. It is not a
persistent character identity, and it cannot trigger an automatic Voice Store
merge. The downloaded checkpoint has no separate license statement in its
hosted artifact; review terms before redistribution or commercial use.

## Optional SAM Audio isolation worker

SAM Audio has its own analyzer-only image and `sam-audio` profile. It reuses
the analyzer CUDA base but pins the existing Torch, torchaudio, torchvision,
NumPy, and Transformers versions. The worker does not download the gated
checkpoint on startup or during inference:

```bash
# After accepting the official Hugging Face model terms and preparing
# facebook/sam-audio-large-tv under models/sam-audio-large-tv, plus the local
# google-t5/t5-base text encoder under models/sam-audio-t5-base:
docker compose --profile sam-audio up -d sam-audio-worker
curl http://127.0.0.1:8033/health
```

The normal analyzer detects the service automatically. A requested event is
sent as audio bytes with its text prompt and positive timestamp anchor; the
worker returns only a temporary WAV preview. It is copied into analyzer temp
storage with TTL, and the separate explicit director `save_to_repertoire`
decision is still required for persistence. The worker uses the Large TV
checkpoint and a local T5-Base text encoder. It aliases the Hugging Face
checkpoint filename with a symlink (no 15-GB copy), disables unused
ranking/span models for the anchored single-candidate path, and runs offline
after preflight. SAM Audio uses Meta's SAM License; review its terms for your
intended use.

## PE-AV corpus semantic search

The analyzer API's corpus search runs outside the model container, so its
website/host Python environment does not need the PE-AV Transformers build.
Start the optional GPU query worker from this analyzer project:

```bash
docker compose --profile peav-search up -d peav-query-worker
curl http://127.0.0.1:8034/health
```

`run_api.sh` points to `http://127.0.0.1:8034` by default; override it with
`VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_URL` if the worker is elsewhere. The model is
loaded lazily once by the worker. `POST /api/search/all` uses real PE-AV query
vectors only when the worker returns the expected model and vector dimension;
otherwise semantic results are withheld and keyword mode remains available.
This query service is isolated to the analyzer Compose profile and does not
install packages into the Story Builder, ComfyUI, or Conda environments.
Corpus reindexing uses `scripts/reindex_semantic.py --write` and stores the
new clip-level indexes under `corpus_index_v2/`; it never overwrites original
run manifests or `runs/*/index/`. The semantic retrieval unit is a scene clip,
not every sampled frame. Repeated analyses of the same source video/scene are
deduplicated to the newest indexed run.

## Codex director review

After a successful `run_peav_worker.sh` run, the host invokes the installed
Codex CLI (`gpt-6-luna`) in read-only/ephemeral mode when TalkNet/NeMo or Voice
Store candidates are present. Codex sees only a compact, timestamped evidence
payload; CLI credentials are not mounted into Docker. The original run
manifest stays immutable. Decisions and provenance are written under
`director_reviews/` and overlaid by the analyzer manifest API. Voice UUIDs are
linked non-destructively only when independent trusted identity evidence is
present; similarity alone cannot merge identities. Automatic within-video
face-track links require Codex confidence of at least 0.75; voice identity
links require at least 0.80 plus independent trusted identity evidence.
Disable review for a run with `VIDEO_AUDIO_ANALYZER_CODEX_DIRECTOR=0`.

If the CLI is unavailable or returns invalid structured output, analysis
still succeeds and identity candidates remain unconfirmed. No real-person
name is inferred from face/voice vectors.
