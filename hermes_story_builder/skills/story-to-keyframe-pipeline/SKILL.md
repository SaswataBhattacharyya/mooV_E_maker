---
name: story-to-keyframe-pipeline
description: Convert a story (or scene list) into generated image assets and animated keyframes using ComfyUI Qwen Image 2512 + Qwen Image Edit 2511. Orchestrates asset generation → shot planning → composite keyframes. Use when user provides source text for story/image production or asks to 'generate images from a story', 'create frames', 'do visual production', etc.
license: MIT
metadata:
  hermes:
    tags: [story-boarding, image-production, qwen-image, compositing, keyframes]
    related_skills: [image-generation-routing, comfyui-media-operator, minimax-h3-video-prompting]
---

# Story-to-Keyframe Pipeline

## Conceptual Flow (what we do)

```
User provides story
  ↓
Save raw + section into scenes
  ↓
Plan: map characters & backgrounds per scene/shot
  ↓
Phase 1: Generate CHARACTER assets (consistent portraits, any angle pose OK)
  ↓
Phase 2: Generate SCENE BACKGROUND assets (with ref-image reasoning when needed)
  ↓
Phase 3: Composite KEYFRAMES — layer specific character images onto matching backgrounds with qwen edit per shot/pose
```

**The guiding question at every stage:** "Can I get away with one image from my pool, or do I need a new generation/refinement (and why)?"

## Phase 0: Setup & Story Ingestion

### Ask for the story first if not provided. If already in scenes, ask if they want to keep that structure or re-parse into more granular shot-level detail for better keyframe control.

```
mkdir -p /home/riki/web_dev/story_builder/input/$STORY_NAME/{characters,scene_backgrounds,keyframes}
cp <story_source> /home/riki/web_dev/story_builder/input/$STORY_NAME/story.txt
```

**Story file:** Save the original text as `input/$STORY_NAME/story.txt`. If user says "it's already in scenes," ask whether to use their scene division directly. If they say yes, note each scene heading; if no, parse for natural scene breaks (location changes, character arrivals/departures, time/space jumps).

### Reasoning for any improvisation:
- **Before changing anything the user provided** (scene count, character names, settings), ALWAYS stop and explain WHY you need to change it. Get explicit approval. Example reasons:
  - "Scene 3 mentions 'the alley behind the cafe' but the story never introduced a cafe — I'll add one in Phase 1 planning and flag this."
  - "Character X appears once but with dialogue — per coherence rules I'm adding them as recurring character #5."
  - "Scenes 4,5,6 all happen at the same location from opposite angles — one base background generated in Phase 2 is enough; I'll use qwen-edit to get alternative perspectives."

## Phase 1: Character Asset Generation

### Identify characters needing coherence:
- Any character who appears across multiple scenes → **always** generate a dedicated portrait asset.
- Characters with dialogue even if they appear once → **flag for generation** (their visual identity matters).

### Create `characters.json` in the input folder listing each character with a qwen-image-2512 description:
```json
{
  "character_portraits": [
    {
      "name": "Kael",
      "age_description": "30s, lean build",
      "appearance": "dark shoulder-length hair, sharp eyes, scar left eyebrow, wears a long grey duster coat",
      "pose_preference": "standing profile against neutral bg (for later compositing flexibility)",
      "prompt": "Portrait of Kael, a man in his 30s with lean build, dark shoulder-length hair, sharp piercing eyes, a scar on the left eyebrow, wearing a long grey duster coat. Standing in confident posture against plain background."
    }
  ]
}
```

### Generate characters:
1. Use **qwen-image-2512** (text-to-image) for each character portrait. 
   - Prompt follows qwen T2I style: explicit natural language describing appearance, clothing, pose, expression.
   - Neutral/blank background color so compositing won't clash with scenes.
   - Save result to `input/$STORY_NAME/characters/<character_name>.png`.
   - Use a consistent seed strategy (sequential seeds for batch portrait generation).

2. **Prompt construction rules:** Write concise visual prose: clothing, build, hair, colors, expression, pose. Avoid generic quality-word piles (no "masterpiece", "best quality"). Make it qwen-image-2512 compatible.

## Phase 2: Scene Background Asset Generation & Reasoning

### Identify unique backgrounds:
- Group scenes by location/environment. Same room/hallway/landscape = same base background.
- Note where the camera angle changes → this requires **reference images** (qwen-image-edit with the original as reference to produce angle perspective).

### Create `scene_layouts.json` mapping scenes and shots:
```json
{
  "story_name": "Trial I",
  "input_folder": "/home/riki/web_dev/story_builder/input/Trial-I",
  "characters": {
    "kael": "input/Trial-I/characters/kael.png"
  },
  "scene_backgrounds": [
    {
      "id": "bg_library_exterior",
      "description": "Street scene with stone building facade, cafe on right side, trees along sidewalk, evening golden hour lighting, car parked near curb. Wide street view.",
      "prompt": "(qwen-image-2512 prompt for this background)",
      "used_by_scenes": ["Scene 1", "Scene 3"],
      "needs_refinement_for_angles": [
        {
          "id": "bg_library_exterior_angle_right",
          "description": "Same street but from right angle perspective — same buildings, same cafe, same car in distance but different vanishing point.",
          "uses_reference_from": "input/Trial-I/scene_backgrounds/bg_library_exterior.png",
          "edit_prompt": "Change ONLY the camera angle to right side. Keep all building details, cafe position, trees, and parked car exactly as they are. Same lighting and color palette. New perspective showing the left side of the street.",
          "used_by_scenes": ["Scene 4"]
        }
      ]
    }
  ],
  "shots": [
    {
      "shot_id": "S01-K",
      "scene": "Scene 1",
      "description": "Medium shot, Kael standing on the street corner looking left at the approaching car. Cafe visible in background.",
      "character_images": ["input/Trial-I/characters/kael.png"],
      "background_image": "input/Trial-I/scene_backgrounds/bg_library_exterior.png",
      "prompt": "(qwen-image-edit-prompt for this specific shot)"
    }
  ]
}
```

### Generate backgrounds:
1. **First-angle backgrounds** → use **qwen-image-2512** (T2I) with a detailed environmental description as the prompt. Include: architecture, lighting, weather, time of day, objects, atmosphere, color palette, spatial layout. Use qwen T2I style — explicit natural-language relationships between elements.

2. **Angle-changed backgrounds** → reason step by step:
   - Does this scene share the same location as a previous one? Yes → get the existing background image.
   - Is the angle different enough to need a new generation (not just cropping/panning)? 
     - If yes (new vanishing point, visible but unseen surfaces): Use **qwen-image-edit-2511** with `image1` = original background + edit prompt "Change ONLY [the perspective/camera angle]. Keep ALL existing elements exactly as they are: the buildings at these specific locations, the car in this position, trees here... New angle should show: [describe visible new surfaces]."
   - If no (same angle, just different lighting/time): May still be worth qwen-edit with "Same layout but change to night time"

3. Save all backgrounds directly to `input/$STORY_NAME/scene_backgrounds/<bg_id>.png`.

## Phase 3: Shot Planning & Keyframe Generation

### Shots (sub-divisions of scenes):
Each scene can have multiple angles/focuses = different shots/keyframes. For each shot, determine:
- **Which character(s)** are in the frame (not all characters are visible in every shot)
- **Which background** they're against
- **What change/composite** is needed — which existing image goes where

Example scene with multiple shots:
```
Scene 1 — "The Street"
Shot 1a: Wide establishing — no characters yet, just the location (already has bg image → use qwen-image-edit if we need this specific framing)
Shot 1b: Medium shot — Kael standing on corner, looking at car. Uses character 'kael' + bg 'library_exterior' composition.
Shot 1c: Close up — Kael's face, background blurred (different character image with close-up pose).
```

### Shot planning JSON structure:
- Each scene section in the file has `"shots"` array with numbered sub-sections (e.g., S01-S1a)
- Each shot references `character_images` as a relative path — if Kael isn't in this shot, they don't get listed. If the car is part of the shot, it's listed too.

### Generate keyframe images:
1. For each shot with characters + background → use **qwen-image-edit-2511** with:
   - `image1` = character portrait (with transparent/neutral bg)
   - `image2` or `image3` = background scene
   - Prompt describes the composite: "A man [description matching character] standing [position description] in front of this [setting description]. He is located at [exact position, e.g., 'the center-right third of the frame']. The car from the background should remain visible behind him. Natural lighting that matches."
   - Preserve constraints in edit prompt to keep existing elements consistent.

2. For shots with multiple characters → use up to all 3 image inputs (qwen-edit-2511 supports up to 3 input images). If more needed, generate a composite first then edit.

3. Save each keyframe to: `output/$STORY_NAME/scenes/<scene_name>/keyframe_<shot_id>.png`

## Execution Pipeline — How to Call Everything

### Always use the bundled runner (NEVER curl/browser):
```bash
python /home/riki/web_dev/story_builder/hermes_comfyui/runner/comfyui_runner.py run --request /tmp/request.json
```

### For character backgrounds:
```json
{
  "workflow": "qwen-image-2512",
  "prompt": "(detailed description)",
  "width": 1024,
  "height": 1024,
  "seed": (some seed)
}
```

### For perspective-refined backgrounds:
```json
{
  "workflow": "qwen-image-edit-2511",
  "prompt": "Change ONLY the camera angle to [describe]. Keep ALL existing elements exactly as they are.",
  "input_images": [
    "/home/riki/web_dev/story_builder/input/Trial-I/scene_backgrounds/baseline.png"
  ]
}
```

### For keyframe compositing:
```json
{
  "workflow": "qwen-image-edit-2511",
  "prompt": "[Character description matching image1] is positioned at [specific location]. Background setting matches the [describe background elements from image2], with lighting and colors preserved.",
  "input_images": [
    "/home/riki/web_dev/story_builder/input/Trial-I/characters/kael.png",
    "/home/riki/web_dev/story_builder/input/Trial-I/scene_backgrounds/library_exterior.png"
  ]
}
```

## Output Folder Structure (Final)
```
output/
└── $STORY_NAME/
    ├── scenes/
    │   └── <Scene-1-name>/
    │       ├── keyframe_01.png
    │       └── keyframe_02.png
    └── ... (more scenes)

input/
└── $STORY_NAME/
    ├── story.txt
    ├── character_portraits.json
    ├── scene_layouts.json          ← scene→shot mapping, bg & char references
    ├── characters/
    │   ├── kael.png
    │   └── mia.png
    ├── scene_backgrounds/
    │   ├── bg_library_exterior.png
    │   └── bg_library_exterior_angle_right.png
    └── keyframes/                 ← staging area for generated assets
```

## Decision Rules (critical)
- **Reuse over regenerate:** If characters/bgs are in the pool and match → reuse.
- **Reference before new-gen:** If a scene overlaps with an existing location but needs different angle/perspective → use qwen-edit on the reference, not fresh T2I.
- **Shot-specific character lists:** Each shot explicitly states which characters appear. Only those get composited.
- **Never claim success from prompt ID alone** — always confirm completion + output files exist.
- **Never edit master workflow JSONs** directly.

## Prompt Construction Rules
- **Z-Image Turbo:** Concise visual prose only (subject, action, shot, setting, lighting, medium, palette). Avoid quality word piles. Fast/anime/illustration style.
- **Qwen Image 2512 T2I:** Explicit natural-language relationships — exact quoted text if any, foreground/background hierarchy, spatial positioning, camera geometry. No generic terms.
- **Qwen Edit 2511:** Begin with "Change ONLY...", list preservation constraints for ALL existing elements, assign each input image a role, describe the specific change. Never ask to "vaguely combine references."

## Session Progress Tracking
After each phase, save a brief progress file: `input/$STORY_NAME/.pipeline_progress.json` listing which assets are generated and which remain pending. This lets us resume or batch process efficiently.
