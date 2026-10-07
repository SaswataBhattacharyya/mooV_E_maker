---
name: tts-direct-emotion-style
description: Translate creative acting direction into supported Step Audio EditX emotion, style, speed, paralinguistic, and restoration instructions. Use for whisper, laughter, sadness, anger, pacing, voice-character preservation, inline tags, or scene edit JSON values.
---

# Direct Emotion and Style

Read `../_shared/references/emotion-style-catalog.md` and `../_shared/references/scene-surgery.md`.

1. Decide whether the request changes a whole segment or inserts a sound at a position.
2. Choose exactly one primary `edit_type` per scene-edit item. Use multiple items/passes deliberately when combining whole-segment effects.
3. Begin with one iteration; use two only when a stronger result is requested. Warn that three to five can reduce identity and clarity.
4. Prefer separate edit JSON for timed production. Use inline tags only when the selected workflow path implements inline post-processing.
5. Preserve the exact spoken transcript in `text`; tags are instructions, not transcript content.
6. Consider restoration after strong edits, but do not promise perfect identity recovery.

Reject unsupported values rather than silently inventing them. Explain mappings from prose direction to supported values.
