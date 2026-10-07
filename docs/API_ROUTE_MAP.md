# Story Builder route inventory

Generated from the exported source on 2026-10-07. No private project data is included.

## Frontend pages

| URL | Component |
| --- | --- |
| `/` | `Home` |
| `/story` | `StoryBuilder` |
| `/canvas` | `StoryCanvas` |
| `/media` | `MediaComposer` |
| `/generate` | `Generate` |
| `/image-detailer` | `ImageDetailer` |
| `/audio` | `AudioStudio` |
| `/audio-reconstruct` | `AudioReconstruct` |
| `/music-sound` | `MusicSound` |
| `/audio-tools` | `AudioUtilities` |
| `/automation` | `AutomationStudio` |
| `/status` | `AgentStatus` |
| `/video-repertoire` | `VideoRepertoire` |
| `/video-summariser` | `VideoRepertoire` |
| `/manual-director` | `ManualDirector` |
| `/production` | `ProductionWorkspace` |
| `/style-library` | `StyleLibrary` |
| `*` | `NotFound` |

## Backend endpoints

The running backend exposes full schemas at `/docs` and `/openapi.json`.

| Method | Path | Handler | Source line |
| --- | --- | --- | --- |
| GET | `/api/health` | `health` | 2467 |
| GET | `/api/reasoning/provider` | `get_reasoning_provider` | 2483 |
| PUT | `/api/reasoning/provider` | `update_reasoning_provider` | 2489 |
| POST | `/api/reasoning/provider/test` | `test_reasoning_provider` | 2498 |
| POST | `/api/reasoning/provider/test-director` | `test_reasoning_provider_director` | 2506 |
| GET | `/api/projects` | `list_projects` | 2548 |
| POST | `/api/projects` | `create_project` | 2553 |
| GET | `/api/projects/{project_id}` | `fetch_project` | 2564 |
| PUT | `/api/projects/{project_id}/draft` | `update_project_draft` | 2572 |
| GET | `/api/automation/projects` | `list_automation_projects` | 2587 |
| DELETE | `/api/automation/projects` | `delete_automation_projects` | 2600 |
| POST | `/api/projects/{project_id}/automation/start` | `start_story_automation` | 2620 |
| POST | `/api/projects/{project_id}/automation/input` | `upload_automation_input` | 2660 |
| GET | `/api/projects/{project_id}/automation/run` | `get_story_automation` | 2692 |
| GET | `/api/projects/{project_id}/graph` | `get_project_graph` | 2701 |
| POST | `/api/projects/{project_id}/production/start` | `start_production` | 2735 |
| GET | `/api/projects/{project_id}/production/run` | `get_production_run` | 2752 |
| POST | `/api/projects/{project_id}/automation/{action}` | `action_story_automation` | 2761 |
| GET | `/api/projects/{project_id}/status` | `project_status` | 2785 |
| POST | `/api/projects/{project_id}/artifacts/{artifact_type}/generate` | `generate_artifact` | 2793 |
| POST | `/api/projects/{project_id}/artifacts/{artifact_type}/save` | `save_artifact` | 2825 |
| POST | `/api/story/assist` | `story_assist` | 2837 |
| GET | `/api/workflows` | `workflows` | 2863 |
| GET | `/api/production/v2/workflows` | `production_v2_workflows` | 2868 |
| GET | `/api/production/v2/image-workflows` | `production_v2_image_workflows` | 2874 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/image-jobs` | `queue_production_image_job` | 2880 |
| GET | `/api/projects/{project_id}/production/v2/image-jobs/{batch_id}` | `get_production_image_job_batch` | 3025 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/image-candidates/{asset_id}/accept` | `accept_production_image_candidate_route` | 3034 |
| GET | `/api/production/v2/h3-prompt-rules` | `production_v2_h3_prompt_rules` | 3063 |
| POST | `/api/projects/{project_id}/production/v2/runs` | `create_production_v2_run` | 3074 |
| GET | `/api/projects/{project_id}/production/v2/runs` | `list_production_v2_runs` | 3162 |
| GET | `/api/production/v2/director-profiles` | `production_v2_director_profiles` | 3174 |
| GET | `/api/production/v2/styles` | `production_v2_styles` | 3182 |
| GET | `/api/production/v2/style-sources` | `list_production_v2_style_sources` | 3191 |
| POST | `/api/production/v2/style-sources` | `upload_production_v2_style_source` | 3197 |
| GET | `/api/production/v2/styles/variants` | `list_production_v2_style_variants` | 3212 |
| GET | `/api/production/v2/styles/drafts` | `list_production_v2_style_drafts` | 3221 |
| GET | `/api/production/v2/styles/{variant_id}/versions` | `list_production_v2_style_versions` | 3229 |
| POST | `/api/production/v2/styles/analyze` | `analyze_production_v2_style_sources` | 3241 |
| POST | `/api/production/v2/styles/drafts` | `create_production_v2_style_draft` | 3255 |
| PUT | `/api/production/v2/styles/drafts/{variant_id}` | `update_production_v2_style_draft` | 3264 |
| POST | `/api/production/v2/styles/drafts/{variant_id}/publish` | `publish_production_v2_style_draft` | 3278 |
| POST | `/api/production/v2/styles/{variant_id}/fork` | `fork_production_v2_style_variant` | 3289 |
| POST | `/api/production/v2/styles/{variant_id}/archive` | `archive_production_v2_style_variant` | 3299 |
| GET | `/api/projects/{project_id}/production/v2/assets` | `list_project_production_assets` | 3308 |
| GET | `/api/projects/{project_id}/production/v2/canon` | `get_project_production_canon` | 3322 |
| PUT | `/api/projects/{project_id}/production/v2/canon` | `put_project_production_canon` | 3333 |
| POST | `/api/projects/{project_id}/production/v2/canon/characters` | `create_project_character_identity` | 3349 |
| POST | `/api/projects/{project_id}/production/v2/canon/worlds` | `create_project_world_identity` | 3370 |
| GET | `/api/projects/{project_id}/production/v2/runs/{run_id}/voice-bindings` | `get_production_voice_bindings` | 3386 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/voices/bind` | `create_production_voice_binding` | 3395 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/voices/{character_id}/excerpt` | `create_production_h3_voice_excerpt` | 3434 |
| POST | `/api/projects/{project_id}/production/v2/assets` | `upload_project_production_asset` | 3467 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/dialogue-takes` | `upload_production_dialogue_take` | 3488 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/dialogue-takes/{asset_id}/convert` | `convert_production_dialogue_take` | 3530 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/audio-sidecars` | `create_production_audio_sidecar` | 3576 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/dialogue-tts` | `create_production_dialogue_tts` | 3604 |
| GET | `/api/projects/{project_id}/production/v2/runs/{run_id}/audio-sidecars/{job_id}` | `get_production_audio_sidecar` | 3665 |
| POST | `/api/projects/{project_id}/production/v2/assets/{asset_id}/master-identity` | `assign_production_master_identity` | 3680 |
| POST | `/api/projects/{project_id}/production/v2/assets/links` | `link_project_repertoire_asset` | 3695 |
| GET | `/api/projects/{project_id}/production/v2/assets/{asset_id}/content` | `project_production_asset_content` | 3710 |
| GET | `/api/projects/{project_id}/production/v2/runs/{run_id}` | `get_production_v2_run` | 3724 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/story/detail` | `detail_production_v2_story` | 3769 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/story/manual-source` | `create_manual_production_v2_story_source` | 3878 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/story/tasks` | `enqueue_production_v2_story_task` | 4006 |
| GET | `/api/projects/{project_id}/production/v2/runs/{run_id}/story/tasks/{task_id}` | `get_production_v2_story_task` | 4032 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/text/{stage}/tasks` | `enqueue_production_v2_text_task` | 4053 |
| GET | `/api/projects/{project_id}/production/v2/runs/{run_id}/text/{stage}/tasks/{task_id}` | `get_production_v2_text_task` | 4076 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/stage-tasks/{task_id}/resolve` | `resolve_production_v2_stage_task` | 4099 |
| GET | `/api/projects/{project_id}/production/v2/runs/{run_id}/story/revisions` | `list_production_v2_story_revisions` | 4123 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/story/revisions/{revision_id}/manual` | `save_manual_production_v2_story_revision` | 4133 |
| GET | `/api/projects/{project_id}/production/v2/runs/{run_id}/text/{stage}/revisions` | `list_production_v2_text_revisions` | 4183 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/story/revisions/{revision_id}/accept` | `accept_production_v2_story_revision` | 4195 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/text/{stage}` | `generate_production_v2_text_stage` | 4230 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/shots/{shot_id}/validate` | `validate_production_v2_shot` | 4520 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/shots/{shot_id}/prompt-preparations` | `enqueue_production_v2_shot_prompt_preparation` | 4674 |
| GET | `/api/projects/{project_id}/production/v2/runs/{run_id}/shots/{shot_id}/prompt-preparations/{task_id}` | `get_production_v2_shot_prompt_preparation` | 4748 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/shots/{shot_id}/takes` | `queue_production_v2_take` | 4917 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/takes/{take_id}/accept` | `accept_production_v2_take` | 4924 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/takes/{take_id}/cancel` | `cancel_production_v2_take` | 4947 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/takes/{take_id}/retry` | `retry_production_v2_take` | 5023 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/takes/{take_id}/reconcile-absent` | `reconcile_absent_production_v2_take` | 5045 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/text/{stage}/manual` | `save_production_v2_manual_text` | 5104 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/text/{stage}/revisions/{revision_id}/accept` | `accept_production_v2_text_revision` | 5174 |
| GET | `/api/projects/{project_id}/production/v2/runs/{run_id}/shots/{shot_id}` | `get_production_v2_shot` | 5245 |
| PUT | `/api/projects/{project_id}/production/v2/runs/{run_id}/shots/{shot_id}` | `put_production_v2_shot` | 5258 |
| GET | `/api/projects/{project_id}/production/v2/runs/{run_id}/shots/{shot_id}/draft` | `get_production_v2_shot_draft` | 5288 |
| PUT | `/api/projects/{project_id}/production/v2/runs/{run_id}/shots/{shot_id}/draft` | `save_production_v2_shot_draft` | 5310 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/refine` | `propose_production_v2_refine` | 5332 |
| POST | `/api/projects/{project_id}/production/v2/runs/{run_id}/refine/{proposal_id}/accept` | `accept_production_v2_refine` | 5379 |
| GET | `/api/automation/styles` | `automation_styles` | 5434 |
| GET | `/api/automation/styles/{style_id}` | `automation_style` | 5439 |
| GET | `/api/audio/capabilities` | `audio_capabilities` | 5447 |
| GET | `/api/audio/voices` | `audio_voices` | 5461 |
| GET | `/api/audio/models` | `audio_models` | 5466 |
| GET | `/api/music/capabilities` | `get_music_capabilities` | 5471 |
| GET | `/api/music/ace/finetune/preflight` | `get_ace_finetune_preflight` | 5476 |
| GET | `/api/music/control-foley/capabilities` | `get_control_foley_capabilities` | 5481 |
| GET | `/api/music/control-foley/schema` | `get_control_foley_schema` | 5486 |
| POST | `/api/projects/{project_id}/music/ace/jobs` | `create_ace_music_job` | 5511 |
| GET | `/api/projects/{project_id}/music/jobs` | `list_music_jobs` | 5519 |
| GET | `/api/projects/{project_id}/music/jobs/{job_id}` | `get_music_job` | 5524 |
| POST | `/api/projects/{project_id}/music/control-foley/jobs` | `create_control_foley_job` | 5531 |
| GET | `/api/projects/{project_id}/music/control-foley/jobs` | `list_control_foley_jobs` | 5546 |
| GET | `/api/projects/{project_id}/music/control-foley/jobs/{job_id}` | `get_control_foley_job` | 5551 |
| GET | `/api/audio-library/assets` | `get_audio_library_assets` | 5558 |
| POST | `/api/audio-library/assets` | `create_audio_library_asset` | 5563 |
| PATCH | `/api/audio-library/assets/{asset_id}` | `patch_audio_library_asset` | 5569 |
| DELETE | `/api/audio-library/assets/{asset_id}` | `delete_audio_library_asset` | 5575 |
| GET | `/api/audio-library/files/{asset_id}` | `get_audio_library_file` | 5581 |
| GET | `/api/audio/utilities/capabilities` | `get_audio_utility_capabilities` | 5590 |
| POST | `/api/projects/{project_id}/audio/utilities/{operation}/jobs` | `create_audio_utility_job` | 5599 |
| GET | `/api/projects/{project_id}/audio/utilities/jobs` | `list_audio_utility_jobs` | 5612 |
| GET | `/api/projects/{project_id}/audio/utilities/jobs/{job_id}` | `get_audio_utility_job` | 5617 |
| POST | `/api/audio/voices` | `add_audio_voice` | 5624 |
| POST | `/api/audio/voices/refresh` | `refresh_audio_voices` | 5653 |
| GET | `/api/audio/finetune/f5/preflight` | `get_f5_preflight` | 5661 |
| GET | `/api/audio/effects/capabilities` | `get_audio_effect_capabilities` | 5666 |
| GET | `/api/audio/rvc/models` | `get_audio_rvc_models` | 5671 |
| GET | `/api/projects/{project_id}/audio/character-map` | `get_character_map` | 5676 |
| PUT | `/api/projects/{project_id}/audio/character-map` | `put_character_map` | 5685 |
| POST | `/api/projects/{project_id}/audio/tts/timed` | `create_timed_tts_job` | 5997 |
| GET | `/api/projects/{project_id}/audio/tts/jobs` | `list_timed_tts_jobs` | 6021 |
| GET | `/api/projects/{project_id}/audio/tts/jobs/{job_id}` | `get_timed_tts_job` | 6027 |
| POST | `/api/projects/{project_id}/audio/finetune/f5/prepare` | `create_f5_prepare_job` | 6036 |
| GET | `/api/projects/{project_id}/audio/finetune/f5/jobs` | `list_f5_prepare_jobs` | 6064 |
| GET | `/api/projects/{project_id}/audio/finetune/f5/jobs/{job_id}` | `get_f5_prepare_job` | 6070 |
| POST | `/api/projects/{project_id}/audio/effects/{operation}` | `create_audio_effect_job` | 6079 |
| GET | `/api/projects/{project_id}/audio/effects/jobs` | `list_audio_effect_jobs` | 6102 |
| GET | `/api/projects/{project_id}/audio/effects/jobs/{job_id}` | `get_audio_effect_job` | 6107 |
| POST | `/api/projects/{project_id}/audio/scenes/split` | `create_scene_split` | 6114 |
| POST | `/api/projects/{project_id}/audio/scenes/{split_job_id}/stitch` | `create_scene_stitch` | 6135 |
| GET | `/api/projects/{project_id}/audio/scenes/jobs` | `list_scene_jobs` | 6164 |
| GET | `/api/projects/{project_id}/audio/scenes/jobs/{job_id}` | `get_scene_job` | 6169 |
| GET | `/api/automation/blocks` | `get_automation_blocks` | 6176 |
| GET | `/api/automation/blocks/{operation_id}/schema` | `get_automation_block_schema` | 6181 |
| GET | `/api/projects/{project_id}/automation/pipelines` | `list_audio_pipelines` | 6212 |
| POST | `/api/projects/{project_id}/automation/pipelines` | `create_audio_pipeline` | 6217 |
| PUT | `/api/projects/{project_id}/automation/pipelines/{pipeline_id}` | `update_audio_pipeline` | 6222 |
| POST | `/api/projects/{project_id}/automation/pipelines/{pipeline_id}/validate` | `validate_saved_audio_pipeline` | 6231 |
| POST | `/api/projects/{project_id}/automation/pipelines/{pipeline_id}/runs` | `start_audio_pipeline_run` | 6238 |
| GET | `/api/projects/{project_id}/automation/runs` | `list_audio_pipeline_runs` | 6247 |
| GET | `/api/projects/{project_id}/automation/runs/{run_id}` | `get_audio_pipeline_run` | 6252 |
| POST | `/api/projects/{project_id}/automation/runs/{run_id}/steps/{step_id}/retry` | `retry_audio_pipeline_step` | 6259 |
| GET | `/api/workflows/{workflow_id:path}` | `workflow_detail` | 6270 |
| GET | `/api/video-repertoire/capabilities` | `video_repertoire_capabilities` | 6280 |
| POST | `/api/video-references/index` | `index_video_references` | 6285 |
| GET | `/api/video-references/index/status` | `video_reference_index_status` | 6290 |
| POST | `/api/video-references/search` | `search_video_references` | 6296 |
| GET | `/api/video-references/search/{search_id}/next` | `next_video_reference_page` | 6306 |
| POST | `/api/video-references/search/{search_id}/refine` | `refine_video_reference_search` | 6314 |
| GET | `/api/video-references/seo-styles` | `list_video_reference_styles` | 6322 |
| POST | `/api/video-references/seo-styles` | `create_video_reference_style` | 6327 |
| DELETE | `/api/video-references/seo-styles/{style_id}` | `delete_video_reference_style` | 6335 |
| GET | `/api/video-references/clips/{clip_id}` | `get_video_reference_clip` | 6342 |
| GET | `/api/video-references/clips/{clip_id}/content` | `video_reference_clip_content` | 6350 |
| GET | `/api/video-references/clips/{clip_id}/thumbnail` | `video_reference_clip_thumbnail` | 6361 |
| POST | `/api/video-references/automation/select` | `automate_video_reference_selection` | 6372 |
| POST | `/api/projects/{project_id}/video-references/select` | `select_video_references` | 6390 |
| POST | `/api/vision/images/analyze` | `analyze_image_detailer` | 6409 |
| POST | `/api/projects/{project_id}/vision/runs` | `create_project_vision_run` | 6445 |
| GET | `/api/vision/runs/{run_id}` | `get_vision_run` | 6461 |
| GET | `/api/vision/runs/{run_id}/events` | `get_vision_run_events` | 6469 |
| POST | `/api/vision/runs/{run_id}/cancel` | `cancel_vision_run` | 6478 |
| GET | `/api/vision/runs/{run_id}/artifacts/{artifact_path:path}` | `get_vision_run_artifact` | 6486 |
| GET | `/api/vision/runs/{run_id}/generation-brief` | `get_vision_generation_brief` | 6494 |
| POST | `/api/projects/{project_id}/canvas/revisions` | `create_canvas_revision` | 6503 |
| GET | `/api/projects/{project_id}/canvas/revisions` | `list_canvas_revisions` | 6515 |
| POST | `/api/projects/{project_id}/canvas/analysis` | `create_canvas_analysis` | 6524 |
| POST | `/api/projects/{project_id}/canvas/outline` | `create_canvas_outline` | 6543 |
| GET | `/api/projects/{project_id}/audio/reconstruct` | `get_reconstruction_session` | 6556 |
| POST | `/api/projects/{project_id}/audio/reconstruct/calibration` | `save_reconstruction_calibration` | 6565 |
| POST | `/api/projects/{project_id}/audio/reconstruct/parts` | `create_reconstruction_part` | 6576 |
| POST | `/api/projects/{project_id}/audio/reconstruct/parts/{part_id}/takes` | `upload_reconstruction_take` | 6587 |
| POST | `/api/projects/{project_id}/audio/reconstruct/parts/{part_id}/accept/{take_id}` | `accept_reconstruction_take` | 6598 |
| POST | `/api/video-repertoire/youtube/resolve` | `resolve_video_sources` | 6609 |
| POST | `/api/video-repertoire/youtube/jobs` | `create_video_download_job` | 6617 |
| GET | `/api/video-repertoire/youtube/jobs` | `list_video_download_jobs` | 6626 |
| GET | `/api/video-repertoire/youtube/jobs/{job_id}` | `get_video_download_job` | 6631 |
| POST | `/api/video-repertoire/youtube/jobs/{job_id}/cancel` | `cancel_video_download_job` | 6639 |
| POST | `/api/video-repertoire/youtube/jobs/{job_id}/retry` | `retry_video_download_job` | 6649 |
| GET | `/api/video-repertoire/assets` | `list_video_assets` | 6659 |
| POST | `/api/video-repertoire/assets/import-legacy` | `import_legacy_video_assets` | 6664 |
| POST | `/api/video-repertoire/assets/upload` | `upload_video_asset` | 6669 |
| DELETE | `/api/video-repertoire/assets` | `delete_video_assets` | 6677 |
| GET | `/api/video-repertoire/assets/{asset_id}` | `get_video_asset` | 6685 |
| GET | `/api/video-repertoire/assets/{asset_id}/content` | `video_asset_content` | 6693 |
| POST | `/api/video-repertoire/analysis/jobs` | `create_video_analysis_job` | 6705 |
| GET | `/api/video-repertoire/analysis/jobs` | `list_video_analysis_jobs` | 6718 |
| GET | `/api/video-repertoire/analysis/jobs/{job_id}` | `get_video_analysis_job` | 6723 |
| POST | `/api/video-repertoire/analysis/jobs/{job_id}/cancel` | `cancel_video_analysis_job` | 6731 |
| POST | `/api/video-repertoire/analysis/jobs/{job_id}/stop` | `stop_video_analysis_job` | 6743 |
| DELETE | `/api/video-repertoire/analysis/jobs/{job_id}` | `delete_video_analysis_job` | 6753 |
| POST | `/api/video-repertoire/analysis/jobs/{job_id}/retry` | `retry_video_analysis_job` | 6763 |
| GET | `/api/video-repertoire/search` | `search_video_repertoire` | 6773 |
| POST | `/api/video-repertoire/assets/{asset_id}/vision` | `analyze_video_repertoire_asset_vision` | 6778 |
| GET | `/api/vision/references/search` | `search_vision_references` | 6796 |
| POST | `/api/vision/references/{reference_id}/promote` | `promote_vision_reference` | 6803 |
| GET | `/api/video-repertoire/artifacts/{relative_path:path}` | `video_repertoire_artifact` | 6814 |
| GET | `/api/video-repertoire/audio-assets` | `list_video_repertoire_audio_assets` | 6825 |
| DELETE | `/api/video-repertoire/audio-assets` | `delete_video_repertoire_audio_assets` | 6833 |
| GET | `/api/video-repertoire/manual/workflows` | `manual_director_workflows` | 6842 |
| GET | `/api/video-repertoire/manual/assets` | `list_manual_director_assets` | 6848 |
| POST | `/api/video-repertoire/manual/assets` | `upload_manual_director_asset` | 6853 |
| GET | `/api/video-repertoire/manual/assets/content/{relative_path:path}` | `manual_director_asset_content` | 6864 |
| POST | `/api/video-repertoire/manual/jobs` | `create_manual_director_job` | 6872 |
| GET | `/api/video-repertoire/manual/jobs` | `list_manual_director_jobs` | 6884 |
| GET | `/api/video-repertoire/manual/jobs/{run_id}` | `get_manual_director_job` | 6889 |
| DELETE | `/api/video-repertoire/manual/jobs/{run_id}` | `delete_manual_director_job` | 6897 |
| GET | `/api/video-repertoire/manual/files/{run_id}/{filename}` | `manual_director_output` | 6907 |
| GET | `/api/video-repertoire/audio-assets/content/{relative_path:path}` | `video_repertoire_audio_asset_content` | 6916 |
| GET | `/api/video-audio-analyzer/runs/{run_id}/artifacts/{artifact_path:path}` | `video_audio_analyzer_artifact` | 6940 |
| POST | `/api/video-audio-analyzer/search` | `search_video_audio_analyzer` | 6962 |
| POST | `/api/video-audio-analyzer/runs/{run_id}/sam/isolate` | `isolate_video_audio_event` | 6975 |
| GET | `/api/video-audio-analyzer/sam/previews/{temporary_id}/audio` | `video_audio_sam_preview_audio` | 6992 |
| POST | `/api/video-audio-analyzer/sam/previews/{temporary_id}/director-review` | `video_audio_sam_director_review` | 7002 |
| DELETE | `/api/video-audio-analyzer/sam/previews/{temporary_id}` | `discard_video_audio_sam_preview` | 7013 |
| POST | `/api/media/upload` | `upload_media_asset` | 7022 |
| POST | `/api/projects/{project_id}/media/jobs` | `create_media_job` | 7032 |
| GET | `/api/projects/{project_id}/files/{relative_path:path}` | `project_file` | 7099 |
| GET | `/api/projects/{project_id}/media/jobs` | `list_media_jobs` | 7107 |
| POST | `/api/projects/{project_id}/output/finalize` | `finalize_project_output` | 7132 |
| POST | `/api/projects/{project_id}/output/compose` | `compose_project_output` | 7137 |
| GET | `/api/projects/{project_id}/output/manifest` | `get_project_output_manifest` | 7159 |
