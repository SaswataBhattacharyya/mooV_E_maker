# Workflow Build Plan For Timed Multi-Character Emotion Audio

This file turns the earlier notes into a concrete build plan using the nodes that already exist in this repo and in the bundled example workflows.

The user goal is not one single workflow. It is really 4 related workflow types:

1. Automated timed multi-character TTS with emotion on selected parts
2. Best-quality timed multi-character TTS with native emotion control
3. Timed multi-character TTS using emotion reference audio
4. Manual "audio surgery" on an existing audio file, where only selected time ranges are changed

The clean way to think about this project is:

- `📺 Unified TTS SRT` is the timing backbone
- `🎭 Character Voices` is the voice-cloning / narrator reference backbone
- `🌈 IndexTTS-2` is the best native emotion-control backbone
- `🎨 Step Audio EditX` is the best post-processing / style / whisper / laughter / manual edit backbone
- `✏️ Unified ASR Transcribe` + `📺 Text to SRT Builder` are the backbone for editing existing audio by timeline


## 1. What The User Wants, Interpreted Correctly

Yes, this makes sense.

There are really 2 product directions:

### A. Automated workflow

Input:
- script or SRT
- multiple character voices
- optional emotion instructions or emotion reference audio

Output:
- one final timed audio file
- multi-character
- pauses / gaps controlled
- emotions on specific lines or parts

### B. Manual workflow

Input:
- an already existing audio file

Output:
- selectively changed only in chosen regions
- voice changed in some parts
- pauses inserted or extended in some parts
- style / whisper / emotion changed in some parts
- keep the rest of the original audio intact

That second one is not a single built-in magic node. It is a workflow assembly problem using:
- ASR
- SRT / timing data
- regeneration of selected slices
- optional Step Audio EditX post-processing
- audio splicing / concatenation


## 2. Most Important Build Decision

Do not try to force one workflow to do everything.

Build these as 4 workflows:

1. `Workflow A - Automated SRT + Step polish`
2. `Workflow B - Automated SRT + IndexTTS native emotion`
3. `Workflow C - Automated SRT + IndexTTS emotion reference audio`
4. `Workflow D - Manual audio surgery`

That is the clean architecture.


## 3. Best Existing Example Workflows To Reuse

These are the most relevant bundled examples:

- `example_workflows/Unified 📺 TTS SRT.json`
- `example_workflows/🌈 IndexTTS-2 integration.json`
- `example_workflows/🎨 Step Audio EditX - Audio Editor + Inline Edit Tags.json`
- `example_workflows/Qwen3 integration + ASR.json`

What they prove:

- `UnifiedTTSSRTNode` already handles timed multi-character generation
- `CharacterVoicesNode` already provides narrator / reference voice flow
- `IndexTTSEngineNode` already accepts `emotion_control`
- `QwenEmotionNode` already generates text-driven emotion control
- `StepAudioEditXAudioEditorNode` already edits existing audio
- `UnifiedASRTranscribeNode` + `TextToSRTBuilderNode` already create a timing-aware edit path from audio


## 4. Workflow A - Automated SRT + Step Audio EditX Polish

### Goal

Generate one timed multi-character file from SRT, then use inline edit tags or post-editing to add whisper, laughter, style, or emotion to selected segments.

### Best for

- fast setup
- multi-character dialogue
- exact subtitle timing
- selective emotional polish
- whisper / laughter / style effects

### Core node chain

1. `🎭 Character Voices`
2. `TTS Engine` node
   Recommended engines for this route:
   - `ChatterBox`
   - `F5-TTS`
   - `Qwen3-TTS`
   - `Higgs Audio`
3. `📺 Unified TTS SRT`
4. `PreviewAudio`

Optional:

5. `🎨 Step Audio EditX - Audio Editor`
6. `Audio concat / merge nodes` if manually editing only some generated pieces

### Best version of this workflow

Use inline edit tags directly inside the SRT text when possible.

Example:

```srt
1
00:00:00,000 --> 00:00:04,000
[Narrator] The cave was silent.

2
00:00:04,200 --> 00:00:07,000
[Alice] Did you hear that? <style:whisper:2>

3
00:00:07,200 --> 00:00:10,200
[Bob] Relax <emotion:calm>. It is probably just the wind.

4
00:00:10,500 --> 00:00:14,000
[Alice] No, I am serious haha <Laughter:2> <restore>
```

### Why this works

- `Unified TTS SRT` handles the timing and characters
- Step inline tags are applied selectively only where written
- This is the cleanest automated route if the emotion can be approximated by style / edit tags

### Limitation

This is post-processing emotion, not true native emotion modeling. It is strong for:
- whisper
- laughter
- speed
- style
- broad emotional coloring

It is weaker if you want extremely precise emotional acting from a real performance reference.


## 5. Workflow B - Automated SRT + IndexTTS Native Emotion

### Goal

Generate one timed multi-character file with native emotion control from IndexTTS-2.

### Best for

- best quality emotion-aware TTS inside the repo
- per-line emotional intent
- keeping one final timed file

### Core node chain

1. `🎭 Character Voices`
2. One of:
   - `🌈 IndexTTS-2 Text Emotion`
   - `🌈 IndexTTS-2 Emotion Options`
3. `⚙️ IndexTTS-2 Engine`
4. `📺 Unified TTS SRT`
5. `PreviewAudio`

### Wiring

- `QwenEmotionNode.emotion_control` -> `IndexTTSEngineNode.emotion_control`
- `IndexTTSEngineNode.TTS_engine` -> `UnifiedTTSSRTNode.TTS_engine`
- `CharacterVoicesNode.opt_narrator` -> `UnifiedTTSSRTNode.opt_narrator`

### SRT usage

Use normal SRT timing plus character tags:

```srt
1
00:00:00,000 --> 00:00:03,000
[Narrator] Welcome to the trial.

2
00:00:03,200 --> 00:00:06,500
[Alice] I did not do it.

3
00:00:06,700 --> 00:00:10,000
[Bob] Then explain where you were last night.
```

### Emotion method options

#### Option B1 - Prompt emotion for the whole run

Use `QwenEmotionNode` with template:

```text
Tense courtroom testimony: {seg}
```

This lets each segment get emotional analysis from its text.

#### Option B2 - Manual vector control

Use `IndexTTSEmotionOptionsNode` if you want fixed emotion blending rather than prompt analysis.

Good for:
- calm + sad blend
- fear + surprise blend
- excited + happy blend

### Limitation

This workflow is strong for native emotion, but it is not as convenient as Step EditX for things like:
- inserted laughter sounds
- post-style surgery
- whispering only one phrase in the middle of a line

If you need both, generate with IndexTTS first, then optionally polish selected regions with Step Audio EditX.


## 6. Workflow C - Automated SRT + IndexTTS Emotion Reference Audio

### Goal

Generate one timed multi-character file where emotion comes from a real reference audio clip instead of only prompt text.

### Best for

- "make this line sound like this emotional performance"
- preserving a real emotional reference style
- more grounded emotion transfer than prompt-only emotion

### Core node chain

1. `LoadAudio` for emotion reference audio
2. `⚙️ IndexTTS-2 Engine`
3. `🎭 Character Voices`
4. `📺 Unified TTS SRT`
5. `PreviewAudio`

### Wiring

- `LoadAudio(emotion_ref).audio` -> `IndexTTSEngineNode.emotion_control`
- `IndexTTSEngineNode.TTS_engine` -> `UnifiedTTSSRTNode.TTS_engine`
- `CharacterVoicesNode.opt_narrator` -> `UnifiedTTSSRTNode.opt_narrator`

### Best use pattern

Use this when the whole run or a large section should share a common emotional flavor.

If you need different emotions for different characters or segments:

- duplicate the engine path into multiple passes, or
- use character-level emotion reference tags supported by IndexTTS docs:

```text
[Alice:angry_ref] I warned you.
[Bob:sad_ref] I know.
```

This requires the emotional references to exist as discoverable voice items.

### Recommended hybrid

For the strongest "perfect one file" workflow:

- IndexTTS for core TTS + reference emotion
- `Unified TTS SRT` for exact timing
- optional Step Audio EditX only for small polish effects after generation

This is probably the closest thing to the user's "perfect one" workflow.


## 7. Workflow D - Manual Audio Surgery

### Goal

Take an existing audio file and surgically modify only chosen time regions.

This is the workflow for:
- change voice only in one range
- change emotion only in one range
- insert gaps / pauses
- rewrite one sentence only
- keep the rest untouched

### Important truth

This is a multi-stage workflow. It is not one node.

### Core node chain

1. `LoadAudio`
2. `✏️ Unified ASR Transcribe`
3. `📺 Text to SRT Builder`
4. Manually edit the produced text / SRT
5. `📺 Unified TTS SRT` to regenerate only the selected slices
6. `🎨 Step Audio EditX - Audio Editor` for post-edit style or emotion on regenerated slices
7. `Audio concat / splice chain` to reassemble original untouched audio + regenerated edited slices

### Practical operating model

#### Phase D1 - Extract timing map

- load original audio
- transcribe with `Unified ASR Transcribe`
- if needed, enable alignment-capable engine path
- build SRT with `TextToSRTBuilder`

#### Phase D2 - Mark the surgery zones

From the generated SRT, decide:

- which cues stay untouched
- which cues get regenerated
- where you want longer silence or pauses
- where you want a different speaker or style

#### Phase D3 - Regenerate only the target cues

Build a reduced SRT containing only the cues to replace.

Use:
- character tags for voice change
- inline Step tags for style/emotion
- or IndexTTS emotion control if needed

#### Phase D4 - Reassemble

Use audio splice / concat logic:

- original audio before edited cue
- regenerated cue
- original audio between edits
- regenerated cue
- remainder of original audio

### Two sub-variants

#### D-A: transcript surgery

Use when the content changes.

Example:
- replace one sentence
- replace one voice actor
- add a pause between two lines

#### D-B: pure style surgery

Use when the words stay the same but the delivery changes.

Example:
- make one line whisper
- make one line calmer
- add laughter to one line

In that case:

- cut that target piece
- run `StepAudioEditXAudioEditorNode` on only that piece
- stitch it back

### Best current implementation route

Manual surgery is best built as:

- ASR + SRT builder for timing extraction
- human edits in SRT / tag editor
- targeted regeneration or Step edit
- explicit audio concat

This is the correct way to think about it inside this repo.


## 8. Recommended Priority Order

Build these in this order:

### First

`Workflow B`

Why:
- most aligned to "perfect timed multi-character emotion output"
- strongest core feature combination
- uses existing official emotion path cleanly

### Second

`Workflow A`

Why:
- easiest to automate
- strongest for selective whisper / laughter / style
- very practical for real use

### Third

`Workflow D`

Why:
- highest manual control
- best for fixing already-made audio
- but more complex to assemble

### Fourth

`Workflow C`

Why:
- excellent quality
- but more setup-heavy because emotion reference management is stricter


## 9. What To Put Where - Voice Files, Emotion Files, Alias File

### Main voice references

Best storage location:

- preferred: `ComfyUI/models/voices/`
- also supported: this repo's `voices_examples/`

Best naming:

- `name.wav`
- `name.reference.txt`

Examples:

- `alice.wav`
- `alice.reference.txt`
- `bob.wav`
- `bob.reference.txt`

### What should be inside the main voice reference audio

Use:
- clean solo speech
- no music
- no reverb if possible
- no overlapping speakers
- stable microphone quality

Recommended length:

- ideal: 5 to 15 seconds
- acceptable: 3 to 30 seconds

For F5 / Step Audio EditX / strongest cloning quality:

- the transcript file should match exactly what is spoken
- normal clear speech is better than extreme acting
- one speaker only

### Emotion reference audio for IndexTTS

This is separate from the main identity voice in concept.

Use:
- one speaker
- very clear emotional performance
- no music / SFX
- no clipping
- no heavy room echo

Recommended length:

- ideal: 3 to 10 seconds
- acceptable: 2 to 15 seconds

Best content:

- one clean emotional phrase
- focused emotional delivery
- consistent emotion across the clip

Bad content:

- mixed emotions inside one file
- whisper + shout + laugh all in one clip
- dialogue with another voice

### Voice change control reference

If using voice cloning / narrator control via `Character Voices`:

- use the same rules as main voice references
- clean identity reference matters more than emotional acting

If using a clip for emotion reference:

- emotion clarity matters more than neutral identity purity

That means it is valid to maintain two kinds of assets for one character:

1. `identity voice ref`
2. `emotion ref`


## 10. Where To Save The Alias File And How To Write It

File location:

- `voices_examples/#character_alias_map.txt`

or, if your voice discovery is centered in the ComfyUI voices directory, keep the same alias map convention alongside your working voice library setup.

### Purpose

This lets you write:

```text
[Alice]
[Bob]
[Narrator]
```

instead of raw filenames.

### Valid formats

You can use either `=` or tab-separated mapping.

Examples:

```text
# Character Alias Map

Alice = female_01
Bob = male_01
Narrator = david_attenborough_cc3
```

With default language:

```text
Alice = female_01, en
Bob = male_01, fr
Narrator = david_attenborough_cc3, en
```

Tab-separated:

```text
Alice		female_01		en
Bob		male_01			fr
Narrator	david_attenborough_cc3	en
```

### Important rule

The alias points to the voice filename stem, not the folder name.

If you have:

- `voices_examples/female_01.wav`

then the alias should point to:

- `female_01`

not the full path.


## 11. Exact Node Recipes

## Recipe 1 - Timed multi-character + prompt emotion

Use:

1. `🎭 Character Voices`
2. `🌈 IndexTTS-2 Text Emotion`
3. `⚙️ IndexTTS-2 Engine`
4. `📺 Unified TTS SRT`
5. `PreviewAudio`

Connections:

- `Character Voices.opt_narrator` -> `Unified TTS SRT.opt_narrator`
- `QwenEmotionNode.emotion_control` -> `IndexTTS Engine.emotion_control`
- `IndexTTS Engine.TTS_engine` -> `Unified TTS SRT.TTS_engine`


## Recipe 2 - Timed multi-character + emotion reference audio

Use:

1. `LoadAudio` for emotion clip
2. `🎭 Character Voices`
3. `⚙️ IndexTTS-2 Engine`
4. `📺 Unified TTS SRT`
5. `PreviewAudio`

Connections:

- `LoadAudio.audio` -> `IndexTTS Engine.emotion_control`
- `Character Voices.opt_narrator` -> `Unified TTS SRT.opt_narrator`
- `IndexTTS Engine.TTS_engine` -> `Unified TTS SRT.TTS_engine`


## Recipe 3 - Timed multi-character + Step emotion/style tags

Use:

1. `🎭 Character Voices`
2. TTS engine node
3. `📺 Unified TTS SRT`
4. `PreviewAudio`

Write tags inside SRT:

```srt
1
00:00:00,000 --> 00:00:03,000
[Alice] Keep your voice down <style:whisper:2>

2
00:00:03,500 --> 00:00:06,000
[Bob] I am not afraid <emotion:angry>

3
00:00:06,500 --> 00:00:09,500
[Alice] I am serious haha <Laughter:2> <restore>
```


## Recipe 4 - Existing audio surgery

Use:

1. `LoadAudio`
2. `Unified ASR Transcribe`
3. `SRT Advanced Options`
4. `Text to SRT Builder`
5. edit SRT manually
6. `Unified TTS SRT` for replacement parts
7. optionally `Step Audio EditX - Audio Editor`
8. concat / splice outputs


## 12. Which Workflow Is Best For Which Need

### If user says:
"I want the best one-shot final timed emotional dialogue file"

Use:
- `Workflow B`

### If user says:
"I want convenient selective whisper/laughter/style editing in timed dialogue"

Use:
- `Workflow A`

### If user says:
"I have a real emotional acting clip and want that feeling"

Use:
- `Workflow C`

### If user says:
"I already have an audio file and want to change only some parts"

Use:
- `Workflow D`


## 13. Practical Recommendations

### Recommended MVP set to actually build first

Build these first:

1. `IndexTTS + Unified TTS SRT + Character Voices`
2. `Unified TTS SRT + Step inline edit tags`
3. `ASR + TextToSRTBuilder + targeted regeneration`

This gives:
- best timed output
- best selective emotion/style control
- best manual repair path

### Strong recommendation on "perfect workflow"

There is no single universally perfect workflow.

The strongest practical split is:

- `IndexTTS route` for native emotion quality
- `Step route` for local style surgery and whisper / laughter / restoration

That is the real system design.


## 14. Final Conclusion

The user request is valid and can be built using existing repo functionality.

The correct plan is to build 4 workflows, not force all needs into one graph:

1. automated timed multi-character with Step edit tags
2. automated timed multi-character with IndexTTS native emotion
3. automated timed multi-character with IndexTTS emotion reference audio
4. manual audio surgery from existing audio using ASR + SRT + targeted regeneration

If needed next, this plan can be converted into:

- exact node-by-node connection instructions
- example SRT templates for each workflow
- a recommended folder layout for voice assets
- ready-to-build ComfyUI workflow JSON drafts
