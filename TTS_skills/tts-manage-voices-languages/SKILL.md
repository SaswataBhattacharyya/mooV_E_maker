---
name: tts-manage-voices-languages
description: Organize and validate TTS-Audio-Suite voice recordings, exact companion transcripts, character aliases, narrator selection, language defaults, and multilingual tags. Use when adding voice files, editing #character_alias_map.txt, changing a character language, refreshing discovery, or preparing reusable voice data.
---

# Manage Voices and Languages

Read `../_shared/references/dialogue-and-voices.md`.

1. Preserve source recordings; work on copies.
2. Prefer `ComfyUI/models/voices/<collection>/` for personal voices.
3. Give each audio file a stable descriptive filename and an exact same-stem `.reference.txt`. Optionally keep metadata/license in a separate record; do not put metadata in the transcript used for cloning.
4. Add aliases to `#character_alias_map.txt`; prefer `Alias = target, language-code` for readability.
5. Verify every alias target matches an audio filename stem case-insensitively.
6. Use explicit SRT language tags for line-level override and alias defaults for character-wide behavior.
7. Run `scripts/validate_voice_library.py`, then refresh the voice cache.

Do not call a folder name a character; the audio filename stem defines the character. Do not call reference use fine-tuning. Obtain rights/consent for cloned voices.
