import { expect, test } from "@playwright/test";

test("Production V2 creates a story run and reviews its story proposal without live media submission", async ({ page }) => {
  const browserErrors: string[] = [];
  const lostPromptPreparationRequests: string[] = [];
  page.on("console", (message) => { if (message.type() === "error" && !/net::ERR_(TIMED_OUT|FAILED)/.test(message.text())) browserErrors.push(message.text()); });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("response", (response) => { if (response.status() >= 400) browserErrors.push(`${response.status()} ${response.url()}`); });
  page.on("requestfailed", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname.endsWith("/prompt-preparations")) lostPromptPreparationRequests.push(request.postData() || "");
    else if (!(request.resourceType() === "media" && request.failure()?.errorText === "net::ERR_ABORTED")) browserErrors.push(`${request.failure()?.errorText || "request failed"} ${request.url()}`);
  });
  let project: any = null;
  let sentRun: any = null;
  let sentSceneUnits: any[] = [];
  let sentDialogueUnits: any[] = [];
  let canon: any = { schema_version: 1, project_id: "project-1", revision: 0, characters: [], worlds: [] };
  let assets: any[] = [
    { asset_id: "pa-9999999999999999", kind: "audio", roles: ["music_candidate"], filename: "music-bed.wav", source: "project_output", media: { duration_seconds: 8 } },
    { asset_id: "pa-8888888888888888", kind: "audio", roles: ["sfx_candidate"], filename: "door-sfx.wav", source: "project_output", media: { duration_seconds: 4 } },
  ];
  let bindings: any[] = [];
  let queuedTakeCount = 0;
  const queuedTakeRequests: any[] = [];
  const promptPreparationRequests: any[] = [];
  const persistedPromptTasks = new Map<string, { task_id: string; status: string }>();
  let loseFirstPromptPreparationResponse = true;
  let cancellationCount = 0;
  let dialogueTakeUploadCount = 0;
  let dialogueConversionCount = 0;
  const imageBatchId = "image-batch-test";
  const imageJobRequests: any[] = [];
  const acceptancePayloads: any[] = [];
  const masterAssignmentPayloads: any[] = [];
  let workflowReady = false;
  let currentTake: any = null;
  let lastValidationRequest: any = null;
  const savedComposerDrafts: Record<string, any> = {};
  const composerDraftRevisions: Record<string, number> = {};
  const composerDraftCalls: Array<{ method: string; body?: any }> = [];
  const draftQueueOrder: string[] = [];
  const repertoireVideo = { asset_id: "shared-video-1", filename: "storm.mp4", title: "Storm approach", channel: "Archive", media: { duration: 12 }, sha256: "shared-hash", size: 1200 };
  const runId = "11111111-1111-4111-8111-111111111111";
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (url.pathname === "/api/projects" && method === "GET") return route.fulfill({ json: project ? [project] : [] });
    if (url.pathname === "/api/projects" && method === "POST") {
      project = { id: "project-1", title: "Bridge story", story_input: "A traveler crosses a quiet bridge.", automation_mode: false };
      return route.fulfill({ status: 201, json: project });
    }
    if (url.pathname === "/api/projects/project-1/draft" && method === "PUT") return route.fulfill({ json: project });
    if (url.pathname === "/api/production/v2/styles" && method === "GET") return route.fulfill({ json: { production_types: [{ production_type: "story_film", variants: [{ variant_id: "variant-quiet-suspense", display_name: "Quiet suspense", version: 2 }] }] } });
    if (url.pathname === "/api/production/v2/image-workflows" && method === "GET") return route.fulfill({ json: { workflows: ["z_image_turbo", "qwen_image_2512", "qwen_image_edit_2511"].map((workflow_id) => ({ workflow_id, available: true, label: workflow_id, disabled_reason: null })) } });
    if (url.pathname === "/api/projects/project-1/production/v2/runs" && method === "GET") return route.fulfill({ json: { runs: sentRun ? [{ run_id: runId, project_id: "project-1", status: "draft", config: { control_mode: "semi", making_route: "direct_h3", production_type: "story_film" }, created_at: "2026-10-04T00:00:00Z" }] : [] } });
    if (url.pathname.endsWith("/production/v2/runs") && method === "POST") { sentRun = request.postDataJSON(); return route.fulfill({ status: 201, json: { run_id: runId, project_id: "project-1", status: "draft", config: { control_mode: "semi", making_route: "direct_h3" } } }); }
    if (url.pathname === `/api/projects/project-1/production/v2/runs/${runId}` && method === "GET") return route.fulfill({ json: { run_id: runId, project_id: "project-1", status: "draft", takes: currentTake ? [...(queuedTakeCount > 1 ? [{ take_id: "parent-old", shot_id: "shot-01", status: "accepted", attempt: 1 }, { take_id: "dependent-queued", shot_id: "shot-02", parent_take_id: "parent-old", status: "queued", attempt: 1 }] : []), currentTake] : [], config: { control_mode: "semi", making_route: "direct_h3", production_type: "story_film", narrative_style_variant_id: "variant-quiet-suspense", semi_gates: { voice_selection: false } } } });
    if (url.pathname === `/api/projects/project-1/production/v2/runs/${runId}/story/revisions`) return route.fulfill({ json: { revisions: [{ revision_id: "story-canon-0123456789ab", expanded_story: "A traveler crosses a quiet bridge at dawn.", review_status: "accepted", source_hash: "source-hash", accepted_at: "2026-10-02T12:00:00Z" }] } });
    if (url.pathname === `/api/projects/project-1/production/v2/runs/${runId}/text/scenes/revisions`) return route.fulfill({ json: { revisions: [{ revision_id: "scenes-0123456789ab", source_story_hash: "source-hash", review_status: "accepted", accepted_at: "2026-10-02T12:01:00Z", items: [{ unit_id: "scene-001", content: { title: "Opening scene" } }] }] } });
    if (url.pathname === `/api/projects/project-1/production/v2/runs/${runId}/text/dialogue/revisions`) return route.fulfill({ json: { revisions: [] } });
    if (url.pathname === `/api/projects/project-1/production/v2/runs/${runId}/text/shot_plans/revisions`) return route.fulfill({ json: { revisions: [{ revision_id: "shot_plans-bbbbbbbbbbbb", source_story_hash: "source-hash", review_status: "accepted", accepted_at: "2026-10-02T12:02:00Z", items: [{ unit_id: "shot-01", scene_id: "scene-001", content: { prompt: "A traveler crosses at dawn.", scene_id: "scene-001" } }, { unit_id: "shot-02", scene_id: "scene-001", content: { prompt: "The traveler reaches the far side.", scene_id: "scene-001" } }, { unit_id: "shot-03", scene_id: "scene-002", content: { prompt: "A new scene begins at the station.", scene_id: "scene-002" } }] }] } });
    if (url.pathname === "/api/projects/project-1/production/v2/canon" && method === "GET") return route.fulfill({ json: canon });
    if (url.pathname === "/api/projects/project-1/production/v2/canon/characters" && method === "POST") { canon = { ...canon, revision: canon.revision + 1, characters: [...canon.characters, { character_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", display_name: "Character-AAAA", description: "", appearance: "", voice_brief: "", aliases: [], evidence: [], status: "active" }] }; return route.fulfill({ status: 201, json: { character: canon.characters[0], canon_revision: canon.revision } }); }
    if (url.pathname === "/api/projects/project-1/production/v2/canon/worlds" && method === "POST") { canon = { ...canon, revision: canon.revision + 1, worlds: [...canon.worlds, { world_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", display_name: "North Station", description: "", visual_rules: "", locations: [], evidence: [], status: "active" }] }; return route.fulfill({ status: 201, json: { world: canon.worlds[0], canon_revision: canon.revision } }); }
    if (url.pathname === "/api/projects/project-1/production/v2/canon" && method === "PUT") { const body = request.postDataJSON(); canon = { ...canon, ...body, revision: canon.revision + 1 }; return route.fulfill({ json: canon }); }
    if (url.pathname === "/api/projects/project-1/production/v2/assets" && method === "GET") return route.fulfill({ json: { assets, total: assets.length, limit: 50, offset: 0 } });
    if (url.pathname.endsWith("/master-identity") && method === "POST") {
      const body = request.postDataJSON(); masterAssignmentPayloads.push(body);
      const assetId = url.pathname.split("/").at(-2);
      assets = assets.map((asset) => asset.asset_id === assetId ? { ...asset, metadata: { ...asset.metadata, [body.role === "character_master" ? "character_id" : "world_id"]: body.entity_id } } : asset);
      return route.fulfill({ json: assets.find((asset) => asset.asset_id === assetId) });
    }
    if (url.pathname.endsWith("/image-jobs") && method === "POST") { const body = request.postDataJSON(); imageJobRequests.push(body); const status = body.workflow_id === "qwen_image_edit_2511" ? "completed" : "queued"; return route.fulfill({ status: 202, json: { status: "queued", batch_id: imageBatchId, reused: false, jobs: [1, 2, 3, 4].map((index) => ({ job_id: `image-job-${index}`, batch_id: imageBatchId, candidate_index: index, workflow_id: body.workflow_id, asset_role: body.asset_role, status })), generation_policy: { initial_candidates: 4, selection_authority: "user" } } }); }
    if (url.pathname === `/api/projects/project-1/production/v2/image-jobs/${imageBatchId}` && method === "GET") { const outputs = [1, 2, 3, 4].map((index) => ({ asset_id: `pa-image-candidate-${index}`, kind: "image", roles: ["image_candidate"], filename: `candidate-${index}.png`, source: "project_output", media: { width: 1280, height: 720 }, metadata: { production_image_job: { intended_role: "character_master", run_id: runId, job_id: `image-job-${index}`, status: "completed", accepted: false } } })); assets = [...assets.filter((asset) => !outputs.some((row) => row.asset_id === asset.asset_id)), ...outputs]; return route.fulfill({ json: { batch_id: imageBatchId, jobs: outputs.map((asset, index) => ({ job_id: `image-job-${index + 1}`, batch_id: imageBatchId, candidate_index: index + 1, workflow_id: "z_image_turbo", asset_role: "character_master", status: "completed", output_asset_id: asset.asset_id })) } }); }
    if (url.pathname === `/api/projects/project-1/production/v2/runs/${runId}/image-candidates/pa-image-candidate-1/accept` && method === "POST") { const body = request.postDataJSON(); const asset = assets.find((row) => row.asset_id === "pa-image-candidate-1")!; asset.roles.push(body.role); asset.metadata.production_image_job.accepted = true; asset.metadata.production_image_job.accepted_role = body.role; return route.fulfill({ json: asset }); }
    if (url.pathname === "/api/audio/rvc/models" && method === "GET") return route.fulfill({ json: [{ id: "local-voice.pth", name: "Local Voice", indexes: [] }] });
    if (url.pathname.endsWith("/dialogue-takes/pa-dialogue-00000001/convert") && method === "POST") { dialogueConversionCount += 1; return route.fulfill({ status: 202, json: { job_id: "effect-rvc-test", operation: "rvc", status: "queued", sidecar_kind: "dialogue_conversion", source_asset_id: "pa-dialogue-00000001" } }); }
    if (url.pathname.endsWith("/audio-sidecars/effect-rvc-test") && method === "GET") { const original = assets.find((row) => row.asset_id === "pa-dialogue-00000001"); if (!assets.some((row) => row.asset_id === "pa-dialogue-converted")) assets = [...assets, { ...original, asset_id: "pa-dialogue-converted", filename: "converted-line.flac", source: "project_output", metadata: { dialogue_take: { ...original.metadata.dialogue_take, recording_status: "converted", source_asset_id: original.asset_id } } }]; return route.fulfill({ json: { job_id: "effect-rvc-test", operation: "rvc", status: "completed", source_asset_id: "pa-dialogue-00000001", production_asset_id: "pa-dialogue-converted" } }); }
    if (url.pathname === "/api/projects/project-1/production/v2/assets" && method === "POST") { const form = request.postDataBuffer()?.toString("latin1") || ""; const name = form.match(/filename="([^"]+)"/)?.[1] || "voice.wav"; const role = form.match(/name="role"\r\n\r\n([^\r]+)/)?.[1] || "voice_master"; const kind = role.includes("video") || role === "project_video" ? "video" : role.includes("audio") || role === "voice_master" ? "audio" : "image"; const assetId = role === "voice_master" ? "pa-0123456789abcdef" : role === "world_master" ? "pa-world-0000000001" : role === "project_video" ? "pa-video-0000000001" : "pa-abcdef0123456789"; const asset = { asset_id: assetId, kind, roles: [role], filename: name, source: "project_upload", media: { duration_seconds: role === "voice_master" ? 31 : 8 } }; assets = [...assets.filter((row) => row.asset_id !== asset.asset_id), asset]; return route.fulfill({ status: 201, json: asset }); }
    if (url.pathname === "/api/video-repertoire/assets" && method === "GET") return route.fulfill({ json: [repertoireVideo] });
    if (url.pathname === "/api/video-repertoire/audio-assets" && method === "GET") return route.fulfill({ json: [{ asset_id: "shared-audio-1", category: "ambience", filename: "rain.wav", label: "Rain ambience", relative_path: "ambience/rain.wav", content_url: "/api/video-repertoire/audio-assets/content/ambience/rain.wav", available: true, media: { duration_seconds: 6 } }] });
    if (url.pathname === "/api/projects/project-1/production/v2/assets/links" && method === "POST") { const body = request.postDataJSON(); const audio = body.repertoire_kind === "audio"; const linked = audio ? { asset_id: "pa-shared-audio-001", kind: "audio", roles: ["project_audio"], filename: "rain.wav", source: "external_video_repertoire_audio", external_asset_id: body.external_asset_id, content_url: "/api/video-repertoire/audio-assets/content/ambience/rain.wav", media: { duration_seconds: 6 } } : { asset_id: "pa-shared-video-001", kind: "video", roles: ["action_reference_video"], filename: "storm.mp4", source: "external_video_repertoire_video", external_asset_id: body.external_asset_id, content_url: "/api/video-repertoire/assets/shared-video-1/content", media: { duration_seconds: 12 } }; assets = [...assets.filter((row) => row.asset_id !== linked.asset_id), linked]; return route.fulfill({ status: 201, json: linked }); }
    if (/\/shots\/[^/]+\/draft$/.test(url.pathname) && method === "GET") { const shotId = url.pathname.split("/").at(-2)!; composerDraftCalls.push({ method }); return route.fulfill({ json: { shot_id: shotId, revision: composerDraftRevisions[shotId] || 0, ...(savedComposerDrafts[shotId] || { draft: null }), stale: false } }); }
    if (/\/shots\/[^/]+\/draft$/.test(url.pathname) && method === "PUT") { const shotId = url.pathname.split("/").at(-2)!; const body = request.postDataJSON(); composerDraftCalls.push({ method, body, shot_id: shotId }); draftQueueOrder.push("draft"); expect(body.expected_draft_revision).toBe(composerDraftRevisions[shotId] || 0); composerDraftRevisions[shotId] = (composerDraftRevisions[shotId] || 0) + 1; const { expected_draft_revision: _expectedRevision, ...draft } = body; savedComposerDrafts[shotId] = { draft, shot_plan_revision_id: body.shot_plan_revision_id }; const held = shotId === "shot-02" && body.prompt.includes("Edited after queue") && queuedTakeCount >= 4; if (held && currentTake?.shot_id === shotId) currentTake = { ...currentTake, status: "waiting_for_user" }; return route.fulfill({ json: { shot_id: shotId, revision: composerDraftRevisions[shotId], ...savedComposerDrafts[shotId], stale: false, held_child_take_ids: held ? ["take-4"] : [] } }); }
    if (/\/shots\/[^/]+\/validate$/.test(url.pathname) && method === "POST") { const body = request.postDataJSON(); lastValidationRequest = body; const noReferences = !body.images.length && !body.videos.length && !body.standalone_audios.length; return route.fulfill({ json: { valid: true, workflow_id: noReferences ? "minimax_h3_t2v_local_v1" : "minimax_h3_r2v_dynamic_v1", validation_hash: "c".repeat(64), width: body.resolution_preset === 0.4 ? 864 : 1344, height: body.resolution_preset === 0.4 ? 480 : 768, frame_count: noReferences ? 124 : 121, workflow_readiness: { available: workflowReady }, reference_map: { pictures: body.images.map((row: any, index: number) => ({ tag: `<Picture ${index + 1}>`, asset_id: row.asset_id })), videos: [], audios: [] } } }); }
    if (/\/shots\/[^/]+\/prompt-preparations$/.test(url.pathname) && method === "POST") { const body = request.postDataJSON(); promptPreparationRequests.push(body); const task = persistedPromptTasks.get(body.idempotency_key) || { task_id: "prompt-task-test", status: "queued" }; persistedPromptTasks.set(body.idempotency_key, task); if (loseFirstPromptPreparationResponse) { loseFirstPromptPreparationResponse = false; return route.abort("timedout"); } expect({ ...body, idempotency_key: "" }).toEqual({ ...promptPreparationRequests[0], idempotency_key: "" }); return route.fulfill({ status: 202, json: task }); }
    if (url.pathname.endsWith("/prompt-preparations/prompt-task-test") && method === "GET") return route.fulfill({ json: { task_id: "prompt-task-test", status: "completed", result: { accepted: true, prompt: "Prepared prompt: preserve the bridge layout and the traveler’s turn.", prompt_hash: "d".repeat(64) } } });
    if (/\/shots\/[^/]+\/takes$/.test(url.pathname) && method === "POST") { const body = request.postDataJSON(); draftQueueOrder.push("queue"); queuedTakeRequests.push(body); queuedTakeCount += 1; const shotId = url.pathname.split("/").at(-2)!; currentTake = { take_id: `take-${queuedTakeCount}`, shot_id: shotId, parent_take_id: body.parent_take_id, status: body.parent_take_id ? "waiting_for_predecessor" : queuedTakeCount === 2 ? "needs_review" : "queued", attempt: queuedTakeCount, director_review: queuedTakeCount === 2 ? { resolution_status: "accepted", decision: { reason: "The scene matches the approved shot request.", criteria: [{ name: "requested setting", passed: true, evidence: "The bridge is visible." }] } } : null }; return route.fulfill({ status: 202, json: { take: currentTake } }); }
    if (url.pathname.endsWith("/takes/take-1/cancel") && method === "POST") { cancellationCount += 1; currentTake = { ...currentTake, status: "cancelled" }; return route.fulfill({ json: { take: currentTake, comfy_action: "not_needed" } }); }
    if (url.pathname.endsWith("/takes/take-2/accept") && method === "POST") { const body = request.postDataJSON(); acceptancePayloads.push(body); if (!(body.confirm_stale_child_take_ids || []).length) return route.fulfill({ json: { accepted: false, requires_confirmation: true, queued_children_to_stale: [{ take_id: "dependent-queued", shot_id: "shot-02" }] } }); currentTake = { ...currentTake, status: "accepted" }; return route.fulfill({ json: { accepted: true, take: currentTake, staled_child_take_ids: ["dependent-queued"] } }); }
    if (url.pathname.endsWith("/takes/take-6/reconcile-absent") && method === "POST") { expect(request.postDataJSON()).toEqual({ prompt_id: "reserved-prompt-6", confirm_no_output: true }); currentTake = { ...currentTake, status: "failed" }; return route.fulfill({ json: { take: currentTake, message: "Prompt absent; retry is available." } }); }
    if (url.pathname.endsWith("/voice-bindings") && method === "GET") return route.fulfill({ json: { bindings } });
    if (url.pathname.endsWith("/voices/bind") && method === "POST") { const body = request.postDataJSON(); bindings = [{ character_id: body.character_id, voice_asset_id: body.voice_asset_id, speaker_id: "S1" }]; return route.fulfill({ status: 201, json: bindings[0] }); }
    if (url.pathname.endsWith("/dialogue-takes") && method === "POST") { const multipart = request.postDataBuffer()?.toString("latin1") || ""; expect(multipart).toContain("We made it across."); dialogueTakeUploadCount += 1; const asset = { asset_id: "pa-dialogue-00000001", kind: "audio", roles: ["dialogue_take"], filename: "maya-line.wav", source: "project_upload", media: { duration_seconds: 3 }, metadata: { dialogue_take: { run_id: runId, character_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", speaker_id: "S1", transcript: "We made it across.", recording_status: "original_recording" } } }; assets = [...assets, asset]; return route.fulfill({ status: 201, json: asset }); }
    if (/\/voices\/[^/]+\/excerpt$/.test(url.pathname) && method === "POST") { const excerpt = { asset_id: "pa-excerpt-00000001", kind: "audio", roles: ["voice_excerpt"], filename: "voice-reference.wav", source: "project_generated", media: { duration_seconds: 5 } }; assets = [...assets, excerpt]; return route.fulfill({ status: 201, json: excerpt }); }
    if (url.pathname.endsWith("/story/tasks") && method === "POST") return route.fulfill({ status: 202, json: { task_id: "story-task-test", status: "queued" } });
    if (url.pathname.endsWith("/story/tasks/story-task-test") && method === "GET") return route.fulfill({ json: { task_id: "story-task-test", status: "completed", accepted: false, revision: { revision_id: "story-canon-0123456789ab", expanded_story: "A traveler crosses a quiet bridge at dawn.", review_status: "pending_review", source_hash: "source-hash" } } });
    if (/\/text\/(scenes|dialogue|visual_briefs|shot_plans)\/tasks$/.test(url.pathname) && method === "POST") return route.fulfill({ status: 202, json: { task_id: "text-task-test", status: "queued" } });
    if (/\/text\/(scenes|dialogue|visual_briefs|shot_plans)\/tasks\/text-task-test$/.test(url.pathname) && method === "GET") {
      const stage = url.pathname.match(/\/text\/([^/]+)\/tasks\//)?.[1] || "scenes";
      return route.fulfill({ json: { task_id: "text-task-test", status: "completed", accepted: false, revision: { revision_id: `${stage}-0123456789ab`, source_story_hash: "source-hash", review_status: "pending_review", items: [] } } });
    }
    if (url.pathname.endsWith("/story-canon-0123456789ab/manual") && method === "POST") { const body = request.postDataJSON(); return route.fulfill({ json: { accepted: false, review_required: true, revision: { revision_id: "story-canon-abcdef012345", parent_revision_id: "story-canon-0123456789ab", expanded_story: body.expanded_story, review_status: "pending_review", source_hash: body.expected_source_hash, author: "user" } } }); }
    if (url.pathname.endsWith("/story-canon-abcdef012345/accept")) return route.fulfill({ json: { accepted: true, review_status: "accepted" } });
    if (url.pathname.endsWith("/story-canon-0123456789ab/accept")) return route.fulfill({ json: { accepted: true, review_status: "accepted" } });
    if (url.pathname.endsWith("/text/scenes/manual") && method === "POST") { sentSceneUnits = request.postDataJSON().units; return route.fulfill({ json: { review_required: true, revision: { revision_id: "scenes-0123456789ab", source_story_hash: "source-hash", review_status: "pending_review", items: sentSceneUnits } } }); }
    if (url.pathname.endsWith("/text/scenes/revisions/scenes-0123456789ab/accept")) return route.fulfill({ json: { accepted: true, review_status: "accepted" } });
    if (url.pathname.endsWith("/text/dialogue/manual") && method === "POST") { sentDialogueUnits = request.postDataJSON().units; return route.fulfill({ json: { review_required: true, revision: { revision_id: "dialogue-0123456789ab", source_story_hash: "source-hash", review_status: "pending_review", items: sentDialogueUnits } } }); }
    if (url.pathname.endsWith("/text/dialogue/revisions/dialogue-0123456789ab/accept")) return route.fulfill({ json: { accepted: true, review_status: "accepted" } });
    if (url.pathname.endsWith("/text/shot_plans/manual") && method === "POST") return route.fulfill({ json: { review_required: true, revision: { revision_id: "shot_plans-0123456789ab", source_story_hash: "source-hash", review_status: "pending_review", items: [{ unit_id: "shot-01", scene_id: "scene-001", content: { prompt: "A traveler crosses a quiet bridge.", scene_id: "scene-001" } }, { unit_id: "shot-02", scene_id: "scene-001", content: { prompt: "The traveler reaches the far side.", scene_id: "scene-001" } }, { unit_id: "shot-03", scene_id: "scene-002", content: { prompt: "A new scene begins at the station.", scene_id: "scene-002" } }] } } });
    if (url.pathname.endsWith("/text/shot_plans/revisions/shot_plans-0123456789ab/accept")) return route.fulfill({ json: { accepted: true, review_status: "accepted" } });
    if (url.pathname.endsWith("/refine") && method === "POST") return route.fulfill({ json: { proposal: { proposal_id: "refine-aaaaaaaaaaaa", shot_id: "shot-01", base_prompt_hash: "prompt-hash", proposed_prompt: "A traveler crosses at dawn.", change_summary: ["Add dawn lighting"], diff: "-A traveler crosses a quiet bridge.\n+A traveler crosses at dawn.", lint: { ok: true }, applied: false } } });
    if (url.pathname.endsWith("/refine/refine-aaaaaaaaaaaa/accept")) return route.fulfill({ json: { accepted: true, revision: { revision_id: "shot_plans-bbbbbbbbbbbb", source_story_hash: "source-hash", review_status: "accepted", items: [{ unit_id: "shot-01", scene_id: "scene-001", content: { prompt: "A traveler crosses at dawn.", scene_id: "scene-001" } }, { unit_id: "shot-02", scene_id: "scene-001", content: { prompt: "The traveler reaches the far side.", scene_id: "scene-001" } }, { unit_id: "shot-03", scene_id: "scene-002", content: { prompt: "A new scene begins at the station.", scene_id: "scene-002" } }] } } });
    if (url.pathname === "/api/automation/projects") return route.fulfill({ json: [] });
    if (url.pathname === "/api/reasoning/provider") return route.fulfill({ json: { provider: "codex", providers: [{ id: "codex", label: "Codex", model: "gpt-6-luna", available: true, compatibility: false }] } });
    if (url.pathname.endsWith("/content")) {
      const assetId = url.pathname.split("/").at(-2);
      const asset = assets.find((row) => row.asset_id === assetId);
      if (asset?.kind === "image") return route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/qSoAAAAASUVORK5CYII=", "base64") });
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fulfill({ status: 404, json: { detail: "Not mocked" } });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/production");
  const assertNoHorizontalOverflow = async () => {
    const bounds = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: window.innerWidth,
      offenders: [...document.querySelectorAll<HTMLElement>("body *")].map((element) => ({ element,
        rect: element.getBoundingClientRect(), scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }))
        .filter(({ rect, scrollWidth, clientWidth }) => rect.right > window.innerWidth + 1 || rect.left < -1 || scrollWidth > clientWidth + 1)
        .slice(-12).map(({ element, rect, scrollWidth, clientWidth }) => ({ tag: element.tagName, id: element.id,
          className: element.className, left: Math.round(rect.left), right: Math.round(rect.right), width: Math.round(rect.width),
          scrollWidth, clientWidth, text: element.innerText.slice(0, 80) })) }));
    expect(bounds.document, `horizontal overflow at ${bounds.viewport}px: ${bounds.document}px document width; offenders=${JSON.stringify(bounds.offenders)}`).toBeLessThanOrEqual(bounds.viewport + 1);
  };
  await expect(page.getByRole("heading", { name: "Production workspace" })).toBeVisible();
  await assertNoHorizontalOverflow();
  await page.getByLabel("Project title").fill("Bridge story");
  await page.getByLabel("Story / premise (required)").fill("A traveler crosses a quiet bridge.");
  await page.getByRole("button", { name: "Save story draft" }).click();
  await page.getByLabel("How much should I review?").selectOption("semi");
  await page.getByLabel("Voice selection").uncheck();
  await page.getByLabel("Narrative variant").selectOption("variant-quiet-suspense");
  await page.getByRole("button", { name: "Create production run" }).click();
  await expect(page.getByText(new RegExp(runId))).toBeVisible();
  expect(sentRun.semi_gates.voice_selection).toBe(false);
  expect(sentRun.narrative_style_variant_id).toBe("variant-quiet-suspense");
  const assetsStage = page.getByRole("button", { name: /Stage 2 Assets & world/ });
  await expect(assetsStage).toBeEnabled();
  await assetsStage.click();
  await expect(assetsStage).toHaveAttribute("aria-current", "step");
  await expect(page.getByRole("heading", { name: "Character & world bible" })).toBeVisible();
  await page.getByLabel("Image prompt").fill("A weathered traveler in a blue coat, neutral reference portrait");
  await page.getByRole("button", { name: "Generate image candidates" }).click();
  await expect(page.getByLabel("Image candidate job status").getByText("completed", { exact: true })).toHaveCount(4, { timeout: 10000 });
  expect(imageJobRequests).toHaveLength(1);
  expect(imageJobRequests[0]).toMatchObject({ workflow_id: "z_image_turbo", asset_role: "character_master", width: 1280, height: 720, steps: 8 });
  await expect(page.getByRole("img", { name: "candidate-1.png" })).toBeVisible();
  await page.getByRole("button", { name: "Accept candidate" }).first().click();
  await expect(page.getByText("image_candidate, character_master", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("Candidate accepted as character master.")).toBeVisible();
  await page.getByLabel("Image model").selectOption("qwen_image_edit_2511");
  await page.getByLabel("Source images (1–3)").selectOption(["pa-image-candidate-1"]);
  await page.getByLabel("Image prompt").fill("Change the accepted character's coat to green");
  await page.getByRole("button", { name: "Generate image candidates" }).click();
  await expect.poll(() => imageJobRequests.length).toBe(2);
  expect(imageJobRequests[1]).toMatchObject({ workflow_id: "qwen_image_edit_2511", source_asset_ids: ["pa-image-candidate-1"], steps: 4, width: 1024, height: 1024 });
  await expect(page.getByLabel("Image candidate job status").getByText("completed", { exact: true })).toHaveCount(4, { timeout: 10000 });
  await page.getByRole("button", { name: "Add character" }).click();
  await expect(page.getByText("Character identity added to this project's bible.")).toBeVisible();
  await page.getByLabel("New world/location").fill("North Station");
  await page.getByRole("button", { name: "Add world" }).click();
  await expect(page.getByText("World/location added to this project's bible.")).toBeVisible();
  await expect(page.getByLabel("Character and world details (JSON)")).toContainText("Character-AAAA");
  await expect(page.getByLabel("Character and world details (JSON)")).toContainText("North Station");
  await page.getByLabel("Assign master to character").selectOption("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
  await page.getByRole("button", { name: "Assign master", exact: true }).click();
  await expect(page.getByText("Assigned to Character-AAAA", { exact: true })).toBeVisible();
  expect(masterAssignmentPayloads).toEqual([{ role: "character_master", entity_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" }]);
  await page.getByRole("button", { name: "Load shared library" }).click();
  await page.getByLabel("Shared asset").selectOption("shared-video-1");
  await page.getByRole("button", { name: "Link without copying" }).click();
  await expect(page.getByText("storm.mp4", { exact: true })).toBeVisible();
  await expect(page.getByText("Shared Video Repertoire source; original is not copied.", { exact: true })).toBeVisible();
  await expect(page.locator('video[src="/api/video-repertoire/assets/shared-video-1/content"]')).toBeVisible();
  await page.getByLabel("Media type").selectOption("audio");
  await page.getByRole("button", { name: "Load shared library" }).click();
  await page.getByLabel("Shared asset").selectOption("shared-audio-1");
  await page.getByRole("button", { name: "Link without copying" }).click();
  await expect(page.getByText("rain.wav", { exact: true })).toBeVisible();
  await expect(page.locator('audio[src="/api/video-repertoire/audio-assets/content/ambience/rain.wav"]')).toBeVisible();
  await page.getByLabel("Asset purpose").selectOption("voice_master");
  await page.getByLabel("Choose image, video, or audio").setInputFiles({ name: "voice-master.wav", mimeType: "audio/wav", buffer: Buffer.from("RIFF0000WAVEfmt ") });
  await page.getByRole("button", { name: "Upload to project" }).click();
  await expect(page.getByText("voice-master.wav", { exact: true })).toBeVisible();
  await expect(page.locator('audio[src="/api/projects/project-1/production/v2/assets/pa-0123456789abcdef/content"]')).toBeVisible();
  await page.getByRole("button", { name: /Voices & audio/ }).click();
  await page.getByLabel("Character", { exact: true }).selectOption("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
  await page.getByLabel("Eligible voice master").selectOption("pa-0123456789abcdef");
  await page.getByRole("button", { name: "Bind voice to character" }).click();
  await expect(page.getByText(/Character-AAAA → voice-master.wav \(S1\)/)).toBeVisible();
  await page.getByLabel("Exact spoken words").fill("We made it across.");
  await page.getByLabel("Original recorded audio").setInputFiles({ name: "maya-line.wav", mimeType: "audio/wav", buffer: Buffer.from("mocked-recording") });
  await page.getByRole("button", { name: "Save original dialogue take" }).click();
  await expect(page.getByText("maya-line.wav", { exact: true })).toBeVisible();
  expect(dialogueTakeUploadCount).toBe(1);
  await page.getByLabel("Installed local RVC model").selectOption("local-voice.pth");
  await page.getByRole("button", { name: "Convert with local RVC" }).click();
  await expect(page.getByText("converted-line.flac", { exact: true })).toBeVisible({ timeout: 10000 });
  expect(dialogueConversionCount).toBe(1);
  await page.getByLabel("Start time (seconds)").fill("2");
  await page.getByLabel("Excerpt duration (2–15 seconds)").fill("5");
  await page.getByRole("button", { name: "Create H3 voice reference" }).click();
  await expect(page.getByText("voice-reference.wav", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Assets & world/ }).click();
  await page.getByLabel("Asset purpose").selectOption("character_master");
  await page.getByLabel("Choose image, video, or audio").setInputFiles({ name: "maya-master.png", mimeType: "image/png", buffer: Buffer.from("not-a-real-png-but-mocked") });
  await page.getByRole("button", { name: "Upload to project" }).click();
  await expect(page.getByRole("img", { name: "maya-master.png" })).toBeVisible();
  await expect(page.getByText("maya-master.png", { exact: true })).toBeVisible();
  await page.getByLabel("Asset purpose").selectOption("world_master");
  await page.getByLabel("Choose image, video, or audio").setInputFiles({ name: "station-board.png", mimeType: "image/png", buffer: Buffer.from("mocked-world-image") });
  await page.getByRole("button", { name: "Upload to project" }).click();
  await page.getByLabel("Asset purpose").selectOption("project_video");
  await page.getByLabel("Choose image, video, or audio").setInputFiles({ name: "motion-reference.mp4", mimeType: "video/mp4", buffer: Buffer.from("mocked-video") });
  await page.getByRole("button", { name: "Upload to project" }).click();
  await expect(page.locator('video[src="/api/projects/project-1/production/v2/assets/pa-video-0000000001/content"]')).toBeVisible();
  await page.getByRole("button", { name: /Story & direction/ }).click();
  await page.getByRole("button", { name: "Ask Director to expand story" }).click();
  await expect(page.getByLabel("Expanded story proposal")).toHaveValue("A traveler crosses a quiet bridge at dawn.");
  await page.getByLabel("Expanded story proposal").fill("At sunrise, a traveler crosses a quiet bridge.");
  await page.getByRole("button", { name: "Save edits as revision" }).click();
  await expect(page.getByText("story-canon-abcdef012345")).toBeVisible();
  await expect(page.getByLabel("Expanded story proposal")).toHaveValue("At sunrise, a traveler crosses a quiet bridge.");
  await page.getByRole("button", { name: "Accept story canon" }).click();
  await expect(page.getByText("accepted", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Shot composer/ }).click();
  await expect(page.getByText(/H3 produces its own native audio/)).toBeVisible();
  await page.getByLabel("Stage", { exact: true }).selectOption("scenes");
  await page.getByLabel("Scene title").fill("Crossing");
  await page.getByLabel("Source chunk IDs (comma-separated)").fill("story_chunk_0001");
  await page.getByLabel("What happens in this scene?").fill("The traveler crosses the bridge at sunrise.");
  await page.getByRole("button", { name: "Add scene to draft" }).click();
  await expect(page.getByLabel("Stable-ID units (JSON)")).toContainText("scene-002");
  await page.getByRole("button", { name: "Save my text for review" }).click();
  expect(sentSceneUnits).toHaveLength(2);
  expect(sentSceneUnits[1]).toMatchObject({ unit_id: "scene-002", source_chunk_ids: ["story_chunk_0001"], content: { title: "Crossing" } });
  await expect(page.getByText("scenes-0123456789ab")).toBeVisible();
  await page.getByRole("button", { name: "Accept this text revision" }).click();
  await expect(page.getByText("accepted", { exact: true })).toHaveCount(1);
  await page.getByLabel("Stage", { exact: true }).selectOption("dialogue");
  await page.getByLabel("Speaker ID (optional)").fill("S1");
  await page.getByLabel("Scene unit ID (optional)").fill("scene-002");
  await page.getByLabel("Source chunk IDs (comma-separated)").fill("story_chunk_0001");
  await page.getByLabel("Exact dialogue words").fill("We made it across.");
  await page.getByRole("button", { name: "Add dialogue beat to draft" }).click();
  await expect(page.getByLabel("Stable-ID units (JSON)")).toContainText("We made it across.");
  await page.getByRole("button", { name: "Save my text for review" }).click();
  expect(sentDialogueUnits).toHaveLength(1);
  expect(sentDialogueUnits[0]).toMatchObject({ unit_id: "dialogue-001", source_chunk_ids: ["story_chunk_0001"], content: { speaker_id: "S1", scene_id: "scene-002", exact_words: "We made it across." } });
  await page.getByRole("button", { name: "Accept this text revision" }).click();
  await page.getByRole("button", { name: /Assets & world/ }).click();
  await expect(page.getByRole("heading", { name: "Character & world bible" })).toBeVisible();
  await page.getByRole("button", { name: /Voices & audio/ }).click();
  await expect(page.getByRole("heading", { name: "Character voice bindings" })).toBeVisible();
  await assertNoHorizontalOverflow();
  await page.getByRole("button", { name: /Shot composer/ }).click();
  await expect(page.getByLabel("Stage", { exact: true })).toHaveValue("shot_plans");
  await page.getByLabel("Stage", { exact: true }).selectOption("shot_plans");
  await page.getByLabel("Stable-ID units (JSON)").fill(JSON.stringify([{ unit_id: "shot-01", source_chunk_ids: [], content: { prompt: "A traveler crosses a quiet bridge.", asset_intents: [], reference_map: { pictures: [], videos: [], audios: [], speaker_audio_tags: {} } } }]));
  await page.getByRole("button", { name: "Save my text for review" }).click();
  await page.getByRole("button", { name: "Accept this text revision" }).click();
  await page.getByLabel("Shot", { exact: true }).selectOption("shot-01");
  await page.getByLabel("What should change?").fill("Set the scene at dawn");
  await page.getByRole("button", { name: "Create proposal" }).click();
  await expect(page.getByLabel("Refine prompt diff")).toContainText("A traveler crosses at dawn");
  await page.getByRole("button", { name: "Accept as new revision" }).click();
  await expect(page.getByText("shot_plans-bbbbbbbbbbbb")).toBeVisible();
  await page.getByLabel("Accepted shot").selectOption("shot-01");
  await expect(page.getByLabel("Standalone audio refs (up to 3)")).toHaveValues([]);
  await expect(page.getByLabel("Standalone audio refs (up to 3)").locator("option", { hasText: "music-bed.wav" })).toHaveCount(1);
  await expect(page.getByLabel("Standalone audio refs (up to 3)").locator("option", { hasText: "door-sfx.wav" })).toHaveCount(1);
  await expect(page.getByLabel("Include each selected video's own soundtrack")).not.toBeChecked();
  await page.getByLabel("Image references (up to 9)").selectOption(["pa-abcdef0123456789", "pa-world-0000000001"]);
  await page.getByLabel("Video references (up to 3)").selectOption("pa-video-0000000001");
  await page.getByLabel("Standalone audio refs (up to 3)").selectOption("pa-excerpt-00000001");
  await page.getByLabel("Picture 1 · maya-master.png").fill("Canonical face and costume; ignore the image background.");
  await page.getByLabel("Picture 2 · station-board.png").fill("Use only the station architecture and layout.");
  await page.getByRole("button", { name: "Move Picture 2 up" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Move Picture 1 up" })).toBeDisabled();
  await assertNoHorizontalOverflow();
  await page.getByLabel("Video 1 · motion-reference.mp4").fill("Transfer the camera orbit and action timing only.");
  await page.getByLabel("Start seconds").fill("1.5");
  await page.getByLabel("End seconds").fill("6.5");
  await page.getByLabel(/Speaker ID for Audio/).fill("S1");
  await page.getByRole("button", { name: "Preview H3 workflow" }).click();
  await expect(page.getByLabel("H3 reference tag map")).toContainText("<Picture 1>");
  await expect(page.getByText("1344×768 · 121 frames")).toBeVisible();
  expect(lastValidationRequest.images.map((row: any) => row.asset_id)).toEqual(["pa-world-0000000001", "pa-abcdef0123456789"]);
  expect(lastValidationRequest.images[0].intent).toBe("Use only the station architecture and layout.");
  expect(lastValidationRequest.videos[0]).toMatchObject({ asset_id: "pa-video-0000000001", start_sec: 1.5, end_sec: 6.5, intent: "Transfer the camera orbit and action timing only." });
  expect(lastValidationRequest.standalone_audios[0]).toMatchObject({ asset_id: "pa-excerpt-00000001", speaker_id: "S1" });
  await expect(page.getByText(/Preview validates the graph and does not submit GPU work\./i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Validated shot render" })).toBeVisible();
  await expect(page.getByText("Render is currently unavailable")).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate this shot" })).toBeDisabled();
  expect(queuedTakeCount).toBe(0);
  await page.getByLabel("Director's main H3 prompt").fill("A traveler crosses the bridge at dawn; then turns toward the river.");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect.poll(() => composerDraftCalls.some((call) => call.method === "PUT")).toBe(true);
  await expect(page.getByRole("button", { name: "Save draft · r1" })).toBeVisible();
  expect(savedComposerDrafts["shot-01"].draft).toMatchObject({ prompt: "A traveler crosses the bridge at dawn; then turns toward the river.", images: [{ asset_id: "pa-world-0000000001", intent: "Use only the station architecture and layout." }, { asset_id: "pa-abcdef0123456789", intent: "Canonical face and costume; ignore the image background." }], videos: [{ asset_id: "pa-video-0000000001", start_sec: 1.5, end_sec: 6.5, intent: "Transfer the camera orbit and action timing only." }], standalone_audios: [{ asset_id: "pa-excerpt-00000001", speaker_id: "S1" }], duration_seconds: 5 });
  await expect(page.getByRole("heading", { name: "Validated shot render" })).toHaveCount(0);
  workflowReady = true;
  await page.getByRole("button", { name: "Preview H3 workflow" }).click();
  await expect(page.getByText("Workflow preflight ready")).toBeVisible();
  await page.getByRole("button", { name: "Prepare prompt" }).click();
  await expect(page.getByRole("button", { name: "Prepare prompt" })).toBeEnabled();
  expect(promptPreparationRequests).toHaveLength(1);
  expect(lostPromptPreparationRequests).toHaveLength(1);
  expect(JSON.parse(lostPromptPreparationRequests[0]).idempotency_key).toBe(promptPreparationRequests[0].idempotency_key);
  await page.reload();
  await expect(page.getByLabel("Open saved production run")).toHaveValue(runId);
  await page.getByRole("button", { name: /Shot composer/ }).click();
  await expect(page.getByLabel("Director's main H3 prompt")).toHaveValue("A traveler crosses the bridge at dawn; then turns toward the river.");
  await page.getByRole("button", { name: "Preview H3 workflow" }).click();
  await expect(page.getByText("Workflow preflight ready")).toBeVisible();
  await page.getByRole("button", { name: "Prepare prompt" }).click();
  await expect(page.getByLabel("Prepared prompt · review or edit")).toHaveValue("Prepared prompt: preserve the bridge layout and the traveler’s turn.");
  expect(promptPreparationRequests).toHaveLength(2);
  expect(promptPreparationRequests[1].idempotency_key).toBe(promptPreparationRequests[0].idempotency_key);
  expect(persistedPromptTasks.size).toBe(1);
  expect(promptPreparationRequests[0]).toMatchObject({ shot_plan_revision_id: "shot_plans-bbbbbbbbbbbb", validation_request: { images: lastValidationRequest.images, videos: lastValidationRequest.videos } });
  await expect(page.getByRole("button", { name: "Generate this shot" })).toBeDisabled();
  await page.getByRole("button", { name: "Validate reviewed prompt" }).click();
  await expect.poll(() => lastValidationRequest.prompt).toBe("Prepared prompt: preserve the bridge layout and the traveler’s turn.");
  await page.getByRole("button", { name: "Generate this shot" }).click();
  await expect.poll(() => queuedTakeRequests.length).toBe(1);
  expect(queuedTakeRequests[0].prompt_preparation_task_id).toBe("prompt-task-test");
  const firstQueueIndex = draftQueueOrder.indexOf("queue");
  expect(draftQueueOrder[firstQueueIndex - 1]).toBe("draft");
  expect(composerDraftCalls.at(-1)?.body).toMatchObject({ prompt: lastValidationRequest.prompt, shot_plan_revision_id: lastValidationRequest.shot_plan_revision_id });
  await expect(page.getByLabel("Selected take review").getByText("queued", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Production job queue" })).toBeVisible();
  await page.getByRole("button", { name: /shot-01 · take 1/ }).click();
  await expect(page.getByRole("button", { name: /shot-01 · take 1/ })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Stop take" }).click();
  await expect(page.getByLabel("Selected take review").getByText("cancelled", { exact: true })).toBeVisible();
  expect(queuedTakeCount).toBe(1);
  expect(cancellationCount).toBe(1);
  await page.getByRole("button", { name: "Generate this shot" }).click();
  await expect(page.getByRole("button", { name: "Accept take" })).toBeVisible();
  const dependencyDialog = page.waitForEvent("dialog").then(async (dialog) => {
    expect(dialog.message()).toContain("dependent shot(s) shot-02 (dependent-queued) will become stale");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Accept take" }).click();
  await dependencyDialog;
  await expect(page.getByLabel("Selected take review").getByText("accepted", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Director video review")).toContainText("The scene matches the approved shot request.");
  await expect(page.getByLabel("Director video review")).toContainText("requested setting: passed");
  expect(acceptancePayloads).toEqual([{ confirm_stale_child_take_ids: [] }, { confirm_stale_child_take_ids: ["dependent-queued"] }]);
  expect(queuedTakeCount).toBe(2);
  await page.reload();
  await expect(page.getByLabel("Open saved production run")).toHaveValue(runId);
  await expect(page.getByText("shot_plans-bbbbbbbbbbbb")).toBeVisible();
  await page.getByRole("button", { name: /Story & direction/ }).click();
  await expect(page.getByLabel("How much should I review?")).toHaveValue("semi");
  await page.getByRole("button", { name: /Shot composer/ }).click();
  await expect(page.getByLabel("Stage", { exact: true })).toHaveValue("shot_plans");
  await expect(page.getByLabel("Accepted shot")).toHaveValue("shot-01");
  await expect.poll(() => page.getByLabel("Director's main H3 prompt").inputValue()).toBe("Prepared prompt: preserve the bridge layout and the traveler’s turn.");
  await expect(page.getByLabel("Image references (up to 9)")).toHaveValues(["pa-abcdef0123456789", "pa-world-0000000001"]);
  await expect(page.getByLabel("Picture 1 · station-board.png")).toHaveValue("Use only the station architecture and layout.");
  await expect(page.getByLabel("Picture 2 · maya-master.png")).toHaveValue("Canonical face and costume; ignore the image background.");
  await expect(page.getByLabel("Start seconds")).toHaveValue("1.5");
  await expect(page.getByLabel("End seconds")).toHaveValue("6.5");
  await expect(page.getByLabel("Speaker ID for Audio 1 (optional)")).toHaveValue("S1");
  await page.getByRole("button", { name: "Preview H3 workflow" }).click();
  await expect(page.getByText("Workflow preflight ready")).toBeVisible();
  await page.getByRole("button", { name: "Generate & Next" }).click();
  await expect.poll(() => queuedTakeCount).toBe(3);
  expect(queuedTakeRequests[2].parent_take_id).toBeNull();
  await expect(page.getByLabel("Accepted shot")).toHaveValue("shot-02");
  await expect(page.getByLabel("Predecessor take (optional)")).toHaveValue("take-3");
  await page.getByRole("button", { name: "Preview H3 workflow" }).click();
  await expect(page.getByText("Workflow preflight ready")).toBeVisible();
  await page.getByRole("button", { name: "Generate this shot" }).click();
  await expect.poll(() => queuedTakeCount).toBe(4);
  expect(queuedTakeRequests[3].parent_take_id).toBe("take-3");
  await expect(page.getByLabel("Selected take review").getByText("waiting for predecessor", { exact: true })).toBeVisible();
  await page.getByLabel("Director's main H3 prompt").fill("Edited after queue: the traveler turns to wave.");
  await page.getByRole("button", { name: /Save draft/ }).click();
  await expect(page.getByText(/1 queued take\(s\) now wait for review/)).toBeVisible();
  await page.getByRole("button", { name: "Preview H3 workflow" }).click();
  await expect(page.getByText("Workflow preflight ready")).toBeVisible();
  await page.getByRole("button", { name: "Generate & Next" }).click();
  await expect.poll(() => queuedTakeCount).toBe(5);
  expect(queuedTakeRequests[4].parent_take_id).toBe("take-3");
  await expect(page.getByLabel("Accepted shot")).toHaveValue("shot-03");
  await expect(page.getByLabel("Predecessor take (optional)")).toHaveValue("");
  await page.getByLabel("Image references (up to 9)").selectOption([]);
  await page.getByLabel("Video references (up to 3)").selectOption([]);
  await page.getByLabel("Standalone audio refs (up to 3)").selectOption([]);
  await expect(page.getByLabel("Duration (5–10 sec)")).toBeVisible();
  await page.getByLabel("H3 output preset").selectOption("0.4");
  await page.getByRole("button", { name: "Preview H3 workflow" }).click();
  await expect(page.getByText("minimax_h3_t2v_local_v1")).toBeVisible();
  expect(lastValidationRequest).toMatchObject({ resolution_preset: 0.4, images: [], videos: [], standalone_audios: [] });
  await expect(page.getByText("864×480 · 124 frames")).toBeVisible();
  await page.getByRole("button", { name: "Generate this shot" }).click();
  await expect.poll(() => queuedTakeCount).toBe(6);
  expect(queuedTakeRequests[5].validation_request).toMatchObject({ resolution_preset: 0.4, images: [], videos: [], standalone_audios: [] });
  currentTake = { ...currentTake, status: "recovery_required", prompt_id: "reserved-prompt-6" };
  await page.getByRole("button", { name: /shot-03 · take 6/ }).click();
  await page.getByRole("button", { name: "Refresh status" }).click();
  await expect(page.getByLabel("Selected take review")).toContainText("Remote Comfy state is unresolved");
  const absenceDialog = page.waitForEvent("dialog").then(async (dialog) => {
    expect(dialog.message()).toContain("reserved-prompt-6");
    expect(dialog.message()).toContain("no output is registered");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Check prompt and resolve" }).click();
  await absenceDialog;
  await expect(page.getByLabel("Selected take review").getByText("failed", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry failed take" })).toBeVisible();
  for (const width of [390, 768, 1280]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await assertNoHorizontalOverflow();
  }
  await page.evaluate(() => localStorage.removeItem("story-builder.production.run"));
  await page.reload();
  await expect(page.getByLabel("Open saved production run")).toHaveValue("");
  page.once("dialog", (dialog) => dialog.accept());
  await Promise.all([
    page.waitForNavigation({ waitUntil: "domcontentloaded" }),
    page.getByLabel("Open saved production run").selectOption(runId),
  ]);
  await expect(page.getByLabel("Open saved production run")).toHaveValue(runId);
  await expect(page.getByText("shot_plans-bbbbbbbbbbbb")).toBeVisible();
  expect(browserErrors).toEqual([]);
});
