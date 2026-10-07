# Narrative styles, production-type Director profiles and prompt governance

This is part of the production upgrade, not a separate media model. Story style shapes text, dialogue, scene structure and Director judgment; visual treatment shapes image/H3 prompts. Keep them separate so a PDF about writing style cannot silently replace a character image, and a reference film cannot silently become the story's plot.

## Current contract and compatibility

`services/prompt_styles.py` reads `prompts/styles/*.json`; every pack has `style_id`, `name`, `version`, and six required stage strings: `story`, `scene_direction`, `image`, `audio`, `video`, `review`. Preserve the existing IDs and behavior for `story_film`, `social_profile`, `corporate_pitch`, `informative`, `news_report`, `advertisement`. `/api/automation/styles` and current flat picker consumers must continue to receive a compatibility form until updated. Do not rewrite or repurpose these six files destructively.

## Two-layer style system

1. **Production type** (one of six existing bases) gives purpose, pacing, audience expectations and Director behavior rubric. A `story_film` Director can favor character arcs and continuity; a `news_report` Director must distinguish reported fact from dramatic invention; an `advertisement` Director checks product/claim constraints. Write a distinct versioned Director profile for every base, not one generic director prompt with a different label.
2. **Narrative style variant** optionally refines the chosen base: structure, voice, dialogue length, scene rhythm, tone, point of view and constraints. It may inherit/override explicitly declared profile fields. Resolve the complete effective profile at run start and snapshot its version; do not mutate a running project when someone publishes a new variant.

Visual treatment (anime, photorealistic, graphic novel, etc.), character/world art, action-video references and voice timbre remain separate selectable inputs. A style variant can say “favor sparse dialogue and slow reveals,” but cannot create an unapproved Video Repertoire reference or claim a generated character's face is fixed without visual evidence.

## Style source ingestion

Allow only `.pdf`, `.md`, `.txt` into the narrative Style Library. Extract text with file hash plus PDF page or Markdown/text line offsets. Generate **evidence cards** (“rule,” “source quotation or short paraphrase,” page/line, confidence, inferred-vs-explicit flag), then a structured draft style profile, sample story/shot brief and Director review rubric. Avoid copying large verbatim passages, the source's plot, characters or dialogue into unrelated work. A style draft is not active until published; published versions remain immutable and auditable. Invalid/corrupt/empty/upload-too-large sources produce clear errors. Video and image uploads belong to the visual/reference asset flow, not this narrative ingestion route.

Suggested style data fields: `base_style_id`, `variant_id`, `version`, `display_name`, `source_ids`, `rules_by_stage`, `director_behavior_overrides`, `evidence`, `negative_constraints`, `example_brief`, `status=draft|published|archived`, `created_at`, `parent_version`. Explicitly validate override conflicts, required stage coverage, duplicate IDs and unsupported production-type inheritance. A provider-generated recommendation has `confidence` and evidence; user-authored rules are marked as such rather than fabricated citations.

## UI and routing

One shared `ProductionStylePicker` replaces the duplicated flat selector *after* regression tests. First level shows six production types; variants are a flyout/submenu or mobile drawer with a chevron. Users can choose a base default or a named published variant. Show a breadcrumb/label such as `Story & film / Quiet suspense · v2`. Keyboard arrow/Enter/Escape, mouse hover/click, touch, focus and screen-reader semantics are tested. A `Manage styles` action leads to a new Style Library page with source upload, extraction progress, evidence review, draft preview, publish/archive and version history. Both Story Builder and Automation Studio must resolve the **same** effective style snapshot for an equivalent selection. The selected style does not replace the separate visual-treatment or making-route controls.

Add endpoints without breaking old ones: compatibility `GET /api/automation/styles`, a versioned tree catalog, style detail/version, source upload/analyze job, draft/save/publish/archive. Protect source files and citations under an allowlisted style-library root. Run snapshots include effective production type, variant version, Director profile version and evidence hash. Prompts at each story/shot/media stage include only the relevant resolved rules; the full PDF is not pasted into every call.

## Evaluation and safe improvement

The Director may flag that a rule harms output or propose an improved rule/prompt pack. Store a *proposal* with example failure and affected stages; compare it against fixed story/shot fixtures before promotion. Never allow the model to change a published style pack or Python source during a live run. A style change after shots exist creates a new project/run revision and an invalidation preview, not silent rewriting of accepted videos.

Tests: all six old IDs load; base-vs-variant resolution; text-source page/line evidence; source-plot leakage guard; draft/publish immutability; run snapshot unchanged after a new variant version; shared picker on Story Builder and Automation; mobile/keyboard/a11y; video rejected as narrative source; unrelated existing audio/video pages unchanged.
