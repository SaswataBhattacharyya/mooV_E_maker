# PE-AV and LanceDB isolated validation

Date: 2026-09-25

## Result

The limitation is resolved inside the new `video_audio_analyzer` project. No
existing Story Builder, legacy `video_summariser`, ComfyUI image/runtime, or
Conda environment was changed.

| Component | Result |
|---|---|
| Canonical PE-AV checkpoint | `facebook/pe-av-base`, downloaded to `video_audio_analyzer/models/pe-av-base/model.safetensors` (4,134,930,120 bytes) |
| PE-AV worker architecture | ARM64/aarch64 GPU worker derived read-only from the existing ComfyUI image |
| PE-AV runtime | Transformers 5.17.0, timm 1.0.30, Torch 2.11.0+cu130 |
| PE-AV preflight | GPU available, checkpoint present, imports ready |
| Text embedding smoke | passed, output `[1, 1024]` |
| Dummy audio-video embedding | passed; audio, video, joint and text projections returned, each 1024-dimensional |
| Scene-level embedding pipeline | passed; one model load produced one timestamp-linked scene vector |
| PE-AV text retrieval | passed; query encoded by PE-AV and returned indexed results (`query_backend: pe_av`) |
| PANNs sound-event detection | passed on dummy video; emitted timestamped Music/Speech events with confidence and model provenance |
| Measured music analysis | passed on dummy video via isolated librosa; timestamped RMS, spectral centroid, onset strength, beat times/counts, and tempo; measurements only |
| ASR adapter | isolated `faster-whisper==1.2.0` runtime installed; large-v3 checkpoint is an explicit mount; dummy run correctly reports unavailable when cache is absent |
| Demucs policy adapter | `AUTO/off/2/4/6` contract and provenance implemented; dummy run reports unavailable because Demucs is not installed in the isolated image |
| Subtitle precedence | embedded subtitle streams are checked/extracted before ASR; dummy has no embedded stream and correctly falls back to explicit ASR-unavailable status |
| LanceDB shared React runtime | 0.39.0 initialization hangs; never allowed to block a run |
| LanceDB isolated worker | 0.30.0 connect/table/ANN write passed on aarch64; `media_events` table created with 4 dummy records |
| Analyzer tests | 12 passed after music-feature integration |
| Website integration | intentionally not changed; remains the final replacement gate |

## Why the original PE-AV attempt failed

The downloaded Base checkpoint is the official Transformers checkpoint format,
not the older custom-loader state-dict format. The adapter now detects its
`PeAudioVideoModel` architecture and uses `PeAudioVideoProcessor`. The worker
also uses timm 1.0.30 because the base image's older timm did not register the
PE-Core vision architecture. The upstream optional `decord==0.6.0` dependency
has no compatible wheel on this aarch64/Python combination, so it is omitted;
native PyTorch attention and the official Transformers media processor are used
instead.

## Runtime commands

Build the isolated worker:

```bash
docker build -f video_audio_analyzer/Dockerfile.peav \
  -t video-audio-analyzer-peav:dev video_audio_analyzer
```

Run the supplied dummy video through the isolated worker:

```bash
video_audio_analyzer/run_peav_worker.sh \
  'plan/Brother eww what’s that？💀 #meme.mp4'
```

The worker manifest is written under
`video_audio_analyzer/runs/c938423ea483bdc3/`. Its current status is
`retrieval_index: lancedb` and `pe_av_embeddings: completed`: the model loads
once per worker run, encodes each selected scene/clip, and the search path
encodes text with PE-AV when the isolated worker is configured. The safe JSONL
fallback remains available when the isolated worker is not used.

## Phase 3A music validation

The current dummy run reports:

```text
music_analysis: completed
backend: librosa
segments: 1 (0.000–8.731 s)
tempo estimate: 187.5 BPM
beat count: 19
```

The values are persisted under `music_features` in the run manifest. They are
not treated as semantic mood or genre claims. Essentia remains an optional
future specialist pending an isolated architecture/GPU preflight.

The rebuilt worker also includes the local ASR runtime. It does not auto-fetch
weights. The dummy run's `transcription: unavailable` status is expected until
`Systran/faster-whisper-large-v3` is mounted at the configured model path;
scene, frame, audio-event, music, PE-AV, and LanceDB stages still completed.

## Latest dummy validation (2026-09-26)

The isolated worker now reports `transcription: completed`, `demucs:
completed`, `voice_embeddings: completed`, `pe_av_embeddings: completed`,
and `retrieval_index: lancedb`. ASR produced `Brother what's that?` with
word timestamps from 2.93–6.17s. Demucs AUTO produced bass/drums/other/vocals
stems. ECAPA produced one anonymous 192-dimensional embedding linked to the
ASR segment. Diarization, character naming, and SAM Audio remain separate
stages.
