const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export interface ReasoningProviderOption { id: "ollama" | "codex"; label: string; model: string; available: boolean; compatibility: boolean; }
export interface ReasoningProviderCatalog { provider: ReasoningProviderOption["id"]; providers: ReasoningProviderOption[]; }
export interface ReasoningProviderSmokeTest { provider: string; model: string | null; ok: boolean; result: Record<string, unknown>; elapsed_ms: number; }
export interface ReasoningDirectorTest { provider: string; model: string | null; ok: boolean; director_plan: Record<string, any>; shot_count: number; elapsed_ms: number; }
export async function getReasoningProvider(): Promise<ReasoningProviderCatalog> { return parseResponse(await fetch(`${API_BASE}/reasoning/provider`)); }
export async function setReasoningProvider(provider: ReasoningProviderOption["id"]): Promise<ReasoningProviderCatalog> { return parseResponse(await fetch(`${API_BASE}/reasoning/provider`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider }) })); }
export async function testReasoningProvider(provider: ReasoningProviderOption["id"]): Promise<ReasoningProviderSmokeTest> { return parseResponse(await fetch(`${API_BASE}/reasoning/provider/test`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider }) })); }
export async function testReasoningDirector(provider: ReasoningProviderOption["id"]): Promise<ReasoningDirectorTest> { return parseResponse(await fetch(`${API_BASE}/reasoning/provider/test-director`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider }) })); }

export async function analyzeImageDetailer(file: File, mode: "quick" | "balanced" | "deep" = "balanced"): Promise<any> {
  const body = new FormData(); body.append("file", file); body.append("mode", mode);
  const response = await fetch(`${API_BASE}/vision/images/analyze`, { method: "POST", body });
  return parseResponse(response);
}
export async function createVisionRun(projectId: string, file: File, mode: "quick" | "balanced" | "deep" = "balanced"): Promise<any> {
  const body = new FormData(); body.append("file", file); body.append("mode", mode);
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/vision/runs`, { method: "POST", body }));
}
export async function getVisionRun(runId: string): Promise<any> { return parseResponse(await fetch(`${API_BASE}/vision/runs/${encodeURIComponent(runId)}`)); }
export async function cancelVisionRun(runId: string): Promise<any> { return parseResponse(await fetch(`${API_BASE}/vision/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" })); }
export function getVisionArtifactUrl(runId: string, path: string): string { return `${API_BASE}/vision/runs/${encodeURIComponent(runId)}/artifacts/${path.split("/").map(encodeURIComponent).join("/")}`; }

export type ArtifactType = "story" | "characters" | "scenes" | "subscenes" | "dialogue" | "image_jobs";

export interface ProjectArtifact {
  type: ArtifactType;
  status: string;
  path: string;
  updated_at?: string | null;
  content: any;
}

export interface ProjectState {
  id: string;
  title: string;
  story_input: string;
  automation_mode: boolean;
  status: string;
  current_stage: string;
  created_at: string;
  updated_at: string;
  runtime: {
    job_id: string | null;
    state: string;
    current_task: string;
    progress: number;
    completed_tasks: string[];
    last_error: string | null;
    automation_active: boolean;
    supervisor?: Record<string, any>;
  };
  artifacts: Record<ArtifactType, ProjectArtifact>;
  image_queue: {
    current_index: number;
    batches: Array<any>;
    accepted: Array<any>;
  };
  media_jobs?: Array<any>;
  logs: Array<{
    id: string;
    timestamp: string;
    level: string;
    message: string;
  }>;
  automation_run?: AutomationRunState | null;
}

export interface AutomationStyle { style_id: string; name: string; version: number; description: string; stages: Record<string, string>; analysis?: Record<string, unknown>; }
export interface AutomationRunState { run_id: string; project_id: string; status: string; progress: number; current_stage: string; style_id: string; style_version: number; narrative_style_variant_id?: string | null; narrative_style_variant_version?: number | null; narrative_style_variant_hash?: string | null; style_snapshot?: Record<string, any>; detail_story: boolean; reasoning_provider?: string; reasoning_model?: string | null; reasoning_adapter_version?: string; stages: Record<string, string>; started_at?: string; updated_at?: string; error?: string | null; }
export async function listAutomationStyles(): Promise<AutomationStyle[]> { return parseResponse(await fetch(`${API_BASE}/automation/styles`)); }
export async function listAutomationProjects(): Promise<Array<{ project_id: string; title: string; automation_run?: AutomationRunState | null }>> { return parseResponse(await fetch(`${API_BASE}/automation/projects`)); }
export async function deleteAutomationProjects(projectIds: string[]): Promise<{ deleted: string[] }> { return parseResponse(await fetch(`${API_BASE}/automation/projects`, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_ids: projectIds, confirm: true }) })); }
export async function startStoryAutomation(projectId: string, payload: { style_id: string; detail_story: boolean; narrative_style_variant_id?: string | null }): Promise<AutomationRunState> { return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/automation/start`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })); }
export async function uploadAutomationInput(projectId: string, files: File[]): Promise<any> { const form = new FormData(); files.forEach((file) => form.append("files", file)); return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/automation/input`, { method: "POST", body: form })); }
export async function getStoryAutomation(projectId: string): Promise<AutomationRunState> { return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/automation/run`)); }
export async function actionStoryAutomation(projectId: string, action: "pause" | "resume" | "reset"): Promise<AutomationRunState> { return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/automation/${action}`, { method: "POST" })); }
export interface ProductionRunState { run_id?: string; project_id?: string; status: string; stage?: string; progress?: number; scenes?: Array<any>; error?: string | null; manifest_path?: string; }
export interface ProductionStageTask { task_id: string; stage: string; status: string; attempt_count: number; shot_id?: string; shot_plan_revision_id?: string; result?: Record<string, any> | null; error?: Record<string, any> | null; created_at: string; updated_at: string; }
export interface ProductionV2Run { run_id: string; project_id: string; status: string; config: Record<string, any>; created_at?: string; updated_at?: string; takes?: Array<Record<string, any>>; stage_tasks?: ProductionStageTask[]; }
export interface ProductionV2StoryRevision { revision_id: string; expanded_story: string; review_status: string; source_hash: string; [key: string]: any; }
export interface ProductionCanon { revision: number; characters: Array<Record<string, any>>; worlds: Array<Record<string, any>>; [key: string]: any; }
export interface ProductionAsset { asset_id: string; kind: "image" | "video" | "audio"; roles: string[]; filename: string; sha256?: string; size_bytes?: number; media?: Record<string, any>; source?: string; metadata?: Record<string, any>; [key: string]: any; }
export interface ProductionImageJob { job_id: string; batch_id: string; candidate_index: number; workflow_id: string; asset_role: string; status: string; prompt_id?: string | null; output_asset_id?: string | null; error?: Record<string, any> | null; director_review?: { resolution_status: string; attempt_count?: number; lease_until?: string; retake_batch_id?: string | null; retake_jobs?: ProductionImageJob[]; decision?: Record<string, any>; error?: Record<string, any> | null } | null; }
export interface ProductionImageJobBatch { batch_id: string; jobs: ProductionImageJob[]; reused?: boolean; generation_policy?: Record<string, any>; }

export function isProductionImageBatchSettled(batch: ProductionImageJobBatch): boolean {
  const visit = (jobs: ProductionImageJob[]): boolean => jobs.every((job) => {
    if (!["completed", "failed", "cancelled", "recovery_required"].includes(job.status)) return false;
    const review = job.director_review;
    if (batch.generation_policy?.selection_authority !== "director" || job.status !== "completed" || !job.output_asset_id) return true;
    if (!review || ["pending", "reviewing", "review_recovery_pending"].includes(review.resolution_status)) return false;
    if (["accepted", "rejected", "blocked"].includes(review.resolution_status)) return true;
    if (review.resolution_status === "retake_queued") return Boolean(review.retake_jobs?.length) && visit(review.retake_jobs || []);
    return false;
  });
  return batch.jobs.length > 0 && visit(batch.jobs);
}
export interface ProductionImageWorkflowReadiness { workflow_id: string; label: string; available: boolean; disabled_reason?: string | null; }
export async function listProductionImageWorkflows(): Promise<{ workflows: ProductionImageWorkflowReadiness[] }> {
  return parseResponse(await fetch(`${API_BASE}/production/v2/image-workflows`));
}
export async function queueProductionImageJob(projectId: string, runId: string, payload: { idempotency_key: string; workflow_id: string; asset_role: string; prompt: string; seed: number; width?: number; height?: number; steps?: number; cfg?: number; source_asset_ids?: string[]; entity_id?: string }): Promise<ProductionImageJobBatch> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/image-jobs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function getProductionImageJobBatch(projectId: string, batchId: string): Promise<ProductionImageJobBatch> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/image-jobs/${encodeURIComponent(batchId)}`));
}
export async function acceptProductionImageCandidate(projectId: string, runId: string, assetId: string, role: string): Promise<ProductionAsset> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/image-candidates/${encodeURIComponent(assetId)}/accept`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role }),
  }));
}
export async function listProductionAssets(projectId: string, options: { kind?: string; role?: string } = {}): Promise<{ assets: ProductionAsset[]; total: number }> {
  const query = new URLSearchParams(); if (options.kind) query.set("kind", options.kind); if (options.role) query.set("role", options.role);
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/assets?${query.toString()}`));
}
export async function assignProductionMasterIdentity(projectId: string, assetId: string, role: string, entityId: string): Promise<ProductionAsset> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/assets/${encodeURIComponent(assetId)}/master-identity`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role, entity_id: entityId }),
  }));
}
export async function uploadProductionAsset(projectId: string, file: File, role: string): Promise<ProductionAsset> {
  const body = new FormData(); body.set("file", file); body.set("role", role);
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/assets`, { method: "POST", body }));
}
export async function uploadProductionDialogueTake(projectId: string, runId: string, characterId: string, transcript: string, file: File): Promise<ProductionAsset> {
  const body = new FormData(); body.set("file", file); body.set("character_id", characterId); body.set("transcript", transcript);
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/dialogue-takes`, { method: "POST", body }));
}
export async function convertProductionDialogueTake(projectId: string, runId: string, assetId: string, modelId: string, idempotencyKey?: string): Promise<any> {
  const body = new FormData(); body.set("operation", "rvc"); body.set("settings", JSON.stringify({ model: modelId }));
  if (idempotencyKey) body.set("idempotency_key", idempotencyKey);
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/dialogue-takes/${encodeURIComponent(assetId)}/convert`, { method: "POST", body }));
}
export async function linkProductionRepertoireAsset(projectId: string, repertoireKind: "video" | "audio", externalAssetId: string): Promise<ProductionAsset> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/assets/links`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repertoire_kind: repertoireKind, external_asset_id: externalAssetId }),
  }));
}
export async function getProductionVoiceBindings(projectId: string, runId: string): Promise<{ bindings: Array<Record<string, any>> }> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/voice-bindings`));
}
export async function bindProductionVoice(projectId: string, runId: string, characterId: string, options: { strategy: "manual"; voiceAssetId: string } | { strategy: "seeded_random" }): Promise<any> {
  const payload = options.strategy === "manual"
    ? { character_id: characterId, strategy: options.strategy, voice_asset_id: options.voiceAssetId }
    : { character_id: characterId, strategy: options.strategy };
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/voices/bind`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function createProductionVoiceExcerpt(projectId: string, runId: string, characterId: string, payload: { voice_asset_id: string; start_sec: number; duration_seconds: number }): Promise<ProductionAsset> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/voices/${encodeURIComponent(characterId)}/excerpt`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }));
}
export async function createProductionAudioSidecar(projectId: string, runId: string, payload: { idempotency_key?: string; kind: "music" | "sfx"; prompt: string; duration_seconds: number; seed: number; lyrics?: string; mode?: "instrumental" | "song"; start_seconds?: number }): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/audio-sidecars`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...payload, idempotency_key: payload.idempotency_key || crypto.randomUUID() }),
  }));
}
export async function createProductionDialogueTTS(projectId: string, runId: string, payload: {
  idempotency_key: string;
  speakers: Array<{ character_id: string; voice_excerpt_asset_id: string }>;
  lines: Array<{ character_id: string; text: string; start_seconds: number; end_seconds: number }>;
  seed: number;
}): Promise<any> {
  const endpoint = API_BASE + "/projects/" + encodeURIComponent(projectId) + "/production/v2/runs/" +
    encodeURIComponent(runId) + "/dialogue-tts";
  return parseResponse(await fetch(endpoint, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }));
}
export async function getProductionAudioSidecarJob(projectId: string, runId: string, jobId: string): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/audio-sidecars/${encodeURIComponent(jobId)}`));
}
export async function validateProductionShot(projectId: string, runId: string, shotId: string, payload: { shot_plan_revision_id: string; prompt: string; duration_seconds: number; resolution_preset: number; steps: number; ref_image_size: string; seed: number; images: Array<{ asset_id: string; role: string; intent: string }>; videos: Array<{ asset_id: string; role: string; intent: string; include_paired_soundtrack: boolean; audio_intent: string }>; standalone_audios: Array<{ asset_id: string; role: string; intent: string; speaker_id?: string | null }> }): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/shots/${encodeURIComponent(shotId)}/validate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function prepareProductionShotPrompt(projectId: string, runId: string, shotId: string, payload: { idempotency_key: string; shot_plan_revision_id: string; validation_request: Record<string, unknown>; resolve_catalog?: boolean }): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/shots/${encodeURIComponent(shotId)}/prompt-preparations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function getProductionShotPromptPreparation(projectId: string, runId: string, shotId: string, taskId: string): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/shots/${encodeURIComponent(shotId)}/prompt-preparations/${encodeURIComponent(taskId)}`));
}
export async function getProductionShotDraft(projectId: string, runId: string, shotId: string): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/shots/${encodeURIComponent(shotId)}/draft`));
}
export async function saveProductionShotDraft(projectId: string, runId: string, shotId: string, payload: Record<string, unknown>): Promise<any> {
  const endpoint = `${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/shots/${encodeURIComponent(shotId)}/draft`;
  console.info("[production-api] Saving shot draft", { project_id: projectId, run_id: runId, shot_id: shotId,
    expected_draft_revision: payload.expected_draft_revision, endpoint });
  return parseResponse(await fetch(endpoint, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function queueProductionShot(projectId: string, runId: string, shotId: string, validationRequest: any, idempotencyKey: string, parentTakeId?: string | null, promptPreparationTaskId?: string | null): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/shots/${encodeURIComponent(shotId)}/takes`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idempotency_key: idempotencyKey, validation_request: validationRequest, parent_take_id: parentTakeId || null, prompt_preparation_task_id: promptPreparationTaskId || null }) }));
}
export async function acceptProductionTake(projectId: string, runId: string, takeId: string, confirmStaleChildTakeIds: string[] = []): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/takes/${encodeURIComponent(takeId)}/accept`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm_stale_child_take_ids: confirmStaleChildTakeIds }) }));
}
export async function cancelProductionTake(projectId: string, runId: string, takeId: string): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/takes/${encodeURIComponent(takeId)}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "user_cancelled" }) }));
}
export async function retryProductionTake(projectId: string, runId: string, takeId: string): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/takes/${encodeURIComponent(takeId)}/retry`, { method: "POST" }));
}
export async function reconcileAbsentProductionTake(projectId: string, runId: string, takeId: string, promptId: string): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/takes/${encodeURIComponent(takeId)}/reconcile-absent`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt_id: promptId, confirm_no_output: true }),
  }));
}
export async function fetchProductionV2Run(projectId: string, runId: string): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}`));
}
export async function listProductionV2Runs(projectId: string): Promise<ProductionV2Run[]> {
  const result = await parseResponse<{ runs: ProductionV2Run[] }>(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs`));
  return result.runs;
}
export async function getProductionCanon(projectId: string): Promise<ProductionCanon> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/canon`));
}
export async function saveProductionCanon(projectId: string, canon: ProductionCanon): Promise<ProductionCanon> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/canon`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: canon.revision, characters: canon.characters, worlds: canon.worlds, actor: "user" }) }));
}
export async function createProductionCharacter(projectId: string, displayName?: string): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/canon/characters`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ display_name: displayName || null }) }));
}
export async function createProductionWorld(projectId: string, displayName: string, description = ""): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/canon/worlds`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ display_name: displayName, description }) }));
}
export async function createProductionV2Run(projectId: string, payload: { idempotency_key: string; control_mode: string; making_route: string; image_workflow_id?: string | null; production_type: string; narrative_style_variant_id?: string | null; semi_gates?: Record<string, boolean> }): Promise<ProductionV2Run> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function createProductionV2StoryDetail(projectId: string, runId: string, idempotencyKey: string): Promise<{ revision: ProductionV2StoryRevision; accepted: boolean; review_required: boolean }> {
  const base = `${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/story`;
  type StoryTaskResponse = { task_id: string; status: string; accepted?: boolean; revision?: ProductionV2StoryRevision; error?: { message?: string } | null };
  let task = await parseResponse<StoryTaskResponse>(await fetch(`${base}/tasks`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idempotency_key: idempotencyKey }) }));
  while (["queued", "running"].includes(task.status)) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    task = await parseResponse<StoryTaskResponse>(await fetch(`${base}/tasks/${encodeURIComponent(task.task_id)}`));
  }
  if (task.status === "recovery_required") throw new ProductionStageRecoveryRequiredError(task.task_id);
  if (task.status !== "completed" || !task.revision) {
    const message = task.error?.message || `Story task stopped in ${String(task.status).replaceAll("_", " ")}.`;
    throw new Error(`Story task ${task.status}: ${message}`);
  }
  return { revision: task.revision, accepted: Boolean(task.accepted),
    review_required: task.revision.review_status === "pending_review" };
}

export class ProductionStageRecoveryRequiredError extends Error {
  constructor(readonly taskId: string, readonly retryStorageKey?: string) {
    super(`Task ${taskId} needs reconciliation. Inspect the run for a durable revision before resolving it.`);
    this.name = "ProductionStageRecoveryRequiredError";
  }
}

export async function resolveProductionStageTaskWithoutResult(projectId: string, runId: string, taskId: string): Promise<any> {
  const base = `${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}`;
  return parseResponse(await fetch(`${base}/stage-tasks/${encodeURIComponent(taskId)}/resolve`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm_no_durable_result: true }),
  }));
}
export async function listProductionV2StoryRevisions(projectId: string, runId: string): Promise<{ revisions: ProductionV2StoryRevision[] }> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/story/revisions`));
}
export async function listProductionV2TextRevisions(projectId: string, runId: string, stage: string): Promise<{ revisions: any[] }> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/text/${encodeURIComponent(stage)}/revisions`));
}
export async function acceptProductionV2Story(projectId: string, runId: string, revision: ProductionV2StoryRevision): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/story/revisions/${encodeURIComponent(revision.revision_id)}/accept`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_source_hash: revision.source_hash }) }));
}
export async function createProductionV2ManualStorySource(projectId: string, runId: string, expectedSourceHash: string): Promise<{ revision: ProductionV2StoryRevision; accepted: boolean; review_required: boolean; reused: boolean }> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/story/manual-source`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_source_hash: expectedSourceHash }),
  }));
}
export async function saveProductionV2ManualStory(projectId: string, runId: string, revision: ProductionV2StoryRevision, expandedStory: string): Promise<{ revision: ProductionV2StoryRevision; accepted: boolean; review_required: boolean }> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/story/revisions/${encodeURIComponent(revision.revision_id)}/manual`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expanded_story: expandedStory, expected_source_hash: revision.source_hash }) }));
}
export async function createProductionV2TextStage(projectId: string, runId: string, stage: string, sourceRevisionId: string, units: any[]): Promise<any> {
  const base = `${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/text/${encodeURIComponent(stage)}`;
  const request = { source_revision_id: sourceRevisionId, units };
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify(request)));
  const fingerprint = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  const storageKey = `story-builder-stage-task:${projectId}:${runId}:${stage}:${fingerprint}`;
  let idempotencyKey = localStorage.getItem(storageKey);
  if (!idempotencyKey) {
    idempotencyKey = `text-${crypto.randomUUID()}`;
    localStorage.setItem(storageKey, idempotencyKey);
  }
  type TextTaskResponse = { task_id: string; status: string; accepted?: boolean; revision?: any; error?: { message?: string } | null };
  let task: TextTaskResponse;
  task = await parseResponse<TextTaskResponse>(await fetch(`${base}/tasks`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...request, idempotency_key: idempotencyKey }) }));
  while (["queued", "running"].includes(task.status)) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    task = await parseResponse<TextTaskResponse>(await fetch(`${base}/tasks/${encodeURIComponent(task.task_id)}`));
  }
  if (task.status === "recovery_required") throw new ProductionStageRecoveryRequiredError(task.task_id, storageKey);
  localStorage.removeItem(storageKey);
  if (task.status !== "completed" || !task.revision) {
    const message = task.error?.message || `Text task stopped in ${String(task.status).replaceAll("_", " ")}.`;
    throw new Error(`Text task ${task.status}: ${message}`);
  }
  return { revision: task.revision, accepted: Boolean(task.accepted),
    review_required: task.revision.review_status === "pending_review" };
}
export async function saveProductionV2ManualText(projectId: string, runId: string, stage: string, sourceRevisionId: string, units: any[]): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/text/${encodeURIComponent(stage)}/manual`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_revision_id: sourceRevisionId, units }) }));
}
export async function acceptProductionV2Text(projectId: string, runId: string, stage: string, revisionId: string, sourceHash: string): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/text/${encodeURIComponent(stage)}/revisions/${encodeURIComponent(revisionId)}/accept`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_source_hash: sourceHash }) }));
}
export async function proposeProductionV2Refine(projectId: string, runId: string, shotPlanRevisionId: string, shotId: string, instruction: string): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/refine`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ shot_plan_revision_id: shotPlanRevisionId, shot_id: shotId, instruction }) }));
}
export async function acceptProductionV2Refine(projectId: string, runId: string, proposalId: string, shotPlanRevisionId: string, expectedPromptHash: string): Promise<any> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/v2/runs/${encodeURIComponent(runId)}/refine/${encodeURIComponent(proposalId)}/accept`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ shot_plan_revision_id: shotPlanRevisionId, expected_prompt_hash: expectedPromptHash }) }));
}
export async function startProduction(projectId: string, execute_media = true): Promise<ProductionRunState> { return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/start`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ execute_media }) })); }
export async function getProductionRun(projectId: string): Promise<ProductionRunState> { return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/production/run`)); }

export interface WorkflowField {
  key: string;
  label: string;
  kind: "text" | "number" | "image";
  required: boolean;
  multiple: boolean;
  description: string;
  default: any;
}

export interface WorkflowManifest {
  id: string;
  label: string;
  category: string;
  source_path: string;
  output_type: string;
  fields: WorkflowField[];
  recommended_use_case: string;
  supports_api_submission: boolean;
  node_count: number;
}

export interface AudioBlockCapability {
  id: string;
  label: string;
  phase: number;
  status: "available" | "testing" | "planned" | "research";
  executor: "backend" | "comfyui" | "python" | "training";
}

export interface AudioCapabilities {
  comfyui_url: string;
  comfyui_online: boolean;
  comfyui_root: string;
  comfyui_root_exists: boolean;
  tts_suite_root: string;
  tts_suite_exists: boolean;
  architecture: { machine: string; platform: string; is_aarch64: boolean };
  blocks: AudioBlockCapability[];
}

export interface AudioVoice {
  id: string;
  name: string;
  source: string;
  relative_path: string;
  audio_path: string;
  transcript_path: string | null;
  has_transcript: boolean;
  discoverable: boolean;
  user_managed: boolean;
}

export interface AudioModel {
  id: string;
  family: string;
  name: string;
  path: string;
  artifact_count: number;
  finetune_status: string;
  aarch64_status: string;
  one_shot_reference?: boolean;
}

export interface VoiceRefreshResult {
  refreshed: boolean;
  live_count: number;
  catalog_count: number;
  expected_voice_id?: string | null;
  expected_voice_key?: string | null;
  expected_discovered?: boolean | null;
  restart_required: boolean;
}

export interface VoiceInstallResult {
  voice: AudioVoice | null;
  refresh_required: boolean;
  restart_required: boolean;
  live_discovery?: VoiceRefreshResult & { error?: string };
}

export interface F5Preflight {
  architecture: string;
  supported_models: string[];
  checks: Array<{ name: string; ok: boolean; detail: string }>;
  preparation_ready: boolean;
  training_ready: boolean;
  training_enabled: false;
}

export interface F5PrepareJob {
  job_id: string;
  kind: "f5_prepare";
  status: "queued" | "running" | "completed" | "failed";
  dataset_name: string;
  base_model: string;
  validation: { sample_count: number; total_duration: number; sample_rates: number[]; samples: Array<Record<string, unknown>> };
  artifacts: Record<string, string>;
  command_preview?: string[] | null;
  command_blockers: string[];
  error?: string | null;
}

export interface RVCCatalogModel { id: string; name: string; path: string; size: number; indexes: Array<{ id: string; path: string; size: number }> }
export type AudioEffectOperation = "noise_cleanup" | "voice_repair" | "voice_changer" | "rvc" | "emotion" | "style";
export interface AudioEffectJob {
  job_id: string; operation: AudioEffectOperation; status: "queued" | "running" | "completed" | "failed";
  settings: Record<string, unknown>; outputs: Array<{ kind: string; relative_path: string; filename: string }>;
  primary_output?: { kind: string; relative_path: string; filename: string } | null;
  report_path?: string; export_path?: string; error?: string | null;
}

export interface MusicCapabilities {
  comfyui_online: boolean;
  ace: { status: string; checkpoint: string; checkpoint_size: number };
  finetune: { status: string; smoke_ready: boolean; full_training_enabled: false; checks: Array<{ name: string; ok: boolean; detail: string }> };
}
export interface MusicJob { job_id: string; kind: string; status: string; settings: Record<string, unknown>; outputs: Array<{ kind: string; relative_path: string; filename: string }>; primary_output?: { relative_path: string }; error?: string | null }
export interface ControlFoleyCapabilities { status: string; comfyui_online: boolean; model: string; model_ready: boolean; missing_nodes: string[]; schema: { modes: Array<{ id: string; label: string; requires: string[] }> } }
export interface ControlFoleyJob extends MusicJob { inputs: Record<string, string>; export_path?: string }
export interface AutomationBlock { id: string; label: string; executor: string; inputs: Record<string, string>; outputs: Record<string, string>; parameters: { required?: string[]; fields: Record<string, string> } }
export interface AudioPipeline { pipeline_id: string; version: number; name: string; creator: string; steps: Array<Record<string, unknown>>; valid: boolean; validation_errors: string[]; created_at: string; updated_at: string }
export interface AutomationRun { run_id: string; pipeline_id: string; status: string; steps: Array<{ step_id: string; operation: string; status: string; outputs: Record<string, unknown>; error?: string; job?: Record<string, unknown> }>; error?: string; final_output?: string }
export interface AudioLibraryAsset { asset_id: string; filename: string; relative_source_path: string; size: number; sha256: string; tags: string[]; notes: string; duration?: number; sample_rate?: number; channels?: number; duplicate?: boolean }
export interface AudioUtilityJob { job_id: string; operation: string; status: string; progress?: number; settings: Record<string, unknown>; outputs: Array<{ filename: string; relative_path: string; duration?: number }>; items: Array<Record<string, unknown>>; error?: string | null }
export interface AudioUtilityCapabilities { ffmpeg: boolean; ffprobe: boolean; docker: boolean; architecture: string; operations: Array<{ id: string; status: string; runtime: string; reason?: string | null }> }

export interface VideoRepertoireCapabilities {
  repertoire_root: string; ffmpeg: boolean; ffprobe: boolean; yt_dlp: boolean; ollama_online: boolean;
  ollama_models: string[]; analysis_model: string; legacy_video_root: string; legacy_video_count: number;
  video_audio_analyzer_ready?: boolean; video_audio_analyzer_models_ready?: boolean; video_audio_analyzer_image_ready?: boolean; video_audio_analyzer_audio_image_ready?: boolean;
  pe_av_query_worker_online?: boolean;
  active_analysis_job?: string | null;
}
export interface VideoAsset {
  asset_id: string; filename: string; source_mode: string; source_url: string; title: string; channel: string;
  sha256: string; size: number; created_at: string; provenance_notes: string;
  media: { duration?: number | null; format?: string | null; video_codec?: string | null; audio_codec?: string | null; width?: number | null; height?: number | null };
  analysis_ids: string[];
}
export interface VideoJob {
  job_id: string; kind: "youtube" | "analysis"; status: string; progress: number; stage: string; message: string;
  request: Record<string, unknown>; events: Array<{ timestamp: string; stage: string; status: string; message: string; payload: Record<string, unknown> }>;
  result?: Record<string, unknown> | null; error?: string | null; created_at: string; updated_at: string;
}
export interface ResolvedVideoSource { source_mode: string; query: string; candidates: Array<{ url: string; video_id: string; title: string; channel: string }> }
export interface VideoSearchResult { job_id?: string; clip_id?: string; asset_id?: string; title?: string; source_video?: string; scene_id: string; start_time_sec?: number; end_time_sec?: number | null; summary: string; keywords?: string[]; clip_path?: string; match_score?: number; match_reason?: string }
export interface VideoAudioCorpusResult {
  record_id: string; result_id: string; kind: string; run_id: string; video_id: string; source_video_id?: string;
  source_file?: string; asset_id?: string | null; scene_id?: string | null; start_time_sec?: number | null;
  end_time_sec?: number | null; text: string; score?: number; semantic_score?: number; keyword_score?: number;
  artifact_path?: string | null; clip_artifact_path?: string | null;
  cuts?: Array<{ cut_id: string; parent_scene_id: string; start_time_sec: number; end_time_sec: number; duration_sec: number; boundary_method: string; boundary_confidence: string }>;
}
export interface VideoAudioCorpusSearch {
  query: string; mode: string; query_backend?: string; reason?: string; total_candidates: number;
  next_offset?: number | null; results: VideoAudioCorpusResult[];
}
export interface StoryRevision { revision_id: string; kind: "novel" | "analysis" | "screenplay"; parent_revision_id?: string | null; created_at: string; content_hash: string; metadata: Record<string, unknown>; content: any }
export interface ReconstructionCharacter { character_id: string; name: string; calibration_sentence?: string; voice_settings?: Record<string, unknown>; status: string }
export interface ReconstructionPart { part_id: string; character_name: string; sequence: number; expected_text: string; accepted_take_id?: string | null; accepted_path?: string }
export interface ReconstructionTake { take_id: string; part_id: string; sequence: number; character_name: string; raw_path: string; transcript: string; status: string; created_at: string }
export interface ReconstructionSession { version: number; characters: ReconstructionCharacter[]; parts: ReconstructionPart[]; takes: ReconstructionTake[]; updated_at: string }

export const CURRENT_PROJECT_KEY = "story-builder.currentProjectId";
export const STORY_DRAFT_KEY = "story-builder.draft";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function listProjects(): Promise<ProjectState[]> {
  const response = await fetch(`${API_BASE}/projects`);
  return parseResponse<ProjectState[]>(response);
}

export async function createProject(payload: {
  title: string;
  story_input: string;
  automation_mode: boolean;
}): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<ProjectState>(response);
}

export async function fetchProject(projectId: string): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}`);
  return parseResponse<ProjectState>(response);
}

export async function fetchProjectStatus(projectId: string): Promise<any> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/status`);
  return parseResponse<any>(response);
}

export async function updateProjectDraft(payload: {
  projectId: string;
  title: string;
  story_input: string;
  automation_mode: boolean;
}): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${payload.projectId}/draft`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: payload.title,
      story_input: payload.story_input,
      automation_mode: payload.automation_mode,
    }),
  });
  return parseResponse<ProjectState>(response);
}

export async function generateArtifact(projectId: string, artifactType: ArtifactType): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/artifacts/${artifactType}/generate`, {
    method: "POST",
  });
  return parseResponse<ProjectState>(response);
}

export async function saveArtifact(projectId: string, artifactType: ArtifactType, content: any): Promise<ProjectState> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/artifacts/${artifactType}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  return parseResponse<ProjectState>(response);
}

export async function requestStoryAssist(payload: {
  story_text: string;
  focus: string;
  context?: string;
}): Promise<{
  summary: string;
  questions: string[];
  recommendations: string[];
  revised_text: string;
}> {
  const response = await fetch(`${API_BASE}/story/assist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function listWorkflows(): Promise<WorkflowManifest[]> {
  const response = await fetch(`${API_BASE}/workflows`);
  return parseResponse<WorkflowManifest[]>(response);
}

export async function fetchAudioCapabilities(): Promise<AudioCapabilities> {
  const response = await fetch(`${API_BASE}/audio/capabilities`);
  return parseResponse<AudioCapabilities>(response);
}

export async function listAudioVoices(): Promise<AudioVoice[]> {
  const response = await fetch(`${API_BASE}/audio/voices`);
  return parseResponse<AudioVoice[]>(response);
}

export async function listAudioModels(): Promise<AudioModel[]> {
  const response = await fetch(`${API_BASE}/audio/models`);
  return parseResponse<AudioModel[]>(response);
}

export async function addReferenceVoice(payload: { name: string; transcript: string; file: File }): Promise<VoiceInstallResult> {
  const form = new FormData();
  form.append("name", payload.name);
  form.append("transcript", payload.transcript);
  form.append("file", payload.file);
  const response = await fetch(`${API_BASE}/audio/voices`, { method: "POST", body: form });
  return parseResponse(response);
}

export async function refreshAudioVoices(expectedVoiceId?: string): Promise<VoiceRefreshResult> {
  const response = await fetch(`${API_BASE}/audio/voices/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_voice_id: expectedVoiceId || null }),
  });
  return parseResponse(response);
}

export async function getF5Preflight(): Promise<F5Preflight> {
  return parseResponse(await fetch(`${API_BASE}/audio/finetune/f5/preflight`));
}

export async function createF5PrepareJob(projectId: string, payload: { datasetName: string; baseModel: string; metadata: File; audioFiles: File[] }): Promise<F5PrepareJob> {
  const form = new FormData();
  form.append("dataset_name", payload.datasetName);
  form.append("base_model", payload.baseModel);
  form.append("metadata", payload.metadata);
  payload.audioFiles.forEach((file) => form.append("audio_files", file));
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/finetune/f5/prepare`, { method: "POST", body: form }));
}

export async function getF5PrepareJob(projectId: string, jobId: string): Promise<F5PrepareJob> {
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/finetune/f5/jobs/${jobId}`));
}

export async function listRVCModels(): Promise<RVCCatalogModel[]> {
  return parseResponse(await fetch(`${API_BASE}/audio/rvc/models`));
}

export async function createAudioEffectJob(projectId: string, operation: AudioEffectOperation, settings: Record<string, unknown>, source?: File): Promise<AudioEffectJob> {
  const form = new FormData(); form.append("payload", JSON.stringify(settings)); if (source) form.append("source", source);
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/effects/${operation}`, { method: "POST", body: form }));
}

export async function getAudioEffectJob(projectId: string, jobId: string): Promise<AudioEffectJob> {
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/effects/jobs/${jobId}`));
}

export async function listAudioEffectJobs(projectId: string): Promise<AudioEffectJob[]> {
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/effects/jobs`));
}

export async function getMusicCapabilities(): Promise<MusicCapabilities> { return parseResponse(await fetch(`${API_BASE}/music/capabilities`)); }
export async function createAceMusicJob(projectId: string, settings: Record<string, unknown>): Promise<MusicJob> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/music/ace/jobs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settings) })); }
export async function getMusicJob(projectId: string, jobId: string): Promise<MusicJob> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/music/jobs/${jobId}`)); }
export async function listMusicJobs(projectId: string): Promise<MusicJob[]> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/music/jobs`)); }
export async function getControlFoleyCapabilities(): Promise<ControlFoleyCapabilities> { return parseResponse(await fetch(`${API_BASE}/music/control-foley/capabilities`)); }
export async function createControlFoleyJob(projectId: string, settings: Record<string, unknown>, video?: File | null, referenceAudio?: File | null): Promise<ControlFoleyJob> { const form = new FormData(); form.append("payload", JSON.stringify(settings)); if (video) form.append("video", video); if (referenceAudio) form.append("reference_audio", referenceAudio); return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/music/control-foley/jobs`, { method: "POST", body: form })); }
export async function getControlFoleyJob(projectId: string, jobId: string): Promise<ControlFoleyJob> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/music/control-foley/jobs/${jobId}`)); }
export async function listAutomationBlocks(): Promise<AutomationBlock[]> { return parseResponse(await fetch(`${API_BASE}/automation/blocks`)); }
export async function listAudioPipelines(projectId: string): Promise<AudioPipeline[]> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/automation/pipelines`)); }
export async function createAudioPipeline(projectId: string, payload: Record<string, unknown>): Promise<AudioPipeline> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/automation/pipelines`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })); }
export async function validateAudioPipeline(projectId: string, pipelineId: string): Promise<AudioPipeline> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/automation/pipelines/${pipelineId}/validate`, { method: "POST" })); }
export async function startAudioPipeline(projectId: string, pipelineId: string): Promise<AutomationRun> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/automation/pipelines/${pipelineId}/runs`, { method: "POST" })); }
export async function getAutomationRun(projectId: string, runId: string): Promise<AutomationRun> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/automation/runs/${runId}`)); }
export async function retryAutomationStep(projectId: string, runId: string, stepId: string): Promise<AutomationRun> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/automation/runs/${runId}/steps/${stepId}/retry`, { method: "POST" })); }
export async function listAudioLibraryAssets(): Promise<AudioLibraryAsset[]> { return parseResponse(await fetch(`${API_BASE}/audio-library/assets`)); }
export async function addAudioLibraryAsset(file: File, relativePath = "", tags = "", notes = ""): Promise<AudioLibraryAsset> { const form = new FormData(); form.append("file", file); form.append("relative_path", relativePath); form.append("tags", tags); form.append("notes", notes); return parseResponse(await fetch(`${API_BASE}/audio-library/assets`, { method: "POST", body: form })); }
export async function removeAudioLibraryAsset(assetId: string): Promise<void> { const response = await fetch(`${API_BASE}/audio-library/assets/${assetId}`, { method: "DELETE" }); if (!response.ok) await parseResponse(response); }
export function getAudioLibraryFileUrl(assetId: string): string { return `${API_BASE}/audio-library/files/${assetId}`; }
export async function getAudioUtilityCapabilities(): Promise<AudioUtilityCapabilities> { return parseResponse(await fetch(`${API_BASE}/audio/utilities/capabilities`)); }
export async function createAudioUtilityJob(projectId: string, operation: string, settings: Record<string, unknown>, files: File[]): Promise<AudioUtilityJob> { const form = new FormData(); form.append("payload", JSON.stringify(settings)); files.forEach((file) => { form.append("files", file); form.append("relative_paths", file.webkitRelativePath || file.name); }); return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/utilities/${operation}/jobs`, { method: "POST", body: form })); }
export async function getAudioUtilityJob(projectId: string, jobId: string): Promise<AudioUtilityJob> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/utilities/jobs/${jobId}`)); }
export async function listAudioUtilityJobs(projectId: string): Promise<AudioUtilityJob[]> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/utilities/jobs`)); }

export interface CharacterAssignment {
  name: string;
  language: string;
  reference_voice_id: string;
}

export interface TimedTTSSettings {
  srt_content: string;
  language: string;
  seed: number;
  timing_mode: "stretch_to_fit" | "pad_with_silence" | "smart_natural" | "concatenate";
  exaggeration: number;
  temperature: number;
  cfg_weight: number;
  enable_audio_cache: boolean;
  fade: number;
  max_stretch_ratio: number;
  min_stretch_ratio: number;
  timing_tolerance: number;
  batch_size: number;
}

export interface TimedTTSJob {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: string;
  started_at?: string;
  completed_at?: string;
  prompt_id?: string;
  outputs: Array<{ kind: string; relative_path: string; filename: string }>;
  reports?: Record<string, string>;
  export_path?: string;
  error?: string | null;
}

export interface SceneClip { clip_index: number; start: number; end: number; duration: number; kind: string; text: string; split_file: string; relative_path: string }
export interface AudioSceneJob {
  job_id: string; kind: "split" | "stitch"; status: "queued" | "running" | "completed" | "failed";
  parent_job_id?: string; manifest?: { clips: SceneClip[]; duration: number; sample_rate: number };
  manifest_path?: string; enriched_path?: string; output_path?: string; error?: string | null;
}

export async function getCharacterMap(projectId: string): Promise<{ version: number; characters: CharacterAssignment[] }> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/audio/character-map`);
  return parseResponse(response);
}

export async function saveCharacterMap(projectId: string, characters: CharacterAssignment[]): Promise<{ version: number; characters: CharacterAssignment[] }> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/audio/character-map`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version: 1, characters }),
  });
  return parseResponse(response);
}

export async function createTimedTTSJob(projectId: string, payload: TimedTTSSettings): Promise<TimedTTSJob> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/audio/tts/timed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function getTimedTTSJob(projectId: string, jobId: string): Promise<TimedTTSJob> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/audio/tts/jobs/${jobId}`);
  return parseResponse(response);
}

export async function listTimedTTSJobs(projectId: string): Promise<TimedTTSJob[]> {
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/tts/jobs`));
}

export async function createSceneSplit(projectId: string, payload: Record<string, unknown>, audio?: File): Promise<AudioSceneJob> {
  const form = new FormData(); form.append("payload", JSON.stringify(payload)); if (audio) form.append("audio", audio);
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/scenes/split`, { method: "POST", body: form }));
}

export async function createSceneStitch(projectId: string, splitJobId: string, payload: Record<string, unknown>, files: File[]): Promise<AudioSceneJob> {
  const form = new FormData(); form.append("payload", JSON.stringify(payload)); files.forEach((file) => form.append("files", file));
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/scenes/${splitJobId}/stitch`, { method: "POST", body: form }));
}

export async function getSceneJob(projectId: string, jobId: string): Promise<AudioSceneJob> {
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/scenes/jobs/${jobId}`));
}

export async function listSceneJobs(projectId: string): Promise<AudioSceneJob[]> {
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/scenes/jobs`));
}

export async function createMediaJob(
  projectId: string,
  payload: Record<string, any>,
  files: File[]
): Promise<{ project: ProjectState; job: any }> {
  const form = new FormData();
  form.append("payload", JSON.stringify(payload));
  for (const file of files) {
    form.append("files", file);
  }
  const response = await fetch(`${API_BASE}/projects/${projectId}/media/jobs`, {
    method: "POST",
    body: form,
  });
  return parseResponse(response);
}

export async function listMediaJobs(projectId: string): Promise<any[]> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/media/jobs`);
  return parseResponse<any[]>(response);
}

export async function getReconstructionSession(projectId: string): Promise<ReconstructionSession> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/reconstruct`)); }
export async function saveReconstructionCalibration(projectId: string, payload: { character_name: string; sentence: string; settings?: Record<string, unknown> }): Promise<ReconstructionSession> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/reconstruct/calibration`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })); }
export async function createReconstructionPart(projectId: string, payload: { part_id: string; character_name: string; sequence: number; expected_text: string }): Promise<ReconstructionPart> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/reconstruct/parts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })); }
export async function uploadReconstructionTake(projectId: string, partId: string, recording: File, transcript = ""): Promise<ReconstructionTake> { const form = new FormData(); form.append("recording", recording); form.append("transcript", transcript); return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/reconstruct/parts/${encodeURIComponent(partId)}/takes`, { method: "POST", body: form })); }
export async function acceptReconstructionTake(projectId: string, partId: string, takeId: string): Promise<{ part: ReconstructionPart; take: ReconstructionTake; session: ReconstructionSession }> { return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/audio/reconstruct/parts/${encodeURIComponent(partId)}/accept/${encodeURIComponent(takeId)}`, { method: "POST" })); }

export function getProjectFileUrl(projectId: string, relativePath: string): string {
  return `${API_BASE}/projects/${projectId}/files/${relativePath}`;
}

export function getSupervisorUrl(projectId?: string | null): string {
  if (typeof window === "undefined") {
    return "http://127.0.0.1:3009/";
  }
  const url = new URL(window.location.href);
  url.port = "3009";
  url.pathname = "/";
  url.search = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  url.hash = "";
  return url.toString();
}

export async function fetchVideoRepertoireCapabilities(): Promise<VideoRepertoireCapabilities> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/capabilities`));
}
export async function listVideoAssets(): Promise<VideoAsset[]> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/assets`));
}
export async function deleteVideoAssets(assetIds: string[]): Promise<{ deleted: string[] }> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/assets`, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ asset_ids: assetIds }) }));
}
export async function importLegacyVideoAssets(): Promise<VideoAsset[]> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/assets/import-legacy`, { method: "POST" }));
}
export async function uploadVideoAsset(file: File, provenanceNotes = ""): Promise<VideoAsset> {
  const form = new FormData(); form.append("file", file); form.append("provenance_notes", provenanceNotes);
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/assets/upload`, { method: "POST", body: form }));
}
export async function resolveVideoSources(payload: { mode: string; query?: string; count?: number; urls_text?: string }): Promise<ResolvedVideoSource> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/youtube/resolve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function createVideoDownloadJob(payload: Record<string, unknown>): Promise<VideoJob> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/youtube/jobs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function listVideoDownloadJobs(): Promise<VideoJob[]> { return parseResponse(await fetch(`${API_BASE}/video-repertoire/youtube/jobs`)); }
export async function listVideoAnalysisJobs(): Promise<VideoJob[]> { return parseResponse(await fetch(`${API_BASE}/video-repertoire/analysis/jobs`)); }
export async function createVideoAnalysisJob(payload: Record<string, unknown>): Promise<VideoJob> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/analysis/jobs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function cancelVideoJob(kind: "youtube" | "analysis", jobId: string): Promise<VideoJob> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/${kind === "youtube" ? "youtube" : "analysis"}/jobs/${jobId}/cancel`, { method: "POST" }));
}
export async function stopVideoAnalysisJob(jobId: string): Promise<{ job_id: string; status: string; deleted: boolean }> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/analysis/jobs/${jobId}/stop`, { method: "POST" }));
}
export async function deleteVideoAnalysisJob(jobId: string): Promise<{ job_id: string; status: string; deleted: boolean }> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/analysis/jobs/${jobId}`, { method: "DELETE" }));
}
export async function retryVideoJob(kind: "youtube" | "analysis", jobId: string): Promise<VideoJob> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/${kind === "youtube" ? "youtube" : "analysis"}/jobs/${jobId}/retry`, { method: "POST" }));
}
export async function searchVideoRepertoire(query: string): Promise<VideoSearchResult[]> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/search?q=${encodeURIComponent(query)}`));
}
export async function searchVideoAudioCorpus(payload: { query: string; top_n: number; mode: "semantic" | "keyword" | "hybrid"; offset?: number }): Promise<VideoAudioCorpusSearch> {
  return parseResponse(await fetch(`${API_BASE}/video-audio-analyzer/search`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }));
}

export interface VideoReferenceResult {
  clip_id: string;
  asset_id: string;
  summary: string;
  source_video: string;
  scene_id: string;
  subscene_id: string;
  cut_id: string;
  start_time_sec: number;
  end_time_sec?: number | null;
  duration_sec?: number | null;
  match_score: number;
  match_reason: string;
  thumbnail_path?: string | null;
  frame_cards?: string[];
  provenance?: { license_status?: string; [key: string]: unknown };
}
export interface SeoStyle { style_id: string; name: string; terms: string[]; avoid_terms: string[]; weights: Record<string, number>; }
export async function searchVideoReferences(payload: Record<string, unknown>): Promise<{ search_id: string; results: VideoReferenceResult[]; has_more: boolean; next_exclude_clip_ids: string[] }> {
  return parseResponse(await fetch(`${API_BASE}/video-references/search`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function nextVideoReferencePage(searchId: string, topN: number): Promise<{ search_id: string; results: VideoReferenceResult[]; has_more: boolean }> {
  return parseResponse(await fetch(`${API_BASE}/video-references/search/${encodeURIComponent(searchId)}/next?top_n=${topN}`));
}
export async function listSeoStyles(): Promise<SeoStyle[]> { return parseResponse(await fetch(`${API_BASE}/video-references/seo-styles`)); }
export async function createSeoStyle(payload: Omit<SeoStyle, "style_id">): Promise<SeoStyle> {
  return parseResponse(await fetch(`${API_BASE}/video-references/seo-styles`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export function getVideoReferenceContentUrl(clipId: string): string { return `${API_BASE}/video-references/clips/${encodeURIComponent(clipId)}/content`; }
export function getVideoReferenceThumbnailUrl(clipId: string): string { return `${API_BASE}/video-references/clips/${encodeURIComponent(clipId)}/thumbnail`; }
export async function selectVideoReferences(projectId: string, clips: VideoReferenceResult[]): Promise<Record<string, unknown>> {
  return parseResponse(await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/video-references/select`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clips }) }));
}
export function getVideoAssetUrl(assetId: string): string { return `${API_BASE}/video-repertoire/assets/${encodeURIComponent(assetId)}/content`; }
export function getVideoArtifactUrl(relativePath: string): string {
  return `${API_BASE}/video-repertoire/artifacts/${relativePath.split("/").map(encodeURIComponent).join("/")}`;
}
export type VideoRepertoireAudioAsset = {
  asset_id: string;
  category: "voices" | "music" | "sfx" | "ambience" | "isolated";
  filename: string;
  label?: string | null;
  start_time_sec?: number | null;
  end_time_sec?: number | null;
  confidence?: number | null;
  source_video_id?: string | null;
  project_id?: string | null;
  relative_path: string;
  content_url: string;
  size?: number;
  available?: boolean;
  sha256?: string | null;
  duplicate?: boolean;
  duplicate_group_id?: string;
  duplicate_group_size?: number;
  duplicate_basis?: string;
  classification_duplicate_candidate?: boolean;
  classification_group_id?: string;
  classification_group_size?: number;
  classification_group_label?: string;
  isolation_status?: string;
  semantic_mood?: { method?: string; scores_are_calibrated_probabilities?: boolean; top_match?: string; candidates?: Array<{ label: string; similarity: number }> };
};
export type ManualDirectorSlot = "reference_images" | "first_frame" | "last_frame" | "audio" | "video";
export type ManualDirectorReference = {
  slot: ManualDirectorSlot; asset_id: string; filename?: string; relative_path?: string;
  media_type?: "image" | "audio" | "video"; start_time_sec?: number | null; end_time_sec?: number | null;
  content_url?: string;
};

const MANUAL_DIRECTOR_SELECTION_KEY = "story_builder.manual_director.selection";
/** Stage repertoire references for the Manual Director without copying bytes. */
export function queueManualDirectorReferences(references: ManualDirectorReference[]): number {
  if (typeof window === "undefined") return 0;
  let existing: ManualDirectorReference[] = [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(MANUAL_DIRECTOR_SELECTION_KEY) || "[]");
    if (Array.isArray(parsed)) existing = parsed;
  } catch { /* recover from a malformed stale selection */ }
  const key = (row: ManualDirectorReference) => [row.slot, row.asset_id, row.relative_path || "", row.start_time_sec ?? "", row.end_time_sec ?? ""].join("|");
  const unique = new Map(existing.map((row) => [key(row), row]));
  for (const row of references) unique.set(key(row), row);
  const rows = [...unique.values()];
  window.localStorage.setItem(MANUAL_DIRECTOR_SELECTION_KEY, JSON.stringify(rows));
  return rows.length;
}
export type ManualDirectorWorkflow = {
  workflow_id: string; label: string; available: boolean; file: string; accepted_slots: ManualDirectorSlot[];
  required_slots: ManualDirectorSlot[]; fps: number; description: string;
  reference_limits: Record<string, { min: number; max: number; max_bytes_each: number }>;
  parameters: Array<{ key: string; label: string; kind: "number"; default: number; min: number; max: number; step: number; description?: string }>;
};
export type ManualDirectorAsset = {
  asset_id: string; filename: string; relative_path: string; media_type: "image" | "audio" | "video";
  size: number; sha256: string; content_url: string;
};
export type ManualDirectorJob = {
  run_id: string; status: string; stage: string; progress: number; message: string;
  prompt_id?: string; error?: string | null; outputs: Array<{ kind: string; relative_path: string; filename: string; content_url: string }>;
  created_at: string; updated_at: string;
};
export async function listManualDirectorWorkflows(): Promise<ManualDirectorWorkflow[]> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/manual/workflows`));
}
export async function listManualDirectorAssets(): Promise<ManualDirectorAsset[]> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/manual/assets`));
}
export async function uploadManualDirectorAsset(file: File, slot: ManualDirectorSlot): Promise<ManualDirectorAsset> {
  const form = new FormData(); form.append("file", file); form.append("slot", slot);
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/manual/assets`, { method: "POST", body: form }));
}
export async function createManualDirectorJob(payload: { workflow_id: string; prompt: string; negative_prompt?: string; parameters: Record<string, number>; references: ManualDirectorReference[] }): Promise<ManualDirectorJob> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/manual/jobs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function listManualDirectorJobs(): Promise<ManualDirectorJob[]> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/manual/jobs`));
}
export async function getManualDirectorJob(runId: string): Promise<ManualDirectorJob> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/manual/jobs/${encodeURIComponent(runId)}`));
}
export async function deleteManualDirectorJob(runId: string): Promise<{ deleted: string; source_references_preserved: boolean }> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/manual/jobs/${encodeURIComponent(runId)}`, { method: "DELETE" }));
}
export function getManualDirectorAssetUrl(relativePath: string): string {
  return `${API_BASE}/video-repertoire/manual/assets/content/${relativePath.split("/").map(encodeURIComponent).join("/")}`;
}
export function getManualDirectorOutputUrl(runId: string, filename: string): string {
  return `${API_BASE}/video-repertoire/manual/files/${encodeURIComponent(runId)}/${encodeURIComponent(filename)}`;
}
export async function listVideoRepertoireAudioAssets(category = "all"): Promise<VideoRepertoireAudioAsset[]> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/audio-assets?category=${encodeURIComponent(category)}`));
}
export async function deleteVideoRepertoireAudioAssets(relativePaths: string[], confirmed: boolean): Promise<{ deleted: string[]; failures: Array<{ relative_path: string; error: string }>; reclaimed_bytes: number; occurrence_metadata_preserved: boolean; source_media_preserved: boolean }> {
  return parseResponse(await fetch(`${API_BASE}/video-repertoire/audio-assets`, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ relative_paths: relativePaths, confirmed }) }));
}
export function getVideoRepertoireAudioAssetUrl(relativePath: string): string {
  return `${API_BASE}/video-repertoire/audio-assets/content/${relativePath.split("/").map(encodeURIComponent).join("/")}`;
}
export function getVideoAudioAnalyzerArtifactUrl(runId: string, relativePath: string): string {
  return `${API_BASE}/video-audio-analyzer/runs/${encodeURIComponent(runId)}/artifacts/${relativePath.split("/").map(encodeURIComponent).join("/")}`;
}
export async function isolateVideoAudioEvent(runId: string, eventId: string, prompt: string): Promise<Record<string, unknown>> {
  return parseResponse(await fetch(`${API_BASE}/video-audio-analyzer/runs/${encodeURIComponent(runId)}/sam/isolate`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ event_id: eventId, prompt }),
  }));
}
export function getVideoAudioSamPreviewUrl(temporaryId: string): string {
  return `${API_BASE}/video-audio-analyzer/sam/previews/${encodeURIComponent(temporaryId)}/audio`;
}
export async function reviewVideoAudioSamPreview(temporaryId: string): Promise<Record<string, unknown>> {
  return parseResponse(await fetch(`${API_BASE}/video-audio-analyzer/sam/previews/${encodeURIComponent(temporaryId)}/director-review`, { method: "POST" }));
}
export async function discardVideoAudioSamPreview(temporaryId: string): Promise<Record<string, unknown>> {
  return parseResponse(await fetch(`${API_BASE}/video-audio-analyzer/sam/previews/${encodeURIComponent(temporaryId)}`, { method: "DELETE" }));
}

export async function createCanvasRevision(projectId: string, payload: { content: string; parent_revision_id?: string | null; narrator: boolean }): Promise<StoryRevision> {
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/canvas/revisions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function listCanvasRevisions(projectId: string): Promise<StoryRevision[]> {
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/canvas/revisions`));
}
export async function createCanvasAnalysis(projectId: string, payload: { revision_id?: string; content?: string }): Promise<StoryRevision> {
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/canvas/analysis`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
export async function createCanvasOutline(projectId: string, payload: { revision_id: string; narrator: boolean }): Promise<StoryRevision> {
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/canvas/outline`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}

export async function finalizeProjectOutput(projectId: string): Promise<Record<string, unknown>> {
  return parseResponse(await fetch(`${API_BASE}/projects/${projectId}/output/finalize`, { method: "POST" }));
}
