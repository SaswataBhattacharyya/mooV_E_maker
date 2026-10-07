/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, History, Search, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { CURRENT_PROJECT_KEY, createCanvasAnalysis, createCanvasOutline, createCanvasRevision, createProject, fetchProject, listCanvasRevisions, type ProjectState, type StoryRevision } from "@/lib/project-api";

export default function StoryCanvas() {
  const [project, setProject] = useState<ProjectState | null>(null);
  const [title, setTitle] = useState("");
  const [novel, setNovel] = useState("");
  const [narrator, setNarrator] = useState(false);
  const [revisions, setRevisions] = useState<StoryRevision[]>([]);
  const [analysis, setAnalysis] = useState<StoryRevision | null>(null);
  const [screenplay, setScreenplay] = useState<StoryRevision | null>(null);
  const [selection, setSelection] = useState("");
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const id = localStorage.getItem(CURRENT_PROJECT_KEY);
    if (!id) return;
    fetchProject(id).then((loaded) => { setProject(loaded); setTitle(loaded.title); setNovel(loaded.story_input); return listCanvasRevisions(id); }).then(setRevisions).catch(() => undefined);
  }, []);
  const currentRevision = revisions[0];
  const screenplayScenes = useMemo(() => (Array.isArray(screenplay?.content?.scenes) ? screenplay.content.scenes : []) as Array<{ scene_id: string; scene_number?: number; slugline?: string; summary?: string; characters_present?: string[]; estimated_seconds?: number }>, [screenplay]);
  const run = async (key: string, action: () => Promise<void>) => { setBusy(key); try { await action(); } catch (error: unknown) { toast.error(error instanceof Error ? error.message : "Operation failed"); } finally { setBusy(null); } };
  const saveRevision = () => run("save", async () => {
    const nextProject = project || await createProject({ title: title.trim() || "Untitled Story", story_input: novel, automation_mode: false });
    setProject(nextProject); localStorage.setItem(CURRENT_PROJECT_KEY, nextProject.id);
    const revision = await createCanvasRevision(nextProject.id, { content: novel, parent_revision_id: currentRevision?.revision_id, narrator });
    setRevisions([revision, ...revisions]); toast.success("Novel revision saved.");
  });
  const analyzeStory = () => run("analysis", async () => {
    if (!project && !novel.trim()) throw new Error("Write the novel first.");
    const active = project || await createProject({ title: title.trim() || "Untitled Story", story_input: novel, automation_mode: false });
    if (!project) { setProject(active); localStorage.setItem(CURRENT_PROJECT_KEY, active.id); }
    const revision = currentRevision || await createCanvasRevision(active.id, { content: novel, narrator });
    if (!currentRevision) setRevisions([revision]);
    setAnalysis(await createCanvasAnalysis(active.id, { revision_id: revision.revision_id })); toast.success("Story analysis ready.");
  });
  const createOutline = () => run("outline", async () => {
    if (!project || !currentRevision) throw new Error("Save a novel revision first.");
    setScreenplay(await createCanvasOutline(project.id, { revision_id: currentRevision.revision_id, narrator })); toast.success("Screenplay outline ready.");
  });
  const proposeEdit = () => {
    if (!selection.trim() || !instruction.trim()) { toast.error("Select text and describe the edit."); return; }
    toast.info("Edit proposal prepared locally. Review the selected passage, then save the accepted revision.");
    setNovel(novel.replace(selection, `${selection}\n\n[Requested edit: ${instruction}]`)); setSelection(""); setInstruction("");
  };

  return <AppShell><section className="mb-6 flex flex-wrap items-start justify-between gap-4"><div><Badge variant="outline">Phase 1 · Story Canvas</Badge><h2 className="mt-3 text-3xl font-semibold">Novel workspace</h2><p className="mt-2 max-w-3xl text-sm text-muted-foreground">Write the novel, inspect loose ends, make focused revisions, then turn the approved revision into a scene-by-scene screenplay outline.</p></div><Button asChild variant="outline"><Link to="/story">Open Story Builder<ArrowRight className="ml-2 h-4 w-4" /></Link></Button></section>
    <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]"><Card><CardHeader><CardTitle>Editable novel</CardTitle><CardDescription>Save creates an immutable revision. Existing project storage remains the source of truth.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="grid gap-3 md:grid-cols-2"><div className="space-y-2"><Label htmlFor="canvas-title">Project title</Label><Input id="canvas-title" value={title} onChange={(event) => setTitle(event.target.value)} /></div><div className="flex items-center justify-between rounded-xl border px-3"><Label htmlFor="narrator">Include narrator</Label><Switch id="narrator" checked={narrator} onCheckedChange={setNarrator} /></div></div><Textarea data-testid="novel-editor" className="min-h-[420px]" value={novel} onChange={(event) => setNovel(event.target.value)} placeholder="Write or paste the novel here..." /><div className="flex flex-wrap gap-2"><Button disabled={Boolean(busy)} onClick={saveRevision}><Check className="mr-2 h-4 w-4" />Save revision</Button><Button variant="outline" disabled={Boolean(busy)} onClick={analyzeStory}><Sparkles className="mr-2 h-4 w-4" />Analyze loose ends</Button><Button variant="outline" disabled={Boolean(busy) || !currentRevision} onClick={createOutline}><ArrowRight className="mr-2 h-4 w-4" />Create screenplay outline</Button></div></CardContent></Card>
      <Card><CardHeader><CardTitle>Focused edit</CardTitle><CardDescription>Select a passage, describe the change, review it, then save the resulting revision.</CardDescription></CardHeader><CardContent className="space-y-4"><Textarea value={selection} onChange={(event) => setSelection(event.target.value)} placeholder="Selected passage" /><Textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder="Instruction: clarify, expand, connect, shorten..." /><Button variant="outline" onClick={proposeEdit}><Search className="mr-2 h-4 w-4" />Prepare edit</Button><div className="rounded-xl border p-3 text-xs text-muted-foreground">The selected-range protocol is revision-based: unrelated text is preserved and every accepted change can be restored.</div></CardContent></Card></div>
    <section className="mt-6"><Tabs defaultValue="analysis"><TabsList><TabsTrigger value="analysis">AI analysis</TabsTrigger><TabsTrigger value="screenplay">Screenplay</TabsTrigger><TabsTrigger value="history"><History className="mr-2 h-4 w-4" />Revisions</TabsTrigger></TabsList><TabsContent value="analysis" className="mt-4"><Card><CardContent className="p-6">{analysis ? <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap text-sm">{JSON.stringify(analysis.content, null, 2)}</pre> : <p className="text-sm text-muted-foreground">Run analysis to see loose ends, contradictions, motivation gaps, chronology risks, and author questions.</p>}</CardContent></Card></TabsContent><TabsContent value="screenplay" className="mt-4"><Card><CardContent className="space-y-3 p-6">{screenplay ? <>{screenplayScenes.map((scene: any) => <details key={scene.scene_id} className="rounded-xl border p-4"><summary className="cursor-pointer font-medium">{scene.scene_number}. {scene.slugline || scene.scene_id}</summary><p className="mt-3 text-sm text-muted-foreground">{scene.summary}</p><p className="mt-2 text-xs">Characters: {(scene.characters_present || []).join(", ") || "none listed"} · Approx. {scene.estimated_seconds || 0}s</p></details>)}</> : <p className="text-sm text-muted-foreground">Save a revision and create a screenplay outline.</p>}</CardContent></Card></TabsContent><TabsContent value="history" className="mt-4"><Card><CardContent className="space-y-2 p-6">{revisions.map((revision) => <button key={revision.revision_id} className="block w-full rounded-xl border p-3 text-left hover:bg-secondary" onClick={() => setNovel(String(revision.content))}><p className="font-medium">{revision.revision_id}</p><p className="text-xs text-muted-foreground">{revision.created_at} · {revision.content_hash.slice(0, 12)}</p></button>)}{!revisions.length && <p className="text-sm text-muted-foreground">No revisions yet.</p>}</CardContent></Card></TabsContent></Tabs></section></AppShell>;
}
