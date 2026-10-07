---
name: image-generation-routing
description: Route and write prompts for Z-Turbo and Qwen Image.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [image-generation, comfyui, z-image, qwen-image, prompting, anime, photorealism]
    category: creative
---

# Image Generation Routing

Use this skill to convert a user's visual request into a model-specific prompt for this three-model image system:

- **Z-Image-Turbo** — fast text-to-image; default for anime and a strong default for photorealistic generation.
- **Qwen-Image-2512** — text-to-image; use when complex semantic adherence, detailed scenes, typography/text, or precise natural-language composition matters.
- **Qwen-Image-Edit-2511** — image editing; use whenever one or more source/reference images already define the subject, scene, identity, layout, or style.

The goal is not to make one generic prompt and send it to every model.
First select the correct model, then rewrite the request in the prompt language that suits that model.

---

## When to Use

Activate this skill when the user asks to:

- generate an image or image prompt;
- create a first frame for an image-to-video workflow;
- create or modify a last frame from a first frame;
- edit an existing image;
- preserve a person, character, animal, object, product, environment, or art style while changing something;
- generate anime or 2D animation imagery;
- generate photorealistic imagery;
- render text inside an image;
- compare or choose between Z-Image-Turbo, Qwen-Image-2512, and Qwen-Image-Edit-2511;
- turn a rough visual idea into a ComfyUI-ready prompt.

If the user explicitly names one of the three models, obey that choice unless the requested operation is impossible for that model. If it is impossible, explain the mismatch briefly and route to the correct model.

---

# Core Routing Policy

## Rule 1 — Existing image means Qwen-Image-Edit-2511

If the task starts from an existing image and asks to change it, default to:

**Qwen-Image-Edit-2511**

Examples:

- change pose;
- change facial expression;
- move a person;
- add/remove an object;
- alter clothing;
- change material;
- preserve a character while changing action;
- create a last frame from a first frame;
- combine reference images;
- preserve an anime design while changing the scene;
- replace text in an existing image.

Do not route ordinary image editing to Qwen-Image-2512 or Z-Image-Turbo.

---

## Rule 2 — Anime text-to-image defaults to Z-Image-Turbo

For:

- Japanese anime;
- hand-drawn animation;
- cel-shaded 2D art;
- anime film frames;
- manga-like illustration;
- stylized 2D character scenes;

default to:

**Z-Image-Turbo**

The user's current local testing showed Z-Image-Turbo producing a more authentic flat 2D anime-frame appearance than Qwen-Image-2512 for the same scene.

Use Qwen-Image-2512 for anime only when:

- the user explicitly requests it;
- Z-Turbo repeatedly misses complex scene semantics;
- accurate text/signage is a major requirement;
- the composition contains many relationships that need stronger language following.

---

## Rule 3 — Photorealistic text-to-image starts with Z-Image-Turbo unless complexity favors Qwen

Default photorealistic generation to:

**Z-Image-Turbo**

especially for:

- portraits;
- lifestyle photography;
- wildlife;
- environments;
- cinematic shots;
- fashion;
- simple-to-moderately complex scenes.

Prefer:

**Qwen-Image-2512**

when the request has:

- many separate objects with relationships;
- exact actions or body positioning;
- text/signage/labels;
- detailed foreground-middle-background instructions;
- complicated spatial composition;
- unusual concepts requiring semantic reasoning;
- many simultaneous constraints.

If uncertain, choose Z-Turbo for aesthetic rendering and Qwen-2512 for semantic complexity.

---

## Rule 4 — First frame / last frame workflow

For first-frame/last-frame video conditioning:

### First frame
Generate with:

- **Z-Image-Turbo** for anime and most photorealistic scenes;
- **Qwen-Image-2512** for semantically complex scenes or text-heavy scenes.

### Last frame
Do **not** independently regenerate the last frame from text.

Instead:

**Frame 1 → Qwen-Image-Edit-2511 → Frame N**

The last-frame prompt must explicitly preserve everything that should remain continuous.

---

# Workflow Input Contracts

All three models expose their generation logic as ComfyUI subgraph nodes. COMBO fields (unet/clip/vae/lora) auto-resolve from disk — never type a model filename into a COMBO widget manually; always use the default or select from the dropdown.

## Qwen Image 2512 — Text-to-Image

| Input Field | Type | Role |
|---|---|---|
| `text` (+ prompt) | STRING/positive_prompt | Positive generation prompt (natural prose). Feed your planned positive text here. |
| width/height | INT | Output dimensions. Keep multiples of 64 for clean latent grids. Typical: `1024x1024` square, `1280x720` landscape 16:9, `720x1280` portrait 9:16. |
| unet_name | COMBO (auto) | Defaults to `qwen_image_2512_fp8_e4m3fn.safetensors`. Do not override. |
| clip_name | COMBO (auto) | `qwen_2.5_vl_7b_fp8_scaled.safetensors`. Do not override. |
| vae_name | COMBO (auto) | `qwen_image_vae.safetensors`. Do not override. |
| lora_name | COMBO (auto) | `Qwen-Image-2512-Lightning-4steps-V1.0-fp32.safetensors` (4-step). Do not override. |
| enable_turbo_mode | BOOLEAN | Toggle 4-step Lightning LoRA. Default true — keep it on for speed; turn off only when testing with the full model. |

**Negative prompt note:** Qwen-2512 does offer a separate negative prompt widget (wired via `prompt_1` proxy). For best results keep it: empty/unset for most uses; or use targeted failure-mode strings from the main skill (see "Qwen-2512 negative prompt" section) when the result shows specific flaws.

## Qwen Image Edit 2511 — Image-to-Image / Reference Edit

| Input Field | Type | Role / Default |
|---|---|---|
| `image` (master/image1) | IMAGE | Master/base scene (geometry/identity/composition). LoadImage default: `leather_sofa.png`. |
| `image2` | IMAGE (optional) | Property transfer target only. Assign it a specific role in the prompt: e.g., "Image 2 is ONLY a material reference for skin." Qwen-Edit will NOT copy its shape/pose from this input — only the specified property. Defaults to no link. |
| `image3` | IMAGE (optional) | Same contract as image2. Use when you need two independent transfers (e.g., face from image2, material from image3). Specify each role in the prompt so the system knows what to copy. Default: no link. |
| `prompt` (positive_prompt) | STRING | Positive edit prompt. Must clearly separate PRESERVE from CHANGE (see main skill sections 610-885). |
| `prompt_1` (negative_prompt) | STRING | Targeted negative only — e.g., "waxy skin" when the result looks over-smoothed. Keep it short and task-specific. |
| unet_name/clip_name/vae_name/lora | COMBO (auto) | Auto-resolve to `qwen_image_edit_2511_bf16` (or fp8mixed) / qwen_2.5_vl_7b_fp8_scaled / qwen_image_vae / Qwen-Image-Edit-2511-Lightning-4steps-v1.0-bf16. Do not override. |
| `seed` | INT | Reproducibility seed. Set explicitly when you need reproducibility; leave unset for random each run. |
| enable_turbo_mode | BOOLEAN | Toggle Lightning LoRA for 4-step editing (same speed benefits as Qwen-2512). Default true. |

**Save output prefix defaults to `Qwen_Edit_2511`.**

### Multi-reference practical rules
When feeding image2+image3:
- **Common pattern**: image1=base pose/identity, image2=some property (face/clothing), image3=another property (material). Always assign each one a job in the prompt.
- Say: *"Image 2 defines [texture/material]. Image 3 defines [identity/facial features]."*. **Never** just "combine these images."

## Z-Turbo (Z-Image-Turbo) Model Storage Locations

| Component | Filename | Path |
|---|---|---|
| Diffusion model | `z_image_turbo_bf16.safetensors` | ComfyUI/models/diffusion_models/ |
| Text encoder | `qwen_3_4b.safetensors` | ComfyUI/models/text_encoders/ |
| VAE | `ae.safetensors` | ComfyUI/models/vae/ |

All three are lightweight and fast for generating first frames.

---

# Fast Decision Tree

```text
Does the user provide an existing/reference image?
|
+-- YES --> Is the user asking to modify/combine/preserve it?
|            |
|            +-- YES --> QWEN-IMAGE-EDIT-2511
|            |
|            +-- NO --> Treat it as a reference task; usually QWEN-IMAGE-EDIT-2511
|
+-- NO --> Text-to-image
             |
             +-- Anime / hand-drawn 2D?
             |      |
             |      +-- YES --> Z-IMAGE-TURBO
             |
             +-- Photorealistic?
             |      |
             |      +-- Simple/moderate scene --> Z-IMAGE-TURBO
             |      |
             |      +-- Complex semantics/text --> QWEN-IMAGE-2512
             |
             +-- Text/signage/layout critical --> QWEN-IMAGE-2512
             |
             +-- General illustration --> Z-IMAGE-TURBO first,
                                          QWEN-IMAGE-2512 if semantics fail
```

---

# Universal Prompt Planning

Before writing any prompt, internally extract these fields:

1. **Subject**
   - who or what is shown;
   - age/species/object type where relevant;
   - defining appearance.

2. **Action**
   - exactly what the subject is doing;
   - posture, gesture, direction of motion;
   - object interactions.

3. **Environment**
   - location;
   - background;
   - weather;
   - time of day;
   - important props.

4. **Composition**
   - close-up / medium / full body / wide;
   - camera height;
   - angle;
   - subject placement;
   - foreground / middle ground / background;
   - aspect-ratio implications.

5. **Lighting**
   - natural/studio/practical;
   - direction;
   - softness;
   - time-of-day color;
   - contrast.

6. **Rendering / medium**
   - photograph;
   - documentary photo;
   - anime cel frame;
   - watercolor;
   - graphic illustration;
   - product render;
   - etc.

7. **Surface and material detail**
   - skin;
   - fur;
   - fabric;
   - metal;
   - glass;
   - foliage;
   - water;
   - environmental wear.

8. **Hard constraints**
   - number of subjects;
   - exact text;
   - colors;
   - left/right relationships;
   - items that must be retained.

9. **Things that must NOT drift**
   - mainly relevant to Qwen-Image-Edit.

Do not mechanically include every category. Include only details that affect the requested result.

---

# Z-Image-Turbo Prompting

## Model role

Use Z-Image-Turbo primarily as a **text-to-image generator**.

Best default uses in this system:

- anime;
- cinematic 2D animation frames;
- photorealistic people;
- wildlife;
- landscapes;
- fashion/lifestyle;
- fast visual ideation.

Z-Image-Turbo is a distilled few-step model. Do not design prompts around a traditional separate negative-prompt pipeline.

## Critical rule: do not depend on a negative prompt

For Z-Image-Turbo:

- place desired qualities in the **main positive prompt**;
- state exclusions as natural-language constraints inside that same prompt only when needed;
- do not create a separate `negative_prompt` field as part of the normal Z-Turbo prompt contract.

Bad approach:

```text
Positive: anime girl on rooftop
Negative: CGI, plastic, bad hands, 3D, blurry...
```

Preferred approach:

```text
A hand-drawn 2D anime film frame ... restrained cel shading,
flat painted skin tones, natural line variation, traditionally
painted background. The image should remain unmistakably 2D,
without a glossy 3D-rendered or figurine-like finish.
```

---

## Z-Turbo prompt order

Prefer this order:

```text
[Medium/style]
[Subject + defining traits]
[Action]
[Environment]
[Composition/camera]
[Lighting/color]
[Important materials/details]
[Final rendering constraint]
```

Write fluent descriptive prose rather than keyword soup.

---

## Z-Turbo photorealistic template

```text
An authentic [documentary/editorial/cinematic/lifestyle] photograph of
[SUBJECT].

[SUBJECT DESCRIPTION AND ACTION].

The scene takes place in [ENVIRONMENT], with [IMPORTANT BACKGROUND DETAILS].
[COMPOSITION], photographed from [CAMERA ANGLE/HEIGHT] with the visual
perspective of a [LENS IF USEFUL].

Lighting comes from [LIGHT SOURCE/DIRECTION], producing [SHADOW/HIGHLIGHT
BEHAVIOR]. Preserve real physical materials: [SKIN/FUR/FABRIC/METAL/GLASS
DETAILS]. Surfaces are naturally imperfect, with believable variation,
microtexture, environmental wear, and non-uniform reflectance.

The result should resemble an unretouched real photograph with natural
optical softness and believable photographic detail rather than a polished
CGI render.
```

### Realism vocabulary

When realism matters, describe physical phenomena instead of saying only "realistic":

- skin pores;
- fine wrinkles;
- uneven pigmentation;
- peach fuzz;
- flyaway hairs;
- irregular hair density;
- fabric weave;
- creases and tension in fabric;
- scuffed paint;
- fingerprints on glass;
- oxidized metal;
- dust;
- dirt accumulation;
- subtle scratches;
- wet surfaces;
- matte versus specular reflectance;
- atmospheric haze;
- imperfect focus falloff;
- natural motion blur;
- optical softness.

Do not overload the prompt with all of these. Pick what belongs to the scene.

---

# Z-Turbo Anime Prompting

## Default anime target

Prefer **authentic 2D animation-frame language** instead of generic "beautiful anime art."

Good phrases:

- hand-drawn 2D anime film frame;
- traditional cel-animation aesthetic;
- clean confident linework;
- varied line weight;
- restrained cel shading;
- flat painted skin tones;
- hand-painted background;
- selective soft gradients only where physically appropriate;
- expressive simplified facial design;
- strong silhouette;
- animation-ready character proportions;
- atmospheric perspective;
- frame from a professionally animated theatrical sequence.

Avoid overusing:

- masterpiece;
- ultra-detailed;
- 8K;
- hyperreal;
- ultra-glossy;
- perfect skin;
- Unreal Engine;
- Octane render.

These can push anime toward polished AI illustration or 3D-anime rendering.

---

## Z-Turbo anime template

```text
A hand-drawn 2D Japanese anime film frame.

[CHARACTER], with [KEY CHARACTER FEATURES], is [ACTION].
[EXPRESSION / BODY LANGUAGE].

The scene takes place in [ENVIRONMENT]. Include [IMPORTANT BACKGROUND
ELEMENTS] while keeping the composition readable for animation.

[SHOT TYPE] from [CAMERA ANGLE], with [CHARACTER PLACEMENT / DEPTH].
[LIGHTING] creates [COLOR/SHADOW EFFECT].

Authentic 2D animation rendering: clean confident linework, varied line
weight, restrained cel shading, flat painted skin tones, carefully simplified
facial features, natural fabric folds, individual intentional hair shapes,
and a hand-painted background with atmospheric depth.

It should look like a frame from a professionally hand-drawn anime
production, retaining a genuinely 2D visual language rather than a glossy
3D/CGI or figurine-like finish.
```

---

## Z-Turbo anime action template

```text
Hand-drawn 2D anime action-film frame.

[CHARACTER] is [EXACT ACTION], captured at [MOMENT IN MOTION].
Describe limb placement, body lean, direction of travel, weapon/tool
orientation, hair movement, and clothing movement only as needed.

[ENVIRONMENT AND PURSUING/INTERACTING ELEMENTS].

Dynamic but readable composition, [CAMERA ANGLE], [LENS-LIKE PERSPECTIVE
IF USEFUL], strong foreground-middle-background depth.

Premium traditional anime visual language: expressive hand-drawn linework,
crisp cel shading, controlled highlights, painterly background, believable
motion, clear silhouette, and restrained detail that remains animation-like
rather than turning into a polished digital poster.
```

---

# Qwen-Image-2512 Prompting

## Model role

Use Qwen-Image-2512 for **text-to-image**, especially when:

- instruction adherence is important;
- multiple scene elements must coexist;
- body pose or action is specific;
- background details matter;
- text inside the image matters;
- composition is semantically complicated;
- natural-language reasoning matters more than maximum speed.

It is also a general fallback when Z-Turbo produces attractive imagery but misses important instructions.

---

## Qwen-2512 prompt structure

Qwen-2512 can handle longer explicit descriptions. Use well-structured prose.

Preferred order:

```text
1. Subject
2. Exact action/posture
3. Environment
4. Object relationships
5. Composition/camera
6. Lighting
7. Surface/material detail
8. Rendering target
9. Explicit constraints
```

For complicated scenes, use short paragraphs rather than one enormous sentence.

---

## Qwen-2512 photorealistic template

```text
Create an authentic unretouched photograph of [SUBJECT].

SUBJECT:
[APPEARANCE, CLOTHING, DEFINING FEATURES].

ACTION:
[EXACT POSE, GESTURE, DIRECTION, OBJECT INTERACTION].

ENVIRONMENT:
[LOCATION AND IMPORTANT BACKGROUND ELEMENTS].

COMPOSITION:
[SHOT SIZE], [CAMERA HEIGHT/ANGLE], [SUBJECT POSITION].
Clearly preserve these spatial relationships:
- [A] is to the left/right/in front of/behind [B].
- [OBJECT] is held in [HAND].
- [COUNT OR LOCATION CONSTRAINT].

LIGHTING:
[LIGHTING DESCRIPTION].

PHYSICAL DETAIL:
Describe only relevant real-world microtexture: [SKIN/FUR/FABRIC/OBJECT
MATERIAL]. Keep naturally irregular surface variation, believable
reflectance, subtle imperfections, and optical softness.

The finished image should resemble a real photograph rather than a
beauty-retouched, waxy, plastic, or CGI-rendered image.
```

---

## Qwen-2512 negative prompt

Unlike Z-Turbo, Qwen-Image-2512 workflows can use a negative prompt.

Keep it targeted. Do not dump hundreds of generic terms.

### Photorealistic negative example

```text
waxy skin, plastic skin, glossy synthetic surfaces, excessive smoothing,
beauty-retouched skin, CGI appearance, 3D-rendered look, oversaturated
colors, malformed hands, extra fingers, duplicated limbs, distorted anatomy,
unreadable text
```

Only include failure modes relevant to the task.

---

## Qwen-2512 text-in-image prompting

When text must appear inside the image:

1. quote the exact text;
2. specify location;
3. specify hierarchy;
4. specify font character/style rather than assuming a font file;
5. distinguish text from decorative imagery;
6. keep the number of text elements manageable.

Template:

```text
Create [SCENE/DESIGN].

The image must contain the following exact readable text:

Headline: "EXACT HEADLINE"
Location: top center
Style: bold geometric sans-serif, large, high contrast

Secondary text: "EXACT SECONDARY TEXT"
Location: lower left
Style: smaller clean sans-serif

Do not paraphrase, translate, add, or omit any characters.

[REST OF VISUAL DESCRIPTION]
```

---

# Qwen-2512 Anime

Z-Turbo is the default anime generator in this system.

When Qwen-2512 is required for anime, fight its tendency toward highly polished digital illustration by strongly specifying animation-frame rendering.

Template:

```text
A genuine hand-drawn 2D Japanese anime animation frame, not a standalone
digital poster.

[SUBJECT + ACTION + ENVIRONMENT + COMPOSITION].

Use simplified animation-ready forms, clean variable linework, restrained
flat cel shading, limited highlight treatment, flat painted skin tones,
purposeful hair shapes, and a traditionally painted background.

Preserve the visual economy of an actual animated frame. Do not over-render
the face, skin, hair, clothing, or background. Avoid glossy gradients,
figurine-like surfaces, and a polished 3D-anime appearance.
```

Suggested negative prompt:

```text
3D anime, CGI, figurine, glossy skin, plastic surface, hyper-detailed digital
poster, excessive gradients, beauty-rendered face, waxy skin, oversharpened
line art
```

---

# Qwen-Image-Edit-2511 Prompting

## Model role

Qwen-Image-Edit-2511 is the **preservation-and-change engine**.

Its job is not merely to make a new image "inspired by" the source.

The prompt should clearly divide:

1. what must remain unchanged;
2. what must change;
3. how the changed area should look;
4. which reference image controls which property.

---

# The Preservation / Change Pattern

For most edits, use this structure:

```text
Preserve:
[LIST WHAT MUST NOT CHANGE].

Change only:
[EXACT EDIT].

Result:
[HOW THE EDIT SHOULD PHYSICALLY / STYLISTICALLY APPEAR].

Do not alter:
[HIGH-RISK FEATURES THAT OFTEN DRIFT].
```

Example:

```text
Preserve the exact person, facial identity, hairstyle, clothing, body
proportions, room architecture, lighting direction, camera position, lens
perspective, and overall color palette.

Change only the action: she is now standing beside the machine and inserting
the glass vial into the illuminated slot with her right hand.

Maintain the same scene continuity and photographic rendering.

Do not redesign the person, clothes, machine, room, background objects, or
camera.
```

---

# First Frame → Last Frame Template

```text
This image is FRAME 1 of a continuous shot.

Create a plausible later frame from the SAME shot.

PRESERVE EXACTLY:
- subject identity and facial structure;
- hairstyle and clothing;
- body proportions;
- environment and architecture;
- object designs;
- lighting direction and time of day;
- overall rendering style;
- color palette;
- camera/lens characteristics unless a camera movement is explicitly requested.

CHANGE:
[DESCRIBE THE LATER ACTION OR STATE].

CAMERA:
[NO CAMERA CHANGE / SLOW DOLLY FORWARD / PAN / ORBIT / ETC.].
If camera movement is specified, keep the environment geometrically coherent.

CONTINUITY:
The result must look like a later frame from the same continuous video shot,
not a newly redesigned scene.

Do not introduce new clothing, props, architecture, characters, weather, or
lighting unless explicitly requested.
```

---

# Anime First Frame → Last Frame with Qwen Edit

When editing a Z-Turbo anime frame:

```text
Preserve the exact same character design, facial design, hairstyle,
clothing, line art language, line thickness variation, cel-shading style,
flat painted skin tones, color palette, background painting style, and
2D anime production aesthetic.

Change only:
[NEW ACTION / POSE / EXPRESSION].

Maintain the same environment and scene continuity. The result must look
like a later hand-drawn frame from the exact same anime sequence.

Do not beautify, re-render, add glossy gradients, increase realism, convert
the image into a digital poster, or introduce 3D/CGI characteristics.
```

If Qwen begins to make the anime frame too smooth, emphasize:

- flat cel shading;
- restrained highlights;
- limited gradients;
- animation-ready forms;
- same line-art character;
- same background painting technique.

---

# Anti-Plastic Realism Editing with Qwen-2511

Do not use only:

```text
make it realistic
```

or:

```text
keep it natural and not plastic
```

These are too abstract.

Instead describe the physical surface properties that are missing.

## Realism edit template

```text
Preserve the exact subject anatomy, proportions, pose, silhouette, facial
structure, object shapes, composition, camera angle, environment, and
lighting.

Change only the physical surface rendering so the image resembles an
authentic unretouched photograph.

Restore biologically and physically irregular detail where appropriate:
[SELECT RELEVANT ITEMS: pores, fine wrinkles, skin folds, uneven
pigmentation, fine scars, dust, coarse individual hairs, flyaway hairs,
uneven fur density, fabric weave, scratches, fingerprints, weathering,
non-uniform roughness].

Use natural material-dependent reflectance and subtle optical softness.
Textures must vary organically rather than repeating uniformly.

Do not redesign the subject or change the scene. Avoid waxy, airbrushed,
vinyl-like, uniformly smooth, glossy synthetic, or CGI-style surfaces.
```

---

# Multi-Reference Editing with Qwen-2511

When several reference images are supplied, assign each one a job.

Never say merely:

```text
combine these images
```

Use:

```text
IMAGE 1 defines:
- geometry;
- pose;
- composition;
- primary subject identity.

IMAGE 2 defines ONLY:
- [texture/material/face/clothing/etc.].

IMAGE 3 defines ONLY:
- [another property].

Preserve Image 1's composition and geometry.
Transfer only the specified properties from Images 2 and 3.
Do not copy unrelated background, camera, lighting, pose, or objects from
the reference images.
```

---

# Material / Texture Reference Template

```text
Image 1 is the master image and defines all geometry, anatomy, pose,
composition, camera, and scene layout.

Image 2 is ONLY a physical material reference for [SKIN/FUR/FABRIC/METAL].

Transfer the real physical material characteristics from Image 2 onto the
corresponding surface in Image 1:
[RELEVANT TEXTURE DETAILS].

Do not transfer Image 2's shape, pose, background, lighting, camera, or
identity. Preserve Image 1 in every other respect.
```

---

# Character Identity Preservation

When the same character must survive an edit, explicitly preserve:

- face shape;
- eyes;
- nose;
- mouth;
- age;
- skin tone;
- hairline;
- hairstyle;
- hair length;
- clothing;
- accessories;
- body proportions;
- defining marks.

Do not list features that are irrelevant or invisible.

Template:

```text
Treat the person in Image 1 as the canonical identity reference.
Preserve their identity exactly: [VISIBLE DEFINING FEATURES].
The person must remain recognizably the same individual after the edit.

Change only [EDIT].
```

---

# Object/Product Preservation

For products, machines, vehicles, architecture, props, or fictional objects:

```text
Preserve the product's exact silhouette, dimensions, component placement,
surface seams, controls, openings, logos, color blocks, and perspective.

Change only [MATERIAL / CONTEXT / ACTION / BACKGROUND].

Do not redesign the object or invent new components.
```

---

# Text Editing with Qwen-2511

When changing text already present in an image:

```text
Preserve the entire image, layout, typography style, text size, alignment,
color, perspective, shadows, material interaction, and background.

Replace ONLY the text:
"OLD TEXT"
with exactly:
"NEW TEXT"

Do not change any other visual element.
```

If several text regions exist, identify each by position.

---

# Prompt Specificity Rules

## Prefer concrete visual language

Weak:

```text
make it cinematic
```

Better:

```text
low camera at waist height, 35mm perspective, warm side light from the
setting sun, cool ambient fill from the sky, shallow atmospheric haze
between subject and distant buildings
```

Weak:

```text
make the fur realistic
```

Better:

```text
coarse individual guard hairs, uneven strand direction, clumped areas,
flyaway hairs along the silhouette, subtle dust caught between hairs, matte
natural fur response rather than uniform glossy strands
```

Weak:

```text
keep everything the same
```

Better:

```text
preserve the exact facial identity, hairstyle, clothing, architecture,
camera position, lens perspective, lighting direction, object placement,
and color palette
```

---

# Do Not Overprompt

More words are not automatically better.

Stop adding details once:

- the subject is unambiguous;
- action is clear;
- required spatial relationships are clear;
- composition is defined enough;
- style is defined;
- high-risk failure points are constrained.

Overprompting can cause:

- competing instructions;
- unintended object duplication;
- excessive detail;
- poster-like anime;
- overprocessed photorealism;
- loss of edit preservation.

---

# Prompt Repair Strategy

When a generation fails, do not blindly append more adjectives.

Diagnose the failure.

## Wrong composition
Strengthen:

- shot size;
- camera angle;
- left/right;
- foreground/background;
- exact position.

## Wrong action
Describe:

- limb placement;
- hand-object interaction;
- direction;
- body lean;
- gaze.

## Plastic realism
Replace abstract quality words with:

- physical microtexture;
- irregularities;
- material reflectance;
- environmental wear;
- optical softness.

## Anime became 3D
Strengthen:

- hand-drawn 2D frame;
- flat cel shading;
- limited gradients;
- animation-ready forms;
- painted background;
- restrained highlights.

Reduce:

- ultra-detailed;
- 8K;
- hyperreal;
- cinematic render;
- volumetric everything;
- glossy;
- perfect.

## Qwen edit drifted
Move preservation requirements to the beginning and explicitly say:

```text
Change ONLY...
Do not alter...
```

Remove unnecessary creative language.

## Z-Turbo missed complex semantics
Do not endlessly expand the Z-Turbo prompt.

Route the task to **Qwen-Image-2512** if semantic complexity is the main problem.

---

# First/Last Frame Design Rules for Video

A good last frame is not simply a prettier second image.

For interpolated/generated video, maintain continuity in:

- identity;
- clothing;
- environment;
- illumination;
- object design;
- scene topology;
- focal length character;
- overall art style.

Prefer one meaningful state change per shot.

Good:

```text
Frame 1: woman holds vial beside machine.
Frame N: same woman inserts vial into machine.
```

Riskier:

```text
Frame 1: woman outside laboratory.
Frame N: woman inside spacecraft, different camera, different clothes,
explosion outside, night lighting.
```

If the requested change is too large, recommend splitting it into multiple shots rather than forcing one first/last-frame pair.

---

# Model-Specific Output Contract

When the user asks Hermes to create a prompt but not to execute generation, return:

```text
MODEL: <Z-Image-Turbo | Qwen-Image-2512 | Qwen-Image-Edit-2511>

PROMPT:
<final model-specific prompt>

NEGATIVE PROMPT:
<only when useful for Qwen-Image-2512; otherwise NONE>

INPUT IMAGE ROLES:
<only for Qwen-Image-Edit-2511 with one or more images; otherwise NONE>

WHY THIS MODEL:
<one short sentence>
```

Do not include a long explanation unless the user asks.

If the generation system/tool accepts structured fields directly, pass the same information to it rather than merely printing it.

---

# Automatic Routing Examples

## Request
"Generate a hand-drawn anime girl walking home in rain."

Route:

```text
Z-Image-Turbo
```

Reason: anime T2I.

## Request
"Generate a realistic woman at a café at golden hour."

Route:

```text
Z-Image-Turbo
```

Reason: straightforward photorealistic T2I.

## Request
"Four scientists around a table. The woman on the left holds a red vial.
The man behind her points at a monitor saying PHASE III."

Route:

```text
Qwen-Image-2512
```

Reason: complex object/person relationships and exact text.

## Request
"Take this image and make the same woman insert the vial into the machine."

Route:

```text
Qwen-Image-Edit-2511
```

Reason: source-image-preserving semantic edit.

## Request
"Use this Z-Turbo anime frame and make a later frame where she turns toward
the door."

Route:

```text
Qwen-Image-Edit-2511
```

Use the anime preservation template.

## Request
"This edited animal looks plastic. Keep the exact creature but make the hide
and fur physically believable."

Route:

```text
Qwen-Image-Edit-2511
```

Use the anti-plastic physical-surface template.

---

# Quality Checklist Before Sending a Prompt

Before finalizing, verify:

- [ ] Correct model selected.
- [ ] Existing images are routed to Qwen-Image-Edit-2511.
- [ ] Anime T2I defaults to Z-Image-Turbo.
- [ ] Z-Turbo does not rely on a separate negative prompt.
- [ ] Complex semantic/text-heavy T2I can route to Qwen-Image-2512.
- [ ] Qwen edit clearly separates PRESERVE from CHANGE.
- [ ] First-to-last-frame edits explicitly enforce continuity.
- [ ] "Realism" is described through physical details, not just adjectives.
- [ ] Anime prompts specify actual 2D animation properties.
- [ ] Prompt is not bloated with contradictory style terms.
- [ ] Exact text is quoted when text rendering matters.
- [ ] Left/right/count/object relationships are explicit when important.
- [ ] No model is asked to perform a role it does not support in this system.

---

# Preferred System Summary

Use this mental model:

```text
Z-IMAGE-TURBO
= generate visually strong first frames
= default anime
= default simple/moderate photorealism
= fast T2I

QWEN-IMAGE-2512
= generate semantically difficult first frames
= detailed natural-language composition
= text/signage
= complex T2I fallback

QWEN-IMAGE-EDIT-2511
= preserve + change
= identity consistency
= first frame -> last frame
= image/reference fusion
= material replacement
= text editing
```

The default production pipeline is:

```text
TEXT
 |
 +--> anime ----------------------> Z-Image-Turbo
 |
 +--> photorealistic ------------> Z-Image-Turbo
 |       |
 |       +-- complex semantics --> Qwen-Image-2512
 |
 +--> text-heavy/complex T2I ----> Qwen-Image-2512

FIRST FRAME
 |
 +--> required later-frame edit -> Qwen-Image-Edit-2511
```

---

# Maintenance Notes

This skill is intentionally specific to the three-model local image system.
Do not silently replace these models with newly released models.

If model behavior changes after a checkpoint, ComfyUI, or workflow update:

1. keep the routing philosophy;
2. re-test the same benchmark prompts;
3. update only the affected model section;
4. record the behavior change in this skill's version.

Current assumptions were reviewed against official model/ComfyUI information available in August 2026:

- Z-Image-Turbo is a distilled text-to-image model optimized for few-step generation; its official prompting guidance notes that it does not use traditional classifier-free-guidance negative prompts.
- Qwen-Image-2512 is a text-to-image model with improved human realism, natural detail, text rendering, and a standard 50-step workflow.
- Qwen-Image-Edit-2511 is an editing model with improved character consistency, reduced drift, multi-person editing, material replacement, and stronger geometric reasoning.
