import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleDashed, Cpu, Database, FileCog, Loader2, Mic2, Play, RefreshCw, Scissors, Server, SlidersHorizontal, Workflow } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  addReferenceVoice,
  createF5PrepareJob,
  createAudioEffectJob,
  createTimedTTSJob,
  createSceneSplit,
  createSceneStitch,
  CURRENT_PROJECT_KEY,
  fetchAudioCapabilities,
  getF5Preflight,
  getF5PrepareJob,
  getAudioEffectJob,
  getCharacterMap,
  getProjectFileUrl,
  getTimedTTSJob,
  getSceneJob,
  listAudioModels,
  listAudioVoices,
  listTimedTTSJobs,
  listAudioEffectJobs,
  listRVCModels,
  listSceneJobs,
  refreshAudioVoices,
  saveCharacterMap,
  type CharacterAssignment,
  type AudioCapabilities,
  type AudioModel,
  type AudioVoice,
  type TimedTTSJob,
  type TimedTTSSettings,
  type AudioSceneJob,
  type F5Preflight,
  type F5PrepareJob,
  type VoiceRefreshResult,
  type AudioEffectJob,
  type AudioEffectOperation,
  type RVCCatalogModel,
} from "@/lib/project-api";

export default function AudioStudio() {
  const [capabilities, setCapabilities] = useState<AudioCapabilities | null>(null);
  const [voices, setVoices] = useState<AudioVoice[]>([]);
  const [models, setModels] = useState<AudioModel[]>([]);
  const [characters, setCharacters] = useState<CharacterAssignment[]>([]);
  const [voiceName, setVoiceName] = useState("");
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [voiceFile, setVoiceFile] = useState<File | null>(null);
  const [voiceSearch, setVoiceSearch] = useState("");
  const [modelSearch, setModelSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [voiceRefresh, setVoiceRefresh] = useState<VoiceRefreshResult | null>(null);
  const projectId = localStorage.getItem(CURRENT_PROJECT_KEY);

  useEffect(() => {
    Promise.all([fetchAudioCapabilities(), listAudioVoices(), listAudioModels()])
      .then(([nextCapabilities, nextVoices, nextModels]) => {
        setCapabilities(nextCapabilities);
        setVoices(nextVoices);
        setModels(nextModels);
      })
      .catch((error) => toast.error(error.message || "Failed to load Audio Studio"));
    if (projectId) {
      getCharacterMap(projectId).then((value) => setCharacters(value.characters)).catch(() => undefined);
    }
  }, [projectId]);

  const families = useMemo(() => new Set(models.map((model) => model.family)).size, [models]);
  const discoverableVoices = voices.filter((voice) => voice.discoverable);
  const filteredVoices = useMemo(() => {
    const query = voiceSearch.trim().toLocaleLowerCase();
    if (!query) return voices;
    return voices.filter((voice) =>
      [voice.name, voice.source, voice.relative_path].some((value) => value.toLocaleLowerCase().includes(query)),
    );
  }, [voiceSearch, voices]);
  const filteredModels = useMemo(() => {
    const query = modelSearch.trim().toLocaleLowerCase();
    if (!query) return models;
    return models.filter((model) =>
      [model.name, model.family, model.finetune_status].some((value) => value.toLocaleLowerCase().includes(query)),
    );
  }, [modelSearch, models]);

  const uploadVoice = async () => {
    if (!voiceFile) return toast.error("Choose a reference audio file.");
    setBusy(true);
    try {
      const installed = await addReferenceVoice({ name: voiceName, transcript: voiceTranscript, file: voiceFile });
      if (installed.live_discovery?.refreshed) setVoiceRefresh(installed.live_discovery);
      setVoices(await listAudioVoices());
      setVoiceName(""); setVoiceTranscript(""); setVoiceFile(null);
      if (installed.restart_required) toast.warning("Voice installed, but ComfyUI needs a restart to discover it.");
      else toast.success("Reference voice installed and discovered live by ComfyUI.");
    } catch (error: unknown) { toast.error(error instanceof Error ? error.message : "Failed to add voice"); }
    finally { setBusy(false); }
  };

  const refreshVoices = async () => {
    setBusy(true);
    try {
      const result = await refreshAudioVoices();
      setVoiceRefresh(result);
      setVoices(await listAudioVoices());
      toast.success(`ComfyUI sees ${result.live_count} reference voices.`);
    } catch (error: unknown) { toast.error(error instanceof Error ? error.message : "Voice refresh failed"); }
    finally { setBusy(false); }
  };

  const persistCharacterMap = async () => {
    if (!projectId) return toast.error("Create or select a Story Builder project first.");
    setBusy(true);
    try { setCharacters((await saveCharacterMap(projectId, characters)).characters); toast.success("Character map saved."); }
    catch (error: unknown) { toast.error(error instanceof Error ? error.message : "Failed to save character map"); }
    finally { setBusy(false); }
  };

  return (
    <AppShell>
      <section className="flex flex-col gap-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div className="space-y-2">
            <Badge variant="outline" className="w-fit">Phased audio implementation</Badge>
            <h2 className="text-3xl font-semibold tracking-tight">Audio Studio</h2>
            <p className="max-w-3xl text-sm text-muted-foreground">
              Build voice and audio processes from tested blocks. Available blocks are runnable; later phases remain visible but disabled.
            </p>
          </div>
          <Badge variant={capabilities?.comfyui_online ? "default" : "destructive"} className="w-fit">
            {capabilities?.comfyui_online ? "ComfyUI online" : "ComfyUI offline"}
          </Badge>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <SummaryCard icon={Server} label="ComfyUI" value={capabilities?.comfyui_url || "Loading…"} detail={capabilities?.comfyui_online ? "API reachable" : "Start ComfyUI to run workflows"} />
          <SummaryCard icon={Mic2} label="Reference voices" value={String(discoverableVoices.length)} detail={`${voices.length} audio files scanned`} />
          <SummaryCard icon={Cpu} label="TTS models" value={String(models.length)} detail={`${families} discovered families · ${capabilities?.architecture.machine || "unknown"}`} />
        </div>

        <div className="order-4 space-y-6">
          <TimedTTSPanel projectId={projectId} characters={characters} comfyuiOnline={Boolean(capabilities?.comfyui_online)} />
          <F5PreparationPanel projectId={projectId} />
          <AudioEffectsPanel projectId={projectId} voices={discoverableVoices} />
          <SceneSurgeryPanel projectId={projectId} />
        </div>

        <div className="order-3 grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
          <details className="group h-fit rounded-3xl border border-border bg-card text-card-foreground shadow-sm">
            <summary className="cursor-pointer list-none p-6"><div className="flex items-center justify-between gap-3"><div><h3 className="flex items-center gap-2 text-2xl font-semibold leading-none tracking-tight"><Workflow className="h-5 w-5" /> Block library</h3><p className="mt-2 text-sm text-muted-foreground">Open to inspect available speech blocks.</p></div><Badge variant="secondary">{(capabilities?.blocks || []).filter((block) => block.status === "available").length} available</Badge></div></summary>
            <div className="space-y-3 border-t p-6">
              {(capabilities?.blocks || []).map((block) => {
                const ready = block.status === "available";
                return (
                  <div key={block.id} className={`rounded-2xl border p-4 ${ready ? "border-primary/40 bg-primary/5" : "border-border opacity-65"}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex gap-3">
                        {ready ? <CheckCircle2 className="mt-0.5 h-5 w-5 text-primary" /> : <CircleDashed className="mt-0.5 h-5 w-5 text-muted-foreground" />}
                        <div>
                          <p className="font-medium">{block.label}</p>
                          <p className="text-xs text-muted-foreground">{block.executor} executor</p>
                        </div>
                      </div>
                      <Badge variant={ready ? "default" : "secondary"}>Phase {block.phase} · {block.status}</Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          </details>

          <Card className="rounded-3xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Database className="h-5 w-5" /> Catalogs</CardTitle>
              <CardDescription>Read-only discovery from the active ComfyUI installation.</CardDescription>
            </CardHeader>
            <CardContent>
              <Tabs defaultValue="voices">
                <TabsList>
                  <TabsTrigger value="voices">Voices</TabsTrigger>
                  <TabsTrigger value="models">Models</TabsTrigger>
                  <TabsTrigger value="system">System</TabsTrigger>
                </TabsList>
                <TabsContent value="voices" className="mt-4 space-y-3">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <Label htmlFor="voice-catalog-search" className="shrink-0">Voice catalog ({filteredVoices.length} of {voices.length})</Label>
                    <Input id="voice-catalog-search" className="sm:max-w-xs" value={voiceSearch} onChange={(event) => setVoiceSearch(event.target.value)} placeholder="Search voices…" />
                  </div>
                  <div className="max-h-[32rem] space-y-3 overflow-y-auto pr-2" role="region" aria-label="Voice catalog results" tabIndex={0}>
                  {filteredVoices.map((voice) => (
                    <div key={voice.id} className="min-w-0 rounded-2xl border border-border p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="min-w-0 truncate font-medium" title={voice.name}>{voice.name}</p>
                        <div className="flex gap-2">
                          <Badge variant="outline">{voice.source}</Badge>
                          <Badge variant={voice.has_transcript ? "default" : "destructive"}>{voice.has_transcript ? "Transcript ready" : "Missing transcript"}</Badge>
                        </div>
                      </div>
                      <p className="mt-2 break-all text-xs text-muted-foreground">{voice.relative_path}</p>
                    </div>
                  ))}
                  {!filteredVoices.length ? <p className="rounded-2xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">No voices match this search.</p> : null}
                  </div>
                </TabsContent>
                <TabsContent value="models" className="mt-4 space-y-3">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <Label htmlFor="model-catalog-search" className="shrink-0">Model catalog ({filteredModels.length} of {models.length})</Label>
                    <Input id="model-catalog-search" className="sm:max-w-xs" value={modelSearch} onChange={(event) => setModelSearch(event.target.value)} placeholder="Search models…" />
                  </div>
                  <div className="max-h-[32rem] space-y-3 overflow-y-auto pr-2" role="region" aria-label="Model catalog results" tabIndex={0}>
                  {filteredModels.map((model) => (
                    <div key={model.id} className="min-w-0 rounded-2xl border border-border p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="min-w-0"><p className="truncate font-medium" title={model.name}>{model.name}</p><p className="truncate text-xs text-muted-foreground" title={model.family}>{model.family}</p></div>
                        <Badge variant="secondary">Fine-tuning {model.finetune_status}</Badge>
                      </div>
                    </div>
                  ))}
                  {!filteredModels.length ? <p className="rounded-2xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">No models match this search.</p> : null}
                  </div>
                </TabsContent>
                <TabsContent value="system" className="mt-4 space-y-3 text-sm">
                  <SystemRow label="Architecture" value={capabilities?.architecture.machine || "unknown"} />
                  <SystemRow label="AArch64" value={capabilities?.architecture.is_aarch64 ? "Yes — training audit required" : "No"} />
                  <SystemRow label="ComfyUI root" value={capabilities?.comfyui_root || "unknown"} />
                  <SystemRow label="TTS-Audio-Suite" value={capabilities?.tts_suite_root || "unknown"} />
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </div>

        <div className="order-2 grid gap-6 xl:grid-cols-2">
          <Card className="rounded-3xl">
            <CardHeader><CardTitle>Add reference voice</CardTitle><CardDescription>Installs one audio file and its exact transcript into ComfyUI's user voice library.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2"><Label>Voice name</Label><Input value={voiceName} onChange={(event) => setVoiceName(event.target.value)} placeholder="Alice warm" /></div>
              <div className="space-y-2"><Label>Reference audio</Label><Input type="file" accept="audio/*" onChange={(event) => setVoiceFile(event.target.files?.[0] || null)} /></div>
              <div className="space-y-2"><Label>Exact transcript</Label><Textarea value={voiceTranscript} onChange={(event) => setVoiceTranscript(event.target.value)} placeholder="Enter exactly what is spoken in the reference audio." /></div>
              <div className="flex flex-wrap items-center gap-3"><Button disabled={busy || !voiceName.trim() || !voiceTranscript.trim() || !voiceFile} onClick={uploadVoice}>Install reference voice</Button><Button variant="outline" disabled={busy || !capabilities?.comfyui_online} onClick={refreshVoices}>{busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}Refresh live discovery</Button></div>
              {voiceRefresh ? <p className={`rounded-2xl border p-3 text-sm ${voiceRefresh.restart_required ? "border-destructive/40 text-destructive" : "border-primary/30 text-muted-foreground"}`}>{voiceRefresh.restart_required ? "ComfyUI did not discover the expected voice; restart is required." : `Live discovery refreshed: ${voiceRefresh.live_count} voices available in ComfyUI.`}</p> : null}
            </CardContent>
          </Card>

          <Card className="rounded-3xl">
            <CardHeader><CardTitle>Project character map</CardTitle><CardDescription>Assign one discovered one-shot reference voice to each character.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              {characters.map((character, index) => (
                <div key={index} className="space-y-3 rounded-2xl border border-border p-4">
                  <div className="grid gap-3 sm:grid-cols-[minmax(11rem,1fr)_minmax(9rem,0.65fr)]">
                    <div className="min-w-0 space-y-2">
                      <Label htmlFor={`character-name-${index}`}>Character name</Label>
                      <Input id={`character-name-${index}`} value={character.name} placeholder="e.g. Narrator" onChange={(event) => setCharacters((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))} />
                    </div>
                    <div className="min-w-0 space-y-2">
                      <Label htmlFor={`character-language-${index}`}>Language</Label>
                      <Input id={`character-language-${index}`} value={character.language} placeholder="e.g. en" onChange={(event) => setCharacters((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, language: event.target.value } : item))} />
                    </div>
                  </div>
                  <div className="flex items-end gap-3">
                    <div className="min-w-0 flex-1 space-y-2">
                      <Label htmlFor={`character-voice-${index}`}>Reference voice</Label>
                      <select id={`character-voice-${index}`} title={discoverableVoices.find((voice) => voice.id === character.reference_voice_id)?.name || "Select reference voice"} className="h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 py-2 text-sm" value={character.reference_voice_id} onChange={(event) => setCharacters((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, reference_voice_id: event.target.value } : item))}>
                        <option value="">Select voice</option>{discoverableVoices.map((voice) => <option key={voice.id} value={voice.id}>{voice.name} ({voice.source})</option>)}
                      </select>
                    </div>
                    <Button className="shrink-0" variant="outline" onClick={() => setCharacters((items) => items.filter((_, itemIndex) => itemIndex !== index))}>Remove</Button>
                  </div>
                </div>
              ))}
              <div className="flex gap-3"><Button variant="outline" disabled={!discoverableVoices.length} onClick={() => setCharacters((items) => [...items, { name: "", language: "en", reference_voice_id: discoverableVoices[0]?.id || "" }])}>Add character</Button><Button disabled={busy || !projectId} onClick={persistCharacterMap}>Save map</Button></div>
              {!projectId ? <p className="text-xs text-muted-foreground">Create or select a project in Story Builder to save a character map.</p> : null}
            </CardContent>
          </Card>
        </div>
      </section>
    </AppShell>
  );
}

function SummaryCard({ icon: Icon, label, value, detail }: { icon: typeof Server; label: string; value: string; detail: string }) {
  return <Card className="rounded-3xl"><CardContent className="flex items-start gap-4 pt-6"><Icon className="h-5 w-5 text-primary" /><div className="min-w-0"><p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p><p className="mt-1 truncate text-lg font-semibold">{value}</p><p className="text-xs text-muted-foreground">{detail}</p></div></CardContent></Card>;
}

function SystemRow({ label, value }: { label: string; value: string }) {
  return <div className="rounded-2xl border border-border p-4"><p className="font-medium">{label}</p><p className="mt-1 break-all text-xs text-muted-foreground">{value}</p></div>;
}

const DEFAULT_SRT = `1
00:00:00,000 --> 00:00:04,000
[Narrator] Welcome to the story.

2
00:00:04,500 --> 00:00:08,000
[Alice] Hello!`;

const DEFAULT_TTS_SETTINGS: TimedTTSSettings = {
  srt_content: DEFAULT_SRT,
  language: "English",
  seed: 1,
  timing_mode: "smart_natural",
  exaggeration: 0.5,
  temperature: 0.8,
  cfg_weight: 0.5,
  enable_audio_cache: true,
  fade: 0.01,
  max_stretch_ratio: 1,
  min_stretch_ratio: 0.5,
  timing_tolerance: 2,
  batch_size: 0,
};

function TimedTTSPanel({ projectId, characters, comfyuiOnline }: { projectId: string | null; characters: CharacterAssignment[]; comfyuiOnline: boolean }) {
  const [settings, setSettings] = useState<TimedTTSSettings>(DEFAULT_TTS_SETTINGS);
  const [job, setJob] = useState<TimedTTSJob | null>(null);
  const running = job?.status === "queued" || job?.status === "running";

  useEffect(() => {
    if (!projectId || !job || !running) return;
    const timer = window.setTimeout(() => {
      getTimedTTSJob(projectId, job.job_id)
        .then(setJob)
        .catch((error) => toast.error(error.message || "Failed to refresh timed TTS job"));
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [job, projectId, running]);

  const updateNumber = (key: keyof TimedTTSSettings, value: string) => {
    setSettings((current) => ({ ...current, [key]: Number(value) }));
  };

  const submit = async () => {
    if (!projectId) return toast.error("Create or select a Story Builder project first.");
    try {
      setJob(await createTimedTTSJob(projectId, settings));
      toast.success("Timed TTS job queued.");
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : "Failed to queue timed TTS");
    }
  };

  const audioOutput = job?.outputs.find((output) => output.kind === "audio");
  return (
    <Card className="rounded-3xl border-primary/30">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><CardTitle className="flex items-center gap-2"><Play className="h-5 w-5" /> Timed multi-character TTS</CardTitle><CardDescription className="mt-2">Phase 2 · one shared ChatterBox model with project-mapped reference voices.</CardDescription></div>
          <Badge variant={comfyuiOnline ? "default" : "secondary"}>{comfyuiOnline ? "Ready for live test" : "ComfyUI required"}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-5 lg:grid-cols-[1.4fr_0.6fr]">
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3"><Label htmlFor="timed-tts-srt">Timed dialogue (SRT)</Label><Input className="h-auto max-w-52 py-1 text-xs" type="file" accept=".srt,text/plain" aria-label="Import SRT file" onChange={(event) => { const file = event.target.files?.[0]; if (file) file.text().then((value) => setSettings((current) => ({ ...current, srt_content: value }))); }} /></div>
            <Textarea id="timed-tts-srt" className="min-h-64 font-mono text-xs" value={settings.srt_content} onChange={(event) => setSettings((current) => ({ ...current, srt_content: event.target.value }))} />
          </div>
          <div className="space-y-4">
            <div className="space-y-2"><Label htmlFor="tts-language">Shared base language model</Label><select id="tts-language" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={settings.language} onChange={(event) => setSettings((current) => ({ ...current, language: event.target.value }))}>{["English", "German", "French", "Norwegian", "Russian", "Armenian", "Georgian", "Japanese", "Korean", "Italian"].map((language) => <option key={language}>{language}</option>)}</select></div>
            <div className="space-y-2"><Label htmlFor="tts-timing">Timing mode</Label><select id="tts-timing" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={settings.timing_mode} onChange={(event) => setSettings((current) => ({ ...current, timing_mode: event.target.value as TimedTTSSettings["timing_mode"] }))}><option value="smart_natural">Smart natural</option><option value="stretch_to_fit">Stretch to fit</option><option value="pad_with_silence">Pad with silence</option><option value="concatenate">Concatenate</option></select></div>
            <div className="space-y-2"><Label htmlFor="tts-seed">Seed</Label><Input id="tts-seed" type="number" min={0} value={settings.seed} onChange={(event) => updateNumber("seed", event.target.value)} /></div>
            <div className="rounded-2xl border border-border p-3 text-xs text-muted-foreground"><p className="font-medium text-foreground">Character map</p>{characters.length ? characters.map((character) => <p className="mt-1 truncate" key={character.name}>{character.name} · {character.language}</p>) : <p className="mt-1">Save a character map below before running.</p>}</div>
          </div>
        </div>
        <details className="rounded-2xl border border-border p-4"><summary className="cursor-pointer text-sm font-medium">Advanced ChatterBox and timing settings</summary><div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <NumberField id="tts-exaggeration" label="Exaggeration" value={settings.exaggeration} min={0.25} max={2} step={0.05} onChange={(value) => updateNumber("exaggeration", value)} />
          <NumberField id="tts-temperature" label="Temperature" value={settings.temperature} min={0.05} max={5} step={0.05} onChange={(value) => updateNumber("temperature", value)} />
          <NumberField id="tts-cfg" label="CFG weight" value={settings.cfg_weight} min={0} max={1} step={0.05} onChange={(value) => updateNumber("cfg_weight", value)} />
          <NumberField id="tts-tolerance" label="Timing tolerance" value={settings.timing_tolerance} min={0.5} max={10} step={0.5} onChange={(value) => updateNumber("timing_tolerance", value)} />
          <NumberField id="tts-min-stretch" label="Min stretch ratio" value={settings.min_stretch_ratio} min={0.1} max={2} step={0.1} onChange={(value) => updateNumber("min_stretch_ratio", value)} />
          <NumberField id="tts-max-stretch" label="Max stretch ratio" value={settings.max_stretch_ratio} min={0.5} max={5} step={0.1} onChange={(value) => updateNumber("max_stretch_ratio", value)} />
          <NumberField id="tts-fade" label="Crossfade seconds" value={settings.fade} min={0} max={0.1} step={0.001} onChange={(value) => updateNumber("fade", value)} />
          <NumberField id="tts-batch" label="Batch size" value={settings.batch_size} min={0} max={32} step={1} onChange={(value) => updateNumber("batch_size", value)} />
        </div></details>
        <div className="flex flex-wrap items-center gap-3"><Button disabled={!projectId || !characters.length || !comfyuiOnline || running || !settings.srt_content.trim()} onClick={submit}>{running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}{running ? "Generating…" : "Run timed TTS"}</Button>{job ? <Badge variant={job.status === "failed" ? "destructive" : job.status === "completed" ? "default" : "secondary"}>{job.status}</Badge> : null}<span className="text-xs text-muted-foreground">{!projectId ? "Select a project." : !comfyuiOnline ? "Start ComfyUI on port 3008." : ""}</span></div>
        {job?.error ? <p className="rounded-2xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">{job.error}</p> : null}
        {projectId && audioOutput ? <div className="space-y-3 rounded-2xl border border-primary/30 bg-primary/5 p-4"><p className="font-medium">Generated audio</p><audio className="w-full" controls src={getProjectFileUrl(projectId, audioOutput.relative_path)} /><div className="flex flex-wrap gap-3"><Button asChild variant="outline" size="sm"><a href={getProjectFileUrl(projectId, audioOutput.relative_path)} download>Download FLAC</a></Button>{Object.entries(job?.reports || {}).map(([name, path]) => <Button asChild key={name} variant="ghost" size="sm"><a href={getProjectFileUrl(projectId, path)} download>{name}</a></Button>)}</div></div> : null}
      </CardContent>
    </Card>
  );
}

function NumberField({ id, label, value, min, max, step, onChange }: { id: string; label: string; value: number; min: number; max: number; step: number; onChange: (value: string) => void }) {
  return <div className="space-y-2"><Label htmlFor={id}>{label}</Label><Input id={id} type="number" value={value} min={min} max={max} step={step} onChange={(event) => onChange(event.target.value)} /></div>;
}

function F5PreparationPanel({ projectId }: { projectId: string | null }) {
  const [preflight, setPreflight] = useState<F5Preflight | null>(null);
  const [datasetName, setDatasetName] = useState("");
  const [baseModel, setBaseModel] = useState("F5TTS_v1_Base");
  const [metadata, setMetadata] = useState<File | null>(null);
  const [audioFiles, setAudioFiles] = useState<File[]>([]);
  const [job, setJob] = useState<F5PrepareJob | null>(null);
  const running = job?.status === "queued" || job?.status === "running";

  useEffect(() => {
    getF5Preflight().then((value) => {
      setPreflight(value);
      if (value.supported_models.length) setBaseModel(value.supported_models[0]);
    }).catch((error) => toast.error(error.message || "F5 preflight failed"));
  }, []);

  useEffect(() => {
    if (!projectId || !job || !running) return;
    const timer = window.setTimeout(() => getF5PrepareJob(projectId, job.job_id).then(setJob).catch((error) => toast.error(error.message)), 1500);
    return () => window.clearTimeout(timer);
  }, [job, projectId, running]);

  const submit = async () => {
    if (!projectId || !metadata || !audioFiles.length) return;
    try {
      setJob(await createF5PrepareJob(projectId, { datasetName, baseModel, metadata, audioFiles }));
      toast.success("F5 dataset validation and preparation queued.");
    } catch (error: unknown) { toast.error(error instanceof Error ? error.message : "F5 preparation failed"); }
  };

  const failedChecks = preflight?.checks.filter((check) => !check.ok) || [];
  return <Card className="rounded-3xl border-primary/20">
    <CardHeader>
      <div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle className="flex items-center gap-2"><FileCog className="h-5 w-5" /> F5-TTS dataset preparation</CardTitle><CardDescription className="mt-2">Phase 4 · validate and prepare a consented dataset. Training remains disabled until separately approved.</CardDescription></div><Badge variant={preflight?.preparation_ready ? "default" : "destructive"}>{preflight?.preparation_ready ? "Preparation ready" : "Preflight blocked"}</Badge></div>
    </CardHeader>
    <CardContent className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2"><Label htmlFor="f5-dataset-name">Dataset name</Label><Input id="f5-dataset-name" value={datasetName} onChange={(event) => setDatasetName(event.target.value)} placeholder="alice_voice_v1" /></div>
        <div className="space-y-2"><Label htmlFor="f5-base-model">Base model</Label><select id="f5-base-model" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={baseModel} onChange={(event) => setBaseModel(event.target.value)}>{(preflight?.supported_models || ["F5TTS_v1_Base", "F5TTS_Base", "E2TTS_Base"]).map((model) => <option key={model}>{model}</option>)}</select></div>
        <div className="space-y-2"><Label htmlFor="f5-metadata">metadata.csv</Label><Input id="f5-metadata" type="file" accept=".csv,text/csv" onChange={(event) => setMetadata(event.target.files?.[0] || null)} /><p className="text-xs text-muted-foreground">Required header: audio_file|text</p></div>
        <div className="space-y-2"><Label htmlFor="f5-audio-files">Training audio files</Label><Input id="f5-audio-files" type="file" accept="audio/*" multiple onChange={(event) => setAudioFiles(Array.from(event.target.files || []))} /><p className="text-xs text-muted-foreground">{audioFiles.length} file(s) selected</p></div>
      </div>
      <details className="rounded-2xl border border-border p-4"><summary className="cursor-pointer text-sm font-medium">AArch64 and training preflight</summary><div className="mt-3 space-y-2">{preflight?.checks.map((check) => <div key={check.name} className="flex flex-col gap-1 rounded-xl border border-border p-3 text-xs sm:flex-row sm:justify-between"><span className={check.ok ? "text-primary" : "text-destructive"}>{check.ok ? "Ready" : "Blocked"} · {check.name}</span><span className="break-all text-muted-foreground">{check.detail}</span></div>)}</div></details>
      {failedChecks.length ? <p className="rounded-2xl border border-amber-500/40 bg-amber-500/5 p-4 text-sm text-muted-foreground">Dataset preparation can still run when its required checks pass. Training stays disabled because {failedChecks.length} broader preflight check(s) need attention.</p> : null}
      <div className="flex flex-wrap items-center gap-3"><Button disabled={!projectId || !preflight?.preparation_ready || !datasetName.trim() || !metadata || !audioFiles.length || running} onClick={submit}>{running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileCog className="mr-2 h-4 w-4" />}{running ? "Preparing…" : "Validate and prepare dataset"}</Button><Button disabled title="Training requires explicit approval of the dataset and exact command">Start training (approval required)</Button>{job ? <Badge variant={job.status === "failed" ? "destructive" : job.status === "completed" ? "default" : "secondary"}>{job.status}</Badge> : null}</div>
      {!projectId ? <p className="text-xs text-muted-foreground">Select a Story Builder project before preparing a dataset.</p> : null}
      {job?.error ? <p className="rounded-2xl border border-destructive/40 p-4 text-sm text-destructive">{job.error}</p> : null}
      {job?.validation ? <div className="grid gap-3 sm:grid-cols-3"><SystemRow label="Valid samples" value={String(job.validation.sample_count)} /><SystemRow label="Total duration" value={`${job.validation.total_duration}s`} /><SystemRow label="Sample rates" value={job.validation.sample_rates.join(", ")} /></div> : null}
      {job?.status === "completed" ? <div className="space-y-3 rounded-2xl border border-primary/30 bg-primary/5 p-4"><p className="font-medium">Prepared successfully</p><p className="text-xs text-muted-foreground">raw.arrow, duration.json, and vocab.txt were created inside the project. No training or model download was started.</p>{job.command_preview ? <pre className="overflow-x-auto rounded-xl bg-background p-3 text-xs">{job.command_preview.join(" ")}</pre> : null}{job.command_blockers.map((item) => <p key={item} className="text-xs text-muted-foreground">• {item}</p>)}</div> : null}
    </CardContent>
  </Card>;
}

const EFFECT_LABELS: Record<AudioEffectOperation, string> = {
  noise_cleanup: "Noise Cleanup", voice_repair: "Voice Repair", voice_changer: "Voice Changer",
  rvc: "RVC Voice/Pitch", emotion: "Emotion Change", style: "Style Change",
};

function AudioEffectsPanel({ projectId, voices }: { projectId: string | null; voices: AudioVoice[] }) {
  const [operation, setOperation] = useState<AudioEffectOperation>("voice_repair");
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourcePath, setSourcePath] = useState("");
  const [projectAudio, setProjectAudio] = useState<Array<{ path: string; label: string }>>([]);
  const [rvcModels, setRvcModels] = useState<RVCCatalogModel[]>([]);
  const [job, setJob] = useState<AudioEffectJob | null>(null);
  const [targetVoice, setTargetVoice] = useState(voices[0]?.id || "");
  const [rvcModel, setRvcModel] = useState("");
  const [rvcIndex, setRvcIndex] = useState("");
  const [pitch, setPitch] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [emotion, setEmotion] = useState("happy");
  const [style, setStyle] = useState("whisper");
  const [iterations, setIterations] = useState(1);
  const [refinementPasses, setRefinementPasses] = useState(1);
  const running = job?.status === "queued" || job?.status === "running";

  useEffect(() => { if (!targetVoice && voices.length) setTargetVoice(voices[0].id); }, [targetVoice, voices]);
  useEffect(() => {
    listRVCModels().then((items) => { setRvcModels(items); if (items.length) setRvcModel((value) => value || items[0].id); }).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (!projectId) { setProjectAudio([]); return; }
    Promise.all([listTimedTTSJobs(projectId), listAudioEffectJobs(projectId), listSceneJobs(projectId)]).then(([tts, effects, scenes]) => {
      const options = [
        ...tts.flatMap((item) => item.outputs.filter((output) => output.kind === "audio").map((output) => ({ path: output.relative_path, label: `${item.job_id} · ${output.filename}` }))),
        ...effects.flatMap((item) => item.primary_output ? [{ path: item.primary_output.relative_path, label: `${EFFECT_LABELS[item.operation]} · ${item.job_id}` }] : []),
        ...scenes.flatMap((item) => item.kind === "split" && item.manifest ? item.manifest.clips.map((clip) => ({ path: clip.relative_path, label: `${item.job_id} · clip ${clip.clip_index}` })) : []),
      ];
      setProjectAudio(options);
    }).catch(() => setProjectAudio([]));
  }, [job?.status, projectId]);
  useEffect(() => {
    if (!projectId || !job || !running) return;
    const timer = window.setTimeout(() => getAudioEffectJob(projectId, job.job_id).then(setJob).catch((error) => toast.error(error.message)), 1500);
    return () => window.clearTimeout(timer);
  }, [job, projectId, running]);

  const selectedRVC = rvcModels.find((item) => item.id === rvcModel);
  useEffect(() => { setRvcIndex(rvcModels.find((item) => item.id === rvcModel)?.indexes[0]?.id || ""); }, [rvcModel, rvcModels]);

  const run = async () => {
    if (!projectId) return;
    const settings: Record<string, unknown> = sourceFile ? {} : { source_relative_path: sourcePath };
    if (operation === "noise_cleanup") Object.assign(settings, { model: "UVR/UVR-DeNoise.pth", aggressiveness: 10, use_cache: true });
    if (operation === "voice_repair") Object.assign(settings, { restoration_mode: 0, use_cuda: true });
    if (operation === "voice_changer") Object.assign(settings, { target_voice_id: targetVoice, language: "local:English", refinement_passes: refinementPasses, max_chunk_duration: 30, chunk_method: "smart" });
    if (operation === "rvc") Object.assign(settings, { model: rvcModel, index_file: rvcIndex, pitch, pitch_detection: "rmvpe", index_ratio: .75, consonant_protection: .25, volume_envelope: .25, refinement_passes: refinementPasses, max_chunk_duration: 30, chunk_method: "smart" });
    if (operation === "emotion") Object.assign(settings, { transcript, emotion, iterations });
    if (operation === "style") Object.assign(settings, { transcript, style, iterations });
    try { setJob(await createAudioEffectJob(projectId, operation, settings, sourceFile || undefined)); toast.success(`${EFFECT_LABELS[operation]} queued.`); }
    catch (error: unknown) { toast.error(error instanceof Error ? error.message : "Audio effect failed"); }
  };

  return <Card className="rounded-3xl border-primary/20"><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle className="flex items-center gap-2"><SlidersHorizontal className="h-5 w-5" /> Audio effects</CardTitle><CardDescription className="mt-2">Phases 6–8 · fixed cleanup, repair, voice conversion, emotion, and style workflows.</CardDescription></div><Badge variant="secondary">Independent blocks</Badge></div></CardHeader><CardContent className="space-y-5">
    <div className="grid gap-4 md:grid-cols-3"><div className="space-y-2"><Label htmlFor="effect-operation">Operation</Label><select id="effect-operation" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={operation} onChange={(event) => { setOperation(event.target.value as AudioEffectOperation); setJob(null); }}>{Object.entries(EFFECT_LABELS).filter(([id]) => id !== "noise_cleanup").map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></div><div className="space-y-2"><Label htmlFor="effect-source-file">Upload source</Label><Input id="effect-source-file" type="file" accept="audio/*" onChange={(event) => setSourceFile(event.target.files?.[0] || null)} /></div><div className="space-y-2"><Label htmlFor="effect-source-path">Or project audio/clip</Label><select id="effect-source-path" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={sourcePath} onChange={(event) => { setSourcePath(event.target.value); setSourceFile(null); }}><option value="">Select project audio</option>{projectAudio.map((item) => <option key={item.path} value={item.path}>{item.label}</option>)}</select></div></div>
    {operation === "voice_changer" ? <div className="grid gap-4 md:grid-cols-2"><div className="space-y-2"><Label>Target reference voice</Label><select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={targetVoice} onChange={(event) => setTargetVoice(event.target.value)}>{voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.name}</option>)}</select></div><NumberField id="vc-passes" label="Refinement passes" value={refinementPasses} min={1} max={5} step={1} onChange={(value) => setRefinementPasses(Number(value))} /></div> : null}
    {operation === "rvc" ? <div className="grid gap-4 md:grid-cols-3"><div className="space-y-2"><Label>RVC model</Label><select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={rvcModel} onChange={(event) => setRvcModel(event.target.value)}>{rvcModels.map((model) => <option key={model.id}>{model.id}</option>)}</select></div><div className="space-y-2"><Label>Matching index</Label><select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={rvcIndex} onChange={(event) => setRvcIndex(event.target.value)}><option value="">No index</option>{(selectedRVC?.indexes || []).map((item) => <option key={item.id}>{item.id}</option>)}</select></div><NumberField id="rvc-pitch" label="Pitch semitones" value={pitch} min={-14} max={14} step={1} onChange={(value) => setPitch(Number(value))} /></div> : null}
    {operation === "emotion" || operation === "style" ? <div className="grid gap-4 md:grid-cols-[1fr_14rem_10rem]"><div className="space-y-2"><Label>Exact transcript</Label><Textarea value={transcript} onChange={(event) => setTranscript(event.target.value)} placeholder="Enter exactly what is spoken in this 0.5–30 second clip." /></div><div className="space-y-2"><Label>{operation === "emotion" ? "Emotion" : "Style"}</Label>{operation === "emotion" ? <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={emotion} onChange={(event) => setEmotion(event.target.value)}>{["happy","sad","angry","excited","calm","fearful","surprised","disgusted","remove"].map((item) => <option key={item}>{item}</option>)}</select> : <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={style} onChange={(event) => setStyle(event.target.value)}>{["whisper","serious","warm","authority","radio","story","news","gentle","shout","remove"].map((item) => <option key={item}>{item}</option>)}</select>}</div><NumberField id="edit-iterations" label="Iterations" value={iterations} min={1} max={5} step={1} onChange={(value) => setIterations(Number(value))} /></div> : null}
    <div className="flex flex-wrap items-center gap-3"><Button disabled={!projectId || (!sourceFile && !sourcePath) || running || ((operation === "emotion" || operation === "style") && !transcript.trim()) || (operation === "voice_changer" && !targetVoice) || (operation === "rvc" && !rvcModel)} onClick={run}>{running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}{running ? "Processing…" : `Run ${EFFECT_LABELS[operation]}`}</Button>{job ? <Badge variant={job.status === "failed" ? "destructive" : job.status === "completed" ? "default" : "secondary"}>{job.status}</Badge> : null}</div>
    {job?.error ? <p className="rounded-2xl border border-destructive/40 p-4 text-sm text-destructive">{job.error}</p> : null}
    {projectId && job?.primary_output ? <div className="grid gap-4 rounded-2xl border border-primary/30 bg-primary/5 p-4 md:grid-cols-2"><div><p className="mb-2 text-sm font-medium">Source</p>{sourcePath ? <audio className="w-full" controls src={getProjectFileUrl(projectId, sourcePath)} /> : <p className="text-xs text-muted-foreground">Uploaded source retained with the job.</p>}</div><div><p className="mb-2 text-sm font-medium">Processed output</p><audio className="w-full" controls src={getProjectFileUrl(projectId, job.primary_output.relative_path)} /><Button asChild className="mt-3" size="sm" variant="outline"><a href={getProjectFileUrl(projectId, job.primary_output.relative_path)} download>Download FLAC</a></Button></div></div> : null}
  </CardContent></Card>;
}

type EditRange = { start: number; end: number; text: string; edit_type?: string };

function SceneSurgeryPanel({ projectId }: { projectId: string | null }) {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [sourcePath, setSourcePath] = useState("");
  const [projectAudio, setProjectAudio] = useState<Array<{ path: string; label: string }>>([]);
  const [edits, setEdits] = useState<EditRange[]>([{ start: 0, end: 1, text: "" }]);
  const [splitJob, setSplitJob] = useState<AudioSceneJob | null>(null);
  const [stitchJob, setStitchJob] = useState<AudioSceneJob | null>(null);
  const [mode, setMode] = useState<"simple" | "timed">("simple");
  const [gaps, setGaps] = useState<Record<number, number>>({});
  const [replacements, setReplacements] = useState<Record<number, File>>({});
  const [replacementPaths, setReplacementPaths] = useState<Record<number, string>>({});
  const [effectAudio, setEffectAudio] = useState<Array<{ path: string; label: string }>>([]);
  const active = [splitJob, stitchJob].find((job) => job?.status === "queued" || job?.status === "running");
  useEffect(() => {
    if (!projectId) { setProjectAudio([]); return; }
    Promise.all([listTimedTTSJobs(projectId), listAudioEffectJobs(projectId)]).then(([jobs, effects]) => { setProjectAudio(jobs.flatMap((job) => job.outputs.filter((output) => output.kind === "audio").map((output) => ({ path: output.relative_path, label: `${job.job_id} · ${output.filename}` })))); setEffectAudio(effects.flatMap((job) => job.primary_output ? [{ path: job.primary_output.relative_path, label: `${EFFECT_LABELS[job.operation]} · ${job.job_id}` }] : [])); }).catch(() => { setProjectAudio([]); setEffectAudio([]); });
  }, [projectId]);
  useEffect(() => {
    if (!projectId || !active) return;
    const timer = window.setTimeout(() => getSceneJob(projectId, active.job_id).then((job) => job.kind === "split" ? setSplitJob(job) : setStitchJob(job)).catch((error) => toast.error(error.message)), 1500);
    return () => window.clearTimeout(timer);
  }, [active, projectId]);
  const updateEdit = (index: number, patch: Partial<EditRange>) => setEdits((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  const runSplit = async () => {
    if (!projectId) return toast.error("Select a project first.");
    try { setSplitJob(await createSceneSplit(projectId, { edits, source_relative_path: sourcePath || undefined }, audioFile || undefined)); setStitchJob(null); }
    catch (error: unknown) { toast.error(error instanceof Error ? error.message : "Split failed"); }
  };
  const runStitch = async () => {
    if (!projectId || !splitJob) return;
    const indexes = Object.keys(replacements).map(Number).sort((a, b) => a - b);
    try { setStitchJob(await createSceneStitch(projectId, splitJob.job_id, { mode, gaps, replacement_clip_indexes: indexes, replacement_relative_paths: replacementPaths }, indexes.map((index) => replacements[index]))); }
    catch (error: unknown) { toast.error(error instanceof Error ? error.message : "Stitch failed"); }
  };
  return <Card className="rounded-3xl"><CardHeader><CardTitle className="flex items-center gap-2"><Scissors className="h-5 w-5" /> Split and stitch audio</CardTitle><CardDescription>Phase 5 · split locally, replace selected clips, then reassemble without ComfyUI.</CardDescription></CardHeader><CardContent className="space-y-5">
    <div className="grid gap-4 md:grid-cols-2"><div className="space-y-2"><Label htmlFor="scene-audio">Upload source audio</Label><Input id="scene-audio" type="file" accept="audio/*" onChange={(event) => setAudioFile(event.target.files?.[0] || null)} /></div><div className="space-y-2"><Label htmlFor="scene-path">Or select generated project audio</Label><select id="scene-path" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={sourcePath} onChange={(event) => setSourcePath(event.target.value)}><option value="">Select project audio</option>{projectAudio.map((item) => <option key={item.path} value={item.path}>{item.label}</option>)}</select></div></div>
    <div className="flex items-center justify-between"><Label>Edit ranges</Label><Input className="h-auto max-w-52 py-1 text-xs" type="file" accept=".json,application/json" aria-label="Import edit JSON" onChange={(event) => { const file = event.target.files?.[0]; if (file) file.text().then((text) => { const value = JSON.parse(text); setEdits(Array.isArray(value) ? value : value.edits); }).catch(() => toast.error("Invalid edit JSON")); }} /></div>
    <div className="space-y-3">{edits.map((edit, index) => <div key={index} className="grid gap-3 rounded-2xl border border-border p-3 md:grid-cols-[8rem_8rem_1fr_auto]"><div><Label>Start</Label><Input type="number" min={0} step="0.01" value={edit.start} onChange={(event) => updateEdit(index, { start: Number(event.target.value) })} /></div><div><Label>End</Label><Input type="number" min={0} step="0.01" value={edit.end} onChange={(event) => updateEdit(index, { end: Number(event.target.value) })} /></div><div><Label>Text</Label><Input value={edit.text} onChange={(event) => updateEdit(index, { text: event.target.value })} /></div><Button className="self-end" variant="outline" onClick={() => setEdits((items) => items.filter((_, itemIndex) => itemIndex !== index))}>Remove</Button></div>)}</div>
    <div className="flex gap-3"><Button variant="outline" onClick={() => setEdits((items) => [...items, { start: 0, end: 1, text: "" }])}>Add range</Button><Button disabled={!projectId || (!audioFile && !sourcePath) || !edits.length || Boolean(active)} onClick={runSplit}>{active?.kind === "split" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Split audio</Button>{splitJob ? <Badge variant={splitJob.status === "failed" ? "destructive" : "secondary"}>{splitJob.status}</Badge> : null}</div>
    {splitJob?.error ? <p className="text-sm text-destructive">{splitJob.error}</p> : null}
    {projectId && splitJob?.manifest ? <div className="space-y-3"><h3 className="font-medium">Generated clips</h3>{splitJob.manifest.clips.map((clip) => <div key={clip.clip_index} className="grid gap-3 rounded-2xl border border-border p-3 lg:grid-cols-[5rem_1fr_1fr_14rem]"><div><p className="font-medium">#{clip.clip_index}</p><Badge variant="outline">{clip.kind}</Badge></div><div><p className="text-sm">{clip.start}s–{clip.end}s · {clip.duration}s</p><p className="truncate text-xs text-muted-foreground">{clip.text || "Untouched audio"}</p></div><audio className="w-full" controls src={getProjectFileUrl(projectId, clip.relative_path)} /><div className="space-y-2"><Label>Replacement upload</Label><Input type="file" accept="audio/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) { setReplacements((current) => ({ ...current, [clip.clip_index]: file })); setReplacementPaths((current) => { const next = { ...current }; delete next[clip.clip_index]; return next; }); } }} /><Label>Or effect output</Label><select className="h-9 w-full rounded-md border border-input bg-background px-2 text-xs" value={replacementPaths[clip.clip_index] || ""} onChange={(event) => { const value = event.target.value; setReplacementPaths((current) => { const next = { ...current }; if (value) next[clip.clip_index] = value; else delete next[clip.clip_index]; return next; }); if (value) setReplacements((current) => { const next = { ...current }; delete next[clip.clip_index]; return next; }); }}><option value="">No project replacement</option>{effectAudio.map((item) => <option key={item.path} value={item.path}>{item.label}</option>)}</select>{mode === "timed" ? <Input aria-label={`Gap after clip ${clip.clip_index}`} type="number" min={0} step="0.1" value={gaps[clip.clip_index] || 0} onChange={(event) => setGaps((current) => ({ ...current, [clip.clip_index]: Number(event.target.value) }))} /> : null}</div></div>)}
      <div className="flex flex-wrap items-center gap-3"><select className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={mode} onChange={(event) => setMode(event.target.value as "simple" | "timed")}><option value="simple">Simple stitch</option><option value="timed">Timed stitch</option></select><Button disabled={Boolean(active)} onClick={runStitch}>Stitch clips</Button>{stitchJob ? <Badge variant={stitchJob.status === "failed" ? "destructive" : "secondary"}>{stitchJob.status}</Badge> : null}</div>
    </div> : null}
    {projectId && stitchJob?.output_path ? <div className="rounded-2xl border border-primary/30 bg-primary/5 p-4"><p className="mb-3 font-medium">Final stitched WAV</p><audio className="w-full" controls src={getProjectFileUrl(projectId, stitchJob.output_path)} /><Button asChild className="mt-3" variant="outline"><a href={getProjectFileUrl(projectId, stitchJob.output_path)} download>Download WAV</a></Button></div> : null}
  </CardContent></Card>;
}
