# Video Scene Summarizer — Flaws & Weaknesses Analysis

> Source code location: `/home/riki/web_dev/video_summariser/src/video_scene_summarizer/`
> Config: `configs/settings.yaml`

---

## A. Frame Selection Flaws

### 1. Pixel-diff is naive for semantic understanding

The `score_frame_change()` function in `frame_extract.py` uses raw grayscale pixel differences on 160x90 downsampled images:

```python
target_size = (160, 90)
prev = cv2.resize(prev, target_size, interpolation=cv2.INTER_AREA)
curr = cv2.resize(curr, target_size, interpolation=cv2.INTER_AREA)
diff = cv2.absdiff(prev, curr)
return float(diff.mean() / 255.0)
```

This means:

- **Camera pan of a static scene** will register as *high* change — triggering unnecessary keyframe splits even though nothing semantically changed. A landscape pan where the subject matter is identical gets treated as visually "different."
- **Static camera with a talking person** whose facial expressions shift subtly scores very low and gets *missed*. A 10-minute interview shot on a tripod will be seen as one continuous "no change" block regardless of what's actually happening.
- **Compression artifacts, lighting flicker, codec noise, and encoding variance** can all inflate or deflate scores arbitrarily — the metric has no relation to meaningful visual events.

### 2. `min_scene_length_sec` threshold of 0.2s is dangerously aggressive

Almost any video will produce thousands of "scenes" from ffmpeg's native scene detection when this threshold is this low. The system deals with massive fragmentation. While downstream code merges tiny spans together, the volume still blows up frame extraction and VLM calls.

### 3. `frame_change_threshold: 0.08` is a fixed heuristic with no adaptation

Different resolutions, compression levels, and content types (animation vs. live-action vs. slides vs. screen recordings) all have totally different "natural" inter-frame differences. A single global threshold can't work well across domains.

### 4. No adaptive frame rate per scene type

The system extracts frames at a fixed analysis FPS (`analysis_fps: 4.0` in config). High-action scenes and talking-head scenes both get sampled at the same rate, meaning one wastes VLM calls on redundant frames while the other misses important visual moments.

---

## B. Frame-to-Frame "Connecting the Dots" Flaws

### 5. Object detection matching by label alone is broken

`_compare_objects()` in `frame_detail.py` groups detections simply by `label` string (e.g., "person"), then zips them in order:

```python
for label in labels:
    prev_items = previous_by_label.get(label, [])
    curr_items = current_by_label.get(label, [])
    for prev_item, curr_item in zip(prev_items, curr_items):
        # ... compares bbox centers of what it THINKS is the same object
```

Two different people labeled "person" with similar bounding boxes get matched as the *same object*, producing completely wrong "shift" deltas. There's no identity tracking (like DeepSORT or ByteTrack) — label-based matching without temporal ID continuity is semantically meaningless for human subjects.

### 6. "mostly stable position" threshold is 2 pixels

After resizing to 160x90, 2 pixels of shift is trivial. It effectively marks nothing as moving if its center shifts less than ~16px in the original resolution. But anything slightly more gets labeled with arbitrary directional text ("moves slightly right") that the downstream LLM has to interpret. The quantization to "left/right/up/down" loses fine-grained meaning entirely.

### 7. The VLM delta prompt relies on poor frame pairs

The prompt ("describe what changed from the first image to the second image") is fine in theory, but if the two frames were selected poorly by flawed pixel-diff heuristics (flaw #1), the comparison may be between non-sequential moments or frames that have nothing to do with each other narratively. Error compounds at this stage.

### 8. No cross-scene continuity tracking

Each scene is analyzed entirely independently. Objects/persons/props that enter at the end of one scene and carry through into the next are treated as fresh, new discoveries. The `previous_scene_overlap_frame` copy (in `build_scene_shells`) is purely cosmetic — it's only a single image file copied to disk, not actual context data passed between scenes. No entity, character, or state tracking across scenes exists at all.

---

## C. High-Level Flaws

### 9. Final summary generation loses detail through compounding layers

The pipeline: extract thousands of keyframes → describe each via VLM → stitch into scene narratives → (optionally) compress → compile all scenes for "final fusion." The LLM producing the ultimate summary works from *text representations of text representations of images*. Information degradation compounds at every layer. By the final step, much of the original signal has been lost through multiple reductions.

### 10. FFmpeg scene detection threshold of 0.3 misses semantic cuts

It will miss subtle camera cuts (e.g., cutaway closeups, dialogue-reverse-shot sequences, slow dissolve transitions) where pixel differences between shots are minimal but the meaning is entirely different. This is a well-known limitation of luminance-based scene detection.

### 11. No temporal smoothing or deduplication in frame selection

If a scene has 50 frames extracted at 4fps and 47 look nearly identical (e.g., a person speaking), the algorithm may still select multiple keyframes that differ by tiny pixel amounts — generating redundant VLM calls for essentially the same content. No clustering, cosine sim on feature vectors, or semantic dedup exists.

### 12. Lighting detection via dominant color is extremely shallow

`DominantColorProvider` grabs the top color from `cv2.kmeans` and labels it by name. A shift from "white" to "pale yellow" due to a lamp turning on gets reported as "dominant palette shifts from white to pale yellow" — technically accurate but practically useless for understanding scene continuity.

---

## D. Missing: Intelligent Transcript-Frame Correlation (Cross-Modal Temporal Fusion)

### The Problem

The current system runs audio and video analysis in **separate parallel tracks**:
1. **Visual track**: ffmpeg scene detection → frame extraction → VLM per-frame analysis
2. **Audio track**: Whisper transcript with segment-level timestamps (sentence granularity)

These two tracks are only loosely combined in `stitch_scene_story()` by a single `transcript_text` variable containing *all* text from that scene's time range, blindly concatenated together. The system has no mechanism to answer questions like:

- "The VLM saw someone standing at the window, and the audio says 'I'm leaving now' — is the person actually leaving or just standing there?"
- "What visual event corresponds to the narrator saying 'as you can see here'?"
- "Did the audio narrative change topic at the same moment a visual cut happened, or are they disconnected?"

The transcript-to-frame alignment should be **deep and temporal**, not just a blind timestamp range filter. Below are proposed approaches from research:

---

### D.1. Proposed: WhisperX-Style Forced Phoneme Alignment → Frame-Level Transcript Slots

Instead of Whisper's current sentence-level segments, use **WhisperX** (which has forced phoneme alignment) or upgrade to word-level timestamps for every transcript entry. Then partition the video timeline into **fine-grained temporal slots** (e.g., 0.5s–1s windows), and assign each transcript segment to its precise slot based on word-level timing. This gives us a high-resolution "audio column" aligned to the "video frame column."

**Why current approach is insufficient:** The existing `transcript_slice()` in `scenes.py` does:

```python
for segment in transcript.segments:
    if segment.end >= start_sec and segment.start <= end_sec:
        # grab everything — no precision
```

This grabs every sentence that overlaps the scene window with no sub-scene granularity. A 30-second scene with three different topics spoken sequentially gets dumped as one blob of text to the VLM with zero temporal structure.

**Implementation sketch:** Create a `transcript_slots` field on each scene where each slot has `[start, end, text, speaker(if diarization available)]`. Pass this structured array alongside the frames so the VLM sees "Frame at 5.2s aligns to transcript '...we need to configure...'".

---

### D.2. Proposed: Audio-Driven Scene Boundary Reinforcement (Multimodal Fusion)

The current system uses **only pixel differences** for scene boundaries. Research shows that combining audio features with visual features significantly improves accuracy:

#### Techniques worth investigating:

1. **Audio energy/entropy change detection** — compute short-time energy and spectral centroid of the audio in parallel with video scene detection. A simultaneous spike in both audio entropy AND visual frame difference at the same timestamp is a high-confidence cut point. An audio-only change (e.g., music swell during a static shot) should not produce an artificial visual scene boundary.

2. **Silence gap detection** — long silence gaps often indicate cuts/edits even when the visual is continuous. This is particularly useful for talk shows, interviews, and podcasts.

3. **Speech activity detection (VAD)** — using WhisperX's VAD or librispeech-style VAD to identify speaker-on/speaker-off transitions. Abrupt speech boundaries *should* trigger scene boundary consideration regardless of pixel similarity.

4. **TextTiling-inspired lexical shift detection** — compute rolling vocabulary profiles in the transcript (e.g., cosine similarity between consecutive windows of 10 sentences). A sudden vocabulary shift indicates a topic change. If this aligns with even a minor visual change, it reinforces a new scene boundary from the *semantic* side rather than the purely visual side.

5. **Speaker diarization boundaries** — if WhisperX's pyannote-based diarization is used, a speaker switch can indicate a scene cut in interview/podcast formats. The shift from Interviewer→Guest and Guest→Interviewer are natural "scenes" even if visually there's zero change.

---

### D.3. Proposed: Text-Frame Semantic Alignment via Embedding Cosine Similarity

Instead of blindly attaching all transcript text to every frame, perform **per-frame transcript grounding**:

For each analyzed keyframe at time `t`:
1. Gather transcript segments within a window around `t` (e.g., `t ± 3s`)
2. Compute embedding for each segment (using a lightweight sentence encoder like `all-MiniLM-L6-v2` or BGE)
3. Compute embedding for the VLM's own generated caption/description of that frame
4. Correlate them — highest-similarity segment is the "grounded transcript" for this frame

This tells you **what the person was actually talking about while that specific visual was on screen**. The benefit: the downstream scene stitching can now include context like:

```
Frame at 12.5s [VLM caption]: "Two people seated at a table, one gesturing."
Grounded transcript: "And this is where we configure the settings..."  (similarity=0.87)
Mismatch detected: Frame shows setup scene but narration already moved to topic B
```

This kind of mismatch detection is currently impossible with the system's blind timestamp-range approach.

---

### D.4. Proposed: Cross-Modal Topic Shift Detection for Scene Boundaries

The current `ffmpeg -filter:v "select='gt(scene,0.3)'"` is a **visual-only** scene detector. Research suggests several audio-visual joint scene segmentation methods:

1. **Scene-VLM (CVPR 2026)** — A fine-tuned Qwen2.5-VL-7B framework that jointly processes frames *and* synchronized subtitles/transcriptions for multimodal reasoning across consecutive shots. Each shot representation includes K sampled frames, synced subtitles, and optional actor/character info. This is the most directly applicable research to our codebase architecture since it uses our same base model (Qwen2.5-VL).

2. **StepVTG (Temporal Grounding with LLM)** — Uses chain-of-thought reasoning between text queries and video segments via "short-term cross-modal matching" refined by long-range temporal reasoning. The key insight: instead of binary scene/no-scene classification, use an LLM to output *confidence scores* per frame pair about whether a meaningful boundary exists, informed by both visual and audio features.

3. **Multi-pathway Text-Video Alignment (arXiv 2409.16145)** — Measures alignment through three pathways:
   - Step-narration-video alignment using narration timestamps
   - Direct step-to-video semantic similarity (long-range)  
   - Direct step-to-video fine-grained similarity (short-range)
   Fuses all three for reliable pseudo-step video matching.

Applied to our system, this would mean: instead of just asking the VLM "describe this frame," we also provide aligned transcript segments and use multiple alignment scoring pathways before deciding if two frames belong to the same scene.

---

### D.5. Proposed: Character/Entity Memory Across Scenes

Currently, once a scene boundary is detected, all context about entities in previous scenes is destroyed. To enable real storytelling-level understanding:

1. **Per-scene entity extraction** — For each scene, have the VLM explicitly list *people/entities* seen (not just YOLO generic labels like "person" but descriptions: "man in red shirt holding microphone").
2. **Cross-scene entity registry** — Build a lightweight registry that maps entities across scenes using similarity of their descriptions + temporal proximity.
3. **Context injection** — When analyzing Scene N, pass the entity registry up to Scene N+1 so the VLM can reason about continuity: "The man in red shirt from scene 3 is now seen sitting at the desk."

This is the difference between a system that describes isolated moments and one that *tells a coherent story*.

---

### D.6. Proposed: Closed Caption (CC/VTTE/SRT) Support

The current system only handles **spoken audio** via Whisper transcription. It does not support CC (closed captions) or SRT files as an input source. Many videos have CC with:
- Higher accuracy ASR (human-reviewed vs model-predicted)
- Explicit timestamp markers for each caption line
- Off-screen dialogue and sound-effect descriptions (e.g., `[music playing]`, `[door opens]`)
- Speaker identification

**Implementation path:**
1. Detect `.srt`, `.vtt`, or embedded CC tracks in the video file via `ffprobe`/`ffmpeg -streams`.
2. If found, use them as an *additional* text modality alongside Whisper (higher confidence source for what was actually said).
3. For videos with both spoken audio and CC: merge/cross-validate — differences between spoken transcript and CC reveal off-screen events described in captions but not heard/spoken.

---

### D.7. Proposed: Audio-Visual Mismatch Detection as a Feature

When transcript and visual align *poorly* at the embedding correlation level (from approach D.3), this is not a bug — it's **signal**. It could indicate:
- Off-screen narration ("voice of God" storytelling)
- Flashbacks/time jumps narrated but not visually shown yet
- Narrator summarizing what will appear later
- Music/intro sequence with no spoken words

Instead of forcing alignment, detect mismatches and flag them as structural events in the scene metadata. This enriches rather than degrades the summary.

---

## Summary Table

| Flaw | Severity | Fix Complexity | Impact |
|------|----------|----------------|--------|
| Pixel-diff frame selection | 🔴 High | Medium | Affects entire pipeline's frame inputs |
| Label-only object matching | 🔴 High | Medium-High | Breaks entity tracking completely |
| No cross-scene continuity | 🟡 Medium | Medium | Prevents "story" level understanding |
| Blind transcript-text blob | 🟡 Medium | Low-Medium | Wasted VLM context, lost precision |
| Fixed global thresholds | 🟡 Medium | Low | Poor adaptability across content types |
| Summary compounding degradation | 🟠 Medium-High | Medium | Final output quality limited early on |
| No transcript-frame grounding | 🔴 High | Medium | Biggest missing capability |
| Audio-visual-only parallel tracks | 🟡 Medium | Medium-High | Can't detect audio/visual disconnects |
| No CC/SRT support | 🟢 Low | Low | Misses high-quality captioned metadata |

---

## Research References

- **Scene-VLM** (CVPR 2026) — Multimodal video scene segmentation via vision-language models. Uses Qwen2.5-VL base, processes consecutive shots with frames + synchronized subtitles jointly. **[arxiv:2512.21778](https://arxiv.org/abs/2512.21778)**
- **StepVTG** — Long video temporal grounding with LLM chain-of-thought between multimodal inputs. **[link](https://mn.cs.tsinghua.edu.cn/xinwang/PDF/papers/2025_Localizing+Step-by-Step+Multimodal+Long+Video+Temporal+Grounding+with+LLM.pdf)**
- **Multi-pathway Text-Video Alignment** (arXiv 2409.16145) — LLM-based alignment via narration timestamps + semantic similarity pathways.
- **WhisperX** — Forced phoneme alignment for word-level timestamps + diarization. **[github: m-bain/whisperx](https://github.com/m-bain/whisperx)**
- **TextTiling** (Hearst, 1997) — Early lexicon-based text segmentation detecting topic boundaries via lexical shifts across sentence windows.
- **Cross-modal RAG for video** (NVIDIA) — Multimodal retrieval-augmented generation that fuses visual and audio textual information in a grounded pipeline. **[nvidia.dev](https://developer.nvidia.com/blog/an-easy-introduction-to-multimodal-retrieval-augmented-generation-for-video-and-audio/)**
- **KX Multimedia RAG** — Scene-based multimodal RAG preserving embedding links between frames and transcript. **[kx.com](https://kx.com/blog/revolutionizing-video-search-with-multimodal-ai/)**
