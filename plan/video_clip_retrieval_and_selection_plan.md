# Video Clip Retrieval and Selection Plan

**Status:** implementation complete for the text-first release — curated indexing, scene/clip adaptation, playable media, thumbnails, deterministic local vector retrieval, filters, ranking/diversity, pagination, SEO styles, Media Composer selection and safe Hermes hand-off  
**Purpose:** turn the existing video-summariser repertoire into a searchable clip library that can be used manually in Media Composer or automatically by Hermes.

**Implementation note:** the text-first release is wired additively. It reads curated videos from `out_videos`, adapts existing summariser metadata when present, creates safe playable clips/thumbnails, stores rebuildable JSONL records, uses deterministic local vectors with an optional LanceDB mirror, applies metadata filters and diversity-aware ranking, supports non-repeating sessions and named transient SEO styles, and exposes the Media Composer and Hermes-safe APIs. LanceDB can be enabled with `VIDEO_REFERENCES_USE_LANCEDB=1` after validating the local native wheel; the JSONL/vector fallback remains the safe default. Image embeddings, Graphiti, and model-based Hermes reasoning remain intentionally later phases.

## 1. Goal

Given a natural-language description, return the top `N` relevant **video clips**, not entire videos. Each result must retain its source video, scene/sub-scene/cut identity, exact timestamps, thumbnail, playable clip, compact summary, frame cards and provenance.

Example query:

> Fast two-person sword fight, overhead parry, side-tracking camera, dark blue lighting, energetic rhythm.

Expected results:

```text
clip_023 — 0:12.4–0:16.6 — 87% match — 4.2s
clip_107 — 1:04.1–1:10.9 — 82% match — 6.8s
clip_051 — 0:42.0–0:45.5 — 78% match — 3.5s
```

The system must explain why each clip matched and allow the user or Hermes to select one.

## 2. Source-of-truth and storage

The initial corpus is a deliberately curated collection: only the specific videos the user places in the video-summariser folder are indexed:

```text
/home/riki/web_dev/story_builder/video_summariser/out_videos
```

Do not scan or automatically index the entire Video Repertoire. A manifest/allow-list records which files in `out_videos` are approved for indexing. Videos imported through the existing Video Repertoire API can be added later only through an explicit user action. Do not move, rename or delete source videos.

Generated/indexed data belongs in additive locations:

```text
video_summariser/
  index/
    clips.jsonl                 # canonical searchable records
    lancedb/                    # persistent LanceDB tables
    search_sessions/            # short-lived refinement/session records
    manifest.json
  clips/<asset_id>/<analysis_id>/
    scene_*.mp4                 # existing/generated playable clips
    thumbnails/
  analyses/<analysis_id>/       # existing reports and frame artifacts
```

Approved clips are reusable across projects. The shared clip media and index remain in `video_summariser`; project-specific selections belong under the existing project storage, for example:

```text
storage/projects/<project_id>/references/video_clips/
```

Store a reference to the original clip and never duplicate large media unless an export explicitly requires it. Search results are transient UI data and must not be copied into or accumulate in the UI.

## 3. Canonical clip record

Create a versioned record for every searchable unit:

```json
{
  "clip_id": "video-abc_scene_003_cut_002",
  "asset_id": "video-abc",
  "source_video": ".../out_videos/source.mp4",
  "scene_id": "scene_003",
  "subscene_id": "scene_003_action_01",
  "cut_id": "cut_002",
  "start_time_sec": 12.4,
  "end_time_sec": 16.6,
  "duration_sec": 4.2,
  "clip_path": "clips/video-abc/analysis-123/scene_003.mp4",
  "thumbnail_path": "clips/video-abc/analysis-123/thumbnails/scene_003.jpg",
  "summary": "Two fighters exchange a fast overhead parry in a dark blue room.",
  "action_beats": ["approach", "overhead strike", "parry", "recovery"],
  "subjects": ["fighter_a", "fighter_b"],
  "camera": {"shot_size": "medium-wide", "angle": "three-quarter", "movement": "side tracking"},
  "lighting": {"description": "cool blue side light", "palette": ["#172b52"]},
  "reusable_properties": ["parry timing", "camera movement", "lighting rhythm"],
  "replaceable_properties": ["characters", "costumes", "background"],
  "frame_cards": ["...linked frame-card ids..."],
  "transcript": "",
  "audio_events": [],
  "provenance": {"source_url": "", "notes": "", "license_status": "unknown"},
  "embedding_versions": {"text": "", "image": ""}
}
```

Scene, sub-scene and cut are distinct levels. The UI allows exactly one active sort level at a time:

- **Scene:** broader cut-defined scene; fewer, longer results.
- **Sub-scene:** semantically different action part within a scene.
- **Clip/cut:** individual cut; most precise and potentially many results.

## 4. Indexing pipeline

### 4.1 Corpus discovery

Add an idempotent indexing job that scans only the approved `out_videos` manifest, hashes files, and indexes only new/changed assets. Never index every downloaded repertoire asset by default.

### 4.2 Summariser integration

Reuse the existing video-summariser analysis outputs instead of re-running analysis unnecessarily:

1. Read scene manifests, timestamps, transcripts, frame analyses, frame deltas and generated clips.
2. Create thumbnails from the first frame of each searchable clip.
3. Create sub-scenes from semantic action changes, not arbitrary fixed windows. Use frame deltas, transcript boundaries and motion changes; fall back to the scene when evidence is insufficient.
4. Keep exact source timestamps and links to the playable clip.
5. Generate a compact clip summary and frame cards. Raw analysis remains in artifacts.

### 4.3 Embeddings

Use text retrieval in the first release:

- Text embeddings for summaries, action beats, camera, lighting and tags.
- Keep image/frame fields in the schema, but defer image embeddings and image-query search to a later upgrade.
- Optional audio embeddings later; never pretend audio similarity exists until measured.

The recommended and selected local index is LanceDB under `video_summariser/index/lancedb/`, with JSONL manifests as the rebuildable source of truth. Do not introduce Graphiti as the primary nearest-neighbour store.

## 5. Retrieval and ranking

1. Accept a query text, `top_n`, sort level and filters. Reserve an optional image field for the later visual-search release.
2. Retrieve a larger candidate pool (for example `max(20, top_n × 4)`) using text similarity.
3. Apply metadata filters: scene/sub-scene/cut level, duration range, source/license, subjects, camera, lighting and project restrictions.
4. Rerank candidates using a cross-encoder or Qwen scoring pass over the query and compact clip records.
5. Apply diversity/MMR so five results are not five nearly identical frames from the same moment.
6. Return match score, score explanation, clip metadata, thumbnail, playable URL and source provenance.

`top_n` is user-configurable with a safe maximum. The default should be 5. A search receives a stable `search_id`; “Next top N” uses a cursor or exclusion set so clips already shown in that search can never be repeated.

### 5.1 Optional weighted semantic refinement (the “SEO” control)

Interpret the requested SEO step as optional weighted semantic refinement, not permanent search-engine metadata. The search UI provides:

- **SEO off / No SEO:** use the normal query and ranking.
- **SEO on:** apply the selected named style’s temporary weights and terms.
- **Create SEO style:** name a style and configure preferred/avoided terms plus weights for action, camera, lighting, style, timing and subjects.
- **Choose SEO style:** switch between styles one at a time; only the active style affects the current search.

When a user manually selects a scene, sub-scene or clip, the active style may be applied to that search. In the text-first release, weights are applied to the clip summary, action beats and structured metadata; when visual search is added, the same style can also boost matching frame/image embeddings. A style is a reusable ranking configuration, not a modification to any clip. The active application remains scoped to the current search/session, can be turned off or cleared, and must not permanently bias the canonical index. Persist named style definitions separately (global or project-scoped, according to the user’s choice), while storing only compact search-session state under `video_summariser/index/search_sessions/`.

## 6. Graphiti/GraphRAG phase

Graphiti is a later relationship layer, not the first retrieval engine. After vector retrieval works, populate graph entities and edges such as:

```text
clip → contains → fighter_a
clip → uses → sword
clip → demonstrates → overhead_parry
clip → belongs_to → scene_003
clip → derived_from → source_video
```

Use the graph for continuity and relationship queries, such as finding all references involving the same entity, linking script characters to reference properties, or tracking approved references across revisions. Keep vector retrieval as the fast candidate generator.

## 7. Backend API

Add additive FastAPI endpoints:

- `POST /api/video-references/index` — discover/index new or changed videos.
- `GET /api/video-references/index/status` — report corpus/index health.
- `POST /api/video-references/search` — text query first, `top_n`, sort level, filters and optional session/cursor.
- `GET /api/video-references/search/{search_id}/next` — return the next non-overlapping page of results.
- `POST /api/video-references/search/{search_id}/refine` — apply or clear the active weighted style for the current search.
- `GET /api/video-references/seo-styles` — list named semantic-weighting styles.
- `POST /api/video-references/seo-styles` — create a named style without changing clip records.
- `PUT /api/video-references/seo-styles/{style_id}` — update a named style.
- `DELETE /api/video-references/seo-styles/{style_id}` — delete a named style.
- `GET /api/video-references/clips/{clip_id}` — full clip record and evidence.
- `GET /api/video-references/clips/{clip_id}/content` — safe playable clip.
- `GET /api/video-references/clips/{clip_id}/thumbnail` — first-frame thumbnail.
- `POST /api/projects/{project_id}/video-references/select` — save approved reference(s) to the project.
- `POST /api/video-references/automation/select` — return Hermes-ready ranked candidates and selection rationale.

The search API must support automation without a browser:

```json
{
  "query": "fast sword parry with side tracking camera",
  "top_n": 5,
  "sort_level": "subscene",
  "filters": {"max_duration_sec": 12, "subjects": ["fighter"]},
  "exclude_clip_ids": []
}
```

Responses must be deterministic for the same index/version/config and must include `search_id`, cursor/exclusion state, index version, embedding version and provenance.

## 8. Media Composer UI

Add a collapsible full-width **Video Clip Selection** section to Media Composer without disrupting existing ComfyUI workflow controls.

### Controls

- Prompt/description textarea.
- Top-N number input (default 5, bounded maximum).
- One-choice sort control: Scene, Sub-scene or Clip/Cut.
- Optional filters: duration, subjects, camera, lighting, source/license.
- Search button, clear button and loading/progress state.
- “Next top N” button that requests the next page without repeating any clip already shown in the current search.
- SEO toggle with “No SEO” as the default.
- Named SEO-style selector and “Create new style” editor for terms and dimension weights.
- Clear/remove-style action that immediately returns ranking to the normal query.

### Results

Group results by source video. Each video group becomes a Netflix-style horizontal carousel:

- First frame of each clip as thumbnail.
- Clip duration and exact timestamp.
- Match score and one-line reason.
- Play/pause preview.
- Expand to view frame cards and compact evidence.
- Select/approve reference.
- Manually refine the selected clip’s terms/weights using the active style and rerun the current search.
- Open source video at the relevant timestamp.

Multiple clips from one video remain in the same carousel. The next source video appears in the next carousel below it. Scene/sub-scene/cut sorting is mutually exclusive and visibly reflected in the result labels.

Empty, indexing, partial, offline, permission and failed-search states must be explicit. Results must not block the rest of Media Composer.

## 9. Hermes automation hand-off

Hermes receives the original query plus the top-N compact records, not full raw reports. It should score:

- action match;
- camera match;
- lighting/style match;
- timing/duration suitability;
- subject/replaceable-property compatibility;
- provenance/license constraints.

Hermes returns one of:

- selected clip id and rationale;
- a ranked shortlist requiring user approval;
- a clarification request when no candidate is safe.

The automation path must never silently choose a clip with an unknown license or unresolved identity conflict. Manual selection remains available and produces the same project reference record as automation.

## 10. Testing and safety

- Use the existing videos in `video_summariser/out_videos` and the fixtures under `plan/`.
- Unit-test manifest parsing, scene/sub-scene/cut grouping, thumbnail generation, timestamp math, idempotent indexing, filters, text scoring, reranking, diversity and deterministic `top_n` behavior.
- Test missing analysis artifacts and rebuild from source without deleting existing outputs.
- Test API validation, cancellation, retries, stale index versions and safe path handling.
- Use Playwright to test the collapsible Media Composer section, prompt entry, top-N, mutually exclusive sort, carousels, playback, selection, errors and automation preview.
- Run regression Playwright tests for Story Builder, Image Detailer, Video Summariser/Repertoire, Generate and Audio pages.
- Do not modify or delete existing project storage, video files, workflow JSON, audio paths or working APIs. All additions must be versioned and backward-compatible.

## 11. Implementation phases

1. **Curated inventory and manifest adapter:** read only approved videos in `out_videos` and produce canonical clip records.
2. **Clip thumbnails and level grouping:** scene/sub-scene/cut records with safe playable URLs.
3. **Local LanceDB text index:** text embeddings, rebuild command and index status API.
4. **Search/rerank/diversity API:** variable top-N, mutually exclusive sort level, optional named SEO styles, clear/off behavior and non-repeating pagination.
5. **Media Composer selection UI:** collapsible section, carousels, playback and approval.
6. **Hermes automation adapter:** ranked candidate decision and clarification path.
7. **Graphiti relationship layer:** only after vector retrieval is stable.
8. **Later visual-search upgrade:** image embeddings and text+image fusion.
9. **Fixture/live/Playwright regression verification:** no unrelated regressions accepted.

## 12. Gaps to resolve before implementation

- Confirm Hermes endpoint/model contract; the retrieval API should remain usable without Hermes.
- “SEO” is intentionally implemented as the transient weighted semantic refinement described in §5.1, not conventional web SEO.
