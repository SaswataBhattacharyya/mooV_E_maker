# Dialogue, Voice, and Language Contracts

## Dialogue syntax

- Use SRT timestamps as `HH:MM:SS,mmm --> HH:MM:SS,mmm`.
- Put the character tag at the start of each subtitle line: `[Alice] Text`.
- Untagged text uses `narrator`.
- Use explicit language as `[de:Alice] Text`; a language-only tag such as `[de:]` retains narrator behavior.
- Per-segment parameters use pipes inside the tag, for example `[Alice|seed:42]`.
- Do not place Step Audio EditX directives in clean SRT when producing a separate edit manifest.

## Voice discovery

User voices may live recursively under:

1. `ComfyUI/models/voices/` (highest standard priority)
2. `ComfyUI/models/TTS/voices/`
3. `TTS-Audio-Suite/voices_examples/` (bundled examples)

Supported audio suffixes are `.wav`, `.flac`, `.mp3`, `.ogg`, `.m4a`, and `.aac`.
The character identifier is the lowercase audio filename stem; folders are organizational only.

Companion transcript priority for `Speaker.wav`:

1. `Speaker.reference.txt`
2. `Speaker.txt`

The transcript must match the words actually spoken in the reference recording. F5-TTS and other audio-plus-text engines require it. ChatterBox can use audio without text, but retaining an accurate transcript improves portability.

## Alias map

Name the file `#character_alias_map.txt`. Comments and blank lines are ignored.

```text
Alice = female_01, de
Bob	male_01	fr
Narrator = david_attenborough cc3, en
```

Both equals/comma and tab-separated formats are accepted. Alias and target matching is case-insensitive. Language defaults attach to the alias name. Explicit language in a dialogue tag overrides an alias default; otherwise the alias default overrides automatic detection/global defaults.

Alias load priority, highest last: bundled examples, `models/TTS/voices`, `models/voices`, then configured extra voice paths.

After adding or changing voices, use the `Refresh Voice Cache` node or refresh the Character Voices dropdown; restart only if discovery remains stale.

## Practical reference-audio preparation

- Use clean, single-speaker audio without music, reverb, clipping, or overlapping speech.
- Prefer a natural representative performance and exact transcription.
- Keep original archival recordings separate; place normalized working copies in the voice library.
- Voice cloning is inference, not model fine-tuning. One reference clip is enough for cloning; fine-tuning requires a transcribed multi-clip dataset.
