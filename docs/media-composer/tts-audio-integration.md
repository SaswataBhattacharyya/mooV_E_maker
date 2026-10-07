# TTS-Audio-Suite Integration Notes

The media composer should treat `Art_ist_min/TTS-Audio-Suite` as a connected subsystem, not just a side repository.

## Why It Matters

This suite provides:

- multi-character timed TTS
- SRT building and timing
- ASR transcription
- voice changing
- emotion control
- audio cleanup and surgery
- foley and sound-design paths
- custom Python utilities that are useful even outside direct ComfyUI graph execution

## Important JSON Workflow Surfaces

Already represented in the workflow library:

- `TTS_audio_multichar_timed_wf.json`
- `audio_SRT_timing.json`
- `audio_emotion.json`
- `hunyuan_foley.json`

Additional example flows live in:

- `Art_ist_min/TTS-Audio-Suite/example_workflows/`
- `Art_ist_min/TTS-Audio-Suite/example_workflows/ricky/`

## Important Custom Python and Node Surfaces

### Unified nodes

- `nodes/unified/tts_text_node.py`
- `nodes/unified/tts_srt_node.py`
- `nodes/unified/asr_transcribe_node.py`
- `nodes/unified/voice_changer_node.py`

### Engine nodes

- `nodes/engines/qwen3_tts_engine_node.py`
- `nodes/engines/index_tts_engine_node.py`
- `nodes/engines/f5tts_engine_node.py`
- `nodes/engines/step_audio_editx_engine_node.py`
- `nodes/engines/vibevoice_engine_node.py`
- `nodes/engines/rvc_engine_node.py`
- `nodes/engines/higgs_audio_engine_node.py`

### Audio utility nodes

- `nodes/audio/scene_concat_node.py`
- `nodes/audio/scene_splitter_node.py`
- `nodes/audio/scene_edit_driver_node.py`
- `nodes/audio/merge_audio_node.py`
- `nodes/audio/voice_fixer_node.py`
- `nodes/audio/analyzer_node.py`
- `nodes/audio/vocal_removal_node.py`

### Utility modules and scripts

- `utils/audio/scene_concat.py`
- `utils/audio/scene_splitter.py`
- `utils/audio/scene_edit_driver.py`
- `utils/audio/timed_scene_concat.py`
- `utils/asr/srt_builder.py`
- `utils/timing/engine.py`
- `scripts/concat_scene_audio.py`
- `scripts/split_scene_audio.py`
- `scripts/edit_scene_clips.py`
- `scripts/timed_concat_scene_audio.py`
- `scripts/convert_audio_to_mp3.py`

## Integration Rule

The media composer should support both:

1. pure ComfyUI workflow execution
2. helper-tool execution through Python utilities where that is a better fit

This matters especially for:

- subtitle timing
- scene-level audio assembly
- voice cleanup
- post-generation audio surgery

## UI Implication

Audio should become its own area inside the media composer.

Suggested tabs:

- `Dialogue TTS`
- `SRT / Timing`
- `Voice / Emotion`
- `Audio Edit`
- `Foley / Sound Design`
