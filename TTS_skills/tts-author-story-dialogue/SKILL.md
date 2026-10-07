---
name: tts-author-story-dialogue
description: Convert stories, scripts, scenes, or dialogue into TTS-Audio-Suite-compatible timed multi-character SRT plus selective emotion/style edit JSON. Use for narration, dialogue timing, speaker attribution, multilingual character tags, or production-ready story audio prompt structure.
---

# Author Timed Story Dialogue

Read `../_shared/references/dialogue-and-voices.md`, `../_shared/references/emotion-style-catalog.md`, and `../_shared/references/scene-surgery.md`.

1. Establish characters, voice aliases, languages, desired duration, and whether timing is supplied or estimated.
2. Write natural dialogue before assigning timestamps. Keep one primary performance unit per subtitle.
3. Create chronological SRT with `[Character]` at each subtitle start. Use explicit `[lang:Character]` only when overriding defaults.
4. Keep the SRT clean. Put selective emotion/style/speed/voice changes in `scene_edits.json` using the exact subtitle time range and transcript.
5. Use only implemented catalog values. Translate creative direction such as “worried” to a supported closest value only when the user accepts the interpretation; otherwise flag it.
6. Create or update an alias-map draft for every named character whose voice mapping is required.
7. Run `../tts-author-story-dialogue/scripts/validate_scene_package.py` before handing off.

Start from `assets/scene.srt`, `assets/scene_edits.json`, and `assets/character_alias_map.txt`. Report assumptions for estimated timing and preserve user-supplied timings verbatim unless they overlap or are invalid.
