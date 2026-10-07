---
name: minimax-h3-video-prompting
version: 1.0
description: "Create production-ready MiniMax H3 prompts for text-to-video, image-to-video, first/last-frame video, last-frame video, and reference-to-video generation. Integrates with ComfyUI MCP and workflow files in story_builder/workflows/ricky/."
category: media
---

# MiniMax H3 Audio-Video Prompting

Create production-ready prompts for MiniMax H3 text-to-video, image-to-video, first/last-frame video, last-frame video, and reference-to-video generation. H3 generates visuals and synchronized stereo audio together, so prompts must describe the audiovisual timeline as one coherent event rather than treating sound as an unrelated afterthought.

## When This Skill Activates

Use this skill when the user asks to:

- write, rewrite, optimize, expand, debug, or critique a MiniMax H3 video prompt;
- convert an idea, script, storyboard, shot list, image, first/last frame, or reference pack into an H3 prompt;
- generate native dialogue, sound effects, ambience, or background music with H3;
- preserve a requested prompt format while improving its H3 compatibility;
- prepare a prompt for MiniMax H3 in ComfyUI or through the MiniMax API.

Do not activate merely because the word 'video' appears. Activate when MiniMax, H3, Hailuo, ComfyUI's MiniMax H3 nodes, or H3-style synchronized audio-video prompting is requested or clearly implied.

## Core Principle

Write a chronological audiovisual plan. Every important statement should answer at least one of these questions:

- What is visible?
- What changes over time?
- How does the camera observe it?
- What is heard at that exact moment?
- What must remain consistent?

Prefer observable instructions over abstract intentions. "The camera tracks beside the dragon as its wings beat twice" is more actionable than "make it epic." Translate mood words into visible or audible evidence: lighting, color, lens, movement, tempo, instrumentation, rhythm, volume, and texture.

## Supported Generation Modes

Determine the mode before writing the prompt.

### T2VA -- Text to Audio-Video

Use when the user supplies text only. Construct the complete visual and audio timeline from scratch.

Start directly with the three canonical fields:

~~~
{
  type: String | MiniMaxH3TextToVideo,
  workflows_dir: String | path-to-story_builder/workflows/ricky/vid_minmax_h3_t2v.json,
  prompt: String,
  duration: Number,
  width: Number,
  height: Number,
  unet_name: String | "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
  clip_name: String | "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
  vae_name: String | "minimax_h3_video_vae_fp16.safetensors",
  audio_vae_name: String | "minimax_h3_audio_vae_fp32.safetensors",
  noise_seed: Number
}
~~~

### I2VA -- First-Frame Image to Audio-Video

Use when an image must be the exact opening frame. Begin with this alignment instruction:

~~~
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
~~~

Then anchor Shot 1 to the image's subject identity, clothing or surface details, composition, lighting, key objects, and spatial relationships before describing forward motion.

Recommended motion logic:

first-frame anchor -> action begins -> continuous development -> result or reaction

Do not merely redescribe the image. The prompt must explain how the scene evolves from it.

### FL2VA -- First-and-Last-Frame Audio-Video

Use when the first and last images must be the opening and ending frames. Begin with:

~~~
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the D.DD-second mark of the target video.
~~~

Replace N with the final shot number and D.DD with the effective duration to exactly two decimal places.

Default to a single continuous shot unless the user explicitly wants cuts. Explain the visible transition path between the anchors:

opening state -> intermediate pose/object/composition changes -> narrowing difference -> final-frame landing

The final action, pose, lighting, camera angle, and composition must plausibly converge on Picture 2.

### L2VA -- Last-Frame Image to Audio-Video

Use when an image must be the exact ending frame. Begin with:

~~~
How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the D.DD-second mark of the target video.
~~~

Infer a plausible earlier state, then describe how the scene and camera gradually arrive at the supplied last frame.

Recommended logic:

plausible earlier state -> explicit transition path -> gradual convergence -> exact final-frame landing

### R2VA -- Reference to Audio-Video

Use when images, videos, or audio are references rather than mandatory first/last frames. State each reference's role explicitly in natural language:

- identity or character design;
- wardrobe, texture, prop, environment, or visual style;
- motion, choreography, camera movement, or editing rhythm;
- voice, ambience, sound effect, or musical character.

Do not tell H3 to copy everything from every reference. Explain what to borrow from each reference and what must remain newly generated. Do not mix first/last-frame roles with reference roles in the same request when the selected API or workflow treats them as mutually exclusive.

## Workflow Files Reference

Three workflow JSON files live in your project at `story_builder/workflows/ricky/`:

| File | Task Type | Description |
|:----|:---------|:-----------|
| `vid_minmax_h3_t2v.json` | T2VA | Text-to-video only (no input images) |
| `vid_minmax_h3_i2v.json` | I2VA + FL2VA | Image-to-video; handles t2va when no images connected, fl2va when first/last frames connected |
| `vid_minmax_h3_r2v.json` | R2VA | Reference to video; accepts up to 9 ref images, 3 ref videos, 3 reference audio clips |

## Model Files

**Model Storage Location:**

~~~
ComfyUI/models/
    vae/
        minimax_h3_video_vae_fp16.safetensors
        minimax_h3_audio_vae_fp32.safetensors
    diffusion_models/
        minimax_h3_fl2va_pruned_int8_convrot.safetensors (t2v/i2v)
        minimax_h3_ref2va_pruned_int8_convrot.safetensors (r2v)
    text_encoders/
        qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
~~~

**HuggingFace Links:**

- [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3)
- [ComfyUI #15224](https://github.com/Comfy-Org/ComfyUI/pull/15224)

## Resolution Settings

H3's native canvas is a 768px short edge, capped at 768x1344 pixels. Use megapixels selector:

| megapixels | Aspect | Output (multiple=32) |
|:----------|:------|:--------------------|
| 0.4 | 16:9 | 864 x 480 |
| 0.98 | 16:9 | 1344 x 768 |
| 1.0 | 16:9 | 1376 x 768 |
| 2.0 | 16:9 | 1920 x 1088 |

## Duration and Frame Grid

Duration is converted to a valid frame `length` via the Math Expression node, snapping up to the model's 17-frame-per-block (17k+5) grid at 24fps.

For FL2VA: convert seconds to frames with formula `(total_seconds * fps / num_blocks)`, then floor to nearest integer.

## How to Push a Prompt Through ComfyUI MCP

Use the `comfyui` toolset via MCP. Map your prompt to the corresponding workflow node inputs:

**For T2VA (`vid_minmax_h3_t2v.json`) -- use MiniMaxH3TextToVideo:**
~~~json
{
  "text_prompt": "[Shot 1] ...",
  "duration": 5,
  "megapixels": 0.98,
  "seed": random_int64,
  "unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
}
~~~

**For I2VA (`vid_minmax_h3_i2v.json`) -- use MiniMaxH3ImageToVideo:**
1. Load image via `LoadImage` node
2. Resize with `ImageScaleToTotalPixels` (use megapixels from reference table)
3. Pass to `MiniMaxH3ImageToVideo` via `first_frame`
4. Provide prompt in 3-field format
5. Set `width/height` via `ResolutionSelector`
6. Set duration and seed

**For R2VA (`vid_minmax_h3_r2v.json`) -- use MiniMaxH3ReferenceToVideo:**
1. Connect up to 9 ref images, 3 ref videos, 3 reference audio clips
2. Use `ref_image_size: match` (faster) or `max` (stronger identity fidelity)
3. Reference inputs in prompt as `<Picture 1>`, `<Video 1>`, `<Audio 1>`
4. Sampler: `res_multistep`. `beta` or `normal` scheduler tends to outperform `simple`

## Canonical H3 Prompt Structure

Unless the user explicitly requests another presentation format, produce the canonical three-field format.

### 1. integrated_multimodal_description

This is the main timeline. It includes:

- visual medium and style;
- opening composition;
- subject appearance and position;
- environment, lighting, weather, and important props;
- chronological actions and reactions;
- shot changes and camera motion;
- spoken dialogue, singing, or voiceover;
- diegetic sounds tied to visible events;
- exact on-screen text.

Start the field with `[Shot 1]`. The first shot does not need a timestamp. For later shots, use a precise, increasing cut time:

`[Shot 2] At 00:03.500, the camera cuts to ...`

Use timestamps only for actual shot changes or precisely synchronized events. All timestamps must fall inside the requested duration.

### 2. overall_soundscape

Write one continuous paragraph of roughly one to four sentences. Summarize environmental ambience, physical action sounds, and nonverbal human/creature sounds across the clip.

Suitable content:
- wind, rain, surf, traffic, machinery, room tone;
- footsteps, wing beats, impacts, cloth movement, object handling;
- breathing, laughter, gasps, growls, roars.

Do not repeat dialogue, singing, or background score here. Use `N/A` only when the user explicitly requests total silence.

### 3. non_diegetic_music

Describe music heard by the audience but not by the characters. Use one to three sentences focused on:

- instruments or synthesis;
- tempo and pulse;
- rhythm;
- density and dynamics;
- entry, build, accent, drop, or fade timing.

Avoid relying only on vague mood labels. Convert "cool," "epic," or "sad" into musical instructions. Example:

`non_diegetic_music: A mid-tempo hybrid score combines deep taiko hits, low analog synth pulses, and a rising brass figure, then cuts to a sustained final chord during the last second.`

Use `N/A` when no audience-only music is wanted.

## Human-Readable Storyboard Format

When the user asks to preserve a format like "style paragraph + Timeline + transitions + Audio + exclusions," keep that format. Improve the content without forcing the canonical field labels.

~~~
<Visual style, medium, palette, lighting, atmosphere, subject and environment.>

Timeline:
[0s-Xs] Shot 1: <opening composition, subject action, camera behavior, synchronized sound>.
[Xs-Ys] Shot 2: <new information, action, camera behavior, synchronized sound>.
...

<Editing and camera continuity rules.>

Audio: <ambience and action sounds>; <background music instruments, tempo, rhythm, dynamic arc>.

<Hard constraints: exact text, identity continuity, forbidden elements, no watermark, etc.>
~~~

## Prompt Construction Procedure

### Step 1 -- Extract the Brief

Identify:
- generation mode;
- duration;
- aspect ratio if relevant;
- subject or characters;
- visual medium and level of realism;
- environment and time of day;
- action arc;
- desired camera behavior;
- audio requirements;
- dialogue or on-screen text;
- reference roles;
- mandatory inclusions and exclusions.

Ask a question only when a missing detail blocks a valid prompt, such as an unspecified reference role or unknown target duration needed for frame alignment. Otherwise make restrained, internally consistent assumptions.

### Step 2 -- Set the Complexity Budget

The clip duration limits how many distinct events can remain readable.

Use these working heuristics:
- 4-6 seconds: usually one continuous action or one to three simple shots;
- 7-10 seconds: two to four shots or one richer continuous movement;
- 11-15 seconds: three to six shots if the action remains coherent.

Reduce complexity when:
- the subject must preserve a precise identity;
- readable on-screen text is important;
- the action involves hands, object exchange, or complex anatomy;
- first and last frames must match tightly;
- dialogue must synchronize with visible lips.

### Step 3 -- Draft the Action Spine

Summarize the clip as a causal chain before writing prose:

starting state -> initiating action -> main movement -> consequence -> final state

Every shot must advance this chain. Remove decorative shots that add no new information.

### Step 4 -- Assign Shots and Times

For each shot define:
- time boundary;
- framing;
- subject state;
- one main action;
- camera motion;
- key synchronized sound;
- continuity requirement entering and leaving the shot.

Times must be monotonic and must not exceed the duration. Avoid incompatible overlap such as two different camera cuts at the same moment.

### Step 5 -- Specify Camera Motion Naturally

A useful camera instruction combines:

motion type + optional amplitude + optional speed + target or reveal

Available vocabulary includes:
- zoom in / zoom out;
- push in / pull out;
- pan left / pan right;
- truck left / truck right;
- tilt up / tilt down;
- pedestal up / pedestal down;
- arc around the subject;
- track or follow the subject;
- static shot;
- slight or strong shake;
- POV;
- clockwise or counterclockwise roll.

Write it as part of the action:
*The camera tracks beside Dragonite at fast speed while the mountain ridge slides across the distant background.*

Do not stack contradictory directions. If only framing changes slightly, use camera motion rather than creating an unnecessary cut.

### Step 6 -- Build Visual Continuity

Repeat only the anchors necessary to prevent drift:
- species or identity;
- body shape and scale;
- costume or surface color;
- important props;
- left/right position;
- direction of travel;
- weather and lighting;
- damage or transformation state.

Use explicit continuity language when needed: *Dragonite retains the same orange body, cream belly, teal inner wings, proportions, and direction of flight across every shot.*

### Step 7 -- Design Native Audio

Treat audio as synchronized scene information.

For each visible event, consider a matching diegetic sound:
- wings -> air displacement and rhythmic wing beats;
- landing -> impact and debris;
- cloth -> flutter;
- machine -> motor or servo;
- mouth movement -> dialogue, roar, breath, or silence.

Then describe the continuous ambience in `overall_soundscape` and the audience-only score in `non_diegetic_music`.

Do not write "add cool music." Specify what "cool" means:
*A driving 100 BPM hybrid score with deep taiko drums, pulsing synth bass, short brass stabs, and a rising final chord.*

### Step 8 -- Handle Dialogue and Voice

Assign stable speaker IDs only to characters who vocalize:

`(S1), (S2), (S1,S2)`

On first appearance, identify the voice with concise traits such as age range, pitch, timbre, pace, and accent. Put only the exact spoken words inside the dialogue block:

*The calm, low-pitched pilot (S1) says: <d>Hold the course.*

Preserve user-provided dialogue exactly. Do not translate, paraphrase, fix punctuation, or add extra lines unless requested.

For off-screen voiceover, state that it is off-screen and keep any visible character's lips closed when lip movement would be misleading.

### Step 9 -- Handle On-Screen Text

Put exact visible text in English double quotation marks:

*A title card reading "COMFYUI" appears at center frame.*

Preserve capitalization, spelling, and punctuation. Keep text short. State where it appears, how long it remains, and whether it is static or moving.

### Step 10 -- Add Constraints Without Fighting the Main Prompt

Place critical exclusions at the end. Keep them short and concrete:

*No subtitles, captions, logos, watermarks, extra characters, duplicated limbs, or unrequested dialogue.*

Do not create contradictions such as requesting "no text" after specifying a title card.

## Prompt Style Rules

- Use plain, precise English.
- Follow chronological order.
- Prefer active verbs and observable changes.
- Name the visual medium early: live-action, cinematic, 2D animation, 3D CG, claymation, watercolor, vintage film.
- Separate diegetic sound from non-diegetic music.
- Give later shots exact increasing cut times in canonical prompts.
- Use one dominant camera action at a time.
- Preserve identity and spatial direction across cuts.
- Keep requested text and dialogue verbatim.
- Match prompt complexity to duration.
- For first/last-frame generation, describe the motion path rather than two disconnected still images.
- For references, assign each reference a specific role.

## Common Failure Modes and Repairs

| Failure | Repair |
|:--------|:-------|
| Aesthetic word pile ("epic, cinematic, amazing") | Convert adjectives into production details: lighting, lens, camera motion |
| Too many actions for the duration | Choose one readable action arc or increase duration |
| Camera contradiction (e.g., "static" + "rapid orbit") | Pick ONE dominant camera behavior per shot |
| Audio described only as mood ("cool music") | Specify instruments, tempo, rhythm, dynamic arc |
| First/last frames treated as unrelated images | Specify intermediate changes in pose, object state, composition |
| Repeated identity drift | Establish compact continuity anchor once, reinforce only at cuts |
| Sound duplicated across fields | Keep dialogue/event sounds in timeline; summarize ambience in overall_soundscape; reserve non_diegetic_music for score |
| Vague reference instruction ("use all references") | Specify: "Use Image 1 for identity; Video 1 for motion; Audio 1 for music" |

## Validation Checklist

Before returning a prompt, verify:

**Mode and Timing:** correct mode selected? keyframe alignment at start? cut times increasing and inside duration?

**Visuals:** medium/style stated early? subject/environment/lighting clear? every shot has observable action? identity scale direction prop continuity preserved?

**Camera:** physically understandable movement? amplitude/speed included only when useful? cuts add new information rather than just changing distance?

**Audio:** visible actions paired with plausible sounds? ambience separated from score? instrumentation/tempo/rhythm specified? dialogue exact and attributed?

**Text/Constraints:** visible text quoted exactly? exclusions consistent? free of unnecessary repetition?

## Output Contract

When the user asks only for a prompt:

- return the final prompt in a single fenced block;
- do not prepend a long explanation;
- preserve the requested format;
- include no settings, model-installation instructions, or unrelated advice.

When the user asks for analysis:

- explain the mode selected;
- identify assumptions;
- provide the final prompt;
- note one to two parameters that must match outside the prompt (duration, aspect ratio).

## Reusable Canonical Templates

### T2VA
~~~
integrated_multimodal_description: [Shot 1] <medium/style and opening composition>. <subject action, camera action, synchronized diegetic sound>. [Shot 2] At 00:SS.mmm, the camera cuts to <new framing and action>. <continuity and ending state>.

overall_soundscape: <ambience, physical action sounds, and nonverbal vocal sounds across the clip>.

non_diegetic_music: <instruments, tempo, rhythm, dynamic arc, and ending behavior, or N/A>.
~~~

### I2VA
~~~
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] <preserve Picture 1's subject, style, composition, lighting, spatial anchors>. <describe forward action and camera movement>. <result or reaction>.

overall_soundscape: <ambience and synchronized action sounds>.

non_diegetic_music: <music description or N/A>.
~~~

### FL2VA
~~~
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark; Picture 2 (from Shot N) aligns with the D.DD-second mark.

integrated_multimodal_description: [Shot 1] <begin in Picture 1's state>. <describe continuous physical and compositional path>. <settle into Picture 2's exact ending state>.

overall_soundscape: <ambience and transition sounds>.

non_diegetic_music: <music description or N/A>.
~~~

## Source Basis

This skill is synthesized from the official MiniMax H3 Video Prompt Writing Guide, MiniMax API documentation, and ComfyUI's official MiniMax H3 workflow documentation. Treat those sources as authoritative when this skill conflicts with a future model or API update.
