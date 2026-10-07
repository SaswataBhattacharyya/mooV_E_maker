# 5. Audio workflows

The audio features are a collection of specialized workflows rather than one universal voice model. They use ComfyUI/API workflows or local deterministic utilities depending on the operation.

## Audio Studio (`/audio`)

Typical path:

1. Select a Story Builder project.
2. Browse the installed voice/model catalog and capability report.
3. Add a voice reference asset (a transcript can be required by the selected block/workflow).
4. Map a project character to a reference voice.
5. Provide timed dialogue/SRT and parameters.
6. Submit timed TTS to ComfyUI and inspect generated audio/timing outputs.

The page also exposes block-library and audio edit tooling. Availability is workflow-dependent; catalog visibility is not proof that all blocks are executable.

## Audio Reconstruct (`/audio-reconstruct`)

This is part-by-part dialogue recording/reconstruction. A common sentence calibrates a character's voice settings; a highlighted dialogue part is prepared, a raw take is uploaded, ASR can compare against expected dialogue, and a take can be accepted. It intentionally keeps raw takes recoverable and makes acceptance explicit. It is not a general automatic cloning step.

## Music & Sound (`/music-sound`)

- ACE-Step creates music/instrumental audio via a supported ComfyUI workflow.
- Control Foley creates sound effects using its installed supported workflow and controls.
- Fine-tune preparation is separately gated; do not assume training runs automatically.

Both report capabilities/jobs and store project-scoped outputs. Model/node/runtime readiness must be checked.

## Audio Utilities (`/audio-tools`)

Curated library import/search/play/delete; denoise; extraction/conversion (including MP3); Demucs stem separation. These operations are explicit user jobs. Demucs source categories are production stems, not semantic sound-event labels.

## Audio Automation (`/automation`)

The ordered pipeline UI demonstrates a chain in which timed multicharacter TTS feeds audio splitting, a selected clip can pass through emotion change, and the result is stitched back while other clips are retained. A pipeline can be saved, validated, run, inspected, and a step retried. The executor catalog/schema determines which operations and parameters are available.

This audio pipeline is separate from the story artifact automation run also exposed on the same page.

## Generated audio versus reference audio

The app contains different semantics for:

- a clean voice/timbre reference used to condition new speech;
- exact recorded dialogue kept as the audio output;
- generated TTS dialogue;
- generated music;
- generated Foley/SFX;
- separated stems;
- detected/transcribed source audio from video analysis.

These should not be conflated. File attachment/reference slots only work if the selected workflow actually consumes those inputs.

## Manual recording formats and expected evidence

The Audio Reconstruct UI requests raw recordings per part and an expected transcript for ASR checks. The precise accepted format/limits should be read from `api/main.py` request validation and `services/audio_reconstruct.py` before producing a large batch. Do not infer MiniMax or local TTS limits from this separate recording tool.

