# Video Audio Analyzer dummy comparison

Fixture:

`plan/Brother eww what’s that？💀 #meme.mp4`

## Run status

The isolated analyzer completed an end-to-end deterministic run and wrote:

`video_audio_analyzer/runs/c938423ea483bdc3/`

It produced:

- source metadata: 8.730703 seconds, 360×640, 30 FPS, one audio stream;
- one cut-defined scene covering the complete video;
- three representative frames at approximately 0.00, 4.25, and 8.50 seconds;
- source audio bitstream copy (`source_audio.mka`), `analysis.wav`, and `preview.mp3`;
- five two-second audio-activity windows with RMS and zero-crossing measurements;
- Whisper `small` transcript with timestamped segments;
- compact typed evidence for all three representative frames, including dimensions, brightness, contrast, saturation, edge density, dominant colors, lighting measurements, OCR/model availability, confidence fields, and uncertainty notes;
- eight indexed records (three frames plus five audio windows), separate PE-AV/CLAP vector fields, deterministic offline fallback vectors, and semantic/keyword/hybrid pagination code;
- a versioned manifest and deterministic summary.

## Baseline comparison

The existing analyzer's cached result for the same fixture reports one scene spanning the same 8.731 seconds and the transcript:

`Ewww! Brother, ewww! What's that?`

The existing analyzer selected 35 sampled frame files. The new analyzer intentionally selects three representative frames for the baseline pass, while retaining the scene boundary and timestamps. This is an efficiency change, not a scene-timeline regression; the adaptive second-pass selector remains to be implemented and benchmarked before website replacement.

The new analyzer currently marks these stages explicitly rather than fabricating results:

| Stage | Result |
|---|---|
| Source import/probe | Completed |
| Scene detection | Completed |
| Representative frames | Completed |
| Compact frame evidence | Completed; measurable fields only, no invented objects/actions |
| Retrieval index | Completed with explicit JSONL fallback; PE-AV/CLAP/LanceDB remain preflight-gated |
| Source/analysis/preview audio | Completed |
| Whisper transcript | Completed |
| HTS-AT/PANNs semantic event labels | Preflight/metadata-only |
| NeMo diarization | Not available in this runtime |
| ECAPA Voice Store | Not available in this runtime |
| PE-AV embeddings | Preflight-only |
| CLAP reranking | Preflight-only |
| Demucs | AUTO correctly skipped because semantic event classifier is unavailable |
| SAM Audio | On-demand and gated; no automatic isolation requested |
| Hermes confirmation | Not run |

## Acceptance conclusion

The isolated project is runnable and preserves the source/scene/audio/timestamp contract, but it is not yet ready to replace the website backend. The remaining model workers (PE-AV, HTS-AT/PANNs, NeMo, ECAPA, Hermes integration, and production LanceDB ANN) must be implemented and preflighted first. The retrieval API currently uses an explicit deterministic fallback and never claims that PE-AV or CLAP ran. The existing analyzer and website were not modified during this run.

## Updated full-model comparison (2026-09-26)

The analyzer was rerun after preparing the isolated model workers and correcting
the HTS-AT adapter. The initial full-model validation run is:

`video_audio_analyzer/runs/c938423ea483bdc3-rerun-eab62cb9/`

The legacy summarizer was read-only during this comparison. Its cached transcript
is `Ewww! Brother, ewww! What's that?`, with three timestamped phrases at
0–2s, 3–5s, and 6–8s. It has one scene spanning 8.731s and 35 sampled frames.

The final analyzer run produced:

- the same single scene over 8.731s, preserving the existing scene division;
- three representative frames at 0.00s, 4.25s, and 8.50s;
- source audio bitstream copy, 16 kHz analysis WAV, MP3 preview, and four
  Demucs stems (drums, bass, other, vocals);
- Faster-Whisper `large-v3` transcript `Brother what's that?` at 2.93–6.17s;
- NeMo clustering diarization with local MarbleNet VAD and TitaNet speaker
  embeddings, returning one speaker over three intervals;
- one 192-dimensional ECAPA voice example persisted to the isolated test Voice
  Store under `video_audio_analyzer/validation_voice_store/`;
- official HTS-AT AudioSet inference, returning Speech and Music for this clip.
  Both predictions cover the complete short clip; no specific SFX class was
  confidently detected. These are broad clip-level classifications, not a
  claim that an individual sound effect occurs at every instant;
- PE-AV Base (1024D) plus a separate CLAP index (512D) with no vector
  concatenation. A real text query ran through both models and the API returned
  late-fused PE-AV/CLAP rankings;
- a 5-row LanceDB media index for the three keyframes and two sound events.

The analyzer's final transcript is shorter than the legacy transcript: it
misses the initial “Ewww!” and does not recover the second repetition. The
legacy caption is therefore the better transcript for this specific dummy.
This comparison does not justify replacing transcript provenance with ASR;
embedded/downloaded subtitles remain higher priority where present, and ASR
remains an explicitly sourced fallback. The analyzer preserves word/segment
timestamps and NeMo speaker turns, which the cached legacy transcript lacks.

The official HTS-AT integration initially produced hundreds of false positives
because the adapter applied sigmoid twice and used the wrong interpolation axis.
Those bugs were fixed; the final run now reports two broad event classes. Its
localization for this one short clip is still coarse and does not demonstrate
fine SFX boundaries.

Voice Store validation additionally ran in the analyzer's pinned Docker image:
LanceDB ANN returned a bounded same-project candidate first, then a
cross-project candidate when the local match was below the configured floor.
The dummy's repeated analysis remained an anonymous existing identity rather
than being merged with itself. This is retrieval validation only: no
cross-project identity was merged without a Codex director decision.

| Stage | Final result |
|---|---|
| Scene/frame preservation | Same scene/timeline; 3 selected frames versus legacy 35 |
| Transcript | Analyzer `Brother what's that?`; legacy cached transcript includes more words |
| Sound events | HTS-AT completed; Speech + Music, no confident named SFX |
| NeMo / ECAPA | Completed locally; one diarized speaker and one voice identity |
| LanceDB Voice Store | Local-first and cross-project top-K verified in pinned worker |
| PE-AV / CLAP retrieval | Both real models queried; separate dimensions and late fusion verified |
| Character ↔ voice association | Still unavailable: no configured person-tracking/ReID and active-speaker worker/checkpoint |
| Codex identity confirmation | Not run by the analyzer; no analyzer-side Codex adapter/credential bridge |
| SAM Audio | Correctly unavailable/on-demand; gated checkpoint and sidecar are not prepared |
| Legacy app / website / ComfyUI / Conda | Not modified |

The result is an end-to-end analyzer run, not acceptance of all planned stages.
The subsequent TalkNet validation below adds within-video active-speaker
evidence, but director confirmation and SAM Audio remain explicit gates; the
legacy transcript is better on this clip, and event timing needs broader
evaluation before production replacement.

## Final validation after TalkNet integration (2026-09-26)

The earlier integrated TalkNet run was:

`video_audio_analyzer/runs/c938423ea483bdc3-rerun-5e8c06b4/`

It adds a dedicated `video-audio-analyzer-talknet:dev` image, with official
TalkNet-ASD source and the TalkSet/S3FD checkpoints stored under the analyzer's
`models/talknet/`. TalkNet was isolated because its older inference
requirements must not constrain the PE-AV/NeMo worker or shared environments.
The dummy produced one S3FD face track and 216 timestamped TalkNet scores; 64
frames were classified as active speaking. NeMo's diarized speaker intervals
overlap that face track on two of three turns, emitted as
`candidate_needs_director_confirmation`. This is a voice-to-visible-track
candidate, not a final character identity or a cross-shot face identity.
TalkNet's code repository is MIT; the checkpoint host does not provide an
independent license statement in the downloaded artifact, so redistribution
or commercial use requires license review.

The official PANNs fallback was also run separately against the same
`analysis.wav` in a disposable analyzer container. It independently found
Speech and Music windows; it did not detect a confident named sound effect.
The final manifest still records HTS-AT as the selected detector. This
validates both detector paths without fabricating SFX or changing the
HTS-AT-to-PANNs fallback policy.

| Capability | Current state |
|---|---|
| HTS-AT / PANNs | Both live inference paths validated; Speech and Music found; no confident named SFX in this short clip |
| NeMo clustering diarization | Live, local and offline; 1 speaker, 3 turns |
| ECAPA persistent voice identity | Live 192D embedding, UUID-backed identity; validation uses the separate test store |
| Local-first/global Voice Store search | LanceDB ANN bounded top-K verified in its pinned runtime; no similarity-only merge |
| TalkNet active speaker | Live GPU inference; 1 face track, 216 scores; 2 diarized turns associated as candidates |
| Persistent character identity | Codex-confirmed within-video speaker↔face links; cross-video face/body identity still unavailable |
| CLAP | Live 512D embeddings and late reranking with PE-AV, in separate spaces |
| SAM Audio | Worker/image and temporary-output lifecycle tested; actual isolation waits on the gated local checkpoint |
| Website / Story Builder | Not changed or replaced; Playwright is deferred until approved UI integration |

Analyzer tests after these changes: `24 passed, 1 skipped`. The skipped
LanceDB test is gated to its pinned Docker runtime; equivalent same-project
and cross-project top-K integration was separately verified there. The full
pipeline exited successfully. AV1 hardware-decoding warnings are software
fallback notices and did not fail analysis.

## Latest completion check (2026-09-26)

The final full analyzer run after adding the isolated SAM Audio worker and
rechecking all connected stages is:

`video_audio_analyzer/runs/c938423ea483bdc3-rerun-009fbcdc/`

It completed with the source, scene/frame selection, audio extraction,
HTS-AT event detection, music features, large-v3 transcription, NeMo
clustering diarization, ECAPA embeddings, persistent Voice Store,
PE-AV embeddings, CLAP reranking, Demucs AUTO separation, TalkNet active
speaker inference, and LanceDB index all marked completed/enabled in the
manifest. It retained the same one-scene 8.731-second timeline and 3 selected
frames. There are two broad detected audio event classes; this clip did not
produce a confident named SFX label.

TalkNet produced one within-video face track and 216 timestamped scores. Of
the three NeMo turns, Codex `gpt-6-luna` confirmed one within-video
speaker-to-face link from temporal overlap and active-speaker evidence
(confidence 0.90). A second proposed link at 0.65 fell below the automatic
0.75 confidence floor and remains anonymous; the first turn had no explicit
active-speaker evidence. The analysis manifest remains immutable. Its separate review overlay and JSONL
audit are saved at
`video_audio_analyzer/director_reviews/c938423ea483bdc3-rerun-009fbcdc.json`
and `.jsonl`, and the analyzer API overlays them when returning a manifest.
No cross-project voice identity was merged. Cross-video face/body identity
is not asserted because no licensed appearance-ReID model is installed.

The optional SAM Audio image and worker are now built and isolated from the
base analyzer image. Its health/preflight and missing-checkpoint error path
were exercised. The final run correctly records `sam_audio: on_demand_unavailable`:
`facebook/sam-audio-base-tv` is Hugging Face gated, is not present locally,
and no access token is configured. The worker does not download weights
automatically. Therefore the SAM API lifecycle and truthful fallback are
implemented, but actual sound-isolation inference is not validated until the
owner accepts the model terms and stages the checkpoint.

The PANNs fallback was independently run against this same fixture's
`analysis.wav`, finding Speech and Music windows and no confident named SFX;
HTS-AT remains the selected primary detector. This demonstrates both
available detector paths, not exhaustive detection of every sound or a
quality benchmark over a representative dataset.

Final focused analyzer tests: `22 passed, 1 skipped` using the analyzer
package source path. The skipped case is the host-environment LanceDB test;
the equivalent bounded local-first/global Voice Store ANN checks were run in
the pinned analyzer Docker image. A broad host `pytest` collection was also
attempted but is not a supported invocation because it collects vendored
upstream tests and unrelated legacy tests; the focused analyzer test command
is the meaningful result. No website/UI files were changed, so Playwright was
not applicable. The legacy summarizer comparison remains read-only and is
summarized above: it provides fuller transcript text (`Ewww! Brother, ewww!
What's that?`) and 35 sampled frames, while the new analyzer has richer
speaker, voice, audio-event, multimodal-vector and searchable index metadata.

## Current 2026-09-27 closure checks

These checks supersede the older SAM-unavailable and pre-v2-search status
above. The source video, legacy analyzer, and website remained read-only.

- The new opt-in voice-collection run is
  `video_audio_analyzer/runs/c938423ea483bdc3-rerun-d8fbb2ae/`. It retained
  the same 8.731-second scene, three selected representative frames, source /
  analysis / preview audio, transcript and timestamps. HTS-AT returned broad
  Speech and Music events. ECAPA produced a timestamped voice sample and a
  192D identity in the isolated validation Voice Store. Codex wrote audit
  decisions; no identity was merged from similarity alone.
- A separate-project lookup against that real ECAPA centroid returned the
  same identity as a global top-K candidate. It is a candidate only; no
  identity link was written. The portable fallback searches identity
  centroids, not all raw speech samples against each other.
- A real SAM Large TV text-and-time isolation was run against the analysis
  audio with prompt `music`. It returned a valid, non-empty 48 kHz preview
  with the source run/event and time interval in provenance. Explicit save
  succeeded into a disposable `/tmp` repertoire, and the temporary preview
  was removed afterward. This verifies execution and lifecycle; subjective
  output quality still warrants human listening before production use.
- Reindexing rebuilt the separate corpus v2 index for all 14 runs and retained
  valid 512D legacy CLAP vectors only where record IDs and dimensions matched.
  CLAP and PE-AV remain independent vector spaces. The real GPU PE-AV query
  `a person speaking over a short music cue` now returns exactly one
  deduplicated `scene_clip` for this source, not zero-score CLAP-only rows.
- Final analyzer tests: `46 passed, 1 skipped`; Python compilation passed.
  The skipped test is the LanceDB integration test gated to run in the pinned
  analyzer container; separate project/global voice-store candidate behavior
  passed in the host test suite and the real cross-project lookup above.

Known scope limits remain: no confident named SFX was present in this short
fixture; cross-video face/body recognition is deferred pending a model with
terms suitable for this project; these outputs establish processing and
retrieval behavior, not director-grade narrative quality. Story Builder UI
integration and its Playwright regression are intentionally the next phase.

## Direct-video InternVideo3 primary-path run (2026-09-28)

This run uses the same supplied source and the new direct-video path. Its
outputs are under the canonical `video_repertoire/` tree:

`video_repertoire/analyses/video_audio_analyzer/c938423ea483bdc3/`

- Source: 8.731 seconds, 360×640, 30 FPS; the existing detector retained one
  scene spanning the complete source timeline.
- Frame handling: 11 selected change/anchor timestamps remain in the manifest
  as segmentation evidence; zero selected JPEGs or per-frame image-detailer
  reports were persisted. The direct model received the cut-defined MP4 clip.
- Audio: source bitstream, model-friendly WAV and MP3 preview were retained in
  that same run folder. HTS-AT detected broad Speech (.620) and Music (.578)
  events over the short clip. It did not identify a named SFX. Faster-Whisper
  large-v3 ran in CPU int8 mode and returned “Brother what's that?” at
  2.93–6.17s. Demucs AUTO completed. NeMo diarization and SAM Audio were
  unavailable in this particular run because their optional worker paths were
  not active; the manifest marks these accurately.
- InternVideo3-8B directly analyzed the MP4 at 1 sampled frame/sec. It wrote a
  short visual clip draft, synthesized the full-video narrative using the
  chronological clip plus timestamped transcript/audio labels, and made one
  backward context-refinement pass. The final text describes the bearded man
  in a white cap/headset, his hand gestures and sideward looks, the static
  dark-and-gold setting, and the timed spoken line. It does not assert a
  specific sound effect.
- Model-reported time (excluding checkpoint load): direct clip inference
  10.24s, overall clip/full synthesis/refinement sequence 42.23s. The
  checkpoint took approximately 97s to load in this cold one-shot run. This
  demonstrates direct-video functionality and quality, not a speedup over the
  legacy path. A persistent worker/warm-model benchmark is still needed before
  claiming interactive speed.
- PE-AV Base generated separate 1024D video/audio and summary-text vectors,
  including an independent full-video-summary text vector. CLAP was not
  concatenated. The run-local table and JSONL records were rebuilt; the
  website corpus search currently performs JSONL exact late-fusion scans (the
  report does not claim ANN queries are active).

Comparison with the cached legacy result: both preserve the same single scene
and 8.731-second timestamps. Legacy's transcript is more complete on this
sample (“Ewww! Brother, ewww! What's that?”); the new large-v3 transcript is
shorter but correctly sourced/timed. The new result adds direct video action
summary, one full-video summary, audio-event labels, linked clip/text PE-AV
vectors and multimodal time metadata, while avoiding saved frame JPEGs. This
is the requested functional replacement path; it does not establish that all
optional audio identity/isolation stages are active or that processing is
faster on long videos.
