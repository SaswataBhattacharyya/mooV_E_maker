import { useEffect, useMemo, useState } from "react";
import { FileAudio, FolderUp, Loader2, Scissors, Trash2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CURRENT_PROJECT_KEY, addAudioLibraryAsset, createAudioUtilityJob, getAudioLibraryFileUrl,
  getAudioUtilityCapabilities, getAudioUtilityJob, listAudioLibraryAssets, listProjects,
  removeAudioLibraryAsset, type AudioLibraryAsset, type AudioUtilityCapabilities,
  type AudioUtilityJob, type ProjectState,
} from "@/lib/project-api";

const labels: Record<string, string> = {
  noise_cleanup: "Speech Noise Cleanup",
  extract_mp3: "Extract MP3 from video",
  demucs_stems: "Demucs stem separation",
};

export default function AudioUtilities() {
  const [projects, setProjects] = useState<ProjectState[]>([]);
  const [projectId, setProjectId] = useState(localStorage.getItem(CURRENT_PROJECT_KEY) || "");
  const [assets, setAssets] = useState<AudioLibraryAsset[]>([]);
  const [caps, setCaps] = useState<AudioUtilityCapabilities | null>(null);
  const [query, setQuery] = useState(""); const [files, setFiles] = useState<File[]>([]);
  const [operation, setOperation] = useState("extract_mp3"); const [collection, setCollection] = useState("audio-tools");
  const [quality, setQuality] = useState(2); const [stems, setStems] = useState(2); const [device, setDevice] = useState("cuda");
  const [denoiserModel, setDenoiserModel] = useState("master64"); const [dry, setDry] = useState(0);
  const [job, setJob] = useState<AudioUtilityJob | null>(null); const [running, setRunning] = useState(false);
  const refresh = () => listAudioLibraryAssets().then(setAssets);
  useEffect(() => { listProjects().then(setProjects); getAudioUtilityCapabilities().then(setCaps); refresh(); }, []);
  useEffect(() => { if (!job || !projectId || !["queued", "running"].includes(job.status)) return; const timer = window.setInterval(() => getAudioUtilityJob(projectId, job.job_id).then((next) => { setJob(next); if (!["queued", "running"].includes(next.status)) setRunning(false); }), 1500); return () => clearInterval(timer); }, [job, projectId]);
  const filtered = useMemo(() => assets.filter((a) => (a.filename + " " + a.tags.join(" ")).toLowerCase().includes(query.toLowerCase())), [assets, query]);
  const selectedCapability = caps?.operations.find((item) => item.id === operation);
  const importFiles = async (event: React.ChangeEvent<HTMLInputElement>) => { const selected = Array.from(event.target.files || []); for (const file of selected) await addAudioLibraryAsset(file, file.webkitRelativePath || file.name); await refresh(); toast.success(`Imported ${selected.length} audio file(s)`); };
  const run = async () => {
    if (!projectId || !files.length) return toast.error("Select a project and input files");
    if (selectedCapability?.status !== "available") return toast.error(selectedCapability?.reason || "This runtime is not available");
    setRunning(true);
    try { setJob(await createAudioUtilityJob(projectId, operation, { output_collection: collection, model: denoiserModel, dry, stems, device, quality }, files)); }
    catch (error) { setRunning(false); toast.error(error instanceof Error ? error.message : "Could not start utility job"); }
  };
  return <AppShell><div className="space-y-6">
    <div><Badge variant="outline">Deterministic audio tools</Badge><h2 className="mt-3 text-3xl font-semibold">Audio Utilities</h2><p className="text-muted-foreground">Curated audio, speech cleanup, video audio extraction, and Demucs stem separation.</p></div>
    <Card className="rounded-3xl"><CardHeader><CardTitle>Project</CardTitle></CardHeader><CardContent><select className="h-10 w-full rounded-md border border-input bg-background px-3" value={projectId} onChange={(e) => { setProjectId(e.target.value); localStorage.setItem(CURRENT_PROJECT_KEY, e.target.value); }}><option value="">Select project</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}</select></CardContent></Card>
    <Card className="rounded-3xl"><CardHeader><CardTitle className="flex items-center gap-2"><FileAudio className="h-5 w-5" />Curated audio</CardTitle><CardDescription>Story Builder-managed reusable source audio. Duplicate content is detected by hash.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="grid gap-3 md:grid-cols-2"><label className="flex cursor-pointer items-center justify-center rounded-xl border border-dashed p-5"><FolderUp className="mr-2 h-4 w-4" />Import audio files<Input className="hidden" type="file" accept="audio/*" multiple onChange={importFiles} /></label><Input placeholder="Search filenames or tags" value={query} onChange={(e) => setQuery(e.target.value)} /></div><div className="max-h-96 space-y-3 overflow-y-auto pr-2">{filtered.map((asset) => <div key={asset.asset_id} className="grid items-center gap-3 rounded-xl border p-3 md:grid-cols-[1fr_2fr_auto]"><div className="min-w-0"><p className="truncate font-medium" title={asset.filename}>{asset.filename}</p><p className="text-xs text-muted-foreground">{asset.duration || 0}s · {Math.round(asset.size / 1024)} KB</p></div><audio className="w-full" controls src={getAudioLibraryFileUrl(asset.asset_id)} /><Button aria-label={`Remove ${asset.filename}`} size="icon" variant="ghost" onClick={async () => { await removeAudioLibraryAsset(asset.asset_id); await refresh(); }}><Trash2 className="h-4 w-4" /></Button></div>)}</div></CardContent></Card>
    <Card className="rounded-3xl border-primary/40"><CardHeader><CardTitle className="flex items-center gap-2"><Wand2 className="h-5 w-5" />Batch processing</CardTitle><CardDescription>Choose individual inputs or a folder. Originals remain unchanged.</CardDescription></CardHeader><CardContent className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3"><div><Label>Tool</Label><select className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3" value={operation} onChange={(e) => { setOperation(e.target.value); setFiles([]); }}><option value="noise_cleanup">Speech Noise Cleanup</option><option value="extract_mp3">Extract MP3 from video</option><option value="demucs_stems">Demucs stem separation</option></select></div><div><Label>Output collection</Label><Input className="mt-2" value={collection} onChange={(e) => setCollection(e.target.value)} /></div><div><Label>Runtime</Label><div className="mt-2 flex h-10 items-center gap-2 rounded-md border px-3"><Badge variant={selectedCapability?.status === "available" ? "default" : "secondary"}>{selectedCapability?.status || "checking"}</Badge><span className="truncate text-xs text-muted-foreground">{selectedCapability?.runtime}</span></div></div></div>
      {selectedCapability?.reason ? <p className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-sm">{selectedCapability.reason}</p> : null}
      {operation === "extract_mp3" ? <div className="max-w-xs"><Label>MP3 quality (0 best, 9 smallest)</Label><Input className="mt-2" type="number" min={0} max={9} value={quality} onChange={(e) => setQuality(Number(e.target.value))} /></div> : null}
      {operation === "noise_cleanup" ? <div className="grid gap-4 md:grid-cols-2"><div><Label>Denoiser model</Label><select className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3" value={denoiserModel} onChange={(e) => setDenoiserModel(e.target.value)}><option value="master64">Master64</option><option value="dns64">DNS64</option></select></div><div><Label>Dry mix (0 enhanced, 1 original)</Label><Input className="mt-2" type="number" min={0} max={1} step={0.05} value={dry} onChange={(e) => setDry(Number(e.target.value))} /></div></div> : null}
      {operation === "demucs_stems" ? <div className="grid gap-4 md:grid-cols-2"><div><Label>Output stems</Label><select className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3" value={stems} onChange={(e) => setStems(Number(e.target.value))}><option value={2}>2 — vocals / accompaniment</option><option value={4}>4 — vocals / drums / bass / other</option><option value={6}>6 — plus guitar / piano</option></select></div><div><Label>Device</Label><select className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3" value={device} onChange={(e) => setDevice(e.target.value)}><option value="cuda">CUDA</option><option value="cpu">CPU</option></select></div></div> : null}
      <div className="grid gap-3 md:grid-cols-2"><label className="block rounded-xl border border-dashed p-4 text-center text-sm"><FolderUp className="mr-2 inline h-4 w-4" />Choose files<Input className="hidden" type="file" multiple accept={operation === "extract_mp3" ? "video/*" : "audio/*"} onChange={(e) => setFiles(Array.from(e.target.files || []))} /></label><label className="block rounded-xl border border-dashed p-4 text-center text-sm"><FolderUp className="mr-2 inline h-4 w-4" />Choose folder<Input className="hidden" type="file" multiple {...({ webkitdirectory: "" } as React.InputHTMLAttributes<HTMLInputElement>)} onChange={(e) => setFiles(Array.from(e.target.files || []))} /></label></div>
      <p className="text-sm text-muted-foreground">{files.length ? `${files.length} input(s) selected` : "No inputs selected"}</p>
      <div className="flex items-center gap-3"><Button disabled={running || !files.length || selectedCapability?.status !== "available"} onClick={run}>{running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Scissors className="mr-2 h-4 w-4" />}Run {labels[operation]}</Button>{job ? <Badge variant={job.status === "failed" ? "destructive" : "secondary"}>{job.status} {job.progress || 0}%</Badge> : null}</div>
      {job?.error ? <p className="text-sm text-destructive">{job.error}</p> : null}{job?.outputs?.length ? <div className="rounded-xl border p-3"><p className="font-medium">Outputs</p>{job.outputs.map((output) => <p className="mt-1 truncate text-sm text-muted-foreground" key={output.relative_path}>{output.filename}</p>)}</div> : null}
    </CardContent></Card>
  </div></AppShell>;
}
