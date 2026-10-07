import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Download, Film, FolderInput, Loader2, Play, RefreshCw, Search, Send, Trash2, Upload, X } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  cancelVideoJob, createVideoAnalysisJob, createVideoDownloadJob, deleteVideoAnalysisJob, deleteVideoAssets, fetchVideoRepertoireCapabilities,
  discardVideoAudioSamPreview, getVideoAudioSamPreviewUrl,
  getVideoArtifactUrl, getVideoAssetUrl, importLegacyVideoAssets, listVideoAnalysisJobs, listVideoAssets,
  isolateVideoAudioEvent, listVideoDownloadJobs, listProjects, nextVideoReferencePage, resolveVideoSources, retryVideoJob, reviewVideoAudioSamPreview, searchVideoRepertoire, searchVideoReferences, selectVideoReferences, uploadVideoAsset,
  getVideoAudioAnalyzerArtifactUrl,
  getVideoRepertoireAudioAssetUrl, listVideoRepertoireAudioAssets, deleteVideoRepertoireAudioAssets,
  queueManualDirectorReferences,
  searchVideoAudioCorpus, stopVideoAnalysisJob,
  type ManualDirectorReference, type ResolvedVideoSource, type VideoAsset, type VideoAudioCorpusResult, type VideoJob, type VideoRepertoireAudioAsset, type VideoRepertoireCapabilities, type VideoSearchResult,
} from "@/lib/project-api";

const terminal = new Set(["completed", "failed", "cancelled", "interrupted"]);
const formatBytes = (value: number) => value > 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(1)} GB` : `${(value / 1024 ** 2).toFixed(1)} MB`;
const formatDuration = (value?: number | null) => value == null ? "Unknown duration" : `${Math.floor(value / 60)}:${String(Math.round(value % 60)).padStart(2, "0")}`;

export default function VideoRepertoire() {
  const navigate = useNavigate();
  const [capabilities, setCapabilities] = useState<VideoRepertoireCapabilities | null>(null);
  const [assets, setAssets] = useState<VideoAsset[]>([]);
  const [downloads, setDownloads] = useState<VideoJob[]>([]);
  const [analyses, setAnalyses] = useState<VideoJob[]>([]);
  const [selectedAssets, setSelectedAssets] = useState<string[]>([]);
  const [sourceMode, setSourceMode] = useState("search");
  const [query, setQuery] = useState("");
  const [count, setCount] = useState("5");
  const [urlsText, setUrlsText] = useState("");
  const [resolved, setResolved] = useState<ResolvedVideoSource | null>(null);
  const [chosenUrls, setChosenUrls] = useState<string[]>([]);
  const [upload, setUpload] = useState<File | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [resultJobId, setResultJobId] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [topHits, setTopHits] = useState("5");
  const [searchResults, setSearchResults] = useState<VideoSearchResult[]>([]);
  const [analyzerSearchResults, setAnalyzerSearchResults] = useState<VideoAudioCorpusResult[]>([]);
  const [searchBackend, setSearchBackend] = useState<"analyzer" | "curated">("analyzer");
  const [settings, setSettings] = useState({ extract_fps: 4, extract_cut_clips: true, cut_boundary_threshold: 0.18, min_cut_seconds: 0.5 });
  const [audioAnalyzerEnabled, setAudioAnalyzerEnabled] = useState(true);
  const [audioSettings, setAudioSettings] = useState({ extract_source_audio: true, extract_preview_mp3: true,
    detect_speech: true, detect_music: true, detect_sfx: true,
    create_audio_embeddings: true, create_av_embeddings: true, diarize_speakers: true, run_demucs: "AUTO",
    adaptive_sampling: true, frame_change_threshold: 0.08, preserve_scene_anchors: true, keep_intermediate_samples: false,
    collect_voice_examples: false, collect_music_clips: false, collect_sfx_clips: false });
  const [activeTab, setActiveTab] = useState("library");
  const [searchMode, setSearchMode] = useState({ semantic: true, keyword: true });
  const [searchSession, setSearchSession] = useState<{ id: string; hasMore: boolean; backend: "analyzer" | "curated"; offset?: number } | null>(null);
  const [selectedReferences, setSelectedReferences] = useState<string[]>([]);
  const [sortLevel, setSortLevel] = useState<"scene" | "subscene" | "clip">("subscene");
  const [referenceProject, setReferenceProject] = useState(localStorage.getItem("story_builder.current_project") || "");
  const [projects, setProjects] = useState<Array<{ id: string; title: string }>>([]);
  const [audioLibraryAssets, setAudioLibraryAssets] = useState<VideoRepertoireAudioAsset[]>([]);
  const [audioLibraryCategory, setAudioLibraryCategory] = useState("all");
  const [audioLibraryQuery, setAudioLibraryQuery] = useState("");
  const [audioLibraryBusy, setAudioLibraryBusy] = useState(false);
  const [selectedAudioPaths, setSelectedAudioPaths] = useState<string[]>([]);
  const [selectedDirectorReferences, setSelectedDirectorReferences] = useState<ManualDirectorReference[]>([]);
  const [duplicateCandidatesOnly, setDuplicateCandidatesOnly] = useState(false);

  const refresh = useCallback(async () => {
    const [caps, nextAssets, nextDownloads, nextAnalyses] = await Promise.all([
      fetchVideoRepertoireCapabilities(), listVideoAssets(), listVideoDownloadJobs(), listVideoAnalysisJobs(),
    ]);
    setCapabilities(caps); setAssets(nextAssets); setDownloads(nextDownloads); setAnalyses(nextAnalyses);
    if (!resultJobId && nextAnalyses.length) setResultJobId(nextAnalyses[0].job_id);
  }, [resultJobId]);

  useEffect(() => { refresh().catch((error) => toast.error(error.message)); }, [refresh]);
  useEffect(() => { listProjects().then((items) => setProjects(items.map((item) => ({ id: item.id, title: item.title })))).catch(() => undefined); }, []);
  useEffect(() => {
    if (activeTab !== "audio-assets") return;
    setAudioLibraryBusy(true);
    listVideoRepertoireAudioAssets(audioLibraryCategory)
      .then(setAudioLibraryAssets)
      .catch((error) => toast.error(error instanceof Error ? error.message : "Could not load audio assets"))
      .finally(() => setAudioLibraryBusy(false));
  }, [activeTab, audioLibraryCategory]);
  useEffect(() => {
    const active = [...downloads, ...analyses].some((job) => !terminal.has(job.status));
    if (!active) return;
    const timer = window.setInterval(() => refresh().catch(() => undefined), 2500);
    return () => window.clearInterval(timer);
  }, [downloads, analyses, refresh]);

  const selectedResult = analyses.find((job) => job.job_id === resultJobId) || analyses[0] || null;
  const readiness = capabilities && capabilities.ffmpeg && capabilities.ffprobe && capabilities.video_audio_analyzer_ready;
  const selectedAssetRecords = useMemo(() => assets.filter((asset) => selectedAssets.includes(asset.asset_id)), [assets, selectedAssets]);

  const sendToManualDirector = (references: ManualDirectorReference[]) => {
    if (!references.length) return;
    const total = queueManualDirectorReferences(references);
    toast.success(`${references.length} reference(s) staged · ${total} unique reference(s) in the tray.`);
    navigate("/manual-director");
  };
  const analyzerReference = (item: VideoAudioCorpusResult): ManualDirectorReference | null => {
    const start = item.start_time_sec ?? null;
    const end = item.end_time_sec ?? null;
    if (item.artifact_path) {
      const relative = `analyses/video_audio_analyzer/${item.run_id}/${item.artifact_path}`;
      const isAudio = item.kind === "audio_event" || /\.(wav|mp3|m4a|ogg|flac|aac)$/i.test(item.artifact_path);
      const isImage = /\.(png|jpe?g|webp)$/i.test(item.artifact_path);
      if (isAudio) return { slot: "audio", asset_id: item.result_id, filename: item.text.slice(0, 72) || "audio reference", relative_path: relative, media_type: "audio", start_time_sec: start, end_time_sec: end };
      if (isImage) return { slot: "reference_images", asset_id: item.result_id, filename: item.text.slice(0, 72) || "image reference", relative_path: relative, media_type: "image", start_time_sec: start, end_time_sec: end };
    }
    if (item.clip_artifact_path) return { slot: "video", asset_id: item.result_id, filename: item.text.slice(0, 72) || "video clip", relative_path: `analyses/video_audio_analyzer/${item.run_id}/${item.clip_artifact_path}`, media_type: "video", start_time_sec: start, end_time_sec: end };
    if (item.asset_id?.startsWith("video-")) return { slot: "video", asset_id: item.asset_id, filename: item.source_file || item.video_id, media_type: "video", start_time_sec: start, end_time_sec: end };
    return null;
  };

  const withBusy = async (key: string, action: () => Promise<void>) => {
    setBusy(key); try { await action(); } catch (error: unknown) { toast.error(error instanceof Error ? error.message : "Operation failed"); } finally { setBusy(null); }
  };

  const resolveSources = () => withBusy("resolve", async () => {
    const next = await resolveVideoSources({ mode: sourceMode, query, count: Number(count), urls_text: urlsText });
    setResolved(next); setChosenUrls(next.candidates.map((item) => item.url));
    toast.success(`${next.candidates.length} unique source${next.candidates.length === 1 ? "" : "s"} ready for review.`);
  });
  const startDownload = () => withBusy("download", async () => {
    const candidates = resolved?.candidates.filter((item) => chosenUrls.includes(item.url)) || [];
    if (!candidates.length) throw new Error("Select at least one reviewed URL.");
    await createVideoDownloadJob({ source_mode: sourceMode, urls: candidates, max_height: 720, provenance_notes: notes });
    await refresh(); toast.success("Download job started.");
  });
  const startAnalysis = () => withBusy("analysis", async () => {
    if (!selectedAssets.length) throw new Error("Select at least one library video.");
    const job = await createVideoAnalysisJob({ asset_ids: selectedAssets, settings: { ...settings,
      audio_analyzer_enabled: audioAnalyzerEnabled,
      audio_analyzer: { ...audioSettings, project_id: referenceProject || undefined },
    } });
    setResultJobId(job.job_id); await refresh(); toast.success("Analysis job started.");
  });
  const openAnalyze = () => { if (!selectedAssets.length) { toast.error("Select at least one video first."); return; } setActiveTab("analyze"); };
  const deleteSelected = () => withBusy("delete", async () => {
    if (!selectedAssets.length) throw new Error("Select at least one video first.");
    if (!window.confirm(`Delete ${selectedAssets.length} selected video asset(s) and their generated analysis artifacts?`)) return;
    await deleteVideoAssets(selectedAssets); setSelectedAssets([]); await refresh(); toast.success("Selected video assets deleted.");
  });
  const runReferenceSearch = () => withBusy("search-results", async () => {
    if (!searchText.trim()) throw new Error("Enter a search description.");
    const mode = searchMode.semantic && searchMode.keyword ? "hybrid" : searchMode.semantic ? "semantic" : "keyword";
    if (searchBackend === "analyzer") {
      const result = await searchVideoAudioCorpus({ query: searchText, top_n: Number(topHits) || 5, mode, offset: 0 });
      setAnalyzerSearchResults(result.results);
      setSearchResults([]);
      setSearchSession(result.next_offset == null ? null : { id: "analyzer-corpus", hasMore: true, backend: "analyzer", offset: result.next_offset });
      if (!result.results.length && result.reason) toast.message(result.reason);
      return;
    }
    const result = await searchVideoReferences({ query: searchText, top_n: Number(topHits) || 5, sort_level: sortLevel, search_mode: mode, seo_enabled: false });
    setAnalyzerSearchResults([]);
    if (result.results.length) {
      setSearchResults(result.results as unknown as VideoSearchResult[]); setSearchSession({ id: result.search_id, hasMore: result.has_more, backend: "curated" });
    } else {
      // Keep already-analyzed repertoire results discoverable while the curated
      // clip index is being built or has not yet been rebuilt.
      const fallback = await searchVideoRepertoire(searchText);
      setSearchResults(fallback); setSearchSession(null);
    }
  });
  const nextReferenceSearch = () => withBusy("next-results", async () => {
    if (!searchSession) return;
    if (searchSession.backend === "analyzer") {
      const mode = searchMode.semantic && searchMode.keyword ? "hybrid" : searchMode.semantic ? "semantic" : "keyword";
      const result = await searchVideoAudioCorpus({ query: searchText, top_n: Number(topHits) || 5, mode, offset: searchSession.offset || 0 });
      setAnalyzerSearchResults((items) => [...items, ...result.results]);
      setSearchSession(result.next_offset == null ? null : { id: "analyzer-corpus", hasMore: true, backend: "analyzer", offset: result.next_offset });
      return;
    }
    const result = await nextVideoReferencePage(searchSession.id, Number(topHits) || 5);
    setSearchResults((items) => [...items, ...(result.results as unknown as VideoSearchResult[])]); setSearchSession({ id: result.search_id, hasMore: result.has_more, backend: "curated" });
  });
  const saveReferences = () => withBusy("save-references", async () => {
    if (!referenceProject) throw new Error("Choose a project first.");
    const chosen = searchResults.filter((item) => item.clip_id && selectedReferences.includes(item.clip_id));
    if (!chosen.length) throw new Error("Select at least one result first.");
    await selectVideoReferences(referenceProject, chosen as any); toast.success(`${chosen.length} reference clip(s) saved to the project.`);
  });
  const filteredAudioAssets = audioLibraryAssets.filter((asset) =>
    (!duplicateCandidatesOnly || asset.duplicate || asset.classification_duplicate_candidate) &&
    `${asset.label || ""} ${asset.filename} ${asset.category} ${asset.source_video_id || ""}`.toLowerCase().includes(audioLibraryQuery.trim().toLowerCase()));
  const sendSelectedAudio = () => sendToManualDirector(audioLibraryAssets.filter((asset) => selectedAudioPaths.includes(asset.relative_path) && asset.available !== false)
    .map((asset) => ({ slot: "audio", asset_id: asset.asset_id, filename: asset.filename, relative_path: asset.relative_path, media_type: "audio", start_time_sec: asset.start_time_sec, end_time_sec: asset.end_time_sec })));
  const deleteSelectedAudio = () => withBusy("delete-audio", async () => {
    const selected = audioLibraryAssets.filter((asset) => selectedAudioPaths.includes(asset.relative_path) && asset.available !== false);
    if (!selected.length) throw new Error("Select at least one available derived audio asset.");
    const bytes = selected.reduce((sum, asset) => sum + Number((asset as any).size || 0), 0);
    if (!window.confirm(`Delete ${selected.length} selected derived audio asset(s)${bytes ? ` (${formatBytes(bytes)})` : ""}? Original videos/source audio and event, transcript, and timestamp records will remain.`)) return;
    const result = await deleteVideoRepertoireAudioAssets(selected.map((asset) => asset.relative_path), true);
    setSelectedAudioPaths([]);
    setAudioLibraryAssets(await listVideoRepertoireAudioAssets(audioLibraryCategory));
    toast.success(`Deleted ${result.deleted.length} audio file(s); reclaimed ${formatBytes(result.reclaimed_bytes)}. Occurrence metadata was preserved.`);
    if (result.failures.length) toast.error(`${result.failures.length} file(s) could not be deleted.`);
  });
  const selectDuplicateCandidates = () => setSelectedAudioPaths((current) => {
    const ids = filteredAudioAssets.filter((asset) => asset.duplicate && asset.available !== false).map((asset) => asset.relative_path);
    return [...new Set([...current, ...ids])];
  });

  return (
    <AppShell>
      <section className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <Badge variant="outline">Video & Animation</Badge>
          <h2 className="mt-3 text-3xl font-semibold">Video Repertoire &amp; Summariser</h2>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">Summarize timestamped video clips directly, link each summary with transcript/audio cues, and search the resulting reference media semantically.</p>
        </div>
        <div className="flex flex-wrap gap-2" data-testid="capabilities">
          <Badge variant={capabilities?.ffmpeg ? "default" : "destructive"}>FFmpeg {capabilities?.ffmpeg ? "ready" : "missing"}</Badge>
          <Badge variant={capabilities?.yt_dlp ? "default" : "destructive"}>yt-dlp {capabilities?.yt_dlp ? "ready" : "missing"}</Badge>
          <Badge variant={capabilities?.video_audio_analyzer_ready ? "default" : "destructive"}>Direct analyzer {capabilities?.video_audio_analyzer_ready ? "ready" : "not ready"}</Badge>
          <Badge variant={capabilities?.pe_av_query_worker_online ? "default" : "outline"}>Semantic query {capabilities?.pe_av_query_worker_online ? "ready" : "worker offline · keywords available"}</Badge>
          <Button size="sm" variant="outline" onClick={() => refresh()}><RefreshCw className="mr-2 h-4 w-4" />Refresh</Button>
        </div>
      </section>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-5">
        <TabsList className="grid h-auto w-full grid-cols-2 lg:grid-cols-5">
          <TabsTrigger value="library">Library</TabsTrigger><TabsTrigger value="download">YouTube Download</TabsTrigger>
          <TabsTrigger value="analyze">Analyze</TabsTrigger><TabsTrigger value="results">Results</TabsTrigger><TabsTrigger value="audio-assets">Audio Assets</TabsTrigger>
        </TabsList>

        <TabsContent value="library" className="space-y-5">
          <Card><CardHeader><CardTitle>Add videos</CardTitle><CardDescription>Upload a local video or register the existing standalone summarizer samples without moving the originals.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 lg:grid-cols-[1fr_auto]">
              <div className="space-y-3"><Input type="file" accept="video/*" onChange={(event) => setUpload(event.target.files?.[0] || null)} /><Input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="License or provenance notes" /></div>
              <div className="flex flex-wrap gap-2"><Button disabled={!upload || Boolean(busy)} onClick={() => withBusy("upload", async () => { await uploadVideoAsset(upload!, notes); setUpload(null); await refresh(); toast.success("Video added."); })}><Upload className="mr-2 h-4 w-4" />Upload</Button>
                <Button variant="outline" disabled={!capabilities?.legacy_video_count || Boolean(busy)} onClick={() => withBusy("legacy", async () => { await importLegacyVideoAssets(); await refresh(); toast.success("Legacy videos registered."); })}><FolderInput className="mr-2 h-4 w-4" />Import existing ({capabilities?.legacy_video_count || 0})</Button></div>
            </CardContent></Card>
          <Card className="border-primary/25"><CardContent className="flex flex-wrap items-center justify-between gap-3 py-4"><div className="text-sm text-muted-foreground"><strong className="text-foreground">{selectedAssets.length}</strong> video{selectedAssets.length === 1 ? "" : "s"} selected</div><div className="flex flex-wrap gap-2"><Button disabled={!selectedAssets.length || Boolean(busy)} onClick={openAnalyze}><Play className="mr-2 h-4 w-4" />Analyze selected</Button><Button variant="outline" disabled={!selectedAssets.length || Boolean(busy)} onClick={() => sendToManualDirector(selectedAssetRecords.map((asset) => ({ slot: "video", asset_id: asset.asset_id, filename: asset.filename, media_type: "video" })))}><Send className="mr-2 h-4 w-4" />Send to Manual Director</Button><Button variant="outline" disabled={!selectedAssets.length || Boolean(busy)} onClick={deleteSelected}><Trash2 className="mr-2 h-4 w-4" />Delete selected</Button></div></CardContent></Card>
          <div className="grid gap-5 lg:grid-cols-2">
            {assets.map((asset) => <Card key={asset.asset_id} data-testid="video-asset"><CardHeader><div className="flex justify-between gap-3"><div><CardTitle className="line-clamp-1 text-lg">{asset.title}</CardTitle><CardDescription>{asset.channel || asset.source_mode}</CardDescription></div><Checkbox checked={selectedAssets.includes(asset.asset_id)} onCheckedChange={(checked) => setSelectedAssets((current) => checked ? [...new Set([...current, asset.asset_id])] : current.filter((id) => id !== asset.asset_id))} aria-label={`Select ${asset.title}`} /></div></CardHeader>
              <CardContent className="space-y-3"><video controls preload="metadata" className="aspect-video w-full rounded-xl bg-black" src={getVideoAssetUrl(asset.asset_id)} /><div className="flex flex-wrap gap-2 text-xs"><Badge variant="secondary">{formatDuration(asset.media.duration)}</Badge><Badge variant="secondary">{asset.media.width || "?"}×{asset.media.height || "?"}</Badge><Badge variant="secondary">{formatBytes(asset.size)}</Badge><Badge variant="outline">{asset.analysis_ids.length} analyses</Badge></div><p className="line-clamp-2 text-xs text-muted-foreground">{asset.provenance_notes || asset.source_url || asset.sha256}</p></CardContent></Card>)}
            {!assets.length && <Card className="lg:col-span-2"><CardContent className="py-14 text-center text-sm text-muted-foreground">No registered videos yet. Upload one or import the existing samples.</CardContent></Card>}
          </div>
        </TabsContent>

        <TabsContent value="download" className="space-y-5">
          <Card><CardHeader><CardTitle>Review before downloading</CardTitle><CardDescription>Only download content you are permitted to store and reuse. Playlists, private videos, cookies, and arbitrary yt-dlp flags are disabled.</CardDescription></CardHeader>
            <CardContent className="space-y-4"><div className="flex flex-wrap gap-2">{["search", "paste", "file"].map((mode) => <Button key={mode} variant={sourceMode === mode ? "default" : "outline"} onClick={() => { setSourceMode(mode); setResolved(null); }}>{mode === "search" ? "Search" : mode === "paste" ? "Paste URLs" : "URL File"}</Button>)}</div>
              {sourceMode === "search" ? <div className="grid gap-3 md:grid-cols-[1fr_100px]"><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search YouTube" /><Input type="number" min="1" max="25" value={count} onChange={(event) => setCount(event.target.value)} /></div> : sourceMode === "paste" ? <Textarea value={urlsText} onChange={(event) => setUrlsText(event.target.value)} placeholder="One URL per line" /> : <Input type="file" accept=".txt,text/plain" onChange={(event) => { const file = event.target.files?.[0]; if (file) file.text().then(setUrlsText); }} />}
              <Button disabled={Boolean(busy) || (sourceMode === "search" ? !query.trim() : !urlsText.trim())} onClick={resolveSources}>{busy === "resolve" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}Resolve sources</Button>
              {resolved && <div className="space-y-3 rounded-2xl border p-4"><div className="flex items-center justify-between"><p className="font-medium">Reviewed sources</p><Badge>{chosenUrls.length} selected</Badge></div>{resolved.candidates.map((item) => <label key={item.url} className="flex gap-3 rounded-xl border p-3"><Checkbox checked={chosenUrls.includes(item.url)} onCheckedChange={(checked) => setChosenUrls((current) => checked ? [...current, item.url] : current.filter((url) => url !== item.url))} /><span className="min-w-0"><span className="block truncate text-sm font-medium">{item.title}</span><span className="block truncate text-xs text-muted-foreground">{item.channel || item.url}</span></span></label>)}<Button disabled={!chosenUrls.length || Boolean(busy)} onClick={startDownload}><Download className="mr-2 h-4 w-4" />Download selected at 720p</Button></div>}
            </CardContent></Card>
          <JobList jobs={downloads} onCancel={(job) => withBusy(job.job_id, async () => { await cancelVideoJob("youtube", job.job_id); await refresh(); })} onRetry={(job) => withBusy(job.job_id, async () => { await retryVideoJob("youtube", job.job_id); await refresh(); })} />
        </TabsContent>

        <TabsContent value="analyze" className="space-y-5">
          <Card><CardHeader><CardTitle>Analyze selected videos</CardTitle><CardDescription>Selected: {selectedAssetRecords.map((asset) => asset.title).join(", ") || "none"}. Analysis runs sequentially and survives page refreshes.</CardDescription></CardHeader>
            <CardContent className="space-y-5"><div className="grid gap-4 md:grid-cols-2"><div className="max-w-sm space-y-2"><Label htmlFor="extract-fps">Scene/change sampling rate (FPS)</Label><Input id="extract-fps" type="number" min="0.5" max="24" step="0.5" value={settings.extract_fps} onChange={(event) => setSettings((current) => ({ ...current, extract_fps: Number(event.target.value) }))} /><p className="text-xs text-muted-foreground">Samples the source for scene and cut boundaries; it is not the source video FPS.</p></div><div className="space-y-3 rounded-xl border p-3"><label className="flex items-center justify-between gap-3 text-sm"><span><span className="block font-medium">Attach cut-to-cut subdivisions</span><span className="text-xs text-muted-foreground">Timestamp-only source intervals; no extra files or summaries.</span></span><Switch aria-label="Attach cut-to-cut subdivisions" checked={settings.extract_cut_clips} onCheckedChange={(checked) => setSettings((current) => ({ ...current, extract_cut_clips: checked }))} /></label>{settings.extract_cut_clips && <div className="grid gap-3 sm:grid-cols-2"><label className="space-y-1 text-xs"><span>Change sensitivity</span><Input aria-label="Cut change sensitivity" type="number" min="0.05" max="0.9" step="0.01" value={settings.cut_boundary_threshold} onChange={(event) => setSettings((current) => ({ ...current, cut_boundary_threshold: Number(event.target.value) }))} /></label><label className="space-y-1 text-xs"><span>Minimum cut length (seconds)</span><Input aria-label="Minimum cut length" type="number" min="0.25" max="20" step="0.25" value={settings.min_cut_seconds} onChange={(event) => setSettings((current) => ({ ...current, min_cut_seconds: Number(event.target.value) }))} /></label></div>}<p className="text-xs text-muted-foreground">Cut points are estimated from motion-compensated sampled-frame differences, not frame-accurate edit metadata. Original scene boundaries remain unchanged.</p></div></div>
              {!readiness && <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">Direct analysis requires FFmpeg/FFprobe, Docker, the local InternVideo3 and PE-AV checkpoints, and the isolated analyzer images. Ollama and ComfyUI are not required. Refresh capabilities after preparing the analyzer.</div>}
              {capabilities?.active_analysis_job && <div className="rounded-xl border p-3 text-sm">Active GPU job: <strong>{capabilities.active_analysis_job}</strong>. ComfyUI is never stopped automatically.</div>}
              <Button disabled={!readiness || !selectedAssets.length || Boolean(capabilities?.active_analysis_job) || Boolean(busy)} onClick={startAnalysis}><Play className="mr-2 h-4 w-4" />Start analysis</Button>
            </CardContent></Card>
          <Card className="border-primary/20"><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle>Direct video &amp; optional audio analysis</CardTitle><CardDescription>InternVideo3 analyzes timestamped video clips directly and writes clip/full-video summaries; PE-AV encodes them for semantic search. Audio extraction, transcript, diarization, events, and reusable audio collection are separate options. Video and selected media remain in Video Repertoire.</CardDescription></div><label className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm"><span>Analyze audio too</span><Switch aria-label="Run upgraded audio analyzer" checked={audioAnalyzerEnabled} onCheckedChange={setAudioAnalyzerEnabled} /></label></div></CardHeader>
            {audioAnalyzerEnabled && <CardContent className="space-y-5"><div><p className="mb-2 text-sm font-medium">Audio preparation and analysis (all retained outputs live in Video Repertoire)</p><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{([
                ["extract_source_audio", "Preserve source audio bitstream"], ["extract_preview_mp3", "Create MP3 preview"],
                ["detect_speech", "Speech & transcript"], ["diarize_speakers", "Speaker diarization"], ["detect_music", "Music events"],
                ["detect_sfx", "SFX & ambience events"], ["create_audio_embeddings", "Audio semantic embeddings"], ["create_av_embeddings", "Audio + video embeddings"],
              ] as const).map(([key, label]) => <label key={key} className="flex items-center justify-between gap-3 rounded-xl border p-3 text-sm"><span>{label}</span><Switch aria-label={label} checked={audioSettings[key]} onCheckedChange={(checked) => setAudioSettings((current) => ({ ...current, [key]: checked }))} /></label>)}</div></div>
              <div className="rounded-xl border p-4"><p className="mb-2 text-sm font-medium">Scene boundary and support-sample reduction</p><p className="mb-3 text-xs text-muted-foreground">Scene/cut detection remains enabled. Motion-compensated visual change reduces redundant support timestamps while recording global camera motion separately. This direct workflow does not save selected JPEGs or run a separate image caption per sample; InternVideo3 receives each cut-defined video clip directly.</p><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{([ ["adaptive_sampling", "Frame shaving by visual change"], ["preserve_scene_anchors", "Preserve first/last scene anchors"], ["keep_intermediate_samples", "Keep temporary decode samples"] ] as const).map(([key, label]) => <label key={key} className="flex items-center justify-between gap-3 rounded-xl border p-3 text-sm"><span>{label}</span><Switch aria-label={label} checked={audioSettings[key]} onCheckedChange={(checked) => setAudioSettings((current) => ({ ...current, [key]: checked }))} /></label>)}</div><label className="mt-3 flex max-w-sm items-center gap-3 text-sm">Frame-change threshold <input aria-label="Frame-change threshold" type="number" min="0" max="1" step="0.01" value={audioSettings.frame_change_threshold} onChange={(event) => setAudioSettings((current) => ({ ...current, frame_change_threshold: Number(event.target.value) }))} className="h-9 w-24 rounded-md border bg-background px-2" /></label></div>
              <div className="flex flex-wrap items-end gap-4"><div className="space-y-2"><Label htmlFor="audio-demucs">Source separation</Label><select id="audio-demucs" className="h-10 rounded-md border bg-background px-3" value={audioSettings.run_demucs} onChange={(event) => setAudioSettings((current) => ({ ...current, run_demucs: event.target.value }))}><option value="AUTO">Automatic (recommended)</option><option value="off">Off</option><option value="2-stem">2 stems</option><option value="4-stem">4 stems</option><option value="6-stem">6 stems</option></select></div><p className="max-w-2xl text-xs text-muted-foreground">Automatic separation only runs when the analyzer determines stems are useful. It is independent from sound-event detection.</p></div>
              <div><p className="mb-2 text-sm font-medium">Save reusable audio assets (off by default)</p><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{([
                ["collect_voice_examples", "Save voice examples"], ["collect_music_clips", "Save music clips"], ["collect_sfx_clips", "Save SFX / ambience clips"],
              ] as const).map(([key, label]) => <label key={key} className="flex items-center justify-between gap-3 rounded-xl border p-3 text-sm"><span>{label}</span><Switch aria-label={label} checked={audioSettings[key]} onCheckedChange={(checked) => setAudioSettings((current) => ({ ...current, [key]: checked }))} /></label>)}</div><p className="mt-2 text-xs text-muted-foreground">Only toggled clips are copied to Video Repertoire; all records remain timestamped and linked to their source run.</p></div>
            </CardContent>}
          </Card>
          <JobList jobs={analyses} onSelect={(job) => setResultJobId(job.job_id)}
            onStop={(job) => withBusy(job.job_id, async () => {
              if (!window.confirm(`Stop and delete ${job.job_id}? Its job files and generated clips will be removed; the source video and shared repertoire assets will be kept.`)) return;
              await stopVideoAnalysisJob(job.job_id); await refresh(); toast.success("Analysis stopped and its private job files were deleted.");
            })}
            onDelete={(job) => withBusy(`delete-${job.job_id}`, async () => {
              if (!window.confirm(`Delete ${job.job_id} and its job-owned files? The source video and shared repertoire assets will be kept.`)) return;
              await deleteVideoAnalysisJob(job.job_id); await refresh(); toast.success("Analysis job deleted.");
            })} />
        </TabsContent>

        <TabsContent value="results" className="space-y-5">
          <div className="grid gap-4 lg:grid-cols-[300px_1fr]"><Card><CardHeader><CardTitle>Analysis runs</CardTitle></CardHeader><CardContent><div className="space-y-2">{analyses.map((job) => <div key={job.job_id} className="flex gap-2"><Button className="h-auto min-w-0 flex-1 justify-start py-3 text-left" variant={selectedResult?.job_id === job.job_id ? "default" : "outline"} onClick={() => setResultJobId(job.job_id)}><span className="truncate"><span className="block truncate">{job.job_id}</span><span className="block text-xs opacity-70">{job.status} · {job.stage}</span></span></Button><Button aria-label={`Delete ${job.job_id}`} title="Delete job and owned files" size="icon" variant="outline" onClick={() => withBusy(`delete-${job.job_id}`, async () => { if (!window.confirm(`Delete ${job.job_id} and its job-owned files? The source video and shared repertoire assets will be kept.`)) return; await deleteVideoAnalysisJob(job.job_id); await refresh(); toast.success("Analysis job deleted."); })}><Trash2 className="h-4 w-4" /></Button></div>)}</div></CardContent></Card>
            <div className="space-y-5">{selectedResult ? <ResultViewer job={selectedResult} onSend={sendToManualDirector} /> : <Card><CardContent className="py-16 text-center text-sm text-muted-foreground">No analysis results yet.</CardContent></Card>}</div></div>
          <Card><CardHeader><CardTitle>Find reusable clips</CardTitle><CardDescription>Search the new analyzer corpus or the original curated references. Analyzer semantic results are only shown when real model embeddings are available; word search remains available independently.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="flex flex-wrap items-center gap-4 rounded-xl border p-3"><select aria-label="Search corpus" className="h-9 rounded-md border bg-background px-2 text-sm" value={searchBackend} onChange={(event) => { setSearchBackend(event.target.value as "analyzer" | "curated"); setAnalyzerSearchResults([]); setSearchResults([]); setSearchSession(null); }}><option value="analyzer">Video + audio analyzer</option><option value="curated">Curated video references</option></select><label className="flex items-center gap-2 text-sm"><Switch checked={searchMode.semantic} onCheckedChange={(checked) => setSearchMode((current) => ({ ...current, semantic: checked }))} />Semantic search</label><label className="flex items-center gap-2 text-sm"><Switch checked={searchMode.keyword} onCheckedChange={(checked) => setSearchMode((current) => ({ ...current, keyword: checked }))} />Word similarity</label><label className="flex items-center gap-2 text-sm">Top hits<input aria-label="Top hits per page" className="h-9 w-20 rounded-md border bg-background px-2" type="number" min="1" max="50" value={topHits} onChange={(event) => setTopHits(event.target.value)} /></label>{searchBackend === "curated" && <select aria-label="Result grouping" className="h-9 rounded-md border bg-background px-2 text-sm" value={sortLevel} onChange={(event) => setSortLevel(event.target.value as typeof sortLevel)}><option value="scene">Scene</option><option value="subscene">Sub-scene</option><option value="clip">Clip</option></select>}</div><div className="flex gap-2"><Input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="Sword fight, courtroom argument, product reveal..." /><Button aria-label="Search clips" disabled={Boolean(busy) || (!searchMode.semantic && !searchMode.keyword)} onClick={runReferenceSearch}><Search className="h-4 w-4" /></Button></div>{analyzerSearchResults.length > 0 && <div className="space-y-3"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs text-muted-foreground">{analyzerSearchResults.length} analyzer result(s) · results include timestamps and are deduplicated across reruns.</p><Button size="sm" variant="outline" disabled={!selectedDirectorReferences.length} onClick={() => sendToManualDirector(selectedDirectorReferences)}><Send className="mr-2 h-4 w-4" />Send selected ({selectedDirectorReferences.length}) to Manual Director</Button></div>{analyzerSearchResults.map((item) => { const reference = analyzerReference(item); const selected = Boolean(reference && selectedDirectorReferences.some((row) => row.asset_id === reference.asset_id && row.relative_path === reference.relative_path)); return <AnalyzerSearchResultCard key={item.result_id} item={item} selected={selected} onSelect={() => { if (!reference) { toast.error("This result has no safe, reusable repertoire path."); return; } setSelectedDirectorReferences((current) => selected ? current.filter((row) => !(row.asset_id === reference.asset_id && row.relative_path === reference.relative_path)) : [...current, reference]); }} onSelectCut={(cut) => { if (!item.asset_id?.startsWith("video-")) { toast.error("The source video is not registered in the repertoire."); return; } const ref: ManualDirectorReference = { slot: "video", asset_id: item.asset_id, filename: `${item.source_file || item.video_id} · ${cut.cut_id}`, media_type: "video", start_time_sec: cut.start_time_sec, end_time_sec: cut.end_time_sec }; setSelectedDirectorReferences((current) => current.some((row) => row.asset_id === ref.asset_id && row.start_time_sec === ref.start_time_sec && row.end_time_sec === ref.end_time_sec) ? current : [...current, ref]); toast.success(`Timestamped cut ${cut.cut_id} staged.`); }} />; })}</div>}{searchResults.length > 0 && <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground"><span>{searchResults.length} curated result(s) loaded · {selectedReferences.length} selected</span><div className="flex gap-2"><select aria-label="Reference project" className="h-8 rounded-md border bg-background px-2" value={referenceProject} onChange={(event) => { setReferenceProject(event.target.value); localStorage.setItem("story_builder.current_project", event.target.value); }}><option value="">Save to project…</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}</select><Button size="sm" variant="outline" disabled={!selectedReferences.length || !referenceProject} onClick={saveReferences}>Save selected</Button><Button size="sm" variant="outline" onClick={() => { const rows = searchResults.filter((item) => selectedReferences.includes(item.clip_id || "") && item.asset_id?.startsWith("video-")).map((item) => ({ slot: "video", asset_id: item.asset_id!, filename: item.source_video || item.title || item.asset_id!, media_type: "video", start_time_sec: item.start_time_sec, end_time_sec: item.end_time_sec } as ManualDirectorReference)); sendToManualDirector(rows); }} disabled={!searchResults.some((item) => selectedReferences.includes(item.clip_id || "") && item.asset_id?.startsWith("video-"))}><Send className="mr-1 h-3.5 w-3.5"/>Send compatible selected</Button></div></div>}{searchResults.map((item, index) => <div key={`${item.clip_id || item.job_id}-${item.scene_id}-${index}`} className="rounded-xl border p-3 text-sm"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{item.title || item.source_video} · {item.scene_id}</p><p className="mt-1 text-muted-foreground">{item.summary}</p></div><Button size="sm" variant={item.clip_id && selectedReferences.includes(item.clip_id) ? "default" : "outline"} onClick={() => item.clip_id && setSelectedReferences((items) => items.includes(item.clip_id!) ? items.filter((id) => id !== item.clip_id) : [...items, item.clip_id!])}>{item.clip_id && selectedReferences.includes(item.clip_id) ? <><Check className="mr-1 h-3 w-3" />Selected</> : "Select"}</Button></div>{item.clip_path && <video className="mt-3 max-h-64 w-full rounded-lg bg-black" controls src={getVideoArtifactUrl(item.clip_path)} />}</div>)}{searchSession?.hasMore && <Button variant="outline" onClick={nextReferenceSearch}>Next results</Button>}{!analyzerSearchResults.length && !searchResults.length && searchBackend === "analyzer" && searchSession === null && <p className="text-xs text-muted-foreground">Search the analyzer corpus to retrieve indexed scenes, frames, speech, music and sound events.</p>}</CardContent></Card>
        </TabsContent>

        <TabsContent value="audio-assets" className="space-y-5">
          <Card><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle>Reusable audio library</CardTitle><CardDescription>Same-class SFX/music/ambience are grouped for review, not assumed identical. Exact-file matches are confirmed duplicates. Both markers are review-only; deleting a derived file preserves timestamps and source media.</CardDescription></div><Button variant="outline" onClick={() => { setAudioLibraryBusy(true); listVideoRepertoireAudioAssets(audioLibraryCategory).then(setAudioLibraryAssets).catch((error) => toast.error(error instanceof Error ? error.message : "Could not refresh audio assets")).finally(() => setAudioLibraryBusy(false)); }}><RefreshCw className={`mr-2 h-4 w-4 ${audioLibraryBusy ? "animate-spin" : ""}`} />Refresh</Button></div></CardHeader><CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_240px]"><Input aria-label="Search audio assets" value={audioLibraryQuery} onChange={(event) => setAudioLibraryQuery(event.target.value)} placeholder="Search label, source, or category" /><select aria-label="Audio asset category" className="h-10 rounded-md border bg-background px-3" value={audioLibraryCategory} onChange={(event) => setAudioLibraryCategory(event.target.value)}><option value="all">All audio categories</option><option value="voices">Voice examples</option><option value="music">Music</option><option value="sfx">Sound effects</option><option value="ambience">Ambience</option><option value="isolated">SAM isolations</option></select></div>
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={duplicateCandidatesOnly} onChange={(event) => setDuplicateCandidatesOnly(event.target.checked)} />Duplicate / same-class review groups</label><span className="text-xs text-muted-foreground">{selectedAudioPaths.length} selected · same-class grouping never selects/deletes automatically</span><div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={selectDuplicateCandidates} disabled={!filteredAudioAssets.some((asset) => asset.duplicate && asset.available !== false)}>Select exact duplicates</Button><Button size="sm" variant="outline" onClick={sendSelectedAudio} disabled={!selectedAudioPaths.some((path) => audioLibraryAssets.some((asset) => asset.relative_path === path && asset.available !== false))}><Send className="mr-1.5 h-3.5 w-3.5"/>Send selected to Manual Director</Button><Button size="sm" variant="destructive" onClick={() => void deleteSelectedAudio()} disabled={!selectedAudioPaths.length || Boolean(busy)}><Trash2 className="mr-1.5 h-3.5 w-3.5"/>Delete selected</Button></div></div>
            {audioLibraryBusy && <div role="status" className="flex items-center gap-2 rounded-lg border p-3 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin"/>Loading saved audio assets…</div>}
            {!audioLibraryBusy && filteredAudioAssets.length === 0 && <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">No saved audio assets match this view. In Analyze, enable an audio collection toggle, or approve a SAM isolation.</p>}
            <div className="grid gap-3 lg:grid-cols-2">{filteredAudioAssets.map((asset) => <div key={`${asset.category}-${asset.asset_id}-${asset.relative_path}`} className="min-w-0 space-y-3 rounded-xl border p-4"><div className="flex flex-wrap items-start justify-between gap-2"><label className="flex min-w-0 items-start gap-2"><input type="checkbox" aria-label={`Select ${asset.filename}`} disabled={asset.available === false} checked={selectedAudioPaths.includes(asset.relative_path)} onChange={(event) => setSelectedAudioPaths((current) => event.target.checked ? [...new Set([...current, asset.relative_path])] : current.filter((path) => path !== asset.relative_path))}/><span className="min-w-0"><span className="block truncate font-medium">{asset.label || asset.filename}</span><span className="mt-1 block break-all text-xs text-muted-foreground">{asset.filename}</span></span></label><div className="flex gap-1"><Badge variant="secondary">{asset.category}</Badge>{asset.duplicate && <Badge variant="outline" title="Exact file hash match; retained for manual review">Exact duplicate</Badge>}{asset.classification_duplicate_candidate && <Badge variant="outline" title="Same classifier label in this project; different occurrences may still be distinct">Same-class review · {asset.classification_group_size}</Badge>}</div></div>{asset.available !== false ? <audio controls preload="none" className="w-full" src={getVideoRepertoireAudioAssetUrl(asset.relative_path)}/> : <p className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">Derived audio deleted; occurrence and timestamp metadata retained.</p>}<p className="text-xs text-muted-foreground">{asset.start_time_sec != null ? `${Number(asset.start_time_sec).toFixed(2)}–${Number(asset.end_time_sec || 0).toFixed(2)} sec` : "Saved audio reference"}{asset.source_video_id ? ` · source ${asset.source_video_id}` : ""}{asset.project_id ? ` · project ${asset.project_id}` : ""}{asset.confidence != null ? ` · ${Math.round(Number(asset.confidence) * 100)}% confidence` : ""}{asset.duplicate_group_id ? ` · exact-match group ${asset.duplicate_group_id}` : ""}{asset.classification_group_label ? ` · same classifier label: ${asset.classification_group_label}` : ""}{asset.isolation_status === "unisolated_source_mix" ? " · mixed event excerpt; use on-demand SAM isolation for a separated effect" : ""}</p>{asset.semantic_mood && <div className="rounded-md bg-muted/40 p-2 text-xs"><span className="font-medium">Estimated mood: {asset.semantic_mood.top_match}</span><span className="block text-muted-foreground">PE-AV relative similarity (not calibrated probability); scores available per event.</span></div>}</div>)}</div>
          </CardContent></Card>
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}

function AnalyzerSearchResultCard({ item, selected, onSelect, onSelectCut }: { item: VideoAudioCorpusResult; selected: boolean; onSelect: () => void; onSelectCut: (cut: NonNullable<VideoAudioCorpusResult["cuts"]>[number]) => void }) {
  const start = Number(item.start_time_sec || 0);
  const end = Number(item.end_time_sec || 0);
  const artifactUrl = item.artifact_path
    ? getVideoAudioAnalyzerArtifactUrl(item.run_id, item.artifact_path)
    : "";
  const timedUrl = `${artifactUrl}#t=${start},${end}`;
  return <div className="rounded-xl border p-3 text-sm">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0"><p className="font-medium">{item.source_file || item.video_id} · {item.scene_id || item.kind}</p>
        <p className="mt-1 text-muted-foreground">{item.text}</p>
        <p className="mt-2 text-xs text-muted-foreground">{start.toFixed(2)}–{end.toFixed(2)} sec · {item.kind} · score {Number(item.score || 0).toFixed(3)}</p>
      </div><div className="flex items-center gap-2"><Badge variant="outline">{item.kind}</Badge><Button size="sm" variant={selected ? "default" : "outline"} onClick={onSelect}>{selected ? "Selected" : "Select"}</Button></div>
    </div>
    {item.kind === "audio_event" && artifactUrl && <audio aria-label="Matched audio event" className="mt-3 w-full" controls preload="metadata" src={timedUrl} />}
    {item.clip_artifact_path && <video aria-label="Matched analyzer video clip" className="mt-3 max-h-64 w-full rounded-lg bg-black" controls preload="metadata" src={getVideoAudioAnalyzerArtifactUrl(item.run_id, item.clip_artifact_path)} />}
    {item.kind !== "audio_event" && !item.clip_artifact_path && item.asset_id && <video aria-label="Matched source video interval" className="mt-3 max-h-64 w-full rounded-lg bg-black" controls preload="metadata" src={`${getVideoAssetUrl(item.asset_id)}#t=${start},${end}`} />}
    {item.kind !== "audio_event" && !item.clip_artifact_path && !item.asset_id && artifactUrl && <img className="mt-3 max-h-64 rounded-lg" src={artifactUrl} alt={`Matched frame at ${start.toFixed(2)} seconds`} />}
    {item.kind === "audio_event" && item.asset_id && <details className="mt-3"><summary className="cursor-pointer text-xs text-muted-foreground">View source video context</summary><video aria-label="Audio event source video context" className="mt-2 max-h-64 w-full rounded-lg bg-black" controls preload="metadata" src={`${getVideoAssetUrl(item.asset_id)}#t=${start},${end}`} /></details>}
    {Boolean(item.cuts?.length) && <details className="mt-3 rounded-lg border p-3"><summary className="cursor-pointer text-xs font-medium">Cut-to-cut subdivisions ({item.cuts?.length}) · no separate summaries</summary><div className="mt-3 space-y-3">{item.cuts?.map((cut) => <div key={cut.cut_id} className="flex flex-wrap items-center gap-2 border-t pt-3 first:border-0 first:pt-0"><span className="min-w-40 flex-1 text-xs text-muted-foreground">{cut.cut_id} · {cut.start_time_sec.toFixed(2)}–{cut.end_time_sec.toFixed(2)} sec · estimated boundary</span>{item.asset_id && <video aria-label={`Cut preview ${cut.cut_id}`} className="max-h-28 w-48 rounded bg-black" controls preload="metadata" src={`${getVideoAssetUrl(item.asset_id)}#t=${cut.start_time_sec},${cut.end_time_sec}`} />}<Button size="sm" variant="outline" onClick={() => onSelectCut(cut)}>Add timestamped cut</Button></div>)}</div></details>}
  </div>;
}

function ResultViewer({ job, onSend }: { job: VideoJob; onSend: (references: ManualDirectorReference[]) => void }) {
  const audioRuns = (job.result?.audio_analysis as Array<Record<string, any>> | undefined) || [];
  return <><ResultViewerContent job={job} onSend={onSend} />{audioRuns.filter((run) => run.status === "completed" && run.run_id && Array.isArray(run.audio_events) && run.audio_events.length > 0).map((run) => <SAMIsolationPanel key={`${run.asset_id}-${run.run_id}`} runId={String(run.run_id)} events={run.audio_events as Array<Record<string, unknown>>} />)}</>;
}

function SAMIsolationPanel({ runId, events }: { runId: string; events: Array<Record<string, unknown>> }) {
  const [eventId, setEventId] = useState(String(events[0]?.event_id || ""));
  const [prompt, setPrompt] = useState(String(events[0]?.label || events[0]?.event_type || "sound"));
  const [preview, setPreview] = useState<{ temporary_id: string; prompt: string } | null>(null);
  const [busy, setBusy] = useState<"isolate" | "review" | "discard" | null>(null);
  const selectedEvent = events.find((item) => String(item.event_id) === eventId) || events[0];
  const chooseEvent = (id: string) => {
    const next = events.find((item) => String(item.event_id) === id);
    setEventId(id);
    setPrompt(String(next?.label || next?.event_type || "sound"));
    setPreview(null);
  };
  const isolate = async () => {
    if (!selectedEvent || !prompt.trim()) return;
    setBusy("isolate");
    try {
      const result = await isolateVideoAudioEvent(runId, String(selectedEvent.event_id), prompt.trim());
      const temporaryId = String(result.temporary_id || "");
      if (!temporaryId) throw new Error("SAM Audio did not return a temporary preview ID.");
      setPreview({ temporary_id: temporaryId, prompt: prompt.trim() });
      toast.success("Temporary SAM Audio preview is ready.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "SAM Audio isolation failed.");
    } finally { setBusy(null); }
  };
  const review = async () => {
    if (!preview) return;
    setBusy("review");
    try {
      const result = await reviewVideoAudioSamPreview(preview.temporary_id);
      const directorReview = result.director_review as Record<string, unknown> | undefined;
      setPreview(null);
      if (result.status === "saved") toast.success(`Codex saved the sound reference: ${String(directorReview?.summary || "")}`);
      else toast.message(`Codex discarded the temporary preview: ${String(directorReview?.summary || "")}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Codex review failed; the preview remains temporary.");
    } finally { setBusy(null); }
  };
  const discard = async () => {
    if (!preview) return;
    setBusy("discard");
    try {
      await discardVideoAudioSamPreview(preview.temporary_id);
      setPreview(null);
      toast.success("Temporary SAM preview deleted.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete the temporary preview.");
    } finally { setBusy(null); }
  };
  return <Card data-testid="sam-isolation-panel"><CardHeader><CardTitle>On-demand sound isolation</CardTitle><CardDescription>Choose one detected event and describe the sound to isolate. The preview is temporary; Codex decides whether it is useful enough to save. Codex reviews metadata and technical validity—it does not listen to the waveform.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"><label className="space-y-1 text-sm"><span className="font-medium">Audio event</span><select aria-label="SAM event" className="h-10 w-full rounded-md border bg-background px-3" value={eventId} onChange={(event) => chooseEvent(event.target.value)}>{events.map((item) => <option key={String(item.event_id)} value={String(item.event_id)}>{String(item.label || item.event_type || "Audio event")} · {Number(item.start_time_sec || 0).toFixed(1)}–{Number(item.end_time_sec || 0).toFixed(1)}s</option>)}</select></label><label className="space-y-1 text-sm"><span className="font-medium">Sound to isolate</span><Input aria-label="SAM isolation prompt" value={prompt} maxLength={500} onChange={(event) => setPrompt(event.target.value)} /></label><div className="flex items-end"><Button disabled={Boolean(busy) || !prompt.trim()} onClick={isolate}>{busy === "isolate" ? <><Loader2 className="animate-spin" />Isolating…</> : "Preview isolation"}</Button></div></div>{selectedEvent && <p className="text-xs text-muted-foreground">Selected interval: {Number(selectedEvent.start_time_sec || 0).toFixed(2)}–{Number(selectedEvent.end_time_sec || 0).toFixed(2)} sec · {Math.round(Number(selectedEvent.confidence || 0) * 100)}% detector confidence</p>}{busy === "isolate" && <div role="status" className="space-y-2 rounded-xl border p-3 text-sm text-muted-foreground"><div className="flex items-center gap-2"><Loader2 className="animate-spin" />SAM Audio is isolating the selected interval; first use can take a few minutes.</div><Progress className="h-1.5" /></div>}{preview && <div className="space-y-3 rounded-xl border border-primary/20 bg-primary/5 p-4"><div><p className="text-sm font-medium">Temporary isolation preview</p><p className="text-xs text-muted-foreground">Prompt: {preview.prompt}. This file expires automatically if you do not review or discard it.</p></div><audio controls preload="metadata" className="w-full" src={getVideoAudioSamPreviewUrl(preview.temporary_id)} /><div className="flex flex-wrap gap-2"><Button disabled={Boolean(busy)} onClick={review}>{busy === "review" ? <><Loader2 className="animate-spin" />Codex reviewing…</> : "Codex review & save if useful"}</Button><Button variant="outline" disabled={Boolean(busy)} onClick={discard}>{busy === "discard" ? <><Loader2 className="animate-spin" />Deleting…</> : "Discard preview"}</Button></div>{busy === "review" && <p role="status" className="text-xs text-muted-foreground">Director review in progress. If review fails, the preview stays temporary and can be retried or discarded.</p>}</div>}</CardContent></Card>;
}

function JobList({ jobs, onCancel, onRetry, onStop, onDelete, onSelect }: { jobs: VideoJob[]; onCancel?: (job: VideoJob) => void; onRetry?: (job: VideoJob) => void; onStop?: (job: VideoJob) => void; onDelete?: (job: VideoJob) => void; onSelect?: (job: VideoJob) => void }) {
  if (!jobs.length) return null;
  return <Card><CardHeader><CardTitle>Job history</CardTitle></CardHeader><CardContent className="space-y-3">{jobs.map((job) => <div key={job.job_id} data-testid="video-job" className="rounded-xl border p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><button className="font-medium hover:underline" onClick={() => onSelect?.(job)}>{job.job_id}</button><p className="text-xs text-muted-foreground">{job.stage} · {job.message}</p></div><div className="flex flex-wrap items-center gap-2"><Badge variant={job.status === "completed" ? "default" : job.status === "failed" ? "destructive" : "outline"}>{job.status}</Badge>{onStop && !terminal.has(job.status) && <Button size="sm" variant="outline" aria-label={`Stop ${job.job_id}`} onClick={() => onStop(job)}><X className="mr-1 h-3 w-3" />Stop &amp; delete</Button>}{onCancel && !terminal.has(job.status) && <Button size="sm" variant="outline" onClick={() => onCancel(job)}><X className="mr-1 h-3 w-3" />Cancel</Button>}{onRetry && ["failed", "cancelled", "interrupted"].includes(job.status) && <Button size="sm" variant="outline" onClick={() => onRetry(job)}>Retry</Button>}{onDelete && <Button size="sm" variant="ghost" aria-label={`Delete ${job.job_id}`} title="Delete job and its owned files" onClick={() => onDelete(job)}><Trash2 className="h-4 w-4" /><span className="ml-1">Delete</span></Button>}</div></div><Progress className="mt-3" value={job.progress || 0} /></div>)}</CardContent></Card>;
}

function AnalyzerVisualEvidence({ runId, scenes }: { runId: string; scenes: Array<Record<string, any>> }) {
  if (!scenes.length) return null;
  return <details className="rounded-xl border p-4" data-testid="analyzer-visual-evidence">
    <summary className="cursor-pointer font-medium">Analyzer visual evidence &amp; selected frames ({scenes.length} scene{scenes.length === 1 ? "" : "s"})</summary>
    <div className="mt-4 space-y-4">{scenes.map((scene) => <details key={String(scene.scene_id)} className="rounded-lg border p-3">
      <summary className="cursor-pointer text-sm font-medium">{String(scene.scene_id)} · {Number(scene.start_time_sec || 0).toFixed(2)}–{Number(scene.end_time_sec || 0).toFixed(2)} sec · {Array.isArray(scene.frames) ? scene.frames.length : 0} selected frames</summary>
      <div className="mt-3 space-y-3">{scene.clip_artifact_path && <video controls preload="metadata" className="max-h-80 w-full rounded-lg bg-black" src={getVideoAudioAnalyzerArtifactUrl(runId, String(scene.clip_artifact_path))} />}
        <div className="grid gap-3 sm:grid-cols-2">{(Array.isArray(scene.frames) ? scene.frames : []).map((frame: Record<string, any>) => <div key={String(frame.frame_id)} className="min-w-0 rounded-lg border p-3">
          {frame.artifact_path && <img className="aspect-video w-full rounded-md bg-secondary object-contain" src={getVideoAudioAnalyzerArtifactUrl(runId, String(frame.artifact_path))} alt={`Analyzer frame ${String(frame.frame_id)}`} />}
          <p className="mt-2 text-xs font-medium">{String(frame.frame_id)} · {Number(frame.timestamp_sec || 0).toFixed(2)} sec · visual change {Number(frame.change_score || 0).toFixed(3)} · camera motion {Number(frame.camera_motion_score || 0).toFixed(3)}</p>
          {!frame.artifact_path && <p className="mt-1 text-xs text-muted-foreground">Timestamp only; the sampled image was intentionally not persisted.</p>}
          <p className="mt-1 text-xs text-muted-foreground">Camera: {String(frame.camera?.framing || "unclassified")} / {String(frame.camera?.motion || "unclassified")} · Lighting: {String(frame.lighting?.brightness_level || "unclassified")}, {String(frame.lighting?.contrast_level || "unclassified")}</p>
          {Array.isArray(frame.uncertainties) && frame.uncertainties.length > 0 && <p className="mt-1 text-xs text-amber-600">Evidence limits: {frame.uncertainties.join("; ")}</p>}
        </div>)}</div>
      </div>
    </details>)}</div>
  </details>;
}

function ResultViewerContent({ job, onSend }: { job: VideoJob; onSend: (references: ManualDirectorReference[]) => void }) {
  type Frame = { frame_id: string; timestamp_sec: number; description?: string; summary?: string; path?: string; frame_card?: Record<string, unknown> };
  type Cut = { cut_id: string; start_time_sec: number; end_time_sec: number; duration_sec: number; boundary_confidence?: string };
  type Scene = { scene_id: string; start_time_sec: number; end_time_sec: number; start_time_hms: string; end_time_hms: string; summary: string; transcript?: string; transcript_segments?: Array<Record<string, any>>; audio_events?: Array<Record<string, any>>; cuts?: Cut[]; clip_path?: string; keyframes?: Frame[]; deltas?: unknown[] };
  type Video = { asset_id?: string; title: string; scenes: Scene[]; summary_model?: string; summary?: { detailed_video_summary?: string; brief_video_summary?: string } };
  const videos = ((job.result?.videos as Video[] | undefined) || []);
  const audioRuns = (job.result?.audio_analysis as Array<Record<string, any>> | undefined) || [];
  const gpuUsage = job.result?.gpu_usage as { available?: boolean; baseline_mib?: number; peak_mib?: number; peak_delta_mib?: number; note?: string } | undefined;
  return <>
    {!terminal.has(job.status) && <Card><CardContent className="space-y-3 py-6">
      <div className="flex justify-between text-sm"><span>{job.message}</span><span>{job.progress}%</span></div>
      <Progress value={job.progress || 0} />
      <ScrollArea className="h-32 rounded-xl border p-3"><div className="space-y-1 font-mono text-xs">{job.events.slice(-30).map((item, index) => <p key={`${item.timestamp}-${index}`}>{item.stage}: {item.message}</p>)}</div></ScrollArea>
    </CardContent></Card>}
    {job.error && <Card className="border-destructive"><CardContent className="py-4 text-sm text-destructive">{job.error.split("\n")[0]}</CardContent></Card>}
    {gpuUsage?.available && <p className="rounded-lg border px-3 py-2 text-xs text-muted-foreground">GPU compute allocations during this job: peak {(Number(gpuUsage.peak_mib || 0) / 1024).toFixed(1)} GiB · baseline {(Number(gpuUsage.baseline_mib || 0) / 1024).toFixed(1)} GiB · estimated increase {(Number(gpuUsage.peak_delta_mib || 0) / 1024).toFixed(1)} GiB. {gpuUsage.note}</p>}
    {videos.map((video) => <Card key={video.asset_id || video.title}>
      <CardHeader><CardTitle>{video.title}</CardTitle><CardDescription>{video.scenes.length} timestamped clips · {String(video.summary_model || "Direct-video summary")}</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {video.summary && <div className="rounded-xl bg-secondary p-4 text-sm"><p className="font-medium">Final summary</p><p className="mt-2 whitespace-pre-wrap text-muted-foreground">{video.summary.detailed_video_summary || video.summary.brief_video_summary}</p></div>}
        {video.scenes.map((scene) => <details key={scene.scene_id} className="rounded-xl border p-4">
          <summary className="cursor-pointer font-medium">{scene.scene_id} · {scene.start_time_hms}–{scene.end_time_hms}</summary>
          <div className="mt-4 space-y-4"><p className="text-sm text-muted-foreground">{scene.summary}</p>
            {scene.clip_path && <video controls className="max-h-[420px] w-full rounded-xl bg-black" src={getVideoArtifactUrl(scene.clip_path)} />}
            {Boolean(scene.cuts?.length) && <div className="rounded-xl border p-3"><p className="text-sm font-medium">Cut-to-cut subdivisions ({scene.cuts?.length})</p><p className="mt-1 text-xs text-muted-foreground">Estimated, timestamped intervals in the original video; no duplicate media or per-cut summaries are created.</p><div className="mt-3 space-y-3">{scene.cuts?.map((cut) => <div key={cut.cut_id} className="flex flex-wrap items-center gap-3 border-t pt-3 first:border-0 first:pt-0"><div className="min-w-40 flex-1"><p className="text-sm">{cut.cut_id}</p><p className="text-xs text-muted-foreground">{cut.start_time_sec.toFixed(2)}–{cut.end_time_sec.toFixed(2)} sec · {cut.duration_sec.toFixed(2)} sec</p></div>{video.asset_id && <video aria-label={`Cut preview ${cut.cut_id}`} className="max-h-36 w-60 rounded-lg bg-black" controls preload="metadata" src={`${getVideoAssetUrl(video.asset_id)}#t=${cut.start_time_sec},${cut.end_time_sec}`} />}<Button size="sm" variant="outline" onClick={() => video.asset_id && onSend([{ slot: "video", asset_id: video.asset_id, filename: `${video.title} · ${cut.cut_id}`, media_type: "video", start_time_sec: cut.start_time_sec, end_time_sec: cut.end_time_sec }])} disabled={!video.asset_id}><Send className="mr-1 h-3.5 w-3.5"/>Stage cut</Button></div>)}</div></div>}
            {Boolean(scene.keyframes?.length) && <div className="grid gap-3 sm:grid-cols-2">{scene.keyframes?.map((frame) => <div key={frame.frame_id} className="rounded-xl border p-3">{frame.path && <img className="aspect-video w-full rounded-lg object-cover" src={getVideoArtifactUrl(frame.path)} alt={frame.frame_id} />}<p className="mt-2 text-xs">{frame.description || frame.summary}</p></div>)}</div>}
            {scene.transcript && <div><p className="text-sm font-medium">Transcript</p><p className="mt-1 text-sm text-muted-foreground">{scene.transcript}</p></div>}
            {Boolean(scene.audio_events?.length) && <div><p className="text-sm font-medium">Audio cues in this clip</p><div className="mt-2 space-y-1">{scene.audio_events?.map((cue, cueIndex) => <p className="text-xs text-muted-foreground" key={String(cue.event_id || cueIndex)}>{Number(cue.start_time_sec || 0).toFixed(2)}–{Number(cue.end_time_sec || 0).toFixed(2)} sec · {String(cue.label || cue.event_type || "Audio event")} · {Math.round(Number(cue.confidence || 0) * 100)}% · {String(cue.source || cue.detector || "detector")}</p>)}</div></div>}
            {Boolean(scene.deltas?.length) && <details><summary className="cursor-pointer text-sm font-medium">Frame deltas ({scene.deltas?.length})</summary><pre className="mt-2 overflow-auto rounded-xl bg-secondary p-3 text-xs">{JSON.stringify(scene.deltas, null, 2)}</pre></details>}
          </div>
        </details>)}
      </CardContent>
    </Card>)}
    {audioRuns.map((run) => {
      const previewMp3 = (run.audio as Record<string, any> | undefined)?.preview_mp3;
      const mediaAssets = (run.media_collection as Record<string, any> | undefined)?.assets;
      return <Card key={`${run.asset_id}-${run.run_id}`} data-testid="audio-analysis-result">
        <CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle>Audio analyzer · {String(run.asset_id || "video")}</CardTitle><CardDescription>{String(run.summary || "Timestamped speech, music, SFX and semantic analysis")}</CardDescription></div><Badge variant={run.status === "completed" ? "default" : run.status === "failed" ? "destructive" : "outline"}>{String(run.status)}</Badge></div></CardHeader>
        <CardContent className="space-y-4">
          {run.run_id && previewMp3 && <audio controls preload="metadata" className="w-full" src={getVideoAudioAnalyzerArtifactUrl(String(run.run_id), String(previewMp3))} />}
          {run.run_id && !previewMp3 && <p className="text-xs text-muted-foreground">MP3 preview extraction was disabled for this run.</p>}
          {run.status === "failed" && <pre className="overflow-auto whitespace-pre-wrap rounded-lg bg-destructive/5 p-3 text-xs text-destructive">{String(run.reason || "Analyzer failed; see job log for details")}{run.log_tail ? `\n${String(run.log_tail)}` : ""}</pre>}
          {run.status === "completed" && <>
            <div className="flex flex-wrap gap-2 text-xs"><Badge variant="secondary">{Array.isArray(run.audio_events) ? run.audio_events.length : 0} timestamped events</Badge><Badge variant="secondary">Transcript: {String((run.transcript as Record<string, unknown> | undefined)?.status || "unavailable")}</Badge><Badge variant="secondary">Diarization: {String((run.diarization as Record<string, unknown> | undefined)?.status || "unavailable")}</Badge><Badge variant="outline">PE-AV: {String(((run.statuses as Record<string, unknown> | undefined)?.pe_av_embeddings) || "unavailable")}</Badge></div>
            {Array.isArray(run.scenes) && <AnalyzerVisualEvidence runId={String(run.run_id)} scenes={run.scenes as Array<Record<string, any>>} />}
            {Array.isArray(run.audio_events) && run.audio_events.length > 0 && <div className="max-h-72 space-y-2 overflow-auto rounded-xl border p-3">{(run.audio_events as Array<Record<string, unknown>>).map((item) => { const mood = item.semantic_mood as Record<string, any> | undefined; return <div key={String(item.event_id)} className="flex flex-wrap items-start justify-between gap-3 border-b pb-2 last:border-b-0"><div><p className="text-sm font-medium">{String(item.label || item.event_type || "Audio event")}</p><p className="text-xs text-muted-foreground">{Number(item.start_time_sec || 0).toFixed(2)}–{Number(item.end_time_sec || 0).toFixed(2)} sec · {String(item.detector || "event detector")}</p>{mood?.top_match && <p className="mt-1 text-xs text-muted-foreground">Estimated music mood: {String(mood.top_match)} · relative PE-AV similarity, not a calibrated probability</p>}</div><Badge variant="outline">{Math.round(Number(item.confidence || 0) * 100)}%</Badge></div>; })}</div>}
            {Array.isArray(mediaAssets) && mediaAssets.map((asset: Record<string, any>) => asset.relative_path ? <div key={String(asset.asset_id)} className="flex flex-wrap items-center gap-3 rounded-xl border p-3 text-sm"><Badge variant="secondary">{String(asset.category)}</Badge><span className="min-w-0 flex-1 truncate">{String(asset.label || asset.asset_id)}</span><audio controls preload="none" className="max-w-xs" src={getVideoAudioAnalyzerArtifactUrl(String(run.run_id), String(asset.relative_path))} /></div> : null)}
          </>}
        </CardContent>
      </Card>;
    })}
  </>;
}
