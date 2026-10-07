import { useCallback, useEffect, useMemo, useState, type DragEvent, type ClipboardEvent } from "react";
import { ArrowRight, Film, ImagePlus, Loader2, Mic2, Plus, RefreshCw, Send, Trash2, Upload, WandSparkles, X } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import {
  createManualDirectorJob, deleteManualDirectorJob, getManualDirectorJob, getManualDirectorOutputUrl,
  getVideoAssetUrl, getVideoRepertoireAudioAssetUrl, listManualDirectorAssets, listManualDirectorJobs,
  listManualDirectorWorkflows, listVideoAssets, listVideoRepertoireAudioAssets, queueManualDirectorReferences,
  uploadManualDirectorAsset, type ManualDirectorAsset, type ManualDirectorJob,
  type ManualDirectorReference, type ManualDirectorSlot, type ManualDirectorWorkflow, type VideoAsset,
  type VideoRepertoireAudioAsset,
} from "@/lib/project-api";

const QUEUED_REFS_KEY = "story_builder.manual_director.selection";
const activeStatuses = new Set(["queued", "running"]);
const allSlots: Array<{ slot: ManualDirectorSlot; label: string; media: string; hint: string }> = [
  { slot: "reference_images", label: "Reference images", media: "image", hint: "Minimax H3 references · up to 3" },
  { slot: "first_frame", label: "First frame", media: "image", hint: "WAN first/last-frame workflow" },
  { slot: "last_frame", label: "Last frame", media: "image", hint: "WAN first/last-frame workflow" },
  { slot: "audio", label: "Audio reference", media: "audio", hint: "Reserved until an installed workflow accepts audio input" },
  { slot: "video", label: "Video reference", media: "video", hint: "Reserved until an installed workflow accepts video input" },
];

function loadQueuedRefs(): ManualDirectorReference[] {
  try { const value = JSON.parse(localStorage.getItem(QUEUED_REFS_KEY) || "[]"); return Array.isArray(value) ? value : []; }
  catch { return []; }
}

function referenceKey(reference: ManualDirectorReference) {
  return [reference.slot, reference.asset_id, reference.relative_path || "", reference.start_time_sec ?? "", reference.end_time_sec ?? ""].join("|");
}

export default function ManualDirector() {
  const [workflows, setWorkflows] = useState<ManualDirectorWorkflow[]>([]);
  const [workflowId, setWorkflowId] = useState("minimax_text");
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [parameters, setParameters] = useState<Record<string, number>>({});
  const [references, setReferences] = useState<ManualDirectorReference[]>(loadQueuedRefs);
  const [uploads, setUploads] = useState<ManualDirectorAsset[]>([]);
  const [jobs, setJobs] = useState<ManualDirectorJob[]>([]);
  const [videos, setVideos] = useState<VideoAsset[]>([]);
  const [audioAssets, setAudioAssets] = useState<VideoRepertoireAudioAsset[]>([]);
  const [busy, setBusy] = useState(false);
  const [activeDropSlot, setActiveDropSlot] = useState<ManualDirectorSlot>("reference_images");
  const [draggingSlot, setDraggingSlot] = useState<ManualDirectorSlot | null>(null);

  const refresh = useCallback(async () => {
    const [workflowRows, uploadRows, jobRows, videoRows, audioRows] = await Promise.all([
      listManualDirectorWorkflows(), listManualDirectorAssets(), listManualDirectorJobs(),
      listVideoAssets(), listVideoRepertoireAudioAssets("all"),
    ]);
    setWorkflows(workflowRows); setUploads(uploadRows); setJobs(jobRows); setVideos(videoRows); setAudioAssets(audioRows);
  }, []);
  useEffect(() => { refresh().catch((error) => toast.error(error instanceof Error ? error.message : "Could not load Manual Director")); }, [refresh]);
  useEffect(() => { localStorage.setItem(QUEUED_REFS_KEY, JSON.stringify(references)); }, [references]);

  const workflow = workflows.find((item) => item.workflow_id === workflowId);
  const allowedSlots = new Set(workflow?.accepted_slots || []);
  const incompatibleReferences = references.filter((row) => !allowedSlots.has(row.slot));
  const parametersReady = useMemo(() => Object.fromEntries((workflow?.parameters || []).map((item) => [item.key, item.default])), [workflow?.workflow_id]);
  useEffect(() => { setParameters(parametersReady); }, [parametersReady]);
  const referenceCounts = references.reduce<Record<string, number>>((counts, item) => { counts[item.slot] = (counts[item.slot] || 0) + 1; return counts; }, {});
  const missingRequired = (workflow?.required_slots || []).filter((slot) => !referenceCounts[slot]);
  const canRun = Boolean(workflow?.available && prompt.trim() && !busy && incompatibleReferences.length === 0 && missingRequired.length === 0);

  const addReferences = (items: ManualDirectorReference[]) => {
    setReferences((current) => {
      const map = new Map(current.map((item) => [referenceKey(item), item]));
      for (const item of items) map.set(referenceKey(item), item);
      return [...map.values()];
    });
  };
  const removeReference = (reference: ManualDirectorReference) => setReferences((current) => current.filter((item) => referenceKey(item) !== referenceKey(reference)));
  const upload = async (slot: ManualDirectorSlot, file: File) => {
    setActiveDropSlot(slot); setBusy(true);
    try {
      const asset = await uploadManualDirectorAsset(file, slot);
      setUploads((current) => current.some((item) => item.asset_id === asset.asset_id) ? current : [asset, ...current]);
      addReferences([{ slot, asset_id: asset.asset_id, filename: asset.filename, relative_path: asset.relative_path, media_type: asset.media_type }]);
      toast.success(`${file.name} added to the shared video repertoire.`);
    } catch (error) { toast.error(error instanceof Error ? error.message : "Upload failed"); }
    finally { setBusy(false); }
  };
  const onDrop = (slot: ManualDirectorSlot, event: DragEvent<HTMLDivElement>) => {
    event.preventDefault(); setDraggingSlot(null);
    const json = event.dataTransfer.getData("application/x-story-builder-media");
    if (json) {
      try {
        const item = JSON.parse(json) as ManualDirectorReference;
        const requiredType = slot === "audio" ? "audio" : slot === "video" ? "video" : "image";
        if (item.media_type && item.media_type !== requiredType) {
          toast.error(`${item.filename || "This asset"} is ${item.media_type}, but ${slot.replaceAll("_", " ")} accepts ${requiredType} media.`);
          return;
        }
        addReferences([{ ...item, slot }]);
      } catch { toast.error("That repository item could not be read."); }
      return;
    }
    const file = event.dataTransfer.files?.[0];
    if (file) void upload(slot, file);
  };
  const onPaste = (event: ClipboardEvent<HTMLDivElement>) => {
    const file = Array.from(event.clipboardData.items).find((item) => item.kind === "file")?.getAsFile();
    if (!file) return;
    event.preventDefault(); void upload(activeDropSlot, file);
  };
  const addLibraryVideo = (asset: VideoAsset) => {
    if (asset.size > 500 * 1024 * 1024) { toast.error(`${asset.filename} exceeds the 500 MB video-reference limit.`); return; }
    addReferences([{ slot: "video", asset_id: asset.asset_id, filename: asset.filename, media_type: "video" }]);
  };
  const addLibraryAudio = (asset: VideoRepertoireAudioAsset) => {
    if (asset.available === false) { toast.error("This derived audio file was deleted; only its event metadata remains."); return; }
    if (Number(asset.size || 0) > 200 * 1024 * 1024) { toast.error(`${asset.filename} exceeds the 200 MB audio-reference limit.`); return; }
    addReferences([{ slot: "audio", asset_id: asset.asset_id,
    filename: asset.filename, relative_path: asset.relative_path, media_type: "audio", start_time_sec: asset.start_time_sec, end_time_sec: asset.end_time_sec }]);
  };

  const run = async () => {
    if (!workflow) return;
    setBusy(true);
    try {
      const job = await createManualDirectorJob({ workflow_id: workflowId, prompt, negative_prompt: negativePrompt,
        parameters, references });
      setJobs((current) => [job, ...current.filter((item) => item.run_id !== job.run_id)]);
      toast.success("Manual generation queued.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Could not start generation"); }
    finally { setBusy(false); }
  };
  const deleteJob = async (job: ManualDirectorJob) => {
    if (activeStatuses.has(job.status)) return;
    if (!window.confirm(`Delete ${job.run_id} and its manual input/output records? Shared source assets will remain.`)) return;
    try { await deleteManualDirectorJob(job.run_id); setJobs((current) => current.filter((item) => item.run_id !== job.run_id)); toast.success("Manual run and its outputs deleted."); }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not delete run"); }
  };

  useEffect(() => {
    if (!jobs.some((job) => activeStatuses.has(job.status))) return;
    const timer = window.setInterval(() => {
      void Promise.all(jobs.filter((job) => activeStatuses.has(job.status)).map((job) => getManualDirectorJob(job.run_id)
        .then((updated) => setJobs((current) => current.map((item) => item.run_id === updated.run_id ? updated : item)))
        .catch(() => undefined)));
    }, 1800);
    return () => window.clearInterval(timer);
  }, [jobs]);

  return <AppShell><div className="space-y-6" onPaste={onPaste}>
    <header className="flex flex-wrap items-start justify-between gap-4"><div><Badge variant="outline">Video &amp; Audio Production</Badge><h2 className="mt-3 text-3xl font-semibold">Manual Director</h2><p className="mt-2 max-w-3xl text-sm text-muted-foreground">Compose selected repository references and a director prompt into an available ComfyUI video workflow. Inputs and generated outputs are kept in the shared Video Repertoire.</p></div><Button variant="outline" onClick={() => refresh()}><RefreshCw className="mr-2 h-4 w-4"/>Refresh</Button></header>
    {references.length > 0 && <Card className="border-primary/30"><CardContent className="flex flex-wrap items-center justify-between gap-3 py-4"><p className="text-sm"><strong>{references.length}</strong> staged reference{references.length === 1 ? "" : "s"} · duplicates from repeated handoff are collapsed</p><Button variant="outline" onClick={() => setReferences([])}><X className="mr-2 h-4 w-4"/>Clear references</Button></CardContent></Card>}
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,.8fr)]">
      <div className="space-y-5">
        <Card><CardHeader><CardTitle>Direction</CardTitle><CardDescription>Describe the shot, movement, tone, pacing, and audio intent. The selected workflow determines the actual supported controls.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="space-y-2"><Label htmlFor="manual-prompt">Prompt</Label><Textarea id="manual-prompt" data-testid="manual-prompt" className="min-h-40" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="A close, handheld tracking shot follows the exhausted courier through rain…"/></div><div className="space-y-2"><Label htmlFor="manual-negative">Negative prompt (optional)</Label><Textarea id="manual-negative" className="min-h-20" value={negativePrompt} onChange={(event) => setNegativePrompt(event.target.value)} placeholder="Artifacts or content to avoid"/></div></CardContent></Card>
        <Card><CardHeader><CardTitle>Workflow and settings</CardTitle><CardDescription>Only locally installed, mapped API workflows appear as runnable. Duration and quality controls reflect the workflow graph.</CardDescription></CardHeader><CardContent className="space-y-4"><select aria-label="Manual generation workflow" data-testid="manual-workflow" className="h-11 w-full rounded-md border border-input bg-background px-3" value={workflowId} onChange={(event) => setWorkflowId(event.target.value)}>{workflows.map((item) => <option key={item.workflow_id} value={item.workflow_id} disabled={!item.available}>{item.label}{item.available ? "" : " · unavailable"}</option>)}</select>{workflow && <><p className="text-sm text-muted-foreground">{workflow.description}</p><div className="flex flex-wrap gap-2"><Badge variant="outline">{workflow.file}</Badge><Badge variant={workflow.available ? "default" : "destructive"}>{workflow.available ? "Mapped" : "Missing"}</Badge><Badge variant="secondary">{workflow.fps} fps</Badge></div><div className="grid gap-3 sm:grid-cols-2">{workflow.parameters.map((field) => <div key={field.key} className="space-y-2"><Label htmlFor={`param-${field.key}`}>{field.label}</Label><Input id={`param-${field.key}`} aria-label={field.label} type="number" min={field.min} max={field.max} step={field.step} value={parameters[field.key] ?? field.default} onChange={(event) => setParameters((current) => ({ ...current, [field.key]: Number(event.target.value) }))}/>{field.description && <p className="text-xs text-muted-foreground">{field.description}</p>}</div>)}</div></>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Reference slots</CardTitle><CardDescription>Drop a repository item or local file, paste an image/audio/video file where browser clipboard access permits, or choose from your computer. Unsupported references stay visible and block submission until removed or a compatible workflow is selected.</CardDescription></CardHeader><CardContent className="grid gap-3 md:grid-cols-2">{allSlots.map((item) => {
          const rows = references.filter((row) => row.slot === item.slot);
          const supported = allowedSlots.has(item.slot);
          return <div key={item.slot} onDragOver={(event) => { event.preventDefault(); setDraggingSlot(item.slot); setActiveDropSlot(item.slot); }} onDragLeave={() => setDraggingSlot(null)} onDrop={(event) => onDrop(item.slot, event)} className={`min-h-36 rounded-xl border border-dashed p-4 transition-colors ${draggingSlot === item.slot ? "border-primary bg-primary/10" : ""}`}>
            <div className="flex items-start justify-between gap-2"><div><p className="font-medium">{item.label}</p><p className="mt-1 text-xs text-muted-foreground">{item.hint}</p></div><Badge variant={supported ? "default" : "outline"}>{supported ? "Accepted" : "Not accepted by workflow"}</Badge></div>
            <div className="mt-3 space-y-2">{rows.map((row) => <div key={referenceKey(row)} draggable onDragStart={(event) => event.dataTransfer.setData("application/x-story-builder-media", JSON.stringify(row))} className="flex items-center justify-between gap-2 rounded-md bg-muted/50 px-2 py-2 text-xs"><span className="min-w-0 truncate">{row.filename || row.asset_id}{row.start_time_sec != null ? ` · ${Number(row.start_time_sec).toFixed(1)}s` : ""}</span><Button size="icon" variant="ghost" aria-label={`Remove ${row.filename || row.asset_id}`} onClick={() => removeReference(row)}><X className="h-3.5 w-3.5"/></Button></div>)}
              <div className="flex flex-wrap items-center gap-2"><label className="inline-flex cursor-pointer items-center rounded-md border px-2.5 py-1.5 text-xs hover:bg-muted"><Upload className="mr-1.5 h-3.5 w-3.5"/>Choose file<input aria-label={`Choose ${item.label}`} className="sr-only" type="file" accept={item.media === "image" ? "image/png,image/jpeg,image/webp" : item.media === "audio" ? "audio/*" : "video/*"} disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(item.slot, file); event.currentTarget.value = ""; }}/></label><span className="text-[11px] text-muted-foreground">or drop/paste here</span></div>
            </div>
          </div>;
        })}</CardContent></Card>
        {incompatibleReferences.length > 0 && <div role="alert" className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm"><p className="font-medium">Some staged references are incompatible with this workflow.</p><p className="mt-1 text-muted-foreground">This installed workflow cannot consume the selected audio/video references. Remove them or choose a compatible installed workflow. Nothing will be silently omitted.</p></div>}
        {missingRequired.length > 0 && <div role="alert" className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm">Required before running: {missingRequired.map((item) => item.replaceAll("_", " ")).join(", ")}.</div>}
        <Button size="lg" data-testid="manual-run" disabled={!canRun} onClick={run}><WandSparkles className="mr-2 h-4 w-4"/>{busy ? <><Loader2 className="mr-2 h-4 w-4 animate-spin"/>Working…</> : "Run generation"}</Button>
      </div>
      <aside className="space-y-5">
        <Card><CardHeader><CardTitle>Repository handoff</CardTitle><CardDescription>Drag a repository item onto its reference slot, or add it here. Items are referenced by asset ID/path, not copied into the manual project.</CardDescription></CardHeader><CardContent className="space-y-4"><div><Label className="mb-2 flex items-center gap-2"><Film className="h-4 w-4"/>Video sources</Label><div className="max-h-48 space-y-2 overflow-auto">{videos.map((asset) => <RepositoryRow key={asset.asset_id} label={asset.title || asset.filename} detail={`${(asset.size / 1048576).toFixed(1)} MB · ${asset.media.duration ? `${asset.media.duration.toFixed(1)} sec` : "duration unknown"}`} reference={{ slot: "video", asset_id: asset.asset_id, filename: asset.filename, media_type: "video" }} onAdd={() => addLibraryVideo(asset)}/>)}</div></div><div><Label className="mb-2 flex items-center gap-2"><Mic2 className="h-4 w-4"/>Saved audio</Label><div className="max-h-56 space-y-2 overflow-auto">{audioAssets.filter((asset) => asset.available !== false).map((asset) => <RepositoryRow key={`${asset.category}-${asset.asset_id}`} label={asset.label || asset.filename} detail={`${asset.category}${asset.start_time_sec != null ? ` · ${Number(asset.start_time_sec).toFixed(1)}s` : ""}`} reference={{ slot: "audio", asset_id: asset.asset_id, filename: asset.filename, relative_path: asset.relative_path, media_type: "audio", start_time_sec: asset.start_time_sec, end_time_sec: asset.end_time_sec }} onAdd={() => addLibraryAudio(asset)}/>)}</div></div><div><Label className="mb-2 flex items-center gap-2"><ImagePlus className="h-4 w-4"/>Manual uploads already in repertoire</Label><div className="max-h-40 space-y-2 overflow-auto">{uploads.map((asset) => <RepositoryRow key={asset.asset_id} label={asset.filename} detail={`${asset.media_type} · ${(asset.size / 1048576).toFixed(1)} MB`} reference={{ slot: asset.media_type === "image" ? "reference_images" : asset.media_type, asset_id: asset.asset_id, filename: asset.filename, relative_path: asset.relative_path, media_type: asset.media_type } as ManualDirectorReference} onAdd={() => addReferences([{ slot: asset.media_type === "image" ? "reference_images" : asset.media_type, asset_id: asset.asset_id, filename: asset.filename, relative_path: asset.relative_path, media_type: asset.media_type } as ManualDirectorReference])}/>)}</div></div></CardContent></Card>
        <Card><CardHeader><CardTitle>Generation runs</CardTitle><CardDescription>Input JSON: `video_repertoire/manual/inputs/`. Outputs: `video_repertoire/manual/outputs/`.</CardDescription></CardHeader><CardContent className="space-y-3">{jobs.length === 0 && <p className="text-sm text-muted-foreground">No manual generations yet.</p>}{jobs.map((job) => <div key={job.run_id} className="space-y-3 rounded-xl border p-3" data-testid="manual-job"><div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="truncate text-sm font-medium">{job.run_id}</p><p className="mt-1 text-xs text-muted-foreground">{job.status} · {job.stage}</p></div><Button aria-label={`Delete ${job.run_id}`} size="icon" variant="ghost" disabled={activeStatuses.has(job.status)} onClick={() => void deleteJob(job)}><Trash2 className="h-4 w-4"/></Button></div>{activeStatuses.has(job.status) && <><Progress value={job.progress}/><p className="text-xs text-muted-foreground">{job.message}</p></>}{job.error && <p role="alert" className="text-xs text-destructive">{job.error}</p>}{job.outputs.map((output) => <div key={output.relative_path} className="space-y-2">{output.kind === "video" ? <video controls preload="metadata" className="w-full rounded-lg bg-black" src={getManualDirectorOutputUrl(job.run_id, output.filename)}/> : output.kind === "audio" ? <audio controls className="w-full" src={getManualDirectorOutputUrl(job.run_id, output.filename)}/> : <img alt={output.filename} className="max-h-56 rounded-lg" src={getManualDirectorOutputUrl(job.run_id, output.filename)}/>}<a className="text-xs text-primary underline" href={getManualDirectorOutputUrl(job.run_id, output.filename)} download>{output.filename}</a></div>)}</div>)}</CardContent></Card>
        <p className="text-xs text-muted-foreground">To select analyzed scenes, cut clips, frames, voices, music, or SFX, use the Video Summariser’s “Send to Manual Director” action. <Link className="text-primary underline" to="/video-summariser">Open Video Summariser</Link>.</p>
      </aside>
    </div>
  </div></AppShell>;
}

function RepositoryRow({ label, detail, reference, onAdd }: { label: string; detail: string; reference: ManualDirectorReference; onAdd: () => void }) {
  return <div draggable onDragStart={(event) => event.dataTransfer.setData("application/x-story-builder-media", JSON.stringify(reference))} className="flex items-center justify-between gap-2 rounded-lg border p-2 text-xs"><div className="min-w-0"><p className="truncate font-medium">{label}</p><p className="truncate text-muted-foreground">{detail}</p></div><Button size="icon" variant="outline" aria-label={`Add ${label}`} onClick={onAdd}><Plus className="h-3.5 w-3.5"/></Button></div>;
}
