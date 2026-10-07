import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Loader2, Link2, Play, Save, Search, Sparkles, Upload } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/AppShell";
import { ProductionStylePicker } from "@/components/ProductionStylePicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { productionTakeNeedsPolling } from "@/lib/production-v2-status";
import {
  acceptProductionV2Story, acceptProductionV2Text, createProductionV2Run, createProductionV2StoryDetail, createProductionV2ManualStorySource, saveProductionV2ManualStory,
  acceptProductionV2Refine, createProductionV2TextStage, proposeProductionV2Refine,
  ProductionStageRecoveryRequiredError, resolveProductionStageTaskWithoutResult,
  listProductionV2StoryRevisions, listProductionV2TextRevisions,
  createProject, fetchProject, listProjects, updateProjectDraft, createProductionAudioSidecar, createProductionDialogueTTS, getProductionAudioSidecarJob,
  acceptProductionTake, bindProductionVoice, cancelProductionTake, createProductionCharacter, createProductionWorld, createProductionVoiceExcerpt, getProductionCanon,
  assignProductionMasterIdentity, getProductionVoiceBindings, listProductionAssets, saveProductionCanon, uploadProductionAsset,
  queueProductionImageJob, getProductionImageJobBatch, isProductionImageBatchSettled, listProductionImageWorkflows, type ProductionImageJob, type ProductionImageJobBatch,
  acceptProductionImageCandidate,
  uploadProductionDialogueTake, listRVCModels, convertProductionDialogueTake,
  linkProductionRepertoireAsset, listVideoAssets, listVideoRepertoireAudioAssets, getProductionShotDraft, saveProductionShotDraft,
  fetchProductionV2Run, listProductionV2Runs, queueProductionShot, retryProductionTake, reconcileAbsentProductionTake, saveProductionV2ManualText, validateProductionShot,
  prepareProductionShotPrompt, getProductionShotPromptPreparation,
  type ProjectState, type ProductionAsset, type ProductionCanon, type ProductionV2Run, type ProductionV2StoryRevision, type VideoAsset, type VideoRepertoireAudioAsset,
} from "@/lib/project-api";

const ACTIVE_PROJECT = "story-builder.production.project";
const ACTIVE_RUN = "story-builder.production.run";

function flattenImageJobs(jobs: ProductionImageJob[]): ProductionImageJob[] {
  return jobs.flatMap((job) => [job, ...flattenImageJobs(job.director_review?.retake_jobs || [])]);
}

function DirectorVideoReviewSummary({ review }: { review: any }) {
  if (!review) return null;
  const decision = review.decision;
  const status = String(review.resolution_status || "pending").replaceAll("_", " ");
  return <section aria-label="Director video review" className="rounded border bg-muted/30 p-3 text-sm">
    <p className="font-medium">Director review: {status}</p>
    {decision?.reason || review.error?.message ? <p className="mt-1 text-muted-foreground">{decision?.reason || review.error.message}</p> : null}
    {review.retake_preparation ? <p className="mt-1 text-muted-foreground">Fresh retake prompt preparation: {String(review.retake_preparation.status).replaceAll("_", " ")}.</p> : null}
    {decision?.criteria?.length ? <ul className="mt-2 list-disc pl-5">{decision.criteria.slice(0, 5).map((item: any, index: number) =>
      <li key={`${item.name}-${index}`}>{item.name}: {item.passed ? "passed" : "not passed"}{item.evidence ? ` — ${item.evidence}` : ""}</li>)}</ul> : null}
    {review.retake_take_id ? <p className="mt-1 text-muted-foreground">Retake queued: {review.retake_take_id}</p> : null}
  </section>;
}

export default function ProductionWorkspace() {
  const [projects, setProjects] = useState<ProjectState[]>([]);
  const [existingRuns, setExistingRuns] = useState<ProductionV2Run[]>([]);
  const [project, setProject] = useState<ProjectState | null>(null);
  const [title, setTitle] = useState("");
  const [story, setStory] = useState("");
  const [controlMode, setControlMode] = useState("manual");
  const [makingRoute, setMakingRoute] = useState("direct_h3");
  const [productionType, setProductionType] = useState("story_film");
  const [narrativeVariantId, setNarrativeVariantId] = useState("");
  const [semiGates, setSemiGates] = useState({ story_review: true, image_candidate_selection: true, voice_selection: true, shot_workflow_render_approval: true });
  const [run, setRun] = useState<ProductionV2Run | null>(null);
  const [canon, setCanon] = useState<ProductionCanon | null>(null);
  const [canonText, setCanonText] = useState("");
  const [characterName, setCharacterName] = useState("");
  const [worldName, setWorldName] = useState("");
  const [masterIdentities, setMasterIdentities] = useState<Record<string, string>>({});
  const [assets, setAssets] = useState<ProductionAsset[]>([]);
  const [imageWorkflowId, setImageWorkflowId] = useState("z_image_turbo");
  const [imageAssetRole, setImageAssetRole] = useState("character_master");
  const [imageEntityId, setImageEntityId] = useState("");
  const [imagePrompt, setImagePrompt] = useState("");
  const [imageWidth, setImageWidth] = useState(1280);
  const [imageHeight, setImageHeight] = useState(720);
  const [imageSteps, setImageSteps] = useState(8);
  const [editSourceAssetIds, setEditSourceAssetIds] = useState<string[]>([]);
  const [imageBatch, setImageBatch] = useState<ProductionImageJobBatch | null>(null);
  const [imageWorkflowReadiness, setImageWorkflowReadiness] = useState<Array<{ workflow_id: string; label: string; available: boolean; disabled_reason?: string | null }> | null>(null);
  const [assetRole, setAssetRole] = useState("character_master");
  const [assetFile, setAssetFile] = useState<File | null>(null);
  const [repertoireVideos, setRepertoireVideos] = useState<VideoAsset[]>([]);
  const [repertoireAudios, setRepertoireAudios] = useState<VideoRepertoireAudioAsset[]>([]);
  const [repertoireQuery, setRepertoireQuery] = useState("");
  const [repertoireKind, setRepertoireKind] = useState<"video" | "audio">("video");
  const [repertoireAssetId, setRepertoireAssetId] = useState("");
  const [repertoireLoaded, setRepertoireLoaded] = useState(false);
  const [voiceBindings, setVoiceBindings] = useState<Array<Record<string, any>>>([]);
  const [voiceCharacterId, setVoiceCharacterId] = useState("");
  const [voiceAssetId, setVoiceAssetId] = useState("");
  const [voiceExcerptStart, setVoiceExcerptStart] = useState(0);
  const [voiceExcerptDuration, setVoiceExcerptDuration] = useState(5);
  const [dialogueTakeFile, setDialogueTakeFile] = useState<File | null>(null);
  const [dialogueTranscript, setDialogueTranscript] = useState("");
  const [localRvcModels, setLocalRvcModels] = useState<Array<{ id: string; name: string }>>([]);
  const [selectedRvcModel, setSelectedRvcModel] = useState("");
  const [dialogueConversionJob, setDialogueConversionJob] = useState<any>(null);
  const dialogueConversionRequest = useRef<{ signature: string; key: string } | null>(null);
  const [dialogueTtsSpeakerOne, setDialogueTtsSpeakerOne] = useState("");
  const [dialogueTtsSpeakerTwo, setDialogueTtsSpeakerTwo] = useState("");
  const [dialogueTtsTextOne, setDialogueTtsTextOne] = useState("");
  const [dialogueTtsTextTwo, setDialogueTtsTextTwo] = useState("");
  const [dialogueTtsCueSeconds, setDialogueTtsCueSeconds] = useState(4);
  const [dialogueTtsJob, setDialogueTtsJob] = useState<any>(null);
  const dialogueTtsRequest = useRef<{ signature: string; key: string } | null>(null);
  const [sidecarKind, setSidecarKind] = useState<"music" | "sfx">("music");
  const [sidecarPrompt, setSidecarPrompt] = useState("");
  const [sidecarDuration, setSidecarDuration] = useState(8);
  const [sidecarStart, setSidecarStart] = useState(0);
  const [sidecarJob, setSidecarJob] = useState<any>(null);
  const sidecarRequest = useRef<{ signature: string; key: string } | null>(null);
  const [composerShotId, setComposerShotId] = useState("");
  const [composerParentTakeId, setComposerParentTakeId] = useState("");
  const [composerPrompt, setComposerPrompt] = useState("");
  const [composerDuration, setComposerDuration] = useState(5);
  const [composerResolutionPreset, setComposerResolutionPreset] = useState(0.98);
  const [composerSteps, setComposerSteps] = useState(20);
  const [composerDraftRevision, setComposerDraftRevision] = useState(0);
  const [composerDraftStale, setComposerDraftStale] = useState(false);
  const [composerDraftError, setComposerDraftError] = useState("");
  const [selectedImageIds, setSelectedImageIds] = useState<string[]>([]);
  const [selectedVideoIds, setSelectedVideoIds] = useState<string[]>([]);
  const [selectedAudioIds, setSelectedAudioIds] = useState<string[]>([]);
  const [pairVideoAudio, setPairVideoAudio] = useState(false);
  const [referenceIntents, setReferenceIntents] = useState<Record<string, string>>({});
  const [videoIntervals, setVideoIntervals] = useState<Record<string, { start_sec: number; end_sec: number }>>({});
  const [audioSpeakerIds, setAudioSpeakerIds] = useState<Record<string, string>>({});
  const [shotPreview, setShotPreview] = useState<any>(null);
  const [shotPreviewRequest, setShotPreviewRequest] = useState<any>(null);
  const [shotPromptPreparation, setShotPromptPreparation] = useState<any>(null);
  const [preparedPromptDraft, setPreparedPromptDraft] = useState("");
  const [preparedPromptEdited, setPreparedPromptEdited] = useState(false);
  const [shotIdempotencyKey, setShotIdempotencyKey] = useState("");
  const [selectedTake, setSelectedTake] = useState<any>(null);
  const [revision, setRevision] = useState<ProductionV2StoryRevision | null>(null);
  const [storyCanonDraft, setStoryCanonDraft] = useState("");
  const [textStage, setTextStage] = useState("scenes");
  const [workspaceStage, setWorkspaceStage] = useState("story");
  const [textStageDirty, setTextStageDirty] = useState(false);
  const [textUnits, setTextUnits] = useState('[\n  {\n    "unit_id": "scene-001",\n    "source_chunk_ids": ["story_chunk_0001"],\n    "source": "Draft this scene using the accepted story facts.",\n    "content": {\n      "title": "Opening scene"\n    }\n  }\n]');
  const [unitTitle, setUnitTitle] = useState("");
  const [unitDescription, setUnitDescription] = useState("");
  const [unitSpeaker, setUnitSpeaker] = useState("");
  const [unitDialogue, setUnitDialogue] = useState("");
  const [unitSceneId, setUnitSceneId] = useState("");
  const [unitSourceChunks, setUnitSourceChunks] = useState("");
  const [textRevision, setTextRevision] = useState<any>(null);
  const [refineInstruction, setRefineInstruction] = useState("");
  const [refineProposal, setRefineProposal] = useState<any>(null);
  const [refineShotId, setRefineShotId] = useState("");
  const [busy, setBusy] = useState("");
  const [stageTasks, setStageTasks] = useState<ProductionV2Run["stage_tasks"]>([]);
  const automaticStoryStart = useRef<string | null>(null);

  useEffect(() => {
    listProjects().then(async (items) => {
      setProjects(items);
      const savedId = localStorage.getItem(ACTIVE_PROJECT);
      const selected = items.find((item) => item.id === savedId) || null;
      if (selected) {
        setProject(selected); setTitle(selected.title); setStory(selected.story_input);
        const availableRuns = await listProductionV2Runs(selected.id);
        setExistingRuns(availableRuns);
        const savedRun = localStorage.getItem(ACTIVE_RUN);
        if (savedRun && availableRuns.some((row) => row.run_id === savedRun)) {
          try {
            const response = await fetch(`/api/projects/${encodeURIComponent(selected.id)}/production/v2/runs/${encodeURIComponent(savedRun)}`);
            if (response.ok) {
              const reopened: ProductionV2Run = await response.json();
              setRun(reopened);
              setStageTasks(reopened.stage_tasks || []);
              setControlMode(reopened.config.control_mode);
              setMakingRoute(reopened.config.making_route);
              setImageWorkflowId(reopened.config.image_workflow_id || "z_image_turbo");
              setProductionType(reopened.config.production_type);
              setNarrativeVariantId(reopened.config.narrative_style_variant_id || "");
              const savedWorkspaceStage = localStorage.getItem(`story-builder.production.workspace-stage.${savedRun}`);
              setWorkspaceStage(["story", "assets", "voice", "shots"].includes(savedWorkspaceStage || "") ? savedWorkspaceStage! : "story");
              setSemiGates({ story_review: true, image_candidate_selection: true, voice_selection: true, shot_workflow_render_approval: true, ...(reopened.config.semi_gates || {}) });
              const storyVersions = await listProductionV2StoryRevisions(selected.id, savedRun);
              const latestStory = [...storyVersions.revisions].sort((a, b) => String(b.accepted_at || b.created_at || "").localeCompare(String(a.accepted_at || a.created_at || "")))[0];
              if (latestStory) { setRevision(latestStory); setStoryCanonDraft(latestStory.expanded_story); }
              const savedStage = localStorage.getItem(`story-builder.production.stage.${savedRun}`);
              const stage = ["scenes", "dialogue", "visual_briefs", "shot_plans"].includes(savedStage || "") ? savedStage! : "scenes";
              setTextStage(stage);
              const stageVersions = await listProductionV2TextRevisions(selected.id, savedRun, stage);
              const latestText = [...stageVersions.revisions].sort((a, b) => String(b.accepted_at || b.created_at || "").localeCompare(String(a.accepted_at || a.created_at || "")))[0];
              if (latestText) {
                setTextRevision(latestText);
                setTextUnits(JSON.stringify(latestText.items || [], null, 2));
                if (stage === "shot_plans" && latestText.review_status === "accepted" && latestText.items?.length) {
                  const savedShot = latestText.items.find((item: any) => item.unit_id === localStorage.getItem(`story-builder.production.shot.${savedRun}`)) || latestText.items[0];
                  setComposerShotId(savedShot.unit_id);
                  setComposerPrompt(String(savedShot.content?.prompt || savedShot.content?.prompt_text || ""));
                  setComposerDuration(Number(savedShot.content?.duration_seconds || 5));
                }
              }
              const loadedCanon = await getProductionCanon(selected.id);
              setCanon(loadedCanon); setCanonText(JSON.stringify({ characters: loadedCanon.characters, worlds: loadedCanon.worlds }, null, 2));
              const assetResult = await listProductionAssets(selected.id);
              setAssets(assetResult.assets);
              const savedBindings = (await getProductionVoiceBindings(selected.id, savedRun)).bindings;
              setVoiceBindings(savedBindings);
              if (savedBindings[0]) { setVoiceCharacterId(savedBindings[0].character_id); setVoiceAssetId(savedBindings[0].voice_asset_id); }
            }
          } catch (error) { toast.error(error instanceof Error ? `Could not restore the saved production run: ${error.message}` : "Could not restore the saved production run."); }
        } else if (savedRun) localStorage.removeItem(ACTIVE_RUN);
      }
    }).catch((error) => toast.error(error instanceof Error ? error.message : "Could not load projects."));
  }, []);

  useEffect(() => {
    let disposed = false;
    listRVCModels().then((models) => {
      if (!disposed) {
        setLocalRvcModels(models);
        setSelectedRvcModel((current) => current || models[0]?.id || "");
      }
    }).catch(() => { if (!disposed) setLocalRvcModels([]); });
    return () => { disposed = true; };
  }, []);

  const taskPollProjectId = project?.id;
  const taskPollRunId = run?.run_id;
  const shouldPollStageTasks = Boolean(taskPollProjectId && taskPollRunId &&
    ((run?.config.control_mode || controlMode) === "fully_automated" ||
      ((run?.config.control_mode || controlMode) === "semi" && run?.config.semi_gates?.story_review === false)));
  useEffect(() => {
    if (!taskPollProjectId || !taskPollRunId || !shouldPollStageTasks) return;
    let disposed = false;
    const refreshTasks = async () => {
      try {
        const current = await fetchProductionV2Run(taskPollProjectId, taskPollRunId);
        if (!disposed) {
          setRun(current);
          setStageTasks(current.stage_tasks || []);
        }
      } catch { /* Keep the last persisted controller state visible on transient errors. */ }
    };
    void refreshTasks();
    const timer = window.setInterval(() => void refreshTasks(), 2000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [taskPollProjectId, taskPollRunId, shouldPollStageTasks]);

  useEffect(() => {
    if (!project || !run || !sidecarJob?.job_id || ["completed", "failed", "cancelled"].includes(sidecarJob.status)) return;
    let disposed = false;
    const poll = async () => {
      try {
        const current = await getProductionAudioSidecarJob(project.id, run.run_id, sidecarJob.job_id);
        if (disposed) return;
        setSidecarJob(current);
        if (current.status === "completed") setAssets((await listProductionAssets(project.id)).assets);
      } catch { /* Keep the last durable status visible while a transient poll fails. */ }
    };
    const timer = window.setInterval(() => void poll(), 2500);
    void poll();
    return () => { disposed = true; window.clearInterval(timer); };
  }, [project, run, sidecarJob?.job_id, sidecarJob?.status]);

  useEffect(() => {
    const jobId = dialogueTtsJob?.job_id;
    if (!project || !run || !jobId || ["completed", "failed", "cancelled"].includes(dialogueTtsJob.status)) return;
    let disposed = false;
    const poll = async () => {
      try {
        const latest = await getProductionAudioSidecarJob(project.id, run.run_id, jobId);
        if (disposed) return;
        setDialogueTtsJob(latest);
        if (["completed", "failed", "cancelled"].includes(latest.status)) dialogueTtsRequest.current = null;
        if (latest.status === "completed") setAssets((await listProductionAssets(project.id)).assets);
      } catch { /* Keep the last durable status visible while a transient poll fails. */ }
    };
    const timer = window.setInterval(() => void poll(), 2500);
    void poll();
    return () => { disposed = true; window.clearInterval(timer); };
  }, [project, run, dialogueTtsJob?.job_id, dialogueTtsJob?.status]);
  const canStart = useMemo(() => Boolean(project && story.trim() && !busy), [project, story, busy]);
  const filteredRepertoireVideos = useMemo(() => {
    const needle = repertoireQuery.trim().toLowerCase();
    return repertoireVideos.filter((item) => !needle || `${item.title} ${item.filename} ${item.channel}`.toLowerCase().includes(needle));
  }, [repertoireVideos, repertoireQuery]);
  const filteredRepertoireAudios = useMemo(() => {
    const needle = repertoireQuery.trim().toLowerCase();
    return repertoireAudios.filter((item) => item.available && (!needle || `${item.label || ""} ${item.filename} ${item.category}`.toLowerCase().includes(needle)));
  }, [repertoireAudios, repertoireQuery]);
  const boundDialogueVoices = useMemo(() => (canon?.characters || []).filter((character) => character.status === "active")
    .map((character) => {
      const binding = voiceBindings.find((row) => row.character_id === character.character_id && row.run_id === run?.run_id);
      const excerpt = binding && assets.find((asset) => asset.kind === "audio" && asset.roles.includes("voice_excerpt")
        && asset.metadata?.approval_status === "accepted" && asset.metadata?.run_id === run?.run_id
        && asset.metadata?.character_id === character.character_id
        && asset.metadata?.source_voice_asset_id === binding.voice_asset_id
        && Number(asset.media?.duration_seconds || 0) >= 2 && Number(asset.media?.duration_seconds || 0) <= 15);
      return binding && excerpt ? { character, binding, excerpt } : null;
    }).filter((row): row is NonNullable<typeof row> => row !== null), [canon, voiceBindings, assets, run]);
  useEffect(() => {
    const ids = boundDialogueVoices.map((row) => row.character.character_id);
    if (!ids.includes(dialogueTtsSpeakerOne)) setDialogueTtsSpeakerOne(ids[0] || "");
    const first = ids.includes(dialogueTtsSpeakerOne) ? dialogueTtsSpeakerOne : ids[0];
    const secondOptions = ids.filter((id) => id !== first);
    if (!secondOptions.includes(dialogueTtsSpeakerTwo)) setDialogueTtsSpeakerTwo(secondOptions[0] || "");
  }, [boundDialogueVoices, dialogueTtsSpeakerOne, dialogueTtsSpeakerTwo]);
  const draftProjectId = project?.id;
  const draftRunId = run?.run_id;
  const composerPlanRevisionId = textRevision?.revision_id;
  const composerPlanStatus = textRevision?.review_status;
  const composerPlanItems = textRevision?.items;

  useEffect(() => {
    if (!draftProjectId || !draftRunId || !composerShotId || textStage !== "shot_plans" || composerPlanStatus !== "accepted" || !composerPlanRevisionId) return;
    let disposed = false;
    const item = (composerPlanItems || []).find((row: any) => row.unit_id === composerShotId);
    setComposerPrompt(String(item?.content?.prompt || item?.content?.prompt_text || ""));
    setComposerDuration(Number(item?.content?.duration_seconds || 5));
    setComposerSteps(20);
      setSelectedImageIds([]); setSelectedVideoIds([]); setSelectedAudioIds([]); setPairVideoAudio(false);
      setReferenceIntents({}); setVideoIntervals({}); setAudioSpeakerIds({});
    setComposerDraftRevision(0); setComposerDraftStale(false);
    getProductionShotDraft(draftProjectId, draftRunId, composerShotId).then((saved) => {
      if (disposed) return;
      setComposerDraftRevision(Number(saved.revision || 0));
      setComposerDraftStale(Boolean(saved.stale));
      if (!saved.draft || saved.stale) return;
      setComposerPrompt(String(saved.draft.prompt || ""));
      setComposerDuration(Number(saved.draft.duration_seconds || 5));
      setComposerSteps(Number(saved.draft.steps || 20));
      setSelectedImageIds((saved.draft.images || []).map((row: any) => row.asset_id));
      setSelectedVideoIds((saved.draft.videos || []).map((row: any) => row.asset_id));
      setSelectedAudioIds((saved.draft.standalone_audios || []).map((row: any) => row.asset_id));
      setPairVideoAudio(Boolean(saved.draft.videos?.length && saved.draft.videos.every((row: any) => row.include_paired_soundtrack)));
      const intents: Record<string, string> = {};
      for (const row of [...(saved.draft.images || []), ...(saved.draft.videos || []), ...(saved.draft.standalone_audios || [])]) intents[row.asset_id] = String(row.intent || "");
      const intervals: Record<string, { start_sec: number; end_sec: number }> = {};
      for (const row of (saved.draft.videos || [])) if (row.start_sec != null && row.end_sec != null) intervals[row.asset_id] = { start_sec: Number(row.start_sec), end_sec: Number(row.end_sec) };
      const speakers: Record<string, string> = {};
      for (const row of (saved.draft.standalone_audios || [])) if (row.speaker_id) speakers[row.asset_id] = String(row.speaker_id);
      setReferenceIntents(intents); setVideoIntervals(intervals); setAudioSpeakerIds(speakers);
    }).catch((error) => {
      if (!disposed) toast.error(error instanceof Error ? `Could not restore shot draft ${composerShotId}: ${error.message}` : `Could not restore shot draft ${composerShotId}.`);
    });
    return () => { disposed = true; };
  }, [draftProjectId, draftRunId, composerShotId, textStage, composerPlanRevisionId, composerPlanStatus, composerPlanItems]);
  const chooseProject = async (id: string) => {
    setBusy("load");
    try {
      const next = await fetchProject(id);
      setProject(next); setTitle(next.title); setStory(next.story_input); setRun(null); setStageTasks([]); automaticStoryStart.current = null; setRevision(null); setStoryCanonDraft(""); setCanon(null); setCanonText(""); setAssets([]); setVoiceBindings([]);
      setExistingRuns(await listProductionV2Runs(id));
      localStorage.setItem(ACTIVE_PROJECT, id); localStorage.removeItem(ACTIVE_RUN);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not open project."); }
    finally { setBusy(""); }
  };

  const selectSavedRun = (runId: string) => {
    if (!runId) {
      if (run && !window.confirm("Close this run in the workspace? Its saved data remains available, but unsaved edits will be lost.")) return;
      localStorage.removeItem(ACTIVE_RUN);
      setRun(null); setStageTasks([]); setSelectedTake(null); setRevision(null); setTextRevision(null);
      setWorkspaceStage("story");
      return;
    }
    if (!project || runId === run?.run_id) return;
    if (!window.confirm("Switching production runs reloads this workspace. Save unfinished text or shot edits first. Continue?")) return;
    localStorage.setItem(ACTIVE_PROJECT, project.id);
    localStorage.setItem(ACTIVE_RUN, runId);
    window.location.reload();
  };

  const saveDraft = async () => {
    if (!title.trim() || !story.trim()) { toast.error("A project title and story are required."); return; }
    setBusy("save");
    try {
      const next = project
        ? await updateProjectDraft({ projectId: project.id, title: title.trim(), story_input: story.trim(), automation_mode: false })
        : await createProject({ title: title.trim(), story_input: story.trim(), automation_mode: false });
      setProject(next); setProjects((current) => [next, ...current.filter((item) => item.id !== next.id)]);
      localStorage.setItem(ACTIVE_PROJECT, next.id); toast.success("Story draft saved.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not save the story."); }
    finally { setBusy(""); }
  };

  const startRun = async () => {
    if (!project || !story.trim()) return;
    setBusy("start");
    try {
      const saved = await updateProjectDraft({ projectId: project.id, title: title.trim(), story_input: story.trim(), automation_mode: false });
      setProject(saved); setStory(saved.story_input);
      const next = await createProductionV2Run(project.id, {
        idempotency_key: `workspace-${crypto.randomUUID()}`, control_mode: controlMode,
        making_route: makingRoute, production_type: productionType,
        image_workflow_id: makingRoute === "reference_built" ? imageWorkflowId : null,
        narrative_style_variant_id: narrativeVariantId || null,
        semi_gates: controlMode === "semi" ? semiGates : {},
      });
      setRun(next); setExistingRuns((current) => [next, ...current.filter((row) => row.run_id !== next.run_id)]); setStageTasks(next.stage_tasks || []); setRevision(null); setStoryCanonDraft(""); automaticStoryStart.current = null; localStorage.setItem(ACTIVE_RUN, next.run_id);
      const loadedCanon = await getProductionCanon(project.id); setCanon(loadedCanon); setCanonText(JSON.stringify({ characters: loadedCanon.characters, worlds: loadedCanon.worlds }, null, 2));
      setAssets((await listProductionAssets(project.id)).assets); setVoiceBindings([]);
      toast.success("Production run created. No media has been submitted yet.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not start the production run."); }
    finally { setBusy(""); }
  };

  const generateStory = async () => {
    if (!project || !run) return;
    setBusy("story");
    const requestKey = `${ACTIVE_RUN}.storyTask.${project.id}.${run.run_id}`;
    const idempotencyKey = localStorage.getItem(requestKey) || crypto.randomUUID();
    localStorage.setItem(requestKey, idempotencyKey);
    try {
      const result = await createProductionV2StoryDetail(project.id, run.run_id, idempotencyKey);
      localStorage.removeItem(requestKey);
      setRevision(result.revision); setStoryCanonDraft(result.revision.expanded_story); setTextRevision(null);
      toast.success(result.accepted ? "Director-approved story is ready." : "Story draft is ready for review.");
    }
    catch (error) {
      if (error instanceof ProductionStageRecoveryRequiredError) {
        const confirmed = window.confirm("This task expired without a saved result. Inspect this run's revisions first. Confirm only if you verified that no durable revision exists; resolving will allow a new attempt.");
        if (confirmed) {
          try {
            await resolveProductionStageTaskWithoutResult(project.id, run.run_id, error.taskId);
            localStorage.removeItem(requestKey);
            toast.success("Task reconciled. Start a new story attempt when ready.");
          } catch (resolveError) {
            toast.error(resolveError instanceof Error ? resolveError.message : "Could not resolve the expired story task.");
          }
          return;
        }
      }
      if (error instanceof Error && error.message.startsWith("Story task ")) localStorage.removeItem(requestKey);
      toast.error(error instanceof Error ? error.message : "Story generation failed.");
    }
    finally { setBusy(""); }
  };

  const useSavedStoryAsCanon = async () => {
    if (!project || !run || directorControls("story_review")) return;
    setBusy("manual-source-story");
    try {
      const result = await createProductionV2ManualStorySource(project.id, run.run_id, run.config.source_story_hash);
      setRevision(result.revision);
      setStoryCanonDraft(result.revision.expanded_story);
      setTextRevision(null);
      toast.success(result.reused ? "Your saved story draft is ready to review." : "Your saved story is now a canon draft; no provider was called.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not prepare the saved story for review."); }
    finally { setBusy(""); }
  };

  const acceptStory = async () => {
    if (!project || !run || !revision) return;
    setBusy("accept");
    try { await acceptProductionV2Story(project.id, run.run_id, revision); setRevision({ ...revision, expanded_story: storyCanonDraft, review_status: "accepted" }); toast.success("Story canon accepted for this run."); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not accept this story revision."); }
    finally { setBusy(""); }
  };

  const saveManualStory = async () => {
    if (!project || !run || !revision || !storyCanonDraft.trim()) return;
    setBusy("manual-story");
    try {
      const result = await saveProductionV2ManualStory(project.id, run.run_id, revision, storyCanonDraft);
      setRevision(result.revision); setStoryCanonDraft(result.revision.expanded_story);
      toast.success("Story edits saved as a new review revision; the parent and source story are unchanged.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not save story edits."); }
    finally { setBusy(""); }
  };

  const parseUnits = () => {
    const value = JSON.parse(textUnits);
    if (!Array.isArray(value) || !value.length) throw new Error("Enter at least one text unit as a JSON array.");
    return value;
  };
  const addStructuredTextUnit = () => {
    try {
      let units: any;
      try { units = JSON.parse(textUnits); }
      catch { throw new Error("Fix the JSON draft before adding another unit."); }
      if (!Array.isArray(units)) throw new Error("The text draft must be a JSON array.");
      const stagePrefix = textStage === "dialogue" ? "dialogue" : "scene";
      const nextIndex = units.filter((unit: any) => String(unit.unit_id || "").startsWith(`${stagePrefix}-`)).length + 1;
      const unitId = `${stagePrefix}-${String(nextIndex).padStart(3, "0")}`;
      const sourceChunkIds = unitSourceChunks.split(",").map((item) => item.trim()).filter(Boolean);
      if (textStage === "dialogue") {
        if (!unitDialogue.trim()) throw new Error("Write the exact spoken words before adding this dialogue beat.");
        units.push({ unit_id: unitId, source_chunk_ids: sourceChunkIds, source: unitDialogue.trim(), content: {
          scene_id: unitSceneId.trim() || null, speaker_id: unitSpeaker.trim() || null,
          exact_words: unitDialogue.trim(), language: "as written", target_duration_seconds: null,
        } });
        setUnitDialogue("");
      } else {
        if (!unitTitle.trim() || !unitDescription.trim()) throw new Error("Add both a scene title and a scene description.");
        units.push({ unit_id: unitId, source_chunk_ids: sourceChunkIds, source: unitDescription.trim(),
          content: { title: unitTitle.trim(), description: unitDescription.trim() } });
        setUnitTitle(""); setUnitDescription("");
      }
      setTextUnits(JSON.stringify(units, null, 2)); setTextStageDirty(true);
      toast.success(`${textStage === "dialogue" ? "Dialogue beat" : "Scene"} ${unitId} added to the draft.`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not add the text unit."); }
  };
  const createTextRevision = async (manual: boolean) => {
    if (!project || !run || !revision || revision.review_status !== "accepted") return;
    setBusy(manual ? "manual-text" : "text-stage");
    try {
      const units = parseUnits();
      const result = manual
        ? await saveProductionV2ManualText(project.id, run.run_id, textStage, revision.revision_id, units)
        : await createProductionV2TextStage(project.id, run.run_id, textStage, revision.revision_id, units);
      setTextRevision(result.revision);
      setTextUnits(JSON.stringify(result.revision.items || units, null, 2));
      setTextStageDirty(false);
      toast.success(manual ? "Your authored text is saved for review." : "Director text proposal is ready for review.");
    } catch (error) {
      if (error instanceof ProductionStageRecoveryRequiredError) {
        const confirmed = window.confirm("This task expired without a saved result. Inspect this run's revisions first. Confirm only if you verified that no durable revision exists; resolving will allow a new attempt.");
        if (confirmed) {
          try {
            await resolveProductionStageTaskWithoutResult(project.id, run.run_id, error.taskId);
            if (error.retryStorageKey) localStorage.removeItem(error.retryStorageKey);
            toast.success("Task reconciled. Submit a new text-stage attempt when ready.");
          } catch (resolveError) {
            toast.error(resolveError instanceof Error ? resolveError.message : "Could not resolve the expired text task.");
          }
          return;
        }
      }
      toast.error(error instanceof Error ? error.message : "Could not prepare this text stage.");
    }
    finally { setBusy(""); }
  };
  const acceptTextRevision = async () => {
    if (!project || !run || !textRevision) return;
    setBusy("accept-text");
    try { await acceptProductionV2Text(project.id, run.run_id, textStage, textRevision.revision_id, textRevision.source_story_hash); setTextRevision({ ...textRevision, review_status: "accepted" }); toast.success(`${textStage.replaceAll("_", " ")} revision accepted.`); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not accept this text revision."); }
    finally { setBusy(""); }
  };
  const createRefineProposal = async () => {
    if (!project || !run || !textRevision || !refineShotId || !refineInstruction.trim()) return;
    setBusy("refine");
    try { const result = await proposeProductionV2Refine(project.id, run.run_id, textRevision.revision_id, refineShotId, refineInstruction.trim()); setRefineProposal(result.proposal); toast.success("Refine proposal is ready; selected assets are unchanged."); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not create Refine proposal."); }
    finally { setBusy(""); }
  };
  const acceptRefineProposal = async () => {
    if (!project || !run || !refineProposal || !textRevision) return;
    setBusy("accept-refine");
    try { const result = await acceptProductionV2Refine(project.id, run.run_id, refineProposal.proposal_id, textRevision.revision_id, refineProposal.base_prompt_hash); setTextRevision(result.revision); setRefineProposal({ ...refineProposal, applied: true }); toast.success("Refine accepted as a new shot-plan revision."); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not accept the Refine proposal."); }
    finally { setBusy(""); }
  };
  const reloadCanon = async () => {
    if (!project) return;
    setBusy("canon-load");
    try { const loaded = await getProductionCanon(project.id); setCanon(loaded); setCanonText(JSON.stringify({ characters: loaded.characters, worlds: loaded.worlds }, null, 2)); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not load project character/world bible."); }
    finally { setBusy(""); }
  };
  const addCharacter = async () => {
    if (!project) return;
    setBusy("canon-add-character");
    try { await createProductionCharacter(project.id, characterName.trim() || undefined); setCharacterName(""); await reloadCanon(); toast.success("Character identity added to this project's bible."); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not add character."); setBusy(""); }
  };
  const addWorld = async () => {
    if (!project || !worldName.trim()) return;
    setBusy("canon-add-world");
    try { await createProductionWorld(project.id, worldName.trim()); setWorldName(""); await reloadCanon(); toast.success("World/location added to this project's bible."); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not add world."); setBusy(""); }
  };
  const saveCanon = async () => {
    if (!project || !canon) return;
    setBusy("canon-save");
    try {
      const parsed = JSON.parse(canonText);
      if (!Array.isArray(parsed.characters) || !Array.isArray(parsed.worlds)) throw new Error("Canon needs characters and worlds arrays.");
      const saved = await saveProductionCanon(project.id, { ...canon, characters: parsed.characters, worlds: parsed.worlds });
      setCanon(saved); setCanonText(JSON.stringify({ characters: saved.characters, worlds: saved.worlds }, null, 2)); toast.success("Character and world bible saved as a new revision.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not save the character/world bible."); }
    finally { setBusy(""); }
  };
  const assignMaster = async (asset: ProductionAsset, role: string) => {
    if (!project || !masterIdentities[asset.asset_id]) return;
    setBusy("master-identity");
    try {
      await assignProductionMasterIdentity(project.id, asset.asset_id, role, masterIdentities[asset.asset_id]);
      setAssets((await listProductionAssets(project.id)).assets);
      toast.success("Master assigned to its canon identity.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not assign this master."); }
    finally { setBusy(""); }
  };
  const uploadAsset = async () => {
    if (!project || !assetFile) return;
    setBusy("asset-upload");
    try { await uploadProductionAsset(project.id, assetFile, assetRole); setAssetFile(null); const result = await listProductionAssets(project.id); setAssets(result.assets); toast.success("Asset uploaded once to this project's production library."); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Asset upload failed."); }
    finally { setBusy(""); }
  };
  const generateProjectImageCandidates = async () => {
    if (!project || !run || !imagePrompt.trim()) return;
    setBusy("image-candidates");
    try {
      const seed = crypto.getRandomValues(new Uint32Array(1))[0];
      const batch = await queueProductionImageJob(project.id, run.run_id, {
        idempotency_key: crypto.randomUUID(), workflow_id: imageWorkflowId,
        asset_role: imageAssetRole, prompt: imagePrompt.trim(), seed,
        width: imageWidth, height: imageHeight, steps: imageSteps,
        ...(imageWorkflowId === "qwen_image_edit_2511" ? { source_asset_ids: editSourceAssetIds } : {}),
        ...(directorControls("image_candidate_selection") && ["character_master", "world_master"].includes(imageAssetRole) ? { entity_id: imageEntityId } : {}),
      });
      setImageBatch(batch);
      toast.success(`${batch.jobs.length} image candidate${batch.jobs.length === 1 ? "" : "s"} added to the project's backend queue.`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not queue project image candidates."); }
    finally { setBusy(""); }
  };
  const acceptImageCandidate = async (asset: ProductionAsset) => {
    if (!project || !run) return;
    const role = String(asset.metadata?.production_image_job?.intended_role || "character_master");
    setBusy(`accept-image:${asset.asset_id}`);
    try {
      await acceptProductionImageCandidate(project.id, run.run_id, asset.asset_id, role);
      setAssets((await listProductionAssets(project.id)).assets);
      toast.success(`Candidate accepted as ${role.replaceAll("_", " ")}.`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not accept this image candidate."); }
    finally { setBusy(""); }
  };

  const imageQueueProjectId = project?.id;
  useEffect(() => {
    if (workspaceStage !== "assets") return;
    let active = true;
    setImageWorkflowReadiness(null);
    void listProductionImageWorkflows().then((result) => {
      if (active) setImageWorkflowReadiness(result.workflows);
    }).catch(() => {
      if (active) setImageWorkflowReadiness([]);
    });
    return () => { active = false; };
  }, [workspaceStage]);
  const selectedImageWorkflow = imageWorkflowReadiness?.find((workflow) => workflow.workflow_id === imageWorkflowId);
  const selectedImageWorkflowReady = selectedImageWorkflow?.available === true;
  useEffect(() => {
    if (!imageQueueProjectId || !imageBatch?.batch_id || isProductionImageBatchSettled(imageBatch)) return;
    let active = true;
    const timer = window.setInterval(() => {
      void getProductionImageJobBatch(imageQueueProjectId, imageBatch.batch_id).then(async (next) => {
        if (!active) return;
        setImageBatch((current) => current?.batch_id === next.batch_id ? next : current);
        if (next.jobs.length && isProductionImageBatchSettled(next)) {
          window.clearInterval(timer);
          try { setAssets((await listProductionAssets(imageQueueProjectId)).assets); }
          catch (error) { toast.error(error instanceof Error ? error.message : "Candidates finished, but the project asset list could not refresh."); }
        }
      }).catch((error) => { if (active) toast.error(error instanceof Error ? error.message : "Could not refresh the image candidate queue."); });
    }, 2500);
    return () => { active = false; window.clearInterval(timer); };
  }, [imageQueueProjectId, imageBatch]);
  const loadRepertoire = async () => {
    setBusy("repertoire-load");
    try {
      const [videos, audios] = await Promise.all([listVideoAssets(), listVideoRepertoireAudioAssets("all")]);
      setRepertoireVideos(videos); setRepertoireAudios(audios); setRepertoireLoaded(true);
      toast.success(`Loaded ${videos.length} shared video and ${audios.filter((item) => item.available).length} available audio assets.`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not load Video Repertoire assets."); }
    finally { setBusy(""); }
  };
  const linkRepertoireAsset = async () => {
    if (!project || !repertoireAssetId) return;
    setBusy("repertoire-link");
    try {
      await linkProductionRepertoireAsset(project.id, repertoireKind, repertoireAssetId);
      setAssets((await listProductionAssets(project.id)).assets);
      toast.success("Shared asset linked by ID; its original file remains in Video Repertoire.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not link the shared asset."); }
    finally { setBusy(""); }
  };
  const directorControls = (gate: string) => (run?.config.control_mode || controlMode) === "fully_automated" || ((run?.config.control_mode || controlMode) === "semi" && run?.config.semi_gates?.[gate] === false);
  const automaticStoryProjectId = project?.id;
  const automaticStoryRunId = run?.run_id;
  const shouldAutomaticallyStartStory = Boolean(automaticStoryProjectId && automaticStoryRunId
    && directorControls("story_review") && !revision
    && !stageTasks?.some((task) => task.stage === "story_detail"));
  const generateStoryRef = useRef(generateStory);
  generateStoryRef.current = generateStory;
  useEffect(() => {
    if (!automaticStoryProjectId || !automaticStoryRunId || !shouldAutomaticallyStartStory) return;
    if (automaticStoryStart.current === automaticStoryRunId) return;
    automaticStoryStart.current = automaticStoryRunId;
    let active = true;
    void (async () => {
      try {
        const saved = await listProductionV2StoryRevisions(automaticStoryProjectId, automaticStoryRunId);
        if (!active) return;
        const latest = [...saved.revisions].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))[0];
        if (latest) {
          setRevision(latest);
          setStoryCanonDraft(latest.expanded_story);
          return;
        }
        await generateStoryRef.current();
      } catch (error) {
        if (active) toast.error(error instanceof Error ? error.message : "Automatic story generation could not start.");
      }
    })();
    return () => { active = false; };
  }, [automaticStoryProjectId, automaticStoryRunId, shouldAutomaticallyStartStory]);
  const bindVoice = async () => {
    if (!project || !run || !voiceCharacterId || !voiceAssetId) return;
    setBusy("voice-bind");
    try { await bindProductionVoice(project.id, run.run_id, voiceCharacterId, { strategy: "manual", voiceAssetId }); setVoiceBindings((await getProductionVoiceBindings(project.id, run.run_id)).bindings); toast.success("Voice bound to this character for this run."); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not bind this voice."); }
    finally { setBusy(""); }
  };
  const prepareAutomaticVoices = async () => {
    if (!project || !run || !directorControls("voice_selection") || !canon?.characters.length) return;
    setBusy("automatic-voices");
    try {
      const saved = (await getProductionVoiceBindings(project.id, run.run_id)).bindings;
      const existing = new Set(saved.map((binding: any) => binding.character_id));
      const failures: string[] = [];
      for (const character of canon.characters.filter((row) => row.status === "active" && !existing.has(row.character_id))) {
        try { await bindProductionVoice(project.id, run.run_id, character.character_id, { strategy: "seeded_random" }); }
        catch (error) { failures.push(`${character.display_name}: ${error instanceof Error ? error.message : "no eligible voice"}`); }
      }
      setVoiceBindings((await getProductionVoiceBindings(project.id, run.run_id)).bindings);
      if (failures.length) toast.message(`Automatic voice assignment is incomplete. ${failures.join(" · ")}`);
      else toast.success("Saved reproducible voice choices for this run; existing character bindings were preserved.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not prepare automatic voice choices."); }
    finally { setBusy(""); }
  };
  const createVoiceExcerpt = async () => {
    if (!project || !run || !voiceCharacterId || !voiceAssetId) return;
    setBusy("voice-excerpt");
    try {
      await createProductionVoiceExcerpt(project.id, run.run_id, voiceCharacterId, {
        voice_asset_id: voiceAssetId, start_sec: voiceExcerptStart, duration_seconds: voiceExcerptDuration,
      });
      setAssets((await listProductionAssets(project.id)).assets);
      toast.success(`H3 voice reference created (${voiceExcerptDuration}s, mono 32 kHz PCM); the original master is unchanged.`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not create the H3 voice reference."); }
    finally { setBusy(""); }
  };
  const uploadDialogueTake = async () => {
    if (!project || !run || !voiceCharacterId || !dialogueTakeFile || !dialogueTranscript.trim()) return;
    setBusy("dialogue-take-upload");
    try {
      await uploadProductionDialogueTake(project.id, run.run_id, voiceCharacterId, dialogueTranscript, dialogueTakeFile);
      setDialogueTakeFile(null); setDialogueTranscript("");
      const refreshed = await listProductionAssets(project.id); setAssets(refreshed.assets);
      toast.success("Original dialogue recording saved with its exact transcript and stable speaker ID.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not save this dialogue recording."); }
    finally { setBusy(""); }
  };
  const convertDialogueTake = async (assetId: string) => {
    if (!project || !run || !selectedRvcModel) return;
    setBusy(`dialogue-convert:${assetId}`);
    try {
      const signature = JSON.stringify([project.id, run.run_id, assetId, selectedRvcModel]);
      if (dialogueConversionRequest.current?.signature !== signature) dialogueConversionRequest.current = { signature, key: crypto.randomUUID() };
      const job = await convertProductionDialogueTake(project.id, run.run_id, assetId, selectedRvcModel, dialogueConversionRequest.current.key);
      setDialogueConversionJob(job);
      toast.success("Local RVC conversion queued. The original recording will remain unchanged.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not queue local dialogue conversion."); }
    finally { setBusy(""); }
  };
  const queueAudioSidecar = async () => {
    if (!project || !run || !sidecarPrompt.trim()) return;
    const signature = JSON.stringify([project.id, run.run_id, sidecarKind, sidecarPrompt.trim(), sidecarDuration, sidecarStart]);
    if (sidecarRequest.current?.signature !== signature) sidecarRequest.current = { signature, key: crypto.randomUUID() };
    setBusy("audio-sidecar");
    try {
      const job = await createProductionAudioSidecar(project.id, run.run_id, {
        idempotency_key: sidecarRequest.current.key, kind: sidecarKind, prompt: sidecarPrompt.trim(), duration_seconds: sidecarDuration,
        seed: 42, start_seconds: sidecarStart,
      });
      setSidecarJob(job);
      sidecarRequest.current = null;
      toast.success(`${sidecarKind === "music" ? "Music" : "Sound-effect"} sidecar queued. It remains separate from H3 native audio and voice references.`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not queue the audio sidecar."); }
    finally { setBusy(""); }
  };
  const queueProductionDialogue = async () => {
    if (!project || !run) return;
    const first = boundDialogueVoices.find((row) => row.character.character_id === dialogueTtsSpeakerOne);
    const second = boundDialogueVoices.find((row) => row.character.character_id === dialogueTtsSpeakerTwo);
    const firstText = dialogueTtsTextOne.trim();
    const secondText = dialogueTtsTextTwo.trim();
    if (!first || !second || !firstText || !secondText || dialogueTtsCueSeconds < 1 || dialogueTtsCueSeconds > 60
      || firstText.includes("\n") || secondText.includes("\n")) return;
    const speakers = [
      { character_id: first.character.character_id, voice_excerpt_asset_id: first.excerpt.asset_id },
      { character_id: second.character.character_id, voice_excerpt_asset_id: second.excerpt.asset_id },
    ];
    const lines = [
      { character_id: first.character.character_id, text: firstText, start_seconds: 0, end_seconds: dialogueTtsCueSeconds },
      { character_id: second.character.character_id, text: secondText, start_seconds: dialogueTtsCueSeconds, end_seconds: dialogueTtsCueSeconds * 2 },
    ];
    const signature = JSON.stringify([project.id, run.run_id, speakers, lines, 42]);
    if (dialogueTtsRequest.current?.signature !== signature) {
      dialogueTtsRequest.current = { signature, key: crypto.randomUUID() };
    }
    setBusy("dialogue-tts");
    try {
      const job = await createProductionDialogueTTS(project.id, run.run_id, {
        idempotency_key: dialogueTtsRequest.current.key, speakers, lines, seed: 42,
      });
      setDialogueTtsJob(job);
      toast.success("Bound two-speaker dialogue queued. It will be saved separately from H3 native audio.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not queue generated dialogue."); }
    finally { setBusy(""); }
  };
  const selectComposerShot = (shotId: string, parentTakeId = "", takeToReview: any = null) => {
    setComposerShotId(shotId); setShotPreview(null); setShotPreviewRequest(null); setSelectedTake(takeToReview);
    setComposerParentTakeId(parentTakeId);
    if (run) localStorage.setItem(`story-builder.production.shot.${run.run_id}`, shotId);
    const selected = (textRevision?.items || []).find((item: any) => item.unit_id === shotId);
    const prompt = String(selected?.content?.prompt || selected?.content?.prompt_text || "");
    setComposerPrompt(prompt);
    setComposerDuration(Number(selected?.content?.duration_seconds || 5));
    setReferenceIntents({}); setVideoIntervals({}); setAudioSpeakerIds({});
  };
  const moveReference = (ids: string[], setIds: (next: string[]) => void, index: number, offset: number) => {
    const target = index + offset;
    if (target < 0 || target >= ids.length) return;
    const next = [...ids]; [next[index], next[target]] = [next[target], next[index]]; setIds(next);
    setShotPreview(null); setShotPreviewRequest(null);
  };
  const intentFor = (assetId: string, fallback: string) => referenceIntents[assetId] ?? fallback;
  const setIntentFor = (assetId: string, intent: string) => setReferenceIntents((current) => ({ ...current, [assetId]: intent }));
  const buildComposerReferences = () => ({
    images: selectedImageIds.map((asset_id) => ({ asset_id, role: assets.find((row) => row.asset_id === asset_id)?.roles[0] || "character_master", intent: intentFor(asset_id, "Use as the selected visual reference.") })),
    videos: selectedVideoIds.map((asset_id) => { const duration = Number(assets.find((row) => row.asset_id === asset_id)?.media?.duration_seconds || 15); const interval = videoIntervals[asset_id] || { start_sec: 0, end_sec: Math.min(15, duration) }; return { asset_id, role: "action_reference_video", intent: intentFor(asset_id, "Use for motion, camera movement, or continuity as specified by the Director."), ...interval, include_paired_soundtrack: pairVideoAudio, audio_intent: "Use synchronized timing/sound only where relevant." }; }),
    standalone_audios: selectedAudioIds.map((asset_id) => ({ asset_id, role: "voice_reference", intent: intentFor(asset_id, "the selected standalone audio reference; use it only for its stated purpose"), speaker_id: audioSpeakerIds[asset_id] || undefined })),
  });
  const composerHasReferences = selectedImageIds.length + selectedVideoIds.length + selectedAudioIds.length > 0;
  const composerDurationMax = composerHasReferences ? 15 : 10;
  const previewShot = async () => {
    if (!project || !run || !textRevision || !composerShotId || !composerPrompt.trim()) return;
    if (composerDuration > composerDurationMax) {
      toast.error(`Zero-reference H3 text-to-video supports 5–10 seconds. Shorten this shot or add a supported reference.`);
      return;
    }
    setBusy("shot-preview"); setShotPreview(null);
    try {
      const lines = [...selectedImageIds.map((assetId, i) => `<Picture ${i + 1}> is ${intentFor(assetId, "the selected visual reference")}`)];
      let audioIndex = 1;
      selectedVideoIds.forEach((assetId, i) => { if (pairVideoAudio) lines.push(`<Audio ${audioIndex++}> is the synchronized soundtrack paired with <Video ${i + 1}>; use only its relevant timing and sound cues.`); lines.push(`<Video ${i + 1}> is ${intentFor(assetId, "the selected motion, camera, or continuity reference")}`); });
      selectedAudioIds.forEach((assetId) => lines.push(`<Audio ${audioIndex++}> is ${intentFor(assetId, "the selected standalone audio reference; use it only for its stated purpose")}${audioSpeakerIds[assetId] ? ` for speaker ${audioSpeakerIds[assetId]}` : ""}.`));
      const isSavedPreparedPrompt = shotPromptPreparation?.result?.accepted === true && composerPrompt.trim() === shotPromptPreparation.result.prompt;
      const completedPrompt = isSavedPreparedPrompt ? composerPrompt.trim() : [composerPrompt.trim(), ...lines].join("\n\n");
      const validationRequest = {
        shot_plan_revision_id: textRevision.revision_id, prompt: completedPrompt,
        duration_seconds: composerDuration, resolution_preset: composerResolutionPreset, steps: composerSteps,
        ref_image_size: "max", seed: 1,
        ...buildComposerReferences(),
      };
      const result = await validateProductionShot(project.id, run.run_id, composerShotId, validationRequest);
      setShotPreview({ ...result, compiled_prompt: completedPrompt });
      setShotPreviewRequest(validationRequest); setShotIdempotencyKey(`shot-${crypto.randomUUID()}`); setSelectedTake(null);
      toast.success("Shot reference plan validated; no render was submitted.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Shot validation failed."); }
    finally { setBusy(""); }
  };
  const prepareShotPrompt = async () => {
    if (!project || !run || !shotPreviewRequest || !composerShotId || !textRevision) return;
    setBusy("shot-prompt-prepare");
    try {
      const taskStorageKey = `story-builder.production.prompt-task.${run.run_id}.${composerShotId}.${textRevision.revision_id}`;
      const requestStorageKey = `${taskStorageKey}.request`;
      const requestBody = {
        shot_plan_revision_id: textRevision.revision_id,
        validation_request: shotPreviewRequest,
        resolve_catalog: directorControls("shot_workflow_render_approval"),
      };
      const requestFingerprint = JSON.stringify(requestBody);
      let idempotencyKey = "";
      try {
        const savedRequest = JSON.parse(localStorage.getItem(requestStorageKey) || "null");
        if (savedRequest?.fingerprint === requestFingerprint && typeof savedRequest.idempotency_key === "string") {
          idempotencyKey = savedRequest.idempotency_key;
        }
      } catch { /* Replace malformed local recovery data with a fresh durable key. */ }
      if (!idempotencyKey) {
        idempotencyKey = `shot-prompt-${crypto.randomUUID()}`;
        // Persist the request key before the POST: the server may commit the
        // task even if the response is lost, and a retry must reuse this key.
        localStorage.setItem(requestStorageKey, JSON.stringify({ fingerprint: requestFingerprint, idempotency_key: idempotencyKey }));
      }
      const task = await prepareProductionShotPrompt(project.id, run.run_id, composerShotId, {
        idempotency_key: idempotencyKey,
        ...requestBody,
      });
      setShotPromptPreparation(task); setPreparedPromptDraft(""); setPreparedPromptEdited(false);
      localStorage.setItem(taskStorageKey, task.task_id);
      toast.success("Prompt preparation saved. The task will keep running if this page is closed.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not prepare the shot prompt."); }
    finally { setBusy(""); }
  };
  const validateReviewedShotPrompt = async () => {
    if (!project || !run || !shotPreviewRequest || !composerShotId || !preparedPromptDraft.trim()) return;
    setBusy("shot-prompt-validate");
    try {
      const resolvedRequest = shotPromptPreparation?.result?.resolved_validation_request || shotPreviewRequest;
      const finalRequest = { ...resolvedRequest, prompt: preparedPromptDraft.trim() };
      const result = await validateProductionShot(project.id, run.run_id, composerShotId, finalRequest);
      setShotPreview({ ...result, compiled_prompt: finalRequest.prompt });
      setShotPreviewRequest(finalRequest);
      setShotIdempotencyKey(`shot-${crypto.randomUUID()}`);
      toast.success("Reviewed prompt validated against the current workflow and references.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Reviewed prompt validation failed."); }
    finally { setBusy(""); }
  };
  const saveComposerDraft = async () => {
    if (!project || !run || !textRevision || !composerShotId) {
      const missing = [!project && "project", !run && "run", !textRevision && "accepted shot plan", !composerShotId && "selected shot"].filter(Boolean).join(", ");
      setComposerDraftError(`Cannot save this shot draft: missing ${missing}.`);
      toast.error(`Cannot save this shot draft: missing ${missing}.`);
      return;
    }
    if (composerDraftStale) {
      setComposerDraftError("This shot draft is based on an older shot plan. Reload the current accepted shot plan before saving.");
      toast.error("This shot draft is based on an older shot plan. Reload the current accepted shot plan before saving.");
      return;
    }
    setComposerDraftError("");
    setBusy("shot-draft-save");
    try {
      const saved = await saveProductionShotDraft(project.id, run.run_id, composerShotId, {
        expected_draft_revision: composerDraftRevision,
        shot_plan_revision_id: textRevision.revision_id,
        prompt: composerPrompt.trim(), duration_seconds: composerDuration,
        resolution_preset: composerResolutionPreset, steps: composerSteps, ref_image_size: "max", seed: 1,
        ...buildComposerReferences(),
      });
      setComposerDraftRevision(Number(saved.revision)); setComposerDraftStale(false);
      if (saved.held_child_take_ids?.length) toast.info(`Draft saved. ${saved.held_child_take_ids.length} queued take(s) now wait for review because their frozen inputs changed.`);
      else toast.success(`Shot ${composerShotId} draft saved as revision ${saved.revision}.`);
    } catch (error) { const message = error instanceof Error ? `Could not save shot draft ${composerShotId}: ${error.message}` : `Could not save shot draft ${composerShotId}.`; setComposerDraftError(message); toast.error(message); }
    finally { setBusy(""); }
  };
  const queueShot = async (advanceToNext = false) => {
    if (!project || !run || !shotPreviewRequest || !shotIdempotencyKey || !shotPreview?.workflow_readiness?.available) return;
    setBusy("shot-queue");
    try {
      const finalRequest = shotPromptPreparation?.result?.accepted === true && !preparedPromptEdited
        ? { ...shotPreviewRequest, prompt: shotPromptPreparation.result.prompt }
        : shotPreviewRequest;
      const preparedTaskId = shotPromptPreparation?.result?.accepted === true && !preparedPromptEdited
        && preparedPromptDraft.trim() === shotPromptPreparation.result.prompt ? shotPromptPreparation.task_id : null;
      const saved = await saveProductionShotDraft(project.id, run.run_id, composerShotId, {
        expected_draft_revision: composerDraftRevision,
        ...finalRequest,
      });
      setComposerDraftRevision(Number(saved.revision)); setComposerDraftStale(false);
      const result = await queueProductionShot(project.id, run.run_id, composerShotId,
        finalRequest, shotIdempotencyKey, composerParentTakeId || null, preparedTaskId);
      const latest = await fetchProductionV2Run(project.id, run.run_id);
      setRun(latest); setSelectedTake(latest.takes?.find((take: any) => take.take_id === result.take.take_id) || result.take);
      toast.success("Shot durably queued. The output remains a candidate until reviewed.");
      if (advanceToNext) {
        const items = textRevision?.items || [];
        const currentIndex = items.findIndex((item: any) => item.unit_id === composerShotId);
        const next = currentIndex >= 0 ? items[currentIndex + 1] : null;
        if (next) {
          const current = items[currentIndex];
          const sceneOf = (item: any) => item?.scene_id || item?.content?.scene_id || item?.content?.scene;
          const currentScene = sceneOf(current);
          const nextScene = sceneOf(next);
          selectComposerShot(next.unit_id, currentScene && currentScene === nextScene ? result.take.take_id : "");
          toast.info(currentScene && currentScene === nextScene
            ? `Opened ${next.unit_id} with the queued predecessor linked.`
            : `Opened ${next.unit_id}; scene boundary reset its predecessor.`);
        } else {
          setComposerParentTakeId("");
          toast.info("No next shot is available in this accepted shot plan.");
        }
      }
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not queue this shot."); }
    finally { setBusy(""); }
  };
  const refreshSelectedTake = async () => {
    if (!project || !run || !selectedTake) return;
    setBusy("take-refresh");
    try {
      const latest = await fetchProductionV2Run(project.id, run.run_id);
      setRun(latest);
      setSelectedTake(latest.takes?.find((take: any) => take.take_id === selectedTake.take_id) || selectedTake);
      setAssets((await listProductionAssets(project.id)).assets);
    }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not refresh take status."); }
    finally { setBusy(""); }
  };
  const selectedTakeAssets = selectedTake
    ? assets.filter((asset) => asset.metadata?.take_id === selectedTake.take_id && asset.source === "project_output")
    : [];
  const selectedTakeIsActive = ["queued", "waiting_for_predecessor", "submitting", "running", "collecting", "cancel_requested", "recovery_required"].includes(selectedTake?.status);
  const activeTakeIds = (run?.takes || []).filter((take: any) =>
    productionTakeNeedsPolling(take, directorControls("shot_workflow_render_approval"))).map((take: any) => take.take_id);
  const activeTakeSignature = activeTakeIds.join("|");
  const activeProjectId = project?.id;
  const activeRunId = run?.run_id;
  const activeTakeId = selectedTake?.take_id;
  useEffect(() => {
    const jobId = dialogueConversionJob?.job_id;
    if (!activeProjectId || !activeRunId || !jobId || !["queued", "submitting", "running", "recovery_required"].includes(dialogueConversionJob?.status)) return;
    let disposed = false;
    const timer = window.setInterval(async () => {
      try {
        const latest = await getProductionAudioSidecarJob(activeProjectId, activeRunId, jobId);
        if (disposed) return;
        setDialogueConversionJob(latest);
        if (["completed", "failed", "cancelled"].includes(latest.status)) dialogueConversionRequest.current = null;
        if (latest.status === "completed") {
          setAssets((await listProductionAssets(activeProjectId)).assets);
          toast.success("Converted dialogue is ready as a separate project asset.");
        } else if (latest.status === "failed") {
          toast.error(`Dialogue conversion failed: ${latest.error || "local worker error"}`);
        }
      } catch (error) { console.warn("Dialogue conversion status refresh failed.", error); }
    }, 3000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [activeProjectId, activeRunId, dialogueConversionJob?.job_id, dialogueConversionJob?.status]);
  useEffect(() => {
    setShotPreview(null);
    setShotPreviewRequest(null);
    setShotIdempotencyKey("");
    setShotPromptPreparation(null);
    setPreparedPromptDraft("");
    setPreparedPromptEdited(false);
  }, [composerPrompt, composerDuration, composerResolutionPreset, composerSteps, selectedImageIds, selectedVideoIds, selectedAudioIds, pairVideoAudio, referenceIntents, videoIntervals, audioSpeakerIds]);
  useEffect(() => {
    const mode = run?.config.control_mode || controlMode;
    const autoPrepareShotPrompt = mode === "fully_automated"
      || (mode === "semi" && run?.config.semi_gates?.shot_workflow_render_approval === false);
    if (!project?.id || !run?.run_id || !composerShotId || !textRevision?.revision_id
        || !autoPrepareShotPrompt) return;
    const task = [...(stageTasks || [])]
      .filter((candidate) => candidate.stage === "controller:resolved_shot_prompt"
        && candidate.shot_id === composerShotId
        && candidate.shot_plan_revision_id === textRevision.revision_id)
      .sort((left, right) => String(right.updated_at).localeCompare(String(left.updated_at)))[0];
    if (!task || task.task_id === shotPromptPreparation?.task_id
        && String(shotPromptPreparation?.updated_at || "") >= String(task.updated_at || "")) return;
    localStorage.setItem(`story-builder.production.prompt-task.${run.run_id}.${composerShotId}.${textRevision.revision_id}`, task.task_id);
    setShotPromptPreparation(task);
    setPreparedPromptDraft("");
    setPreparedPromptEdited(false);
  }, [project?.id, run?.run_id, run?.config, composerShotId, textRevision?.revision_id,
    stageTasks, shotPromptPreparation?.task_id, shotPromptPreparation?.updated_at, controlMode]);
  useEffect(() => {
    if (!project?.id || !run?.run_id || !composerShotId || !textRevision?.revision_id) return;
    let disposed = false;
    const storageKey = `story-builder.production.prompt-task.${run.run_id}.${composerShotId}.${textRevision.revision_id}`;
    const restore = async () => {
      try {
        const taskId = localStorage.getItem(storageKey);
        if (taskId && !shotPromptPreparation?.task_id) {
          const task = await getProductionShotPromptPreparation(project.id, run.run_id, composerShotId, taskId);
          if (!disposed) setShotPromptPreparation(task);
        }
      } catch (error) { console.warn("Saved shot prompt preparation could not be restored.", error); }
    };
    void restore();
    if (!shotPromptPreparation?.task_id || !["queued", "running"].includes(shotPromptPreparation.status)) return () => { disposed = true; };
    const timer = window.setInterval(async () => {
      try {
        const task = await getProductionShotPromptPreparation(project.id, run.run_id, composerShotId, shotPromptPreparation.task_id);
        if (disposed) return;
        setShotPromptPreparation(task);
        if (task.status === "completed" && task.result?.accepted === true && !preparedPromptEdited) {
          setPreparedPromptDraft(task.result.prompt || "");
        }
      } catch (error) { console.warn("Shot prompt status refresh failed; the task remains saved.", error); }
    }, 2000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [project?.id, run?.run_id, composerShotId, textRevision?.revision_id, shotPromptPreparation?.task_id, shotPromptPreparation?.status, preparedPromptEdited]);
  useEffect(() => {
    if (shotPromptPreparation?.status === "completed" && shotPromptPreparation.result?.accepted === true && !preparedPromptDraft) {
      setPreparedPromptDraft(shotPromptPreparation.result.prompt || "");
      setPreparedPromptEdited(false);
    }
  }, [shotPromptPreparation?.status, shotPromptPreparation?.result?.prompt, shotPromptPreparation?.result?.accepted, preparedPromptDraft]);
  useEffect(() => {
    if (!activeProjectId || !activeRunId || !activeTakeSignature) return;
    let disposed = false;
    const previouslyActive = new Set(activeTakeSignature.split("|"));
    const timer = window.setInterval(async () => {
      try {
        const latest = await fetchProductionV2Run(activeProjectId, activeRunId);
        if (disposed) return;
        setRun(latest);
        const current = activeTakeId ? latest.takes?.find((take: any) => take.take_id === activeTakeId) : null;
        if (current) setSelectedTake(current);
        const terminalTakeCompleted = (latest.takes || []).some((take: any) => previouslyActive.has(take.take_id) && ["needs_review", "accepted", "failed", "cancelled"].includes(take.status));
        if (terminalTakeCompleted) {
          (latest.takes || []).forEach((take: any) => previouslyActive.delete(take.take_id));
          setAssets((await listProductionAssets(activeProjectId)).assets);
        }
      } catch (error) {
        console.warn("Production take status refresh failed; manual refresh remains available.", error);
      }
    }, 5000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [activeProjectId, activeRunId, activeTakeId, activeTakeSignature]);
  const openTake = async (take: any) => {
    if (take.shot_id && take.shot_id !== composerShotId) {
      selectComposerShot(take.shot_id, take.parent_take_id || "", take);
    }
    setSelectedTake(take);
    setWorkspaceStage("shots");
    if (run) localStorage.setItem(`story-builder.production.workspace-stage.${run.run_id}`, "shots");
    if (project) {
      try { setAssets((await listProductionAssets(project.id)).assets); }
      catch (error) { toast.error(error instanceof Error ? error.message : "Could not load this take's registered outputs."); }
    }
  };
  const actOnTake = async (action: "accept" | "cancel" | "retry") => {
    if (!project || !run || !selectedTake) return;
    setBusy(`take-${action}`);
    try {
      if (action === "accept") {
        const preview = await acceptProductionTake(project.id, run.run_id, selectedTake.take_id);
        if (preview.requires_confirmation) {
          const childIds = (preview.queued_children_to_stale || []).map((child: any) => String(child.take_id));
          const childSummary = (preview.queued_children_to_stale || [])
            .map((child: any) => `${child.shot_id} (${child.take_id})`).join(", ");
          const confirmed = window.confirm(
            `This retake replaces the accepted version of this shot. Queued dependent shot(s) ${childSummary} will become stale and must be revalidated/requeued. Already accepted later clips will remain unchanged. Continue?`,
          );
          if (!confirmed) {
            toast.info("Take acceptance cancelled; no dependent shots were changed.");
            return;
          }
          const accepted = await acceptProductionTake(project.id, run.run_id, selectedTake.take_id, childIds);
          if (!accepted.accepted) throw new Error("Dependency state changed after the preview. Review the updated queue and try again.");
        } else if (!preview.accepted) {
          throw new Error("Take could not be accepted. Review its dependency state and try again.");
        }
      }
      else if (action === "cancel") await cancelProductionTake(project.id, run.run_id, selectedTake.take_id);
      else await retryProductionTake(project.id, run.run_id, selectedTake.take_id);
      await refreshSelectedTake(); toast.success(`Take ${action} action recorded.`);
    } catch (error) { toast.error(error instanceof Error ? error.message : `Could not ${action} this take.`); }
    finally { setBusy(""); }
  };

  const reconcileAbsentTake = async () => {
    if (!project || !run || !selectedTake?.prompt_id) return;
    const confirmed = window.confirm(
      `Resolve take ${selectedTake.take_id} as failed only if ComfyUI confirms prompt ${selectedTake.prompt_id} is absent from its queue and history, and no output is registered. This does not stop a running prompt. Continue with that check?`,
    );
    if (!confirmed) return;
    setBusy("take-reconcile");
    try {
      await reconcileAbsentProductionTake(project.id, run.run_id, selectedTake.take_id, selectedTake.prompt_id);
      await refreshSelectedTake();
      toast.success("Exact prompt absence confirmed. The take is failed and can now be retried.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not safely reconcile this take."); }
    finally { setBusy(""); }
  };

  const selectTextStage = async (stage: string): Promise<boolean> => {
    if (!project || !run) return false;
    if (textStageDirty && !window.confirm("This text has unsaved edits. Switch stage and discard those edits?")) return false;
    setBusy("stage-load");
    try {
      const result = await listProductionV2TextRevisions(project.id, run.run_id, stage);
      const latest = [...result.revisions].sort((a, b) => String(b.accepted_at || b.created_at || "").localeCompare(String(a.accepted_at || a.created_at || "")))[0] || null;
      setTextStage(stage);
      localStorage.setItem(`story-builder.production.stage.${run.run_id}`, stage);
      setTextRevision(latest);
      setTextUnits(JSON.stringify(latest?.items || [], null, 2));
      setTextStageDirty(false);
      setRefineProposal(null);
      if (stage === "shot_plans" && latest?.review_status === "accepted" && latest.items?.length) {
        const savedShot = latest.items.find((item: any) => item.unit_id === localStorage.getItem(`story-builder.production.shot.${run.run_id}`)) || latest.items[0];
        setComposerShotId(savedShot.unit_id);
        setComposerPrompt(String(savedShot.content?.prompt || savedShot.content?.prompt_text || ""));
        setComposerDuration(Number(savedShot.content?.duration_seconds || 5));
      }
      return true;
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not load this text stage."); return false; }
    finally { setBusy(""); }
  };

  const goToWorkspaceStage = async (stage: string) => {
    if (stage !== "story" && !run) {
      toast.message("Create a production run from a saved story before opening later stages.");
      setWorkspaceStage("story");
      document.getElementById("production-story-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (stage === "shots" && run && textStage !== "shot_plans" && !(await selectTextStage("shot_plans"))) return;
    if (stage === "voice" && directorControls("voice_selection")) await prepareAutomaticVoices();
    setWorkspaceStage(stage);
    if (run) localStorage.setItem(`story-builder.production.workspace-stage.${run.run_id}`, stage);
    const target = stage === "voice" && !document.getElementById("production-voices") ? "production-asset-library" : ({ story: "production-story-section", assets: "production-assets", voice: "production-voices", shots: "production-shots" }[stage]);
    window.setTimeout(() => document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };

  const runActive = Boolean(run);
  return <AppShell><div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-sm font-medium text-primary">Production · V2</p><h1 className="mt-1 text-3xl font-semibold">Production workspace</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">Build a production run around a required story. This workspace is additive; the existing Story Builder and Automation routes are unchanged.</p></div>
      <Badge variant="outline">Project-scoped production · GPU jobs require validated readiness</Badge>
    </div>

    <nav className="grid gap-2 sm:grid-cols-4" aria-label="Production stages">
      {[{ id: "story", label: "Story & direction", status: revision?.review_status === "accepted" ? "Story accepted" : run ? "Review story" : "Start here" }, { id: "assets", label: "Assets & world", status: canon ? `${canon.characters.length} characters · ${canon.worlds.length} worlds` : run ? "Project bible" : "After story" }, { id: "voice", label: "Voices & audio", status: voiceBindings.length ? `${voiceBindings.length} voice binding(s)` : "Optional / choose voices" }, { id: "shots", label: "Shot composer", status: textRevision?.review_status === "accepted" && textStage === "shot_plans" ? "Shot plan accepted" : "Prompts & renders" }].map((stage, index) => <button key={stage.id} type="button" aria-current={workspaceStage === stage.id ? "step" : undefined} onClick={() => void goToWorkspaceStage(stage.id)} disabled={busy !== ""} className={`rounded-xl border p-3 text-left transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-wait disabled:opacity-60 ${workspaceStage === stage.id ? "border-primary bg-primary/5" : "border-border hover:bg-muted/60"}`}><p className="text-xs">Stage {index + 1}</p><p className="font-medium">{stage.label}</p><p className="mt-1 text-xs text-muted-foreground">{stage.status}</p></button>)}
    </nav>

    {project ? <div className="max-w-2xl space-y-2"><Label htmlFor="production-run">Open saved production run</Label><select id="production-run" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={run?.run_id || ""} onChange={(event) => selectSavedRun(event.target.value)} disabled={busy !== ""}><option value="">Create a new production run</option>{existingRuns.map((saved) => <option key={saved.run_id} value={saved.run_id}>{new Date(saved.created_at || saved.updated_at || 0).toLocaleString()} · {saved.config.control_mode} · {saved.config.making_route} · {saved.status} · {saved.run_id.slice(0, 8)}</option>)}</select><p className="text-xs text-muted-foreground">Runs are scoped to this project. Selecting one restores its saved story, stages, drafts, and review queue.</p></div> : null}

    {workspaceStage === "story" ? <Card id="production-story-section"><CardHeader><CardTitle>Choose or create a project</CardTitle><CardDescription>Each production run snapshots the project story. Save edits before opening a new run.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {stageTasks?.length ? <section aria-label="Director text workflow status" className="space-y-2 rounded-md border p-3">
          <p className="text-sm font-medium">Director text workflow</p>
          {stageTasks.map((task) => <div key={task.task_id} className="flex flex-wrap items-center gap-2 text-sm">
            <span>{task.stage === "controller:scene_outline" ? "Scene and shot outline" : task.stage.replace(/^text:/, "").replaceAll("_", " ").replace("story_detail", "Story detailing")}</span>
            <Badge variant={task.status === "failed" || task.status === "recovery_required" ? "destructive" : task.status === "completed" ? "default" : "secondary"}>{task.status.replaceAll("_", " ")}</Badge>
            {task.error?.message ? <span className="text-xs text-destructive">{task.error.message}</span> : null}
            {task.stage === "controller:scene_outline" && task.result?.voice_binding_status === "needs_eligible_voice_assets" ? <span className="basis-full text-xs text-amber-700 dark:text-amber-400">Automatic voice assignment is waiting for an accepted project voice master of at least {task.result.minimum_voice_seconds || 30} seconds. Add one in Assets, then open Voices & audio to retry; existing character choices are preserved.</span> : null}
            {task.stage === "controller:scene_outline" && task.result?.voice_binding_status === "complete" ? <span className="basis-full text-xs text-muted-foreground">Saved reproducible local voice choices for {task.result.voice_binding_count} character(s).</span> : null}
          </div>)}
          <p className="text-xs text-muted-foreground">Automatic text drafting stops before image or video generation. GPU jobs still require their saved approval gates.</p>
        </section> : null}
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(16rem,0.65fr)]">
          <div className="space-y-2"><Label htmlFor="production-project">Existing project</Label><select id="production-project" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={project?.id || ""} onChange={(event) => event.target.value && chooseProject(event.target.value)}><option value="">Create a new project below</option>{projects.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></div>
          <div className="space-y-2"><Label htmlFor="production-title">Project title</Label><Input id="production-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="A short working title" /></div>
        </div>
        <div className="space-y-2"><Label htmlFor="production-story">Story / premise (required)</Label><Textarea id="production-story" value={story} onChange={(event) => setStory(event.target.value)} placeholder="Write the story yourself, or save a rough premise to expand with the Director." className="min-h-40" /><p className="text-xs text-muted-foreground">Your story is the source of truth. Director expansion is a proposal/canon revision and does not replace this source text.</p></div>
        <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={saveDraft} disabled={busy !== "" || !title.trim() || !story.trim()}><Save className="mr-2 h-4 w-4" />{busy === "save" ? "Saving…" : "Save story draft"}</Button></div>
      </CardContent>
    </Card> : null}

    {workspaceStage === "story" ? <Card><CardHeader><CardTitle>Run controls</CardTitle><CardDescription>Control mode and making route are independent choices.</CardDescription></CardHeader><CardContent className="grid gap-4 md:grid-cols-4">
      <div className="space-y-2"><Label htmlFor="control-mode">How much should I review?</Label><select id="control-mode" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={controlMode} onChange={(event) => setControlMode(event.target.value)}><option value="manual">Manual</option><option value="semi">Semi-automated</option><option value="fully_automated">Fully automated</option></select></div>
      <div className="space-y-2"><Label htmlFor="making-route">How should visuals be made?</Label><select id="making-route" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={makingRoute} onChange={(event) => setMakingRoute(event.target.value)}><option value="direct_h3">Direct H3</option><option value="reference_built">Reference-built</option><option value="hybrid">Hybrid</option></select></div>
      {makingRoute === "reference_built" && (controlMode === "fully_automated" || (controlMode === "semi" && !semiGates.image_candidate_selection)) ? <div className="space-y-2"><Label htmlFor="run-image-workflow">Automatic master image workflow</Label><select id="run-image-workflow" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={imageWorkflowId} onChange={(event) => setImageWorkflowId(event.target.value)}><option value="z_image_turbo">Z-Image Turbo</option><option value="qwen_image_2512">Qwen Image 2512</option></select><p className="text-xs text-muted-foreground">Saved with this run. If the selected workflow is unavailable, automatic master generation stays held.</p></div> : null}
      <ProductionStylePicker title="Production type and narrative style" value={productionType} variantId={narrativeVariantId} onChange={(type, variant) => { setProductionType(type); setNarrativeVariantId(variant); }} />
      {controlMode === "semi" ? <fieldset className="space-y-2 md:col-span-3"><legend className="text-sm font-medium">Pause for my decision at</legend><div className="grid gap-2 sm:grid-cols-2">{([
        ["story_review", "Story and scene review"], ["image_candidate_selection", "Image candidate selection"],
        ["voice_selection", "Voice selection"], ["shot_workflow_render_approval", "Shot, workflow, and render approval"],
      ] as const).map(([key, label]) => <label key={key} className="flex min-h-10 items-center gap-2 rounded-md border px-3 text-sm"><input type="checkbox" checked={semiGates[key]} onChange={(event) => setSemiGates((current) => ({ ...current, [key]: event.target.checked }))} />{label}</label>)}</div></fieldset> : null}
    </CardContent></Card> : null}

    {workspaceStage === "story" ? <div className="flex flex-wrap gap-2"><Button onClick={startRun} disabled={!canStart}><Play className="mr-2 h-4 w-4" />{busy === "start" ? "Creating run…" : "Create production run"}</Button>
      {run && !revision && !directorControls("story_review") ? <Button variant="outline" onClick={useSavedStoryAsCanon} disabled={busy !== ""}><Check className="mr-2 h-4 w-4" />{busy === "manual-source-story" ? "Preparing story…" : "Use saved story as my canon"}</Button> : null}
      {run ? <Button variant="outline" onClick={generateStory} disabled={busy !== ""}><Sparkles className="mr-2 h-4 w-4" />{busy === "story" ? "Working…" : "Ask Director to expand story"}</Button> : null}</div>
      : null}

    {workspaceStage === "story" && run ? <Card><CardHeader><CardTitle>Story review</CardTitle><CardDescription>Run {run.run_id} · {run.config.control_mode} · {run.config.making_route}. Text and shot validation are available; actual rendering is enabled only when the exact H3 workflow preflight passes.</CardDescription></CardHeader><CardContent className="space-y-4">
      {!revision ? <p className="text-sm text-muted-foreground">Use the saved source as your story, or ask the Director for an expanded proposal.</p> : <><div className="flex items-center gap-2"><Badge variant={revision.review_status === "accepted" ? "default" : "secondary"}>{revision.review_status.replaceAll("_", " ")}</Badge><span className="text-xs text-muted-foreground">Revision {revision.revision_id}</span></div><Textarea aria-label="Expanded story proposal" value={storyCanonDraft} onChange={(event) => setStoryCanonDraft(event.target.value)} readOnly={directorControls("story_review")} className="min-h-56" /><p className="text-xs text-muted-foreground">The source story stays frozen for this run. Manual/Semi edits are saved as a new revision; source excerpts and evidence remain attached to its parent lineage.</p>{!directorControls("story_review") ? <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={saveManualStory} disabled={busy !== "" || !storyCanonDraft.trim() || storyCanonDraft === revision.expanded_story}><Save className="mr-2 h-4 w-4" />{busy === "manual-story" ? "Saving revision…" : "Save edits as revision"}</Button>{revision.review_status !== "accepted" ? <Button onClick={acceptStory} disabled={busy !== "" || !storyCanonDraft.trim() || storyCanonDraft !== revision.expanded_story}><Check className="mr-2 h-4 w-4" />{busy === "accept" ? "Accepting…" : "Accept story canon"}</Button> : null}</div> : null}</>}
    </CardContent></Card> : null}

    {workspaceStage === "assets" && run && canon ? <Card id="production-assets"><CardHeader><CardTitle>Character & world bible</CardTitle><CardDescription>Project-scoped text canon with immutable IDs. Create anonymous identities safely, describe their appearance/voice and define recurring places. This does not generate or duplicate media.</CardDescription></CardHeader><CardContent className="space-y-4">
      <div className="flex flex-wrap items-end gap-3"><div className="min-w-56 flex-1 space-y-2"><Label htmlFor="new-character-name">New character name (optional)</Label><Input id="new-character-name" value={characterName} onChange={(event) => setCharacterName(event.target.value)} placeholder="Leave blank for a safe Character-XXXX alias" /></div><Button variant="outline" onClick={addCharacter} disabled={busy !== ""}>Add character</Button><div className="min-w-56 flex-1 space-y-2"><Label htmlFor="new-world-name">New world/location</Label><Input id="new-world-name" value={worldName} onChange={(event) => setWorldName(event.target.value)} placeholder="e.g. North Station" /></div><Button variant="outline" onClick={addWorld} disabled={busy !== "" || !worldName.trim()}>Add world</Button></div>
      <div className="space-y-2"><Label htmlFor="production-canon-json">Character and world details (JSON)</Label><Textarea id="production-canon-json" value={canonText} onChange={(event) => setCanonText(event.target.value)} className="min-h-56 font-mono text-xs" /><p className="text-xs text-muted-foreground">Edit descriptive fields and aliases; do not change IDs. Existing entries cannot be removed—archive them instead. Save uses revision checking to prevent overwriting another tab's edits.</p></div>
      <div className="flex flex-wrap items-center gap-2"><Button onClick={saveCanon} disabled={busy !== ""}><Save className="mr-2 h-4 w-4" />{busy === "canon-save" ? "Saving…" : "Save character/world bible"}</Button><Button variant="outline" onClick={reloadCanon} disabled={busy !== ""}>Reload latest</Button><Badge variant="outline">Canon revision {canon.revision}</Badge></div>
    </CardContent></Card> : null}

    {workspaceStage === "assets" && run && canon ? <Card aria-label="Generate project image candidates"><CardHeader><CardTitle>Generate character or world images</CardTitle><CardDescription>The Director can prepare the prompt. Manual/Semi with human image selection queues four candidates; Director-owned selection queues one candidate, reviews its saved output, and allows at most two deterministic retakes. All work remains in the website queue and accepted files are indexed without another project copy. Qwen Edit stages selected project images under a durable owner.</CardDescription></CardHeader><CardContent className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2"><div className="space-y-2"><Label htmlFor="production-image-workflow">Image model</Label><select id="production-image-workflow" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={imageWorkflowId} onChange={(event) => { setImageWorkflowId(event.target.value); if (event.target.value === "qwen_image_2512") { setImageWidth(1664); setImageHeight(928); setImageSteps(50); } else if (event.target.value === "qwen_image_edit_2511") { setImageWidth(1024); setImageHeight(1024); setImageSteps(4); } else { setImageWidth(1280); setImageHeight(720); setImageSteps(8); } }}><option value="z_image_turbo" disabled={!imageWorkflowReadiness?.find((workflow) => workflow.workflow_id === "z_image_turbo")?.available}>Z-Image Turbo · fast text-to-image</option><option value="qwen_image_2512" disabled={!imageWorkflowReadiness?.find((workflow) => workflow.workflow_id === "qwen_image_2512")?.available}>Qwen Image 2512 · quality text-to-image</option><option value="qwen_image_edit_2511" disabled={!imageWorkflowReadiness?.find((workflow) => workflow.workflow_id === "qwen_image_edit_2511")?.available}>Qwen Image Edit 2511 · image edit</option></select>{!imageWorkflowReadiness ? <p role="status" className="text-xs text-muted-foreground">Checking exact workflow, model, node, and smoke readiness…</p> : !selectedImageWorkflowReady ? <p role="alert" className="text-xs text-destructive">{selectedImageWorkflow?.disabled_reason || "Image workflow readiness could not be verified."}</p> : null}</div><div className="space-y-2"><Label htmlFor="production-image-role">Save as</Label><select id="production-image-role" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={imageAssetRole} onChange={(event) => { setImageAssetRole(event.target.value); setImageEntityId(""); }}><option value="character_master">Character master</option><option value="world_master">World/location master</option><option value="scene_board">Scene board</option><option value="first_frame">First frame</option><option value="last_frame">Last frame</option></select></div></div>
      {directorControls("image_candidate_selection") && ["character_master", "world_master"].includes(imageAssetRole) ? <div className="space-y-2"><Label htmlFor="production-image-identity">Canon identity for automatic review</Label><select id="production-image-identity" className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={imageEntityId} onChange={(event) => setImageEntityId(event.target.value)}><option value="">Choose an active {imageAssetRole === "character_master" ? "character" : "world"}</option>{(imageAssetRole === "character_master" ? canon.characters : canon.worlds).filter((entity) => entity.status === "active").map((entity: any) => { const id = imageAssetRole === "character_master" ? entity.character_id : entity.world_id; return <option key={id} value={id}>{entity.display_name || id}</option>; })}</select><p className="text-xs text-muted-foreground">The Director’s accepted master is assigned to this exact canon ID. Ambiguous reviews remain blocked for you to resolve.</p></div> : null}
      <div className="space-y-2"><Label htmlFor="production-image-prompt">Image prompt</Label><Textarea id="production-image-prompt" value={imagePrompt} onChange={(event) => setImagePrompt(event.target.value)} maxLength={20000} className="min-h-28" placeholder="Describe the character, location, or intended composition. This is an image-model prompt, not the H3 video prompt." /></div>
      {imageWorkflowId === "qwen_image_edit_2511" ? <div className="space-y-2"><Label htmlFor="production-edit-sources">Source images (1–3)</Label><select id="production-edit-sources" multiple size={4} className="w-full rounded-md border border-input bg-background p-2 text-sm" value={editSourceAssetIds} onChange={(event) => { const next = Array.from(event.target.selectedOptions, (option) => option.value); if (next.length <= 3) setEditSourceAssetIds(next); }}><option disabled value="">Select project images</option>{assets.filter((asset) => asset.kind === "image" && !asset.source?.startsWith("external_") && (!asset.roles.includes("image_candidate") || asset.metadata?.production_image_job?.accepted === true)).map((asset) => <option key={asset.asset_id} value={asset.asset_id}>{asset.filename} · {asset.roles.join(", ")}</option>)}</select><p className="text-xs text-muted-foreground">Images are copied into ComfyUI input under a batch-owned manifest and retained until all candidates finish.</p></div> : null}
      <div className="grid gap-3 sm:grid-cols-3"><div className="space-y-2"><Label htmlFor="production-image-width">Width</Label><Input id="production-image-width" type="number" min={256} max={2048} step={8} value={imageWidth} onChange={(event) => setImageWidth(Number(event.target.value))} /></div><div className="space-y-2"><Label htmlFor="production-image-height">Height</Label><Input id="production-image-height" type="number" min={256} max={2048} step={8} value={imageHeight} onChange={(event) => setImageHeight(Number(event.target.value))} /></div><div className="space-y-2"><Label htmlFor="production-image-steps">Steps</Label><Input id="production-image-steps" type="number" min={imageWorkflowId === "z_image_turbo" || imageWorkflowId === "qwen_image_edit_2511" ? 4 : 20} max={imageWorkflowId === "z_image_turbo" || imageWorkflowId === "qwen_image_edit_2511" ? 16 : 80} value={imageSteps} onChange={(event) => setImageSteps(Number(event.target.value))} /></div></div>
      <Button onClick={() => void generateProjectImageCandidates()} disabled={busy !== "" || !selectedImageWorkflowReady || !imagePrompt.trim() || imageWidth % 8 !== 0 || imageHeight % 8 !== 0 || (directorControls("image_candidate_selection") && ["character_master", "world_master"].includes(imageAssetRole) && !imageEntityId) || (imageWorkflowId === "qwen_image_edit_2511" && (editSourceAssetIds.length < 1 || editSourceAssetIds.length > 3))}><Sparkles className="mr-2 h-4 w-4" />{busy === "image-candidates" ? "Adding candidates to queue…" : "Generate image candidates"}</Button>
      {imageBatch ? <div role="status" aria-label="Image candidate job status" className="space-y-2 rounded-md border p-3"><p className="text-sm font-medium">Candidate batch {imageBatch.batch_id}</p>{flattenImageJobs(imageBatch.jobs).map((job) => { const asset = assets.find((row) => row.asset_id === job.output_asset_id); return <div key={job.job_id} className="flex flex-wrap items-center justify-between gap-2 rounded bg-muted/40 p-2 text-sm"><span>Candidate {job.candidate_index}</span><Badge variant={job.status === "failed" || job.status === "recovery_required" || job.director_review?.resolution_status === "blocked" ? "destructive" : job.director_review?.resolution_status === "accepted" ? "default" : "secondary"}>{(job.director_review?.resolution_status || job.status).replaceAll("_", " ")}</Badge>{asset ? <span className="text-xs text-muted-foreground">Saved: {asset.filename}</span> : null}{job.director_review?.resolution_status === "reviewing" ? <p className="w-full text-xs text-muted-foreground">Director review in progress (attempt {job.director_review.attempt_count}).</p> : null}{job.director_review?.resolution_status === "review_recovery_pending" ? <p className="w-full text-xs text-muted-foreground">Director review worker stopped; the saved candidate will be retried after its recovery lease expires (attempt {job.director_review.attempt_count}).</p> : null}{job.director_review?.decision?.reason ? <p className="w-full text-xs text-muted-foreground">Director: {job.director_review.decision.reason}</p> : null}{job.error ? <pre className="w-full whitespace-pre-wrap text-xs text-destructive">{JSON.stringify(job.error, null, 2)}</pre> : null}</div>; })}<p className="text-xs text-muted-foreground">Unknown ComfyUI submissions are not retried automatically; they require reconciliation by their recorded prompt ID.</p></div> : null}
    </CardContent></Card> : null}

    {(workspaceStage === "assets" || workspaceStage === "voice") && run && project ? <Card id="production-asset-library"><CardHeader><CardTitle>{workspaceStage === "assets" ? "Project asset library" : "Voice and audio"}</CardTitle><CardDescription>{workspaceStage === "assets" ? "Uploads are stored once under this project. Repertoire sources remain linked, not copied." : "Select or automatically assign a project-local voice for each character, with stable speaker identities across cuts."}</CardDescription></CardHeader><CardContent className="space-y-5">
      <div className="grid gap-3 md:grid-cols-[minmax(12rem,0.5fr)_minmax(16rem,1fr)_auto]"><div className="space-y-2"><Label htmlFor="production-asset-role">Asset purpose</Label><select id="production-asset-role" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={assetRole} onChange={(event) => setAssetRole(event.target.value)}><option value="character_master">Character reference image</option><option value="world_master">World/location reference image</option><option value="first_frame">First frame</option><option value="last_frame">Last frame</option><option value="action_reference_video">Action/reference video</option><option value="voice_master">Voice master (30s+)</option><option value="project_audio">Other project audio</option><option value="project_video">Other project video</option></select></div><div className="space-y-2"><Label htmlFor="production-asset-file">Choose image, video, or audio</Label><Input id="production-asset-file" type="file" accept="image/*,video/*,audio/*" onChange={(event) => setAssetFile(event.target.files?.[0] || null)} /></div><Button className="self-end" onClick={uploadAsset} disabled={busy !== "" || !assetFile}><Upload className="mr-2 h-4 w-4" />{busy === "asset-upload" ? "Uploading…" : "Upload to project"}</Button></div>
      <div className="space-y-3 rounded-lg border p-4"><div className="flex flex-wrap items-end gap-3"><div className="min-w-56 flex-1 space-y-2"><Label htmlFor="repertoire-search">Search shared Video Repertoire</Label><Input id="repertoire-search" value={repertoireQuery} onChange={(event) => setRepertoireQuery(event.target.value)} placeholder="Filter by title, filename, channel, or category" /></div><div className="w-full space-y-2 sm:w-44"><Label htmlFor="repertoire-kind">Media type</Label><select id="repertoire-kind" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={repertoireKind} onChange={(event) => { setRepertoireKind(event.target.value as "video" | "audio"); setRepertoireAssetId(""); }}><option value="video">Video</option><option value="audio">Audio</option></select></div><div className="min-w-64 flex-1 space-y-2"><Label htmlFor="repertoire-result">Shared asset</Label><select id="repertoire-result" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={repertoireAssetId} onChange={(event) => setRepertoireAssetId(event.target.value)}><option value="">{repertoireLoaded ? "Choose a shared asset" : "Load the shared library first"}</option>{repertoireKind === "video" ? filteredRepertoireVideos.map((item) => <option key={item.asset_id} value={item.asset_id}>{item.title || item.filename} · {item.media.duration ? `${Number(item.media.duration).toFixed(1)}s` : "video"}</option>) : filteredRepertoireAudios.map((item) => <option key={item.asset_id} value={item.asset_id}>{item.label || item.filename} · {item.category}</option>)}</select></div><Button variant="outline" onClick={loadRepertoire} disabled={busy !== ""}><Search className="mr-2 h-4 w-4" />{busy === "repertoire-load" ? "Loading…" : "Load shared library"}</Button><Button onClick={linkRepertoireAsset} disabled={busy !== "" || !repertoireAssetId}><Link2 className="mr-2 h-4 w-4" />{busy === "repertoire-link" ? "Linking…" : "Link without copying"}</Button></div><p className="text-xs text-muted-foreground">Keyword filtering only. Linking stores an ID and preview URL; shared source media stays owned by Video Repertoire and is never copied into this project.</p>{repertoireLoaded && (repertoireKind === "video" ? filteredRepertoireVideos.length === 0 : filteredRepertoireAudios.length === 0) ? <p role="status" className="text-sm text-muted-foreground">No matching available {repertoireKind} assets.</p> : null}</div>
      {assets.length ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{assets.map((asset) => {
        const dialogue = asset.metadata?.dialogue_take;
        const originalDialogue = asset.roles.includes("dialogue_take") && dialogue?.recording_status === "original_recording";
        const sourceJob = dialogueConversionJob?.source_asset_id === asset.asset_id ? dialogueConversionJob : null;
        return <article key={asset.asset_id} className="space-y-2 rounded-lg border p-3"><div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="truncate text-sm font-medium">{asset.filename}</p><p className="text-xs text-muted-foreground">{asset.kind} · {asset.roles.join(", ")} · {asset.media?.duration_seconds ? `${Number(asset.media.duration_seconds).toFixed(1)}s` : asset.source === "external_video_repertoire_video" || asset.source === "external_video_repertoire_audio" ? "Video Repertoire link" : "project file"}</p></div><Badge variant="outline">{asset.kind}</Badge></div>{asset.source?.startsWith("external_") ? <><p className="text-xs text-muted-foreground">Shared Video Repertoire source; original is not copied.</p>{asset.kind === "video" ? <video className="max-h-48 w-full rounded" controls preload="metadata" src={asset.content_url} /> : <audio className="w-full" controls preload="none" src={asset.content_url} />}</> : asset.kind === "image" ? <img className="max-h-40 w-full rounded object-contain" src={`/api/projects/${encodeURIComponent(project.id)}/production/v2/assets/${encodeURIComponent(asset.asset_id)}/content`} alt={asset.filename} /> : asset.kind === "video" ? <video className="max-h-48 w-full rounded" controls preload="metadata" src={`/api/projects/${encodeURIComponent(project.id)}/production/v2/assets/${encodeURIComponent(asset.asset_id)}/content`} /> : <audio className="w-full" controls preload="none" src={`/api/projects/${encodeURIComponent(project.id)}/production/v2/assets/${encodeURIComponent(asset.asset_id)}/content`} />}{asset.roles.includes("image_candidate") && asset.metadata?.approval_status !== "accepted" ? <div className="space-y-2 rounded-md border border-primary/30 p-2"><p className="text-xs">Unaccepted generated candidate · intended role: {String(asset.metadata?.production_image_job?.intended_role || "image").replaceAll("_", " ")}. It will not be used as a canon master until accepted.</p>{workspaceStage === "assets" && !directorControls("image_candidate_selection") ? <Button variant="outline" onClick={() => void acceptImageCandidate(asset)} disabled={busy !== ""}>{busy === `accept-image:${asset.asset_id}` ? "Accepting…" : "Accept candidate"}</Button> : <p className="text-xs text-muted-foreground">Director review is pending or blocked; this candidate remains unaccepted. Check its batch decision before use.</p>}</div> : null}{asset.roles.includes("voice_master") ? <p className="text-xs text-muted-foreground">Audition here; a bound clean sample can be cropped into an H3 2–15s reference without altering this master.</p> : null}{originalDialogue && workspaceStage === "voice" ? <div className="space-y-2 rounded-md bg-muted/40 p-3"><p className="text-xs">Original take · {dialogue.speaker_id} · “{dialogue.transcript}”</p><p className="text-xs text-muted-foreground">RVC uses an installed local model, not the character’s bound voice master. Choose a model you have permission to use; the original stays unchanged.</p>{localRvcModels.length ? <><Label htmlFor="dialogue-rvc-model">Installed local RVC model</Label><select id="dialogue-rvc-model" className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={selectedRvcModel} onChange={(event) => setSelectedRvcModel(event.target.value)}><option value="">Choose installed model</option>{localRvcModels.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}</select><Button variant="outline" onClick={() => void convertDialogueTake(asset.asset_id)} disabled={busy !== "" || !selectedRvcModel || Boolean(sourceJob && ["queued", "preparing", "submitting", "running", "recovery_required"].includes(sourceJob.status))}>{busy === `dialogue-convert:${asset.asset_id}` ? "Queueing local conversion…" : "Convert with local RVC"}</Button></> : <p role="status" className="text-xs">No local RVC models found. Install/select a model in the local audio environment first; nothing will be downloaded automatically.</p>}{sourceJob ? <p role="status" className="text-xs">Conversion {sourceJob.status}{sourceJob.error ? `: ${sourceJob.error}` : ""}</p> : null}</div> : null}{workspaceStage === "assets" && canon && (asset.roles.includes("character_master") || asset.roles.includes("world_master")) ? (() => {
          const character = asset.roles.includes("character_master");
          const role = character ? "character_master" : "world_master";
          const field = character ? "character_id" : "world_id";
          const assigned = asset.metadata?.[field];
          const choices = character ? canon.characters : canon.worlds;
          return assigned ? <p className="text-xs">Assigned to {choices.find((row) => row[field] === assigned)?.display_name || assigned}</p> : <div className="space-y-2"><label className="text-xs" htmlFor={`master-${asset.asset_id}`}>Assign master to {character ? "character" : "world"}</label><select id={`master-${asset.asset_id}`} className="h-10 w-full rounded-md border bg-background px-2 text-sm" value={masterIdentities[asset.asset_id] || ""} onChange={(event) => setMasterIdentities((previous) => ({ ...previous, [asset.asset_id]: event.target.value }))}><option value="">Choose canon identity</option>{choices.filter((row) => row.status === "active").map((row) => <option key={row[field]} value={row[field]}>{row.display_name}</option>)}</select><Button variant="outline" onClick={() => assignMaster(asset, role)} disabled={busy !== "" || !masterIdentities[asset.asset_id] || directorControls("image_candidate_selection")}>Assign master</Button></div>;
        })() : null}</article>;
      })}</div> : <p className="rounded-lg border p-6 text-center text-sm text-muted-foreground">No project assets yet. Upload a character/world image, a voice master, or a reference clip.</p>}
      {workspaceStage === "voice" && canon?.characters?.length ? <div id="production-voices" className="space-y-3 rounded-lg border p-4">
        <div><h3 className="font-medium">Character voice bindings</h3><p className="text-xs text-muted-foreground">Manual/Semi lets you audition and choose. Full mode makes one reproducible project-local random choice per character and preserves it across cuts.</p></div>
        {directorControls("voice_selection") ? <div role="status" className="space-y-2 rounded-md border p-3"><p className="text-sm">Voice choices are selected from accepted project voice masters of at least 30 seconds. No voice is cloned or uploaded.</p><Button className="h-auto min-h-10 w-full whitespace-normal py-2 text-left sm:w-auto" variant="outline" onClick={prepareAutomaticVoices} disabled={busy !== ""}>{busy === "automatic-voices" ? "Preparing saved choices…" : "Prepare / restore automatic voice choices"}</Button></div> : <><div className="grid gap-3 md:grid-cols-2"><div className="space-y-2"><Label htmlFor="voice-character">Character</Label><select id="voice-character" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={voiceCharacterId} onChange={(event) => setVoiceCharacterId(event.target.value)}><option value="">Choose character</option>{canon.characters.filter((row) => row.status === "active").map((row) => <option key={row.character_id} value={row.character_id}>{row.display_name}</option>)}</select></div><div className="space-y-2"><Label htmlFor="voice-master">Eligible voice master</Label><select id="voice-master" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={voiceAssetId} onChange={(event) => setVoiceAssetId(event.target.value)}><option value="">Choose voice (30 seconds or longer)</option>{assets.filter((asset) => asset.kind === "audio" && asset.roles.includes("voice_master") && Number(asset.media?.duration_seconds || 0) >= 30).map((asset) => <option key={asset.asset_id} value={asset.asset_id}>{asset.filename} · {Number(asset.media?.duration_seconds).toFixed(1)}s</option>)}</select></div></div><Button onClick={bindVoice} disabled={busy !== "" || !voiceCharacterId || !voiceAssetId}>Bind voice to character</Button></>}
        {voiceBindings.length ? <ul aria-label="Saved character voice choices" className="space-y-2">{voiceBindings.map((binding: any) => <li key={binding.character_id} className="rounded bg-muted/50 px-3 py-2 text-sm">{canon.characters.find((character) => character.character_id === binding.character_id)?.display_name || binding.character_id} → {assets.find((asset) => asset.asset_id === binding.voice_asset_id)?.filename || binding.voice_asset_id} ({binding.speaker_id}){binding.strategy === "seeded_random" ? " · saved random choice" : " · manual"}</li>)}</ul> : null}
        {controlMode !== "fully_automated" && voiceBindings.find((binding: any) => binding.character_id === voiceCharacterId) ? <div className="space-y-3 rounded-md border p-3" aria-label="Recorded dialogue take"><div><h4 className="text-sm font-medium">Save an exact recorded dialogue take</h4><p className="text-xs text-muted-foreground">Record the line with a local recorder, then upload the original audio and exact transcript. It is linked to the selected character’s saved speaker ID and kept unchanged. No voice is cloned or sent to a hosted service. After saving, use the take’s local RVC control in this stage if an installed model is available.</p></div><div className="space-y-2"><Label htmlFor="dialogue-take-transcript">Exact spoken words</Label><Textarea id="dialogue-take-transcript" value={dialogueTranscript} onChange={(event) => setDialogueTranscript(event.target.value)} maxLength={5000} placeholder="Type exactly what is spoken in the recording." /></div><div className="space-y-2"><Label htmlFor="dialogue-take-file">Original recorded audio</Label><Input id="dialogue-take-file" type="file" accept="audio/wav,audio/mpeg,audio/mp4,audio/ogg,audio/flac,audio/aac" onChange={(event) => setDialogueTakeFile(event.target.files?.[0] || null)} /></div><Button variant="outline" onClick={uploadDialogueTake} disabled={busy !== "" || !dialogueTranscript.trim() || !dialogueTakeFile}>{busy === "dialogue-take-upload" ? "Saving recording…" : "Save original dialogue take"}</Button></div> : null}
        {!directorControls("voice_selection") ? <div className="space-y-3 rounded-md border p-3"><div><h4 className="text-sm font-medium">Prepare H3 voice reference</h4><p className="text-xs text-muted-foreground">Create an explicit 2–15 second mono 32 kHz PCM excerpt from the selected character's bound master. The source remains unchanged and the excerpt is added as a project asset.</p></div><div className="grid gap-3 sm:grid-cols-2"><div className="space-y-2"><Label htmlFor="voice-excerpt-start">Start time (seconds)</Label><Input id="voice-excerpt-start" type="number" min="0" step="0.1" value={voiceExcerptStart} onChange={(event) => setVoiceExcerptStart(Number(event.target.value))} /></div><div className="space-y-2"><Label htmlFor="voice-excerpt-duration">Excerpt duration (2–15 seconds)</Label><Input id="voice-excerpt-duration" type="number" min="2" max="15" step="0.1" value={voiceExcerptDuration} onChange={(event) => setVoiceExcerptDuration(Number(event.target.value))} /></div></div><Button variant="outline" onClick={createVoiceExcerpt} disabled={busy !== "" || !voiceCharacterId || !voiceAssetId || voiceExcerptStart < 0 || voiceExcerptDuration < 2 || voiceExcerptDuration > 15 || voiceExcerptStart + voiceExcerptDuration > Number(assets.find((asset) => asset.asset_id === voiceAssetId)?.media?.duration_seconds || 0)}>{busy === "voice-excerpt" ? "Preparing excerpt…" : "Create H3 voice reference"}</Button></div> : null}
        <div className="space-y-3 rounded-md border p-3" aria-label="Optional audio sidecar generation"><div><h4 className="text-sm font-medium">Optional music or sound-effect sidecar</h4><p className="text-xs text-muted-foreground">Uses the installed local ACE-Step or Control-Foley workflow. Saved outputs are separate project assets with their own role and start time; H3 native audio stays intact and these assets are never treated as voice references.</p></div><div className="grid gap-3 sm:grid-cols-2"><div className="space-y-2"><Label htmlFor="production-sidecar-kind">Asset type</Label><select id="production-sidecar-kind" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={sidecarKind} onChange={(event) => { const kind = event.target.value as "music" | "sfx"; setSidecarKind(kind); setSidecarDuration(kind === "music" ? Math.max(5, sidecarDuration) : Math.min(30, sidecarDuration)); }}><option value="music">Music candidate</option><option value="sfx">Sound-effect candidate</option></select></div><div className="space-y-2"><Label htmlFor="production-sidecar-duration">Duration seconds</Label><Input id="production-sidecar-duration" type="number" min={sidecarKind === "music" ? 5 : 0.7} max={sidecarKind === "music" ? 240 : 30} step="0.1" value={sidecarDuration} onChange={(event) => setSidecarDuration(Number(event.target.value))} /></div><div className="space-y-2"><Label htmlFor="production-sidecar-start">Start time in edit (seconds)</Label><Input id="production-sidecar-start" type="number" min="0" step="0.1" value={sidecarStart} onChange={(event) => setSidecarStart(Number(event.target.value))} /></div></div><div className="space-y-2"><Label htmlFor="production-sidecar-prompt">Music description or sound cue</Label><Textarea id="production-sidecar-prompt" value={sidecarPrompt} onChange={(event) => setSidecarPrompt(event.target.value)} maxLength={4000} placeholder={sidecarKind === "music" ? "e.g. restrained instrumental strings, hopeful but unresolved" : "e.g. close wooden door latch, then a short heavy close"} /></div><Button variant="outline" onClick={() => void queueAudioSidecar()} disabled={busy !== "" || !sidecarPrompt.trim() || sidecarDuration < (sidecarKind === "music" ? 5 : 0.7) || sidecarDuration > (sidecarKind === "music" ? 240 : 30)}>{busy === "audio-sidecar" ? "Queueing local audio…" : `Generate ${sidecarKind === "music" ? "music" : "sound effect"} candidate`}</Button>{sidecarJob ? <p role="status" className="text-xs">Sidecar {sidecarJob.job_id}: {String(sidecarJob.status).replace(/_/g, " ")}{sidecarJob.production_asset_id ? ` · saved as ${sidecarJob.production_asset_id}` : " · refresh the asset list after completion to audition it"}{sidecarJob.error ? ` · ${sidecarJob.error}` : ""}</p> : null}</div>
      </div> : null}
    </CardContent></Card> : null}

    {workspaceStage === "shots" && run && revision?.review_status === "accepted" ? <Card id="production-shots"><CardHeader><CardTitle>Scenes and text stages</CardTitle><CardDescription>Author stable-ID units yourself or ask the Director to draft them. Manual inputs are stored as review revisions; Full mode stays Director-controlled. H3 produces its own native audio; selected voice references guide timbre, not exact speech or a second dialogue track. Music and sound effects stay separate and are never auto-selected as voice references.</CardDescription></CardHeader><CardContent className="space-y-4">
      <div className="space-y-2"><Label htmlFor="text-stage">Stage</Label><select id="text-stage" className="h-10 w-full max-w-sm rounded-md border border-input bg-background px-3 text-sm" value={textStage} onChange={(event) => void selectTextStage(event.target.value)}><option value="scenes">Scenes</option><option value="dialogue">Dialogue</option><option value="visual_briefs">Visual briefs</option><option value="shot_plans">Shot plans</option></select></div>
      {!directorControls("story_review") && (textStage === "scenes" || textStage === "dialogue") ? <div className="space-y-3 rounded-md border p-4"><div><h3 className="font-medium">Build a {textStage === "scenes" ? "scene" : "dialogue beat"}</h3><p className="text-xs text-muted-foreground">This adds a stable-ID unit to your review draft. Source chunk IDs are optional links such as story_chunk_0001.</p></div>{textStage === "scenes" ? <div className="grid gap-3 md:grid-cols-2"><div className="space-y-2"><Label htmlFor="manual-scene-title">Scene title</Label><Input id="manual-scene-title" value={unitTitle} onChange={(event) => setUnitTitle(event.target.value)} placeholder="Opening scene" /></div><div className="space-y-2"><Label htmlFor="manual-scene-source-chunks">Source chunk IDs (comma-separated)</Label><Input id="manual-scene-source-chunks" value={unitSourceChunks} onChange={(event) => setUnitSourceChunks(event.target.value)} placeholder="story_chunk_0001" /></div><div className="space-y-2 md:col-span-2"><Label htmlFor="manual-scene-description">What happens in this scene?</Label><Textarea id="manual-scene-description" value={unitDescription} onChange={(event) => setUnitDescription(event.target.value)} className="min-h-24" /></div></div> : <div className="grid gap-3 md:grid-cols-2"><div className="space-y-2"><Label htmlFor="manual-dialogue-speaker">Speaker ID (optional)</Label><Input id="manual-dialogue-speaker" value={unitSpeaker} onChange={(event) => setUnitSpeaker(event.target.value)} placeholder="character-uuid or S1" /></div><div className="space-y-2"><Label htmlFor="manual-dialogue-scene">Scene unit ID (optional)</Label><Input id="manual-dialogue-scene" value={unitSceneId} onChange={(event) => setUnitSceneId(event.target.value)} placeholder="scene-001" /></div><div className="space-y-2"><Label htmlFor="manual-dialogue-source-chunks">Source chunk IDs (comma-separated)</Label><Input id="manual-dialogue-source-chunks" value={unitSourceChunks} onChange={(event) => setUnitSourceChunks(event.target.value)} placeholder="story_chunk_0001" /></div><div className="space-y-2 md:col-span-2"><Label htmlFor="manual-dialogue-exact-words">Exact dialogue words</Label><Textarea id="manual-dialogue-exact-words" value={unitDialogue} onChange={(event) => setUnitDialogue(event.target.value)} className="min-h-24" placeholder="Enter the words exactly as they should be spoken." /></div></div>}<Button type="button" variant="outline" onClick={addStructuredTextUnit} disabled={busy !== ""}>{textStage === "scenes" ? "Add scene to draft" : "Add dialogue beat to draft"}</Button></div> : null}
      <div className="space-y-2"><Label htmlFor="text-units">Stable-ID units (JSON)</Label><Textarea id="text-units" value={textUnits} onChange={(event) => { setTextUnits(event.target.value); setTextStageDirty(true); }} className="min-h-48 font-mono text-xs" /><p className="text-xs text-muted-foreground">Each unit needs a unique unit_id and content object. Link relevant story chunks with source_chunk_ids; never send the entire project graph as context.</p></div>
      <div className="flex flex-wrap gap-2">{!directorControls("story_review") ? <Button variant="outline" onClick={() => createTextRevision(true)} disabled={busy !== ""}><Save className="mr-2 h-4 w-4" />Save my text for review</Button> : null}<Button onClick={() => createTextRevision(false)} disabled={busy !== ""}><Sparkles className="mr-2 h-4 w-4" />Ask Director to draft this stage</Button></div>
      {textRevision ? <div className="space-y-3 rounded-lg border p-4"><div className="flex items-center gap-2"><Badge variant={textRevision.review_status === "accepted" ? "default" : "secondary"}>{String(textRevision.review_status).replaceAll("_", " ")}</Badge><span className="text-xs text-muted-foreground">{textRevision.revision_id}</span></div><pre className="max-h-80 overflow-auto rounded bg-muted p-3 text-xs">{JSON.stringify(textRevision.items, null, 2)}</pre>{!directorControls("story_review") && textRevision.review_status !== "accepted" ? <Button onClick={acceptTextRevision} disabled={busy !== ""}><Check className="mr-2 h-4 w-4" />Accept this text revision</Button> : null}</div> : null}
      {textStage === "shot_plans" && textRevision?.review_status === "accepted" ? <div className="space-y-4 rounded-lg border border-primary/30 p-4"><div><h3 className="font-medium">Refine a shot prompt</h3><p className="text-xs text-muted-foreground">The Director proposes a prompt change. It cannot replace or reorder the selected references; accepting creates a new revision.</p></div><div className="grid gap-3 md:grid-cols-2"><div className="space-y-2"><Label htmlFor="refine-shot">Shot</Label><select id="refine-shot" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={refineShotId} onChange={(event) => { setRefineShotId(event.target.value); setRefineProposal(null); }}><option value="">Choose a shot</option>{(textRevision.items || []).map((item: any) => <option key={item.unit_id} value={item.unit_id}>{item.unit_id}</option>)}</select></div><div className="space-y-2"><Label htmlFor="refine-instruction">What should change?</Label><Input id="refine-instruction" value={refineInstruction} onChange={(event) => setRefineInstruction(event.target.value)} placeholder="For example: use softer dawn light" /></div></div><Button variant="outline" onClick={createRefineProposal} disabled={busy !== "" || !refineShotId || !refineInstruction.trim()}>{busy === "refine" ? "Refining…" : "Create proposal"}</Button>{refineProposal ? <div className="space-y-3 rounded-md bg-muted/60 p-3"><div className="flex items-center gap-2"><Badge variant={refineProposal.lint?.ok ? "default" : "destructive"}>{refineProposal.lint?.ok ? "Valid proposal" : "Needs correction"}</Badge><span className="text-xs">{refineProposal.applied ? "Accepted" : "Not applied"}</span></div><p className="text-sm">{(refineProposal.change_summary || []).join(" · ")}</p><pre aria-label="Refine prompt diff" className="max-h-64 overflow-auto whitespace-pre-wrap rounded border bg-background p-3 text-xs">{refineProposal.diff || refineProposal.proposed_prompt}</pre>{refineProposal.lint?.ok && !refineProposal.applied && !directorControls("shot_workflow_render_approval") ? <Button onClick={acceptRefineProposal} disabled={busy !== ""}><Check className="mr-2 h-4 w-4" />Accept as new revision</Button> : null}</div> : null}</div> : null}
      {textStage === "shot_plans" && textRevision?.review_status === "accepted" ? <div className="space-y-4 rounded-lg border p-4"><div><h3 className="font-medium">Shot composer · H3 workflow preview</h3><p className="text-xs text-muted-foreground">Choose project references for R2V, or leave them empty to use the separately validated H3 text-to-video workflow. Zero-reference shots support 5–10 seconds; referenced shots support 5–15 seconds. Final preset is 0.98 (1344×768); preview preset is 0.4 (864×480). Preview validates the graph and does not submit GPU work.</p></div>{composerDraftStale ? <p role="alert" className="rounded border border-amber-500/40 bg-amber-500/5 p-3 text-sm">This saved draft belongs to an older accepted shot-plan revision. Reload the current shot plan before editing or saving it.</p> : null}{composerDraftError ? <p role="alert" className="rounded border border-destructive/40 bg-destructive/5 p-3 text-sm">{composerDraftError}</p> : null}<div className="grid gap-3 md:grid-cols-3"><div className="space-y-2"><Label htmlFor="composer-shot">Accepted shot</Label><select id="composer-shot" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={composerShotId} onChange={(event) => selectComposerShot(event.target.value)}><option value="">Choose a shot</option>{(textRevision.items || []).map((item: any) => <option key={item.unit_id} value={item.unit_id}>{item.unit_id}</option>)}</select></div><div className="space-y-2"><Label htmlFor="composer-duration">Duration (5–{composerDurationMax} sec)</Label><Input id="composer-duration" type="number" min={5} max={composerDurationMax} value={composerDuration} onChange={(event) => setComposerDuration(Number(event.target.value))} /></div><div className="space-y-2"><Label htmlFor="composer-resolution">H3 output preset</Label><select id="composer-resolution" className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={composerResolutionPreset} onChange={(event) => setComposerResolutionPreset(Number(event.target.value))}><option value={0.98}>Final · 0.98 · 1344×768</option><option value={0.4}>Preview · 0.4 · 864×480</option></select></div></div><div className="space-y-2"><Label htmlFor="composer-prompt">Director's main H3 prompt</Label><Textarea id="composer-prompt" value={composerPrompt} onChange={(event) => setComposerPrompt(event.target.value)} className="min-h-36" placeholder="Shot prompt from accepted shot plan; edit before validating." /></div><div className="grid gap-3 md:grid-cols-3"><div className="space-y-2"><Label htmlFor="composer-images">Image references (up to 9)</Label><select id="composer-images" multiple size={5} className="w-full rounded-md border border-input bg-background p-2 text-sm" value={selectedImageIds} onChange={(event) => { const next = Array.from(event.target.selectedOptions, (option) => option.value); if (next.length <= 9) setSelectedImageIds(next); }}><option disabled value="">Select images</option>{assets.filter((row) => row.kind === "image" && !row.source?.startsWith("external_")).map((asset) => <option key={asset.asset_id} value={asset.asset_id}>{asset.filename} · {asset.roles.join(", ")}</option>)}</select></div><div className="space-y-2"><Label htmlFor="composer-videos">Video references (up to 3)</Label><select id="composer-videos" multiple size={5} className="w-full rounded-md border border-input bg-background p-2 text-sm" value={selectedVideoIds} onChange={(event) => { const next = Array.from(event.target.selectedOptions, (option) => option.value); if (next.length <= 3) setSelectedVideoIds(next); }}><option disabled value="">Select videos</option>{assets.filter((row) => row.kind === "video" && !row.source?.startsWith("external_")).map((asset) => <option key={asset.asset_id} value={asset.asset_id}>{asset.filename} · {Number(asset.media?.duration_seconds || 0).toFixed(1)}s</option>)}</select><label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={pairVideoAudio} onChange={(event) => setPairVideoAudio(event.target.checked)} />Include each selected video's own soundtrack</label></div><div className="space-y-2"><Label htmlFor="composer-audios">Standalone audio refs (up to 3)</Label><select id="composer-audios" multiple size={5} className="w-full rounded-md border border-input bg-background p-2 text-sm" value={selectedAudioIds} onChange={(event) => { const next = Array.from(event.target.selectedOptions, (option) => option.value); if (next.length <= 3) setSelectedAudioIds(next); }}><option disabled value="">Choose 2–15s audio</option>{assets.filter((row) => row.kind === "audio" && !row.source?.startsWith("external_") && Number(row.media?.duration_seconds || 0) >= 2 && Number(row.media?.duration_seconds || 0) <= 15).map((asset) => <option key={asset.asset_id} value={asset.asset_id}>{asset.filename} · {Number(asset.media?.duration_seconds || 0).toFixed(1)}s</option>)}</select></div></div><div className="flex flex-wrap items-center gap-2"><Button variant="outline" type="button" onClick={(event) => { event.preventDefault(); void saveComposerDraft(); }} disabled={busy !== "" || !composerShotId || !composerPrompt.trim() || composerDraftStale}>{busy === "shot-draft-save" ? "Saving draft…" : `Save draft${composerDraftRevision ? ` · r${composerDraftRevision}` : ""}`}</Button><Button onClick={previewShot} disabled={busy !== "" || !composerShotId || !composerPrompt.trim() || composerDraftStale}>{busy === "shot-preview" ? "Validating…" : "Preview H3 workflow"}</Button><Badge variant="outline">Preset · {composerResolutionPreset === 0.98 ? "0.98 final" : "0.4 preview"} · 20 steps default</Badge></div>{shotPreview ? <div className="space-y-3 rounded-md bg-muted/50 p-3"><div className="flex flex-wrap gap-2"><Badge variant="outline">{shotPreview.workflow_id}</Badge><Badge variant={shotPreview.workflow_readiness?.available ? "default" : "secondary"}>{shotPreview.workflow_readiness?.available ? "Workflow preflight ready" : "Preview only · render unavailable"}</Badge><Badge variant="outline">{shotPreview.width}×{shotPreview.height} · {shotPreview.frame_count} frames</Badge></div><p className="break-all text-xs text-muted-foreground">Validation hash: {shotPreview.validation_hash}</p><pre aria-label="H3 reference tag map" className="max-h-48 overflow-auto rounded border bg-background p-3 text-xs">{JSON.stringify(shotPreview.reference_map, null, 2)}</pre><details><summary className="cursor-pointer text-sm">Compiled H3 prompt</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded border bg-background p-3 text-xs">{shotPreview.compiled_prompt}</pre></details><section aria-label="Durable shot prompt preparation" className="space-y-3 rounded-md border bg-background p-3"><div className="flex flex-wrap items-center gap-2"><h4 className="font-medium">Prompt preparation</h4>{shotPromptPreparation ? <Badge variant={shotPromptPreparation.status === "failed" || shotPromptPreparation.status === "recovery_required" ? "destructive" : "secondary"}>{String(shotPromptPreparation.status).replaceAll("_", " ")}</Badge> : null}</div><p className="text-xs text-muted-foreground">Prepare from this accepted shot. Director-controlled runs resolve only approved catalog IDs; review the selected references and saved prompt, then validate before any render submission.</p><Button variant="outline" onClick={() => void prepareShotPrompt()} disabled={busy !== "" || !shotPreviewRequest}>{busy === "shot-prompt-prepare" ? "Saving preparation…" : shotPromptPreparation && ["queued", "running"].includes(shotPromptPreparation.status) ? "Preparing…" : "Prepare prompt"}</Button>{shotPromptPreparation?.status === "failed" || shotPromptPreparation?.status === "recovery_required" ? <p role="alert" className="text-sm text-destructive">{shotPromptPreparation.error?.message || "Prompt preparation needs recovery. The saved task was not replayed."}</p> : null}{shotPromptPreparation?.status === "completed" && shotPromptPreparation.result?.accepted === true ? <><div className="space-y-2"><Label htmlFor="prepared-shot-prompt">Prepared prompt · review or edit</Label><Textarea id="prepared-shot-prompt" value={preparedPromptDraft} onChange={(event) => { setPreparedPromptDraft(event.target.value); setPreparedPromptEdited(true); }} className="min-h-36" /><p className="text-xs text-muted-foreground">{preparedPromptEdited ? "Edited prompts use the normal human-authored validation path." : `Accepted preparation · ${shotPromptPreparation.result.prompt_hash || "saved hash unavailable"}`}</p></div><Button onClick={() => void validateReviewedShotPrompt()} disabled={busy !== "" || !preparedPromptDraft.trim()}>{busy === "shot-prompt-validate" ? "Validating reviewed prompt…" : "Validate reviewed prompt"}</Button></> : null}{shotPromptPreparation?.status === "completed" && shotPromptPreparation.result?.accepted !== true ? <p role="alert" className="text-sm text-amber-700">The saved prompt did not pass its reviewer. Revise the main prompt and validate manually; this preparation cannot be attached to a take.</p> : null}</section></div> : null}</div> : null}
    </CardContent></Card> : null}

    {workspaceStage === "shots" && textStage === "shot_plans" && textRevision?.review_status === "accepted" && !shotPreview ? <div className="max-w-lg space-y-2"><Label htmlFor="shot-parent-take">Predecessor take (optional)</Label><select id="shot-parent-take" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={composerParentTakeId} onChange={(event) => setComposerParentTakeId(event.target.value)}><option value="">Start without a predecessor</option>{(run?.takes || []).filter((take: any) => take.shot_id !== composerShotId && ["accepted", "queued", "waiting_for_predecessor", "submitting", "running", "collecting", "recovery_required"].includes(take.status)).map((take: any) => <option key={take.take_id} value={take.take_id}>{take.shot_id} · take {take.attempt || 1} · {String(take.status).replaceAll("_", " ")}</option>)}</select><p className="text-xs text-muted-foreground">A child can wait for this take. Generate & Next links the next cut only when both shots declare the same scene.</p></div> : null}
    {workspaceStage === "shots" && textStage === "shot_plans" && textRevision?.review_status === "accepted" && shotPreview ? <Card aria-label="Shot render controls"><CardHeader><CardTitle>Validated shot render</CardTitle><CardDescription>Preview validates the exact selected inputs without GPU work. Queueing is enabled only when this exact H3 workflow and its models have passed preflight.</CardDescription></CardHeader><CardContent className="space-y-4">
      {!shotPreview.workflow_readiness?.available ? <div role="status" className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm"><p className="font-medium">Render is currently unavailable</p><p className="mt-1 text-muted-foreground">{shotPreview.workflow_readiness?.reason || "Exact workflow/model preflight has not passed. No GPU job was queued."}</p></div> : null}
      {directorControls("shot_workflow_render_approval") ? <p role="status" className="text-sm text-muted-foreground">Director-controlled rendering is unavailable for this run, and human approval cannot override its saved mode. Start a new Manual run or a Semi run with shot, workflow, and render approval enabled to render with human review.</p> : null}
      <div className="space-y-3"><div className="max-w-lg space-y-2"><Label htmlFor="shot-parent-take">Predecessor take (optional)</Label><select id="shot-parent-take" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={composerParentTakeId} onChange={(event) => setComposerParentTakeId(event.target.value)}><option value="">Start without a predecessor</option>{(run?.takes || []).filter((take: any) => take.shot_id !== composerShotId && ["accepted", "queued", "waiting_for_predecessor", "submitting", "running", "collecting", "recovery_required"].includes(take.status)).map((take: any) => <option key={take.take_id} value={take.take_id}>{take.shot_id} · take {take.attempt || 1} · {String(take.status).replaceAll("_", " ")}</option>)}</select><p className="text-xs text-muted-foreground">A child can wait for this take. Generate & Next links the next cut only when both shots declare the same scene.</p></div><div className="flex flex-wrap gap-2"><Button onClick={() => void queueShot()} disabled={busy !== "" || !shotPreview.workflow_readiness?.available || !shotPreviewRequest || (["queued", "running"].includes(shotPromptPreparation?.status) || (shotPromptPreparation?.status === "completed" && shotPromptPreparation.result?.accepted === true && shotPreviewRequest.prompt !== preparedPromptDraft.trim())) || directorControls("shot_workflow_render_approval")}>{busy === "shot-queue" ? "Queueing…" : "Generate this shot"}</Button><Button variant="outline" onClick={() => void queueShot(true)} disabled={busy !== "" || !shotPreview.workflow_readiness?.available || !shotPreviewRequest || (["queued", "running"].includes(shotPromptPreparation?.status) || (shotPromptPreparation?.status === "completed" && shotPromptPreparation.result?.accepted === true && shotPreviewRequest.prompt !== preparedPromptDraft.trim())) || directorControls("shot_workflow_render_approval")}>{busy === "shot-queue" ? "Queueing…" : "Generate & Next"}</Button></div></div>
      
    </CardContent></Card> : null}

    {workspaceStage === "shots" && selectedTake ? <Card aria-label="Selected take review"><CardHeader><CardTitle>Selected take review</CardTitle><CardDescription>Review saved output and status for this take.</CardDescription></CardHeader><CardContent className="space-y-3">
      <div className="flex flex-wrap items-center gap-2"><Badge variant={selectedTake.status === "failed" ? "destructive" : selectedTake.status === "accepted" ? "default" : "secondary"}>{String(selectedTake.status).replaceAll("_", " ")}</Badge><span className="text-xs text-muted-foreground">Take {selectedTake.take_id} · attempt {selectedTake.attempt || 1}{selectedTake.prompt_id ? ` · Comfy prompt ${selectedTake.prompt_id}` : ""}</span></div>
      <DirectorVideoReviewSummary review={selectedTake.director_review} />
      {selectedTake.error ? <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 text-xs">{typeof selectedTake.error === "string" ? selectedTake.error : JSON.stringify(selectedTake.error, null, 2)}</pre> : null}
      {selectedTakeAssets.length ? <div className="grid gap-3 md:grid-cols-2">{selectedTakeAssets.map((asset) => <div key={asset.asset_id} className="space-y-2 rounded border p-2"><p className="text-sm font-medium">{asset.filename} · candidate</p>{asset.kind === "video" ? <video className="max-h-80 w-full rounded bg-black" controls preload="metadata" src={`/api/projects/${encodeURIComponent(project!.id)}/production/v2/assets/${encodeURIComponent(asset.asset_id)}/content`} /> : asset.kind === "audio" ? <audio className="w-full" controls preload="metadata" src={`/api/projects/${encodeURIComponent(project!.id)}/production/v2/assets/${encodeURIComponent(asset.asset_id)}/content`} /> : <img className="max-h-72 w-full rounded object-contain" src={`/api/projects/${encodeURIComponent(project!.id)}/production/v2/assets/${encodeURIComponent(asset.asset_id)}/content`} alt={asset.filename} />}</div>)}</div> : selectedTake.status === "needs_review" ? <p className="text-sm text-muted-foreground">The take completed, but no indexed outputs were returned. Refresh once; if still empty, inspect the run event/error record before accepting.</p> : null}
      {selectedTake.status === "recovery_required" ? <p role="alert" className="text-sm text-amber-700">Remote Comfy state is unresolved. Retry remains disabled until the exact prompt is confirmed absent from ComfyUI queue and history and no output is registered.</p> : null}
      <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={refreshSelectedTake} disabled={busy !== ""}>{busy === "take-refresh" ? "Refreshing…" : "Refresh status"}</Button>{selectedTakeIsActive ? <Button variant="destructive" onClick={() => actOnTake("cancel")} disabled={busy !== ""}>{busy === "take-cancel" ? "Stopping…" : "Stop take"}</Button> : null}{selectedTake?.status === "recovery_required" && selectedTake.prompt_id ? <Button variant="outline" onClick={() => void reconcileAbsentTake()} disabled={busy !== ""}>{busy === "take-reconcile" ? "Checking exact prompt…" : "Check prompt and resolve"}</Button> : null}{selectedTake?.status === "failed" ? <Button variant="outline" onClick={() => actOnTake("retry")} disabled={busy !== ""}>Retry failed take</Button> : null}{selectedTake?.status === "needs_review" && !directorControls("shot_workflow_render_approval") ? <Button onClick={() => actOnTake("accept")} disabled={busy !== ""}>{busy === "take-accept" ? "Accepting…" : "Accept take"}</Button> : null}</div>
    </CardContent></Card> : null}

    {run && run.takes?.length ? <Card aria-label="Production job queue"><CardHeader><CardTitle>Production job queue</CardTitle><CardDescription>All durable takes for this run, including waiting and review-needed outputs. Selecting a take opens its shot review; status refreshes while any take is active.</CardDescription></CardHeader><CardContent><ol className="space-y-2">{run.takes.map((take: any) => <li key={take.take_id}><button type="button" aria-pressed={selectedTake?.take_id === take.take_id} onClick={() => openTake(take)} className={`flex w-full flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selectedTake?.take_id === take.take_id ? "border-primary bg-primary/5" : "hover:bg-muted/50"}`}><span className="min-w-0"><span className="block truncate text-sm font-medium">{take.shot_id} · take {take.attempt || 1}</span><span className="block text-xs text-muted-foreground">{take.take_id}{take.parent_take_id ? ` · after ${take.parent_take_id}` : " · no predecessor"}</span></span><Badge variant={take.status === "failed" ? "destructive" : take.status === "accepted" ? "default" : "secondary"}>{String(take.status).replaceAll("_", " ")}</Badge></button></li>)}</ol></CardContent></Card> : null}

    <div className="flex items-center justify-between border-t pt-4" aria-label="Production stage navigation"><Button variant="outline" onClick={() => void goToWorkspaceStage(({ assets: "story", voice: "assets", shots: "voice" } as Record<string, string>)[workspaceStage] || "story")} disabled={busy !== "" || workspaceStage === "story"}>Back</Button><span className="text-sm text-muted-foreground">{workspaceStage === "story" ? "Story & direction" : workspaceStage === "assets" ? "Assets & world" : workspaceStage === "voice" ? "Voices & audio" : "Shot composer"}</span><Button onClick={() => void goToWorkspaceStage(({ story: "assets", assets: "voice", voice: "shots" } as Record<string, string>)[workspaceStage] || "shots")} disabled={busy !== "" || workspaceStage === "shots" || (!run && workspaceStage === "story")}>{workspaceStage === "shots" ? "Final stage" : "Next stage"}</Button></div>
    {workspaceStage === "shots" && textStage === "shot_plans" && textRevision?.review_status === "accepted" && composerShotId && (selectedImageIds.length + selectedVideoIds.length + selectedAudioIds.length) > 0 ? <Card aria-label="Per-reference instructions"><CardHeader><CardTitle>Reference roles and order · {composerShotId}</CardTitle><CardDescription>Set each file’s job in this shot and reorder within its media type. H3 tags are reassigned from the final order; video excerpts retain their source timestamps.</CardDescription></CardHeader><CardContent className="space-y-5">
      {selectedImageIds.length ? <section className="space-y-2" aria-label="Image reference instructions"><h3 className="text-sm font-medium">Image references</h3>{selectedImageIds.map((assetId, index) => { const asset = assets.find((row) => row.asset_id === assetId); return <div key={assetId} className="grid gap-2 rounded-md border p-3 md:grid-cols-[1fr_auto]"><div className="space-y-2"><Label htmlFor={`image-intent-${assetId}`}>{`Picture ${index + 1} · ${asset?.filename || assetId}`}</Label><Textarea id={`image-intent-${assetId}`} value={intentFor(assetId, "Use as the selected visual reference.")} onChange={(event) => setIntentFor(assetId, event.target.value)} placeholder="e.g. canonical face and costume identity; ignore its background" className="min-h-16" /></div><div className="flex items-start gap-2"><Button type="button" variant="outline" aria-label={`Move Picture ${index + 1} up`} disabled={index === 0} onClick={() => moveReference(selectedImageIds, setSelectedImageIds, index, -1)}>↑</Button><Button type="button" variant="outline" aria-label={`Move Picture ${index + 1} down`} disabled={index === selectedImageIds.length - 1} onClick={() => moveReference(selectedImageIds, setSelectedImageIds, index, 1)}>↓</Button></div></div>; })}</section> : null}
      {selectedVideoIds.length ? <section className="space-y-2" aria-label="Video reference instructions"><h3 className="text-sm font-medium">Video references</h3>{selectedVideoIds.map((assetId, index) => { const asset = assets.find((row) => row.asset_id === assetId); const duration = Number(asset?.media?.duration_seconds || 15); const interval = videoIntervals[assetId] || { start_sec: 0, end_sec: Math.min(15, duration) }; return <div key={assetId} className="space-y-2 rounded-md border p-3"><div className="flex flex-wrap items-center justify-between gap-2"><Label htmlFor={`video-intent-${assetId}`}>{`Video ${index + 1} · ${asset?.filename || assetId}`}</Label><div className="flex gap-2"><Button type="button" variant="outline" aria-label={`Move Video ${index + 1} up`} disabled={index === 0} onClick={() => moveReference(selectedVideoIds, setSelectedVideoIds, index, -1)}>↑</Button><Button type="button" variant="outline" aria-label={`Move Video ${index + 1} down`} disabled={index === selectedVideoIds.length - 1} onClick={() => moveReference(selectedVideoIds, setSelectedVideoIds, index, 1)}>↓</Button></div></div><Textarea id={`video-intent-${assetId}`} value={intentFor(assetId, "Use for motion, camera movement, or continuity as specified by the Director.")} onChange={(event) => setIntentFor(assetId, event.target.value)} className="min-h-16" /><div className="grid max-w-md grid-cols-2 gap-2"><div className="space-y-1"><Label htmlFor={`video-start-${assetId}`}>Start seconds</Label><Input id={`video-start-${assetId}`} type="number" min={0} max={duration} step={0.1} value={interval.start_sec} onChange={(event) => setVideoIntervals((current) => ({ ...current, [assetId]: { ...interval, start_sec: Number(event.target.value) } }))} /></div><div className="space-y-1"><Label htmlFor={`video-end-${assetId}`}>End seconds</Label><Input id={`video-end-${assetId}`} type="number" min={0} max={duration} step={0.1} value={interval.end_sec} onChange={(event) => setVideoIntervals((current) => ({ ...current, [assetId]: { ...interval, end_sec: Number(event.target.value) } }))} /></div></div></div>; })}</section> : null}
      {selectedAudioIds.length ? <section className="space-y-2" aria-label="Audio reference instructions"><h3 className="text-sm font-medium">Standalone audio references</h3>{selectedAudioIds.map((assetId, index) => { const asset = assets.find((row) => row.asset_id === assetId); const tagIndex = (pairVideoAudio ? selectedVideoIds.length : 0) + index + 1; return <div key={assetId} className="grid gap-2 rounded-md border p-3 md:grid-cols-[1fr_auto]"><div className="space-y-2"><Label htmlFor={`audio-intent-${assetId}`}>{`Audio · ${asset?.filename || assetId}`}</Label><Textarea id={`audio-intent-${assetId}`} value={intentFor(assetId, "Use only for the selected voice or sound-reference purpose.")} onChange={(event) => setIntentFor(assetId, event.target.value)} className="min-h-16" /><div className="max-w-xs space-y-1"><Label htmlFor={`audio-speaker-${assetId}`}>{`Speaker ID for Audio ${tagIndex} (optional)`}</Label><Input id={`audio-speaker-${assetId}`} value={audioSpeakerIds[assetId] || ""} onChange={(event) => setAudioSpeakerIds((current) => ({ ...current, [assetId]: event.target.value }))} placeholder="S1" /></div></div><div className="flex items-start gap-2"><Button type="button" variant="outline" aria-label={`Move audio ${index + 1} up`} disabled={index === 0} onClick={() => moveReference(selectedAudioIds, setSelectedAudioIds, index, -1)}>↑</Button><Button type="button" variant="outline" aria-label={`Move audio ${index + 1} down`} disabled={index === selectedAudioIds.length - 1} onClick={() => moveReference(selectedAudioIds, setSelectedAudioIds, index, 1)}>↓</Button></div></div>; })}</section> : null}
      <p className="text-xs text-muted-foreground">Reference order updates the actual compiled tags. Paired video soundtracks still follow their corresponding video order and can be enabled or disabled above. Validation rejects out-of-range intervals and over-limit selections before any render.</p>
    </CardContent></Card> : null}
    {workspaceStage === "voice" && project && run ? <Card aria-label="Generated exact dialogue"><CardHeader><CardTitle>Generate bound two-character dialogue</CardTitle><CardDescription>Uses local VibeVoice with each character’s accepted run-bound voice excerpt. The supplied words stay in the transcript; audition pronunciation and speaker likeness. This audio remains separate from H3 native sound.</CardDescription></CardHeader><CardContent className="space-y-4">
      {boundDialogueVoices.length < 2 ? <p role="status" className="text-sm text-muted-foreground">Bind two active characters and create an accepted 2–15 second excerpt from each bound master first.</p> : <>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2"><Label htmlFor="dialogue-tts-speaker-one">Speaker 1</Label><select id="dialogue-tts-speaker-one" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={dialogueTtsSpeakerOne} onChange={(event) => setDialogueTtsSpeakerOne(event.target.value)}>{boundDialogueVoices.map((row) => <option key={row.character.character_id} value={row.character.character_id}>{row.character.display_name} · {row.binding.speaker_id} · {row.excerpt.filename}</option>)}</select><Textarea aria-label="Speaker 1 exact dialogue" value={dialogueTtsTextOne} onChange={(event) => setDialogueTtsTextOne(event.target.value)} maxLength={2000} placeholder="Exact words for Speaker 1" /></div>
          <div className="space-y-2"><Label htmlFor="dialogue-tts-speaker-two">Speaker 2</Label><select id="dialogue-tts-speaker-two" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={dialogueTtsSpeakerTwo} onChange={(event) => setDialogueTtsSpeakerTwo(event.target.value)}>{boundDialogueVoices.filter((row) => row.character.character_id !== dialogueTtsSpeakerOne).map((row) => <option key={row.character.character_id} value={row.character.character_id}>{row.character.display_name} · {row.binding.speaker_id} · {row.excerpt.filename}</option>)}</select><Textarea aria-label="Speaker 2 exact dialogue" value={dialogueTtsTextTwo} onChange={(event) => setDialogueTtsTextTwo(event.target.value)} maxLength={2000} placeholder="Exact words for Speaker 2" /></div>
        </div>
        <div className="max-w-xs space-y-2"><Label htmlFor="dialogue-tts-cue-seconds">Seconds reserved for each line</Label><Input id="dialogue-tts-cue-seconds" type="number" min="1" max="60" step="0.5" value={dialogueTtsCueSeconds} onChange={(event) => setDialogueTtsCueSeconds(Number(event.target.value))} /></div>
        <Button variant="outline" onClick={() => void queueProductionDialogue()} disabled={busy !== "" || !dialogueTtsTextOne.trim() || !dialogueTtsTextTwo.trim() || dialogueTtsTextOne.includes("\n") || dialogueTtsTextTwo.includes("\n") || dialogueTtsTextOne.length > 2000 || dialogueTtsTextTwo.length > 2000 || dialogueTtsCueSeconds < 1 || dialogueTtsCueSeconds > 60}>{busy === "dialogue-tts" ? "Queueing dialogue…" : "Generate dialogue audio"}</Button>
        {dialogueTtsJob ? <div role="status" aria-label="Generated dialogue status" className="space-y-2 text-sm"><p>Dialogue {dialogueTtsJob.job_id}: {String(dialogueTtsJob.status).replace(/_/g, " ")}{dialogueTtsJob.production_asset_id ? " · asset " + dialogueTtsJob.production_asset_id : ""}</p>{dialogueTtsJob.error ? <p className="text-destructive">{dialogueTtsJob.error}</p> : null}{dialogueTtsJob.production_asset_id ? <audio className="w-full" controls preload="metadata" src={"/api/projects/" + encodeURIComponent(project.id) + "/production/v2/assets/" + encodeURIComponent(dialogueTtsJob.production_asset_id) + "/content"} /> : null}</div> : null}
      </>}
    </CardContent></Card> : null}
    {busy ? <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Please wait…</div> : null}
    {runActive ? <p className="text-xs text-muted-foreground">This route deliberately does not alter legacy automation, image/video/audio jobs, or generated assets.</p> : null}
  </div></AppShell>;
}
